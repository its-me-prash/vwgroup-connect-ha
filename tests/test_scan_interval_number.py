# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""v2.23.0 (#847) — account-scoped poll-interval Number entity.

The poll interval used to live only in the options-flow slider. This exposes it
as a Number so it can be driven from an HA automation (shorter by day, longer at
night) to cut load on the manufacturer backend. It writes CONF_SCAN_INTERVAL
into entry.options; the update-listener folds that into entry.data and
_poll_loop re-reads it live every iteration (no reload).

Covered:
- native_value: default when unset; options-then-data; survives the options→data
  fold (value present only in data).
- async_set_native_value: writes CONF_SCAN_INTERVAL to entry.options; clamps a
  raw service-call value below MIN / above max into range.
- async_setup_entry creates the entity even for a read-only (portal) entry —
  those users especially want to tune polling.
- entity metadata matches the spec (minutes, 5..240, CONFIG).
"""
from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

from custom_components.vag_connect.const import (
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
)
from custom_components.vag_connect.number import (
    VagConnectScanIntervalNumber,
    async_setup_entry,
)


def _entry(options: dict | None = None, data: dict | None = None):
    entry = MagicMock()
    entry.entry_id = "e1"
    entry.options = options if options is not None else {}
    entry.data = data if data is not None else {}
    return entry


def _coord():
    coord = MagicMock()
    coord.hass.config_entries.async_update_entry = MagicMock()
    return coord


def _num(options: dict | None = None, data: dict | None = None):
    return VagConnectScanIntervalNumber(_coord(), _entry(options, data))


# ── native_value ─────────────────────────────────────────────────────────────

def test_native_value_defaults_when_unset() -> None:
    assert _num().native_value == float(DEFAULT_SCAN_INTERVAL)


def test_native_value_reads_options_first() -> None:
    assert _num(options={CONF_SCAN_INTERVAL: 30}).native_value == 30.0


def test_native_value_survives_options_to_data_fold() -> None:
    # the update-listener blanks options into data; an options-only read would
    # miss the stored value — data must be the fallback.
    assert _num(options={}, data={CONF_SCAN_INTERVAL: 45}).native_value == 45.0


def test_native_value_bad_value_falls_back_to_default() -> None:
    assert _num(options={CONF_SCAN_INTERVAL: "nonsense"}).native_value == float(
        DEFAULT_SCAN_INTERVAL
    )


# ── async_set_native_value ───────────────────────────────────────────────────

def _set(num, value):
    num.async_write_ha_state = MagicMock()  # not added to hass in the unit test
    asyncio.run(num.async_set_native_value(value))
    call = num._coordinator.hass.config_entries.async_update_entry.call_args
    return call.kwargs["options"][CONF_SCAN_INTERVAL]


def test_set_writes_scan_interval_to_options() -> None:
    assert _set(_num(), 25) == 25


def test_set_clamps_below_min() -> None:
    assert _set(_num(), 1) == MIN_SCAN_INTERVAL


def test_set_clamps_above_max() -> None:
    assert _set(_num(), 9999) == 240


# ── async_setup_entry: created even for read-only entries ────────────────────

def test_entity_created_for_read_only_entry() -> None:
    coord = _coord()
    coord.is_read_only = MagicMock(return_value=True)
    entry = _entry()
    entry.runtime_data = coord
    added: list = []
    asyncio.run(async_setup_entry(MagicMock(), entry, added.extend))
    # read-only returns before the per-VIN command sliders, but the poll-interval
    # slider must still be present.
    assert len(added) == 1
    assert isinstance(added[0], VagConnectScanIntervalNumber)


def test_entity_created_before_read_only_gate_for_normal_entry() -> None:
    coord = _coord()
    coord.is_read_only = MagicMock(return_value=False)
    entry = _entry(data={"brand": "volkswagen"})
    entry.runtime_data = coord
    added: list = []
    with patch("custom_components.vag_connect.number.register_dynamic_spawner"):
        asyncio.run(async_setup_entry(MagicMock(), entry, added.extend))
    assert any(isinstance(e, VagConnectScanIntervalNumber) for e in added)


# ── metadata ─────────────────────────────────────────────────────────────────

def test_entity_metadata_matches_spec() -> None:
    num = _num()
    assert num._attr_native_min_value == MIN_SCAN_INTERVAL
    assert num._attr_native_max_value == 240
    assert num._attr_native_step == 5
    assert num._attr_translation_key == "scan_interval"
    assert num.unique_id == "e1_scan_interval"
