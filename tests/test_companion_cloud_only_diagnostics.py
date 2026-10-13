# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Companion: no cloud-client diagnostics that a companion entry never fills.

The push event stream, the API field observer (Vehicle Data Scout) and the
wake counter belong to the cloud clients; on a companion entry they never
change, so they are not created and an earlier version's entry is removed.
"""
from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

import pytest

from custom_components.vag_connect import event as ev
from custom_components.vag_connect import sensor as sn
from custom_components.vag_connect.const import vehicle_unique_id

VIN = "WVGZZZ1KZAW123456"


def _coordinator(*, companion):
    coord = MagicMock()
    coord.is_companion = MagicMock(return_value=companion)
    coord.is_read_only = MagicMock(return_value=True)
    coord.read_capability_hidden = MagicMock(return_value=False)
    coord.vehicles = coord.data = {VIN: {
        "vin": VIN, "wake_count_today": 0, "battery_soc": 70, "has_battery": True,
    }}
    return coord


def _run(platform, coord, registry):
    entry = MagicMock()
    entry.runtime_data = coord
    entry.data = {"brand": "volkswagen"}
    entry.options = {}
    added: list = []
    with patch("homeassistant.helpers.entity_registry.async_get", return_value=registry):
        asyncio.run(platform.async_setup_entry(
            MagicMock(), entry, lambda e, **_k: added.extend(e),
        ))
    return added


def _registry():
    return MagicMock(async_get_entity_id=MagicMock(return_value=None))


def _keys(added):
    return {getattr(getattr(e, "entity_description", None), "key", None) for e in added}


@pytest.mark.parametrize("companion", [True, False])
def test_the_cloud_sensors_only_on_cloud_entries(companion):
    keys = _keys(_run(sn, _coordinator(companion=companion), _registry()))
    assert ("wake_count_today" in keys) is not companion
    assert ("api_observer_findings" in keys) is not companion
    assert "battery_soc" in keys


@pytest.mark.parametrize("companion", [True, False])
def test_the_push_event_only_on_cloud_entries(companion):
    added = _run(ev, _coordinator(companion=companion), _registry())
    assert bool(added) is not companion


def test_an_earlier_push_event_is_removed():
    registry = MagicMock()
    registry.async_get_entity_id = MagicMock(
        side_effect=lambda domain, platform, uid: (
            "event.tiguan_push_event_2"
            if (domain, uid) == ("event", vehicle_unique_id(VIN, "push_event", companion=True))
            else None
        )
    )
    _run(ev, _coordinator(companion=True), registry)
    registry.async_remove.assert_called_once_with("event.tiguan_push_event_2")
