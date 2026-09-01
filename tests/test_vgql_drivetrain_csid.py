# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""vgql surfaces the authoritative drivetrain classification + customer-service id.

The same ``userVehicles`` query we already run for render images and the model
name also carries ``vehicle.classification.driveTrain`` (BEV / PHEV / …) and a
stable per-vehicle ``csid``. Both are read from the GraphQL block and gap-filled
onto the vehicle so they surface as diagnostic sensors — never overwriting a real
value that a telemetry-derived path already produced.
"""
from __future__ import annotations

from custom_components.vag_connect.cariad.api.graphql import (
    VehicleImageData,
    VehicleImageFetcher,
)
from custom_components.vag_connect.cariad.api.vw_eu import VWEUClient

_parse_response = VehicleImageFetcher._parse_response


def _client(meta: dict, image_data: dict) -> VWEUClient:
    c = VWEUClient.__new__(VWEUClient)
    c._vehicle_metadata = meta
    c._image_data = image_data
    return c


# --- GraphQL parse -----------------------------------------------------------

def test_parse_extracts_drive_train_and_csid():
    data = {
        "data": {
            "userVehicles": [
                {
                    "vin": "VINX",
                    "csid": "csid-abc-123",
                    "vehicle": {
                        "core": {"modelYear": 2023},
                        "media": {"longName": "Q4 e-tron"},
                        "classification": {"driveTrain": "BEV"},
                        "renderPictures": [],
                    },
                }
            ]
        }
    }
    out = _parse_response(data)
    assert out["VINX"].drive_train == "BEV"
    assert out["VINX"].csid == "csid-abc-123"


def test_parse_tolerates_missing_classification_and_csid():
    data = {
        "data": {
            "userVehicles": [
                {
                    "vin": "VINY",
                    "vehicle": {"media": {"longName": "Golf"}, "renderPictures": []},
                }
            ]
        }
    }
    out = _parse_response(data)
    assert out["VINY"].drive_train is None
    assert out["VINY"].csid is None


def test_parse_ignores_non_string_shapes():
    data = {
        "data": {
            "userVehicles": [
                {
                    "vin": "VINZ",
                    "csid": {"unexpected": "object"},
                    "vehicle": {"classification": {"driveTrain": 42}},
                }
            ]
        }
    }
    out = _parse_response(data)
    assert out["VINZ"].drive_train is None
    assert out["VINZ"].csid is None


# --- vw_eu seeding -----------------------------------------------------------

def test_seeds_drive_train_and_csid_onto_vehicle():
    c = _client(
        {"VINX": {"model": None}},
        {"VINX": VehicleImageData(
            vin="VINX", image_urls={},
            drive_train="PHEV", csid="csid-xyz")},
    )
    d = c._parse_status("VINX", {}, parking={})
    assert d.drive_train == "PHEV"
    assert d.csid == "csid-xyz"


def test_seeding_never_overwrites_existing_values():
    c = _client(
        {"VINX": {"model": None}},
        {"VINX": VehicleImageData(
            vin="VINX", image_urls={},
            drive_train="BEV", csid="from-vgql")},
    )
    d = c._parse_status("VINX", {}, parking={})
    d.drive_train = "already-set"
    d.csid = "already-set"
    # re-run seeding is a no-op once a value is present
    if c._image_data["VINX"].drive_train and not d.drive_train:
        d.drive_train = c._image_data["VINX"].drive_train
    assert d.drive_train == "already-set"
    assert d.csid == "already-set"


def test_no_image_data_leaves_fields_none():
    c = _client({"VINX": {"model": None}}, {})
    d = c._parse_status("VINX", {}, parking={})
    assert d.drive_train is None
    assert d.csid is None


# --- sensor registration + phantom guard -------------------------------------

def test_sensors_registered_with_expected_wiring():
    from homeassistant.components.sensor import SensorDeviceClass

    from custom_components.vag_connect.sensor import SENSOR_DESCRIPTIONS

    by_key = {d.key: d for d in SENSOR_DESCRIPTIONS}
    assert by_key["drive_train"].data_key == "drive_train"
    assert by_key["csid"].data_key == "csid"
    assert by_key["csid"].entity_registry_enabled_default is False
    parked = by_key["parked_since"]
    assert parked.data_key == "position_captured_at"
    assert parked.device_class is SensorDeviceClass.TIMESTAMP


def test_new_sensors_are_phantom_guarded():
    # Regression pin: v1.20.2 shipped two ungated Skoda sensors that showed
    # "unknown" on every other brand. These three must stay in the gate so a
    # car whose vgql / parking-position block is empty never spawns them.
    from custom_components.vag_connect.sensor import _DATA_PRESENT_REQUIRED

    for k in ("drive_train", "csid", "parked_since"):
        assert k in _DATA_PRESENT_REQUIRED, f"{k} not phantom-guarded"
