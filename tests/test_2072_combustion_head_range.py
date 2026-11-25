# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#2072 — a car without a high-voltage battery gets its headline range from
the total or combustion range when the merged headline is missing, or is 0
while the tank is not empty (no false low-fuel alarm). PHEVs, EVs and a real
0 with an empty or unknown tank are left alone."""
from __future__ import annotations

from custom_components.vag_connect.cariad._channel_merge import merge_channels
from custom_components.vag_connect.cariad.models import VehicleData

VIN = "WVWZZZ00000000001"


def _eu(**kw: object) -> VehicleData:
    return VehicleData(vin=VIN, **kw)  # type: ignore[arg-type]


def _merge(*pairs: tuple[str, VehicleData]) -> VehicleData:
    return merge_channels(list(pairs))


def test_zero_head_range_with_fuel_takes_total() -> None:
    """The reporter's constellation: range 0, combustion 760, total 780, fuel 100."""
    eu = _eu(range_km=0, combustion_range_km=760, total_range_km=780)
    web = _eu(fuel_level=100)
    m = _merge(("website_authproxy", web), ("eu_data_act", eu))
    assert m.range_km == 780
    assert m.combustion_range_km == 760
    assert m.total_range_km == 780
    assert m.has_battery is False


def test_missing_head_range_falls_back_to_combustion() -> None:
    eu = _eu(combustion_range_km=760, fuel_level=80)
    m = _merge(("eu_data_act", eu))
    assert m.range_km == 760


def test_missing_head_range_without_fuel_level_is_filled() -> None:
    eu = _eu(combustion_range_km=500)
    m = _merge(("eu_data_act", eu))
    assert m.range_km == 500


def test_real_zero_with_empty_tank_is_kept() -> None:
    eu = _eu(range_km=0, combustion_range_km=0, total_range_km=30, fuel_level=0)
    m = _merge(("eu_data_act", eu))
    assert m.range_km == 0


def test_zero_with_unknown_fuel_is_kept() -> None:
    eu = _eu(range_km=0, combustion_range_km=760, total_range_km=780)
    m = _merge(("eu_data_act", eu))
    assert m.range_km == 0


def test_nonzero_head_range_is_not_touched() -> None:
    eu = _eu(range_km=700, combustion_range_km=760, total_range_km=780,
             fuel_level=90)
    m = _merge(("eu_data_act", eu))
    assert m.range_km == 700


def test_phev_is_untouched() -> None:
    eu = _eu(range_km=0, combustion_range_km=600, total_range_km=640,
             electric_range_km=40, battery_soc=50, fuel_level=70)
    m = _merge(("eu_data_act", eu))
    assert m.has_battery is True
    assert m.range_km == 0


def test_ev_is_untouched() -> None:
    eu = _eu(range_km=None, electric_range_km=300, battery_soc=80)
    m = _merge(("eu_data_act", eu))
    assert m.range_km is None


def test_no_range_sources_leaves_none() -> None:
    m = _merge(("eu_data_act", _eu(fuel_level=50)))
    assert m.range_km is None


def test_provenance_follows_the_source_field() -> None:
    eu = _eu(range_km=0, combustion_range_km=760, total_range_km=780,
             field_captured_ts={"range_km": "2026-11-10T07:07:13+00:00"})
    web = _eu(fuel_level=100)
    m = _merge(("website_authproxy", web), ("eu_data_act", eu))
    assert m.range_km == 780
    assert m.field_sources["range_km"] == "eu_data_act"
    # the stamp of the replaced 0 must not stay attached to the new value
    assert "range_km" not in m.field_captured_ts
