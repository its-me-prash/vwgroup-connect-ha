# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#1990 — Škoda started shipping the plug fields on the CHARGING endpoint.

Seventeen Scout reports were filed between 12:44 and 15:12 on 2026-11-05, #1990
through #2006 without a gap. Fifteen were still open and their bodies were read;
the two the reporters had already closed themselves (#1995, #1998) were not, so
every count below is over the fifteen that were read. One owner filed the same
observation twice, three minutes apart, both bodies carrying the identical
``Reported at``. What they report: ``status.plugConnectionState``,
``status.plugLockState`` and — in one body — ``status.chargingErrorReason``,
arriving with no reader on that endpoint, so the Scout called them unmapped.

Nothing was broken. This parser reads the plug off the AIR-CONDITIONING endpoint
under Škoda's own names (``chargerConnectionState`` / ``chargerLockState``) and
has since 2026-04-26; the backend simply began offering the CARIAD spelling on
the charging endpoint as well. (``skoda_official.py`` has read these same two
field names since #1286 — what had no reader was the mysmob charging endpoint,
not the field names as such.)

**The raw token is passed through and NOT folded into a boolean.** That is the
#1286 decision for these two exact field names: the official spec declares both
as plain strings with no enum, so the allowed values are not specified, and
``skoda_official.py`` deliberately hands the token to the entity layer instead
of interpreting it. Deriving ``plug_connected`` from "CONNECTED" here would be
inventing that mapping, so the tests below pin the absence of the boolean just
as firmly as the presence of the string. The fifteen bodies that were read do
not settle the vocabulary: across them each field shows exactly two values
(CONNECTED/DISCONNECTED 7:8, LOCKED/UNLOCKED 4:11), and two values seen is not
the same fact as two values existing.

The chain was measured end to end rather than assumed, because a token that
misses by case costs the whole sensor (#1739): ``plug_state`` is an ENUM with
options ``["connected", "disconnected"]``, ``normalize_enum_states`` folds with
``.strip().lower()``, and it runs on both paths that reach the entities — the
poll and the cache restore. So "CONNECTED" lands as ``connected`` instead of
being folded away. ``plug_lock_state`` and ``charging_error_code`` declare no
options, so nothing folds them and their raw token passes through as-is.

That paragraph records how the chain was checked, not what this file asserts:
the tests below drive ``SkodaClient.get_status`` and assert on ``VehicleData``,
and the fold itself is guarded by
``tests/test_1739_enum_states_normalised_on_every_path.py``. Also worth knowing
for a reader of the entity list: all three sensors already existed, so this adds
no entity — ``plug_state`` and ``charging_error_code`` are enabled by default
and ``plug_lock_state`` is not.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

from custom_components.vag_connect.cariad.api.skoda import SkodaClient
from custom_components.vag_connect.cariad.models import VehicleData

#: The project's documented synthetic placeholder — never a real VIN.
_VIN = "WVWZZZAUZFW000000"


def _run(charging_status: dict, ac: dict | None = None) -> VehicleData:
    """Drive get_status with a payload instead of inspecting its source.

    A source-level assertion would pass on code that reads the right key into
    the wrong field, which is exactly the mistake this change nearly made.
    """
    c = SkodaClient(MagicMock(), "u@t.de", "pw")
    c._powertrain = {}
    c._official_mode = "mysmob_only"
    c._eu_portal = None

    async def fake_get(url: str, *a: object, **k: object) -> dict:
        if "/api/v1/charging/" in url:
            return {"status": charging_status}
        if "/air-conditioning/" in url:
            return ac or {}
        return {}

    c._get = AsyncMock(side_effect=fake_get)  # type: ignore[method-assign]
    return asyncio.run(c.get_status(_VIN))


# ── the three fields reach the model, raw ───────────────────────────────────

def test_connection_state_reaches_the_model_raw() -> None:
    d = _run({"plugConnectionState": "CONNECTED"})
    assert d.plug_state == "CONNECTED"


def test_lock_state_reaches_the_model_raw() -> None:
    d = _run({"plugLockState": "UNLOCKED"})
    assert d.plug_lock_state == "UNLOCKED"


def test_error_reason_reaches_the_model_raw() -> None:
    d = _run({"chargingErrorReason": "ERROR_CHARGING_SYSTEM"})
    assert d.charging_error_code == "ERROR_CHARGING_SYSTEM"


def test_an_unknown_dialect_survives_unchanged() -> None:
    # No enum is declared, so a prefixed dialect is not ours to normalise.
    d = _run({"plugConnectionState": "PLUG_CONNECTION_STATE_CONNECTED"})
    assert d.plug_state == "PLUG_CONNECTION_STATE_CONNECTED"


# ── and are NOT folded into booleans (the #1286 decision) ───────────────────

def test_no_boolean_is_invented_from_the_charging_endpoint() -> None:
    d = _run({"plugConnectionState": "CONNECTED", "plugLockState": "LOCKED"})
    assert d.plug_state == "CONNECTED"
    assert d.plug_lock_state == "LOCKED"
    # The point of the test: a reader of "CONNECTED"/"LOCKED" would find it
    # obvious to set these two. The spec declares no enum, so we do not.
    assert d.plug_connected is None, "a boolean was invented from an unspecified vocabulary"
    assert d.connector_locked is None, "a boolean was invented from an unspecified vocabulary"


def test_the_air_conditioning_source_still_decides_plug_connected() -> None:
    """Non-regression: the ac block keeps its vocabulary and its precedence.

    It runs after the charging block in get_status, so a car that reads
    correctly today cannot be changed by this addition.
    """
    d = _run(
        {"plugConnectionState": "DISCONNECTED"},
        ac={"chargerConnectionState": "CONNECTED", "chargerLockState": "LOCKED"},
    )
    assert d.plug_connected is True
    assert d.connector_locked is True
    # The ac block also owns plug_state, and wins it by position.
    assert d.plug_state == "CONNECTED"


# ── rejections ──────────────────────────────────────────────────────────────

def test_sentinels_are_dropped() -> None:
    for token in ("invalid", "unavailable", "unknown", "PLUG_CONNECTION_STATE_INVALID"):
        d = _run({"plugConnectionState": token, "plugLockState": token})
        assert d.plug_state is None, token
        assert d.plug_lock_state is None, token


def test_blank_and_non_string_are_rejected() -> None:
    d = _run({"plugConnectionState": "   ", "plugLockState": ""})
    assert d.plug_state is None
    assert d.plug_lock_state is None
    d = _run({"plugConnectionState": 1, "plugLockState": {"a": 1}, "chargingErrorReason": []})
    assert d.plug_state is None
    assert d.plug_lock_state is None
    assert d.charging_error_code is None


def test_absent_fields_leave_everything_unset() -> None:
    """Positive control. Without this, every assertion above could be passing
    on a parser that never reads the keys at all.
    """
    d = _run({"state": "CHARGING"})
    assert d.plug_state is None
    assert d.plug_lock_state is None
    assert d.charging_error_code is None
    # and the payload we did send was understood, so the harness works
    assert d.charging_state == "CHARGING"
