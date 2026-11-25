# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#2200 — a sign-in that stops on a consent page gets its own message.

On 5.6.1 the reporter's volkswagen.de sign-in ended after the e-mail code at
``identity.vwgroup.io/v2/login/ui/consent``. The dialog said the sign-in failed
at a later step and pointed at the log, which is true but leaves the user to
guess. The page was a consent question on the account; after he answered it in
a normal browser sign-in, the channel was added on the first try.

#1827 is the same situation one host over: an optional consent hook on
``consent.vwgroup.io/hooks/...``. The connector declines it when the page offers
a skip link; when it does not, the sign-in stops there, and two reporters only
got past it by answering it in a browser.

Pinned here:
- a stop on either consent page raises ``WebsiteConsentRequiredError``, still a
  ``WebsiteLoginIncompleteError`` (so every older handler keeps working), and
  the message names host and path, never the query;
- any other stop stays a plain ``WebsiteLoginIncompleteError``, and a lookalike
  host or path is not taken for a consent page;
- the setup, options and repair dialogs show ``website_consent_required`` for
  it, at the code step and at the password step;
- the key passes the setup allowlist and has a text in every place and every
  language that has ``website_login_failed``.
"""
from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.vag_connect._vwde_reauth import VwDeReauthMixin
from custom_components.vag_connect.cariad.auth import _website_authproxy as wap
from custom_components.vag_connect.cariad.auth._website_authproxy import (
    WebsiteAuthProxyConnector,
)
from custom_components.vag_connect.cariad.exceptions import (
    WebsiteConsentRequiredError,
    WebsiteLoginIncompleteError,
)

CHALLENGE = "https://identity.vwgroup.io/u/email-challenge?state=ST"
CHALLENGE_FORM = (
    '<html><body><form method="post" action="/u/email-challenge?state=ST">'
    '<input type="hidden" name="_csrf" value="C1">'
    '<input type="text" name="code" value="">'
    "</form></body></html>"
)
# The reporter's landing point, with a state that must never reach the log.
IDENTITY_CONSENT = "https://identity.vwgroup.io/v2/login/ui/consent?state=SECRETSTATE"
# #1827's hook, served without a skip link, so the decline cannot remove it.
HOOK_CONSENT = "https://consent.vwgroup.io/hooks/marketing?state=SECRETSTATE"
OTHER_STOP = "https://identity.vwgroup.io/u/login/identifier?state=SECRETSTATE"
PORTAL_OK = "https://www.volkswagen.de/de/besitzer-und-nutzer/myvolkswagen.html"

COMPONENT = Path(__file__).resolve().parents[1] / "custom_components" / "vag_connect"


class _Resp:
    def __init__(self, url: str, status: int, text: str = "") -> None:
        self.url, self.status, self._text = url, status, text
        self.history: tuple[Any, ...] = ()

    async def __aenter__(self) -> _Resp:
        return self

    async def __aexit__(self, *_exc: Any) -> bool:
        return False

    async def text(self, errors: str | None = None) -> str:  # noqa: ARG002
        return self._text


class _Session:
    """The code POST lands on ``landed``; nothing else is requested."""

    def __init__(self, landed: str, status: int = 200) -> None:
        self._landed, self._status = landed, status
        self.closed = False

    def post(self, _url: str, **_kw: Any) -> _Resp:
        return _Resp(self._landed, self._status)

    def get(self, url: str, **_kw: Any) -> _Resp:
        raise AssertionError(f"unexpected GET {url}")


def _connector(landed: str) -> WebsiteAuthProxyConnector:
    c = WebsiteAuthProxyConnector.__new__(WebsiteAuthProxyConnector)
    c._session = _Session(landed)
    c._resume_dead_this_cycle = False
    c.logged_in = False
    c._headers = MagicMock(return_value={})
    c._otp_url = CHALLENGE
    c._otp_html = CHALLENGE_FORM
    c._otp_state = "ST"
    return c


def _run(coro: Any) -> Any:
    return asyncio.new_event_loop().run_until_complete(coro)


# ── the connector ─────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("landed", "where"),
    [
        (IDENTITY_CONSENT, "identity.vwgroup.io/v2/login/ui/consent"),
        (HOOK_CONSENT, "consent.vwgroup.io/hooks/marketing"),
    ],
)
def test_a_stop_on_a_consent_page_is_its_own_error(landed: str, where: str) -> None:
    with pytest.raises(WebsiteConsentRequiredError) as excinfo:
        _run(_connector(landed).submit_otp("123456"))
    msg = str(excinfo.value)
    assert where in msg
    assert "SECRETSTATE" not in msg, "the query must not travel in the message"
    assert isinstance(excinfo.value, WebsiteLoginIncompleteError), (
        "every handler of the parent must keep working"
    )


def test_another_stop_is_not_called_a_consent_page() -> None:
    with pytest.raises(WebsiteLoginIncompleteError) as excinfo:
        _run(_connector(OTHER_STOP).submit_otp("123456"))
    assert not isinstance(excinfo.value, WebsiteConsentRequiredError)


@pytest.mark.parametrize(
    "landed",
    [
        # trailing slash: still the consent page
        "https://identity.vwgroup.io/v2/login/ui/consent/?state=S",
        # another spelling of the same segment
        "https://identity.vwgroup.io/v2/login/ui/Consent?state=S",
    ],
)
def test_other_spellings_of_the_consent_path_count(landed: str) -> None:
    with pytest.raises(WebsiteConsentRequiredError):
        _run(_connector(landed).submit_otp("123456"))


@pytest.mark.parametrize(
    "landed",
    [
        # a lookalike host that merely starts with the real one
        "https://identity.vwgroup.io.example.com/v2/login/ui/consent",
        # the same for the consent-hook host
        "https://consent.vwgroup.io.example.com/hooks/marketing",
        # the word in the middle of a path is not the consent page
        "https://identity.vwgroup.io/v2/consent/info",
        # the word in the query is not the consent page
        "https://identity.vwgroup.io/u/login/identifier?next=consent",
        # another host's consent path
        "https://example.com/v2/login/ui/consent",
    ],
)
def test_a_lookalike_is_not_taken_for_a_consent_page(landed: str) -> None:
    with pytest.raises(WebsiteLoginIncompleteError) as excinfo:
        _run(_connector(landed).submit_otp("123456"))
    assert not isinstance(excinfo.value, WebsiteConsentRequiredError)


def test_a_completed_sign_in_is_untouched() -> None:
    c = _connector(PORTAL_OK)
    assert _run(c.submit_otp("123456")) is True
    assert c.logged_in is True


# ── the code step in all three dialogs ───────────────────────────────────────


class _Options(VwDeReauthMixin):
    def __init__(self, connector: WebsiteAuthProxyConnector | None = None) -> None:
        self.hass = MagicMock()
        self.ovw_reset()
        self._ovw_connector = connector


def test_options_code_step_names_the_consent_page(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    flow = _Options(_connector(IDENTITY_CONSENT))
    with pytest.raises(ValueError, match="^website_consent_required$"):
        _run(flow._ovw_submit_otp("123456"))
    assert any(
        r.levelno == logging.WARNING
        and "identity.vwgroup.io/v2/login/ui/consent" in r.getMessage()
        for r in caplog.records
    ), "the landing point is not in the log at WARNING"
    assert "SECRETSTATE" not in caplog.text


def test_setup_code_step_names_the_consent_page() -> None:
    from custom_components.vag_connect.config_flow import VagConnectConfigFlow

    stub = MagicMock()
    stub._wap_connector = _connector(IDENTITY_CONSENT)
    stub._wap_capture_cookies = MagicMock(return_value=[])
    stub._wap_close_session = AsyncMock()
    bound = VagConnectConfigFlow._wap_submit_otp.__get__(stub)
    with pytest.raises(ValueError, match="^website_consent_required$"):
        _run(bound("123456"))


def test_setup_code_step_keeps_the_general_message_for_another_stop() -> None:
    from custom_components.vag_connect.config_flow import VagConnectConfigFlow

    stub = MagicMock()
    stub._wap_connector = _connector(OTHER_STOP)
    stub._wap_capture_cookies = MagicMock(return_value=[])
    stub._wap_close_session = AsyncMock()
    bound = VagConnectConfigFlow._wap_submit_otp.__get__(stub)
    with pytest.raises(ValueError, match="^website_login_failed$"):
        _run(bound("123456"))


def test_repair_code_step_names_the_consent_page() -> None:
    from custom_components.vag_connect.repairs import (
        _SupplementaryReauthRepairFlow,
    )

    flow = _SupplementaryReauthRepairFlow("entry-2200")
    flow.hass = MagicMock()
    flow._ovw_connector = _connector(IDENTITY_CONSENT)
    flow._ovw_username = "user@example.com"

    res = _run(flow.async_step_otp({"mfa_code": "123456"}))

    assert res["type"] == "form" and res["step_id"] == "otp"
    assert res["errors"]["base"] == "website_consent_required"


# ── the password step in both drivers ────────────────────────────────────────


class _ConsentAtPassword:
    """A connector whose password step already stops on the consent page."""

    def __init__(self, *_a: Any, **_kw: Any) -> None:
        pass

    async def begin_login(self) -> str:
        raise WebsiteConsentRequiredError(
            "Website authproxy: login did not complete "
            "(ended at identity.vwgroup.io/v2/login/ui/consent)"
        )


@pytest.fixture
def _no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    import aiohttp

    monkeypatch.setattr(aiohttp, "ClientSession", MagicMock())
    monkeypatch.setattr(aiohttp, "TCPConnector", MagicMock())
    monkeypatch.setattr(aiohttp, "CookieJar", MagicMock())
    monkeypatch.setattr(wap, "WebsiteAuthProxyConnector", _ConsentAtPassword)


@pytest.mark.usefixtures("_no_network")
def test_setup_password_step_names_the_consent_page() -> None:
    from custom_components.vag_connect.config_flow import VagConnectConfigFlow

    stub = MagicMock()
    stub._wap_close_session = AsyncMock()
    bound = VagConnectConfigFlow._wap_begin_login.__get__(stub)
    with pytest.raises(ValueError, match="^website_consent_required$"):
        _run(bound("user@example.com", "pw"))


@pytest.mark.usefixtures("_no_network")
def test_options_password_step_names_the_consent_page() -> None:
    flow = _Options()
    flow._ovw_close_session = AsyncMock()  # type: ignore[method-assign]
    with pytest.raises(ValueError, match="^website_consent_required$"):
        _run(flow._ovw_begin_login("user@example.com", "pw"))


# ── the key reaches a text ───────────────────────────────────────────────────


def test_the_key_passes_the_setup_allowlist() -> None:
    from custom_components.vag_connect.config_flow import _map_error

    assert _map_error("website_consent_required") == "website_consent_required"


def _paths_with(obj: Any, key: str, path: tuple[str, ...] = ()) -> set[tuple[str, ...]]:
    found: set[tuple[str, ...]] = set()
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == key:
                found.add(path)
            found |= _paths_with(v, key, (*path, k))
    return found


@pytest.mark.parametrize(
    "file",
    ["strings.json", *sorted(p.name for p in (COMPONENT / "translations").glob("*.json"))],
)
def test_every_place_with_the_general_text_has_the_consent_text(file: str) -> None:
    base = COMPONENT if file == "strings.json" else COMPONENT / "translations"
    data = json.loads((base / file).read_text(encoding="utf-8"))
    general = _paths_with(data, "website_login_failed")
    consent = _paths_with(data, "website_consent_required")
    assert general, f"{file}: the general text is gone, the check measures nothing"
    assert consent == general, f"{file}: consent text missing in {general - consent}"
    for path in consent:
        node = data
        for k in path:
            node = node[k]
        text = node["website_consent_required"]
        assert text.strip() and text != node["website_login_failed"]
        assert "volkswagen.de" in text, f"{file}: the text must say where to sign in"
