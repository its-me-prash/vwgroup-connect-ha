# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""v2.29.x — VW NA fixes derived from sstur/vwapp (iOS-decompiled, live-verified
myVW NA reference).

Read side (safe, non-live-gated):
  - plugStatus.plugLockState -> connector_locked (was never set for NA).
  - climateStatusReport.remainingClimatizationTimeMin -> climate_remaining_time_min.

Command side (carnet-Bearer rewrite, live-gated shapes):
  - set-climate-temperature is a nested-object PUT
    {targetTemperature:{temperature,unit}} with the carnetVehicleToken as Bearer.

Pure-Python: VWNAClient via __new__, mocking at the _request boundary.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest


pytestmark = pytest.mark.ha_required

_VIN = "WVWZZZ1KZAW000503"
_UUID = "11112222-3333-4444-5555-666677778888"


class _FakeTokens:
    access_token = "ACCESS-TOKEN"
    id_token = "ID-TOKEN"
    refresh_token = "REFRESH-TOKEN"


def _client(spin: str = ""):
    from custom_components.vag_connect.cariad.api.vw_na import VWNAClient

    c = VWNAClient.__new__(VWNAClient)
    c._base = "https://example.test"
    c._vin_to_uuid = {_VIN: _UUID}
    c._vin_to_model = {}
    c._vin_to_nickname = {}
    c._user_id = "user-abc"
    c._spin = spin
    c._tokens = _FakeTokens()
    c.vw_na_data_forbidden = False
    c.vw_na_data_forbidden_reason = ""
    c._last_privileges_status = None
    c._read_session_tokens = {}
    c._spin_read_session_disabled = False
    c._spin_read_warned = False
    c._bare_403_streak = 0
    return c


# ── read-side mappings ──────────────────────────────────────────────────────


class TestReadMappings:
    @pytest.mark.asyncio
    async def test_plug_lock_state_maps_connector_locked(self):
        client = _client(spin="")  # no S-PIN -> plain reads

        async def fake_request(method, url, retry=True, _carnet_auth=False, **kwargs):
            if "/charge/summary" in url:
                return {
                    "plugStatus": {
                        "plugConnectionState": "CONNECTED",
                        "plugLockState": "LOCKED",
                    }
                }
            if "/rvs/" in url:
                return {"powerStatus": {}}
            return {}

        client._request = fake_request  # type: ignore[method-assign]
        client.get_subscription_privileges = AsyncMock(return_value={})  # type: ignore[method-assign]

        d = await client.get_status(_VIN)
        assert d.connector_locked is True
        assert d.plug_connected is True

    @pytest.mark.asyncio
    async def test_plug_lock_state_unlocked(self):
        client = _client(spin="")

        async def fake_request(method, url, retry=True, _carnet_auth=False, **kwargs):
            if "/charge/summary" in url:
                return {"plugStatus": {"plugLockState": "UNLOCKED"}}
            if "/rvs/" in url:
                return {"powerStatus": {}}
            return {}

        client._request = fake_request  # type: ignore[method-assign]
        client.get_subscription_privileges = AsyncMock(return_value={})  # type: ignore[method-assign]

        d = await client.get_status(_VIN)
        assert d.connector_locked is False

    @pytest.mark.asyncio
    async def test_remaining_climatization_time_maps(self):
        client = _client(spin="")

        async def fake_request(method, url, retry=True, _carnet_auth=False, **kwargs):
            if "/climate/summary" in url:
                return {
                    "climateStatusReport": {
                        "climateStatusInd": "COOLING",
                        "remainingClimatizationTimeMin": 12,
                    }
                }
            if "/rvs/" in url:
                return {"powerStatus": {}}
            return {}

        client._request = fake_request  # type: ignore[method-assign]
        client.get_subscription_privileges = AsyncMock(return_value={})  # type: ignore[method-assign]

        d = await client.get_status(_VIN)
        assert d.climate_remaining_time_min == 12


# ── command side ────────────────────────────────────────────────────────────


class TestClimateTemperatureCommand:
    @pytest.mark.asyncio
    async def test_set_temp_nested_put_with_carnet(self):
        client = _client(spin="1234")
        client._get_read_session_token = AsyncMock(  # type: ignore[method-assign]
            return_value="carnet-tok"
        )
        client._read = AsyncMock(return_value={})  # type: ignore[method-assign]  # no current settings
        client._request = AsyncMock(return_value={})  # type: ignore[method-assign]

        await client.command_set_climate_temperature(_VIN, 21.5)
        a = client._request.await_args
        assert a.args[0] == "PUT"
        assert a.args[1].endswith(f"/ev/v1/vehicle/{_UUID}/pretripclimate/settings")
        assert a.kwargs["json"] == {
            "targetTemperature": {"temperature": 21.5, "unit": "celsius"}
        }
        assert a.kwargs["headers"]["Authorization"] == "Bearer carnet-tok"

    @pytest.mark.asyncio
    async def test_set_temp_merges_existing_settings(self):
        client = _client(spin="1234")
        client._get_read_session_token = AsyncMock(  # type: ignore[method-assign]
            return_value="carnet-tok"
        )
        client._read = AsyncMock(  # type: ignore[method-assign]
            return_value={"climateSettings": {"climatisationWithoutHVpower": True}}
        )
        client._request = AsyncMock(return_value={})  # type: ignore[method-assign]

        await client.command_set_climate_temperature(_VIN, 20.0)
        body = client._request.await_args.kwargs["json"]
        # existing setting preserved, target temperature added as nested object
        assert body["climatisationWithoutHVpower"] is True
        assert body["targetTemperature"] == {"temperature": 20.0, "unit": "celsius"}


# ── idk NA login throttle marker ────────────────────────────────────────────


class TestNaLoginThrottleMarker:
    """A con-veh NA login returns throttling as a 200 signin-HTML body
    (marker ``login.error.throttled``), not a 429. It must classify as a
    rate-limit, not a wrong-password (which fired a reauth/throttle loop)."""

    def test_throttle_marker_substring(self) -> None:
        throttled = "<html>login.error.throttled please wait</html>".lower()
        normal = "<html>please enter your password</html>".lower()
        assert (
            "login.error.throttled" in throttled or "throttl" in throttled
        ) is True
        assert (
            "login.error.throttled" in normal or "throttl" in normal
        ) is False

    def test_source_checks_throttle_before_wrong_credentials(self) -> None:
        from pathlib import Path

        src = Path(
            "custom_components/vag_connect/cariad/auth/idk.py"
        ).read_text(encoding="utf-8")
        throttle_pos = src.find("login.error.throttled")
        wrong_creds_pos = src.find("Unexpected 200 after password POST")
        assert throttle_pos > 0, "throttle marker check missing in idk.py"
        assert wrong_creds_pos > 0
        assert throttle_pos < wrong_creds_pos, (
            "the throttle→RateLimitError branch must run BEFORE the generic "
            "wrong-credentials raise"
        )
