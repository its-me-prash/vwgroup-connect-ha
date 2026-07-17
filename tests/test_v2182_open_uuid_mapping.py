# Copyright 2026 Prash Balan (@its-me-prash) - Apache License 2.0
# SPDX-License-Identifier: AGPL-3.0-or-later
"""v2.18.2 — #794/#807: the 15-min EU-Data-Act feed encodes opening states
UUID-keyed under a generic ``open`` boolean leaf. ~10 opening UUIDs share that
leaf, so the bare ``open`` name collides and is meaningless on its own; the
``Data.key`` dictionary UUID is what says WHICH opening it is.

We alias the single-boolean opening UUIDs that fold cleanly into an existing
entity (trunk / engine hood / front sunroof) — the same UUID-alias mechanism the
primary-range point (0ca40e18) already uses — and read them as a fallback when
the descriptive ``open_state_*`` enum path didn't fire.

SCOPE: these tests exercise the MAPPER read (first("<uuid>") → entity). The
flattener step that aliases a live ``{dataFieldName: "open", key: <uuid>}`` point
to its UUID is the existing, separately-covered machinery (config: "open" is now
in _GENERIC_FIELD_NAMES and the UUIDs are in _MAPPED_UUIDS). End-to-end against a
real feed report shape is live-gated — no raw feed trace exists in fixtures yet.
"""
from __future__ import annotations

from custom_components.vag_connect.cariad.auth._eu_data_act import (
    _GENERIC_FIELD_NAMES,
    _MAPPED_UUIDS,
    map_dataset_to_vehicle_data,
)
from custom_components.vag_connect.cariad.models import VehicleData

TRUNK = "25ed3407-82de-353e-9f3e-f37952731932"
HOOD = "8540dd41-556c-3e41-aea9-3e28f8d80a2a"
SUNROOF = "3d219e22-1311-3112-a9cc-f8db86a69a9f"


def _map(fields: dict[str, str]) -> VehicleData:
    return map_dataset_to_vehicle_data(dict(fields), VehicleData(vin="WVWZZZ1KZAW000000"))


def test_v2182_open_is_a_generic_name_and_uuids_are_aliased() -> None:
    assert "open" in _GENERIC_FIELD_NAMES
    for u in (TRUNK, HOOD, SUNROOF):
        assert u in _MAPPED_UUIDS


def test_v2182_trunk_open_uuid_maps_true() -> None:
    assert _map({TRUNK: "true"}).trunk_open is True


def test_v2182_hood_open_uuid_maps_false() -> None:
    assert _map({HOOD: "false"}).hood_open is False


def test_v2182_sunroof_open_uuid_maps_true() -> None:
    assert _map({SUNROOF: "true"}).sunroof_open is True


def test_v2182_descriptive_enum_wins_over_uuid_fallback() -> None:
    # The descriptive open_state_tailgate enum runs first; the UUID fallback only
    # fires when it left the field None. 3 == closed must win over the UUID's true.
    d = _map({"open_state_tailgate": "3", TRUNK: "true"})
    assert d.trunk_open is False
