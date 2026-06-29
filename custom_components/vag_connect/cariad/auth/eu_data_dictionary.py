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
from functools import lru_cache
from pathlib import Path
from typing import Any

_DICT_PATH = Path(__file__).with_name("eu_data_dictionary.json")


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


def lookup(key: str | None) -> dict[str, Any] | None:
    """Return the spec entry for a field UUID **or official name**. Accepts a
    dotted path (``eu_data_act.<field>``) and falls back to its last segment;
    tries the UUID table first, then the name index."""
    if not key:
        return None
    table = _load()
    bare = key.rsplit(".", 1)[-1] if "." in key else key
    entry = table.get(key) or table.get(bare)
    if entry is None:
        # portal payloads carry NAMES, not UUIDs → resolve via the name index
        entry = _by_name().get(bare)
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
