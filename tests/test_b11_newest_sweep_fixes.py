# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""b11 — fixes from the newest-comments deep sweep.

#1343 (@n300home) — Skoda cars that return NO charging-profiles never populate
``max_charging_current`` (the charge-current select's usual source), so the
"Max. Ladestrom" select showed Unknown even though the plain charging settings
carry the MAXIMUM/REDUCED enum (``maxChargeCurrentAc``). The select now falls
back to that enum, captured into ``VehicleData.max_charge_current_enum``.
"""
from __future__ import annotations

from dataclasses import asdict
from unittest.mock import MagicMock

from custom_components.vag_connect.cariad.models import VehicleData


# ── #1343: the new field is real and is emitted into the vehicle dict ────────

def test_vehicledata_carries_enum_field_and_emits_it() -> None:
    d = VehicleData(vin="VINX", max_charge_current_enum="MAXIMUM")
    assert d.max_charge_current_enum == "MAXIMUM"
    # to_dict()/asdict emits every field → the select can read it off the dict.
    assert asdict(d)["max_charge_current_enum"] == "MAXIMUM"


def test_vehicledata_enum_defaults_none() -> None:
    assert VehicleData(vin="VINX").max_charge_current_enum is None


# ── #1343: the Skoda select falls back to the enum when no profiles exist ────

class TestSkodaChargeCurrentEnumFallback:
    def _entity(self, vehicle: dict):
        from custom_components.vag_connect.select import VagSkodaChargeCurrentSelect
        coord = MagicMock()
        coord.data = {"VINX": vehicle}
        coord.vehicles = {"VINX": vehicle}
        e = VagSkodaChargeCurrentSelect.__new__(VagSkodaChargeCurrentSelect)
        e.coordinator = coord
        e._vin = "VINX"
        return e

    def test_enum_fallback_when_no_profiles(self) -> None:
        # the #1343 case: no profiles → max_charging_current unset, only the enum
        e = self._entity({"vin": "VINX", "max_charge_current_enum": "MAXIMUM"})
        assert e.current_option == "maximum"

    def test_enum_fallback_reduced_casefold(self) -> None:
        e = self._entity({"vin": "VINX", "max_charge_current_enum": "REDUCED"})
        assert e.current_option == "reduced"

    def test_profiles_value_wins_over_enum(self) -> None:
        # a profiles car keeps its profile-derived value even if the enum differs
        e = self._entity({
            "vin": "VINX",
            "max_charging_current": "REDUCED",
            "max_charge_current_enum": "MAXIMUM",
        })
        assert e.current_option == "reduced"

    def test_neither_present_is_none(self) -> None:
        assert self._entity({"vin": "VINX"}).current_option is None

    def test_unknown_enum_value_is_none(self) -> None:
        e = self._entity({"vin": "VINX", "max_charge_current_enum": "WEIRD"})
        assert e.current_option is None
