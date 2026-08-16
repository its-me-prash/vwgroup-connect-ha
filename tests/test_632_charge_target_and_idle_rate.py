# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#632 (gr6803 VW ID.7) — two MEB charge-telemetry fixes, grounded in the
archived v3.0.3 gr6803/rogie67 diagnostics.

(a) Charge target read 100 while the user set 80: settings.target_soc carries the
    raw profile ceiling (100) but Battery Care caps the car at 80, so the
    effective target is the lower of the two.
(b) charging_rate_kmh stayed stuck at 29 while the car sat idle at
    READY_FOR_CHARGING: the #1090 idle-zeroing gates on plug_connected, which
    EU-Data-Act portal cars never report, so the stale rate was never cleared.
"""
from __future__ import annotations

from unittest.mock import MagicMock

from custom_components.vag_connect.cariad.auth._eu_data_act import (
    map_dataset_to_vehicle_data,
)
from custom_components.vag_connect.cariad.models import VehicleData

VIN = "WVWZZZE1ZPP000001"


# ── (a) target vs Battery-Care ceiling ────────────────────────────────────────
def _map(**fields):
    return map_dataset_to_vehicle_data(dict(fields), VehicleData(vin=VIN))


def test_target_capped_by_active_battery_care() -> None:
    d = _map(**{
        "settings.target_soc": "100",
        "battery_care_mode.charge_bcam_threshold": "80",
        "setting.bcam_activation": "ACTIVATED",
    })
    assert d.battery_care_mode_active is True
    assert d.battery_care_target_soc_pct == 80
    assert d.target_soc == 80          # min(100, 80) — the gr6803 case


def test_target_kept_when_below_care_threshold() -> None:
    d = _map(**{
        "settings.target_soc": "70",
        "battery_care_mode.charge_bcam_threshold": "80",
        "setting.bcam_activation": "ACTIVATED",
    })
    assert d.target_soc == 70          # min(70, 80) — profile target still binds


def test_target_untouched_when_care_inactive() -> None:
    d = _map(**{
        "settings.target_soc": "100",
        "battery_care_mode.charge_bcam_threshold": "80",
        "setting.bcam_activation": "DEACTIVATED",
    })
    assert d.battery_care_mode_active is False
    assert d.target_soc == 100         # care off → raw target untouched


def test_care_gapfill_still_works_without_profile_target() -> None:
    # Audi Q4 case: no settings.target_soc, care active → threshold IS the target.
    d = _map(**{
        "battery_care_mode.charge_bcam_threshold": "80",
        "setting.bcam_activation": "ACTIVATED",
    })
    assert d.target_soc == 80


# ── (b) stale charge power/rate on idle portal cars ───────────────────────────
def _sensor(key: str, **vehicle):
    from custom_components.vag_connect.sensor import (
        VagConnectSensor,
        VagSensorDescription,
    )

    coord = MagicMock()
    coord.data = {VIN: {"vin": VIN, **vehicle}}
    s = VagConnectSensor.__new__(VagConnectSensor)
    s._vin = VIN
    s.coordinator = coord
    s.entity_description = VagSensorDescription(key=key, data_key=key)
    return s


IDLE_KEYS = ("charging_power_kw", "charging_rate_kmh", "actual_charge_rate_kw")


def test_stale_rate_zeroed_on_idle_portal_car() -> None:
    # portal car: plug_connected never reported (None), is_charging explicitly off
    for key in IDLE_KEYS:
        s = _sensor(key, is_charging=False, charging_state="READY_FOR_CHARGING",
                    **{key: 29})
        assert s.native_value == 0, key


def test_rate_kept_while_charging() -> None:
    for key in IDLE_KEYS:
        s = _sensor(key, is_charging=True, plug_connected=True,
                    charging_state="CHARGING", **{key: 29})
        assert s.native_value == 29, key


def test_rate_unknown_when_is_charging_none() -> None:
    for key in IDLE_KEYS:
        s = _sensor(key, is_charging=None, **{key: 29})
        assert s.native_value == 29, key


def test_no_fabricated_zero_when_value_missing() -> None:
    # is_charging off but the field never arrived → stays unavailable, not 0
    s = _sensor("charging_rate_kmh", is_charging=False)
    assert s.native_value is None
