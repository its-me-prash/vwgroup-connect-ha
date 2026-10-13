"""Companion entities keep their own unique-id namespace.

A companion (ADB) entry usually sits next to a cloud or EU Data Act entry for
the same VIN. With a bare ``{vin}_{key}`` both entries claimed the same ids, HA
dropped the second entry's copy ("does not generate unique IDs"), and the
companion's battery level, ranges, doors locked and currently charging never
reached HA. Companion entities now use ``{vin}_companion_{key}``; the setup
moves already-registered ids in place so entity ids and history stay.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from custom_components.vag_connect.const import (
    CONF_STRATEGY,
    STRATEGY_COMPANION_ADB,
    is_companion_entry_data,
    vehicle_unique_id,
)

VIN = "WVGZZZTEST0000001"


def _coordinator(companion: bool) -> MagicMock:
    coord = MagicMock()
    coord.entry.data = {CONF_STRATEGY: STRATEGY_COMPANION_ADB} if companion else {}
    coord.is_companion = MagicMock(return_value=companion)
    coord.is_read_only = MagicMock(return_value=False)
    coord.data = {VIN: {}}
    return coord


def test_vehicle_unique_id_namespaces() -> None:
    assert vehicle_unique_id(VIN, "battery_soc") == f"{VIN}_battery_soc"
    assert (
        vehicle_unique_id(VIN, "battery_soc", companion=True)
        == f"{VIN}_companion_battery_soc"
    )


def test_is_companion_entry_data() -> None:
    assert is_companion_entry_data({CONF_STRATEGY: STRATEGY_COMPANION_ADB})
    assert not is_companion_entry_data({CONF_STRATEGY: "cloud"})
    assert not is_companion_entry_data({})
    assert not is_companion_entry_data(None)
    assert not is_companion_entry_data(MagicMock())


def test_companion_entity_does_not_collide_with_cloud_entity() -> None:
    from custom_components.vag_connect.entity_base import VagConnectEntity

    cloud = VagConnectEntity(_coordinator(False), VIN, "battery_soc")
    companion = VagConnectEntity(_coordinator(True), VIN, "battery_soc")
    assert cloud.unique_id == f"{VIN}_battery_soc"
    assert companion.unique_id == f"{VIN}_companion_battery_soc"
    assert cloud.unique_id != companion.unique_id


class _FakeRegistry:
    def __init__(self, entries: list[SimpleNamespace]) -> None:
        self.entries = entries

    def async_get_entity_id(self, domain, platform, unique_id):
        for e in self.entries:
            if e.domain == domain and e.unique_id == unique_id:
                return e.entity_id
        return None

    def async_update_entity(self, entity_id, *, new_unique_id):
        for e in self.entries:
            if e.entity_id == entity_id:
                e.unique_id = new_unique_id


def _reg(entity_id: str, unique_id: str) -> SimpleNamespace:
    return SimpleNamespace(
        entity_id=entity_id, domain=entity_id.split(".")[0], unique_id=unique_id
    )


def test_setup_moves_registered_ids_in_place() -> None:
    import custom_components.vag_connect as integ

    entries = [
        _reg("sensor.tiguan_adb_charging_speed", f"{VIN}_charging_rate_kmh"),
        _reg("switch.tiguan_adb_charging", f"{VIN}_charging_switch"),
        # a legacy key that itself starts with "companion_"
        _reg("button.tiguan_reset", f"{VIN}_companion_reset_button"),
        _reg("number.settings_poll", "01ENTRY_scan_interval"),
        _reg("switch.settings_read", "01ENTRY_companion_read_charge_detail"),
    ]
    registry = _FakeRegistry(entries)
    entry = SimpleNamespace(entry_id="01ENTRY")
    with patch.object(integ.er, "async_get", return_value=registry), patch.object(
        integ.er, "async_entries_for_config_entry", return_value=list(entries)
    ):
        integ._migrate_companion_unique_ids(MagicMock(), entry, [VIN])

    by_id = {e.entity_id: e.unique_id for e in entries}
    assert by_id["sensor.tiguan_adb_charging_speed"] == f"{VIN}_companion_charging_rate_kmh"
    assert by_id["switch.tiguan_adb_charging"] == f"{VIN}_companion_charging_switch"
    # already in the namespace: the reset button's key is "reset_button", so
    # the id upstream shipped is exactly the one the entity builds now
    assert by_id["button.tiguan_reset"] == f"{VIN}_companion_reset_button"
    # entry-scoped ids are left alone
    assert by_id["number.settings_poll"] == "01ENTRY_scan_interval"
    assert by_id["switch.settings_read"] == "01ENTRY_companion_read_charge_detail"


def test_setup_migration_skips_when_target_id_exists() -> None:
    import custom_components.vag_connect as integ

    old = _reg("sensor.tiguan_battery_level_2", f"{VIN}_battery_soc")
    taken = _reg("sensor.tiguan_companion_battery", f"{VIN}_companion_battery_soc")
    registry = _FakeRegistry([old, taken])
    entry = SimpleNamespace(entry_id="01ENTRY")
    with patch.object(integ.er, "async_get", return_value=registry), patch.object(
        integ.er, "async_entries_for_config_entry", return_value=[old]
    ):
        integ._migrate_companion_unique_ids(MagicMock(), entry, [VIN])
    assert old.unique_id == f"{VIN}_battery_soc"


def test_utility_meter_probe_follows_the_namespace() -> None:
    from custom_components.vag_connect import utility_meter

    registry = _FakeRegistry([_reg("sensor.odo", f"{VIN}_companion_odometer_km")])
    with patch.object(utility_meter.er, "async_get", return_value=registry):
        assert utility_meter.any_source_sensor_present(MagicMock(), [VIN], companion=True)
        assert not utility_meter.any_source_sensor_present(MagicMock(), [VIN])


def test_no_companion_entity_key_carries_the_infix_again() -> None:
    """The helper adds the infix; a key starting with it would double it."""
    from custom_components.vag_connect.button import (
        VagCompanionForceRefreshButton,
        VagCompanionResetButton,
    )
    from custom_components.vag_connect.sensor import VagCompanionChargeModeSensor

    coord = _coordinator(True)
    for cls in (VagCompanionResetButton, VagCompanionForceRefreshButton,
                VagCompanionChargeModeSensor):
        uid = cls(coord, VIN).unique_id
        assert "_companion_companion_" not in uid, uid
    assert VagCompanionResetButton(coord, VIN).unique_id == f"{VIN}_companion_reset_button"


def test_doubled_ids_from_earlier_fork_builds_are_repaired() -> None:
    import custom_components.vag_connect as integ

    entries = [
        _reg("button.tiguan_reset", f"{VIN}_companion_companion_reset_button"),
        _reg("button.tiguan_refresh_vehicle", f"{VIN}_companion_companion_force_refresh_button"),
        _reg("sensor.tiguan_charging_mode", f"{VIN}_companion_companion_charge_mode"),
        _reg("sensor.tiguan_soc", f"{VIN}_companion_battery_soc"),
    ]
    registry = _FakeRegistry(entries)
    with patch.object(integ.er, "async_get", return_value=registry), patch.object(
        integ.er, "async_entries_for_config_entry", return_value=list(entries)
    ):
        integ._migrate_companion_unique_ids(MagicMock(), SimpleNamespace(entry_id="E"), [VIN])
    by_id = {e.entity_id: e.unique_id for e in entries}
    assert by_id == {
        "button.tiguan_reset": f"{VIN}_companion_reset_button",
        "button.tiguan_refresh_vehicle": f"{VIN}_companion_force_refresh_button",
        "sensor.tiguan_charging_mode": f"{VIN}_companion_charge_mode",
        "sensor.tiguan_soc": f"{VIN}_companion_battery_soc",
    }


def test_migration_runs_once_per_entry_and_version() -> None:
    """The flag, not an id prefix, says the move is done; version 1 entries
    run once more to repair doubled ids."""
    import custom_components.vag_connect as integ
    from custom_components.vag_connect.const import CONF_COMPANION_UID_NAMESPACE

    base = {CONF_STRATEGY: STRATEGY_COMPANION_ADB}
    assert integ._companion_uid_migration_due(base)
    assert integ._companion_uid_migration_due({**base, CONF_COMPANION_UID_NAMESPACE: 1})
    assert not integ._companion_uid_migration_due(
        {**base, CONF_COMPANION_UID_NAMESPACE: integ.COMPANION_UID_NAMESPACE_VERSION}
    )
    assert not integ._companion_uid_migration_due({})
    assert not integ._companion_uid_migration_due({CONF_STRATEGY: "cloud"})
