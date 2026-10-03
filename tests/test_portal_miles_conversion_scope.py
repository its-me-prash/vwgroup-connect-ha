# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The portal's miles→km conversion is a property of the SOURCE LEAF.

A UK/US car's portal payload carries a companion unit field saying the car
DISPLAYS miles, and the parser used to multiply ten km-typed attributes by
1.60934 whenever it saw that. The official V6.0 catalogue says that is too
broad, and it says so structurally:

* A unit COMPANION exists for exactly eight data points — ``mileage.unit``,
  ``distance.unit``, ``estimatedcruisingrangeprimary.unit``,
  ``estimatedcruisingrangesecondary.unit``,
  ``battery_state_report.cruising_ranges.[*].unit``,
  ``service_maintenances.[*].due_in_distance.unit``, its ``due_in_time`` twin
  and ``tires.[*].unit``. Those are the points whose unit varies per car, which
  is also why ``mileage`` itself is documented with NO unit at all (column
  ``'-``).
* Every other distance leaf declares a FIXED ``km`` in its own unit column, and
  several say it in the description too: ``cruising_range_primary_engine`` /
  ``_secondary_engine`` / ``_combined`` ("in kilometer"),
  ``maintenance_interval_distance_until_inspection`` / ``_until_oil_change``
  ("always in km" / "in each case in kilometers"),
  ``maintenance_interval_monthly_mileage``, ``short_term_data_mileage`` and the
  camel-case ``inspectionDistance`` ("(km)").

So on a miles car the service interval, the oil interval, the monthly average,
the last-trip distance and — on any car shipping the ``cruising_range_*``
dialect — the ranges were all 1.6x too high.

The instrument-cluster range block (DID 0x2AB6) escaped only by POSITION: it is
decoded further down the function than the post-process runs, so it was never
scaled. Its tests below therefore pass with and without this change; they are
here because that block is read only when its own envelope states kilometres,
so the invariant is real even though the bug was not, and because recording its
source makes the escape explicit instead of accidental.

Each of those attributes can be filled from EITHER kind of leaf, so the
decision cannot be made from the attribute name — these tests pin it per source
leaf, including the two directions that must NOT change: the odometer family
(unit-variable) and the undocumented legacy spellings (unknown, so still
scaled, exactly as the conversion was originally grounded).
"""
from __future__ import annotations

import base64
import json

from custom_components.vag_connect.cariad.auth._eu_data_act import (
    _walk_fields,
    map_dataset_to_vehicle_data,
)
from custom_components.vag_connect.cariad.models import VehicleData

MI = 1.60934


def _map(fields: dict, *, miles: bool = True) -> VehicleData:
    """Map a payload, declaring the car's display unit as miles by default."""
    payload = dict(fields)
    if miles:
        payload["distance_unit"] = "miles"
    syn: dict = {}
    flat = _walk_fields(payload, None, syn)
    return map_dataset_to_vehicle_data(flat, VehicleData(vin="X"), field_syn=syn)


# ── unchanged: the leaves whose unit really does vary per car ───────────────

def test_the_odometer_is_still_converted() -> None:
    """``mileage`` is documented with no unit of its own and ships
    ``mileage.unit`` — it follows the display unit, so it must still scale."""
    assert _map({"mileage": "26500"}).odometer_km == round(26500 * MI)


def test_the_numeric_unit_enum_still_triggers() -> None:
    d = _map({"mileage": "26500", "mileage.unit": "1"}, miles=False)
    assert d.odometer_km == round(26500 * MI)


def test_a_kilometre_car_is_never_touched() -> None:
    for unit in (None, "0", "km", "KILOMETRES"):
        fields = {"mileage": "26500",
                  "maintenance_interval_distance_until_inspection": "15000"}
        if unit is not None:
            fields["mileage.unit"] = unit
        d = _map(fields, miles=False)
        assert d.odometer_km == 26500, unit
        assert d.service_km == 15000, unit


def test_the_official_range_points_with_their_own_unit_still_convert() -> None:
    """``estimatedcruisingrangeprimary`` HAS a unit companion, so it follows the
    display unit like the odometer does."""
    d = _map({"estimatedcruisingrangeprimary.value": "180"})
    assert d.range_km == round(180 * MI)


def test_the_undocumented_legacy_spellings_still_convert() -> None:
    """``range`` / ``primaryEngineRange`` are not in the catalogue at all. The
    conversion was originally grounded on exactly these legacy payloads, so an
    unknown source keeps scaling — this change narrows the rule, it does not
    reverse it."""
    assert _map({"range": "180"}).range_km == round(180 * MI)
    assert _map({"primaryEngineRange": "180"}).range_km == round(180 * MI)


# ── fixed: the leaves the catalogue documents in kilometres ─────────────────

def test_the_documented_service_interval_is_not_converted() -> None:
    d = _map({"maintenance_interval_distance_until_inspection": "15000"})
    assert d.service_km == 15000


def test_the_flat_dialect_service_interval_is_not_converted() -> None:
    """``inspectionDistance`` IS in the catalogue, documented "(km)"."""
    assert _map({"inspectionDistance": "15000"}).service_km == 15000


def test_the_documented_oil_interval_is_not_converted() -> None:
    d = _map({"maintenance_interval_distance_until_oil_change": "9000"})
    assert d.oil_service_km == 9000


def test_the_monthly_average_is_not_converted() -> None:
    assert _map({"maintenance_interval_monthly_mileage": "1200"}).monthly_mileage_km == 1200


def test_the_last_trip_distance_is_not_converted() -> None:
    assert _map({"short_term_data_mileage": "120"}).last_trip_distance_km == 120


def test_the_cruising_range_dialect_is_not_converted() -> None:
    """All three ``cruising_range_*`` leaves document "in kilometer"."""
    d = _map({"cruising_range_primary_engine": "180",
              "cruising_range_secondary_engine": "40",
              "cruising_range_combined": "220"})
    assert d.range_km == 180
    assert d.electric_range_km == 180
    assert d.secondary_engine_range_km == 40
    assert d.total_range_km == 220


def test_a_phev_keeps_both_documented_ranges_unscaled() -> None:
    """The #555/#565 orientation path assigns the same two locals to different
    attributes depending on the drivetrain, so the source has to travel with
    the value rather than with the attribute name."""
    d = _map({
        "engine_type": "ENGINE_TYPE_PETROL_GASOLINE",
        "cruising_range_primary_engine": "520",
        "cruising_range_secondary_engine": "48",
        "fuel_level": "76",
    })
    assert d.combustion_range_km == 520
    assert d.electric_range_km == 48


def test_a_mixed_payload_scales_only_the_variable_half() -> None:
    """One car, one display unit, two kinds of leaf: the proof that this cannot
    be decided per attribute."""
    d = _map({
        "mileage": "26500",                                   # variable -> scaled
        "maintenance_interval_distance_until_inspection": "15000",   # km -> kept
        "short_term_data_mileage": "120",                     # km -> kept
        "cruising_range_combined": "220",                     # km -> kept
        "range": "180",                                       # unknown -> scaled
    })
    assert d.odometer_km == round(26500 * MI)
    assert d.range_km == round(180 * MI)
    assert d.service_km == 15000
    assert d.last_trip_distance_km == 120
    assert d.total_range_km == 220


def test_the_documented_leaf_wins_when_a_car_ships_both_spellings() -> None:
    """``cruising_range_combined`` is tried before ``totalRange_km``, so the
    recorded source — and therefore the no-scale decision — must follow the
    leaf that actually matched."""
    d = _map({"cruising_range_combined": "220", "totalRange_km": "999"})
    assert d.total_range_km == 220


def test_the_undocumented_total_range_spelling_still_converts() -> None:
    assert _map({"totalRange_km": "220"}).total_range_km == round(220 * MI)


# ── the instrument-cluster block: kilometres by construction ────────────────

def _uds_range_envelope(unit: str = "kilometre") -> str:
    doc = {
        "schema": "diagDataResults_Response_Schema_V1.3.json",
        "OperationStatus": "Completed",
        "DiagnosticData": [{
            "DiagnosticAddress": "1010",
            "LogicalLink": "LL_GatewUDS",
            "DiagNodeStatus": "Success",
            "Timestamp": "2026-10-01T08:02:31.126Z",
            "DataObjects": [{
                "Semantic": "IDENTIFICATION",
                "Result": "Success",
                "Values": [
                    {"ParamShortName": "Param_MatchRecorDataIdent",
                     "Value": "2AB6"},
                    {"ParamShortName": "Param_DataRecor", "Structure": [
                        {"ParamShortName": "Param_RangeSumDispl", "Value": "244"},
                        {"ParamShortName": "Param_RangePrimaDriveDispl",
                         "Value": "244"},
                        {"ParamShortName": "Param_RangeSoncoDriveDispl",
                         "Value": "40"},
                        {"ParamShortName": "Param_RangeUnitDispl", "Value": unit},
                    ]},
                ],
            }],
        }],
    }
    return base64.b64encode(json.dumps(doc).encode()).decode()


UDS_RANGE_KEY = (
    "LL_GatewUDS_ReadDataByIdentMeasuValue_Calculated_value_range_display_0x2AB6"
)


def test_the_cluster_range_block_is_never_converted() -> None:
    """That block is only read when its OWN envelope says kilometres, so the
    display-unit companion must not touch it. True before this change as well,
    but only because the block is decoded below where the post-process runs —
    recording its source is what makes it stay true if that ever moves."""
    d = _map({UDS_RANGE_KEY: _uds_range_envelope()})
    assert d.total_range_km == 244
    assert d.secondary_engine_range_km == 40


def test_the_cluster_block_in_miles_is_still_ignored_entirely() -> None:
    """Unchanged behaviour: a non-kilometre envelope is not trusted at all,
    rather than being converted on our side."""
    d = _map({UDS_RANGE_KEY: _uds_range_envelope(unit="miles")})
    assert d.total_range_km is None
    assert d.secondary_engine_range_km is None


# ── the mechanism itself ───────────────────────────────────────────────────

def test_every_converted_attribute_has_a_recorded_source() -> None:
    """If an attribute in the conversion list can be filled without recording
    its source, it silently falls back to "scale it" — which is the old bug for
    that leaf. This pins that the ten attributes all record.
    """
    import inspect

    from custom_components.vag_connect.cariad.auth import _eu_data_act as m

    src = inspect.getsource(m.map_dataset_to_vehicle_data)
    for attr in ("odometer_km", "range_km", "electric_range_km",
                 "combustion_range_km", "secondary_engine_range_km",
                 "total_range_km", "service_km", "oil_service_km",
                 "monthly_mileage_km", "last_trip_distance_km"):
        assert f'dist_src["{attr}"]' in src, attr


def test_the_fixed_km_set_matches_the_catalogue_claim() -> None:
    from custom_components.vag_connect.cariad.auth._eu_data_act import (
        _FIXED_KM_LEAVES,
    )

    for leaf in (
        "cruising_range_primary_engine", "cruising_range_secondary_engine",
        "cruising_range_combined", "inspectionDistance", "inspection_distance",
        "maintenance_interval_distance_until_inspection",
        "maintenance_interval_distance_until_oil_change",
        "maintenance_interval_monthly_mileage", "short_term_data_mileage",
    ):
        assert leaf in _FIXED_KM_LEAVES, leaf
    # ...and the unit-variable ones must NOT be in it, or the conversion stops
    # working for the cars it was built for.
    for leaf in ("mileage", "mileage.value", "odometer", "range",
                 "primaryEngineRange", "totalRange_km",
                 "estimatedcruisingrangeprimary.value"):
        assert leaf not in _FIXED_KM_LEAVES, leaf
