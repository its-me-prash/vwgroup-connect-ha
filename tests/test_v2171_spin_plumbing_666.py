# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""v2.17.x (#666) — S-PIN reaches the armed MBB command connector.

torstentosh got "configure your S-PIN" on his Q4 even with a correct PIN:
on a split-brain (EU-Data-Act reads + armed MBB commands) setup the connector
captured its S-PIN once at arm time from entry.data only, so a PIN added
later via Options (which lands in entry.options) never reached it. Fix:
arm resolves options-first, and an Options edit refreshes the live connector.
"""
from __future__ import annotations

from types import MappingProxyType
from unittest.mock import MagicMock

from custom_components.vag_connect.const import CONF_SPIN, CONF_SPIN_BY_VIN


def _coord(options=None, data=None):
    from custom_components.vag_connect.coordinator import VagConnectCoordinator
    c = VagConnectCoordinator.__new__(VagConnectCoordinator)
    c.entry = MagicMock()
    # HA exposes ConfigEntry.data/.options as MappingProxyType, never as a plain
    # dict. Faking them as dicts here hid a bug where the lookup tested
    # `isinstance(..., dict)` and silently dropped every configured S-PIN.
    c.entry.options = MappingProxyType(options if options is not None else {})
    c.entry.data = MappingProxyType(data if data is not None else {})
    return c


class TestSpinFromEntry:
    def test_options_first(self):
        c = _coord(options={CONF_SPIN: "9999"}, data={CONF_SPIN: "1111"})
        assert c._spin_from_entry() == "9999"

    def test_falls_back_to_data(self):
        c = _coord(options={}, data={CONF_SPIN: "1111"})
        assert c._spin_from_entry() == "1111"

    def test_empty(self):
        assert _coord()._spin_from_entry() == ""

    # ── v2.17.5 (#759) per-VIN S-PIN overrides ──────────────────────────────
    def test_per_vin_override_wins(self):
        c = _coord(options={CONF_SPIN: "1111", CONF_SPIN_BY_VIN: {"VINA": "2222"}})
        assert c._spin_from_entry("VINA") == "2222"  # per-VIN override wins
        assert c._spin_from_entry("VINB") == "1111"  # unlisted VIN → shared
        assert c._spin_from_entry() == "1111"         # no VIN → shared

    def test_per_vin_empty_falls_back_to_shared(self):
        c = _coord(options={CONF_SPIN: "1111", CONF_SPIN_BY_VIN: {"VINA": ""}})
        assert c._spin_from_entry("VINA") == "1111"

    def test_no_by_vin_setup_unchanged_with_vin_arg(self):
        # existing single-S-PIN setups: passing a VIN must not change the result
        c = _coord(options={CONF_SPIN: "1111"})
        assert c._spin_from_entry("ANYVIN") == "1111"
        c2 = _coord(options={}, data={CONF_SPIN: "3333"})
        assert c2._spin_from_entry("ANYVIN") == "3333"


class TestSpinMappingProxyRegression:
    """The config entry hands out MappingProxyType, not dict.

    `isinstance(MappingProxyType({...}), dict)` is False, so a lookup gated on
    `isinstance(..., dict)` returns "" for every real-world entry and the user
    gets `spin_required` despite a correctly stored S-PIN. These tests pin the
    runtime type explicitly so the guard cannot regress to `dict`.
    """

    def test_spin_in_data_survives_mappingproxy(self):
        c = _coord(options={}, data={CONF_SPIN: "1111", "username": "a@b.c"})
        assert isinstance(c.entry.data, MappingProxyType)
        assert not isinstance(c.entry.data, dict)  # the trap
        assert c._spin_from_entry() == "1111"

    def test_spin_in_nonempty_options_survives_mappingproxy(self):
        # a non-empty options mapping stays a MappingProxyType (an empty one is
        # falsy and gets replaced by a real dict via `or {}`, masking the bug)
        c = _coord(options={CONF_SPIN: "9999", "scan_interval": 300},
                   data={CONF_SPIN: "1111"})
        assert c._spin_from_entry() == "9999"

    def test_per_vin_override_survives_mappingproxy(self):
        c = _coord(options={CONF_SPIN: "1111", CONF_SPIN_BY_VIN: {"VINA": "2222"}})
        assert c._spin_from_entry("VINA") == "2222"

    def test_refresh_mbb_pushes_real_spin_not_empty(self):
        c = _coord(options={}, data={CONF_SPIN: "1234"})
        cmd = MagicMock()
        cmd._spin = "0000"
        client = MagicMock()
        client._mbb_command_target = lambda: cmd
        c._cariad_client = client
        c._refresh_mbb_command_spin()
        assert cmd._spin == "1234"  # not "" — #666's symptom


class TestRefreshMbbSpin:
    def _armed(self, coord, current="0000"):
        cmd = MagicMock()
        cmd._spin = current
        client = MagicMock()
        client._mbb_command_target = lambda: cmd
        coord._cariad_client = client
        return cmd

    def test_updates_armed_connector_options_first(self):
        c = _coord(options={CONF_SPIN: "4321"}, data={CONF_SPIN: "0000"})
        cmd = self._armed(c)
        c._refresh_mbb_command_spin()
        assert cmd._spin == "4321"  # the later Options PIN now reaches it

    def test_updates_from_data_when_no_options(self):
        c = _coord(options={}, data={CONF_SPIN: "1234"})
        cmd = self._armed(c)
        c._refresh_mbb_command_spin()
        assert cmd._spin == "1234"

    def test_noop_when_nothing_armed(self):
        c = _coord(options={CONF_SPIN: "4321"})
        client = MagicMock()
        client._mbb_command_target = lambda: None
        c._cariad_client = client
        c._refresh_mbb_command_spin()  # must not raise

    def test_noop_when_no_client(self):
        c = _coord()
        c._cariad_client = None
        c._refresh_mbb_command_spin()  # must not raise
