# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""v2.17.4 — EU-Data-Act read-path fixes verified against a competitor-source
diff of the EU-Data-Act forks (all cross-checked to a real portal signature
before shipping):

- #1 UUID-keyed field mapping: MEB/ID.x ships the primary electric range under a
  GENERIC dataFieldName "value" disambiguated ONLY by its per-point ``key`` UUID
  (0ca40e18…). The name-keyed flattener collapsed all "value" points onto one
  field, losing range on ID.3/4/5/7. The flattener now also keys generic-named
  points by their UUID; the mapper resolves the primary range from 0ca40e18.
- #3 INT32_MIN (-2147483648) sentinel: a signed "no reading" the service
  countdown ships; must drop BEFORE the sign transform or it negates into a
  +2.1-billion-km leak.
- #4 400/429 soft-transient: a datadelivery 400/429 is a provisioning-window /
  throttle transient, not an auth failure — must not trigger a re-login loop.
"""
from __future__ import annotations

from custom_components.vag_connect.cariad.auth._eu_data_act import (
    _GLOBAL_SENTINELS,
    _RETRIABLE_STATUSES,
    _TRANSIENT_STATUSES,
    _is_sentinel,
    _walk_fields,
    map_dataset_to_vehicle_data,
)
from custom_components.vag_connect.cariad.models import VehicleData

_RANGE_UUID = "0ca40e18-0564-3eda-bcc0-7aee9ef44f04"  # "Value of the primary range"


# ── #1 UUID-keyed range ──────────────────────────────────────────────────────

def test_uuid_keyed_generic_point_flattens_under_its_uuid() -> None:
    payload = {
        "data": [
            {"dataFieldName": "battery_state_report.soc", "value": "77"},
            {"dataFieldName": "value", "key": _RANGE_UUID, "value": "320"},
        ]
    }
    fields = _walk_fields(payload)
    # the UUID becomes its own key (lowercased) — no collapse onto bare "value"
    assert fields[_RANGE_UUID] == "320"


def test_uuid_primary_range_maps_to_electric_on_bev() -> None:
    payload = {
        "data": [
            {"dataFieldName": "battery_state_report.soc", "value": "77"},
            {"dataFieldName": "value", "key": _RANGE_UUID, "value": "320"},
        ]
    }
    d = map_dataset_to_vehicle_data(_walk_fields(payload), VehicleData(vin="X"))
    assert d.electric_range_km == 320  # BEV: primary range is electric
    assert d.range_km == 320


def test_uuid_primary_range_routes_to_combustion_on_phev() -> None:
    # combustion-primary PHEV (fuel + a secondary range, no engine_type token):
    # the primary-range UUID must land on COMBUSTION, secondary on electric.
    payload = {
        "data": [
            {"dataFieldName": "value", "key": _RANGE_UUID, "value": "540"},
            {"dataFieldName": "cruising_range_secondary_engine", "value": "42"},
            {"dataFieldName": "fuel_level", "value": "60"},
        ]
    }
    d = map_dataset_to_vehicle_data(_walk_fields(payload), VehicleData(vin="X"))
    assert d.combustion_range_km == 540
    assert d.electric_range_km == 42


def test_generic_point_without_uuid_key_unchanged() -> None:
    # no ``key`` → behaves exactly as before (no UUID alias, bare name kept)
    fields = _walk_fields({"data": [{"dataFieldName": "value", "value": "99"}]})
    assert fields.get("value") == "99"
    assert not any(k.count("-") == 4 and len(k) == 36 for k in fields)


def test_well_named_field_with_uuid_key_gets_no_alias() -> None:
    # a non-generic name that happens to carry a key UUID must NOT be UUID-aliased
    fields = _walk_fields(
        {"data": [{"dataFieldName": "battery_state_report.soc",
                   "key": _RANGE_UUID, "value": "80"}]}
    )
    assert fields["battery_state_report.soc"] == "80"
    assert _RANGE_UUID not in fields


def test_unmapped_generic_uuid_emits_no_alias_no_scout_flood() -> None:
    """v2.17.5 regression guard: the 2.17.4 blanket alias emitted an
    ``eu_data_act.<uuid>`` key for EVERY generic-named point, flooding the
    Vehicle Data Scout with dozens of unmapped timestamp/state UUID rows per car.
    Only UUIDs we actually MAP are aliased now; every other generic point keeps
    only its bare name (still Scout-visible) and emits NO UUID row."""
    fields = _walk_fields(
        {
            "data": [
                # unmapped generic "timestamp"/"state" points carrying real UUIDs
                {"dataFieldName": "timestamp", "key": "067f539c-85fe-3067-9c29-d63e177e3712", "value": "2026-07-15T10:42:52Z"},
                {"dataFieldName": "state", "key": "0718582b-7259-3c9a-818a-ea848a7365a8", "value": "VALID"},
                # the ONE mapped UUID still gets its alias
                {"dataFieldName": "value", "key": _RANGE_UUID, "value": "300"},
            ]
        }
    )
    # only the mapped range UUID surfaced — no unmapped-UUID flood
    uuid_keys = [k for k in fields if k.count("-") == 4 and len(k) == 36]
    assert uuid_keys == [_RANGE_UUID]
    # the bare generic names stay Scout-visible (no suppression)
    assert "state" in fields


# ── #3 INT32_MIN sentinel ────────────────────────────────────────────────────

def test_int32_min_is_a_global_sentinel() -> None:
    assert -2147483648.0 in _GLOBAL_SENTINELS
    assert _is_sentinel("service_km", -2147483648) is True
    assert _is_sentinel("oil_service_km", "-2147483648") is True


def test_real_negative_countdown_is_not_a_sentinel() -> None:
    # a genuine negative service countdown must survive (it is later negated)
    assert _is_sentinel("service_km", -15000) is False


def test_int32_min_service_field_dropped_not_leaked() -> None:
    # end-to-end: an INT32_MIN service value must NOT surface as a giant distance
    d = map_dataset_to_vehicle_data(
        {"service_km": "-2147483648", "oil_service_km": "-2147483648"},
        VehicleData(vin="X"),
    )
    assert d.service_km is None
    assert d.oil_service_km is None


# ── #4 400/429 soft-transient ────────────────────────────────────────────────

def test_400_and_429_are_soft_transient() -> None:
    assert 400 in _TRANSIENT_STATUSES
    assert 429 in _TRANSIENT_STATUSES


def test_400_429_not_aggressively_retried() -> None:
    # transient (return "no data this poll") but NOT retriable (no portal hammering)
    assert 400 not in _RETRIABLE_STATUSES
    assert 429 not in _RETRIABLE_STATUSES
    assert 500 in _RETRIABLE_STATUSES  # 5xx still backs off + retries


# ── v2.17.5 portal-coverage aliases (verified-real gaps from the full sweep) ──

def test_v2175_oil_low_level_warning_alias() -> None:
    # oil_level_min_warning (0=OK, 1=low) → existing oil_level_warning sensor
    assert map_dataset_to_vehicle_data(
        {"oil_level_min_warning": "1"}, VehicleData(vin="X")
    ).oil_level_warning is True
    assert map_dataset_to_vehicle_data(
        {"oil_level_min_warning": "0"}, VehicleData(vin="X")
    ).oil_level_warning is False


def test_v2175_sunroof_hood3_position_fallback() -> None:
    d = map_dataset_to_vehicle_data(
        {"position_sunroof_motor_hood_3": "40"}, VehicleData(vin="X")
    )
    assert d.sunroof_position_pct == 40


def test_v2175_rear_climate_zones_aliased() -> None:
    d = map_dataset_to_vehicle_data(
        {
            "setting_zone_enabled_rear_left": "true",
            "setting_zone_enabled_rear_right": "false",
        },
        VehicleData(vin="X"),
    )
    assert d.climate_zone_rear_left is True
    assert d.climate_zone_rear_right is False


def test_v2175_live_active_climate_and_mirror() -> None:
    d = map_dataset_to_vehicle_data(
        {
            "state_mirror_heating_active": "true",
            "state_zone_active_front_left": "true",
            "state_zone_active_front_right": "false",
            "state_zone_active_rear_left": "true",
            "state_zone_active_rear_right": "false",
        },
        VehicleData(vin="X"),
    )
    assert d.mirror_heating_active is True
    assert d.climate_zone_active_front_left is True
    assert d.climate_zone_active_front_right is False
    assert d.climate_zone_active_rear_left is True
    assert d.climate_zone_active_rear_right is False


def test_v2175_parkinglightstate_is_set() -> None:
    assert map_dataset_to_vehicle_data(
        {"parkinglightstate.is_set": "true"}, VehicleData(vin="X")
    ).parking_light is True


def test_v2175_trunk_locked_dotted_and_no_doors_collision() -> None:
    # trunk.locked → trunk_locked; and a QUALIFIED door field wins over the
    # trunk's bare 'locked' leaf (the cross-container collision fix).
    d = map_dataset_to_vehicle_data(
        {"trunk.locked": "true", "doorLockStatus": "unlocked", "locked": "true"},
        VehicleData(vin="X"),
    )
    assert d.trunk_locked is True
    assert d.doors_locked is False
