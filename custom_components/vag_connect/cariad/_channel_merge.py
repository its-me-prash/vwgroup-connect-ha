# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Cross-channel data merge (b1/C1).

VW EU vehicles can be reachable over several read channels at once, each
carrying a *different* slice of the truth — e.g. for a Golf GTE:

    brand-native / MBB  → fuel level, commands
    EU Data Act portal  → SoC, charging, climate
    vw.de web (authproxy) → VIN, odometer, service, master data

No single channel is complete, so this layer takes the per-channel snapshots
for one VIN and produces a single merged ``VehicleData`` that is the union of
what each channel knows. This generalises the long-standing endpoint-specific
fuel merge (BFF ← MBB VSR) into a field-level, provenance-tracked union.

Pure + deterministic — no I/O, no HA imports. The coordinator owns *when* to
call it; this module only owns *how* the snapshots combine.

Merge rule (gap-fill, priority order):
- ``sources`` are ordered highest-trust first.
- For every field, the first non-None value in priority order wins. A channel
  therefore never overwrites a higher-trust channel's reading; it only fills
  gaps. Disjoint fields (the common case) combine without conflict.
- Drivetrain flags are unioned across all channels (additive detection) and
  ``is_electric`` / ``is_hybrid`` are re-derived from the merged result.
- ``source_channel`` records the channels that actually contributed a value.
"""
from __future__ import annotations

import asyncio
import copy
import logging
from collections.abc import Awaitable
from dataclasses import fields
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .models import VehicleData

_LOGGER = logging.getLogger(__name__)

# Identity / bookkeeping fields the merge must never touch.
_SKIP_FIELDS = frozenset(
    {"vin", "source_channel", "no_data", "has_battery", "has_combustion",
     "is_electric", "is_hybrid"}
)


def merge_channels(
    sources: list[tuple[str, "VehicleData"]],
) -> "VehicleData":
    """Merge per-channel snapshots for one VIN into a single ``VehicleData``.

    ``sources`` is ``[(channel_name, VehicleData), …]`` ordered highest-trust
    first and must be non-empty. Returns a new merged object (inputs are not
    mutated); ``source_channel`` is set to the "+"-joined contributors.
    """
    if not sources:
        raise ValueError("merge_channels requires at least one source")

    from .models import VehicleData  # noqa: PLC0415

    base_name, base = sources[0]
    merged = copy.deepcopy(base)
    contributors: set[str] = set()

    # A field is "unset" when it still equals the construction default — this
    # treats None, [], {} and a default ``False`` uniformly as "no data", so a
    # freshly-built empty snapshot never looks like a contributor.
    ref = VehicleData(vin=base.vin)
    defaults = {f.name: getattr(ref, f.name) for f in fields(ref)}

    def _unset(name: str, value: object) -> bool:
        return bool(value == defaults[name])

    # Seed contributors if the base carries any real value.
    for f in fields(merged):
        if f.name in _SKIP_FIELDS:
            continue
        if not _unset(f.name, getattr(merged, f.name)):
            contributors.add(base_name)
            break

    for name, vd in sources[1:]:
        if vd.vin and base.vin and vd.vin != base.vin:
            # never merge across VINs — a programming error upstream
            continue
        for f in fields(merged):
            if f.name in _SKIP_FIELDS:
                continue
            if _unset(f.name, getattr(merged, f.name)):
                new = getattr(vd, f.name)
                if not _unset(f.name, new):
                    # deepcopy so a mutable value (dict/list, e.g.
                    # raw_unmapped_fields / available_charge_modes) is NOT
                    # shared with the source snapshot — otherwise a later
                    # mutation of either object would corrupt the other.
                    setattr(merged, f.name, copy.deepcopy(new))
                    contributors.add(name)

    _merge_drivetrain(merged, sources)

    # Provenance = the channels that actually contributed a value: "+"-joined
    # when several did, the single channel name when only one had data, None
    # when nothing did (every channel empty).
    if len(contributors) > 1:
        merged.source_channel = "+".join(sorted(contributors))
    elif contributors:
        merged.source_channel = next(iter(contributors))

    # ``merged`` is fully independent: base was deep-copied (above) and every
    # gap-filled value was deep-copied on assignment, so no mutable field is
    # shared with any source snapshot.
    return merged


def _merge_drivetrain(
    merged: "VehicleData", sources: list[tuple[str, "VehicleData"]]
) -> None:
    """Union the additive drivetrain flags across channels and re-derive the
    EV/PHEV/ICE classification from the merged result."""
    has_battery = any(vd.has_battery for _n, vd in sources) or (
        merged.battery_soc is not None
        or merged.electric_range_km is not None
        or merged.charging_state is not None
    )
    has_combustion = any(vd.has_combustion for _n, vd in sources) or (
        merged.fuel_level is not None or merged.combustion_range_km is not None
    )
    merged.has_battery = has_battery
    merged.has_combustion = has_combustion
    if has_battery or has_combustion:
        merged.is_electric = has_battery and not has_combustion
        merged.is_hybrid = has_battery and has_combustion


async def gather_and_merge(
    primary_name: str,
    primary: "VehicleData",
    suppliers: list[tuple[str, Awaitable["VehicleData | None"]]],
) -> "VehicleData":
    """Read supplementary channels concurrently and merge them onto ``primary``.

    The async layer over :func:`merge_channels` for the C1 multi-channel poll:
    ``primary`` is the already-fetched highest-trust snapshot (e.g. brand-native
    / MBB) and ``suppliers`` are ``(channel_name, awaitable→VehicleData|None)``
    read coroutines for read-only channels (EU Data Act portal, vw.de). They run
    concurrently; a supplier that raises or returns None is skipped (a read-only
    fallback failing must never sink the whole poll). Returns ``primary`` verbatim
    when there are no suppliers or none succeed — so single-channel polling is
    byte-for-byte unchanged. The merge keeps ``primary`` highest priority, so a
    read-only channel only ever fills gaps; command routing is untouched.
    """
    if not suppliers:
        return primary
    results = await asyncio.gather(
        *(awaitable for _name, awaitable in suppliers),
        return_exceptions=True,
    )
    sources: list[tuple[str, "VehicleData"]] = [(primary_name, primary)]
    for (name, _awaitable), res in zip(suppliers, results):
        if isinstance(res, BaseException):
            _LOGGER.debug("supplementary channel %s failed, skipped: %s",
                          name, type(res).__name__)
            continue
        if res is not None:
            sources.append((name, res))
    if len(sources) == 1:
        return primary
    return merge_channels(sources)
