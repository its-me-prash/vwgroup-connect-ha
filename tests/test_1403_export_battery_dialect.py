# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#1403 (@placidcasual98, Audi A6 e-tron Avant, PPE, UK) — his one-time export
carried a charge level of 31 % and an electric range of 148 km, he ran the
import, it reported success, and his car still had no battery entity at all.

The cause was not the portal and not a missing reload. The import shares ONE
mapper with the 15-minute feed, and every charge-level alias in that mapper is a
FEED spelling: of the 17 names in the SoC chain exactly one ("soc") is
catalogued under ``Historical Export``, and of the electric-range names, none.
So his file was fetched, downloaded and parsed with a non-empty field set, and
then every battery attribute came out None with the whole lot sitting in
``raw_unmapped_fields``. The drivetrain flag that gates the ~98 electric entity
descriptions is derived from those attributes, so no battery entity was ever
built. That is the same bug class as the #702 Touareg dialect and the #1780 body
dialect: we never asked for the export's spelling.

Three refusals are pinned here as hard as the mapping itself, because each of
them would publish a lie rather than a gap:

* ``LvsocValue`` is the LOW voltage starter battery, one letter from the HV
  names. It must never reach ``battery_soc``.
* ``ChargingEvent.[N].*`` values are per-session history. The index is not a
  time order, this reporter has eleven sessions, and a session's charge level is
  not the car's current one. ``battery_soc`` is a MEASUREMENT sensor feeding
  long-term statistics, so a session value would be recorded as a real reading.
* Both export range names declare kilometres, so the miles post-process must
  leave them alone. Without that a UK car's 148 km publishes as 238.

The new names go in their own ``if ... is None`` + ``first()`` step rather than
onto the existing chain, because position in ``first_freshest`` is only a
tie-break: its sort key is the capture timestamp and a candidate carrying one
always beats a candidate without. "Kept last" would not have held them back.
"""
from __future__ import annotations

import pytest

from custom_components.vag_connect.cariad.auth._eu_data_act import (
    _walk_fields,
    map_dataset_to_vehicle_data,
)
from custom_components.vag_connect.cariad.models import VehicleData

#: @placidcasual98's export, as he reported it in #1403: the two charge-level
#: names at 31, the two range names at 148, the platform, the charging error
#: state his last reading carried, and the connected plug.
REPORTER_EXPORT: dict[str, str] = {
    "carCapturedTimestamp": "2026-10-08T13:36:26.340Z",
    "batteryStatus.currentSOC_pct": "31",
    "ChargingEvent.[0].BatteryStatus.[0].currentSocPct": "31",
    "ChargingEvent.[0].BatteryStatus.[0].cruisingRangeElectricKm": "148",
    "batteryStatus.cruisingRange.range": "148",
    "vehiclePlatform": "PPE",
    "chargingStatus.currentChargeState": "error",
    "plugConnectionState": "PLUG_CONNECTION_STATE_CONNECTED",
}


def _map(fields: dict) -> VehicleData:
    """Map through the real portal envelope and the production call shape.

    The portal sends a ``Data`` list of ``{dataFieldName, value}`` records whose
    names are the dotted catalogue paths, which is how the reporter quoted them.
    All four companion dicts are passed because both production entry points do;
    a harness that omits them disables the timestamp-aware resolution and so
    measures a different mapper than the one that ships.
    """
    payload = {
        "Data": [
            {"dataFieldName": name, "value": value}
            for name, value in fields.items()
        ]
    }
    ts: dict = {}
    syn: dict = {}
    contested: dict = {}
    uuids: dict = {}
    walked = _walk_fields(payload, ts, syn, contested, uuids)
    return map_dataset_to_vehicle_data(
        walked, VehicleData(vin="TESTVIN0000000001"), ts, syn, contested, uuids
    )


def test_the_reporters_export_produces_a_battery() -> None:
    """The headline case. FAILS BEFORE THE FIX: measured every one of these as
    None / False on this exact field set."""
    d = _map(REPORTER_EXPORT)
    assert d.battery_soc == 31
    assert d.electric_range_km == 148
    # These two are what actually gate the electric entity descriptions, so the
    # readings alone would not have been enough.
    assert d.has_battery is True
    assert d.is_electric is True


@pytest.mark.parametrize("name,raw,expected", [
    ("batteryStatus.currentSOC_pct", "31", 31),
    ("currentSOCInPct", "44", 44),
    ("Stateofcharge", "77", 77),
])
def test_each_export_charge_level_spelling(name: str, raw: str, expected: int) -> None:
    """All three are catalogued as the HV traction SoC in percent."""
    d = _map({name: raw})
    assert d.battery_soc == expected
    assert d.has_battery is True


@pytest.mark.parametrize("name,raw,expected", [
    ("cruisingRangeElectricInKm", "148", 148),
    ("batteryStatus.cruisingRange.range", "148", 148),
])
def test_each_export_electric_range_spelling(name: str, raw: str, expected: int) -> None:
    d = _map({name: raw})
    assert d.electric_range_km == expected


def test_the_12v_battery_is_never_the_traction_pack() -> None:
    """``LvsocValue`` is "Last reported low voltage battery percentage".

    It sits one letter from the HV family in the same catalogue cluster, so the
    only thing stopping it from being read as the charge level is that it is
    deliberately absent from the lookup.
    """
    d = _map({"LvsocValue": "51"})
    assert d.battery_soc is None
    assert d.has_battery is False


@pytest.mark.parametrize("name", [
    "ChargingEvent.[0].BatteryStatus.[0].currentSocPct",
    "ChargingEvent.[0].BatteryStatus.[0].cruisingRangeElectricKm",
])
def test_a_charging_session_is_not_the_current_state(name: str) -> None:
    """Per-session history must not become a live reading.

    The reporter has eleven sessions, the bracket index is not a time order, and
    the family carries no capture timestamp to settle which is newest. Publishing
    one would put a historical charge level into long-term statistics as a real
    measurement.
    """
    d = _map({name: "77"})
    assert d.battery_soc is None
    assert d.electric_range_km is None
    assert d.has_battery is False


def test_the_export_only_fills_gaps_and_never_overrides_the_feed() -> None:
    """A live reading always wins, whichever spelling the export used.

    The import is gap-fill by design, and this is the property that makes adding
    export names safe at all.
    """
    d = _map({
        "soc": "62",
        "range": "300",
        "batteryStatus.currentSOC_pct": "99",
        "cruisingRangeElectricInKm": "111",
    })
    assert d.battery_soc == 62
    assert d.electric_range_km == 300


@pytest.mark.parametrize("name", [
    "cruisingRangeElectricInKm",
    "batteryStatus.cruisingRange.range",
])
def test_a_kilometre_range_is_not_scaled_for_a_miles_car(name: str) -> None:
    """Both names declare kilometres in the catalogue.

    The mapper scales distances to km when the car's display unit is miles, and
    a new mapping is opted into that by default. For a field that is already
    kilometres this reporter's 148 would have been published as 238, on exactly
    the UK car the mapping exists to fix.
    """
    d = _map({name: "148", "mileage.unit": "mi"})
    assert d.electric_range_km == 148


def test_an_implausible_export_charge_level_is_dropped_too() -> None:
    """The export names get the same 0..100 screen as the feed chain."""
    d = _map({"batteryStatus.currentSOC_pct": "255"})
    assert d.battery_soc is None
    assert d.has_battery is False


def test_a_combustion_engine_type_blocks_the_export_range() -> None:
    """When the dataset names a combustion engine, its range is not electric.

    The per-engine container is read as the self-describing pair it is: an engine
    type and that engine's range.
    """
    d = _map({
        "batteryStatus.cruisingRange.range": "620",
        "batteryStatus.cruisingRange.engineType": "ENGINE_TYPE_PETROL_GASOLINE",
    })
    assert d.electric_range_km is None
    assert d.combustion_range_km == 620
    assert d.has_battery is False


def test_the_combustion_primary_phevs_still_do_not_move() -> None:
    """#555/#565 regression guard, repeated here because this change also
    touches the range path: the GTE-class swap fix must stay as it is."""
    d = _map({
        "cruising_range_primary_engine": "380",
        "cruising_range_secondary_engine": "20",
        "fuel_level": "55",
        "batteryStatus.cruisingRange.range": "999",
    })
    assert d.combustion_range_km == 380
    assert d.electric_range_km == 20
    assert d.is_hybrid is True
