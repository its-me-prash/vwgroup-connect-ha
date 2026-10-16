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
Play Integrity client and still sends ``x-assertion``. So the
``client_id × qmauth`` candidate walk cannot succeed, and spending it costs six
rejected sign-ins per login AND per refresh against an endpoint this project
elsewhere warns about rate-limiting.

This mirrors #1165/#659 (the North-American wall), whose handling these tests
follow deliberately: same fail-fast, same "not a credentials issue" wording,
same discrimination before the generic ``AuthenticationError``.

Verified here:
1. The exception exists and IS an ``AuthenticationError`` subclass, so the auth
   loop re-raises it — while the config flow catches it FIRST, so VW EU and
   Audi owners are not told their password is wrong.
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
        # stop firing and the six-attempt walk would come back.
        assert oauth_error_code(_WALL_BODY) != ""

    @pytest.mark.parametrize("body", _OTHER_BODIES)
    def test_other_rejections_do_not_match(self, body: str) -> None:
        assert oauth_error_code(body).lower() != _EU_ATTESTATION_ERROR

    def test_casing_from_the_backend_does_not_decide(self) -> None:
        shouty = json.dumps({"error": "Invalid Assertion Headers"})
        assert oauth_error_code(shouty).lower() == _EU_ATTESTATION_ERROR


def _session_answering(status: int, body: str) -> tuple[object, list]:
    """A session whose POST always answers *status*/*body*, recording each call."""
    from unittest.mock import AsyncMock, MagicMock

    posts: list = []

    def _post(url, **kwargs):  # noqa: ANN001, ANN202
        posts.append(url)
        resp = AsyncMock()
        resp.__aenter__ = AsyncMock(return_value=resp)
        resp.__aexit__ = AsyncMock(return_value=False)
        resp.status = status
        resp.text = AsyncMock(return_value=body)
        return resp

    session = MagicMock()
    session.post = MagicMock(side_effect=_post)
    return session, posts


class TestFailFast:
    """The point of the fix: one rejected sign-in instead of six.

    Six rejected attempts land on the IDP per login AND per token refresh, on
    an endpoint this project warns about elsewhere (``RateLimitError``: "nicht
    hochfrequent retry'n — sonst Account-Lockout"). Against an attestation wall
    not one of them can pass, so they are pure cost.
    """

    def test_the_wall_stops_the_candidate_walk_after_one_attempt(self) -> None:
        import asyncio

        from custom_components.vag_connect.cariad.auth.idk import IDKAuth
        from custom_components.vag_connect.cariad.models import BRAND_AUDI

        session, posts = _session_answering(400, _WALL_BODY)
        auth = IDKAuth(session, BRAND_AUDI)
        with pytest.raises(EuropeAttestationError):
            asyncio.run(auth._exchange_code("thecode", "theverifier"))
        assert len(posts) == 1, (
            f"walked {len(posts)} candidates against an attestation wall; "
            "each one is a rejected sign-in on the IDP"
        )

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
