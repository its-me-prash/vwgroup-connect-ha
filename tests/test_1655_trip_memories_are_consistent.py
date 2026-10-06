# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The three trip-distance memories are presented the same way.

@fschulte2812 asked why the trip-computer distance his car reports does not
appear, having found the other two. The answer was that it shipped as a
disabled diagnostic entity while its two siblings are ordinary sensors — a
caution left over from when the field was new and unverified. The field has
been read on real cars since (#1655 and the Scout reports behind it), so the
caution has outlived its reason.

What stays cautious is the state class, and that is a different question with
its own open issue (#1578): nobody has confirmed yet whether this memory can be
reset. ``measurement`` records the value either way; ``total_increasing`` would
also publish a long-term statistics SUM, and if the memory does reset that sum
silently double-counts distance the odometer already carries. Upgrading later
is one line. Un-poisoning accumulated statistics is not.
"""
from __future__ import annotations

import pytest

from custom_components.vag_connect.sensor import SENSOR_DESCRIPTIONS

_TRIP_MEMORIES = (
    "lifetime_trip_distance_km",
    "last_trip_distance_km",
    "cyclic_trip_distance_km",
)


def _by_key(key: str):
    for desc in SENSOR_DESCRIPTIONS:
        if desc.key == key:
            return desc
    raise AssertionError(f"no sensor description for {key}")


@pytest.mark.parametrize("key", _TRIP_MEMORIES)
def test_a_trip_memory_is_an_ordinary_visible_sensor(key: str):
    desc = _by_key(key)

    assert getattr(desc, "entity_registry_enabled_default", True) is True, (
        f"{key} is hidden until the user goes looking for it"
    )
    assert getattr(desc, "entity_category", None) is None, (
        f"{key} is filed under diagnostics while its siblings are not"
    )


@pytest.mark.parametrize("key", _TRIP_MEMORIES)
def test_a_trip_memory_is_a_distance_in_kilometres(key: str):
    from homeassistant.components.sensor import SensorDeviceClass
    from homeassistant.const import UnitOfLength

    desc = _by_key(key)

    assert desc.device_class is SensorDeviceClass.DISTANCE
    assert desc.native_unit_of_measurement == UnitOfLength.KILOMETERS


def test_the_resettable_question_keeps_the_cyclic_memory_on_measurement():
    """#1578 — until we know whether it resets, it must not publish a SUM."""
    from homeassistant.components.sensor import SensorStateClass

    assert (_by_key("cyclic_trip_distance_km").state_class
            is SensorStateClass.MEASUREMENT)
    # the one that is known not to reset is the one allowed to total
    assert (_by_key("lifetime_trip_distance_km").state_class
            is SensorStateClass.TOTAL_INCREASING)
