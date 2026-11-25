# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#2072 — a carried headline range on a car without a high-voltage battery
follows the range this poll delivered.

On 5.6.1 the reporter's Tayron showed a main range of 760 km while the app and
the fuel range from volkswagen.de both read 720 km. The portal had delivered its
three cruising-range fields without a value, so the 760 was the last headline it
had sent, kept by the carry-forward step. volkswagen.de carries no headline for
a combustion car, only the fuel range, so nothing in that poll replaced it.

Rule, at the end of reconcile(), next to the 0-km rule from #2228: when this
poll delivered no headline, the stored one is being carried, and neither this
poll nor the stored snapshot shows any sign of a high-voltage battery, the first
of the total range and the combustion range that THIS poll delivered above 0
replaces it, with the provenance of that field. The replaced value is a fresh
one, so the #1917 carried marker must not claim it even when the number happens
to be the same as before. Never produces 0, never uses a carried candidate,
never touches a headline this poll delivered.
"""
from __future__ import annotations

from dataclasses import asdict
from typing import Any

from custom_components.vag_connect.cariad._channel_merge import merge_channels
from custom_components.vag_connect.cariad.models import VehicleData
from custom_components.vag_connect.cariad.vehicle_cache import reconcile

VIN = "WVWZZZ00000000001"


def _car(**kw: object) -> VehicleData:
    return VehicleData(vin=VIN, **kw)  # type: ignore[arg-type]


def _poll(
    previous: dict[str, Any], *pairs: tuple[str, VehicleData],
) -> tuple[dict[str, Any], list[str]]:
    """One full poll: channel merge, then reconcile against the stored one."""
    return reconcile(previous, asdict(merge_channels(list(pairs))))


def _stored(**kw: object) -> dict[str, Any]:
    base: dict[str, Any] = {
        "vin": VIN, "range_km": 760, "total_range_km": 760, "fuel_level": 100,
        "has_battery": False, "has_combustion": True,
        "field_sources": {"range_km": "eu_data_act", "total_range_km": "eu_data_act"},
    }
    base.update(kw)
    return base


# --- the reporter's constellation -------------------------------------------

def test_mogsug_561_carried_760_follows_the_vwde_fuel_range() -> None:
    """Portal: no ranges this poll. volkswagen.de: fuel 94 %, fuel range 720."""
    web = _car(fuel_level=94, combustion_range_km=720)
    eu = _car(odometer_km=24812)
    out, notes = _poll(_stored(), ("website_authproxy", web), ("eu_data_act", eu))
    assert out["range_km"] == 720
    assert out["field_sources"]["range_km"] == "website_authproxy"
    assert any("#2072" in n and "range_km" in n for n in notes)


def test_derived_value_is_not_marked_carried() -> None:
    out, _ = _poll(_stored(), ("website_authproxy", _car(combustion_range_km=720)))
    assert out["range_km"] == 720
    assert "range_km" not in (out.get("field_carried_since") or {})


def test_derived_value_equal_to_the_stored_one_is_not_marked_carried() -> None:
    """Same number as before, but THIS poll delivered it: not 'carried'."""
    stored = _stored(range_km=720)
    out, _ = _poll(stored, ("website_authproxy", _car(combustion_range_km=720)))
    assert out["range_km"] == 720
    assert "range_km" not in (out.get("field_carried_since") or {})
    assert out["field_sources"]["range_km"] == "website_authproxy"


def test_total_from_this_poll_comes_first() -> None:
    eu = _car(total_range_km=740, combustion_range_km=720)
    out, _ = _poll(_stored(), ("eu_data_act", eu))
    assert out["range_km"] == 740


# --- what must stay as it was -------------------------------------------------

def test_headline_delivered_by_this_poll_is_not_touched() -> None:
    eu = _car(range_km=800, combustion_range_km=720)
    out, _ = _poll(_stored(), ("eu_data_act", eu))
    assert out["range_km"] == 800


def test_carried_headline_without_a_fresh_candidate_stays_carried() -> None:
    out, _ = _poll(_stored(), ("website_authproxy", _car(fuel_level=94)))
    assert out["range_km"] == 760
    assert "range_km" in (out.get("field_carried_since") or {})


def test_fresh_zero_candidate_is_never_taken() -> None:
    out, _ = _poll(_stored(), ("website_authproxy", _car(combustion_range_km=0)))
    assert out["range_km"] == 760


def test_battery_evidence_in_the_stored_snapshot_blocks_it() -> None:
    stored = _stored(has_battery=True, is_hybrid=True)
    out, _ = _poll(stored, ("website_authproxy", _car(combustion_range_km=600)))
    assert out["range_km"] == 760


def test_battery_value_in_this_poll_blocks_it() -> None:
    web = _car(combustion_range_km=600, battery_soc=55, electric_range_km=40)
    out, _ = _poll(_stored(has_battery=None), ("website_authproxy", web))
    assert out["range_km"] == 760


def test_never_delivered_headline_stays_missing() -> None:
    stored = _stored(range_km=None)
    out, _ = _poll(stored, ("website_authproxy", _car(combustion_range_km=600)))
    assert out["range_km"] is None
