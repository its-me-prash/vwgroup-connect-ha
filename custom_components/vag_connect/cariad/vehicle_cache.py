# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Portal-safety: a per-entry local last-known-good cache of vehicle data.

A null / empty / failed poll (e.g. an EU Data Act portal outage) must never
blank the dashboard, the recorded values must survive a Home Assistant restart,
and an implausible reading — e.g. an odometer that jumps *backwards* — must be
rejected in favour of the recorded value, until real new data arrives.

This module is the pure reconcile/serialise logic; the coordinator owns the
``Store`` that actually reads/writes the snapshot to ``.storage``.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from ._util import drop_odometer_sentinel

VEHICLE_CACHE_VERSION = 1


def vehicle_cache_key(entry_id: str) -> str:
    """`.storage` key for an entry's last-known-good vehicle snapshot."""
    return f"vag_connect_vehicles_{entry_id}"


# Cumulative / slow telemetry: when a fresh poll omits the field (None) but we
# hold a recorded value, keep the recorded one ("old but visible") instead of
# blanking it. Volatile state (locks, charging, doors, windows, climate) is
# deliberately NOT here — a stale "unlocked" / "charging" reads as fact and is
# misleading, so those always reflect the latest poll (fresh-or-unknown).
CARRY_FORWARD_FIELDS: frozenset[str] = frozenset({
    "odometer_km",
    "battery_soc", "primary_engine_soc_pct",
    "fuel_level", "primary_engine_fuel_level_pct", "secondary_engine_fuel_level_pct",
    "range_km", "electric_range_km", "combustion_range_km", "total_range_km",
    "range_estimated_full_km", "range_wltp_km", "cng_range_km", "adblue_range_km",
    "primary_engine_range_km", "secondary_engine_range_km",
    "target_soc", "min_soc", "nav_target_soc_pct",
    "fuel_tank_capacity_liters",
    "service_km", "oil_service_km", "service_due_in_days", "oil_service_due_in_days",
    "last_seen_at",
})

# #923 — the parked position belongs in the "old but visible" class too: a
# degraded parkingposition response that omits the coordinates does NOT mean the
# car moved, and blanking them sent the device_tracker to "unknown" mid-outage.
# A parked car is still where it last was, and the poll that brings real
# coordinates back overwrites these immediately.
#
# v2.24.1 — but NOT forever, and not as a bare pair. Held in CARRY_FORWARD_FIELDS
# these were carried with no age attached and across restarts, so a position from
# last week presented exactly like one from a minute ago, and the backend's own
# ``parkingPositionNotAvailable`` was masked rather than surfaced. They are now
# reconciled as one group under a TTL, address and city included: carrying
# coordinates while dropping the address left a half-position that read as a
# parser fault, and the address is the only staleness hint a user actually sees.
POSITION_FIELDS: tuple[str, ...] = (
    "latitude", "longitude", "parking_address", "parking_city",
)

# How long a recorded position may still be shown when the backend stops serving
# one. A parked car really does stay put, so this is generous; it exists to stop
# an indefinitely stale position, not to expire a legitimately parked one.
POSITION_MAX_AGE_S: int = 24 * 3600


def _parse_iso(raw: Any) -> datetime | None:
    """Best-effort ISO-8601 → aware datetime. ``None`` when unparseable."""
    if not isinstance(raw, str) or not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def position_age_seconds(previous: dict[str, Any]) -> float | None:
    """Age of a recorded position, or ``None`` when it cannot be established.

    Prefers the backend's own capture time and falls back to ``last_seen_at``.
    An unknown age is deliberately NOT treated as expired: brands that never
    supply a timestamp would otherwise lose a working position entirely.
    """
    for key in ("position_captured_at", "last_seen_at"):
        stamp = _parse_iso(previous.get(key))
        if stamp is not None:
            return (datetime.now(tz=timezone.utc) - stamp).total_seconds()
    return None

# Fields that physically only ever increase. A fresh value below the recorded
# one is a bad reading (the portal occasionally serves a stale / zero odometer)
# — keep the recorded value so the "km" sensor never jumps backwards.
MONOTONIC_INCREASING_FIELDS: tuple[str, ...] = ("odometer_km",)

# Raw portal field name -> the entity attribute it fills, for the contested
# reading resolver below. Deliberately explicit and NUMERIC-only: comparing a
# candidate to the last known value is only meaningful for a quantity that
# moves gradually. Enum fields turn up contested too (charge mode, charge
# state), but "closest to last" is meaningless there and preferring the
# previous one would just freeze the state, so they are left alone.
_CONTESTED_ATTR: dict[str, str] = {
    "battery_state_report.soc": "battery_soc",
    "soc": "battery_soc",
    "settings.target_soc": "target_soc",
    "target_soc": "target_soc",
    "mileage.value": "odometer_km",
    "mileage": "odometer_km",
    "odometer": "odometer_km",
}


# #1195 — charging_state normalises inconsistently across paths ("charging" /
# "off" / raw "READY_FOR_CHARGING"), so "plugged" is inferred as "not one of the
# clearly-unplugged states". Deliberately conservative: an ambiguous "off" is
# treated as NOT plugged so the charge-aware rule never fires on a stable
# unplugged car (better to under-fire than to wrongly prefer the higher twin).
_SOC_UNPLUGGED_STATES = frozenset({
    "", "off", "not_ready_for_charging", "unplugged", "disconnected",
    "none", "unknown", "error", "invalid",
})


def _resolve_contested_soc(
    numeric: list[float],
    old_val: float,
    fresh: dict[str, Any],
    previous: dict[str, Any],
) -> float:
    """Pick the correct value among contested SoC candidates (#1195, Fishermanjb).

    The default "closest to the last-known value" rule LATCHES on a stale reading:
    once the sensor is stuck on the old value, that value is both the anchor AND a
    candidate, so it keeps winning and a genuinely changed SoC can never land. We
    break the tie with independent LIVE evidence instead:

    1. **Energy-content ratio** — ``battery_available_kwh / battery_cap_kwh`` is the
       actual charge in the pack, is not part of the contested set, and is
       *stateless*, so it can override a stuck latch. Pick the candidate nearest
       that ratio when it clearly favours one.
    2. **Change-by-exclusion** — the odometer is monotonic and uncontested, so if
       it advanced since the last poll the car demonstrably moved and the SoC must
       have changed; a candidate still equal to the frozen last value is therefore
       the stale one and is excluded.
    3. Otherwise fall back to closest-to-last (unchanged behaviour).

    Only ``fresh`` values are consulted, so a carried-forward stale energy/odometer
    reading never drives the choice.
    """
    # 0) charge-aware (#1195, Fishermanjb): a car that demonstrably did NOT move
    #    (odometer unchanged) but is plugged in can only have GAINED charge —
    #    driving is the only thing that quickly drops SoC — so when a candidate
    #    higher than the frozen value exists, that higher one is the post-charge
    #    reading. This is exactly the case the energy-ratio step below gets WRONG:
    #    right after a charge the derived ``battery_available_kwh`` still lags the
    #    old SoC, so the ratio points back at the stale value and latches it. (He
    #    charged 94→99 without driving; available 67.45/73.45 ≈ 92 % sat nearer 94.)
    prev_odo = previous.get("odometer_km")
    fresh_odo = fresh.get("odometer_km")
    _not_driven = (
        isinstance(prev_odo, (int, float)) and not isinstance(prev_odo, bool)
        and isinstance(fresh_odo, (int, float)) and not isinstance(fresh_odo, bool)
        and fresh_odo <= prev_odo
    )
    _cs = str(fresh.get("charging_state") or "").strip().lower()
    _plugged = bool(fresh.get("is_charging")) or _cs not in _SOC_UNPLUGGED_STATES
    if _not_driven and _plugged and max(numeric) > old_val:
        return max(numeric)
    # 1) energy-content ratio (only fresh values; must be a plausible 0..100 %).
    avail = fresh.get("battery_available_kwh")
    cap = fresh.get("battery_cap_kwh")
    if (
        isinstance(avail, (int, float)) and not isinstance(avail, bool)
        and isinstance(cap, (int, float)) and not isinstance(cap, bool)
        and cap > 0 and avail >= 0
    ):
        ratio = avail / cap * 100.0
        if 0.0 <= ratio <= 100.0:
            by_ratio = min(numeric, key=lambda v: abs(v - ratio))
            others = [v for v in numeric if v != by_ratio]
            if others and all(abs(by_ratio - ratio) < abs(o - ratio) for o in others):
                return by_ratio
    # 2) the car moved (odometer advanced) → a candidate still equal to the frozen
    #    last value is stale; drop it and choose from the rest.
    prev_odo = previous.get("odometer_km")
    fresh_odo = fresh.get("odometer_km")
    if (
        isinstance(prev_odo, (int, float)) and not isinstance(prev_odo, bool)
        and isinstance(fresh_odo, (int, float)) and not isinstance(fresh_odo, bool)
        and fresh_odo > prev_odo
    ):
        non_frozen = [v for v in numeric if v != old_val]
        if non_frozen and len(non_frozen) < len(numeric):
            return min(non_frozen, key=lambda v: abs(v - old_val))
    # 3) unchanged: closest to the last-known value.
    return min(numeric, key=lambda v: abs(v - old_val))


def _heal_cached_sentinels(previous: dict[str, Any]) -> dict[str, Any]:
    """Purge a poisoned sentinel from a restored snapshot so it neither carries
    forward nor blocks a fresh reading (#1122).

    A pre-fix cache can hold an implausible odometer (``429_496_729`` km, the
    uint32/10 "no value" sentinel) written before ``drop_odometer_sentinel``
    existed. Left in ``previous`` it does DOUBLE damage in :func:`reconcile`: it
    is carried forward whenever a poll drops the sentinel to ``None`` (endlessly
    resurrecting itself), AND — because ``odometer_km`` is monotonic-increasing —
    it out-ranks the real low reading (``1_794 < 429_496_729`` → "went backwards,
    kept old"), actively blocking the true value from ever landing. Dropping it
    here lets the cache self-heal on the next poll, on ANY channel. Returns a
    shallow copy only when something was purged, else the original untouched.
    """
    odo = previous.get("odometer_km")
    if odo is not None and drop_odometer_sentinel(odo) is None:
        previous = dict(previous)
        previous.pop("odometer_km", None)
    return previous


def strip_runtime(data: dict[str, Any]) -> dict[str, Any]:
    """Drop runtime-only keys (``_client``, ``_poll_failed``, ``_restored``, …)
    so the snapshot is JSON-serialisable for the on-disk store."""
    return {k: v for k, v in data.items() if not str(k).startswith("_")}


def reconcile(
    previous: dict[str, Any] | None,
    fresh: dict[str, Any],
) -> tuple[dict[str, Any], list[str]]:
    """Merge a fresh poll over the last-known-good snapshot.

    * carry a recorded value forward when the fresh poll omitted it (``None``);
    * reject a monotonic field that went backwards (keep the recorded value).

    Returns ``(merged, notes)`` where ``notes`` are human-readable discrepancy
    lines for debug logging. A falsy ``previous`` returns ``fresh`` untouched.
    """
    if not previous:
        return fresh, []
    # #1122 — a snapshot poisoned with a pre-fix odometer sentinel must not
    # resurrect itself (carry-forward) or block the real reading (monotonic).
    previous = _heal_cached_sentinels(previous)
    merged = dict(fresh)
    notes: list[str] = []
    for field in CARRY_FORWARD_FIELDS:
        if merged.get(field) is None and previous.get(field) is not None:
            merged[field] = previous[field]
    # Position — carried as ONE group and only when the fresh poll has no
    # coordinates at all. Topping a fresh position up with the previous
    # address would pin last week's street name onto this minute's
    # coordinates, which is worse than showing no address.
    if merged.get("latitude") is None and merged.get("longitude") is None:
        age = position_age_seconds(previous)
        if age is not None and age > POSITION_MAX_AGE_S:
            notes.append(
                f"recorded position is {age / 3600:.0f}h old "
                f"(limit {POSITION_MAX_AGE_S // 3600}h); dropped, not carried"
            )
        else:
            for field in (*POSITION_FIELDS, "position_captured_at"):
                if merged.get(field) is None and previous.get(field) is not None:
                    merged[field] = previous[field]
    # Contested readings: the export delivered one field twice under a single
    # capture time with different values, so the parser could only pick by
    # position in the array. That is not evidence, and it is what makes a
    # charge level flip between two numbers on a parked car. Here we know the
    # last good value, so we take the candidate closest to it: a real change
    # moves the reading gradually between polls, while the spurious twin sits
    # far away (typically a fixed placeholder that never tracks the car at
    # all). This ONLY runs where the parser already had to guess, so a reading
    # that was never contested is untouched.
    contested = fresh.get("contested_fields") or {}
    if isinstance(contested, dict):
        for raw_name, candidates in contested.items():
            attr = _CONTESTED_ATTR.get(raw_name)
            if attr is None or not isinstance(candidates, (list, tuple, set)):
                continue
            old_val = previous.get(attr)
            if not isinstance(old_val, (int, float)) or isinstance(old_val, bool):
                continue
            numeric: list[float] = []
            for c in candidates:
                try:
                    numeric.append(float(c))
                except (TypeError, ValueError):
                    continue
            if len(numeric) < 2:
                continue
            if attr == "battery_soc":
                # #1195 — break a stuck-on-stale SoC latch with live evidence
                # (energy-content ratio / the car having moved), not just
                # closest-to-last which freezes on the old value.
                best_val = _resolve_contested_soc(
                    numeric, float(old_val), fresh, previous
                )
            else:
                best_val = min(numeric, key=lambda v: abs(v - float(old_val)))
            current = merged.get(attr)
            if isinstance(current, (int, float)) and not isinstance(current, bool):
                if float(current) != best_val:
                    notes.append(
                        f"{attr} was reported as {sorted(numeric)} under one "
                        f"capture time; kept {best_val} as the one consistent "
                        f"with the last reading {old_val}"
                    )
                    merged[attr] = (
                        int(best_val) if float(old_val).is_integer()
                        and best_val.is_integer() else best_val
                    )

    for field in MONOTONIC_INCREASING_FIELDS:
        new = merged.get(field)
        old = previous.get(field)
        if (
            isinstance(new, (int, float))
            and not isinstance(new, bool)
            and isinstance(old, (int, float))
            and not isinstance(old, bool)
            and new < old
        ):
            notes.append(f"{field} went backwards {old}->{new}; kept {old}")
            merged[field] = old
    return merged, notes
