# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Companion: new entity ids carry the ADB tag, entity names do not.

Live, the EU Data Act entry and the companion entry of one car each had a
device the user named "Tiguan", so both derived sensor.tiguan_battery_level
(the second as ..._2). The companion's ids now read sensor.tiguan_adb_…, while
its names stay "Tiguan Battery Level".
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from custom_components.vag_connect.const import CONF_STRATEGY, STRATEGY_COMPANION_ADB
from custom_components.vag_connect.sensor import SENSOR_DESCRIPTIONS, VagConnectSensor

VIN = "WVGZZZ1KZAW123456"
SOC = next(d for d in SENSOR_DESCRIPTIONS if d.key == "battery_soc")


def _sensor(companion: bool) -> VagConnectSensor:
    coord = MagicMock()
    coord.entry = SimpleNamespace(
        data={CONF_STRATEGY: STRATEGY_COMPANION_ADB} if companion else {"brand": "volkswagen"}
    )
    coord.data = {VIN: {}}
    sensor = VagConnectSensor(coord, VIN, SOC)
    key = f"component.vag_connect.entity.sensor.{SOC.translation_key}.name"
    # Home Assistant 2026.10 reads translations from platform_data, older
    # releases from platform: give both the same fake.
    sensor.platform = sensor.platform_data = SimpleNamespace(
        platform_name="vag_connect", domain="sensor",
        platform_translations={key: "Battery Level"},
        object_id_platform_translations={key: "Battery Level"},
        component_translations={}, object_id_component_translations={},
    )
    return sensor


@pytest.mark.parametrize(("companion", "object_id"), [
    (True, "ADB Battery Level"), (False, "Battery Level"),
])
def test_only_the_derived_entity_id_is_tagged(companion, object_id):
    sensor = _sensor(companion)
    assert sensor.name == "Battery Level"
    # HA prefixes the device name and slugs it: sensor.tiguan_adb_battery_level.
    assert sensor.suggested_object_id == object_id

