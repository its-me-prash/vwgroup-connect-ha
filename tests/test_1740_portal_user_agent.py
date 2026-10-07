# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Portal-domain requests identify themselves; the IDP login does not change.

The portal's operator asked on #1740 for a dedicated user-agent on requests to
the portal host, so they can attribute traffic and report problems back to the
project causing them. Their own PR changed the constant used by the *login*
steps and left the portal requests on aiohttp's default agent — the opposite of
what was asked — so the split is what these tests pin.

The login steps keep the browser agent on purpose: they go to the IDP, which is
a browser flow behind a WAF that answered 403 to a non-browser agent once
already (#388/#393).
"""
from __future__ import annotations

import asyncio
from typing import Any

from custom_components.vag_connect.cariad.auth import _eu_data_act as mod
from custom_components.vag_connect.cariad.auth._eu_data_act import (
    EUDataActConnector,
    _portal_user_agent,
    set_integration_version,
)


class _Resp:
    def __init__(self, payload: Any = None, status: int = 200) -> None:
        self._payload = payload if payload is not None else {}
        self.status = status
        self.url = "https://portal.invalid/x"
        self.headers: dict[str, str] = {}

    async def __aenter__(self) -> "_Resp":
        return self

    async def __aexit__(self, *_exc: object) -> bool:
        return False

    async def json(self, content_type: str | None = None) -> Any:
        return self._payload

    async def text(self, errors: str | None = None) -> str:
        return "{}"

    async def read(self) -> bytes:
        return b""


class _Session:
    """Records the headers of every request made through it."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def get(self, url: str, **kw: Any) -> _Resp:
        self.calls.append({"method": "GET", "url": url, **kw})
        return _Resp()

    def post(self, url: str, **kw: Any) -> _Resp:
        self.calls.append({"method": "POST", "url": url, **kw})
        return _Resp()


def _run(coro: Any) -> Any:
    return asyncio.new_event_loop().run_until_complete(coro)


def _connector() -> tuple[Any, _Session]:
    s = _Session()
    return EUDataActConnector(s), s  # type: ignore[arg-type]


# ───────────────────────────────────────────────────────────── the agent itself


def test_the_agent_carries_the_version_when_it_is_known():
    try:
        set_integration_version("4.11.1")
        assert _portal_user_agent() == "HA_vag_connect/4.11.1"
    finally:
        set_integration_version("")


def test_an_unknown_version_still_identifies_the_product():
    """Never an agent ending in a bare slash, and never empty."""
    set_integration_version("")
    assert _portal_user_agent() == "HA_vag_connect"

    set_integration_version("   ")
    assert _portal_user_agent() == "HA_vag_connect"


def test_setting_the_version_never_raises_on_junk():
    for junk in (None, "", "  4.11.1  "):
        set_integration_version(junk)  # type: ignore[arg-type]
    assert _portal_user_agent() == "HA_vag_connect/4.11.1"
    set_integration_version("")


# ─────────────────────────────────────────────── where it is and is not applied


def test_a_portal_json_request_identifies_itself():
    set_integration_version("4.11.1")
    try:
        conn, session = _connector()
        _run(conn._get_json("https://eu-data-act.drivesomethinggreater.com/x"))
    finally:
        set_integration_version("")

    assert session.calls, "no request was made"
    assert session.calls[0]["headers"]["User-Agent"] == "HA_vag_connect/4.11.1"


def test_a_caller_supplied_agent_is_not_overridden():
    """setdefault, not assignment — a caller that needs its own agent keeps it."""
    conn, session = _connector()
    _run(conn._get_json("https://eu-data-act.drivesomethinggreater.com/x",
                        headers={"User-Agent": "something/1.0"}))

    assert session.calls[0]["headers"]["User-Agent"] == "something/1.0"


def test_the_bearer_header_survives_the_addition():
    conn, session = _connector()
    conn._bearer = "token-value"
    _run(conn._get_json("https://eu-data-act.drivesomethinggreater.com/x"))

    h = session.calls[0]["headers"]
    assert h["Authorization"] == "Bearer token-value"
    assert h["User-Agent"] == _portal_user_agent()


def test_the_login_steps_keep_the_browser_agent():
    """#388/#393 — the IDP sits behind a WAF that disliked a non-browser agent.

    Asserted on source because driving the whole login would prove less: the
    invariant is that the login path reads the browser constant and the portal
    path reads the dedicated one, and that they are two different values.
    """
    import inspect

    src = inspect.getsource(mod)
    assert 'headers = {"User-Agent": _USER_AGENT}' in src
    assert "Mozilla/5.0" in src, "the browser agent must still exist"
    assert mod._USER_AGENT != _portal_user_agent()
    # the dedicated agent is never the one handed to the login steps
    assert "_portal_user_agent()" not in src.split("def _login_impl")[1][:4000]


def test_the_priming_get_is_gone():
    """The operator confirmed the affinity cookie arrives on the IDP redirect."""
    import inspect

    src = inspect.getsource(mod.EUDataActConnector._login_impl)
    assert "Prime portal session cookies" not in src
    assert 'f"{_PORTAL_BASE}/", headers=headers' not in src
    # and the login still starts at the IDP authorize step
    assert "_AUTHORIZE_URL" in src
