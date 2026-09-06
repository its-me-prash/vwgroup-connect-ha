# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#1340 — one-time entity-registry cleanup of orphaned connectivity sensors.

The per-source connectivity binary_sensors are created dynamically, one per armed
read channel (unique_id ``{vin}_connectivity_{token}``). When an account's channel
set changes across versions/reconfigures, the old sensor is never re-created and
lingers in the registry as a permanent ``unknown``/``unavailable`` leftover
(cyrano330 had to delete ``connectivity_eu_data_act`` by hand). ``_reconcile_
connectivity_entities`` prunes any connectivity entity whose token is no longer in
the vehicle's current ``channel_status`` — conservatively, and scoped to this entry.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from custom_components.vag_connect.coordinator import VagConnectCoordinator

VIN = "WVGZZZ1KZAW123456"
VIN2 = "WAUZZZ8K9BA654321"


def _entry(entity_id: str, unique_id: str):
    e = MagicMock()
    e.entity_id = entity_id
    e.unique_id = unique_id
    return e


def _coord(vehicles: dict):
    c = VagConnectCoordinator.__new__(VagConnectCoordinator)
    c.hass = MagicMock()
    c.entry = MagicMock()
    c.entry.entry_id = "cfg1"
    c.vehicles = vehicles
    return c


def _run(coord, entries):
    registry = MagicMock()
    with patch(
        "homeassistant.helpers.entity_registry.async_get", return_value=registry
    ), patch(
        "homeassistant.helpers.entity_registry.async_entries_for_config_entry",
        return_value=entries,
    ):
        coord._reconcile_connectivity_entities()
    return [call.args[0] for call in registry.async_remove.call_args_list]


def test_orphaned_connectivity_entity_is_removed():
    # The car's current channels are the brand primary + eu_data_act supplementary.
    coord = _coord({
        VIN: {"channel_status": {
            "audi": {"armed": True},
            "eu_data_act": {"armed": True},
        }},
    })
    kept = _entry(
        "binary_sensor.audi_connectivity_eu_data_act",
        f"{VIN}_connectivity_eu_data_act",
    )
    orphan = _entry(
        "binary_sensor.audi_connectivity_website_authproxy",
        f"{VIN}_connectivity_website_authproxy",
    )
    unrelated = _entry("sensor.audi_battery_level", f"{VIN}_battery_level")

    removed = _run(coord, [kept, orphan, unrelated])

    assert orphan.entity_id in removed          # channel no longer armed → pruned
    assert kept.entity_id not in removed        # still armed → kept
    assert unrelated.entity_id not in removed   # not a connectivity sensor → untouched


def test_vin_without_channel_status_is_left_untouched():
    # A VIN whose poll has not populated channel_status: its valid set is unknown,
    # so NOTHING is pruned for it (conservative — never remove on a failed poll).
    coord = _coord({VIN: {"battery_level": 55}})
    orphan_looking = _entry(
        "binary_sensor.audi_connectivity_website_authproxy",
        f"{VIN}_connectivity_website_authproxy",
    )
    removed = _run(coord, [orphan_looking])
    assert removed == []


def test_only_the_matching_vin_is_reconciled():
    # Two cars; only VIN's channels are known. A connectivity entity belonging to
    # VIN2 (unknown channel set) must not be touched by VIN's reconcile.
    coord = _coord({
        VIN: {"channel_status": {"audi": {"armed": True}}},
        VIN2: {"battery_level": 60},  # no channel_status
    })
    vin_orphan = _entry(
        "binary_sensor.a_connectivity_eu_data_act",
        f"{VIN}_connectivity_eu_data_act",
    )
    vin2_entity = _entry(
        "binary_sensor.b_connectivity_eu_data_act",
        f"{VIN2}_connectivity_eu_data_act",
    )
    removed = _run(coord, [vin_orphan, vin2_entity])
    assert vin_orphan.entity_id in removed       # not armed on VIN → pruned
    assert vin2_entity.entity_id not in removed  # VIN2 channel set unknown → skipped


def test_registry_failure_is_swallowed():
    # entity_registry.async_get blowing up must never propagate into the poll.
    coord = _coord({VIN: {"channel_status": {"audi": {"armed": True}}}})
    with patch(
        "homeassistant.helpers.entity_registry.async_get",
        side_effect=RuntimeError("boom"),
    ):
        coord._reconcile_connectivity_entities()  # must not raise
