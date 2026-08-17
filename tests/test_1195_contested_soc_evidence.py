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


# ── actively charging: SoC can only rise ─────────────────────────────────────

def test_is_charging_true_prefers_higher_without_charging_state() -> None:
    """A live ``is_charging`` is enough on its own (no charging_state string):
    charging can only raise SoC, so the higher contested candidate is the fresh one."""
    assert _soc(
        {"battery_soc": 50, "odometer_km": 100},
        {"battery_soc": 50, **_contest(50, 62), "odometer_km": 100,
         "is_charging": True},
    ) == 62


def test_unplugged_parked_car_does_not_prefer_higher() -> None:
    """Guard: a parked car, not charging, no energy evidence → a spurious high twin
    must NOT win. Falls back to closest-to-last, so the v2.29.0 spurious-twin guard
    still holds (94, not the fabricated 99)."""
    assert _soc(
        {"battery_soc": 94, "odometer_km": 48768},
        {"battery_soc": 94, **_contest(94, 99), "odometer_km": 48768,
         "charging_state": "off"},
    ) == 94


def test_no_energy_and_no_movement_stays_closest_to_last() -> None:
    """Plugged but no candidate exceeds the frozen value and no energy → inert (94)."""
    assert _soc(
        {"battery_soc": 94, "odometer_km": 48768},
        {"battery_soc": 90, **_contest(90, 94), "odometer_km": 48768,
         "charging_state": "READY_FOR_CHARGING"},
    ) == 94


def test_no_odometer_baseline_and_no_energy_stays_inert() -> None:
    """No previous odometer and no energy → no evidence → closest-to-last (94)."""
    assert _soc(
        {"battery_soc": 94},
        {"battery_soc": 94, **_contest(94, 99),
         "charging_state": "READY_FOR_CHARGING"},
    ) == 94


# ── the accepted trade-off: charged-idle with LAGGING energy (transient) ──────

def test_charged_idle_with_lagging_energy_is_a_self_correcting_transient() -> None:
    """Fishermanjb v3.2.0 verbatim: charged 94→99 without driving, but the energy
    reading still lagged (67.45/73.45 ≈ 92 %), so NOTHING fresh proves the 99 yet
    (not contested-vs-energy: |94−92|=2 < 15; not actively charging; odometer flat).

    The old "plugged + not-moved → prefer the higher twin" guessed 99 but was a
    REGRESSION: a car driven DOWN then parked-and-plugged matches the exact same
    shape, so it latched the high stale value (Fishermanjb's real .4 below: it would
    have shown 94 while the car was at ~73). We removed it. We now take the
    energy-nearest 94 for a poll or two, until ``available_kwh`` catches up to the
    charge — then the same rule yields 99. A brief transient-low beats a persistent
    stuck-high."""
    # while the energy reading still lags the finished charge → energy-nearest 94.
    assert _soc(
        {"battery_soc": 94, "odometer_km": 48768},
        {"battery_soc": 94, **_contest(94, 99), "odometer_km": 48768,
         "charging_state": "READY_FOR_CHARGING",
         "battery_available_kwh": 67.45, "battery_cap_kwh": 73.45},
    ) == 94
    # once the pack energy reflects the charge (~99 %), the SAME rule yields 99.
    assert _soc(
        {"battery_soc": 94, "odometer_km": 48768},
        {"battery_soc": 94, **_contest(94, 99), "odometer_km": 48768,
         "charging_state": "READY_FOR_CHARGING",
         "battery_available_kwh": 72.7, "battery_cap_kwh": 73.45},
    ) == 99


# ── Fishermanjb's REAL diagnostic values (v3.2.3 exports .4 and .5) ───────────

def test_fishermanjb_diag4_contested_drove_down_prefers_energy_73() -> None:
    """Real .4 export: soc contested ['73','94'], pack energy 49.15/73.35 ≈ 67 %,
    is_charging False, READY_FOR_CHARGING, odometer unchanged in-poll. He drove the
    car down; 94 is the stale twin. The stale anchor (94) disagrees with the fresh
    67 % energy by 27 (≥ 15) → trust the measurement → the nearest candidate, 73.
    This is exactly the case the removed step-0 got WRONG (it would have kept 94)."""
    assert _soc(
        {"battery_soc": 94, "odometer_km": 48768},
        {"battery_soc": 94, **_contest(73, 94), "odometer_km": 48768,
         "charging_state": "READY_FOR_CHARGING", "is_charging": False,
         "battery_available_kwh": 49.15, "battery_cap_kwh": 73.35},
    ) == 73


def test_fishermanjb_diag5_single_stale_soc_uses_energy_68() -> None:
    """Real .5 export: soc NOT contested (single stale 94), pack energy
    49.6/73.4 ≈ 67.6 %, is_charging False, NOT_READY_FOR_CHARGING. No candidate list
    to arbitrate — the single stale value sits 26 above the fresh energy on a
    not-charging car → the single-value sanity replaces it with round(67.6) = 68."""
    assert _soc(
        {"battery_soc": 94, "odometer_km": 48768},
        {"battery_soc": 94, "odometer_km": 48768,
         "charging_state": "NOT_READY_FOR_CHARGING", "is_charging": False,
         "battery_available_kwh": 49.6, "battery_cap_kwh": 73.4},
    ) == 68


# ── single-value sanity: guards against false overrides ───────────────────────

def test_single_value_small_gap_is_left_untouched() -> None:
    """A normal car: soc 80 with pack energy 78 % (gap 2 < 15) → untouched."""
    assert _soc(
        {"battery_soc": 82},
        {"battery_soc": 80, "battery_available_kwh": 57.3, "battery_cap_kwh": 73.4},
    ) == 80


def test_single_value_soc_below_energy_is_not_overridden() -> None:
    """Directional guard: soc 60 BELOW energy 80 % (a charge just topped the pack,
    soc not yet risen) must NOT be dragged UP — energy trails, it does not lead in a
    way we trust for a single value. Left at the fresh 60."""
    assert _soc(
        {"battery_soc": 55},
        {"battery_soc": 60, "battery_available_kwh": 58.7, "battery_cap_kwh": 73.4},
    ) == 60


def test_single_value_override_skipped_while_charging() -> None:
    """Charge-lag guard: actively charging, soc 94 fresh over a lagging 60 % energy
    → the large gap is the normal charge shape, NOT a stale reading → left at 94."""
    assert _soc(
        {"battery_soc": 50},
        {"battery_soc": 94, "is_charging": True, "charging_state": "CHARGING",
         "battery_available_kwh": 44.0, "battery_cap_kwh": 73.4},
    ) == 94


def test_single_value_override_skipped_when_charging_state_charging() -> None:
    """Same guard via the charging_state string alone (no is_charging key)."""
    assert _soc(
        {"battery_soc": 50},
        {"battery_soc": 94, "charging_state": "CHARGING",
         "battery_available_kwh": 44.0, "battery_cap_kwh": 73.4},
    ) == 94


def test_single_value_override_needs_fresh_energy() -> None:
    """No fresh energy (only a carried-forward previous reading) → no override."""
    assert _soc(
        {"battery_soc": 94, "battery_available_kwh": 49.6, "battery_cap_kwh": 73.4},
        {"battery_soc": 94, "charging_state": "NOT_READY_FOR_CHARGING"},
    ) == 94
