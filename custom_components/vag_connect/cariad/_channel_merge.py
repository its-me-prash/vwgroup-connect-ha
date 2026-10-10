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
from collections.abc import Awaitable, Callable
from dataclasses import fields
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .models import VehicleData

_LOGGER = logging.getLogger(__name__)

# Identity / bookkeeping fields the merge must never touch.
_SKIP_FIELDS = frozenset(
    {"vin", "source_channel", "field_sources",
     # v4.7.11 (#465/#529/#1218) — per-value freshness + ambiguity bookkeeping.
     # Like ``field_sources`` these are attribute-keyed provenance, not readings:
     # the generic gap-fill must never merge them field-by-field (that would mix a
     # ts onto a field a different channel owns). merge_channels rebuilds them from
     # the final ``field_sources`` instead, so the ts always tracks the surviving
     # value.
     "field_captured_ts", "ambiguous_fields",
     "no_data", "has_battery",
     "has_combustion", "is_electric", "is_hybrid"}
)

# The EU Data Act portal's continuous feed is a ~15-minute BATCH export that
# ships frozen stop-charging blocks (a snapshot from the last charge, re-sent —
# sometimes re-stamped with a fresh capture time). Every other channel (vw.de
# web, the CARIAD BFF, MBB, SEAT/CUPRA OLA, the brand-native reads) is a LIVE
# read. For live telemetry — SoC, charging, plug, range, climate — a live
# channel's reading must therefore always beat the batch feed's, regardless of
# which channel is configured as primary; otherwise a stale batch value wins the
# gap-fill and the reading jumps backwards mid-charge (Ra72xx, #1195-family).
# This mirrors a competing integration's portal-supersedes-EU-DA dedup, but is
# brand-agnostic (keyed on channel + field, never on brand).
_BATCH_SOURCES = frozenset({"eu_data_act"})

_LIVE_TELEMETRY = frozenset({
    # battery / SoC / range
    "battery_soc", "target_soc", "electric_range_km",
    # charging live state
    "charging_state", "is_charging", "charging_scenario", "charging_reason",
    "charging_preferred_mode",
    # charge power / rate / time / energy
    "charging_power_kw", "charging_rate_kmh", "actual_charge_rate_kw",
    "charge_complete_eta", "remaining_time_target_soc", "charge_session_energy_kwh",
    # plug / connector
    "plug_state", "plug_connected", "connector_locked",
    # power flow
    "external_power_supply_state", "energy_flow_active",
    # climate live state
    "climatisation_state", "climatisation_active",
    # climate ETA (#1231) — the "time remaining to target temp" twin of the
    # charge-time ETA above; a live channel must win over a stale portal batch
    # value, exactly as remaining_time_target_soc does.
    "climate_remaining_time_min",
})

# Volatile physical closure/lock state. Same reasoning as _LIVE_TELEMETRY: when
# the batch feed is primary it can carry a ≥15-minute-stale (and, like the charge
# blocks, sometimes frozen-and-re-stamped) door/window/lock snapshot, while a live
# channel's on-demand read reflects the car's current closure state. A stale
# "locked"/"closed" reading here is worse than for telemetry — it's the kind of
# thing an automation ("warn me if a door is open") acts on — so a live channel's
# reading must win exactly as it does for SoC/charging.
#
# Deliberately EXCLUDES the fields where "highest-priority live channel wins" is
# NOT a safe proxy for "freshest":
#   - odometer_km: monotonic and monotonic-protected elsewhere; a lower-priority
#     live channel could hold a staler (lower) value → regression (see the
#     odometer test). Gap-fill / primary must stand.
#   - position (lat/lon/position_captured_at): governed by its own carry-forward
#     TTL in vehicle_cache.reconcile, which already reasons about capture age.
#   - fuel_level: has a dedicated endpoint-specific merge (BFF ← MBB VSR).
#   - service_*/master data: effectively static; a 15-min batch age is irrelevant.
_LIVE_CLOSURE = frozenset({
    "doors_locked", "doors_open", "windows_open",
    "doors_individual", "windows_individual", "windows_position",
    "trunk_open", "trunk_locked", "hood_open", "bonnet_locked",
})

# Fields a live channel supersedes when the batch feed owns them (see the loop
# below). Telemetry + volatile closure state; never the monotonic/static/TTL-
# managed fields excluded above.
_LIVE_SUPERSEDE = _LIVE_TELEMETRY | _LIVE_CLOSURE


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

    # v2.18.0 (A2) — per-field provenance, rebuilt from scratch on every merge.
    field_sources: dict[str, str] = {}

    # Seed contributors + provenance from the base. Every field the base
    # actually carries is attributed to the base channel.
    for f in fields(merged):
        if f.name in _SKIP_FIELDS:
            continue
        if not _unset(f.name, getattr(merged, f.name)):
            contributors.add(base_name)
            field_sources[f.name] = base_name

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
                    # This channel filled the gap, so it owns the reading.
                    field_sources[f.name] = name

    # Live supersede: a stale EU-DA batch value must never outrank a live
    # channel's reading. For every superseding field (live telemetry + volatile
    # closure state) the batch feed currently owns, hand it to the highest-
    # priority live channel that actually has a reading. No-op when no live
    # channel is present (EU-DA-only cars keep their value) or when a live channel
    # already owns the field. Order-preserving (walks ``sources`` in priority
    # order) and provenance-correct.
    if any(nm not in _BATCH_SOURCES for nm, _ in sources):
        for f_name in _LIVE_SUPERSEDE:
            if field_sources.get(f_name) not in _BATCH_SOURCES:
                continue  # a live channel already owns it, or nobody set it
            for nm, vd in sources:
                if nm in _BATCH_SOURCES:
                    continue
                live_val = getattr(vd, f_name, None)
                if not _unset(f_name, live_val):
                    setattr(merged, f_name, copy.deepcopy(live_val))
                    field_sources[f_name] = nm
                    contributors.add(nm)
                    break

    # v4.7.8 (#923/#1378) — position: FRESHEST capture wins, not merge order.
    # The EU-DA batch feed can now carry a pin (``persLocation``), and with the
    # portal as PRIMARY its 15-min-old pin would outrank a live vw.de fix via
    # plain gap-fill (position is deliberately outside the live-supersede set:
    # capture AGE, not channel class, is the right judge). Among every source
    # that has a pin AND a parseable capture time, take the newest; a source
    # without a timestamp can't win over one that has one.
    _best_nm: str | None = None
    _best_vd: VehicleData | None = None
    _best_ts: datetime | None = None
    for nm, vd in sources:
        lat = getattr(vd, "latitude", None)
        lon = getattr(vd, "longitude", None)
        ts_raw = getattr(vd, "position_captured_at", None)
        if lat is None or lon is None or not ts_raw:
            continue
        try:
            ts = datetime.fromisoformat(str(ts_raw).replace("Z", "+00:00"))
        except ValueError:
            continue
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        if _best_ts is None or ts > _best_ts:
            _best_nm, _best_vd, _best_ts = nm, vd, ts
    if (
        _best_nm is not None
        and _best_vd is not None
        and field_sources.get("latitude") != _best_nm
    ):
        for f_name in ("latitude", "longitude", "position_captured_at", "heading"):
            val = getattr(_best_vd, f_name, None)
            if val is not None:
                setattr(merged, f_name, copy.deepcopy(val))
                field_sources[f_name] = _best_nm
        contributors.add(_best_nm)

    # v4.7.10 (#1419 Ra72xx) — last_seen_at: FRESHEST capture wins, not merge
    # order. It anchors the stale_data Repair + data_stale binary, but was plain
    # primary-first gap-fill and outside the live-supersede set. With the EU-DA
    # portal contributing, its 15-min batch (here 98 h-frozen) snapshot would win
    # over a live vw.de read via gap-fill → a false "not updated in 98 h" daily.
    # Like position, capture AGE (not channel class) is the right judge: among
    # every source that carries a parseable last_seen_at, the newest wins; a
    # source without one can't win. Values are heterogeneous (datetime from the
    # BFF/Škoda, ISO string from EU-DA/vw.de) — parse tolerant, skip unparseable.
    def _ls_dt(vd: "VehicleData") -> datetime | None:
        raw = getattr(vd, "last_seen_at", None)
        if isinstance(raw, datetime):
            return raw if raw.tzinfo else raw.replace(tzinfo=timezone.utc)
        if isinstance(raw, str) and raw:
            try:
                ts = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            except ValueError:
                return None
            return ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)
        return None

    _ls_nm: str | None = None
    _ls_vd: VehicleData | None = None
    _ls_ts: datetime | None = None
    for nm, vd in sources:
        ls_dt = _ls_dt(vd)
        if ls_dt is None:
            continue
        if _ls_ts is None or ls_dt > _ls_ts:
            _ls_nm, _ls_vd, _ls_ts = nm, vd, ls_dt
    if (
        _ls_nm is not None
        and _ls_vd is not None
        and field_sources.get("last_seen_at") != _ls_nm
    ):
        merged.last_seen_at = copy.deepcopy(_ls_vd.last_seen_at)
        field_sources["last_seen_at"] = _ls_nm
        contributors.add(_ls_nm)

    _merge_drivetrain(merged, sources)

    # Provenance = the channels that actually contributed a value: "+"-joined
    # when several did, the single channel name when only one had data, None
    # when nothing did (every channel empty).
    if len(contributors) > 1:
        merged.source_channel = "+".join(sorted(contributors))
    elif contributors:
        merged.source_channel = next(iter(contributors))

    # v2.18.0 (A2) — per-field provenance. Unlike source_channel this is set
    # even for a single-channel merge, so an entity can always answer "where
    # did my value come from" rather than only on multi-channel entries.
    merged.field_sources = field_sources

    # v4.7.11 (#465/#529/#1218) — carry per-value freshness + ambiguity, rebuilt
    # from scratch each merge exactly like field_sources. For every field, take
    # the entry from the SAME source that OWNS it in ``field_sources`` (computed
    # above, AFTER live-supersede / position / last_seen overrides), so the
    # timestamp always belongs to the value that actually survived. EU-DA is the
    # only channel that populates these, so only EU-DA-sourced fields get an
    # entry; when a live channel supersedes an EU-DA field the ts is correctly
    # dropped (its owner no longer carries one).
    name_to_vd: dict[str, VehicleData] = {}
    for nm, vd in sources:
        name_to_vd.setdefault(nm, vd)
    captured_ts: dict[str, str] = {}
    ambiguous: dict[str, str] = {}
    for f_name, owner in field_sources.items():
        owner_vd = name_to_vd.get(owner)
        if owner_vd is None:
            continue
        src_ts = getattr(owner_vd, "field_captured_ts", None)
        if isinstance(src_ts, dict):
            iso = src_ts.get(f_name)
            if isinstance(iso, str) and iso:
                captured_ts[f_name] = iso
        src_amb = getattr(owner_vd, "ambiguous_fields", None)
        if isinstance(src_amb, dict):
            note = src_amb.get(f_name)
            if isinstance(note, str) and note:
                ambiguous[f_name] = note
    merged.field_captured_ts = captured_ts
    merged.ambiguous_fields = ambiguous

    # ``merged`` is fully independent: base was deep-copied (above) and every
    # gap-filled value was deep-copied on assignment, so no mutable field is
    # shared with any source snapshot.
    return merged


def annotate_provenance(channel: str, data: "VehicleData") -> "VehicleData":
    """Record single-channel provenance on *data*, in place.

    v2.18.0 (B2) — a car with no supplementary channel never reaches
    :func:`merge_channels`, so it had no provenance at all: its entities could
    not say where their values came from, which is exactly the common case.

    This applies the same "does this field carry a value" rule as the merge and
    nothing else. It deliberately does NOT route the snapshot through
    ``merge_channels``: that would also re-derive the drivetrain flags
    (:func:`_merge_drivetrain`), silently changing EV/PHEV classification for
    every single-channel car — a different change wearing this one's clothes.
    """
    from .models import VehicleData  # noqa: PLC0415

    ref = VehicleData(vin=data.vin)
    defaults = {f.name: getattr(ref, f.name) for f in fields(ref)}

    sources: dict[str, str] = {}
    for f in fields(data):
        if f.name in _SKIP_FIELDS:
            continue
        if not bool(getattr(data, f.name) == defaults[f.name]):
            sources[f.name] = channel

    data.field_sources = sources
    if sources:
        data.source_channel = channel
    return data


_BATTERY_EVIDENCE: tuple[str, ...] = (
    "battery_soc", "electric_range_km", "charging_state",
)
_COMBUSTION_EVIDENCE: tuple[str, ...] = ("fuel_level", "combustion_range_km")


def drivetrain_from_evidence(
    get: Callable[[str], Any],
    *,
    asserted_battery: bool = False,
    asserted_combustion: bool = False,
) -> dict[str, bool]:
    """This project's single drivetrain rule, as a mapping of flags to set.

    ADDITIVE and positive-evidence only: a flag goes True on a clear signal and
    is never forced False, so a channel that knows nothing about combustion can
    never flatten a PHEV into an EV. ``asserted_*`` carries the flags already
    believed (from other channels, or from the snapshot being merged into), so
    passing them in is what makes the function unable to demote.

    ``get`` reads one field by name — ``snapshot.get`` for a dict,
    ``lambda k: getattr(obj, k, None)`` for a ``VehicleData``. Extracted in
    v4.12.1 (#1776) so the one-time-export import can use the very rule
    :func:`_merge_drivetrain` already applies, instead of growing a second
    implementation of it next door.
    """
    has_battery = bool(asserted_battery) or any(
        get(k) is not None for k in _BATTERY_EVIDENCE
    )
    has_combustion = bool(asserted_combustion) or any(
        get(k) is not None for k in _COMBUSTION_EVIDENCE
    )
    flags: dict[str, bool] = {
        "has_battery": has_battery,
        "has_combustion": has_combustion,
    }
    # Only claim a CLASSIFICATION when there is something to classify: a car we
    # know nothing about must stay unclassified rather than be called an EV.
    if has_battery or has_combustion:
        flags["is_electric"] = has_battery and not has_combustion
        flags["is_hybrid"] = has_battery and has_combustion
    return flags


def _merge_drivetrain(
    merged: "VehicleData", sources: list[tuple[str, "VehicleData"]]
) -> None:
    """Union the additive drivetrain flags across channels and re-derive the
    EV/PHEV/ICE classification from the merged result."""
    for name, value in drivetrain_from_evidence(
        lambda k: getattr(merged, k, None),
        asserted_battery=any(vd.has_battery for _n, vd in sources),
        asserted_combustion=any(vd.has_combustion for _n, vd in sources),
    ).items():
        setattr(merged, name, value)


async def gather_and_merge(
    primary_name: str,
    primary: "VehicleData",
    suppliers: list[tuple[str, Awaitable["VehicleData | None"]]],
    preferred: str | None = None,
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
    # #1357 — per-VIN read priority. The per-field winner is the ORDER of this
    # list (merge_channels keeps sources[0] highest-trust and lets lower channels
    # only fill gaps). When the caller names a ``preferred`` channel, stable-sort
    # it to the front so it wins every field it carries while the others keep
    # filling the rest. ``list.sort`` is stable, so every other tie-break — and
    # thus the whole merge — is byte-for-byte identical to today when ``preferred``
    # is None/"auto" or names the channel already at the front.
    #
    # NOTE: the preference reorders EVERY field the channel carries, INCLUDING
    # position (lat/lon). The winning channel's ``position_captured_at`` travels
    # with it, so freshness is still surfaced — but a caller that prefers a channel
    # whose position is staler than another's will show the preferred channel's
    # older fix (the whole point of the option is "trust this channel", so this is
    # intended; the motivating case prefers the FRESHER channel).
    if preferred and preferred != "auto":
        sources.sort(key=lambda s: 0 if s[0] == preferred else 1)
    return merge_channels(sources)
