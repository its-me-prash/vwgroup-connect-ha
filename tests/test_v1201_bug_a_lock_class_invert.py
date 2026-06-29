# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for v1.20.1 Bug A — BinarySensor LOCK device-class invert (#131).

Closes Chr1sDub's #131 finding: Skoda Octavia iV 2024 zeigte
"Unlocked" in HA UI obwohl das Auto tatsächlich verriegelt war.
Root cause: HA's `BinarySensorDeviceClass.LOCK` hat invertierte
Semantik — `is_on=True` bedeutet "open/unsafe/unlocked",
`is_on=False` bedeutet "locked/safe". Unser `data["doors_locked"]
= True` (= "ja, verriegelt") wurde direkt durchgereicht und damit
wurde "verriegelt" als "Unlocked" angezeigt.

Fix: in `binary_sensor.is_on`, invert the value when device_class
is LOCK. Other device-classes (DOOR, WINDOW, PLUG, etc.) bleiben
unverändert. Das LockEntity (`lock.py:is_locked`) hat NICHT-
invertierte Semantik (HA convention: True = locked) und liest
denselben Wert — bleibt korrekt.

Affects every brand's `binary_sensor.<vin>_doors_locked` since
the LOCK class was added (early releases).
"""

from __future__ import annotations

from unittest.mock import MagicMock


class TestBinarySensorLockInvert:
    """LOCK device-class is_on must invert the doors_locked field."""

    def _make_sensor(self, key, device_class, vehicle_data):
        from custom_components.vag_connect.binary_sensor import (
            VagConnectBinarySensor, VagBinarySensorDescription, BINARY_DESCRIPTIONS,
        )
        # Find existing description for the key, or build one inline
        desc = next(
            (d for d in BINARY_DESCRIPTIONS if d.key == key),
            None,
        )
        if desc is None:
            # Build minimal description for non-existent test key
            desc = VagBinarySensorDescription(
                key=key,
                translation_key=key,
                data_key=key,
                device_class=device_class,
            )
        coordinator = MagicMock()
        coordinator.data = {"TEST_VIN_123456": vehicle_data}
        sensor = VagConnectBinarySensor.__new__(VagConnectBinarySensor)
        sensor.coordinator = coordinator
        sensor._vin = "TEST_VIN_123456"
        sensor.entity_description = desc
        return sensor

    def test_lock_class_inverts_true(self):
        """data["doors_locked"]=True (= locked) → is_on=False
        (LOCK class: False=safe=locked)."""
        from homeassistant.components.binary_sensor import (
            BinarySensorDeviceClass,
        )
        sensor = self._make_sensor(
            "doors_locked",
            BinarySensorDeviceClass.LOCK,
            {"doors_locked": True},
        )
        assert sensor.is_on is False  # ← inverted: locked = is_on False

    def test_lock_class_inverts_false(self):
        """data["doors_locked"]=False (= unlocked) → is_on=True
        (LOCK class: True=unsafe=unlocked)."""
        from homeassistant.components.binary_sensor import (
            BinarySensorDeviceClass,
        )
        sensor = self._make_sensor(
            "doors_locked",
            BinarySensorDeviceClass.LOCK,
            {"doors_locked": False},
        )
        assert sensor.is_on is True  # ← inverted: unlocked = is_on True

    def test_lock_class_none_stays_none(self):
        """No invert when value is None — stays None for unknown."""
        from homeassistant.components.binary_sensor import (
            BinarySensorDeviceClass,
        )
        sensor = self._make_sensor(
            "doors_locked",
            BinarySensorDeviceClass.LOCK,
            {"doors_locked": None},
        )
        assert sensor.is_on is None

    def test_door_class_does_not_invert(self):
        """DOOR class follows natural semantics: True=open."""
        from homeassistant.components.binary_sensor import (
            BinarySensorDeviceClass,
        )
        sensor = self._make_sensor(
            "doors_open",
            BinarySensorDeviceClass.DOOR,
            {"doors_open": True},
        )
        assert sensor.is_on is True  # ← NOT inverted

    def test_window_class_does_not_invert(self):
        from homeassistant.components.binary_sensor import (
            BinarySensorDeviceClass,
        )
        sensor = self._make_sensor(
            "windows_open",
            BinarySensorDeviceClass.WINDOW,
            {"windows_open": True},
        )
        assert sensor.is_on is True

    def test_plug_class_does_not_invert(self):
        from homeassistant.components.binary_sensor import (
            BinarySensorDeviceClass,
        )
        sensor = self._make_sensor(
            "plug_connected",
            BinarySensorDeviceClass.PLUG,
            {"plug_connected": True},
        )
        assert sensor.is_on is True

    def test_lock_entity_is_locked_unchanged(self):
        """LockEntity (lock.py) has NON-inverted convention —
        is_locked=True when actually locked. Same data field as
        binary_sensor but different entity type. Verify lock entity
        still reads the field correctly."""
        from custom_components.vag_connect.lock import VagDoorLock
        coordinator = MagicMock()
        coordinator.data = {"V": {"doors_locked": True}}
        # Construct without going through __init__ to skip HA wiring
        lock = VagDoorLock.__new__(VagDoorLock)
        lock.coordinator = coordinator
        lock._vin = "V"
        # Lock entity reads doors_locked directly — True means locked
        assert lock.is_locked is True
