# Copyright 2026 Prash Balan (@its-me-prash) — Apache License 2.0
# SPDX-License-Identifier: Apache-2.0
"""v2.2.0 — Model-Year / Platform quirk-suppression table.

Closes a bug-class the existing ``_capabilities.py`` Phase 3 layer
can't catch: **firmware regressions where the backend reports a
capability as available but the actual API endpoint silently fails**.

Examples reported by competitor projects in 2026:

- **CUPRA Born MY24-MY25** — backend ``capabilities[]`` includes
  ``access`` (lock/unlock) but POST to ``/api/v2/access/{vin}/unlock``
  returns 400 with no error body. Confirmed by pycupra #79.

- **Formentor PHEV (current gen)** — ``engines.primary`` key missing
  from ``mycar`` response despite capability ``engines`` advertised
  as supported. Confirmed by pycupra #76 (parser crash).

- **Audi Q6 e-tron / A6 e-tron (PPE platform, MY24+)** — backend
  advertises ``parameters`` but the actual response uses a different
  schema shape entirely. Confirmed by upstream #686.

### How this differs from `_capabilities.py`

| Layer | What it catches | Source of truth |
|---|---|---|
| `_capabilities.py` | Capability MISSING in backend response | Backend `capabilities[]` endpoint |
| `_my_quirks.py`    | Capability ADVERTISED but BROKEN     | Known-bad firmware list (manual) |

Both layers run before entity creation. Either layer returning
"suppress" hides the entity. Catch-and-release semantics:

1. ``_capabilities.cap_id_for(brand, command)`` → backend lookup
2. ``_my_quirks.is_command_suppressed(brand, model, my, command)`` → manual list
3. If either says hide → entity not created

### How to add a quirk

When a competitor reports a Born MY26 firmware silently breaking
``command_set_target_soc``:

    QUIRKS.append(MYQuirk(
        brand="cupra",
        model_glob="Born",          # case-insensitive substring
        year_min=2026, year_max=None,  # MY26+ until further notice
        suppress_commands={"command_set_target_soc"},
        source="pycupra #XXX (date)",
    ))

That's it — the next coordinator update will hide the entity for any
matching VIN without entity-ID renames or user-visible churn.

"Have you met... your car's actual capabilities?"
— Ted Mosby, in front of the wrong Cariad backend response
"""

from __future__ import annotations

from dataclasses import dataclass
import logging

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class MYQuirk:
    """Single model-year/platform quirk row.

    Matching rules (all must hold):
    - ``brand`` exact match (lower-case) against the integration's
      configured brand-id (audi, volkswagen, skoda, seat, cupra,
      porsche, volkswagen_na, plus Phase-4 luxury adapters).
    - ``model_glob`` case-insensitive substring match against
      ``vehicle["model"]``. Use ``None`` to match any model on this
      brand. Use a tight string (``"Born"``, ``"Octavia iV"``) for
      surgical scoping.
    - ``year_min`` / ``year_max`` (inclusive) bracket against
      ``vehicle["model_year"]``. Use ``None`` for open-ended bounds.
    - ``suppress_commands`` is the set of ``command_id`` strings to
      hide. Same string-space as ``_capabilities.CAPABILITY_MAP``
      keys (``command_lock``, ``command_unlock``, etc.).
    """

    brand: str
    model_glob: str | None
    year_min: int | None
    year_max: int | None
    suppress_commands: frozenset[str]
    source: str  # e.g. "pycupra #79 (2026-05-04)" — for future-archaeology


# ─────────────────────────────────────────────────────────────────────────────
# Seed table — only confirmed quirks. Conservative by design:
# every row needs a competitor-issue source so we never speculate.
#
# Adding a row is cheap — the runtime check is O(N) and N stays small
# (~10-30 max foreseeable, even at full ecosystem maturity).
# ─────────────────────────────────────────────────────────────────────────────


QUIRKS: list[MYQuirk] = [
    # ───── CUPRA Born MY24-MY25 — unlock silently fails (pycupra #79) ─────
    # Backend reports access-capability available but POST returns 400
    # with empty body. v0.2.13+ pycupra explicitly excludes these MYs
    # from the unlock UI. Confirmed across multiple owner reports.
    MYQuirk(
        brand="cupra",
        model_glob="Born",
        year_min=2024,
        year_max=2025,
        suppress_commands=frozenset({"command_unlock"}),
        source="pycupra #79 (2026-05-04)",
    ),
    # ───── Audi PPE platform — engineRemoteStart not on PPE (audi #711) ─────
    # Audi A6 e-tron / Q6 e-tron (PPE platform, MY24+) cannot do remote
    # engine-start because they're pure-electric — the backend should
    # filter the capability but observed live to advertise it anyway.
    MYQuirk(
        brand="audi",
        model_glob="e-tron",  # matches both A6 e-tron + Q6 e-tron substrings
        year_min=2024,
        year_max=None,
        suppress_commands=frozenset({"command_engine_start", "command_engine_stop"}),
        source="upstream #711 (2026-03-18) + PPE-platform inference",
    ),
]


def is_command_suppressed(
    brand: str,
    model: str | None,
    model_year: int | None,
    command_id: str,
) -> bool:
    """Return True if a known quirk says this command silently fails.

    Defensive: missing model / year → no suppression (don't hide
    entities just because metadata is incomplete). Quirk must match
    ALL of: brand, model_glob (if set), year_min (if set), year_max
    (if set). At least one of the matching quirks must list this
    ``command_id`` in its ``suppress_commands`` for suppression.

    Pure function — safe to call from any thread, no I/O.
    """
    brand_lc = (brand or "").lower()
    model_lc = (model or "").lower() if model else None
    for quirk in QUIRKS:
        if quirk.brand != brand_lc:
            continue
        if quirk.model_glob is not None:
            if model_lc is None:
                continue
            if quirk.model_glob.lower() not in model_lc:
                continue
        if quirk.year_min is not None:
            if model_year is None or model_year < quirk.year_min:
                continue
        if quirk.year_max is not None:
            if model_year is None or model_year > quirk.year_max:
                continue
        if command_id in quirk.suppress_commands:
            _LOGGER.debug(
                "MY-quirk hit: brand=%s model=%s my=%s cmd=%s → suppressed (%s)",
                brand_lc, model_lc, model_year, command_id, quirk.source,
            )
            return True
    return False
