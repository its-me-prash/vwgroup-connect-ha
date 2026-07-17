# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The shared entity attributes never reached the entities that matter.

``VagConnectEntity.extra_state_attributes`` adds ``image_url`` and ``source``,
and its docstring told subclasses to "override + call super()". Seven
subclasses overrode it. None called super(). Python says nothing about that —
the subclass property just wins the MRO and the base never runs.

So sensors, binary_sensors, device_tracker and both image entities — nearly
every entity we create — got neither. ``image_url`` had been dead that way
since v1.25.0 while its docstring claimed "every entity ... becomes a valid
source for those cards", and ``source`` was born dead in 2.18.0: the CHANGELOG
announced "every reading tells you where it came from" for a release in which
no reading did.

The fix inverts the pattern: the base owns the property and calls a
``_platform_attributes`` hook. A platform can't shadow the shared attributes by
forgetting super(), because there's nothing left to forget.

These tests assert on the MRO and on real property calls. A test that mirrors
the logic it checks would have passed against the broken code — that's how this
shipped in the first place.
"""
from __future__ import annotations

import inspect
from unittest.mock import MagicMock

import pytest

from custom_components.vag_connect.binary_sensor import (
    VagAbrpDataChangedSensor,
    VagConnectBinarySensor,
)
from custom_components.vag_connect.device_tracker import VagConnectTracker
from custom_components.vag_connect.entity_base import VagConnectEntity
from custom_components.vag_connect.image import (
    VagRenderImageEntity,
    VagSkodaWidgetImageEntity,
)
from custom_components.vag_connect.sensor import ReporterSensor, VagConnectSensor

_PLATFORM_CLASSES = [
    VagConnectSensor,
    ReporterSensor,
    VagConnectBinarySensor,
    VagAbrpDataChangedSensor,
    VagConnectTracker,
    VagRenderImageEntity,
    VagSkodaWidgetImageEntity,
]


@pytest.mark.parametrize("cls", _PLATFORM_CLASSES, ids=lambda c: c.__name__)
def test_base_owns_the_property(cls: type) -> None:
    """The base must win the MRO — that is the whole fix."""
    winner = next(
        c for c in cls.__mro__ if "extra_state_attributes" in c.__dict__
    )
    assert winner is VagConnectEntity, (
        f"{cls.__name__} shadows extra_state_attributes again; image_url and "
        f"source will silently vanish from every one of its entities"
    )


def test_no_platform_reintroduces_an_override() -> None:
    """Catch the next person who adds one, in any platform file."""
    import ast
    import pathlib

    root = pathlib.Path(__file__).resolve().parents[1] / "custom_components/vag_connect"
    offenders = []
    for path in sorted(root.glob("*.py")):
        if path.name == "entity_base.py":
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if not isinstance(node, ast.ClassDef):
                continue
            for item in node.body:
                if (
                    isinstance(item, ast.FunctionDef)
                    and item.name == "extra_state_attributes"
                ):
                    offenders.append(f"{path.name}::{node.name}")
    assert offenders == [], (
        f"override extra_state_attributes and the shared attributes disappear; "
        f"use _platform_attributes instead. Offenders: {offenders}"
    )


def test_the_hook_is_not_a_property() -> None:
    # The overrides used to be @property. If someone renames one to the hook
    # but leaves the decorator on, the base would merge a property object.
    for cls in _PLATFORM_CLASSES:
        hook = cls.__dict__.get("_platform_attributes")
        if hook is not None:
            assert not isinstance(hook, property), f"{cls.__name__}._platform_attributes"
            assert inspect.isfunction(hook), f"{cls.__name__}._platform_attributes"


class _Probe(VagConnectEntity):
    """Minimal real entity: a platform that adds one attribute of its own."""

    def __init__(self, vehicle: dict, source: str | None = None) -> None:
        self.coordinator = MagicMock()
        self.coordinator.data = {"V": vehicle}
        self._vin = "V"
        self._key = "k"
        self.entity_description = MagicMock(data_key="battery_soc")

    def _platform_attributes(self) -> dict:
        return {"mine": 1}


def test_shared_and_platform_attributes_both_survive() -> None:
    veh = {
        "image_urls": {"front": "https://x/car.png"},
        "field_sources": {"battery_soc": "eu_data_act"},
    }
    attrs = _Probe(veh).extra_state_attributes
    assert attrs is not None
    assert attrs["source"] == "eu_data_act"  # would be missing pre-fix
    assert attrs["mine"] == 1  # the platform's own must not be lost
    assert "image_url" in attrs


def test_platform_attributes_win_on_collision() -> None:
    """A platform naming an attribute the base also sets keeps its own value.

    Merging order is the base first, platform second — the platform is closer
    to the data, so it wins.
    """

    class _Collide(_Probe):
        def _platform_attributes(self) -> dict:
            return {"source": "platform-says-so"}

    veh = {"field_sources": {"battery_soc": "eu_data_act"}}
    assert _Collide(veh).extra_state_attributes["source"] == "platform-says-so"


def test_entity_without_a_description_does_not_explode() -> None:
    """HA's Entity has no class-level entity_description, and our image
    entities never assign one. Reading straight through it was survivable only
    while the overrides shadowed the base away."""

    class _NoDesc(VagConnectEntity):
        def __init__(self) -> None:
            self.coordinator = MagicMock()
            self.coordinator.data = {"V": {"image_urls": {"front": "https://x/y.png"}}}
            self._vin = "V"
            self._key = "k"

    attrs = _NoDesc().extra_state_attributes  # must not raise AttributeError
    assert attrs == {"image_url": "https://x/y.png"}


def test_no_source_when_the_field_has_none() -> None:
    assert _Probe({"field_sources": {}}).extra_state_attributes == {"mine": 1}
