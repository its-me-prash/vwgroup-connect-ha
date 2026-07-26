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
