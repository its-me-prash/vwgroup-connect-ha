# Copyright 2026 Prash Balan (@its-me-prash) — Apache License 2.0
"""v2.2.0 Phase 5b PR #19/20 — Pydantic v2 response-model definitions.

Read-only "dual-write" foundation. Models defined here are validated
ALONGSIDE the legacy dataclass parse — they don't replace it.
Schema mismatches log at DEBUG level so we can iterate on the model
definitions BEFORE the v3.0.0 cut-over removes the legacy code.

## Why ``extra="allow"``

Cariad ships new keys on a rolling basis (mid-month firmware
rotations). ``extra="allow"`` means an unknown key does NOT trigger
a validation error — it's preserved on the model so the existing
scout-warner can still flag truly novel fields, but the validation
SUCCEEDS for the known-good subset.

This is the cross-platform consensus from pycupra + upstream
+ myskoda: strict validation against a rolling backend = constant
false-alarm fatigue. Permissive base with explicit known fields =
real signal.

## Scope (intentionally narrow)

Phase 5b ships ONE model: ``BatteryStatusValue`` covering the
``charging.batteryStatus.value`` block from the Cariad BFF. This is:

- The single most-stable block (currentSOC_pct + cruisingRangeElectric_km
  + carCapturedTimestamp — these field names have been stable since
  2023)
- The most-read block (every coordinator update polls battery state)
- The lowest-risk first model (small surface, well-typed)

Future PRs will expand to: chargingStatus.value, plugStatus.value,
parkingPosition, climatisationStatus.value, fuelLevelStatus.value.

## How to add a new model

When a parser block has stabilised (no schema rotations for 30+
days, ≥3 brands ship the same shape):

1. Define a BaseModel subclass below
2. Wire ONE call site in the brand parser with
   ``validate_response(raw, MyModel, context="vw_eu/myblock")``
3. Monitor DEBUG logs for ~7 days for mismatches
4. If mismatches found: iterate on the model (add field, mark
   Optional, etc.). If clean: lock in.

"In a perfect world, every response would arrive in a Pydantic
model. We live in a world of dataclasses. But we're moving towards
the perfect world. Slowly. With dual-writes."
— Lisa Simpson, on incremental refactoring
"""

from __future__ import annotations

# Import-time guard: this module MUST be importable even when
# Pydantic isn't available (e.g. dev environment without HA Core).
# All the model classes are wrapped so the file parses but the
# classes are None when Pydantic isn't there.
try:
    from pydantic import BaseModel, ConfigDict, Field

    _PYDANTIC_OK = True
except ImportError:
    _PYDANTIC_OK = False
    BaseModel = object  # type: ignore[assignment,misc]
    ConfigDict = None  # type: ignore[assignment,misc]
    Field = None  # type: ignore[assignment,misc]


if _PYDANTIC_OK:

    class BatteryStatusValue(BaseModel):
        """v2.2.0 Phase 5b PR #19/20 — first Pydantic model in the codebase.

        Covers the ``charging.batteryStatus.value`` block from the Cariad
        BFF (VW EU + Audi). Field names have been stable since 2023
        across multiple firmware rotations — lowest-risk first target.

        ``extra="allow"`` keeps validation passing when Cariad rolls a
        new sibling key (e.g. ``batteryConditioning_state`` on PPE
        platform) — the scout-warner catches truly novel keys.
        """

        model_config = ConfigDict(extra="allow")

        # Core fields — every EV / PHEV ships these. Optional because
        # ICE-only vehicles return an empty block on this endpoint.
        currentSOC_pct: int | None = Field(default=None, ge=0, le=100)
        cruisingRangeElectric_km: float | None = Field(default=None, ge=0)
        carCapturedTimestamp: str | None = None

else:
    # Stub so type-checkers in dev environment don't complain about
    # the symbol not existing
    class BatteryStatusValue:  # type: ignore[no-redef]
        """Stub — Pydantic not available in this environment."""
