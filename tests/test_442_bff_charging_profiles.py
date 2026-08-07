# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#442 — per-profile / per-location charging target SoC for VW EU + Audi.

Until now only SEAT/CUPRA parsed the charging-profile list; the VW-EU/Audi
selectivestatus path only counted queued changes. This parses the profile LIST
from automation.chargingProfiles.value into the same shape the Skoda/SEAT/CUPRA
path produces, so the existing per-profile entities populate for VW EU / Audi.

Field names are grounded in We Connect 4.2.1 (androguard Moshi-model dump):
ChargingProfile(id=...), targetSOC_pct / targetStateOfChargePercent, and the
GPS-derived active pointer vehiclePositionedInProfileID.
"""
from __future__ import annotations

from custom_components.vag_connect.cariad.api.vw_eu import (
    _bff_profile_target_soc,
    _parse_bff_charging_profiles,
)

_VALUE = {
    "chargingProfiles": [
        {"id": 1, "name": "Home", "targetSOC_pct": 80, "maxChargingCurrent": "maximum"},
        {"id": 2, "name": "Work", "options": {"targetStateOfChargePercent": 60}},
    ],
    "vehiclePositionedInProfileID": 2,
}


class TestParse:
    def test_list_and_count(self) -> None:
        out = _parse_bff_charging_profiles(_VALUE)
        assert out["charging_profiles_count"] == 2
        assert out["charging_profiles"][0]["target_soc_pct"] == 80
        assert out["charging_profiles"][0]["name"] == "Home"

    def test_active_is_the_gps_positioned_profile(self) -> None:
        # THE #442 payoff: the active profile's target SoC (60, nested under
        # options on the Work profile the car is parked in).
        out = _parse_bff_charging_profiles(_VALUE)
        assert out["active_charging_profile_target_soc_pct"] == 60
        assert out["active_charging_profile_name"] == "Work"

    def test_gps_pointer_wins_over_activeProfileId(self) -> None:
        out = _parse_bff_charging_profiles({**_VALUE, "activeProfileId": 1})
        assert out["active_charging_profile_target_soc_pct"] == 60

    def test_falls_back_to_activeProfileId(self) -> None:
        out = _parse_bff_charging_profiles(
            {"chargingProfiles": [{"id": 5, "targetSoc": 90}], "activeProfileId": 5}
        )
        assert out["active_charging_profile_target_soc_pct"] == 90


class TestDefensive:
    def test_unusable_shapes_return_empty(self) -> None:
        assert _parse_bff_charging_profiles(None) == {}
        assert _parse_bff_charging_profiles({}) == {}
        assert _parse_bff_charging_profiles({"chargingProfiles": "x"}) == {}
        assert _parse_bff_charging_profiles({"chargingProfiles": []}) == {}

    def test_target_soc_spellings_and_nesting(self) -> None:
        assert _bff_profile_target_soc({"targetStateOfChargePercentage": 70}) == 70
        assert _bff_profile_target_soc({"settings": {"targetStateOfChargeInPercent": 55}}) == 55
        assert _bff_profile_target_soc({"targetSOC_pct": 80}) == 80
        assert _bff_profile_target_soc({"foo": 1}) is None
        # a bool must never be read as a percentage
        assert _bff_profile_target_soc({"targetSoc": True}) is None
