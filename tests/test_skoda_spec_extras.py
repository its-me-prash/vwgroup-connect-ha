# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Škoda factory specification → battery capacity, charge power, engine power.

MyŠkoda 8.18.0 ``VehicleSpecificationDto`` (``vehicleSpecification`` of
``GET api/v1/vehicle-information/{vin}``, ``specification`` of the garage
document) carries ``battery.capacityInKWh``, ``maxChargingPowerInKW`` and
``engine.powerInKW``. The integration already caches the vehicle-information
answer for 24 h; these figures were simply never read. The fixture below has the
shape of ``coverage.txt`` in the 8.18.0 APK inventory, not a capture from a car.
"""
from __future__ import annotations

import asyncio
import json
import threading
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

from homeassistant.const import EntityCategory

from custom_components.vag_connect.cariad.models import VehicleData
from custom_components.vag_connect.coordinator import (
    VagConnectCoordinator,
    _skoda_spec_extras,
)

VIN = "TMBJJ7NX0PY000001"
_PKG = Path(__file__).resolve().parents[1] / "custom_components" / "vag_connect"


def _info(**spec_over: Any) -> dict[str, Any]:
    spec: dict[str, Any] = {
        "title": "Enyaq 85",
        "model": "Enyaq",
        "modelYear": "2024",
        "manufacturingDate": "2023-11-02",
        "engine": {"powerInKW": 210, "type": "electric"},
        "gearbox": {"type": "AUTOMATIC"},
        "maxChargingPowerInKW": 135,
        "battery": {"capacityInKWh": 82},
        "exteriorColour": "Race Blue",
    }
    spec.update(spec_over)
    return {"devicePlatform": "MBB_ODP", "vehicleSpecification": spec}


def test_figures_are_read_from_vehicle_specification() -> None:
    assert _skoda_spec_extras(_info()) == {
        "battery_capacity_spec_kwh": 82.0,
        "max_charging_power_kw": 135.0,
        "engine_power": "210 kW",
    }


def test_older_specification_key_and_upper_case_kwh_are_read() -> None:
    info = {"specification": {"battery": {"capacityInKWH": 13}}}
    assert _skoda_spec_extras(info) == {"battery_capacity_spec_kwh": 13.0}


def test_missing_wrong_type_and_non_positive_values_are_left_out() -> None:
    info = _info(
        battery={"capacityInKWh": "82"},
        maxChargingPowerInKW=None,
        engine={"powerInKW": 0},
    )
    assert _skoda_spec_extras(info) == {}
    assert _skoda_spec_extras(_info(maxChargingPowerInKW=True)) == {
        "battery_capacity_spec_kwh": 82.0,
        "engine_power": "210 kW",
    }


def test_garbage_input_returns_empty() -> None:
    for bad in (None, [], "x", {}, {"vehicleSpecification": "x"}):
        assert _skoda_spec_extras(bad) == {}


def _coord(brand: str, info: dict[str, Any] | None) -> VagConnectCoordinator:
    coord = VagConnectCoordinator.__new__(VagConnectCoordinator)
    coord.hass = MagicMock()
    coord.hass.async_add_executor_job = AsyncMock(return_value=None)
    coord.entry = MagicMock()
    coord.entry.data = {"brand": brand, "username": "t@t.com", "password": "x",
                        "spin": "", "update_interval": 300}
    coord._vehicles_lock = threading.Lock()
    coord._cariad_client = MagicMock()
    coord._cariad_client._image_data = {}
    coord.vehicle_static_info = {VIN: {"info": info}} if info is not None else {}
    coord.vehicle_capabilities = {}
    coord._was_available = True
    coord.data = None
    coord.refresh_static_info = AsyncMock()  # type: ignore[method-assign]
    coord.refresh_capabilities = AsyncMock()  # type: ignore[method-assign]
    return coord


def _enrich(coord: VagConnectCoordinator, data: dict[str, Any]) -> dict[str, Any]:
    data.setdefault("latitude", None)
    data.setdefault("longitude", None)
    return asyncio.run(coord._enrich(data))


def test_enrich_fills_the_figures_for_skoda() -> None:
    out = _enrich(_coord("skoda", _info()), {"vin": VIN})
    assert out["battery_capacity_spec_kwh"] == 82.0
    assert out["max_charging_power_kw"] == 135.0
    assert out["engine_power"] == "210 kW"


def test_enrich_never_touches_the_measured_capacity() -> None:
    # battery_cap_kwh feeds the SoH estimate and ABRP; the nameplate must not.
    out = _enrich(_coord("skoda", _info()), {"vin": VIN})
    assert out.get("battery_cap_kwh") is None


def test_enrich_keeps_values_a_client_already_set() -> None:
    out = _enrich(_coord("skoda", _info()),
                  {"vin": VIN, "max_charging_power_kw": 11.0,
                   "engine_power": "100 kW / 136 PS"})
    assert out["max_charging_power_kw"] == 11.0
    assert out["engine_power"] == "100 kW / 136 PS"


def test_enrich_leaves_other_brands_alone() -> None:
    out = _enrich(_coord("cupra", _info()), {"vin": VIN})
    assert out.get("battery_capacity_spec_kwh") is None
    assert out.get("max_charging_power_kw") is None


def test_enrich_without_cached_info_adds_nothing() -> None:
    out = _enrich(_coord("skoda", None), {"vin": VIN})
    assert out.get("battery_capacity_spec_kwh") is None
    assert out.get("max_charging_power_kw") is None


def test_vehicle_data_fields_default_to_none() -> None:
    d = VehicleData(vin=VIN)
    assert d.battery_capacity_spec_kwh is None
    assert d.max_charging_power_kw is None


def test_sensors_are_diagnostic_typed_and_data_gated() -> None:
    from homeassistant.components.sensor import SensorDeviceClass

    from custom_components.vag_connect import sensor as sn

    cap = next(d for d in sn.SENSOR_DESCRIPTIONS
               if d.key == "battery_capacity_spec_kwh")
    pwr = next(d for d in sn.SENSOR_DESCRIPTIONS
               if d.key == "max_charging_power_kw")
    assert cap.device_class is SensorDeviceClass.ENERGY_STORAGE
    assert cap.native_unit_of_measurement == "kWh"
    assert pwr.device_class is SensorDeviceClass.POWER
    assert pwr.native_unit_of_measurement == "kW"
    for d in (cap, pwr):
        assert d.entity_category is EntityCategory.DIAGNOSTIC
        assert d.data_key == d.key
        assert d.key in sn._DATA_PRESENT_REQUIRED


def test_entity_names_exist_in_strings_and_every_translation() -> None:
    files = [_PKG / "strings.json", *sorted((_PKG / "translations").glob("*.json"))]
    assert len(files) == 13
    for f in files:
        ent = json.loads(f.read_text(encoding="utf-8"))["entity"]["sensor"]
        assert ent["battery_capacity_spec_kwh"]["name"], f.name
        assert ent["max_charging_power_kw"]["name"], f.name


def test_sensors_read_their_value_from_the_data_dict() -> None:
    """The sensor path itself: native_value comes from ``data_key`` of the data."""
    from custom_components.vag_connect import sensor as sn

    data = {
        "vin": VIN,
        "battery_capacity_spec_kwh": 77.0,
        "max_charging_power_kw": 135.0,
        "engine_power": "210 kW",
    }
    for key, want in (
        ("battery_capacity_spec_kwh", 77.0),
        ("max_charging_power_kw", 135.0),
        ("engine_power", "210 kW"),
    ):
        desc = next(d for d in sn.SENSOR_DESCRIPTIONS if d.key == key)
        s = sn.VagConnectSensor.__new__(sn.VagConnectSensor)
        s._vin = VIN
        s.entity_description = desc
        s.coordinator = MagicMock()
        s.coordinator.data = {VIN: data}
        assert s.native_value == want, key
