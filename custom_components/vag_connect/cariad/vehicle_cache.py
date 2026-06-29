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
