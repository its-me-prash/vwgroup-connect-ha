# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Loader for the official EU Data Act Data Dictionary (V5.0 Continuous-Data
spec), re-emitted in this project's format. Maps each spec field UUID →
``{name, unit, type, cluster, description}``.

Used to give human names/units to otherwise-opaque portal field identifiers:
the Vehicle Data Scout annotates its findings with the official name, and raw
field discovery names auto-created diagnostic sensors from it. Pure data — no
network, no HA imports — so it is cheap to import anywhere."""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

_DICT_PATH = Path(__file__).with_name("eu_data_dictionary.json")

_WS_RE = re.compile(r"\s+")


def _strip_ws(name: str) -> str:
    """A field name with every run of whitespace removed."""
    return _WS_RE.sub("", name)


@lru_cache(maxsize=1)
def _load() -> dict[str, dict[str, Any]]:
    """Load + cache the dictionary (without the ``_meta`` block). Missing or
    corrupt file degrades to an empty map — the dictionary is an enrichment,
    never a hard dependency."""
    try:
        raw = json.loads(_DICT_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(raw, dict):
        return {}
    return {
        k: v for k, v in raw.items()
        if k != "_meta" and isinstance(v, dict)
    }


@lru_cache(maxsize=1)
def _by_name() -> dict[str, dict[str, Any]]:
    """Secondary index: official field NAME → spec entry. The EU Data Act portal
    returns NAMED fields (``locked_state_front_left_door``), not the UUIDs the
    primary table is keyed by — so name lookup is what the Scout + raw-discovery
    actually need (first name wins on the few duplicate names)."""
    out: dict[str, dict[str, Any]] = {}
    for entry in _load().values():
        name = entry.get("name")
        if isinstance(name, str) and name and name not in out:
            out[name] = entry
    return out


@lru_cache(maxsize=1)
def _by_stripped_name() -> dict[str, dict[str, Any]]:
    """Tertiary index: field name with all whitespace removed → spec entry.

    #1767/#1769 — the catalogue was extracted from VW's PDF, and the extraction
    left line-wrap spaces INSIDE 43 field names: the tyre-sensor service-life
    family is listed as ``LL_TirePressMonit1UDS_ ReadDataByIdentMeasu Value_…``
    once and fully space-stripped once, while cars send a THIRD spelling —
    unbroken prefix, real spaces in the description. The exact indices can never
    match any of the three against the others, so those fields resolved to no
    official name at all and the Scout reported them with an empty spec column
    even though the catalogue describes them.

    Collapsing whitespace on both sides bridges all three spellings. It is a
    LAST resort, tried only after both exact indices miss, so a field that
    already resolves keeps resolving exactly as before.

    Ambiguity is dropped rather than guessed. Nine normalised keys have more
    than one source name; four are one field written two ways (identical
    metadata) and five are the same quantity published twice with DIFFERENT
    unit and type — ``Fuel level`` is ``(%)``/number under Vehicle Status and
    unitless/string under Historical Export. Answering those from here could
    attach the wrong unit to an auto-created sensor, and both spellings are in
    the exact index anyway, so a key whose candidates disagree on
    description/unit/type/cluster is omitted entirely.
    """
    groups: dict[str, list[dict[str, Any]]] = {}
    for entry in _load().values():
        name = entry.get("name")
        if isinstance(name, str) and name:
            stripped = _strip_ws(name)
            if stripped:
                groups.setdefault(stripped, []).append(entry)
    out: dict[str, dict[str, Any]] = {}
    for stripped, candidates in groups.items():
        signatures = {
            (c.get("description"), c.get("unit"), c.get("type"), c.get("cluster"))
            for c in candidates
        }
        if len(signatures) == 1:
            out[stripped] = candidates[0]
    return out


def lookup(key: str | None) -> dict[str, Any] | None:
    """Return the spec entry for a field UUID **or official name**. Accepts a
    dotted path (``eu_data_act.<field>``) and falls back to its last segment;
    tries the UUID table first, then the name index, then the whitespace-
    insensitive name index (see :func:`_by_stripped_name`)."""
    if not key:
        return None
    table = _load()
    bare = key.rsplit(".", 1)[-1] if "." in key else key
    entry = table.get(key) or table.get(bare)
    if entry is None:
        # portal payloads carry NAMES, not UUIDs → resolve via the name index
        entry = _by_name().get(bare)
    if entry is None:
        entry = _by_stripped_name().get(_strip_ws(bare))
    return entry


def describe(key: str | None) -> str | None:
    """Human label for a field UUID — ``'Name (unit)'`` / ``'Name'`` — or None
    when the key is unknown to the spec."""
    entry = lookup(key)
    if not entry:
        return None
    name = entry.get("name")
    if not name:
        return None
    unit = entry.get("unit")
    return f"{name} ({unit})" if unit else str(name)


def field_count() -> int:
    """Number of spec fields available (0 if the dictionary failed to load)."""
    return len(_load())
