# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#1740 — the portal-domain user-agent, as the operator asked for it.

Originally written by @VWGroupDatahub against a single module-wide agent. The
agent moved to the portal-domain requests (the ones they asked about) and the
login steps kept their browser string, so these assertions moved with it.
"""
from __future__ import annotations

from custom_components.vag_connect.cariad.auth import _eu_data_act


def test_the_portal_agent_carries_the_version() -> None:
    try:
        _eu_data_act.set_integration_version("9.9.9")
        assert _eu_data_act._portal_user_agent() == "HA_vag_connect/9.9.9"
    finally:
        _eu_data_act.set_integration_version("")


def test_an_unknown_version_falls_back_to_the_bare_product() -> None:
    """Never an agent ending in a bare slash."""
    _eu_data_act.set_integration_version("")
    assert _eu_data_act._portal_user_agent() == "HA_vag_connect"


def test_a_blank_version_is_treated_as_unknown() -> None:
    try:
        _eu_data_act.set_integration_version("   ")
        assert _eu_data_act._portal_user_agent() == "HA_vag_connect"
    finally:
        _eu_data_act.set_integration_version("")


def test_the_login_steps_keep_the_browser_agent() -> None:
    """#388/#393 — the IDP sits behind a WAF that refused a non-browser agent."""
    assert "Mozilla/5.0" in _eu_data_act._USER_AGENT
    assert _eu_data_act._USER_AGENT != _eu_data_act._portal_user_agent()


# ── The one-time-export scraper, which the original change missed ────────────
#
# The #1740 comment enumerates what it covered, and that is how the gap stayed
# invisible: the export and auto-kickoff requests live in their own module and
# went out under the HTTP library default name, including the two POSTs that
# CREATE a data request on the portal. Measured before the fix: no user-agent
# anywhere in that module in any spelling, and the portal session is built
# without default headers, so nothing supplied one further down either.


class _FakeResponse:
    """Enough of an aiohttp response for one portal GET."""

    def __init__(self, status: int, payload: object) -> None:
        self.status = status
        self.headers: dict[str, str] = {}
        self._payload = payload

    async def __aenter__(self) -> "_FakeResponse":
        return self

    async def __aexit__(self, *_exc: object) -> bool:
        return False

    async def json(self, content_type: object = None) -> object:
        return self._payload

    async def read(self) -> bytes:
        return b""

    async def text(self) -> str:
        return ""


class _RecordingSession:
    """Records the headers of every request instead of sending it."""

    def __init__(self, status: int = 200, payload: object = None) -> None:
        self.calls: list[tuple[str, str, dict[str, str]]] = []
        self._status = status
        self._payload = [] if payload is None else payload

    def _record(self, method: str, url: str, kwargs: dict) -> _FakeResponse:
        self.calls.append((method, url, dict(kwargs.get("headers") or {})))
        return _FakeResponse(self._status, self._payload)

    def get(self, url: str, **kwargs: object) -> _FakeResponse:
        return self._record("GET", url, kwargs)

    def post(self, url: str, **kwargs: object) -> _FakeResponse:
        return self._record("POST", url, kwargs)


def _scraper(session: _RecordingSession):
    from custom_components.vag_connect.cariad.auth._data_act_scraper import (
        DataActScraper,
    )

    return DataActScraper(session, brand_name="volkswagen")  # type: ignore[arg-type]


async def test_an_export_scraper_request_identifies_the_project() -> None:
    """FAILS BEFORE THE FIX: the request carried no user-agent at all."""
    session = _RecordingSession()
    try:
        _eu_data_act.set_integration_version("9.9.9")
        await _scraper(session).get_active_custom_request_identifier(
            "WVWZZZ1JZ3W000001"
        )
    finally:
        _eu_data_act.set_integration_version("")

    assert session.calls, "the method made no request at all"
    _method, url, headers = session.calls[0]
    assert headers.get("User-Agent") == "HA_vag_connect/9.9.9"
    # And it really is the portal domain, which is why tagging it is correct
    # while the IDP keeps its browser string.
    assert "eu-data-act" in url


async def test_the_scraper_keeps_the_headers_it_already_sent() -> None:
    """The agent is merged in, not substituted for what was there.

    This request already carried an Accept and a traceId, and the portal's
    euda-apim layer answers 400 without the traceId, so losing it while adding
    an agent would have traded one defect for a worse one.
    """
    session = _RecordingSession()
    await _scraper(session).get_active_custom_request_identifier(
        "WVWZZZ1JZ3W000001"
    )
    _method, _url, headers = session.calls[0]
    assert headers.get("Accept") == "application/json"
    assert headers.get("traceId")
    assert headers.get("User-Agent")


def test_every_scraper_request_site_sets_the_agent() -> None:
    """The structural guard, and deliberately the inverse kind of check.

    A presence grep for the agent string would pass while a single site still
    sent a bare request, which is exactly how the #584 refusal messages shipped
    dead. So this enumerates the request sites and fails on any one of them that
    does not pass the header helper.
    """
    import inspect
    import re

    from custom_components.vag_connect.cariad.auth import _data_act_scraper

    lines = inspect.getsource(_data_act_scraper).split("\n")
    sites = [
        i for i, ln in enumerate(lines)
        if re.search(r"self\._session\.(get|post)\(", ln)
    ]
    assert len(sites) == 7, f"expected 7 request sites, found {len(sites)}"
    for i in sites:
        window = "\n".join(lines[i:i + 14])
        assert "headers=self._hdrs(" in window, (
            f"request at offset {i} sends no identified headers: {lines[i].strip()}"
        )
