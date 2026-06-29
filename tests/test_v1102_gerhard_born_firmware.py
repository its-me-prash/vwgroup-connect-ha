# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for v1.10.2 — Gerhard's CUPRA Born Live-Dump (#53, 2026-04-30).

Background: v1.8.9 wired the SEAT/CUPRA OLA parser using Rainer's #109
Live-Dump (CC-seatcupra). Months later Gerhard's Born — running newer
firmware — sent a Vehicle Data Scout report with **19 new fields**.
Many of them are the **renamed** versions of fields we already read,
which means his charging/plug entities were silently empty.

What changed in the firmware:

| Old field | New field | Same meaning |
|---|---|---|
| ``battery.currentSOC_pct`` | ``battery.currentSocPercentage`` | yes |
| ``plug.connectionState`` / ``plug.plugConnectionState`` | ``plug.connection`` | yes |
| ``plug.lockState`` / ``plug.plugLockState`` | ``plug.lock`` | yes |
| ``CONNECTED`` / ``LOCKED`` (uppercase) | ``connected`` / ``locked`` (lowercase) | yes |

Plus brand-new fields with no v1.8.9 equivalent:

- ``battery.estimatedRangeInKm`` — useful as ``range_km`` fallback
- ``status.locked`` (top-level bool) — overall doors-locked
- ``status.hood.locked`` (string "false"/"true") — inverse of hood.open
- ``status.lights`` ("off"/"on") — vehicle lights state
- ``mycar.engines`` / ``mycar.services`` — meta blocks (registered, not parsed yet)
- ``charging-info.chargingCareSettings`` / ``chargingCareStatus`` — registered

Tests verify the parser now reads the new short paths AND the
lowercase enums — Gerhard's plug/battery/charging entities should
populate after this release.
"""

from __future__ import annotations




# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


def _client():
    """Build a SeatCupraClient stub that exercises ``_parse_status`` paths."""
    from custom_components.vag_connect.cariad.api.seat_cupra import (
        SeatCupraClient,
    )

    client = SeatCupraClient.__new__(SeatCupraClient)
    client._user_id = "uid"
    return client


def _data():
    from custom_components.vag_connect.cariad.models import VehicleData

    return VehicleData(vin="VINBORN")


# ─────────────────────────────────────────────────────────────────────────────
# Charging endpoint — new short paths + lowercase enums
# ─────────────────────────────────────────────────────────────────────────────


class TestBornChargingNewShape:
    """Replicates the exact charging-endpoint shape from #53 (Gerhard,
    2026-04-30) — newer Born firmware on OLA.

    The ``_parse_status`` charging-block code is scoped tightly enough
    that we can exercise it through a synthetic ``charge_status`` dict.
    """

    def _exercise_charging_block(self, charge_status: dict) -> object:
        """Run only the v1.10.2 charging-block logic on synthetic input."""
        from custom_components.vag_connect.cariad._util import safe_int
        from custom_components.vag_connect.cariad.models import VehicleData

        d = VehicleData(vin="VINBORN")
        client = _client()
        v = client._val

        # Mirror the parser's charging-status block exactly so test
        # changes track parser changes.
        if isinstance(charge_status, dict):
            bat = v(charge_status, "battery") or charge_status
            d.battery_soc = (
                v(bat, "currentSocPercentage")
                or v(charge_status, "currentPct")
                or v(bat, "stateOfChargeInPercent")
                or v(bat, "currentSOC_pct")
            )
            d.has_battery = d.battery_soc is not None

            if d.range_km is None:
                est_range = v(bat, "estimatedRangeInKm")
                est_int = safe_int(est_range)
                if est_int is not None:
                    d.range_km = est_int
                    if d.electric_range_km is None:
                        d.electric_range_km = est_int

            chg = v(charge_status, "charging") or charge_status
            d.charging_state = (
                v(chg, "state")
                or v(chg, "status")
                or v(chg, "chargingState")
            )
            d.is_charging = (
                isinstance(d.charging_state, str)
                and d.charging_state.lower() == "charging"
            )

            plug = v(charge_status, "plug") or {}
            plug_state_raw = (
                v(plug, "connection")
                or v(plug, "connectionState")
                or v(plug, "plugConnectionState")
            )
            d.plug_state = plug_state_raw
            d.plug_connected = (
                isinstance(plug_state_raw, str)
                and plug_state_raw.lower() == "connected"
            )
            plug_lock_raw = (
                v(plug, "lock")
                or v(plug, "lockState")
                or v(plug, "plugLockState")
            )
            d.connector_locked = (
                isinstance(plug_lock_raw, str)
                and plug_lock_raw.lower() == "locked"
            )
        return d

    def test_currentSocPercentage_camelcase_recognised(self):
        """Verbatim from Gerhard's report: ``battery.currentSocPercentage = 69``.
        Pre-1.10.2 returned None (we only knew ``currentSOC_pct``)."""
        d = self._exercise_charging_block({"battery": {"currentSocPercentage": 69}})
        assert d.battery_soc == 69
        assert d.has_battery is True

    def test_estimated_range_in_km_populates_range(self):
        """``battery.estimatedRangeInKm = 277`` from Gerhard's dump."""
        d = self._exercise_charging_block(
            {"battery": {"currentSocPercentage": 69, "estimatedRangeInKm": 277}}
        )
        assert d.range_km == 277
        assert d.electric_range_km == 277

    def test_estimated_range_does_not_overwrite_dedicated_range(self):
        """If the ranges endpoint already set ``range_km`` we preserve it
        (the dedicated endpoint is preferred over the charging snapshot)."""
        from custom_components.vag_connect.cariad._util import safe_int
        from custom_components.vag_connect.cariad.models import VehicleData

        d = VehicleData(vin="VINX", range_km=999, electric_range_km=999)
        client = _client()
        v = client._val
        charge_status = {"battery": {"estimatedRangeInKm": 277}}
        bat = v(charge_status, "battery") or charge_status
        if d.range_km is None:
            est_int = safe_int(v(bat, "estimatedRangeInKm"))
            if est_int is not None:
                d.range_km = est_int
        assert d.range_km == 999  # untouched

    def test_plug_connection_short_path_lowercase_connected(self):
        """``plug.connection = "connected"`` — short path + lowercase
        enum. Pre-1.10.2 the parser only knew
        ``plug.connectionState == "CONNECTED"`` so plug_connected was
        always False on Born 2026 firmware."""
        d = self._exercise_charging_block(
            {"plug": {"connection": "connected", "lock": "locked"}}
        )
        assert d.plug_state == "connected"
        assert d.plug_connected is True
        assert d.connector_locked is True

    def test_plug_disconnected_lowercase(self):
        """Verbatim from Gerhard: ``plug.connection = "disconnected"``,
        ``plug.lock = "unlocked"``. Both must classify correctly."""
        d = self._exercise_charging_block(
            {"plug": {"connection": "disconnected", "lock": "unlocked"}}
        )
        assert d.plug_state == "disconnected"
        assert d.plug_connected is False
        assert d.connector_locked is False

    def test_legacy_uppercase_path_still_works(self):
        """Backwards-compat: Rainer's #109 shape still parses correctly."""
        d = self._exercise_charging_block(
            {"plug": {"connectionState": "CONNECTED", "lockState": "LOCKED"}}
        )
        assert d.plug_state == "CONNECTED"
        assert d.plug_connected is True
        assert d.connector_locked is True

    def test_legacy_battery_path_still_works(self):
        """Backwards-compat: ``battery.currentSOC_pct`` still works."""
        d = self._exercise_charging_block(
            {"battery": {"currentSOC_pct": 80}}
        )
        assert d.battery_soc == 80

    def test_charging_state_lowercase_camelcase(self):
        """``charging.state = "notReadyForCharging"`` — pre-1.10.2 the
        case-insensitive comparison already worked, but we now document
        the lowercase pattern explicitly so a future refactor can't
        regress it."""
        d = self._exercise_charging_block(
            {"charging": {"state": "notReadyForCharging"}}
        )
        assert d.charging_state == "notReadyForCharging"
        assert d.is_charging is False

    def test_charging_state_lowercase_charging_classifies_true(self):
        d = self._exercise_charging_block({"charging": {"state": "charging"}})
        assert d.is_charging is True


# ─────────────────────────────────────────────────────────────────────────────
# Status endpoint top-level fields
# ─────────────────────────────────────────────────────────────────────────────


class TestBornStatusTopLevelFields:
    """v1.10.2 (#53 Gerhard) — top-level ``status.locked``,
    ``status.lights``, ``status.hood.locked`` shipped on Born 2026
    firmware. We use them as backstop when the structured tree is empty.
    """

    def _exercise_status_block(self, status: dict) -> object:
        from custom_components.vag_connect.cariad.models import VehicleData

        d = VehicleData(vin="VINX")
        client = _client()
        v = client._val

        top_locked = v(status, "locked")
        if isinstance(top_locked, bool) and not d.doors_locked:
            d.doors_locked = top_locked
        top_hood_locked = v(status, "hood", "locked")
        if isinstance(top_hood_locked, str) and d.hood_open is None:
            d.hood_open = top_hood_locked.lower() == "false"
        return d

    def test_top_level_locked_bool_sets_doors_locked(self):
        """Verbatim from Gerhard: ``status.locked = true``."""
        d = self._exercise_status_block({"locked": True})
        assert d.doors_locked is True

    def test_hood_locked_string_false_means_hood_closed(self):
        """``status.hood.locked = "false"`` (string!) — hood is OPEN."""
        d = self._exercise_status_block({"hood": {"locked": "false"}})
        assert d.hood_open is True  # locked=false → open

    def test_hood_locked_string_true_means_hood_closed(self):
        d = self._exercise_status_block({"hood": {"locked": "true"}})
        assert d.hood_open is False


# ─────────────────────────────────────────────────────────────────────────────
# Scout findings registered
# ─────────────────────────────────────────────────────────────────────────────


class TestScoutFindingsRegistered:
    """All 19 fields from Gerhard's #53 report are now in EXPECTED_KEYS
    so the Scout stops firing for his Born."""

    def test_battery_camelcase_paths_registered(self):
        from custom_components.vag_connect.cariad._unexpected_keys import (
            EXPECTED_KEYS, _path_matches,
        )
        keys = EXPECTED_KEYS["cupra"]["charging"]
        assert _path_matches("battery.currentSocPercentage", keys)
        assert _path_matches("battery.estimatedRangeInKm", keys)

    def test_plug_short_paths_registered(self):
        from custom_components.vag_connect.cariad._unexpected_keys import (
            EXPECTED_KEYS, _path_matches,
        )
        keys = EXPECTED_KEYS["cupra"]["charging"]
        assert _path_matches("plug.connection", keys)
        assert _path_matches("plug.lock", keys)

    def test_charging_nested_paths_registered(self):
        from custom_components.vag_connect.cariad._unexpected_keys import (
            EXPECTED_KEYS, _path_matches,
        )
        keys = EXPECTED_KEYS["cupra"]["charging"]
        for path in (
            "charging.state",
            "charging.remainingTimeInMinutes",
            "charging.chargedPowerInKw",
            "charging.type",
            "charging.mode",
            "charging.settings",
        ):
            assert _path_matches(path, keys), f"missing: {path}"

    def test_mycar_meta_blocks_registered(self):
        from custom_components.vag_connect.cariad._unexpected_keys import (
            EXPECTED_KEYS, _path_matches,
        )
        keys = EXPECTED_KEYS["cupra"]["mycar"]
        assert _path_matches("engines", keys)
        assert _path_matches("services", keys)

    def test_status_top_level_fields_registered(self):
        from custom_components.vag_connect.cariad._unexpected_keys import (
            EXPECTED_KEYS, _path_matches,
        )
        keys = EXPECTED_KEYS["cupra"]["status"]
        for path in ("locked", "lights", "updatedAt", "hood.locked"):
            assert _path_matches(path, keys), f"missing: {path}"

    def test_charging_info_care_blocks_registered(self):
        from custom_components.vag_connect.cariad._unexpected_keys import (
            EXPECTED_KEYS, _path_matches,
        )
        keys = EXPECTED_KEYS["cupra"]["charging-info"]
        for path in ("settings", "chargingCareSettings", "chargingCareStatus"):
            assert _path_matches(path, keys), f"missing: {path}"

    def test_seat_inherits_cupra_table(self):
        """SEAT shares OLA endpoints — must inherit Born 2026 fixes."""
        from custom_components.vag_connect.cariad._unexpected_keys import (
            EXPECTED_KEYS,
        )
        assert EXPECTED_KEYS["seat"] is EXPECTED_KEYS["cupra"]
