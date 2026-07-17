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

from custom_components.vag_connect.const import CONF_SPIN, CONF_SPIN_BY_VIN


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

    # ── v2.17.5 (#759) per-VIN S-PIN overrides ──────────────────────────────
    def test_per_vin_override_wins(self):
        c = _coord(options={CONF_SPIN: "1111", CONF_SPIN_BY_VIN: {"VINA": "2222"}})
        assert c._spin_from_entry("VINA") == "2222"  # per-VIN override wins
        assert c._spin_from_entry("VINB") == "1111"  # unlisted VIN → shared
        assert c._spin_from_entry() == "1111"         # no VIN → shared

    def test_per_vin_empty_falls_back_to_shared(self):
        c = _coord(options={CONF_SPIN: "1111", CONF_SPIN_BY_VIN: {"VINA": ""}})
        assert c._spin_from_entry("VINA") == "1111"

    # ── v2.18.0 — the entry state production actually produces ───────────
    # The options update-listener folds options into entry.data and blanks
    # entry.options (__init__.py), so a saved per-VIN map lives in DATA. The
    # 2.17.5 tests only ever passed options={...} — a state that never exists
    # at runtime — which is why nobody noticed the per-VIN lookup had no data
    # fallback and every car silently used the shared S-PIN instead.
    def test_per_vin_read_from_data_once_listener_folded_options_in(self):
        c = _coord(
            options={},
            data={CONF_SPIN: "1111", CONF_SPIN_BY_VIN: {"VINA": "2222"}},
        )
        assert c._spin_from_entry("VINA") == "2222"
        assert c._spin_from_entry("VINB") == "1111"

    def test_per_vin_options_still_win_over_data(self):
        c = _coord(
            options={CONF_SPIN_BY_VIN: {"VINA": "2222"}},
            data={CONF_SPIN: "1111", CONF_SPIN_BY_VIN: {"VINA": "3333"}},
        )
        assert c._spin_from_entry("VINA") == "2222"

    def test_per_vin_empty_in_data_falls_back_to_shared(self):
        c = _coord(
            options={},
            data={CONF_SPIN: "1111", CONF_SPIN_BY_VIN: {"VINA": ""}},
        )
        assert c._spin_from_entry("VINA") == "1111"

    def test_no_by_vin_setup_unchanged_with_vin_arg(self):
        # existing single-S-PIN setups: passing a VIN must not change the result
        c = _coord(options={CONF_SPIN: "1111"})
        assert c._spin_from_entry("ANYVIN") == "1111"
        c2 = _coord(options={}, data={CONF_SPIN: "3333"})
        assert c2._spin_from_entry("ANYVIN") == "3333"


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
