# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Cross-brand normalization helpers.

v1.25.0 Sprint C PR-A: extracts logic that was duplicated across 4-5
brand modules into a single place. Pure-function module — no HA imports,
no API client refs, no logging side-effects.

Why this exists:
- Kelvin↔Celsius math was inlined at 5 sites (vw_eu, seat_cupra, vw_na)
  with subtly different defensive checks
- Drivetrain derivation (`is_electric` / `is_hybrid` from
  `has_battery` / `has_combustion`) was inlined at 4 sites
- Range-headline priority (electric → total → combustion) was inlined
  at 2 sites with subtly different fallback orders
- Status-shape walker `node["status"][0]["value"]` for Cariad-BFF
  doors/windows was inlined at 3 sites in vw_eu.py (and inherited by
  audi.py)

All functions tolerate None / garbage input and return either a
typed result or None — they NEVER raise. Property tests in
``tests/test_v1250_normalize.py`` enforce that contract for arbitrary
input via hypothesis (same pattern as v1.24.2's
``test_v1242_property_safe_helpers.py``).

Audit trail: 5-Agent Master-Audit 2026-05-08 → Sprint-C plan in
``docs/SPRINT_C_v1.25.0_PLAN.md`` PR-A.
"""

from __future__ import annotations

from typing import Any, Iterable

from ._util import safe_float


# ─────────────────────────────────────────────────────────────────────────────
# Temperature: Kelvin ↔ Celsius
# ─────────────────────────────────────────────────────────────────────────────


def k_to_c(value: Any, *, decimals: int = 1) -> float | None:
    """Convert Kelvin → Celsius, rounded to ``decimals`` places.

    Used at 5 sites in brand modules for ``targetTemperature_K``,
    ``outsideTemperature_K``, ``temperatureHvBatteryMin_K``. Backend
    has historically shipped string Kelvin temps + null on PHEV
    firmwares — bare ``float()`` crashed the whole vehicle's poll
    (fixed in v1.24.2 via ``safe_float``, now centralised here).

    Returns None for any unparseable input. NEVER raises.
    """
    k = safe_float(value)
    if k is None:
        return None
    return round(k - 273.15, decimals)


def c_to_k(celsius: Any) -> float | None:
    """Convert Celsius → Kelvin (write-side payload helper).

    Used by ``command_set_target_temperature`` write-paths
    (``seat_cupra.py``, ``vw_na.py``). Returns None for unparseable
    input — caller must check before sending the payload.
    """
    c = safe_float(celsius)
    if c is None:
        return None
    return round(c + 273.15, 2)


# ─────────────────────────────────────────────────────────────────────────────
# Drivetrain derivation
# ─────────────────────────────────────────────────────────────────────────────


def derive_drivetrain(
    has_battery: bool, has_combustion: bool,
) -> tuple[bool, bool]:
    """Derive ``(is_electric, is_hybrid)`` from feature presence.

    Replaces inlined::

        d.is_electric = d.has_battery and not d.has_combustion
        d.is_hybrid   = d.has_battery and d.has_combustion

    used at 4 sites (skoda.py, vw_eu.py, seat_cupra.py, vw_na.py,
    porsche.py). Pure logical: 4 input combinations, 4 outputs.
    Property-tested for exhaustiveness.
    """
    is_electric = bool(has_battery) and not bool(has_combustion)
    is_hybrid = bool(has_battery) and bool(has_combustion)
    return is_electric, is_hybrid


# ─────────────────────────────────────────────────────────────────────────────
# Range headline priority
# ─────────────────────────────────────────────────────────────────────────────


def derive_range_headline(
    *,
    electric_km: int | None,
    total_km: int | None,
    combustion_km: int | None,
    has_battery: bool,
) -> int | None:
    """Pick the "headline" range to expose as ``range_km``.

    Preference order (matches user intuition):

    1. **EV/PHEV** (``has_battery=True``) → electric range first
    2. Total range second (PHEV displays this in the dash)
    3. Combustion range third (pure ICE only)
    4. None if no source available

    Replaces inlined ~10-line block in skoda.py:589-598 and ~6-line
    block in vw_eu.py:865-870. Subtle bug fix: the old vw_eu.py path
    fell through to ``electric or total`` (truthy chain) which
    returned 0 if electric was 0; this version returns None when all
    sources are None and never coerces 0 → falsy.
    """
    if has_battery and electric_km is not None:
        return electric_km
    if total_km is not None:
        return total_km
    if combustion_km is not None:
        return combustion_km
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Cariad-BFF status-shape walker
# ─────────────────────────────────────────────────────────────────────────────


def first_status_value(node: Any, default: Any = None) -> Any:
    """Walk Cariad-BFF ``{status: [{value: X, ...}, ...]}`` shape.

    The Cariad-BFF doors/windows endpoint returns lists like::

        {"frontLeft": {"status": [{"value": "CLOSED", "ts": "..."}]}}

    Three sites in ``vw_eu.py`` (lines 906/912/918, inherited by
    ``audi.py``) inline the unreadable
    ``door.get("status", [{}])[0].get("value")`` pattern. This
    helper centralises it + tolerates the 4 backend-bug shapes
    observed in the wild (None, empty list, non-dict element,
    missing "value" key).
    """
    if not isinstance(node, dict):
        return default
    status = node.get("status")
    if not isinstance(status, list) or not status:
        return default
    first = status[0]
    if not isinstance(first, dict):
        return default
    val = first.get("value")
    return val if val is not None else default


# ─────────────────────────────────────────────────────────────────────────────
# Software-update enum tolerance (myskoda PR #565 backport)
# ─────────────────────────────────────────────────────────────────────────────


# Known software-update status values across all VAG brands.
# myskoda PR #565 added ``NO_UPDATE_AVAILABLE`` (silent firmware
# state). myskoda #207 added ``NOT_ACTIVATED``. myskoda #503 added
# ``CHARGING_INTERRUPTED`` (charging-state, not update — but same
# unannounced-enum-value class of bug).
SOFTWARE_UPDATE_STATES_KNOWN: frozenset[str] = frozenset({
    "UP_TO_DATE",
    "UPDATE_AVAILABLE",
    "INSTALLING",
    "INSTALLED_SUCCESSFULLY",
    "INSTALLATION_FAILED",
    "NOT_ACTIVATED",
    "NO_UPDATE_AVAILABLE",         # myskoda PR #565 (2026-04-20)
    "READY_FOR_INSTALLATION",
    "DOWNLOADING",
})


def normalize_software_update_state(
    raw: Any, known: Iterable[str] = SOFTWARE_UPDATE_STATES_KNOWN,
) -> tuple[bool | None, str | None]:
    """Parse a software-update status value into ``(is_update_available, raw_state)``.

    Returns ``(None, None)`` for unparseable input — caller should
    surface as "unknown" rather than crashing the entity. NEVER raises.

    Tolerates the ``NO_UPDATE_AVAILABLE`` and ``NOT_ACTIVATED`` enum
    values that older parsers crashed on (myskoda PR #565 + #207
    pattern). Also tolerates lower-case + whitespace.
    """
    if raw is None:
        return None, None
    text = str(raw).strip()
    if not text:
        return None, None
    upper = text.upper()
    known_upper = {k.upper() for k in known}
    is_available_states = {"UPDATE_AVAILABLE", "READY_FOR_INSTALLATION", "DOWNLOADING"}
    is_unavailable_states = {"UP_TO_DATE", "NO_UPDATE_AVAILABLE", "NOT_ACTIVATED",
                             "INSTALLED_SUCCESSFULLY"}
    if upper in is_available_states:
        return True, text
    if upper in is_unavailable_states:
        return False, text
    if upper in known_upper:
        # Known-but-ambiguous (e.g. INSTALLING, INSTALLATION_FAILED) —
        # surface as "no update available" so the binary_sensor stays off.
        return False, text
    # Unknown enum — defensive: don't crash, just return raw.
    return None, text
