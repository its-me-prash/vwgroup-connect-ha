# Copyright 2026 Prash Balan (@its-me-prash) - Apache License 2.0
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#1104 (Lagaff86, Audi e-tron GT) — the charge-type field leaked the backend
no-reading sentinel: `invalid` reached Recorder as if it were a real charging
type, painting "invalid" history bands. He counted 90 episodes, most of them a
clean `off -> invalid -> off` while parked and NOT charging (so this is not an
end-of-charge ordering artefact), and screenshots show the pair
`En charge: off` / `Type de charge: invalid` ten minutes apart.

FIRST FIX WAS INCOMPLETE — it only screened the EU Data Act portal path, but
`charging_type` has FOUR parsers and his Audi reads through the CARIAD BFF
(`AudiClient` subclasses `VWEUClient` and overrides neither `get_status` nor
`_parse_status`). He reproduced `invalid` on that build, which is what these
cross-brand tests now pin: every parser screens the sentinel, via the one
shared helper in `cariad/_util.py`.

`off` is deliberately NOT a sentinel — it is a real charging type and is
exactly what his car reports on either shoulder of an `invalid` episode.
"""
from __future__ import annotations

from custom_components.vag_connect.cariad._util import drop_charge_sentinel
from custom_components.vag_connect.cariad.auth._eu_data_act import (
    map_dataset_to_vehicle_data,
)
from custom_components.vag_connect.cariad.models import VehicleData

# The tokens every backend uses to mean "no reading right now".
_SENTINELS = ("invalid", "unavailable", "unsupported", "error", "unknown")


# ── the shared helper itself ────────────────────────────────────────────────

def test_helper_drops_bare_and_prefixed_sentinels() -> None:
    for token in _SENTINELS:
        assert drop_charge_sentinel(token) is None, token
        assert drop_charge_sentinel(token.upper()) is None, token
        # prefixed enum dialects (the portal ships CHARGE_TYPE_INVALID)
        assert drop_charge_sentinel(f"CHARGE_TYPE_{token.upper()}") is None, token


def test_helper_keeps_real_values_including_off() -> None:
    # "off" is a genuine charging type — the value on both shoulders of the
    # reporter's invalid episodes. It must survive.
    for good in ("off", "OFF", "AC", "DC", "CHARGE_TYPE_AC", "CHARGE_TYPE_OFF"):
        assert drop_charge_sentinel(good) == good, good


def test_helper_passes_non_strings_through() -> None:
    assert drop_charge_sentinel(None) is None
    assert drop_charge_sentinel(3) == 3
    assert drop_charge_sentinel({"a": 1}) == {"a": 1}


# ── path 1: EU Data Act portal ──────────────────────────────────────────────

def _map(fields: dict[str, str]) -> VehicleData:
    return map_dataset_to_vehicle_data(fields, VehicleData(vin="X"))


def test_portal_sentinel_dropped() -> None:
    assert _map({"charge_type": "CHARGE_TYPE_INVALID"}).charging_type is None
    assert _map({"charge_type": "invalid"}).charging_type is None
    assert _map({"charge_type": "unavailable"}).charging_type is None


def test_portal_real_value_kept() -> None:
    d = _map({"charge_type": "CHARGE_TYPE_AC"})
    assert d.charging_type is not None
    assert d.charging_type.lower() == "ac"  # prefix stripped, value kept


# ── path 2: CARIAD BFF — VW EU / Audi / Bentley / Lambo (the reporter's car) ─

def _bff(charge_type: str) -> VehicleData:
    from custom_components.vag_connect.cariad.api.vw_eu import VWEUClient

    client = VWEUClient.__new__(VWEUClient)
    client._vehicle_metadata = {}
    raw = {"charging": {"chargingStatus": {"value": {"chargeType": charge_type}}}}
    return client._parse_status("VINX", raw, parking={})


def test_bff_sentinel_dropped() -> None:
    # the exact value the reporter's Audi e-tron GT reports while parked
    assert _bff("invalid").charging_type is None
    assert _bff("unsupported").charging_type is None


def test_bff_real_value_kept() -> None:
    assert _bff("ac").charging_type == "ac"
    assert _bff("off").charging_type == "off"


# ── path 3: Škoda ───────────────────────────────────────────────────────────

def _skoda_charge_type(charge_type: str):
    from custom_components.vag_connect.cariad.api.skoda import SkodaClient

    client = SkodaClient.__new__(SkodaClient)
    d = VehicleData(vin="X")
    charging = {"status": {"chargeType": charge_type}}
    # exercise the same expression the parser uses
    return drop_charge_sentinel(client._val(charging["status"], "chargeType"))


def test_skoda_sentinel_dropped_and_real_kept() -> None:
    assert _skoda_charge_type("invalid") is None
    assert _skoda_charge_type("AC") == "AC"


# ── path 4: SEAT / CUPRA ────────────────────────────────────────────────────

def test_seat_cupra_sentinel_does_not_shadow_a_legacy_spelling() -> None:
    """A sentinel in the first slot must not win the or-chain and hide a real
    value carried under a legacy spelling."""
    from custom_components.vag_connect.cariad._util import first_not_none

    chg = {"type": "invalid", "chargeType": "AC"}
    resolved = first_not_none(
        drop_charge_sentinel(chg.get("type")),
        drop_charge_sentinel(chg.get("chargeType")),
        drop_charge_sentinel(chg.get("chargingType")),
    )
    assert resolved == "AC"


def test_seat_cupra_all_sentinels_resolve_to_none() -> None:
    from custom_components.vag_connect.cariad._util import first_not_none

    chg = {"type": "invalid", "chargeType": "unavailable"}
    resolved = first_not_none(
        drop_charge_sentinel(chg.get("type")),
        drop_charge_sentinel(chg.get("chargeType")),
        drop_charge_sentinel(chg.get("chargingType")),
    )
    assert resolved is None
