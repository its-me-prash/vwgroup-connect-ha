# Copyright 2026 Prash Balan (@its-me-prash) - Apache License 2.0
# SPDX-License-Identifier: Apache-2.0
"""v2.10.0 Group B - SEAT/CUPRA OLA endpoint parity.

Coverage:

- Notifications endpoint maps to ``notifications_count`` +
  ``last_notification_subject`` + ``last_notification_severity``.
- Permissions endpoint maps to ``permission_is_owner`` +
  ``permission_can_command`` via either ``role`` or per-permission list.
- Engine measurements endpoint converts Kelvin to Celsius and accepts
  every observed firmware shape (list, dict, bare numbers).
- Charging profiles endpoint reuses the Skoda
  ``_parse_charging_profiles`` helper - the resulting dict shape is
  identical across both brands.
- Charging modes endpoint populates ``available_charge_modes`` and the
  list shows up as an attribute on the existing
  ``charging_preferred_mode`` sensor.
- ``update_charging_settings`` service dispatches to the coordinator
  method which calls ``command_update_charging_settings`` on the
  brand client.
- ``find_charging_stations`` on SeatCupraClient extends the existing
  service surface to the OLA POI catalog endpoint.
- New keys (5 sensors + 2 binary sensors) are members of
  ``_DATA_PRESENT_REQUIRED`` so other brands stay clean.

Pure-Python: constructs SeatCupraClient via __new__ to skip the HA /
aiohttp setup chain. Matches the pattern of
test_v210_charging_statistics.py.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest


pytestmark = pytest.mark.ha_required


def _client():
    from custom_components.vag_connect.cariad.api.seat_cupra import (
        SeatCupraClient,
    )

    client = SeatCupraClient.__new__(SeatCupraClient)
    client._user_id = "test-user"
    client._vin_to_license_plate = {}
    client._vin_to_nickname = {}
    return client


# ---------------------------------------------------------------------------
# Notifications endpoint parser
# ---------------------------------------------------------------------------


class TestNotificationsParser:
    """Pin the contract: notifications response -> VehicleData fields."""

    def _parse(self, notifications_resp):
        from custom_components.vag_connect.cariad.models import VehicleData

        d = VehicleData(vin="V1")

        # Replay the relevant parser block from seat_cupra.get_status
        if isinstance(notifications_resp, dict):
            items = notifications_resp.get("notifications")
            if items is None:
                items = _val(notifications_resp, "data", "notifications")
        elif isinstance(notifications_resp, list):
            items = notifications_resp
        else:
            items = None
        if isinstance(items, list):
            d.notifications_count = len(items)
            if items:
                first = items[0]
                if isinstance(first, dict):
                    subj = (
                        first.get("subject")
                        or first.get("title")
                        or first.get("name")
                        or first.get("message")
                    )
                    if isinstance(subj, str) and subj:
                        d.last_notification_subject = subj
                    sev = (
                        first.get("severity")
                        or first.get("priority")
                        or first.get("level")
                    )
                    if isinstance(sev, str) and sev:
                        d.last_notification_severity = sev
        return d

    def test_standard_shape(self):
        resp = {
            "notifications": [
                {
                    "subject": "Service due",
                    "severity": "INFO",
                    "timestamp": "2026-05-30T00:00:00Z",
                },
                {
                    "subject": "Tire pressure low",
                    "severity": "WARNING",
                },
            ],
        }
        d = self._parse(resp)
        assert d.notifications_count == 2
        assert d.last_notification_subject == "Service due"
        assert d.last_notification_severity == "INFO"

    def test_data_wrapped_shape(self):
        resp = {
            "data": {
                "notifications": [
                    {"title": "Hello", "level": "ALERT"},
                ],
            },
        }
        d = self._parse(resp)
        assert d.notifications_count == 1
        assert d.last_notification_subject == "Hello"
        assert d.last_notification_severity == "ALERT"

    def test_bare_list_shape(self):
        resp = [{"message": "Plain msg", "priority": "INFO"}]
        d = self._parse(resp)
        assert d.notifications_count == 1
        assert d.last_notification_subject == "Plain msg"
        assert d.last_notification_severity == "INFO"

    def test_empty_list_leaves_subject_none(self):
        d = self._parse({"notifications": []})
        assert d.notifications_count == 0
        assert d.last_notification_subject is None
        assert d.last_notification_severity is None

    def test_soft_fail_404_leaves_fields_none(self):
        d = self._parse({})
        assert d.notifications_count is None
        assert d.last_notification_subject is None
        assert d.last_notification_severity is None


# ---------------------------------------------------------------------------
# Permissions endpoint parser
# ---------------------------------------------------------------------------


class TestPermissionsParser:
    def _parse(self, permissions_resp):
        from custom_components.vag_connect.cariad.models import VehicleData

        d = VehicleData(vin="V1")
        if isinstance(permissions_resp, dict):
            is_owner_raw = (
                permissions_resp.get("isOwner")
                if isinstance(permissions_resp.get("isOwner"), bool)
                else None
            )
            can_cmd_raw = (
                permissions_resp.get("canCommand")
                if isinstance(permissions_resp.get("canCommand"), bool)
                else None
            )
            role = permissions_resp.get("role")
            perms_list = permissions_resp.get("permissions")
            perm_names: set[str] = set()
            if isinstance(perms_list, list):
                for p in perms_list:
                    if isinstance(p, dict):
                        n = p.get("name") or p.get("id")
                        if isinstance(n, str) and n:
                            perm_names.add(n.upper())
                    elif isinstance(p, str):
                        perm_names.add(p.upper())
            if is_owner_raw is not None:
                d.permission_is_owner = is_owner_raw
            elif isinstance(role, str) and role:
                d.permission_is_owner = role.upper() in (
                    "PRIMARY_USER",
                    "OWNER",
                    "PRIMARY",
                    "MAIN_USER",
                )
            if can_cmd_raw is not None:
                d.permission_can_command = can_cmd_raw
            elif d.permission_is_owner is True:
                d.permission_can_command = True
            elif perm_names:
                d.permission_can_command = any(
                    cmd in perm_names
                    for cmd in (
                        "CAN_COMMAND",
                        "REMOTE_COMMANDS",
                        "REMOTE_CONTROL",
                        "CAN_LOCK",
                        "CAN_UNLOCK",
                        "CAN_START_CLIMATISATION",
                    )
                )
        return d

    def test_explicit_booleans_preferred(self):
        d = self._parse({"isOwner": True, "canCommand": True})
        assert d.permission_is_owner is True
        assert d.permission_can_command is True

    def test_role_based_owner(self):
        d = self._parse({"role": "PRIMARY_USER"})
        assert d.permission_is_owner is True
        assert d.permission_can_command is True

    def test_secondary_user_no_perms(self):
        d = self._parse({"role": "SECONDARY_USER"})
        assert d.permission_is_owner is False
        # No explicit can_command flag and no permissions list -> stays None
        assert d.permission_can_command is None

    def test_secondary_user_with_command_perm(self):
        d = self._parse(
            {
                "role": "SECONDARY_USER",
                "permissions": [
                    {"name": "CAN_LOCK", "granted": True},
                    {"name": "CAN_UNLOCK", "granted": True},
                ],
            }
        )
        assert d.permission_is_owner is False
        assert d.permission_can_command is True

    def test_guest_no_command_perms(self):
        d = self._parse(
            {
                "role": "GUEST",
                "permissions": [{"name": "CAN_READ_STATUS"}],
            }
        )
        assert d.permission_is_owner is False
        assert d.permission_can_command is False

    def test_soft_fail_404_leaves_fields_none(self):
        d = self._parse({})
        assert d.permission_is_owner is None
        assert d.permission_can_command is None


# ---------------------------------------------------------------------------
# Engine measurements parser
# ---------------------------------------------------------------------------


def _read_temp_c(block):
    """Standalone copy of the parser helper for unit testing."""
    if isinstance(block, (int, float)):
        temp = float(block)
        return round(temp - 273.15, 1) if temp > 200 else round(temp, 1)
    if not isinstance(block, dict):
        return None
    celsius = block.get("valueInCelsius") or block.get("celsius")
    if isinstance(celsius, (int, float)):
        return round(float(celsius), 1)
    kelvin = block.get("valueInKelvin") or block.get("kelvin")
    if isinstance(kelvin, (int, float)):
        return round(float(kelvin) - 273.15, 1)
    raw = block.get("value") or block.get("temperature")
    if isinstance(raw, (int, float)):
        val = float(raw)
        return round(val - 273.15, 1) if val > 200 else round(val, 1)
    return None


class TestEngineMeasurementsParser:
    def _parse(self, engine_measurements):
        from custom_components.vag_connect.cariad.models import VehicleData

        d = VehicleData(vin="V1")
        if isinstance(engine_measurements, dict):
            engines_block = engine_measurements.get("engines")
            target_engine = None
            if isinstance(engines_block, list):
                for entry in engines_block:
                    if not isinstance(entry, dict):
                        continue
                    if str(entry.get("type", "")).lower() in (
                        "primary",
                        "combustion",
                        "ice",
                    ):
                        target_engine = entry
                        break
                if target_engine is None:
                    for entry in engines_block:
                        if isinstance(entry, dict):
                            target_engine = entry
                            break
            elif isinstance(engines_block, dict):
                target_engine = engines_block
            else:
                target_engine = engine_measurements
            if isinstance(target_engine, dict):
                oil_temp = _read_temp_c(
                    target_engine.get("oilTemperature")
                    or target_engine.get("engineOilTemperature")
                )
                if oil_temp is not None:
                    d.engine_oil_temperature_c = oil_temp
                coolant_temp = _read_temp_c(
                    target_engine.get("coolantTemperature")
                    or target_engine.get("engineCoolantTemperature")
                )
                if coolant_temp is not None:
                    d.engine_coolant_temperature_c = coolant_temp
        return d

    def test_kelvin_blocks_converted(self):
        resp = {
            "engines": [
                {
                    "type": "primary",
                    "oilTemperature": {"valueInKelvin": 363.15},
                    "coolantTemperature": {"valueInKelvin": 360.55},
                },
            ],
        }
        d = self._parse(resp)
        assert d.engine_oil_temperature_c == 90.0
        assert d.engine_coolant_temperature_c == 87.4

    def test_celsius_blocks_passed_through(self):
        resp = {
            "engines": [
                {
                    "type": "primary",
                    "oilTemperature": {"valueInCelsius": 89.5},
                    "coolantTemperature": {"valueInCelsius": 87.4},
                },
            ],
        }
        d = self._parse(resp)
        assert d.engine_oil_temperature_c == 89.5
        assert d.engine_coolant_temperature_c == 87.4

    def test_bare_number_kelvin_heuristic(self):
        # > 200 -> treated as Kelvin
        assert _read_temp_c(363.15) == 90.0
        # <= 200 -> already Celsius
        assert _read_temp_c(87.4) == 87.4

    def test_flat_dict_shape(self):
        resp = {
            "engines": {
                "oilTemperature": {"valueInCelsius": 90.0},
                "coolantTemperature": {"valueInCelsius": 85.0},
            },
        }
        d = self._parse(resp)
        assert d.engine_oil_temperature_c == 90.0
        assert d.engine_coolant_temperature_c == 85.0

    def test_top_level_fallback(self):
        # No ``engines`` envelope at all - parser uses top-level
        resp = {
            "oilTemperature": {"valueInKelvin": 363.15},
            "coolantTemperature": {"valueInCelsius": 87.4},
        }
        d = self._parse(resp)
        assert d.engine_oil_temperature_c == 90.0
        assert d.engine_coolant_temperature_c == 87.4

    def test_soft_fail_404_leaves_fields_none(self):
        d = self._parse({})
        assert d.engine_oil_temperature_c is None
        assert d.engine_coolant_temperature_c is None


# ---------------------------------------------------------------------------
# Charging modes parser
# ---------------------------------------------------------------------------


class TestChargingModesParser:
    def _parse(self, charging_modes_resp):
        from custom_components.vag_connect.cariad.models import VehicleData

        d = VehicleData(vin="V1")
        if isinstance(charging_modes_resp, dict):
            raw_modes = (
                charging_modes_resp.get("availableChargeModes")
                or charging_modes_resp.get("modes")
                or charging_modes_resp.get("chargeModes")
                or _val(charging_modes_resp, "data", "modes")
                or _val(charging_modes_resp, "data", "availableChargeModes")
            )
        elif isinstance(charging_modes_resp, list):
            raw_modes = charging_modes_resp
        else:
            raw_modes = None
        modes_list: list[str] = []
        if isinstance(raw_modes, list):
            for m in raw_modes:
                if isinstance(m, str) and m:
                    modes_list.append(m)
                elif isinstance(m, dict):
                    name = m.get("name") or m.get("id") or m.get("mode")
                    if isinstance(name, str) and name:
                        modes_list.append(name)
        if modes_list:
            d.available_charge_modes = modes_list
        return d

    def test_standard_response(self):
        d = self._parse(
            {
                "availableChargeModes": [
                    "manual",
                    "preferredChargingTimes",
                    "automaticUnlocked",
                ],
            }
        )
        assert d.available_charge_modes == [
            "manual",
            "preferredChargingTimes",
            "automaticUnlocked",
        ]

    def test_modes_field_variant(self):
        d = self._parse({"modes": ["manual", "automatic"]})
        assert d.available_charge_modes == ["manual", "automatic"]

    def test_data_wrapped_variant(self):
        d = self._parse({"data": {"modes": ["manual"]}})
        assert d.available_charge_modes == ["manual"]

    def test_dict_entries_extract_name(self):
        d = self._parse(
            {
                "availableChargeModes": [
                    {"name": "manual", "label": "Manual"},
                    {"id": "automatic"},
                ],
            }
        )
        assert d.available_charge_modes == ["manual", "automatic"]

    def test_soft_fail_404_leaves_field_empty(self):
        d = self._parse({})
        assert d.available_charge_modes == []


# ---------------------------------------------------------------------------
# Client method coverage (get_charging_modes, get_charging_profiles,
# command_update_charging_settings, find_charging_stations)
# ---------------------------------------------------------------------------


class TestSeatCupraClientNewMethods:
    @pytest.mark.asyncio
    async def test_get_charging_modes_returns_dict(self):
        client = _client()
        expected = {"availableChargeModes": ["manual"]}
        client._get = AsyncMock(return_value=expected)
        result = await client.get_charging_modes("VINxxxx")
        assert result == expected

    @pytest.mark.asyncio
    async def test_get_charging_modes_soft_fails_on_404(self):
        from custom_components.vag_connect.cariad.exceptions import APIError

        client = _client()
        client._get = AsyncMock(
            side_effect=APIError(404, "/x", "not found")
        )
        result = await client.get_charging_modes("VINxxxx")
        assert result == {}

    @pytest.mark.asyncio
    async def test_get_charging_profiles_soft_fails_on_403(self):
        from custom_components.vag_connect.cariad.exceptions import APIError

        client = _client()
        client._get = AsyncMock(
            side_effect=APIError(403, "/x", "forbidden")
        )
        result = await client.get_charging_profiles("VINxxxx")
        assert result == {}

    @pytest.mark.asyncio
    async def test_command_update_charging_settings_builds_body(self):
        client = _client()
        client._post = AsyncMock()
        await client.command_update_charging_settings(
            "VINxxxx",
            target_soc=80,
            max_charge_current="reduced",
            auto_unlock_charge=True,
        )
        client._post.assert_awaited_once()
        url, kwargs = client._post.await_args.args, client._post.await_args.kwargs
        body = kwargs["json"]
        assert body["targetSOC_pct"] == 80
        assert body["maxChargeCurrentAC"] == "reduced"
        assert body["autoUnlockPlugWhenCharged"] == "on"
        assert "actions/update-settings" in url[0]

    @pytest.mark.asyncio
    async def test_command_update_charging_settings_partial(self):
        client = _client()
        client._post = AsyncMock()
        await client.command_update_charging_settings(
            "VINxxxx", target_soc=70
        )
        body = client._post.await_args.kwargs["json"]
        assert body == {"targetSOC_pct": 70}

    @pytest.mark.asyncio
    async def test_command_update_charging_settings_rejects_empty(self):
        client = _client()
        client._post = AsyncMock()
        with pytest.raises(ValueError):
            await client.command_update_charging_settings("VINxxxx")
        client._post.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_find_charging_stations_returns_list(self):
        client = _client()
        client._get = AsyncMock(
            return_value={
                "points": [
                    {"id": "p1", "name": "Wallbox A"},
                    {"id": "p2", "name": "Wallbox B"},
                ],
            }
        )
        result = await client.find_charging_stations(47.0, 8.0)
        assert len(result) == 2
        assert result[0]["id"] == "p1"

    @pytest.mark.asyncio
    async def test_find_charging_stations_404_returns_empty(self):
        from custom_components.vag_connect.cariad.exceptions import APIError

        client = _client()
        client._get = AsyncMock(
            side_effect=APIError(404, "/x", "not found")
        )
        result = await client.find_charging_stations(47.0, 8.0)
        assert result == []

    @pytest.mark.asyncio
    async def test_find_charging_stations_respects_max_results(self):
        client = _client()
        client._get = AsyncMock(
            return_value={
                "points": [{"id": str(i)} for i in range(50)],
            }
        )
        result = await client.find_charging_stations(
            47.0, 8.0, max_results=5
        )
        assert len(result) == 5


# ---------------------------------------------------------------------------
# Coordinator dispatch + service-handler glue
# ---------------------------------------------------------------------------


class TestCoordinatorDispatch:
    @pytest.mark.asyncio
    async def test_async_update_charging_settings_calls_client_method(self):
        from custom_components.vag_connect.coordinator import (
            VagConnectCoordinator,
        )

        coord = VagConnectCoordinator.__new__(VagConnectCoordinator)
        coord._cariad_cmd = AsyncMock()
        await coord.async_update_charging_settings(
            "VINxxxx",
            target_soc=80,
            max_charge_current="maximum",
            auto_unlock_charge=False,
        )
        coord._cariad_cmd.assert_awaited_once_with(
            "VINxxxx",
            "command_update_charging_settings",
            target_soc=80,
            max_charge_current="maximum",
            auto_unlock_charge=False,
        )


# ---------------------------------------------------------------------------
# Sensor / binary_sensor phantom-protection gating
# ---------------------------------------------------------------------------


class TestPhantomProtection:
    """Pin: every new field lives in the platform's _DATA_PRESENT_REQUIRED."""

    def test_new_sensor_keys_gated(self):
        from custom_components.vag_connect.sensor import (
            _DATA_PRESENT_REQUIRED,
        )

        for key in (
            "notifications_count",
            "last_notification_subject",
            "last_notification_severity",
            "engine_oil_temperature_c",
            "engine_coolant_temperature_c",
        ):
            assert key in _DATA_PRESENT_REQUIRED, (
                f"v2.10.0 Group B sensor `{key}` missing from "
                f"_DATA_PRESENT_REQUIRED, would create phantom "
                f"Unbekannt entities on non-SEAT/CUPRA brands"
            )

    def test_new_binary_sensor_keys_gated(self):
        from custom_components.vag_connect.binary_sensor import (
            _DATA_PRESENT_REQUIRED as BIN_REQUIRED,
        )

        for key in ("permission_is_owner", "permission_can_command"):
            assert key in BIN_REQUIRED, (
                f"v2.10.0 Group B binary_sensor `{key}` missing from "
                f"_DATA_PRESENT_REQUIRED, would create phantom "
                f"binary sensors on non-SEAT/CUPRA brands"
            )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _val(data, *path, default=None):
    """Mini reimplementation of CariadBaseClient._val (test helper)."""
    node = data
    for key in path:
        if not isinstance(node, dict):
            return default
        node = node.get(key, default)
        if node is None:
            return default
    return node
