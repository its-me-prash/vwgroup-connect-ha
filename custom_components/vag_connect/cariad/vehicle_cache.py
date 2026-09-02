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
    # NOT ``primary_engine_soc_pct`` (#1310, indigomejor): on a combustion Škoda
    # ``_primary_soc_or_none`` deliberately suppresses the 12V-SoC that mirrors the
    # fuel level by returning None. reconcile() can't tell "deliberately withheld"
    # from "poll omitted it", so carrying it forward resurrected the stale value —
    # latching the bogus 12V sensor at the last full-tank reading (100 %) forever,
    # since every future poll re-suppresses it. Same trap as the last-fill-up
    # fields below. A genuine distinct 12V reading is re-sent each poll anyway.
    "battery_soc",
    "fuel_level", "primary_engine_fuel_level_pct", "secondary_engine_fuel_level_pct",
    "range_km", "electric_range_km", "combustion_range_km", "total_range_km",
    "range_estimated_full_km", "range_wltp_km", "cng_range_km", "adblue_range_km",
    "primary_engine_range_km", "secondary_engine_range_km",
    "target_soc", "min_soc", "nav_target_soc_pct",
    "fuel_tank_capacity_liters",
    "service_km", "oil_service_km", "service_due_in_days", "oil_service_due_in_days",
    "last_seen_at",
    # #1310 (indigomejor) — equipment_count comes and goes with a richer/leaner
    # payload but doesn't actually change poll-to-poll; blanking it to "unknown"
    # every time a poll omitted the block made it useless in automations/history.
    # NOT the last-fill-up fields: those are staleness-suppressed in _parse_fueling
    # (an implausibly old account session is dropped), and carrying them forward
    # would resurrect exactly the suppressed stale reading we just removed.
    "equipment_count",
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


def _as_aware_dt(raw: Any) -> datetime | None:
    """Coerce a capture timestamp to an aware datetime — it may be a ``datetime``
    (BFF / Škoda paths) or an ISO string (EU Data Act portal). ``None`` otherwise."""
    if isinstance(raw, datetime):
        return raw if raw.tzinfo else raw.replace(tzinfo=timezone.utc)
    return _parse_iso(raw)


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


# #1195 — the energy-content ratio (battery_available_kwh / battery_cap_kwh) is a
# DIRECT physical measurement of the pack charge. Across the whole diagnostics
# archive it tracks battery_soc to ~1 % (p50) / 4.3 % (p75); a gap this large
# (>= 15 %) only ever appeared on the one car whose SoC latched stale-high, so it
# is a safe, evidence-grounded threshold for "the SoC reading is wrong, trust the
# measurement". Below it, normal cars are never touched. (Behavioural signals —
# GPS, time-of-day, "charges at home" — were considered and rejected: they are
# proxies that would be strictly worse than this direct measurement, and add
# state, privacy exposure and failure modes for no gain.)
_SOC_ENERGY_LARGE_GAP = 15.0


def _energy_ratio(fresh: dict[str, Any]) -> float | None:
    """Fresh pack charge as a 0..100 % ratio, or None. Only ``fresh`` values, so a
    carried-forward stale energy reading never drives the choice."""
    avail = fresh.get("battery_available_kwh")
    cap = fresh.get("battery_cap_kwh")
    if (
        isinstance(avail, (int, float)) and not isinstance(avail, bool)
        and isinstance(cap, (int, float)) and not isinstance(cap, bool)
        and cap > 0 and avail >= 0
    ):
        ratio = avail / cap * 100.0
        if 0.0 <= ratio <= 100.0:
            return ratio
    return None


def _resolve_contested_soc(
    numeric: list[float],
    old_val: float,
    fresh: dict[str, Any],
    previous: dict[str, Any],
) -> float:
    """Pick the correct value among contested SoC candidates (#1195, Fishermanjb).

    "Closest to the last-known value" LATCHES on a stale reading, so we break the
    tie with the energy-content ratio — a direct, stateless measurement of the
    pack charge that the archive shows tracks SoC to ~1 %:

    1. **Large disagreement → trust energy.** When the stale anchor disagrees with
       the fresh energy ratio by >= _SOC_ENERGY_LARGE_GAP the SoC is wrong (driven
       down, or the portal shipping a stale value) → take the candidate nearest the
       energy ratio. (The earlier "plugged + not-moved → prefer the higher" step
       was a regression: a car driven down then parked-and-plugged also matched it,
       so it wrongly latched the high stale value — Fishermanjb 94 while really ~73.)
    2. **Actively charging → SoC can only rise** → the higher candidate is real.
    3. **Energy ratio picks the nearest** on a small, clearly-discriminating gap.
    4. **Odometer advanced** → drop a candidate still equal to the frozen value.
    5. Otherwise closest-to-last (unchanged).
    """
    ratio = _energy_ratio(fresh)
    # 1) energy anchor, large gap → the stale SoC is wrong; trust the measurement.
    if ratio is not None and abs(old_val - ratio) >= _SOC_ENERGY_LARGE_GAP:
        return min(numeric, key=lambda v: abs(v - ratio))
    # 2) actively charging → SoC only rises → the higher candidate is the fresh one.
    if fresh.get("is_charging") is True and max(numeric) > old_val:
        return max(numeric)
    # 3) energy ratio picks the nearest candidate when it clearly favours one.
    if ratio is not None:
        by_ratio = min(numeric, key=lambda v: abs(v - ratio))
        others = [v for v in numeric if v != by_ratio]
        if others and all(abs(by_ratio - ratio) < abs(o - ratio) for o in others):
            return by_ratio
    # 4) the car moved (odometer advanced) → a candidate still equal to the frozen
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
    # 5) unchanged: closest to the last-known value.
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
    # #1195 partial-dataset SoC guard. The reliable live SoC is the single-
    # occurrence VALID ``battery_level_HV`` pair; a poll that OMITS it carries
    # only the ``battery_state_report.soc`` leaf, which VW stamps with a fresh-
    # looking capture time even when it is the frozen value from the last stop-
    # charging report. So on a car that normally reports HV, a leaf-only poll
    # would publish that stale leaf as a phantom SoC up/down while parked
    # (soulriding's CUPRA Born datasets 11/13/14; Arno-MA-73's 35-field poll #465).
    # When the recorded SoC came from HV and this poll's SoC is leaf-only, treat
    # the leaf as unreliable and hold the recorded value — exactly like an omitted
    # field. Inert for cars that never ship the HV pair (their SoC always reads as
    # leaf-only, so the recorded provenance is never HV and this never fires).
    _fresh_from_hv = merged.get("battery_soc_from_hv")
    _prev_from_hv = previous.get("battery_soc_from_hv")
    if (
        _prev_from_hv is True
        and _fresh_from_hv is False
        and previous.get("battery_soc") is not None
    ):
        if merged.get("battery_soc") != previous.get("battery_soc"):
            notes.append(
                f"battery_soc {merged.get('battery_soc')} came from the leaf only "
                f"(no HV pair this poll); held recorded {previous['battery_soc']} "
                "(partial dataset, #1195)"
            )
        merged["battery_soc"] = previous["battery_soc"]
    # Provenance is sticky-True: a car that ever shipped a VALID HV pair reports
    # it normally, so remember that across partial polls (and across the carry-
    # forward above, where the fresh poll had no SoC at all).
    if _prev_from_hv is True or _fresh_from_hv is True:
        merged["battery_soc_from_hv"] = True
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
    soc_was_contested = False
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
                # #1195 — when this poll's SoC came from the single-occurrence,
                # VALID battery_level_HV pair, it is already authoritative: do NOT
                # let the contested LEAF candidates (which ship the live AND the
                # frozen value under one capture time) override it. Leave
                # soc_was_contested False so the energy-sanity guard below still
                # catches a stale-high HV value (Fishermanjb .5, soc 94 vs 67%).
                if merged.get("battery_soc_from_hv") is True:
                    continue
                soc_was_contested = True
                # break a stuck-on-stale SoC latch with live evidence (energy-
                # content ratio / the car having moved), not just closest-to-last
                # which freezes on the old value.
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

    # #1195 — single-value energy sanity. A battery_soc that was NOT contested this
    # poll but sits a large margin ABOVE the fresh energy anchor on a car that is
    # NOT charging is a stale-stuck reading (Fishermanjb .5: soc 94 while the pack
    # energy is 67.6 %). The archive shows a >= 15 % gap only ever on that one car,
    # never a normal one. Trust the measurement: round() the ratio — it reads
    # ~usable/gross, a few % low, still far closer to reality than the stale value.
    #
    # Gated deliberately:
    #   * directional (soc - energy, not abs) — energy TRAILS soc during a charge,
    #     so a fresh-high soc over a lagging-low energy is the normal charge shape,
    #     NOT a stale reading; only soc ABOVE energy on a settled car is suspect;
    #   * not charging — the same charge-lag guard from the other side; and
    #   * skipped when soc was already contest-resolved above (that path has the
    #     candidate list and its own, richer evidence).
    if not soc_was_contested:
        _soc = merged.get("battery_soc")
        _sr = _energy_ratio(fresh)
        _cs = str(fresh.get("charging_state") or "").strip().upper()
        _charging = fresh.get("is_charging") is True or _cs == "CHARGING"
        if (
            isinstance(_soc, (int, float)) and not isinstance(_soc, bool)
            and _sr is not None and not _charging
            and _soc - _sr >= _SOC_ENERGY_LARGE_GAP
        ):
            notes.append(
                f"battery_soc {_soc} sat >= {_SOC_ENERGY_LARGE_GAP:.0f} above the "
                f"pack energy ({_sr:.0f}%) on a not-charging car; used the "
                f"energy-derived {round(_sr)}"
            )
            merged["battery_soc"] = round(_sr)

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

    # #465 (shaarkys) — last_seen_at is the car's OWN data-capture time; it only
    # moves forward. On the EU Data Act portal that timestamp arrives contested (a
    # fresh block next to a frozen one from an old stop-charging report); a poll
    # that ships only the OLDER stamp must NOT regress the recorded newer
    # last_seen_at, or the staleness repair fires a false "data is N hours old"
    # even though fresher readings are present (shaarkys: a stale 138h-old
    # car_captured_time latched while live values were current). Hold the newer
    # recorded value; a genuinely fresher reading (> recorded) still wins and
    # auto-clears the warning.
    _fresh_seen = _as_aware_dt(merged.get("last_seen_at"))
    _prev_seen = _as_aware_dt(previous.get("last_seen_at"))
    if _fresh_seen is not None and _prev_seen is not None and _fresh_seen < _prev_seen:
        notes.append(
            f"last_seen_at went backwards {previous.get('last_seen_at')} -> "
            f"{merged.get('last_seen_at')}; kept the newer recorded value (#465)"
        )
        merged["last_seen_at"] = previous["last_seen_at"]
    return merged, notes
