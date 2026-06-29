# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for v1.9.1 — hotfix #92 + Capability-Filter Phase 2 (#56).

Three groups:

- ``TestAudiLockSpin`` — issue #92: Audi S6 C8 returns ``403 spin_error``
  on ``/access/lock`` when no S-PIN is sent. Lock now passes the S-PIN
  through exactly the same way unlock does.
- ``TestVWEUWake`` — issue #92: ``/vehicle/v1/vehicles/{vin}/vehicleWakeup``
  returns 404 on premium Audi models. ``command_wake`` now uses
  ``_post_command`` for v1 → v2 fallback.
- ``TestClassifyAndAutoRecord`` — issue #56: improved body-content
  classification + ``_cariad_cmd`` auto-records failures into
  ``FeatureState`` so command-bound entities can hide themselves.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest


def _vw_eu_client():
    """Build a VWEUClient whose ``_post`` is fully mocked."""
    from custom_components.vag_connect.cariad.api.vw_eu import VWEUClient

    client = VWEUClient.__new__(VWEUClient)
    client._tokens = None
    client._post = AsyncMock(return_value=None)
    client._spin = ""
    client._v2_command_paths = {}
    return client


# ─────────────────────────────────────────────────────────────────────────────
# #92 — Audi lock requires S-PIN
# ─────────────────────────────────────────────────────────────────────────────


class TestAudiLockSpin:
    """v1.9.1 — Audi S6 C8 2021 fix.

    Pre-fix ``command_lock`` sent ``{"action": "lock"}`` with no S-PIN.
    Premium Audi backends respond ``403 spin_error``. The fix mirrors
    ``command_unlock`` and includes the S-PIN in the payload when set.
    """

    def test_lock_without_spin_payload_omits_spin_field(self):
        client = _vw_eu_client()
        asyncio.run(client.command_lock("VINX"))
        client._post.assert_awaited_once()
        call_kwargs = client._post.await_args.kwargs
        body = call_kwargs.get("json", {})
        assert body.get("action") == "lock"
        assert "spin" not in body  # no S-PIN configured → no field

    def test_lock_with_spin_kwarg_includes_in_payload(self):
        client = _vw_eu_client()
        asyncio.run(
            client.command_lock("VINX", spin="1234")
        )
        body = client._post.await_args.kwargs["json"]
        assert body == {"action": "lock", "spin": "1234"}

    def test_lock_with_client_default_spin_uses_it(self):
        client = _vw_eu_client()
        client._spin = "9876"
        asyncio.run(client.command_lock("VINX"))
        body = client._post.await_args.kwargs["json"]
        assert body == {"action": "lock", "spin": "9876"}

    def test_coordinator_lock_passes_spin_for_audi(self):
        """Coordinator's ``async_lock`` must forward the configured S-PIN
        through to the brand client when brand is audi/volkswagen.

        v1.11.1 update: ``async_lock`` now goes through the optimistic-UI
        path (``_cariad_cmd_optimistic``), so the test stub also needs
        ``_vehicles_lock`` and ``async_set_updated_data``.
        """
        import threading
        from custom_components.vag_connect.coordinator import VagConnectCoordinator

        coord = VagConnectCoordinator.__new__(VagConnectCoordinator)
        coord.entry = MagicMock()
        coord.entry.data = {"brand": "audi"}
        coord.entry.options = {"spin": "1234"}
        coord._cariad_client = MagicMock()
        coord._cariad_client.command_lock = AsyncMock()
        coord.async_request_refresh = AsyncMock()
        # Stub feature-state side-effects so ``_cariad_cmd`` doesn't blow up.
        coord.record_command_success = MagicMock()
        coord.record_command_failure = MagicMock()
        coord.vehicles = {"VINA": {"doors_locked": False}}
        # v1.11.1 — required by the optimistic-UI helper.
        coord._vehicles_lock = threading.Lock()
        coord.async_set_updated_data = MagicMock()

        asyncio.run(coord.async_lock("VINA"))
        coord._cariad_client.command_lock.assert_awaited_once_with("VINA", spin="1234")

    def test_coordinator_lock_no_spin_for_audi_falls_back_no_kwarg(self):
        import threading
        from custom_components.vag_connect.coordinator import VagConnectCoordinator

        coord = VagConnectCoordinator.__new__(VagConnectCoordinator)
        coord.entry = MagicMock()
        coord.entry.data = {"brand": "audi"}
        coord.entry.options = {}
        coord._cariad_client = MagicMock()
        coord._cariad_client.command_lock = AsyncMock()
        coord.async_request_refresh = AsyncMock()
        coord.record_command_success = MagicMock()
        coord.record_command_failure = MagicMock()
        coord.vehicles = {"VINA": {"doors_locked": False}}
        # v1.11.1 — required by the optimistic-UI helper.
        coord._vehicles_lock = threading.Lock()
        coord.async_set_updated_data = MagicMock()

        asyncio.run(coord.async_lock("VINA"))
        # Pre-1.9.1 behaviour: no spin kwarg when not configured.
        coord._cariad_client.command_lock.assert_awaited_once_with("VINA")


# ─────────────────────────────────────────────────────────────────────────────
# #92 — vehicleWakeup 404 fix
# ─────────────────────────────────────────────────────────────────────────────


class TestVWEUWake:
    """v1.9.1 — wake endpoint fix.

    Pre-fix ``command_wake`` hit ``/vehicle/v1/.../vehicleWakeup`` directly
    via ``self._post`` — no fallback. Premium Audi (S6 C8 2021) returns
    404 on this path. Now uses ``_post_command`` so the same v1 → v2
    fallback as every other command kicks in.
    """

    def test_wake_uses_post_command_dispatcher(self):
        """The wake endpoint goes through ``_post_command`` (not bare
        ``_post``) so its v1 → v2 retry takes effect on 404."""
        client = _vw_eu_client()
        client._post_command = AsyncMock(return_value=None)
        asyncio.run(client.command_wake("VINX"))
        client._post_command.assert_awaited_once_with(
            "VINX", "vehicleWakeup", json={}
        )

    def test_wake_v1_404_falls_back_to_v2(self):
        """Real path: v1 returns 404, v2 succeeds, VIN flips to v2-active."""
        from custom_components.vag_connect.cariad.exceptions import APIError

        client = _vw_eu_client()
        client._post = AsyncMock(side_effect=[
            APIError(404, "/v1/vehicleWakeup", "Not Found"),
            None,
        ])
        asyncio.run(client.command_wake("VINX"))
        assert client._post.call_count == 2
        assert "/vehicle/v1/" in client._post.call_args_list[0][0][0]
        assert "/vehicle/v2/" in client._post.call_args_list[1][0][0]
        assert client._supports_v2_paths("VINX")


# ─────────────────────────────────────────────────────────────────────────────
# #56 — classify_command_failure body sniffing + Phase-2 entity gating
# ─────────────────────────────────────────────────────────────────────────────


class TestClassifyAndAutoRecord:
    """Phase 2 wires body-content classification + entity availability."""

    def test_classify_spin_error_in_body(self):
        from custom_components.vag_connect.cariad.exceptions import (
            APIError, CommandFailureReason, classify_command_failure,
        )
        # Body taken verbatim from #92 (Audi S6 C8 2021)
        err = APIError(
            403,
            "/v1/access/lock",
            '{"error":{"message":"spin_error","spinState":"DEFINED","remainingTries":3}}',
        )
        assert classify_command_failure(err) == CommandFailureReason.SPIN_REQUIRED

    def test_classify_subscription_expired_in_body(self):
        from custom_components.vag_connect.cariad.exceptions import (
            APIError, CommandFailureReason, classify_command_failure,
        )
        err = APIError(
            400, "/v1/charging/start",
            '{"error":"subscription expired — renew at my.audi.com"}',
        )
        assert (
            classify_command_failure(err)
            == CommandFailureReason.SUBSCRIPTION_EXPIRED
        )

    def test_classify_not_entitled_in_body(self):
        from custom_components.vag_connect.cariad.exceptions import (
            APIError, CommandFailureReason, classify_command_failure,
        )
        err = APIError(403, "/v1/x", '{"reason":"not_entitled"}')
        assert classify_command_failure(err) == CommandFailureReason.NOT_ENTITLED

    def test_classify_falls_back_to_status_when_no_markers(self):
        from custom_components.vag_connect.cariad.exceptions import (
            APIError, CommandFailureReason, classify_command_failure,
        )
        err = APIError(500, "/v1/x", "Internal Server Error")
        assert classify_command_failure(err) == CommandFailureReason.BACKEND_ERROR

    def test_command_known_unsupported_only_after_definitive_no(self):
        """``is_command_known_unsupported`` is False until a definitive
        negative outcome lands. Transient errors leave it False."""
        from custom_components.vag_connect.coordinator import VagConnectCoordinator
        from custom_components.vag_connect.cariad.exceptions import (
            CommandFailureReason,
        )

        coord = VagConnectCoordinator.__new__(VagConnectCoordinator)
        coord.feature_states = {}

        # Initially: unknown → False
        assert coord.is_command_known_unsupported("VIN1", "command_lock") is False

        # Transient backend error → still False
        coord.record_command_failure(
            "VIN1", "command_lock", CommandFailureReason.BACKEND_ERROR,
        )
        assert coord.is_command_known_unsupported("VIN1", "command_lock") is False

        # Missing capability → True (definitive vehicle-level no)
        coord.record_command_failure(
            "VIN1", "command_lock", CommandFailureReason.MISSING_CAPABILITY,
        )
        assert coord.is_command_known_unsupported("VIN1", "command_lock") is True

        # A subsequent success on the same command flips it back
        coord.record_command_success("VIN1", "command_lock")
        assert coord.is_command_known_unsupported("VIN1", "command_lock") is False

    def test_command_known_unsupported_after_subscription_expiry(self):
        from custom_components.vag_connect.coordinator import VagConnectCoordinator
        from custom_components.vag_connect.cariad.exceptions import (
            CommandFailureReason,
        )

        coord = VagConnectCoordinator.__new__(VagConnectCoordinator)
        coord.feature_states = {}
        coord.record_command_failure(
            "VIN1", "command_start_climate",
            CommandFailureReason.SUBSCRIPTION_EXPIRED,
        )
        assert coord.is_command_known_unsupported(
            "VIN1", "command_start_climate"
        ) is True

    def test_cariad_cmd_records_classification_on_failure(self):
        """``_cariad_cmd`` must auto-route classified failures into
        ``record_command_failure`` so entities can react."""
        import asyncio
        from custom_components.vag_connect.coordinator import VagConnectCoordinator
        from custom_components.vag_connect.cariad.exceptions import (
            APIError, CommandFailureReason,
        )

        coord = VagConnectCoordinator.__new__(VagConnectCoordinator)
        coord.entry = MagicMock()
        coord.entry.data = {"brand": "audi"}
        coord._cariad_client = MagicMock()
        coord._cariad_client.command_lock = AsyncMock(
            side_effect=APIError(
                403, "/v1/access/lock",
                '{"error":{"message":"spin_error","spinState":"DEFINED"}}',
            )
        )
        coord.async_request_refresh = AsyncMock()
        # Stub for spy
        coord.feature_states = {}
        coord.record_command_failure = MagicMock(
            side_effect=lambda *a, **kw: VagConnectCoordinator.record_command_failure(
                coord, *a, **kw
            )
        )
        coord.record_command_success = MagicMock()

        with pytest.raises(APIError):
            asyncio.run(
                coord._cariad_cmd("VINA", "command_lock")
            )

        # The classification must have routed to SPIN_REQUIRED.
        coord.record_command_failure.assert_called_once()
        args = coord.record_command_failure.call_args.args
        assert args[1] == "command_lock"
        assert args[2] == CommandFailureReason.SPIN_REQUIRED


# ─────────────────────────────────────────────────────────────────────────────
# Vehicle Data Scout — newly-registered keys must NOT fire as findings
# ─────────────────────────────────────────────────────────────────────────────


class TestScoutKeyRegistration:
    """v1.9.1 — fields surfaced in #91 + #90 are now registered.

    The Vehicle Data Scout no longer flags them as drift; entity work
    can drill into them in a future MINOR release.
    """

    def test_audi_diesel_range_registered(self):
        from custom_components.vag_connect.cariad._unexpected_keys import (
            EXPECTED_KEYS, _path_matches,
        )
        keys = EXPECTED_KEYS["audi"]["selectivestatus"]
        assert _path_matches("measurements.rangeStatus.value.dieselRange", keys)
        assert _path_matches(
            "measurements.fuelLevelStatus.value.currentFuelLevel_pct", keys,
        )

    def test_vw_max_charge_current_amperes_registered(self):
        from custom_components.vag_connect.cariad._unexpected_keys import (
            EXPECTED_KEYS, _path_matches,
        )
        keys = EXPECTED_KEYS["volkswagen"]["selectivestatus"]
        assert _path_matches(
            "charging.chargingSettings.value.maxChargeCurrentAC_A", keys,
        )

    def test_top_level_diagnostic_blocks_registered(self):
        from custom_components.vag_connect.cariad._unexpected_keys import (
            EXPECTED_KEYS, _path_matches,
        )
        keys = EXPECTED_KEYS["volkswagen"]["selectivestatus"]
        for path in (
            "userCapabilities", "fuelStatus",
            "vehicleHealthInspection", "vehicleHealthWarnings",
            "automation", "departureProfiles",
        ):
            assert _path_matches(path, keys), f"missing: {path}"

    def test_lights_status_nested_paths_registered(self):
        from custom_components.vag_connect.cariad._unexpected_keys import (
            EXPECTED_KEYS, _path_matches,
        )
        keys = EXPECTED_KEYS["volkswagen"]["selectivestatus"]
        assert _path_matches(
            "vehicleLights.lightsStatus.value.carCapturedTimestamp", keys,
        )
        assert _path_matches(
            "vehicleLights.lightsStatus.value.lights", keys,
        )

    def test_audi_inherits_volkswagen_table(self):
        """Smoke check — Audi reports use the same registered keys."""
        from custom_components.vag_connect.cariad._unexpected_keys import (
            EXPECTED_KEYS,
        )
        assert EXPECTED_KEYS["audi"] is EXPECTED_KEYS["volkswagen"]
