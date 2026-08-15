# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#1195 (Fishermanjb) — break a stuck-on-stale SoC latch with live evidence.

VW's portal ships the SoC under disagreeing values, sometimes stamping the STALE
one with a NEWER capture time, so the parser leaves it contested. The reconcile
step then picks the candidate CLOSEST to the last-known value — which latches: the
stale value is both the anchor and a candidate, so it keeps winning and a real
SoC change can never land (Fishermanjb's ID.4 froze at 94 % while the car was at
57 %). We now arbitrate contested SoC with independent live evidence:

* energy-content ratio (``battery_available_kwh / battery_cap_kwh``) — stateless,
  so it can override a stuck latch; and
* the car having moved (odometer advanced) — a demonstrable state change, so a
  candidate still equal to the frozen value is the stale one.

The parked-car / no-evidence cases fall back to closest-to-last unchanged, so the
v2.29.0 spurious-twin guard tests still hold.
"""
from __future__ import annotations

from custom_components.vag_connect.cariad.vehicle_cache import reconcile


def _soc(previous: dict, fresh: dict) -> int:
    return reconcile(previous, fresh)[0]["battery_soc"]


def _contest(a: object, b: object) -> dict:
    return {"contested_fields": {"battery_state_report.soc": [str(a), str(b)]}}


# ── energy-content ratio ─────────────────────────────────────────────────────

def test_energy_ratio_picks_the_fresh_value_over_the_frozen_one() -> None:
    """Fishermanjb's exact case: stuck at 94, real 57; 38.9/73.4 kWh ≈ 53 % → 57."""
    assert _soc(
        {"battery_soc": 94},
        {"battery_soc": 57, **_contest(57, 94),
         "battery_available_kwh": 38.9, "battery_cap_kwh": 73.4},
    ) == 57


def test_energy_ratio_only_uses_fresh_values() -> None:
    """A carried-forward (previous) energy reading must not drive the choice —
    only ``fresh`` is consulted, so with no fresh energy it falls through."""
    # previous has energy that would point at 94; fresh has none → no ratio used,
    # and with no other evidence it stays closest-to-last (94).
    assert _soc(
        {"battery_soc": 94, "battery_available_kwh": 68.0, "battery_cap_kwh": 73.4},
        {"battery_soc": 57, **_contest(57, 94)},
    ) == 94


def test_energy_ratio_ignored_when_ambiguous() -> None:
    """If both candidates are ~equidistant from the ratio, don't force a pick."""
    # ratio 50 %; candidates 45 and 55 are equidistant → fall back to closest-last.
    assert _soc(
        {"battery_soc": 45},
        {"battery_soc": 55, **_contest(45, 55),
         "battery_available_kwh": 36.7, "battery_cap_kwh": 73.4},
    ) == 45  # closest to the last-known 45


# ── change-by-exclusion (the car moved) ──────────────────────────────────────

def test_moved_car_excludes_the_frozen_candidate() -> None:
    """Odometer advanced since the last poll → the candidate equal to the frozen
    value is stale and is dropped (no energy fields present)."""
    assert _soc(
        {"battery_soc": 94, "odometer_km": 48000},
        {"battery_soc": 57, "odometer_km": 48005, **_contest(57, 94)},
    ) == 57


def test_parked_car_keeps_closest_to_last() -> None:
    """Odometer unchanged (parked) + no energy → no evidence → closest-to-last."""
    assert _soc(
        {"battery_soc": 94, "odometer_km": 48000},
        {"battery_soc": 57, "odometer_km": 48000, **_contest(57, 94)},
    ) == 94


# ── the v2.29.0 guard tests must still hold (no evidence supplied) ────────────

def test_guard_spurious_twin_on_parked_car_unchanged() -> None:
    """v2.29.0 test_the_reported_case: parked ID.3, spurious 50 twin → keep 71."""
    assert _soc({"battery_soc": 71}, {"battery_soc": 50, **_contest(50, 71)}) == 71


def test_guard_follows_closest_to_last_unchanged() -> None:
    """v2.29.0 test_it_follows_a_car_that_is_actually_charging: prev 60 → 65."""
    assert _soc({"battery_soc": 60}, {"battery_soc": 50, **_contest(50, 65)}) == 65
