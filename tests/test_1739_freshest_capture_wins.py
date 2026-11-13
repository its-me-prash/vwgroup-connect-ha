# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#1739 (awood-ops, 5.3.0) — when two captures of the same day disagree, the
NEWEST capture must win for charging_state, charging_scenario and the plug field.

An Audi Q4 e-tron (portal mode) was unplugged at 08:07 but the Charging Port kept
reading `connected` and the status `CHARGING` all afternoon. Two captures that day
disagreed: an 08:01 capture (CHARGING_HV_BATTERY / IMMEDIATELY_CHARGING_ACTIVE —
correct, it was plugged then) and a 14:57 capture (NOT_READY_FOR_CHARGING / OFF).
The stale 08:01 values won because charging_state, charging_scenario and the plug
field were resolved with ``first()`` (fixed alias order), not ``first_freshest()``
(newest capture wins) — the same stale-alias trap #465 fixed for SoC. The stale
"charging" kept is_charging True and fired the IMMEDIATELY lift, which set
plug_connected True, which the coordinator derives into Charging Port = connected.

Equal timestamps still keep the canonical list order, so the common case (bare and
dotted spellings of one node, same capture time) is unchanged.
"""
from __future__ import annotations

from custom_components.vag_connect.cariad.auth._eu_data_act import (
    map_dataset_to_vehicle_data,
)
from custom_components.vag_connect.cariad.models import VehicleData

_CS_CANON = "charging_state_report.current_charge_state"
_CS_LATER = "chargingState"
_SCN_CANON = "charging_state_report.charging_scenario"
_SCN_LATER = "charging_scenario"
_PLUG_CANON = "charging_plug1_connectionstate"
_PLUG_LATER = "plugConnectionState"


def _map(fields: dict, field_ts: dict | None = None) -> VehicleData:
    return map_dataset_to_vehicle_data(
        dict(fields), VehicleData(vin="X"), field_ts=field_ts
    )


def test_fresh_off_capture_beats_stale_charging_capture() -> None:
    # awood-ops: the stale 08:01 "charging" values sit on the canonical-first
    # aliases; the fresh 14:57 "off/not-ready" values sit on later aliases. The
    # newer capture must win, so the car reads not-charging and the plug is not
    # inferred from the (now-stale) IMMEDIATELY plan.
    fields = {
        _CS_CANON: "CHARGING_HV_BATTERY",
        _CS_LATER: "NOT_READY_FOR_CHARGING",
        _SCN_CANON: "CHARGING_SCENARIO_IMMEDIATELY_CHARGING_ACTIVE",
        _SCN_LATER: "CHARGING_SCENARIO_OFF",
    }
    ts = {
        _CS_CANON: 100.0,
        _CS_LATER: 200.0,
        _SCN_CANON: 100.0,
        _SCN_LATER: 200.0,
    }
    d = _map(fields, ts)
    assert d.is_charging is not True       # fresh NOT_READY wins -> not charging
    assert d.plug_connected is None        # fresh OFF -> no IMMEDIATELY lift


def test_fresh_disconnected_plug_beats_stale_connected() -> None:
    # The real plug field is resolved with first() too (gpt-oss completeness):
    # a car that ships the plug field under two disagreeing aliases must take the
    # newest. Stale "connected" on the canonical-first alias, fresh
    # "disconnected" on a later alias.
    fields = {_PLUG_CANON: "connected", _PLUG_LATER: "disconnected"}
    ts = {_PLUG_CANON: 100.0, _PLUG_LATER: 200.0}
    d = _map(fields, ts)
    assert d.plug_connected is False       # fresh "disconnected" wins


def test_equal_timestamps_keep_canonical_charging_state() -> None:
    # Regression guard: at equal capture time the canonical list order still
    # wins, identical to the old first() behaviour (common case unchanged).
    fields = {_CS_CANON: "CHARGING_HV_BATTERY", _CS_LATER: "NOT_READY_FOR_CHARGING"}
    ts = {_CS_CANON: 100.0, _CS_LATER: 100.0}
    d = _map(fields, ts)
    assert d.is_charging is True           # canonical CHARGING wins at equal ts


def test_no_timestamps_falls_back_to_list_order() -> None:
    # Without capture timestamps first_freshest falls back to first() exactly,
    # so the flat-dict tests elsewhere are unaffected.
    fields = {_CS_CANON: "CHARGING_HV_BATTERY", _CS_LATER: "NOT_READY_FOR_CHARGING"}
    d = _map(fields, None)
    assert d.is_charging is True           # first-present (canonical) wins
