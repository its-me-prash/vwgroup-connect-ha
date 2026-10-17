# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#1712 — the EU sign-in attestation wall on the CARIAD BFF token endpoint.

The login itself works: the right page, the right POST, ``authenticated``, and
an authorization code comes back. Trading that code for a token is what fails,
with ``400`` and the OAuth error ``invalid assertion headers`` — a statement
about the headers we sign the request with, not about the account.

Measured against the shipping app rather than inferred: myAudi 5.8.1 carries no
``qmauth`` symbol in any of its six DEX files or its native libraries, nor the
HMAC secret this integration signs ``x-qmauth`` with, while it does carry the
Play Integrity client and still sends ``x-assertion``. So once every qmauth
secret has drawn that answer, the rest of the ``client_id × qmauth`` walk cannot
change it, and spending it costs six (Audi) or eight (VW EU) rejected sign-ins per login (a failed
refresh falls back to a login) against an endpoint this project elsewhere warns
about rate-limiting.

This mirrors #1165/#659 (the North-American wall), whose handling these tests
follow deliberately: same fail-fast, same "not a credentials issue" wording,
same discrimination before the generic ``AuthenticationError``.

Verified here:
1. The exception exists and IS an ``AuthenticationError`` subclass — the config
   flow and the coordinator catch it FIRST, and the strategy loop in
   ``authenticate()`` hands it on when the portal fallback fails generically,
   so VW EU and Audi owners are not told their password is wrong.
2. ``_map_error`` routes the key to itself, not to ``cannot_connect``.
3. The detector fires on the real marker and stays quiet on everything else —
   including the other ``400`` the same endpoint returns.
4. ``strings.json`` and all 12 translations declare the key.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from custom_components.vag_connect.cariad.auth.idk import _EU_ATTESTATION_ERROR
from custom_components.vag_connect.cariad._util import oauth_error_code
from custom_components.vag_connect.cariad.exceptions import (
    AuthenticationError,
    EuropeAttestationError,
    NorthAmericaAttestationError,
)

_ROOT = Path(__file__).parents[1] / "custom_components" / "vag_connect"

# The live rejection, as measured on an Audi account (2026-10-16).
_WALL_BODY = json.dumps({"error": "invalid assertion headers"})
# Other 400s the same endpoint really returns — these must keep walking the
# candidate chain, because a different client_id genuinely can fix them.
_OTHER_BODIES = (
    json.dumps({"error": "invalid_grant"}),
    json.dumps({"errorCode": "USER_NOT_AUTHORIZED"}),
    json.dumps({"errorCode": "INVALID_REQUEST"}),
    json.dumps({"errorCode": "METHOD_NOT_ALLOWED"}),
    json.dumps({"errorCode": "RS.security.9007"}),
    "",
    "<html>gateway</html>",
)


class TestExceptionClass:
    def test_is_an_authentication_error_like_its_na_twin(self) -> None:
        # The idk token-exchange loop re-raises AuthenticationError subclasses;
        # the config flow discriminates by catching this one first.
        assert issubclass(EuropeAttestationError, AuthenticationError)
        assert issubclass(NorthAmericaAttestationError, AuthenticationError)

    def test_it_is_not_the_na_error(self) -> None:
        # Two different walls, two different messages, two different keys.
        assert not issubclass(EuropeAttestationError, NorthAmericaAttestationError)
        assert not issubclass(NorthAmericaAttestationError, EuropeAttestationError)

    def test_message_names_attestation_and_the_status(self) -> None:
        msg = str(EuropeAttestationError(
            f"Sign-in blocked by VW device attestation "
            f"(HTTP 400, {_EU_ATTESTATION_ERROR})"
        ))
        assert "attestation" in msg.lower()
        assert "400" in msg


class TestTheMarker:
    def test_the_detector_reads_the_measured_body(self) -> None:
        # The production rule is `oauth_error_code(body).lower() == const`.
        # Assert on that composition, not on a reimplementation of it.
        assert oauth_error_code(_WALL_BODY).lower() == _EU_ATTESTATION_ERROR

    def test_the_marker_survives_the_error_token_gate(self) -> None:
        # safe_error_token() is deliberately narrow and allows exactly one
        # spaced value. If that gate tightened, the detector would silently
        # stop firing and the full candidate walk would come back.
        assert oauth_error_code(_WALL_BODY) != ""

    @pytest.mark.parametrize("body", _OTHER_BODIES)
    def test_other_rejections_do_not_match(self, body: str) -> None:
        assert oauth_error_code(body).lower() != _EU_ATTESTATION_ERROR

    def test_casing_from_the_backend_does_not_decide(self) -> None:
        shouty = json.dumps({"error": "Invalid Assertion Headers"})
        assert oauth_error_code(shouty).lower() == _EU_ATTESTATION_ERROR


def _session_answering(
    status: int, body: str, *, bodies: list[str] | None = None,
) -> tuple[object, list]:
    """A session whose POST answers *status* with *body* (or, per call, the next
    of *bodies*), recording each call."""
    from unittest.mock import AsyncMock, MagicMock

    posts: list = []

    def _post(url, **kwargs):  # noqa: ANN001, ANN202
        posts.append(url)
        resp = AsyncMock()
        resp.__aenter__ = AsyncMock(return_value=resp)
        resp.__aexit__ = AsyncMock(return_value=False)
        resp.status = status
        answer = bodies[len(posts) - 1] if bodies else body
        resp.text = AsyncMock(return_value=answer)
        return resp

    session = MagicMock()
    session.post = MagicMock(side_effect=_post)
    return session, posts


_CIDS = ["cid-a@apps_vw-dilab_com", "cid-b@apps_vw-dilab_com", "cid-c@apps_vw-dilab_com"]
_QMS = [("aa" * 16, "qm-current"), ("bb" * 16, "qm-prior")]


@pytest.fixture
def _fixed_chain(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pin the candidate chain to 3 client_ids × 2 qmauth pairs."""
    from custom_components.vag_connect.cariad.auth import _auth_config_resolver as r

    monkeypatch.setattr(r.AuthConfigResolver, "oauth_client_id_chain", lambda self: list(_CIDS))
    monkeypatch.setattr(r.AuthConfigResolver, "qmauth_chain", lambda self: list(_QMS))


@pytest.mark.usefixtures("_fixed_chain")
class TestFailFast:
    """The point of the fix: two rejected sign-ins instead of six or eight.

    Six (Audi) or eight (VW EU) rejected attempts land on the IDP per login (and a refresh that
    fails falls back to a login), on an endpoint this project warns about
    elsewhere (``RateLimitError``: "nicht hochfrequent retry'n — sonst
    Account-Lockout"). Once every qmauth secret has drawn the wall, no other
    client_id can change the answer about the headers, so the rest is pure cost.
    """

    def test_the_wall_stops_once_every_qmauth_secret_is_refused(self) -> None:
        import asyncio

        from custom_components.vag_connect.cariad.auth.idk import IDKAuth
        from custom_components.vag_connect.cariad.models import BRAND_AUDI

        session, posts = _session_answering(400, _WALL_BODY)
        auth = IDKAuth(session, BRAND_AUDI)
        with pytest.raises(EuropeAttestationError):
            asyncio.run(auth._exchange_code("thecode", "theverifier"))
        assert len(posts) == len(_QMS), (
            f"walked {len(posts)} candidates against an attestation wall; "
            "each one is a rejected sign-in on the IDP"
        )

    def test_one_refused_secret_does_not_stop_the_walk(self) -> None:
        # GUARD: the chain carries the PRIOR qmauth pair for VW re-rotations,
        # and a stale secret plausibly draws the same answer. While another
        # secret has not been refused that way, the walk must go on.
        import asyncio

        from custom_components.vag_connect.cariad.auth.idk import IDKAuth
        from custom_components.vag_connect.cariad.models import BRAND_AUDI

        grant = json.dumps({"error": "invalid_grant"})
        # Order is client_id-major: (a,current) (a,prior) (b,current) …
        bodies = [_WALL_BODY, grant] * len(_CIDS)
        session, posts = _session_answering(400, "", bodies=bodies)
        auth = IDKAuth(session, BRAND_AUDI)
        with pytest.raises(AuthenticationError) as err:
            asyncio.run(auth._exchange_code("thecode", "theverifier"))
        assert not isinstance(err.value, EuropeAttestationError)
        assert len(posts) == len(_CIDS) * len(_QMS)

    def test_a_brand_without_assertion_headers_is_not_judged_by_it(self) -> None:
        # Only Audi/VW sign assertion headers. Any other brand sharing this
        # branch walks its client_id chain whatever the body says.
        import asyncio

        from custom_components.vag_connect.cariad.auth.idk import IDKAuth
        from custom_components.vag_connect.cariad.models import BRAND_SEAT

        session, posts = _session_answering(400, _WALL_BODY)
        auth = IDKAuth(session, BRAND_SEAT)
        with pytest.raises(AuthenticationError) as err:
            asyncio.run(auth._exchange_code("thecode", "theverifier"))
        assert not isinstance(err.value, EuropeAttestationError)
        assert len(posts) > 1

    def test_a_plain_rejection_still_walks_the_chain(self) -> None:
        # GUARD: the fail-fast must be specific to the wall. A bare
        # invalid_grant can genuinely be fixed by another client_id, so that
        # chain has to keep working exactly as before.
        import asyncio

        from custom_components.vag_connect.cariad.auth.idk import IDKAuth
        from custom_components.vag_connect.cariad.models import BRAND_AUDI

        session, posts = _session_answering(400, json.dumps({"error": "invalid_grant"}))
        auth = IDKAuth(session, BRAND_AUDI)
        with pytest.raises(AuthenticationError) as err:
            asyncio.run(auth._exchange_code("thecode", "theverifier"))
        assert not isinstance(err.value, EuropeAttestationError)
        assert len(posts) > 1, "the client_id × qmauth chain stopped being walked"


class TestConfigFlowMapping:
    def test_map_error_keeps_the_key(self) -> None:
        from custom_components.vag_connect.config_flow import _map_error

        # Unlisted keys silently become "cannot_connect", which is how a new
        # error reaches the user as a generic one.
        assert _map_error("eu_signin_attestation") == "eu_signin_attestation"

    def test_the_na_twin_still_maps(self) -> None:
        from custom_components.vag_connect.config_flow import _map_error

        assert _map_error("na_signin_attestation") == "na_signin_attestation"

    def test_it_is_caught_before_the_generic_authentication_error(self) -> None:
        # EuropeAttestationError is a subclass, so order decides whether the
        # user is told the truth or told their password is wrong. Compare the
        # source positions of the two except-branches.
        src = (_ROOT / "config_flow.py").read_text(encoding="utf-8")
        specific = src.index("except EuropeAttestationError")
        generic = src.index("except AuthenticationError")
        assert specific < generic


class TestTranslations:
    def test_every_shipped_language_declares_the_key(self) -> None:
        files = [_ROOT / "strings.json", *sorted((_ROOT / "translations").glob("*.json"))]
        assert len(files) >= 13  # strings.json + 12 languages
        for path in files:
            data = json.loads(path.read_text(encoding="utf-8"))
            text = data["config"]["error"]["eu_signin_attestation"]
            assert text.strip(), path.name

    def test_the_text_does_not_blame_the_password(self) -> None:
        # The whole point: the credentials are fine. A translation that tells
        # the user to check them would undo the fix for that language.
        data = json.loads((_ROOT / "strings.json").read_text(encoding="utf-8"))
        text = data["config"]["error"]["eu_signin_attestation"].lower()
        assert "1712" in text
        assert "play integrity" in text


class TestRuntimePath:
    """The config flow was not the only place that read this as a bad password."""

    def test_setup_catches_it_before_the_generic_authentication_error(self) -> None:
        # Same ordering trap as the config flow: as a subclass it would
        # otherwise land on "invalid_credentials" and prompt for a password
        # that is already right.
        src = (_ROOT / "coordinator.py").read_text(encoding="utf-8")
        specific = src.index("except EuropeAttestationError")
        generic = src.index("except AuthenticationError as err:\n            raise ValueError(\"invalid_credentials\")")
        assert specific < generic
        assert 'raise ValueError("eu_signin_attestation")' in src

    def test_the_setup_reason_is_hard(self) -> None:
        # The wall does not clear on its own. As a soft ConfigEntryNotReady HA
        # would re-run the whole login on every backoff tick (#909), against a
        # rate-limited endpoint, while the message says retrying cannot help.
        from custom_components.vag_connect import (
            _HARD_AUTH_SETUP_ERRORS,
            _SETUP_ERRORS,
        )

        assert "eu_signin_attestation" in _SETUP_ERRORS
        assert "eu_signin_attestation" in _HARD_AUTH_SETUP_ERRORS

    def test_no_text_promises_portal_data(self) -> None:
        # The reason only surfaces once the portal fallback has failed too, so
        # no text may claim the data is still flowing through it.
        files = [_ROOT / "strings.json", *sorted((_ROOT / "translations").glob("*.json"))]
        for path in files:
            if path.name not in ("strings.json", "en.json"):
                continue
            data = json.loads(path.read_text(encoding="utf-8"))
            for text in (
                data["config"]["error"]["eu_signin_attestation"],
                data["issues"]["eu_signin_attestation"]["description"],
            ):
                assert "still flows" not in text, path.name
                assert "data sharing" in text, path.name

    def test_the_repair_has_its_own_copy_in_every_language(self) -> None:
        files = [_ROOT / "strings.json", *sorted((_ROOT / "translations").glob("*.json"))]
        for path in files:
            issue = json.loads(path.read_text(encoding="utf-8"))["issues"][
                "eu_signin_attestation"
            ]
            assert issue["title"].strip() and issue["description"].strip(), path.name
            assert "{brand}" in issue["title"], path.name

    def test_the_repair_is_cleared_after_a_good_login(self) -> None:
        src = (_ROOT / "repairs.py").read_text(encoding="utf-8")
        assert src.count('"eu_signin_attestation"') >= 3  # map, key, clear list


def _strategy_client(brand: str = "audi"):
    """A brand client stub whose IDK strategies hit the wall."""
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from custom_components.vag_connect.cariad.api.base import CariadBaseClient

    me = CariadBaseClient.__new__(CariadBaseClient)
    me._brand = SimpleNamespace(name=brand)
    me._email = "owner@example.com"
    me._password = "right-password"
    me._spin = ""
    me._use_website_proxy = False
    me._tokens = None
    me._auth = SimpleNamespace(authenticate=AsyncMock(
        side_effect=EuropeAttestationError("Sign-in blocked by VW device attestation")
    ))
    return me


class TestStrategyLoop:
    """The strategy loop in ``authenticate()`` stood between the wall and every
    catch above: VW and Audi end on the portal strategy, so before this only
    the portal's own error ever reached the user."""

    @pytest.mark.asyncio
    async def test_a_generic_portal_failure_hands_on_the_attestation_error(self) -> None:
        me = _strategy_client()

        async def _portal_fails() -> None:
            raise AuthenticationError("portal login failed")

        me._arm_eu_portal = _portal_fails
        with pytest.raises(EuropeAttestationError) as err:
            await me.authenticate()
        assert isinstance(err.value.__cause__, AuthenticationError)

    @pytest.mark.asyncio
    async def test_an_unexpected_portal_crash_hands_it_on_too(self) -> None:
        me = _strategy_client(brand="volkswagen")

        async def _portal_crashes() -> None:
            raise RuntimeError("boom")

        me._arm_eu_portal = _portal_crashes
        with pytest.raises(EuropeAttestationError):
            await me.authenticate()

    @pytest.mark.asyncio
    async def test_a_specific_portal_stop_keeps_precedence(self) -> None:
        # GUARD: a portal stop names an action the user can take; the wall
        # must not hide it.
        from custom_components.vag_connect.cariad.exceptions import (
            PortalInteractionRequiredError,
        )

        me = _strategy_client()

        async def _portal_needs_action() -> None:
            raise PortalInteractionRequiredError("accept terms")

        me._arm_eu_portal = _portal_needs_action
        with pytest.raises(PortalInteractionRequiredError):
            await me.authenticate()

    @pytest.mark.asyncio
    async def test_a_working_portal_still_wins(self) -> None:
        me = _strategy_client()
        me._notify_tokens_changed = __import__("unittest.mock").mock.AsyncMock()

        async def _portal_ok() -> None:
            return None

        me._arm_eu_portal = _portal_ok
        await me.authenticate()  # no exception: reads continue on the portal
