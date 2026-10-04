# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#465 — a portal outage on VIN enumeration was classified as a dead session.

VIN enumeration (``/consent/me/vehicles``) is a HARD portal call: an empty list
would be read as "this account has no cars", so the call has to fail loudly
rather than return nothing. It did fail loudly — but as
``AuthenticationError``, carrying the status only inside the message text.

The caller in the VW EU client catches a bare ``AuthenticationError`` with no
status inspection, and responds the only way it knows: refresh the token or
**replay the password**, retry once, and on the second failure raise
``PortalSessionExpiredError``, which the coordinator turns into a
"session expired" Repair. So a portal 503 — a VW-side outage lasting seconds —
produced a credential replay the user never asked for and a Repair notice
blaming their session.

This is the same misdiagnosis class as the volkswagen.de 502 fixed in #1709,
one channel over, and ``UpstreamUnavailableError`` already exists for exactly
it; its own docstring records users reconfiguring their integration during the
502-storms "because the failure looked like wrong credentials". The portal's
hard path simply never raised it.

Unchanged on purpose: 401 and 403 are still a session problem, 404/410 still
mean "not provisioned", and every soft call still gives up quietly as "no data
this poll".
"""
from __future__ import annotations

import asyncio
from typing import Any

import pytest


class _Resp:
    def __init__(self, status: int, payload: Any = None) -> None:
        self.status = status
        self._payload = payload if payload is not None else {}
        self.headers: dict[str, str] = {}
        self.cookies: dict[str, str] = {}

    async def json(self, content_type: str | None = None) -> Any:
        return self._payload

    async def text(self) -> str:
        return "" if self.status >= 400 else "{}"

    async def __aenter__(self) -> _Resp:
        return self

    async def __aexit__(self, *_a: object) -> None:
        return None


class _Session:
    """Answers every GET with the same status, and counts the attempts."""

    def __init__(self, status: int, payload: Any = None) -> None:
        self._status = status
        self._payload = payload
        self.calls = 0
        self.cookie_jar = type(
            "_J", (), {"filter_cookies": lambda *_a: {}, "update_cookies": lambda *_a: None}
        )()

    def get(self, *_a: object, **_k: object) -> _Resp:
        self.calls += 1
        return _Resp(self._status, self._payload)

    post = get


@pytest.fixture(autouse=True)
def _no_real_backoff(monkeypatch: pytest.MonkeyPatch) -> None:
    """The hard path retries a 5xx with a 3 s + 6 s backoff; don't wait for it."""
    async def _instant(_delay: float) -> None:
        return None

    monkeypatch.setattr(asyncio, "sleep", _instant)


def _connector(status: int, payload: Any = None):
    from custom_components.vag_connect.cariad.auth._eu_data_act import (
        EUDataActConnector,
    )

    session = _Session(status, payload)
    return EUDataActConnector(session, brand="volkswagen"), session


# ── The fix ──────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("status", [500, 502, 503, 504, 429])
def test_a_portal_outage_raises_upstream_unavailable_not_authentication(
    status: int,
) -> None:
    """The whole point: an outage must not look like a credentials problem."""
    from custom_components.vag_connect.cariad.exceptions import (
        AuthenticationError,
        UpstreamUnavailableError,
    )

    conn, _ = _connector(status)
    with pytest.raises(UpstreamUnavailableError) as excinfo:
        asyncio.new_event_loop().run_until_complete(conn.list_vehicle_vins())
    assert not isinstance(excinfo.value, AuthenticationError), (
        "still inherits the auth branch the caller keys on"
    )
    assert str(status) in str(excinfo.value)


def test_the_outage_message_says_it_is_not_the_password() -> None:
    """Users reconfigured their integrations over this; the text matters."""
    from custom_components.vag_connect.cariad.exceptions import (
        UpstreamUnavailableError,
    )

    conn, _ = _connector(503)
    with pytest.raises(UpstreamUnavailableError) as excinfo:
        asyncio.new_event_loop().run_until_complete(conn.list_vehicle_vins())
    msg = str(excinfo.value).lower()
    assert "not a credentials problem" in msg
    assert "do not reconfigure" in msg


def test_the_retries_still_happen_before_giving_up() -> None:
    """The change is the exception type, not the retry behaviour: a 5xx is
    still retried twice before anything is raised."""
    from custom_components.vag_connect.cariad.auth._eu_data_act import (
        _PORTAL_RETRY_DELAYS,
    )
    from custom_components.vag_connect.cariad.exceptions import (
        UpstreamUnavailableError,
    )

    conn, session = _connector(503)
    with pytest.raises(UpstreamUnavailableError):
        asyncio.new_event_loop().run_until_complete(conn.list_vehicle_vins())
    assert session.calls == len(_PORTAL_RETRY_DELAYS) + 1


# ── Unchanged paths ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("status", [401, 403])
def test_a_real_session_problem_still_raises_authentication_error(
    status: int,
) -> None:
    """401/403 is genuinely the session: the re-login path must keep firing."""
    from custom_components.vag_connect.cariad.exceptions import AuthenticationError

    conn, _ = _connector(status)
    with pytest.raises(AuthenticationError):
        asyncio.new_event_loop().run_until_complete(conn.list_vehicle_vins())


@pytest.mark.parametrize("status", [404, 410])
def test_not_provisioned_still_raises_authentication_error(status: int) -> None:
    """404/410 means the data request is not provisioned — unchanged, so the
    existing "delivery not ready" handling is untouched."""
    from custom_components.vag_connect.cariad.exceptions import AuthenticationError

    conn, _ = _connector(status)
    with pytest.raises(AuthenticationError):
        asyncio.new_event_loop().run_until_complete(conn.list_vehicle_vins())


def test_a_successful_enumeration_still_returns_the_vins() -> None:
    """Guard the happy path."""
    conn, _ = _connector(200, {"vehicles": [{"vin": "WVWZZZE1ZTP000001"}]})
    vins = asyncio.new_event_loop().run_until_complete(conn.list_vehicle_vins())
    assert vins == ["WVWZZZE1ZTP000001"]


# ── What the user actually sees ───────────────────────────────────────────────

def test_the_coordinator_treats_the_outage_as_self_healing() -> None:
    """It must not reach the public Error Reporter: it is VW's server, not a
    bug in this integration."""
    from custom_components.vag_connect.coordinator import _is_selfhealing_poll_error
    from custom_components.vag_connect.cariad.exceptions import (
        UpstreamUnavailableError,
    )

    assert _is_selfhealing_poll_error(UpstreamUnavailableError(503, brand="VW")) is True


def test_the_vw_eu_caller_does_not_replay_the_password_on_an_outage() -> None:
    """The user-visible consequence: the enumeration caller catches
    ``AuthenticationError`` to re-login. An outage must bypass that branch, so
    no credential replay and no session-expired Repair."""
    import inspect

    from custom_components.vag_connect.cariad.api import vw_eu

    src = inspect.getsource(vw_eu)
    # The re-login branch keys on AuthenticationError only ...
    assert "except AuthenticationError:" in src
    # ... and UpstreamUnavailableError must not be a subclass of it, or the
    # branch would still catch the outage.
    from custom_components.vag_connect.cariad.exceptions import (
        AuthenticationError,
        UpstreamUnavailableError,
    )

    assert not issubclass(UpstreamUnavailableError, AuthenticationError)
