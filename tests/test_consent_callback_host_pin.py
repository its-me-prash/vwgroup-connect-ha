# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The consent-skip callback is a request target named by a remote party.

Both consent-skip methods — the IDK one and the EU Data Act port of it — read
``callback=`` out of the URL of the page they landed on and then FETCH it with
the client's own headers. Nothing checked where it pointed. ``urljoin`` returns
an absolute URL unchanged, so a ``callback=https://elsewhere/`` on a consent
page turned into a request issued from the owner's Home Assistant to a host of
someone else's choosing.

This is not a hypothetical shape to worry about in the abstract: both reference
implementations the portal operator points maintainers at validate that target,
and the ioBroker one added exactly this validation on 2026-10-08.

**The refusal is deliberately generous, because the likelier harm is a false
refusal.** Rejecting a legitimate callback ends the login in
``MarketingConsentError``, and that is certain where a diversion is
hypothetical. Three targets are accepted: the host that served the consent page
(which is what every relative callback resolves to, and what the brand IDPs
are), ``vwgroup.io`` with its subdomains, and the portal's own host.

The same file carried two more guards of this class on the cookie path, written
as ``"vwgroup.io" not in domain``. A substring test admits
``vwgroup.io.attacker.com`` and ``evil-vwgroup.io``; the import side would have
restored such a cookie into the jar and then sent it to that host. The correct
form was already documented a few hundred lines away in another module (#632) —
these two copies had been left behind.
"""
from __future__ import annotations

from typing import Any

import pytest

from custom_components.vag_connect.cariad._util import (
    host_in_domains,
    is_https_on_domains,
)
from custom_components.vag_connect.cariad.auth._eu_data_act import EUDataActConnector
from custom_components.vag_connect.cariad.exceptions import MarketingConsentError

_PORTAL_LANDING = "https://eu-data-act.vwgroup-datahub.com/dashboard"
_SIGNIN_HTML = (
    '<form action="/signin-service/v1/CLIENT/login/identifier">'
    '<input type="hidden" name="hmac" value="email_hmac">'
    '<input type="hidden" name="_csrf" value="csrf1">'
    '<input type="hidden" name="relayState" value="rs1">'
    "</form>"
)
_PASSWORD_HTML = (
    "<script>window._IDK = {templateModel: "
    '{"hmac":"fresh_pw_hmac","relayState":"rs1",'
    '"postAction":"/signin-service/v1/CLIENT/login/authenticate"}, '
    'csrf_token: "csrf2"};</script>'
)
_MARKETING_HTML = (
    '<script>window._IDK = {templateModel: {"template":"marketing-consent"}};</script>'
)
_CONSENT = "https://identity.vwgroup.io/signin-service/v1/CLIENT/consent/marketing"


# ── the pure helper, where the boundary actually lives ───────────────────────
class TestTheBoundaryCheck:
    def test_an_exact_host_and_a_true_subdomain_pass(self) -> None:
        assert host_in_domains("vwgroup.io", "vwgroup.io")
        assert host_in_domains("identity.vwgroup.io", "vwgroup.io")
        assert host_in_domains("cupraid.vwgroup.io", "vwgroup.io")
        assert host_in_domains("a.b.c.vwgroup.io", "vwgroup.io")

    def test_the_two_lookalikes_a_substring_test_would_admit(self) -> None:
        """The whole reason this function exists. Both of these contain the
        string "vwgroup.io" and neither is ours."""
        assert not host_in_domains("vwgroup.io.attacker.com", "vwgroup.io")
        assert not host_in_domains("evil-vwgroup.io", "vwgroup.io")
        # And the other direction: a prefix of our domain is not our domain.
        assert not host_in_domains("group.io", "vwgroup.io")
        assert not host_in_domains("io", "vwgroup.io")

    def test_a_cookie_domains_leading_dot_and_a_trailing_root_dot(self) -> None:
        """Cookie domains are written ``.vwgroup.io``, and a fully-qualified
        host may carry a trailing root dot. Neither may change the verdict."""
        assert host_in_domains(".vwgroup.io", "vwgroup.io")
        assert host_in_domains(".identity.vwgroup.io", "vwgroup.io")
        assert host_in_domains("identity.vwgroup.io.", "vwgroup.io")
        assert not host_in_domains(".vwgroup.io.attacker.com", "vwgroup.io")

    def test_case_is_irrelevant_and_emptiness_is_a_refusal(self) -> None:
        assert host_in_domains("IDENTITY.VWGroup.IO", "vwgroup.io")
        assert not host_in_domains("", "vwgroup.io")
        assert not host_in_domains(None, "vwgroup.io")
        assert not host_in_domains("identity.vwgroup.io")  # no domains given

    def test_several_domains_are_an_or(self) -> None:
        assert is_https_on_domains(
            "https://eu-data-act.example.com/x", "vwgroup.io", "eu-data-act.example.com"
        )

    def test_the_scheme_is_pinned_too(self) -> None:
        """Half the point. A host check alone would still allow a downgrade to
        cleartext, or a ``file:`` read."""
        assert not is_https_on_domains("http://identity.vwgroup.io/x", "vwgroup.io")
        assert not is_https_on_domains("file:///etc/passwd", "vwgroup.io")
        assert not is_https_on_domains("//identity.vwgroup.io/x", "vwgroup.io")
        assert not is_https_on_domains("", "vwgroup.io")
        assert not is_https_on_domains(None, "vwgroup.io")
        assert is_https_on_domains("https://identity.vwgroup.io/x", "vwgroup.io")

    def test_a_url_with_credentials_or_a_port_is_judged_on_the_host(self) -> None:
        """``urlsplit().hostname`` is the host, not the authority — so neither a
        port nor a userinfo section can smuggle a different one past it. The
        userinfo trick is the classic: everything before the @ is ignored by
        the fetcher."""
        assert is_https_on_domains("https://identity.vwgroup.io:443/x", "vwgroup.io")
        assert not is_https_on_domains(
            "https://identity.vwgroup.io@attacker.example/x", "vwgroup.io"
        )


# ── the portal consent-skip, end to end ──────────────────────────────────────
class _Resp:
    def __init__(self, url: str, *, status: int = 200, text: str = "") -> None:
        self.url, self.status, self._text = url, status, text
        self.headers: dict[str, str] = {}

    async def __aenter__(self) -> "_Resp":
        return self

    async def __aexit__(self, *_a: Any) -> bool:
        return False

    async def text(self, errors: str | None = None) -> str:  # noqa: ARG002
        return self._text


class _Session:
    """prime -> authorize -> identifier -> credential POST -> (callback).

    Any GET that is not one of the two expected steps is recorded AND raises,
    so "the guard refused and nothing was fetched" is checkable rather than
    assumed.
    """

    def __init__(self, cred_landing: str, callback_landing: str | None = None) -> None:
        self._cred = cred_landing
        self._cb = callback_landing
        self.unexpected: list[str] = []

    def get(self, url: str, **_kw: Any) -> _Resp:
        if url.endswith("/") and "vwgroup-datahub" in url:
            return _Resp(url, text="<html>portal</html>")
        if "authorize" in url:
            return _Resp(
                "https://identity.vwgroup.io/signin-service/v1/CLIENT/login/identifier",
                text=_SIGNIN_HTML,
            )
        if self._cb is not None:
            return _Resp(self._cb, text="<html>logged in</html>")
        self.unexpected.append(url)
        raise AssertionError(f"the guard let this through: {url}")

    def post(self, url: str, **_kw: Any) -> _Resp:
        if url.endswith("/login/identifier"):
            return _Resp(
                "https://identity.vwgroup.io/signin-service/v1/CLIENT/login/"
                "authenticate?relayState=rs1",
                text=_PASSWORD_HTML,
            )
        if "/login/authenticate" in url:
            return _Resp(self._cred, text=_MARKETING_HTML)
        raise AssertionError(f"unmatched POST {url}")


async def _login(cred_landing: str, callback_landing: str | None = None) -> _Session:
    sess = _Session(cred_landing, callback_landing)
    conn = EUDataActConnector(sess)  # type: ignore[arg-type]
    await conn.login("user@example.com", "secret")
    return sess


class TestTheLegitimateShapesStillWork:
    """The regression half, and the one that matters more day to day: a false
    refusal breaks every portal login that meets this page."""

    @pytest.mark.asyncio
    async def test_the_measured_shape_an_identity_callback(self) -> None:
        sess = await _login(
            f"{_CONSENT}?callback=https://identity.vwgroup.io/oidc/v1/callback/success",
            _PORTAL_LANDING,
        )
        assert sess.unexpected == []

    @pytest.mark.asyncio
    async def test_a_relative_callback_resolves_against_the_page(self) -> None:
        """Nothing says VW must send an absolute one, and a relative value
        resolves to the host that served the page — which is by definition not
        a diversion."""
        sess = await _login(f"{_CONSENT}?callback=/oidc/v1/callback/success",
                            _PORTAL_LANDING)
        assert sess.unexpected == []

    @pytest.mark.asyncio
    async def test_a_brand_idp_callback(self) -> None:
        sess = await _login(
            f"{_CONSENT}?callback=https://cupraid.vwgroup.io/oidc/v1/done",
            _PORTAL_LANDING,
        )
        assert sess.unexpected == []

    @pytest.mark.asyncio
    async def test_a_callback_back_to_the_portal_itself(self) -> None:
        sess = await _login(
            f"{_CONSENT}?callback=https://eu-data-act.vwgroup-datahub.com/cb",
            _PORTAL_LANDING,
        )
        assert sess.unexpected == []


class TestTheDiversionIsRefused:
    @pytest.mark.asyncio
    async def test_a_foreign_host_is_not_fetched_and_the_login_falls_through(
        self,
    ) -> None:
        """The reported shape. Refusing must degrade to the behaviour a missing
        callback already has — the classifier's MarketingConsentError — and it
        must not issue the request first."""
        sess = _Session(f"{_CONSENT}?callback=https://attacker.example/steal")
        conn = EUDataActConnector(sess)  # type: ignore[arg-type]
        with pytest.raises(MarketingConsentError):
            await conn.login("user@example.com", "secret")
        assert sess.unexpected == [], "the off-domain callback was fetched"

    @pytest.mark.asyncio
    async def test_the_lookalike_host_is_refused(self) -> None:
        sess = _Session(f"{_CONSENT}?callback=https://vwgroup.io.attacker.example/x")
        conn = EUDataActConnector(sess)  # type: ignore[arg-type]
        with pytest.raises(MarketingConsentError):
            await conn.login("user@example.com", "secret")
        assert sess.unexpected == []

    @pytest.mark.asyncio
    async def test_a_cleartext_callback_is_refused(self) -> None:
        sess = _Session(f"{_CONSENT}?callback=http://identity.vwgroup.io/oidc/v1/cb")
        conn = EUDataActConnector(sess)  # type: ignore[arg-type]
        with pytest.raises(MarketingConsentError):
            await conn.login("user@example.com", "secret")
        assert sess.unexpected == []


# ── all four sites, pinned structurally ──────────────────────────────────────
def test_no_substring_host_test_survives_in_the_auth_modules() -> None:
    """The form that was wrong, searched for by its shape rather than by its
    line number. ``"vwgroup.io" not in domain`` is the exact text that admitted
    a lookalike host, and the correct boundary check now exists as a helper, so
    a reappearance is a regression and not a style choice.
    """
    import pathlib

    root = pathlib.Path(__file__).resolve().parent.parent / "custom_components"
    offenders: list[str] = []
    for path in (root / "vag_connect").rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for num, line in enumerate(text.splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            if '"vwgroup.io" not in' in stripped or "'vwgroup.io' not in" in stripped:
                offenders.append(f"{path.name}:{num}")
    assert not offenders, (
        "a substring host test is back — it admits vwgroup.io.attacker.com: "
        f"{offenders}"
    )


def test_both_consent_skip_methods_pin_the_callback_target() -> None:
    """Read off each method's own source, so a guard sitting in some unrelated
    function cannot satisfy this. The IDK method is the original and the portal
    one is its port; fixing only one would leave the other channel open, which
    is how this came to exist in two places at once.
    """
    import ast
    import inspect

    from custom_components.vag_connect.cariad.auth import _eu_data_act, idk

    for module, method in (
        (_eu_data_act, "_skip_marketing_consent_landing"),
        (idk, "_skip_marketing_consent"),
    ):
        src = inspect.getsource(module)
        body = ""
        for node in ast.walk(ast.parse(src)):
            if (
                isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                and node.name == method
            ):
                body = ast.get_source_segment(src, node) or ""
        assert body, f"{module.__name__}.{method} not found — renamed?"
        assert "is_https_on_domains" in body, (
            f"{module.__name__}.{method} fetches the callback target without "
            "pinning where it points"
        )
        # And it must be pinned BEFORE the fetch, or it is decoration.
        guard_at = body.index("is_https_on_domains")
        fetch_at = min(
            (body.index(tok) for tok in ("self._session.get", "_follow_login_redirects")
             if tok in body),
            default=-1,
        )
        assert fetch_at != -1, f"no fetch found in {module.__name__}.{method}"
        assert guard_at < fetch_at, (
            f"{module.__name__}.{method} pins the target after fetching it"
        )
