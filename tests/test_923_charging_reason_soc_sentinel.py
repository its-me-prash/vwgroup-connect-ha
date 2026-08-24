# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#923 (@naked-head, VW e-up! 2020) — two more portal fields leaked the
backend no-reading sentinel, the same class the charge_type path (#1104)
already screens:

- ``charging_reason`` surfaced a bare ``invalid`` on a car that doesn't expose
  a charging reason (MQB-schema residue).
- ``remaining_time_target_soc`` surfaced the literal ``unsupported`` instead of
  reading unavailable.

Both are portal-dialect-only (single write path in ``_eu_data_act``), so one
guard each via the shared ``drop_charge_sentinel`` fixes it. A real value must
still survive — ``off``/a minutes count are genuine readings.

Everything here is synthetic.
"""
from __future__ import annotations

from custom_components.vag_connect.cariad.auth._eu_data_act import (
    map_dataset_to_vehicle_data,
)
from custom_components.vag_connect.cariad.models import VehicleData


def _map(fields: dict[str, object]) -> VehicleData:
    return map_dataset_to_vehicle_data(fields, VehicleData(vin="X"))


class TestChargingReasonSentinel:
    def test_bare_invalid_dropped(self) -> None:
        assert _map({"charging_reason_trigger": "invalid"}).charging_reason is None

    def test_prefixed_invalid_dropped(self) -> None:
        assert (
            _map({"charging_reason_trigger": "CHARGING_REASON_INVALID"}).charging_reason
            is None
        )

    def test_unsupported_dropped(self) -> None:
        assert (
            _map({"charging_reason_trigger": "unsupported"}).charging_reason is None
        )

    def test_real_reason_kept(self) -> None:
        # a genuine reason must survive the sentinel guard (its exact shortened
        # spelling is pre-existing behaviour we don't touch here)
        d = _map({"charging_reason_trigger": "CHARGING_REASON_TIMER"})
        assert d.charging_reason is not None
        assert "timer" in d.charging_reason.lower()


class TestRemainingTimeTargetSocSentinel:
    def test_unsupported_dropped(self) -> None:
        d = _map({"remaining_charging_time_target_soc": "unsupported"})
        assert d.remaining_time_target_soc is None

    def test_invalid_dropped(self) -> None:
        d = _map({"remaining_charging_time_target_soc": "invalid"})
        assert d.remaining_time_target_soc is None

    def test_real_minutes_value_kept(self) -> None:
        # a genuine reading is a minutes count — must pass through untouched
        d = _map({"remaining_charging_time_target_soc": 45})
        assert d.remaining_time_target_soc == 45
