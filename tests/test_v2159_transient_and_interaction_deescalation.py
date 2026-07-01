# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""v2.15.9 — de-escalate two noise classes out of the Error Reporter.

#593 (@dardares) — a transport-level ``ClientConnectorError`` / ``TimeoutError``
on the VW-NA ``_request`` path used to propagate raw out of ``get_status`` and
land in the Error Reporter as a per-VIN poll failure, exactly like the EU-login
timeouts the v2.15.8 fix (#576/#578) already tamed. ``_request`` now maps those
transport errors to ``UpstreamUnavailableError`` — the typed "backend
temporarily unavailable" the coordinator de-escalates and does NOT error-report.
Genuine HTTP responses (4xx/5xx incl. auth 401 and data-plane 403) still raise
``APIError`` and are reported as before.

#596 (@knalp) — a user-actionable auth-interaction (T&C / marketing-consent /
2FA / portal-interaction) re-hit on every poll fired ``record_error`` once per
VIN per poll, flooding the Reporter (~20x). The per-VIN gate now excludes the
``AuthenticationError`` family (all five interaction classes subclass it) from
``record_error`` — mirroring the outer poll-loop handler, which already
de-escalates the same family. It still surfaces as a fixable Repair at setup.

CRITICAL: a genuine data-plane failure (real 403/500, parse error, unexpected
exception) is none of the de-escalated types and MUST still be recorded. The
last test proves that.
"""

from __future__ import annotations

import asyncio
import types
from unittest.mock import AsyncMock

import pytest

from custom_components.vag_connect.cariad.exceptions import (
    APIError,
    AuthenticationError,
    EmailTwoFactorRequiredError,
    MarketingConsentError,
    PortalInteractionRequiredError,
    TermsAndConditionsError,
    TwoFactorRequiredError,
    UpstreamUnavailableError,
)


# ===========================================================================
# #593 — VW-NA _request maps transport errors to UpstreamUnavailableError
# ===========================================================================


class _Resp:
    """Minimal aiohttp response context manager returning a canned status."""

    def __init__(self, status: int, body: str = "{}") -> None:
        self.status = status
        self._body = body

    async def __aenter__(self) -> "_Resp":
        return self

    async def __aexit__(self, *_a: object) -> bool:
        return False

    async def json(self) -> dict:
        return {}

    async def text(self) -> str:
        return self._body


class _RaisingSession:
    """aiohttp-ish session whose .request() raises the given exception."""

    def __init__(self, exc: BaseException) -> None:
        self._exc = exc

    def request(self, *_a: object, **_kw: object) -> _Resp:
        raise self._exc


class _RespondingSession:
    """aiohttp-ish session whose .request() yields a canned response."""

    def __init__(self, status: int, body: str = "{}") -> None:
        self._status = status
        self._body = body

    def request(self, *_a: object, **_kw: object) -> _Resp:
        return _Resp(self._status, self._body)


def _vw_na_client(session: object):
    """Build a VWNAClient via __new__ with only what _request touches."""
    from custom_components.vag_connect.cariad.api.vw_na import VWNAClient
    from custom_components.vag_connect.cariad.models import TokenSet

    client = VWNAClient.__new__(VWNAClient)
    client._session = session  # type: ignore[assignment]
    client._tokens = TokenSet(
        access_token="at", refresh_token="rt", id_token="it"
    )
    return client


def _client_connector_error():
    """A real aiohttp.ClientConnectorError (subclass of ClientConnectionError)."""
    from aiohttp import ClientConnectorError

    return ClientConnectorError(
        connection_key=None,  # type: ignore[arg-type]
        os_error=OSError("Connection refused"),
    )


@pytest.mark.asyncio
async def test_vw_na_connector_error_maps_to_upstream_unavailable():
    """A ClientConnectorError during the request → UpstreamUnavailableError."""
    client = _vw_na_client(_RaisingSession(_client_connector_error()))
    with pytest.raises(UpstreamUnavailableError):
        await client._get("https://example.test/rvs/v1/vehicle/x")


@pytest.mark.asyncio
async def test_vw_na_timeout_maps_to_upstream_unavailable():
    """An asyncio/builtin TimeoutError (aiohttp total-timeout) → transient."""
    client = _vw_na_client(_RaisingSession(asyncio.TimeoutError()))
    with pytest.raises(UpstreamUnavailableError):
        await client._get("https://example.test/rvs/v1/vehicle/x")


@pytest.mark.asyncio
async def test_vw_na_upstream_unavailable_carries_504_and_brand():
    """The mapped error is a 504 backend-unavailable, not an auth failure."""
    client = _vw_na_client(_RaisingSession(_client_connector_error()))
    try:
        await client._get("https://example.test/rvs/v1/vehicle/x")
    except UpstreamUnavailableError as exc:
        assert exc.status == 504
        assert exc.brand == "volkswagen_na"
        # It must NOT be an AuthenticationError — the coordinator's reauth
        # path keys on that; a transient blip must never trigger reauth.
        assert not isinstance(exc, AuthenticationError)
    else:  # pragma: no cover
        pytest.fail("expected UpstreamUnavailableError")


@pytest.mark.asyncio
async def test_vw_na_genuine_403_still_raises_api_error():
    """A real data-plane 403 is NOT swallowed — it still raises APIError."""
    client = _vw_na_client(_RespondingSession(403, '{"error":"forbidden"}'))
    with pytest.raises(APIError) as ei:
        await client._get("https://example.test/rvs/v1/vehicle/x")
    assert ei.value.status == 403
    assert not isinstance(ei.value, UpstreamUnavailableError)


@pytest.mark.asyncio
async def test_vw_na_genuine_500_still_raises_api_error():
    """A real backend 500 still raises APIError (the coordinator de-escalates
    5xx separately; the client must NOT hide it as a connection error)."""
    client = _vw_na_client(_RespondingSession(500, '{"error":"boom"}'))
    with pytest.raises(APIError) as ei:
        await client._get("https://example.test/rvs/v1/vehicle/x")
    assert ei.value.status == 500


@pytest.mark.asyncio
async def test_vw_na_success_still_returns_json():
    """A 200 response is unaffected by the transient wrap."""
    client = _vw_na_client(_RespondingSession(200))
    assert await client._get("https://example.test/rvs/v1/vehicle/x") == {}


# ===========================================================================
# #596 — auth-interaction family de-escalation in the coordinator per-VIN gate
# ===========================================================================
#
# The per-VIN decision lives inline in the (un-callable) _poll_loop body, so we
# drive ONE real poll iteration through the actual coordinator code and inspect
# the real error_buffer. This exercises the genuine gate, not a copy of it.


def _build_coordinator(get_status_result):
    """A VagConnectCoordinator (via __new__) wired for exactly one poll pass.

    ``get_status_result`` is the exception (or VehicleData) the mocked client
    returns for the single VIN. Downstream best-effort helpers are stubbed to
    no-ops; ``_started`` flips False after the first pass so the loop exits.
    """
    from custom_components.vag_connect.cariad._error_reporter import ErrorRingBuffer
    from custom_components.vag_connect.coordinator import VagConnectCoordinator

    coord = VagConnectCoordinator.__new__(VagConnectCoordinator)

    vin = "WVWZZZ1KZAW000596"
    coord.vehicles = {vin: {"model": "ID.4", "model_year": 2023}}
    coord.error_buffer = ErrorRingBuffer()
    coord.vehicle_success = {}
    coord.vehicle_failure_count = {}
    coord.vehicle_last_good_at = {}

    import threading

    coord._vehicles_lock = threading.Lock()
    coord._started = True

    # entry stub — only .data/.options .get are read on the poll path we hit.
    coord.entry = types.SimpleNamespace(
        data={"brand": "volkswagen", "scan_interval": 1},
        options={},
        entry_id="e1",
    )

    # Client returns the canned result (exception) for the VIN.
    async def _get_status(_vin):
        if isinstance(get_status_result, Exception):
            raise get_status_result
        return get_status_result

    coord._cariad_client = types.SimpleNamespace(get_status=_get_status)

    # Stop after one pass: called near the end of the try-body.
    async def _push(_data, success=True):
        coord._started = False

    coord._async_push_update = _push  # type: ignore[assignment]

    # Best-effort no-ops the poll body invokes after the per-VIN gate.
    coord._refresh_reporter_issues = lambda: None  # type: ignore[assignment]
    coord._save_vehicle_cache = lambda: None  # type: ignore[assignment]
    coord._update_data_act_no_data_repair = lambda: None  # type: ignore[assignment]
    coord._maybe_run_stale_watchdog = AsyncMock()  # type: ignore[assignment]
    coord.refresh_trip_statistics = AsyncMock()  # type: ignore[assignment]
    coord.refresh_charging_history = AsyncMock()  # type: ignore[assignment]
    coord.refresh_charging_profiles = AsyncMock()  # type: ignore[assignment]
    coord.refresh_battery_care = AsyncMock()  # type: ignore[assignment]
    return coord, vin


async def _run_one_poll(coord):
    """Run the real _poll_loop; the stubbed _async_push_update stops it."""
    # asyncio.sleep is real but the interval is clamped; patch sleep to no-op
    # so the test is instant and deterministic.
    import custom_components.vag_connect.coordinator as mod

    orig_sleep = mod.asyncio.sleep

    async def _fast_sleep(_s):
        return None

    mod.asyncio.sleep = _fast_sleep  # type: ignore[assignment]
    try:
        await asyncio.wait_for(coord._poll_loop(), timeout=5)
    finally:
        mod.asyncio.sleep = orig_sleep  # type: ignore[assignment]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "interaction",
    [
        MarketingConsentError(),
        TermsAndConditionsError(),
        TwoFactorRequiredError(),
        EmailTwoFactorRequiredError(),
        PortalInteractionRequiredError("region-selection"),
    ],
)
async def test_auth_interaction_not_recorded_to_error_reporter(interaction):
    """Every auth-interaction subclass is de-escalated: the poll fails for the
    VIN (tracked) but NOTHING lands in the Error Reporter."""
    coord, vin = _build_coordinator(interaction)
    await _run_one_poll(coord)

    assert len(coord.error_buffer) == 0, (
        f"{type(interaction).__name__} flooded the Error Reporter"
    )
    # The poll is still counted as a failure so the stale-cache watchdog engages.
    assert coord.vehicle_success[vin] is False
    assert coord.vehicle_failure_count[vin] == 1


@pytest.mark.asyncio
async def test_upstream_unavailable_not_recorded():
    """The #593-shaped transient (UpstreamUnavailableError from the client)
    is de-escalated at the per-VIN gate too — no Error-Reporter entry."""
    coord, vin = _build_coordinator(UpstreamUnavailableError(504, brand="volkswagen"))
    await _run_one_poll(coord)
    assert len(coord.error_buffer) == 0
    assert coord.vehicle_success[vin] is False


@pytest.mark.asyncio
async def test_genuine_error_is_still_recorded():
    """A genuine data-plane 403 (real bug/entitlement, NOT a de-escalated
    class) STILL lands in the Error Reporter — we did not go silent."""
    coord, vin = _build_coordinator(
        APIError(403, "https://example.test/rvs/v1/vehicle/x", '{"error":"forbidden"}')
    )
    await _run_one_poll(coord)

    assert len(coord.error_buffer) == 1, "genuine error was wrongly swallowed"
    rec = coord.error_buffer.latest
    assert rec is not None
    assert rec.exception_type == "APIError"
    assert rec.endpoint == "get_status"


@pytest.mark.asyncio
async def test_unexpected_exception_is_still_recorded():
    """An unexpected exception type (e.g. a real parse/logic bug surfacing from
    get_status) is neither transient nor an interaction → still recorded."""
    coord, vin = _build_coordinator(ValueError("unexpected boom"))
    await _run_one_poll(coord)

    assert len(coord.error_buffer) == 1
    assert coord.error_buffer.latest.exception_type == "ValueError"


# ===========================================================================
# Contract guards — the gate relies on these type relationships
# ===========================================================================


def test_interaction_classes_are_authentication_errors():
    """One isinstance(result, AuthenticationError) must cover all five."""
    for cls in (
        TermsAndConditionsError,
        MarketingConsentError,
        TwoFactorRequiredError,
        EmailTwoFactorRequiredError,
        PortalInteractionRequiredError,
    ):
        assert issubclass(cls, AuthenticationError), cls.__name__


def test_upstream_unavailable_is_not_authentication_error():
    """A transient must NOT be an AuthenticationError — otherwise it would wrongly
    trip the reauth path in the outer handler."""
    assert not issubclass(UpstreamUnavailableError, AuthenticationError)
