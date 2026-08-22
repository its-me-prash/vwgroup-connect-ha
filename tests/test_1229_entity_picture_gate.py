# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#1229 (@Ra72xx) — the vehicle render must not replace every entity's icon.

Previously ``entity_picture`` returned the car photo for EVERY entity, so in
dashboards (mushroom / glance) all 100+ sensors showed the car image instead of
their icons. The render is available as its own Image entity (image.py); now only
opt-in entities (the device tracker, so the device page + map marker keep the
photo) carry it, and every other entity falls back to its icon.
"""
from __future__ import annotations

from unittest.mock import MagicMock

from custom_components.vag_connect.entity_base import VagConnectEntity
from custom_components.vag_connect.device_tracker import VagConnectTracker

_IMG = {"MYAPN8NB": "https://img.example/car.png"}


def _mk(cls, image_urls):
    e = cls.__new__(cls)
    e._vin = "V1"
    e.coordinator = MagicMock()
    e.coordinator.data = {"V1": {"image_urls": image_urls}}
    return e


class TestEntityPictureGate:
    def test_class_flags(self) -> None:
        assert VagConnectEntity._show_vehicle_picture is False
        assert VagConnectTracker._show_vehicle_picture is True

    def test_regular_entity_shows_no_car_picture(self) -> None:
        # A sensor keeps its own icon even when the render is available.
        e = _mk(VagConnectEntity, _IMG)
        assert e.entity_picture is None

    def test_tracker_keeps_the_car_picture(self) -> None:
        t = _mk(VagConnectTracker, _IMG)
        assert t.entity_picture == "https://img.example/car.png"

    def test_tracker_without_images_is_none(self) -> None:
        t = _mk(VagConnectTracker, {})
        assert t.entity_picture is None
