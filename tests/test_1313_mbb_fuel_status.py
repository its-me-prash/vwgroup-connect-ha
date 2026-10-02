# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#1313 — ``fuel/status``, the only state-of-charge source on MBB plug-in hybrids.

Those cars ship no drive-battery SoC in the EU Data Act portal feed, and their
``charging/status`` is refused with ``4004 missingUserConsent`` — so until now
they had no state of charge at all. ``fuel/status`` answers 200 on the same
realm / gdc / resource host as the maintenance read and carries BOTH drives.

Two reporters, two model years, with the bodies below taken from their captures:

* **@realynot** — Tiguan eHybrid 2023. Also established that the endpoint keeps
  answering 200 through a lapsed and renewed We Connect subscription, so the
  parser needs no subscription-state guard.
* **@fschulte2812** — Tiguan 1.5 eHybrid MY2026, identical shape.

(@Joassens' Passat GTE in #1659 is a plausible third but never tested this
endpoint, so it is not counted here.)

Both shapes seen on the one endpoint are covered: the LIST form with
``properties`` name/value pairs, and the flat DICT form. Every number arrives as
a STRING, unlike every other surface the integration parses.
"""
from __future__ import annotations

import re

from custom_components.vag_connect.cariad.auth._website_authproxy import (
    map_fuel_to_vehicle_data,
)
from custom_components.vag_connect.cariad.models import VehicleData

# @fschulte2812 / @realynot — the list form, verbatim shape
LIST_BODY = {"data": [
    {"id": "primaryEngine", "properties": [
        {"name": "engineType", "value": "gasoline"},
        {"name": "remainingRange_km", "value": "530"},
        {"name": "currentFuelLevel_pct", "value": "76"},
        {"name": "currentOilLevel_pct", "value": "100.0"},
    ]},
    {"id": "secondaryEngine", "carCapturedTimestamp": "2026-09-30T20:18:19Z",
     "properties": [
        {"name": "engineType", "value": "electric"},
        {"name": "remainingRange_km", "value": "10"},
        {"name": "currentSOC_pct", "value": "23"},
     ]},
]}

# @realynot — the earlier flat form, same car
DICT_BODY = {
    "secondaryEngine": {"currentSOC_pct": "23", "remainingRange_km": "10",
                        "engineType": "electric"},
    "primaryEngine": {"currentFuelLevel_pct": "76", "remainingRange_km": "530",
                      "currentOilLevel_pct": "100.0", "engineType": "gasoline"},
}


def _map(body, base: VehicleData | None = None) -> VehicleData:
    return map_fuel_to_vehicle_data(body, base or VehicleData(vin="X"))


def test_the_list_form_gives_a_phev_everything():
    d = _map(LIST_BODY)
    assert d.battery_soc == 23           # the whole point of the read
    assert d.electric_range_km == 10
    assert d.fuel_level == 76
    assert d.combustion_range_km == 530
    assert d.oil_level_pct == 100


def test_the_dict_form_gives_the_same_result():
    assert _map(DICT_BODY).battery_soc == _map(LIST_BODY).battery_soc
    d = _map(DICT_BODY)
    assert (d.battery_soc, d.electric_range_km, d.fuel_level,
            d.combustion_range_km) == (23, 10, 76, 530)


def test_engines_are_matched_on_type_not_on_position():
    """Which drive is "primary" is a property of the car, so keying on the
    position would be a guess — engineType states it outright. Here the order is
    swapped AND the electric drive is the primary one."""
    body = {"data": [
        {"id": "primaryEngine", "properties": [
            {"name": "engineType", "value": "electric"},
            {"name": "currentSOC_pct", "value": "64"},
            {"name": "remainingRange_km", "value": "300"},
        ]},
        {"id": "secondaryEngine", "properties": [
            {"name": "engineType", "value": "diesel"},
            {"name": "currentFuelLevel_pct", "value": "40"},
            {"name": "remainingRange_km", "value": "600"},
        ]},
    ]}
    d = _map(body)
    assert d.battery_soc == 64
    assert d.electric_range_km == 300
    assert d.fuel_level == 40
    assert d.combustion_range_km == 600


def test_an_unknown_engine_type_is_skipped_not_guessed():
    body = {"data": [{"id": "primaryEngine", "properties": [
        {"name": "engineType", "value": "fusion_reactor"},
        {"name": "currentSOC_pct", "value": "50"},
        {"name": "remainingRange_km", "value": "900"},
    ]}]}
    d = _map(body)
    assert d.battery_soc is None
    assert d.electric_range_km is None
    assert d.combustion_range_km is None


def test_a_brand_native_reading_always_wins():
    base = VehicleData(vin="X")
    base.battery_soc = 55
    base.fuel_level = 10
    d = _map(LIST_BODY, base)
    assert d.battery_soc == 55
    assert d.fuel_level == 10
    # ...while the fields it did NOT have are still filled
    assert d.electric_range_km == 10


def test_out_of_range_percentages_are_dropped():
    body = {"data": [
        {"id": "primaryEngine", "properties": [
            {"name": "engineType", "value": "gasoline"},
            {"name": "currentFuelLevel_pct", "value": "255"},
            {"name": "currentOilLevel_pct", "value": "-1"},
        ]},
        {"id": "secondaryEngine", "properties": [
            {"name": "engineType", "value": "electric"},
            {"name": "currentSOC_pct", "value": "255"},
        ]},
    ]}
    d = _map(body)
    assert d.battery_soc is None
    assert d.fuel_level is None
    assert d.oil_level_pct is None


def test_a_combustion_only_car_gets_no_phantom_soc():
    body = {"data": [{"id": "primaryEngine", "properties": [
        {"name": "engineType", "value": "diesel"},
        {"name": "currentFuelLevel_pct", "value": "80"},
        {"name": "remainingRange_km", "value": "700"},
    ]}]}
    d = _map(body)
    assert d.fuel_level == 80
    assert d.battery_soc is None
    assert d.electric_range_km is None


def test_garbage_leaves_the_vehicle_untouched():
    for body in (None, "", [], {}, {"data": None}, {"data": "nope"},
                 {"data": [{"no_id": 1}]}, 42):
        d = _map(body)
        assert d.battery_soc is None and d.fuel_level is None


def test_the_capture_timestamp_advances_last_seen():
    d = _map(LIST_BODY)
    assert d.last_seen_at is not None, (
        "a live read must anchor freshness or the stale-data repair misfires"
    )


def test_the_url_mirrors_the_maintenance_recipe():
    """Both reporters specified realm vw-de + gdc + the live VCF host — i.e. the
    maintenance read's recipe, which is why it rides a session that works."""
    from custom_components.vag_connect.cariad._authproxy import (
        build_fuel_url,
        build_maintenance_url,
    )

    fuel = build_fuel_url("WVWZZZ00000000001", "myvw-wcar-prod")
    maint = build_maintenance_url("WVWZZZ00000000001", "myvw-wcar-prod")
    assert "fuel/status" in fuel
    assert fuel.replace("fuel/status", "maintenance/status") == maint


def test_the_read_is_wired_with_its_own_wall_guard():
    """A wall on this read must not cost the two reads that already succeeded."""
    import inspect

    from custom_components.vag_connect.cariad.auth import _website_authproxy as wap

    src = inspect.getsource(wap)
    assert 'record_as="vwde_fuel"' in src
    assert src.count('_core_read = "fuel"') == 1
    # every core read records its own wall and continues; the fuel read must be
    # one of them rather than riding another read's guard. (The file has more
    # _core_read stages than the three vehicle reads — relations and
    # relations-detail use the same bookkeeping.)
    stages = re.findall(r'_core_read = "([a-z-]+)"', src)
    assert "fuel" in stages
    assert src.count('self.probe_outcomes[f"vwde_core_read:{_core_read}"]') >= len(
        {"charging", "maintenance", "fuel"} & set(stages)
    )
