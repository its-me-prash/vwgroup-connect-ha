# Copyright 2026 Prash Balan (@its-me-prash) - Apache License 2.0
# SPDX-License-Identifier: Apache-2.0
"""v2.10.0 (Group C) - VW NA endpoint parity tests.

Covers the 4 new Cox-backend behaviours added in Group C:

1. ``get_subscription_privileges`` parses the
   ``/rrs/v1/privileges/user/{uid}/vehicle/{uuid}`` response and feeds
   ``subscription_active`` + ``subscription_expiry_at`` +
   ``subscription_days_remaining`` + ``capabilities_count`` onto
   VehicleData. Soft-fails on 401 / 403 / 404 / non-dict.

2. SPIN flow: ``SHA1(spin + nonce).hexdigest().upper()`` digest is the
   protocol-mandated handshake response.

3. ``command_lock`` / ``command_unlock`` hit the new
   ``/lockunlock/v1/vehicle/{uuid}`` endpoint first and fall back to the
   legacy ``/ev/v1/vehicle/{uuid}/lock`` on 404.

4. ``command_start_climate`` / stop hit ``/pretripclimate/{start,stop}``
   first and fall back to ``/climatisation/{start,stop}`` on 404.

Pure-Python tests; constructs VWNAClient via __new__ to skip the HA /
aiohttp setup chain. Matches the pattern of test_v1242_porsche_vw_na_parity.
"""

from __future__ import annotations

import hashlib
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
# 2) SPIN handshake
# ---------------------------------------------------------------------------


class TestSpinFlow:
    """Two-step challenge / response with SHA1(SPIN + nonce) digest."""

    @pytest.mark.asyncio
    async def test_sha1_response_correctness(self):
        """The protocol response must be SHA1(spin + nonce) uppercase hex."""
        client = _client()
        nonce = "deadbeef12345678"
        spin = "1234"
        expected_digest = hashlib.sha1(  # noqa: S324
            (spin + nonce).encode("utf-8")
        ).hexdigest().upper()

        # Capture the response body the helper sends to /spin
        sent_payloads: list = []

        async def fake_post(url, **kwargs):
            sent_payloads.append((url, kwargs.get("json")))
            if url.endswith("/challenge"):
                return {"challenge": nonce}
            if url.endswith("/spin"):
                return {"sessionToken": "session-token-xyz"}
            raise AssertionError(f"unexpected url {url}")

        client._post = fake_post  # type: ignore[method-assign]

        token = await client._get_na_spin_session_token(
            "VWNA00000000000001", spin
        )
        assert token == "session-token-xyz"
        # Two POSTs total: challenge, spin
        assert len(sent_payloads) == 2
        assert sent_payloads[0][0].endswith(
            "/ss/v1/user/user-abc/challenge"
        )
        assert sent_payloads[1][0].endswith(
            "/ss/v1/user/user-abc/spin"
        )
        # The /spin body carries the protocol digest
        assert sent_payloads[1][1]["response"] == expected_digest
        assert sent_payloads[1][1]["challenge"] == nonce

    @pytest.mark.asyncio
    async def test_alt_nonce_field_names(self):
        """Backend has shipped 3 key-names for the same field."""
        client = _client()

        async def fake_post(url, **kwargs):
            if url.endswith("/challenge"):
                return {"nonce": "abc"}  # alt key name
            return {"token": "tok"}  # alt session-token key

        client._post = fake_post  # type: ignore[method-assign]
        token = await client._get_na_spin_session_token(
            "VWNA00000000000001", "1234"
        )
        assert token == "tok"

    @pytest.mark.asyncio
    async def test_no_user_id_short_circuits(self):
        client = _client(user_id=None)
        token = await client._get_na_spin_session_token(
            "VWNA00000000000001", "1234"
        )
        assert token is None

    @pytest.mark.asyncio
    async def test_empty_spin_short_circuits(self):
        client = _client()
        token = await client._get_na_spin_session_token(
            "VWNA00000000000001", ""
        )
        assert token is None

    @pytest.mark.asyncio
    async def test_challenge_failure_returns_none(self):
        from custom_components.vag_connect.cariad.exceptions import APIError

        client = _client()
        client._post = AsyncMock(  # type: ignore[method-assign]
            side_effect=APIError(500, "/x", "server error")
        )
        token = await client._get_na_spin_session_token(
            "VWNA00000000000001", "1234"
        )
        assert token is None

    @pytest.mark.asyncio
    async def test_garbage_nonce_returns_none(self):
        client = _client()

        async def fake_post(url, **kwargs):  # noqa: ARG001
            return {"unrelated_field": 42}  # no challenge key

        client._post = fake_post  # type: ignore[method-assign]
        token = await client._get_na_spin_session_token(
            "VWNA00000000000001", "1234"
        )
        assert token is None


# ---------------------------------------------------------------------------
# 3) Lock primary endpoint, fallback to legacy on 404
# ---------------------------------------------------------------------------


class TestLockFallback:
    """``command_lock`` tries /lockunlock/v1 first, falls back on 404."""

    @pytest.mark.asyncio
    async def test_primary_endpoint_called_first(self):
        client = _client()
        urls: list[str] = []

        async def fake_post(url, **kwargs):  # noqa: ARG001
            urls.append(url)
            return {}

        client._post = fake_post  # type: ignore[method-assign]
        await client.command_lock("VWNA00000000000001")
        assert len(urls) == 1
        assert urls[0] == (
            "https://example.test/lockunlock/v1/vehicle/uuid-xyz"
        )

    @pytest.mark.asyncio
    async def test_falls_back_to_legacy_on_404(self):
        from custom_components.vag_connect.cariad.exceptions import APIError

        client = _client()
        urls: list[str] = []

        async def fake_post(url, **kwargs):  # noqa: ARG001
            urls.append(url)
            if "/lockunlock/" in url:
                raise APIError(404, url, "not found")
            return {}

        client._post = fake_post  # type: ignore[method-assign]
        await client.command_lock("VWNA00000000000001")
        # Primary attempted, then legacy
        assert len(urls) == 2
        assert urls[0].endswith("/lockunlock/v1/vehicle/uuid-xyz")
        assert urls[1].endswith("/ev/v1/vehicle/uuid-xyz/lock")

    @pytest.mark.asyncio
    async def test_non_404_propagates(self):
        """500 must propagate so the caller surfaces the real error."""
        from custom_components.vag_connect.cariad.exceptions import APIError

        client = _client()
        client._post = AsyncMock(  # type: ignore[method-assign]
            side_effect=APIError(500, "/x", "server error")
        )
        with pytest.raises(APIError) as exc:
            await client.command_lock("VWNA00000000000001")
        assert exc.value.status == 500

    @pytest.mark.asyncio
    async def test_unlock_sends_x_spin_session_when_token_present(self):
        """When the SPIN handshake succeeds, the unlock POST must carry
        the ``X-Spin-Session`` header."""
        client = _client()
        client._spin = "1234"

        captured_headers: dict = {}

        async def fake_post(url, **kwargs):
            if "/challenge" in url:
                return {"challenge": "n0nc3"}
            if url.endswith("/spin"):
                return {"sessionToken": "session-xyz"}
            # Action POST
            captured_headers.update(kwargs.get("headers") or {})
            return {}

        client._post = fake_post  # type: ignore[method-assign]
        await client.command_unlock("VWNA00000000000001")
        assert captured_headers.get("X-Spin-Session") == "session-xyz"


# ---------------------------------------------------------------------------
# 4) Climate naming fallback (NA pretripclimate -> EU climatisation on 404)
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
