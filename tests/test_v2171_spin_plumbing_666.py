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

from unittest.mock import MagicMock

from custom_components.vag_connect.const import CONF_SPIN


def _coord(options=None, data=None):
    from custom_components.vag_connect.coordinator import VagConnectCoordinator
    c = VagConnectCoordinator.__new__(VagConnectCoordinator)
    c.entry = MagicMock()
    c.entry.options = options if options is not None else {}
    c.entry.data = data if data is not None else {}
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
