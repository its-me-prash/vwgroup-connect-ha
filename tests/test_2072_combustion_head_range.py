# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#2072 — a car without a high-voltage battery gets its headline range from
the total or combustion range when the final headline is 0 while the tank is
not empty (no false low-fuel alarm). The rule runs at the end of reconcile(),
where carried values and the evidence of earlier polls are known; the channel
merge sees one poll only and never derives it. PHEVs, EVs, a missing headline
and a real 0 with an empty or unknown tank are left alone."""
from __future__ import annotations

from dataclasses import asdict
from typing import Any

from custom_components.vag_connect.cariad._channel_merge import merge_channels
from custom_components.vag_connect.cariad.models import VehicleData
from custom_components.vag_connect.cariad.vehicle_cache import reconcile

VIN = "WVWZZZ00000000001"


def _eu(**kw: object) -> VehicleData:
    return VehicleData(vin=VIN, **kw)  # type: ignore[arg-type]


def _merge(*pairs: tuple[str, VehicleData]) -> VehicleData:
    return merge_channels(list(pairs))


def _poll(
    previous: dict[str, Any] | None, *pairs: tuple[str, VehicleData],
) -> dict[str, Any]:
    """One full poll: channel merge, then reconcile against the stored one."""
    merged, _notes = reconcile(previous, asdict(_merge(*pairs)))
    return merged


# --- the channel merge no longer derives anything ---------------------------

def test_merge_leaves_a_delivered_zero_alone() -> None:
    eu = _eu(range_km=0, combustion_range_km=760, total_range_km=780)
    web = _eu(fuel_level=100)
    m = _merge(("website_authproxy", web), ("eu_data_act", eu))
    assert m.range_km == 0
    assert m.has_battery is False


def test_merge_leaves_a_missing_headline_missing() -> None:
    m = _merge(("eu_data_act", _eu(combustion_range_km=760, fuel_level=80)))
    assert m.range_km is None


# --- reconcile derives it ----------------------------------------------------

def test_mogsug_constellation_gives_total() -> None:
    """Range 0, combustion 760, total 780, fuel 100, no battery anywhere."""
    eu = _eu(range_km=0, combustion_range_km=760, total_range_km=780)
    web = _eu(fuel_level=100)
    previous = {"vin": VIN, "range_km": 0, "fuel_level": 100}
    out = _poll(previous, ("website_authproxy", web), ("eu_data_act", eu))
    assert out["range_km"] == 780
    assert out["combustion_range_km"] == 760
    assert out["total_range_km"] == 780
    assert out["has_battery"] is False


def test_stored_zero_with_poll_without_headline_is_corrected() -> None:
    """The stored 0 is carried (poll has no headline) and then corrected."""
    previous = {"vin": VIN, "range_km": 0, "fuel_level": 80,
                "combustion_range_km": 760, "has_battery": False}
    eu = _eu(fuel_level=80, combustion_range_km=760)
    out = _poll(previous, ("eu_data_act", eu))
    assert out["range_km"] == 760


def test_missing_headline_takes_this_polls_range_instead_of_carrying() -> None:
    """Until 25 November this pinned the carried 700. On 5.6.1 that is what kept
    a Tayron at a stale 760 km next to the app's 720 km, so a carried headline on
    a car without battery evidence now follows the range this poll delivered
    (tests/test_2072_carried_headline_fuel_range.py has the cases)."""
    previous = {"vin": VIN, "range_km": 700, "fuel_level": 80,
                "combustion_range_km": 760}
    out = _poll(previous, ("eu_data_act", _eu(fuel_level=80,
                                              combustion_range_km=760)))
    assert out["range_km"] == 760


def test_nothing_stored_and_no_headline_stays_missing() -> None:
    previous = {"vin": VIN, "fuel_level": 80}
    out = _poll(previous, ("eu_data_act", _eu(fuel_level=80,
                                              combustion_range_km=600)))
    assert out["range_km"] is None


def test_zero_candidates_are_never_taken() -> None:
    previous = {"vin": VIN, "range_km": 0}
    eu = _eu(range_km=0, total_range_km=0, combustion_range_km=500,
             fuel_level=80)
    assert _poll(previous, ("eu_data_act", eu))["range_km"] == 500
    eu2 = _eu(range_km=0, total_range_km=0, combustion_range_km=0,
              fuel_level=80)
    assert _poll(previous, ("eu_data_act", eu2))["range_km"] == 0


def test_real_zero_with_empty_tank_is_kept() -> None:
    previous = {"vin": VIN, "range_km": 0}
    eu = _eu(range_km=0, combustion_range_km=0, total_range_km=30, fuel_level=0)
    assert _poll(previous, ("eu_data_act", eu))["range_km"] == 0


def test_zero_with_unknown_fuel_is_kept() -> None:
    previous = {"vin": VIN, "range_km": 0}
    eu = _eu(range_km=0, combustion_range_km=760, total_range_km=780)
    assert _poll(previous, ("eu_data_act", eu))["range_km"] == 0


def test_nonzero_headline_is_not_touched() -> None:
    previous = {"vin": VIN, "range_km": 650}
    eu = _eu(range_km=700, combustion_range_km=760, total_range_km=780,
             fuel_level=90)
    assert _poll(previous, ("eu_data_act", eu))["range_km"] == 700


def test_phev_partial_poll_with_battery_evidence_in_previous_is_untouched() -> None:
    """This poll: range 0, fuel, combustion, no battery field. The earlier
    poll knew the battery, so the headline must stay 0."""
    previous = {"vin": VIN, "range_km": 0, "has_battery": True,
                "is_hybrid": True, "has_combustion": True,
                "battery_soc": None, "electric_range_km": None}
    eu = _eu(range_km=0, fuel_level=70, combustion_range_km=600)
    out = _poll(previous, ("eu_data_act", eu))
    assert out["range_km"] == 0


def test_phev_untouched_when_battery_value_is_carried() -> None:
    previous = {"vin": VIN, "range_km": 0, "battery_soc": 50,
                "electric_range_km": 40}
    eu = _eu(range_km=0, fuel_level=70, combustion_range_km=600)
    out = _poll(previous, ("eu_data_act", eu))
    assert out["range_km"] == 0
    assert out["has_battery"] is True


def test_phev_untouched_in_one_poll() -> None:
    eu = _eu(range_km=0, combustion_range_km=600, total_range_km=640,
             electric_range_km=40, battery_soc=50, fuel_level=70)
    previous = {"vin": VIN, "range_km": 0}
    assert _poll(previous, ("eu_data_act", eu))["range_km"] == 0


def test_ev_is_untouched() -> None:
    previous = {"vin": VIN, "range_km": 0}
    eu = _eu(range_km=None, electric_range_km=300, battery_soc=80)
    assert _poll(previous, ("eu_data_act", eu))["range_km"] == 0


def test_provenance_follows_the_source_field() -> None:
    eu = _eu(range_km=0, combustion_range_km=760, total_range_km=780,
             field_captured_ts={"range_km": "2026-11-10T07:07:13+00:00",
                                "total_range_km": "2026-11-11T08:00:00+00:00"},
             field_source_leaf={"range_km": "old.leaf",
                                "total_range_km": "total.leaf"})
    web = _eu(fuel_level=100)
    previous = {"vin": VIN, "range_km": 0}
    out = _poll(previous, ("website_authproxy", web), ("eu_data_act", eu))
    assert out["range_km"] == 780
    assert out["field_sources"]["range_km"] == "eu_data_act"
    assert "eu_data_act" in out["source_channel"].split("+")
    # the stamp and leaf of the replaced 0 are gone; the source field's are copied
    assert out["field_captured_ts"]["range_km"] == "2026-11-11T08:00:00+00:00"
    assert out["field_source_leaf"]["range_km"] == "total.leaf"


def test_provenance_of_the_zero_is_dropped_when_source_has_none() -> None:
    eu = _eu(range_km=0, combustion_range_km=760,
             field_captured_ts={"range_km": "2026-11-10T07:07:13+00:00"},
             field_source_leaf={"range_km": "old.leaf"})
    out = _poll({"vin": VIN, "range_km": 0}, ("eu_data_act", eu),
                ("website_authproxy", _eu(fuel_level=100)))
    assert out["range_km"] == 760
    assert "range_km" not in out["field_captured_ts"]
    assert "range_km" not in out["field_source_leaf"]


# --- gate on what THIS poll delivered ---------------------------------------

def test_poll_without_fuel_or_ranges_keeps_a_delivered_zero() -> None:
    """A delivered 0 with nothing else from this poll: every candidate and the
    fuel level are carried, so nothing is derived from them."""
    previous = {"vin": VIN, "range_km": 500, "fuel_level": 80,
                "combustion_range_km": 400, "has_battery": False}
    out, _ = reconcile(previous, {"vin": VIN, "range_km": 0})
    assert out["range_km"] == 0


def test_carried_candidates_and_fuel_are_not_enough() -> None:
    previous = {"vin": VIN, "range_km": 0, "fuel_level": 70,
                "total_range_km": 600, "combustion_range_km": 600}
    out, _ = reconcile(previous, {"vin": VIN, "range_km": 0, "fuel_level": 70})
    assert out["range_km"] == 0


def test_only_a_candidate_delivered_by_this_poll_is_used() -> None:
    previous = {"vin": VIN, "range_km": 0, "fuel_level": 70,
                "total_range_km": 900}
    out, _ = reconcile(previous, {"vin": VIN, "range_km": 0, "fuel_level": 70,
                                  "combustion_range_km": 500})
    assert out["range_km"] == 500


def test_replacement_drops_ambiguity_and_takes_inherited_stamp() -> None:
    fresh = {"vin": VIN, "range_km": 0, "fuel_level": 70,
             "combustion_range_km": 500,
             "ambiguous_fields": {"range_km": ["a", "b"], "other": ["c"]},
             "field_captured_inherited": {"range_km": True,
                                          "combustion_range_km": False}}
    out, _ = reconcile({"vin": VIN, "range_km": 0}, fresh)
    assert out["range_km"] == 500
    assert "range_km" not in out["ambiguous_fields"]
    assert out["ambiguous_fields"]["other"] == ["c"]
    assert out["field_captured_inherited"]["range_km"] is False


def test_replacement_removes_inherited_key_when_source_has_none() -> None:
    fresh = {"vin": VIN, "range_km": 0, "fuel_level": 70,
             "combustion_range_km": 500,
             "field_captured_inherited": {"range_km": True}}
    out, _ = reconcile({"vin": VIN, "range_km": 0}, fresh)
    assert out["range_km"] == 500
    assert "range_km" not in out["field_captured_inherited"]
