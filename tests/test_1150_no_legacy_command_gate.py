# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#1150 / #584 — the "no legacy MBB enrolment" verdict must hide the command.

When a car's MBB operationList returns the definitive ``gw.error.authentication``
401, the MBB command channel can never work for that VIN, so the command controls
must be hidden (not left to fail on every press). This guards the gate in
``_mbb_command_capability``. (The diagnostics-visibility half of #1150 — unioning
the parent client with its ``_mbb_command`` / ``_mbb_fallback`` sub-connectors —
is exercised by the diagnostics suite.)

Critically, a VSR 403 ``XID_APP_VW`` must NOT trigger this: that is the HEALTHY
durable-MBB state (commands work, only the data-read plane is closed), and the
recorder deliberately never adds it to the set — see test_584_no_legacy_verdict.
"""
from __future__ import annotations

from types import SimpleNamespace

from custom_components.vag_connect.coordinator import _mbb_command_capability


def _coord(no_legacy: set[str]) -> SimpleNamespace:
    # MBB-primary shape: _mbb_command_channel_client returns the client itself
    # (strategy == "mbb"), which is where the verdict set lives.
    client = SimpleNamespace(
        _tokens=SimpleNamespace(strategy="mbb"),
        mbb_no_legacy_vins=set(no_legacy),
        _mbb_oplist_cache={},
    )
    return SimpleNamespace(_cariad_client=client)


def test_no_legacy_vin_hides_the_mbb_command():
    coord = _coord({"NOLEGACYVIN"})
    # any MBB-routed command → hidden (False), before the oplist-cache path
    assert _mbb_command_capability(coord, "NOLEGACYVIN", "lock") is False
    assert _mbb_command_capability(coord, "NOLEGACYVIN", "start_charging") is False


def test_other_vin_is_not_hidden_by_the_no_legacy_gate():
    coord = _coord({"NOLEGACYVIN"})
    # a VIN NOT in the set falls through to the normal path (empty oplist cache →
    # None / permissive BFF gate); it must never be forced to the no-legacy False.
    assert _mbb_command_capability(coord, "OTHERVIN", "lock") is not False


def test_empty_set_leaves_the_gate_inactive():
    coord = _coord(set())
    assert _mbb_command_capability(coord, "ANYVIN", "lock") is not False
