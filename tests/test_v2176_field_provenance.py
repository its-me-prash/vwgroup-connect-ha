# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""A2 — per-field provenance: every reading knows which channel produced it.

``source_channel`` answers "which channels fed this car" and is only set when
a merge happened. It cannot answer "where did THIS reading come from", which
is what an entity needs to show its own source — on a Golf GTE the fuel level
and the SoC legitimately come from different channels.

``field_sources`` records {field_name: channel} for every field that carries a
value, on every merge including single-channel ones.
"""
from __future__ import annotations

from custom_components.vag_connect.cariad._channel_merge import merge_channels
from custom_components.vag_connect.cariad.models import VehicleData


def test_single_channel_still_gets_provenance() -> None:
    # The whole point: a one-source car must still know where its data is from.
    a = VehicleData(vin="V", battery_soc=55, odometer_km=1000)
    m = merge_channels([("eu_data_act", a)])
    assert m.field_sources["battery_soc"] == "eu_data_act"
    assert m.field_sources["odometer_km"] == "eu_data_act"


def test_gap_filled_field_is_attributed_to_the_filler() -> None:
    # The Golf GTE case: SoC from the portal, fuel from MBB.
    portal = VehicleData(vin="V", battery_soc=55)
    mbb = VehicleData(vin="V", fuel_level=80)
    m = merge_channels([("eu_data_act", portal), ("mbb", mbb)])
    assert m.field_sources["battery_soc"] == "eu_data_act"
    assert m.field_sources["fuel_level"] == "mbb"


def test_primary_keeps_ownership_when_both_carry_the_field() -> None:
    # A supplementary never overwrites the primary, so it never owns the field.
    primary = VehicleData(vin="V", battery_soc=55)
    supp = VehicleData(vin="V", battery_soc=99)
    m = merge_channels([("eu_data_act", primary), ("vw_de", supp)])
    assert m.battery_soc == 55
    assert m.field_sources["battery_soc"] == "eu_data_act"


def test_unset_fields_are_absent_not_guessed() -> None:
    a = VehicleData(vin="V", battery_soc=55)
    m = merge_channels([("eu_data_act", a)])
    assert "fuel_level" not in m.field_sources
    assert "odometer_km" not in m.field_sources


def test_field_sources_is_never_itself_merged() -> None:
    # It is bookkeeping, not vehicle data: a stale map on a source snapshot
    # must not leak into the merged result.
    a = VehicleData(vin="V", battery_soc=55)
    b = VehicleData(vin="V", fuel_level=80)
    b.field_sources = {"battery_soc": "LIES", "nonsense": "LIES"}
    m = merge_channels([("eu_data_act", a), ("mbb", b)])
    assert m.field_sources["battery_soc"] == "eu_data_act"
    assert "nonsense" not in m.field_sources


def test_provenance_matches_source_channel() -> None:
    # The two views must not contradict each other.
    portal = VehicleData(vin="V", battery_soc=55)
    mbb = VehicleData(vin="V", fuel_level=80)
    m = merge_channels([("eu_data_act", portal), ("mbb", mbb)])
    assert m.source_channel == "eu_data_act+mbb"
    assert set(m.field_sources.values()) == {"eu_data_act", "mbb"}


def test_vin_mismatch_contributes_nothing() -> None:
    a = VehicleData(vin="V", battery_soc=55)
    other = VehicleData(vin="OTHER", fuel_level=80)
    m = merge_channels([("eu_data_act", a), ("mbb", other)])
    assert "fuel_level" not in m.field_sources
    assert m.fuel_level is None
