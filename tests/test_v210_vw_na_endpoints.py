# Copyright 2026 Prash Balan (@its-me-prash) - Apache License 2.0
# SPDX-License-Identifier: AGPL-3.0-or-later
"""v2.10.0 (Group C) - VW NA endpoint parity tests.

Covers the Cox-backend behaviours:

1. ``get_subscription_privileges`` parses the
   ``/rrs/v1/privileges/user/{uid}/vehicle/{uuid}`` response and feeds
   ``subscription_active`` + ``subscription_expiry_at`` +
   ``subscription_days_remaining`` + ``capabilities_count`` onto
   VehicleData. Soft-fails on 401 / 403 / 404 / non-dict.

2. Remote commands (v2.29.x, sstur/vwapp APK-verified): lock/unlock is
   ``PUT {lock: bool}`` with the per-vehicle carnetVehicleToken as the
   Authorization Bearer (NOT ``POST {"action":...}`` on the access_token,
   which VW silently ignored). ``_carnet_command`` falls back to the plain
   access_token path when no carnet token is available.

3. ``command_start_climate`` / stop hit ``/pretripclimate/{start,stop}``
   first and fall back to ``/climatisation/{start,stop}`` on 404.

Pure-Python tests; constructs VWNAClient via __new__ to skip the HA /
aiohttp setup chain. Matches the pattern of test_v1242_porsche_vw_na_parity.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest


pytestmark = pytest.mark.ha_required


def _client(user_id: str | None = "user-abc"):
    """Construct a VWNAClient skipping __init__.

    Sets only the attributes that the new helpers touch so tests stay
    isolated from the rest of the client state.
    """
    from custom_components.vag_connect.cariad.api.vw_na import VWNAClient

    client = VWNAClient.__new__(VWNAClient)
    client._base = "https://example.test"
    client._vin_to_uuid = {"VWNA00000000000001": "uuid-xyz"}
    client._user_id = user_id
    client._spin = ""
    client._read_session_tokens = {}
    return client


# ---------------------------------------------------------------------------
# 1) Subscription privileges parser
# ---------------------------------------------------------------------------


class TestSubscriptionPrivileges:
    """``get_subscription_privileges`` -> normalised dict for the parser."""

    @pytest.mark.asyncio
    async def test_happy_path_active_subscription(self):
        client = _client()
        client._get = AsyncMock(  # type: ignore[method-assign]
            return_value={
                "data": {
                    "subscription": {
                        "active": True,
                        "expiresAt": "2027-08-14T00:00:00Z",
                    },
                    "capabilities": {
                        "remoteLockUnlock": "ENABLED",
                        "preTripClimate": "ENABLED",
                        "horn": "ENABLED",
                    },
                }
            }
        )
        out = await client.get_subscription_privileges("VWNA00000000000001")
        assert out["subscription_active"] is True
        assert out["subscription_expiry_at"] == "2027-08-14T00:00:00Z"
        assert out["capabilities_count"] == 3

    @pytest.mark.asyncio
    async def test_alt_key_names_state_string(self):
        """Defensive: backend may ship ``status: ACTIVE`` instead of bool."""
        client = _client()
        client._get = AsyncMock(  # type: ignore[method-assign]
            return_value={
                "subscription": {
                    "status": "ACTIVE",
                    "validUntil": "2026-12-31T23:59:59Z",
                }
            }
        )
        out = await client.get_subscription_privileges("VWNA00000000000001")
        assert out["subscription_active"] is True
        assert out["subscription_expiry_at"] == "2026-12-31T23:59:59Z"

    @pytest.mark.asyncio
    async def test_no_user_id_returns_empty(self):
        """Without a captured user_id the endpoint URL cannot be built."""
        client = _client(user_id=None)
        out = await client.get_subscription_privileges("VWNA00000000000001")
        assert out == {}

    @pytest.mark.asyncio
    async def test_soft_fails_on_404(self):
        from custom_components.vag_connect.cariad.exceptions import APIError

        client = _client()
        client._get = AsyncMock(  # type: ignore[method-assign]
            side_effect=APIError(404, "/x", "not found")
        )
        out = await client.get_subscription_privileges("VWNA00000000000001")
        assert out == {}

    @pytest.mark.asyncio
    async def test_soft_fails_on_403(self):
        from custom_components.vag_connect.cariad.exceptions import APIError

        client = _client()
        client._get = AsyncMock(  # type: ignore[method-assign]
            side_effect=APIError(403, "/x", "forbidden")
        )
        out = await client.get_subscription_privileges("VWNA00000000000001")
        assert out == {}

    @pytest.mark.asyncio
    async def test_non_dict_response_returns_empty(self):
        client = _client()
        client._get = AsyncMock(  # type: ignore[method-assign]
            return_value=["not", "a", "dict"]
        )
        out = await client.get_subscription_privileges("VWNA00000000000001")
        assert out == {}

    @pytest.mark.asyncio
    async def test_empty_subscription_block(self):
        """No subscription key at all - field stays absent from output dict."""
        client = _client()
        client._get = AsyncMock(  # type: ignore[method-assign]
            return_value={"data": {"capabilities": {"a": "X"}}}
        )
        out = await client.get_subscription_privileges("VWNA00000000000001")
        assert "subscription_active" not in out
        assert "subscription_expiry_at" not in out
        assert out["capabilities_count"] == 1

    @pytest.mark.asyncio
    async def test_url_format(self):
        """URL must follow /rrs/v1/privileges/user/{uid}/vehicle/{uuid}."""
        client = _client()
        client._get = AsyncMock(return_value={})  # type: ignore[method-assign]
        await client.get_subscription_privileges("VWNA00000000000001")
        url_arg = client._get.await_args.args[0]
        assert url_arg == (
            "https://example.test/rrs/v1/privileges/user/user-abc"
            "/vehicle/uuid-xyz"
        )


# ---------------------------------------------------------------------------
# 2) Remote commands — carnet-token Bearer (v2.29.x, sstur/vwapp)
# ---------------------------------------------------------------------------


class TestCommandCarnet:
    """lock/unlock/wake/charge use ``_carnet_command``: PUT/POST with the
    carnetVehicleToken as the Authorization Bearer, or the plain access_token
    path when no carnet token is available."""

    @pytest.mark.asyncio
    async def test_lock_puts_lock_true_with_carnet_bearer(self):
        client = _client()
        client._get_read_session_token = AsyncMock(  # type: ignore[method-assign]
            return_value="carnet-tok"
        )
        client._request = AsyncMock(return_value={})  # type: ignore[method-assign]
        await client.command_lock("VWNA00000000000001")
        a = client._request.await_args
        assert a.args[0] == "PUT"
        assert a.args[1].endswith("/lockunlock/v1/vehicle/uuid-xyz")
        assert a.kwargs["json"] == {"lock": True}
        assert a.kwargs["headers"]["Authorization"] == "Bearer carnet-tok"
        assert a.kwargs["_carnet_auth"] is True

    @pytest.mark.asyncio
    async def test_unlock_puts_lock_false_with_carnet_bearer(self):
        client = _client()
        client._get_read_session_token = AsyncMock(  # type: ignore[method-assign]
            return_value="carnet-tok"
        )
        client._request = AsyncMock(return_value={})  # type: ignore[method-assign]
        await client.command_unlock("VWNA00000000000001")
        a = client._request.await_args
        assert a.args[0] == "PUT"
        assert a.args[1].endswith("/lockunlock/v1/vehicle/uuid-xyz")
        assert a.kwargs["json"] == {"lock": False}
        assert a.kwargs["headers"]["Authorization"] == "Bearer carnet-tok"

    @pytest.mark.asyncio
    async def test_no_carnet_falls_back_to_access_token_path(self):
        """No S-PIN (or exchange disabled) -> plain access_token _request with
        no carnet Authorization header injected by the helper."""
        client = _client()
        client._get_read_session_token = AsyncMock(  # type: ignore[method-assign]
            return_value=None
        )
        client._request = AsyncMock(return_value={})  # type: ignore[method-assign]
        await client.command_lock("VWNA00000000000001")
        a = client._request.await_args
        assert a.args[0] == "PUT"
        assert "headers" not in a.kwargs
        assert a.kwargs.get("_carnet_auth") in (None, False)

    @pytest.mark.asyncio
    async def test_carnet_command_403_drops_cached_token_and_raises(self):
        from custom_components.vag_connect.cariad.exceptions import APIError

        client = _client()
        client._read_session_tokens = {"uuid-xyz": ("carnet-tok", None)}
        client._get_read_session_token = AsyncMock(  # type: ignore[method-assign]
            return_value="carnet-tok"
        )
        client._request = AsyncMock(  # type: ignore[method-assign]
            side_effect=APIError(403, "/x", "USER_NOT_AUTHORIZED")
        )
        with pytest.raises(APIError) as exc:
            await client.command_lock("VWNA00000000000001")
        assert exc.value.status == 403
        # cached carnet token popped so the next command re-mints
        assert "uuid-xyz" not in client._read_session_tokens

    @pytest.mark.asyncio
    async def test_wake_posts_rvs_refresh_with_carnet(self):
        client = _client()
        client._get_read_session_token = AsyncMock(  # type: ignore[method-assign]
            return_value="carnet-tok"
        )
        client._request = AsyncMock(return_value={})  # type: ignore[method-assign]
        await client.command_wake("VWNA00000000000001")
        a = client._request.await_args
        assert a.args[0] == "POST"
        assert a.args[1].endswith("/rvs/v1/vehicle/uuid-xyz/refresh")
        assert a.kwargs["headers"]["Authorization"] == "Bearer carnet-tok"

    @pytest.mark.asyncio
    async def test_charging_start_actionmode_immediate(self):
        client = _client()
        client._get_read_session_token = AsyncMock(  # type: ignore[method-assign]
            return_value="carnet-tok"
        )
        client._request = AsyncMock(return_value={})  # type: ignore[method-assign]
        await client.command_start_charging("VWNA00000000000001")
        a = client._request.await_args
        assert a.args[0] == "POST"
        assert a.args[1].endswith("/ev/v1/vehicle/uuid-xyz/charging/start")
        assert a.kwargs["json"] == {"actionMode": "immediate"}

    @pytest.mark.asyncio
    async def test_target_soc_puts_merged_settings(self):
        """set-target-soc reads current charge settings and PUTs the merged
        object (VW replaces the whole object) with the carnet Bearer."""
        client = _client()
        client._get_read_session_token = AsyncMock(  # type: ignore[method-assign]
            return_value="carnet-tok"
        )
        client._read = AsyncMock(  # type: ignore[method-assign]
            return_value={"chargeSettings": {"autoUnlockPlug": "PERMANENT",
                                             "targetSOCPercentage": 80}}
        )
        client._request = AsyncMock(return_value={})  # type: ignore[method-assign]
        await client.command_set_target_soc("VWNA00000000000001", 90)
        a = client._request.await_args
        assert a.args[0] == "PUT"
        assert a.args[1].endswith("/ev/v1/vehicle/uuid-xyz/charging/settings")
        # merged: other setting preserved, target overwritten to 90
        assert a.kwargs["json"] == {"autoUnlockPlug": "PERMANENT",
                                    "targetSOCPercentage": 90}


# ---------------------------------------------------------------------------
# 3) Climate naming fallback (NA pretripclimate -> EU climatisation on 404)
# ---------------------------------------------------------------------------


class TestClimateFallback:
    """NA climatisation naming first, EU naming as fallback on 404."""

    @pytest.mark.asyncio
    async def test_start_climate_na_naming_first(self):
        client = _client()
        urls: list[str] = []

        async def fake_post(url, **kwargs):  # noqa: ARG001
            urls.append(url)
            return {}

        client._post = fake_post  # type: ignore[method-assign]
        await client.command_start_climate("VWNA00000000000001")
        assert urls[0].endswith("/pretripclimate/start")

    @pytest.mark.asyncio
    async def test_start_climate_falls_to_eu_naming_on_404(self):
        from custom_components.vag_connect.cariad.exceptions import APIError

        client = _client()
        urls: list[str] = []

        async def fake_post(url, **kwargs):  # noqa: ARG001
            urls.append(url)
            if "/pretripclimate/start" in url:
                raise APIError(404, url, "not found")
            return {}

        client._post = fake_post  # type: ignore[method-assign]
        await client.command_start_climate("VWNA00000000000001")
        assert len(urls) == 2
        assert urls[0].endswith("/pretripclimate/start")
        assert urls[1].endswith("/climatisation/start")

    @pytest.mark.asyncio
    async def test_stop_climate_na_naming_first(self):
        client = _client()
        urls: list[str] = []

        async def fake_post(url, **kwargs):  # noqa: ARG001
            urls.append(url)
            return {}

        client._post = fake_post  # type: ignore[method-assign]
        await client.command_stop_climate("VWNA00000000000001")
        assert urls[0].endswith("/pretripclimate/stop")

    @pytest.mark.asyncio
    async def test_window_heating_start_falls_back(self):
        from custom_components.vag_connect.cariad.exceptions import APIError

        client = _client()
        urls: list[str] = []

        async def fake_post(url, **kwargs):  # noqa: ARG001
            urls.append(url)
            if "/pretripclimate/windowheating/start" in url:
                raise APIError(404, url, "not found")
            return {}

        client._post = fake_post  # type: ignore[method-assign]
        await client.command_start_window_heating("VWNA00000000000001")
        assert len(urls) == 2
        assert urls[0].endswith("/pretripclimate/windowheating/start")
        assert urls[1].endswith("/climatisation/windowheating/start")


# ---------------------------------------------------------------------------
# Sanity check - gating
# ---------------------------------------------------------------------------


class TestSensorGating:
    """The cross-brand subscription + capability sensors must be phantom-
    protected so non-NA brands without the privileges endpoint don't
    surface phantom Unbekannt entities."""

    def test_subscription_keys_gated_in_sensor(self):
        from custom_components.vag_connect.sensor import _DATA_PRESENT_REQUIRED

        for key in (
            "subscription_expiry_at",
            "subscription_days_remaining",
            "capabilities_count",
        ):
            assert key in _DATA_PRESENT_REQUIRED, (
                f"v2.10.0 VW NA subscription sensor `{key}` missing from "
                f"_DATA_PRESENT_REQUIRED"
            )

    def test_subscription_active_gated_in_binary_sensor(self):
        from custom_components.vag_connect.binary_sensor import (
            _DATA_PRESENT_REQUIRED,
        )

        assert "subscription_active" in _DATA_PRESENT_REQUIRED
