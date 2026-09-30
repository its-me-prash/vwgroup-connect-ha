# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#1231 (Ra72xx) — the climate "time remaining to target temp" ETA must not
latch to a finished run.

On his multi-channel car (EU Data Act portal + vw.de) the climatisation STATE is
live-superseded to OFF from the live channel, while the ETA stays owned by the
portal batch feed, which keeps re-sending the last run's value (the #1403 replay
family). ``reconcile`` now zeroes ``climate_remaining_time_min`` whenever the
final (merged, live-superseded) climatisation state reads off — matching the VW
app (no ETA shown when climate is off) and the pre-heater timer's clear-on-stop.
The gate runs on both reconcile paths (with and without a cached previous) and
only ever fires on an explicit OFF, never on unknown.
"""
from __future__ import annotations

from custom_components.vag_connect.cariad._channel_merge import _LIVE_SUPERSEDE
from custom_components.vag_connect.cariad.vehicle_cache import reconcile


def test_eta_zeroed_when_off_and_replayed() -> None:
    # Ra72xx's exact case: the portal re-sends a non-null ETA every poll while the
    # (live-superseded) state reads off.
    prev = {"climatisation_active": False, "climate_remaining_time_min": 30}
    fresh = {"climatisation_active": False, "climate_remaining_time_min": 30}
    merged, notes = reconcile(prev, fresh)
    assert merged["climate_remaining_time_min"] == 0
    assert any("#1231" in n for n in notes)


def test_eta_zeroed_on_first_poll_no_cache() -> None:
    # falsy previous → the early-return path must gate too.
    merged, _ = reconcile(None, {
        "climatisation_active": False, "climate_remaining_time_min": 45,
    })
    assert merged["climate_remaining_time_min"] == 0


def test_eta_kept_while_climatising() -> None:
    for prev in ({"x": 1}, None):
        merged, _ = reconcile(prev, {
            "climatisation_active": True, "climate_remaining_time_min": 18,
        })
        assert merged["climate_remaining_time_min"] == 18


def test_eta_untouched_when_state_unknown() -> None:
    # climatisation_active None (unknown) must NOT zero a reported ETA.
    for prev in ({"x": 1}, None):
        merged, _ = reconcile(prev, {
            "climatisation_active": None, "climate_remaining_time_min": 12,
        })
        assert merged["climate_remaining_time_min"] == 12


def test_absent_eta_is_a_noop() -> None:
    merged, notes = reconcile({"x": 1}, {"climatisation_active": False})
    assert merged.get("climate_remaining_time_min") in (None, 0)
    assert not any("#1231" in n for n in notes)


def test_climate_eta_is_live_superseded() -> None:
    # symmetry with the charge-time ETA: a live channel must win over a stale
    # portal batch value for the climate ETA too (this was the overlooked gap).
    assert "climate_remaining_time_min" in _LIVE_SUPERSEDE
    assert "remaining_time_target_soc" in _LIVE_SUPERSEDE
