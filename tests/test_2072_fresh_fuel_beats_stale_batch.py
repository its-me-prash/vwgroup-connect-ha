# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#2072 — a fresh live fuel level must beat a stale EU-Data-Act batch value.

A VW Tayron owner refuelled; vw.de reported 100% minutes old, but the EU-DA batch
still held a 2-day-old 23% and — being the higher-priority channel — won by plain
gap-fill, so HA showed 23%. fuel_level is the combustion twin of
electric_range_km (already live-superseding) and is non-monotonic, so a live
channel now supersedes a batch value for it too.
"""
from __future__ import annotations

from custom_components.vag_connect.cariad._channel_merge import merge_channels
from custom_components.vag_connect.cariad.models import VehicleData


def _vd(fuel: float) -> VehicleData:
    vd = VehicleData(vin="WVWZZZTESTVIN2072")
    vd.fuel_level = fuel
    return vd


def test_fresh_live_fuel_beats_stale_eu_data_act_batch() -> None:
    # eu_data_act is the higher-priority (primary) channel here, exactly as in the
    # report; the live vw.de channel must still win on fuel.
    merged = merge_channels([
        ("eu_data_act", _vd(23)),
        ("website_authproxy", _vd(100)),
    ])
    assert merged.fuel_level == 100
    assert merged.field_sources["fuel_level"] == "website_authproxy"


def test_eu_data_act_only_car_keeps_its_fuel() -> None:
    # No live channel present — the batch value must stand (no regression).
    merged = merge_channels([("eu_data_act", _vd(50))])
    assert merged.fuel_level == 50
    assert merged.field_sources["fuel_level"] == "eu_data_act"
