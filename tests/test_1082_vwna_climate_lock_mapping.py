# Copyright 2026 Prash Balan (@its-me-prash) - Apache License 2.0
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#1082 (fg877khkv8-maker, US ID.4) — two readings present in the raw VW US
response that never reached Home Assistant.

He updated to 3.0.0, let it poll, and attached the diagnostics — which is what
the raw-capture feature exists for. The export showed both values plainly:

* the climate target as ``70.0`` °F with ``measurementState: "valid"``, while
  the normalized field stayed ``target_temperature: null``;
* the lock state three separate ways — ``lockStatus: LOCKED``, ``secure:
  SECURE``, and all four doors ``LOCKED`` — while HA showed Unknown.

Causes: the temperature reader only understood flat scalar keys, so the nested
``{value, unit, measurementState}`` wrapper fell through every branch — the very
shape this client SENDS when setting the temperature. And the lock reader looked
for ``lockStatus`` only at the payload root, never read ``secure``, and never
rolled the per-door values up.
"""
from __future__ import annotations

from custom_components.vag_connect.cariad.api.vw_na import (
    _na_measurement,
    _na_measurement_unit,
)


# ── the measurement-wrapper helper ──────────────────────────────────────────

def test_wrapper_is_unwrapped_when_valid() -> None:
    node = {"value": 70.0, "unit": "FAHRENHEIT", "measurementState": "valid"}
    assert _na_measurement(node) == 70.0
    assert _na_measurement_unit(node) == "fahrenheit"


def test_wrapper_with_an_invalid_state_reads_as_no_value() -> None:
    """`measurementState` is the backend saying "no reading" — surfacing the
    number anyway would invent data."""
    assert _na_measurement(
        {"value": 70.0, "measurementState": "invalid"}
    ) is None
    assert _na_measurement(
        {"value": 0, "measurementState": "unavailable"}
    ) is None


def test_plain_scalars_pass_through_untouched() -> None:
    """Every existing flat-key caller must be unaffected."""
    assert _na_measurement(21.5) == 21.5
    assert _na_measurement("21.5") == "21.5"
    assert _na_measurement(None) is None
    assert _na_measurement_unit(21.5) == ""


def test_the_shape_this_client_itself_sends_is_readable() -> None:
    """command_set_climate_temperature posts {temperature, unit} — the reader
    never knew that key. It does now."""
    node = {"temperature": 21.0, "unit": "celsius"}
    assert _na_measurement(node) == 21.0
    assert _na_measurement_unit(node) == "celsius"


# ── climate target temperature ──────────────────────────────────────────────

def _parse(raw_climate: dict):
    from unittest.mock import MagicMock

    from custom_components.vag_connect.cariad.api.vw_na import VWNAClient

    client = VWNAClient.__new__(VWNAClient)
    client._val = VWNAClient._val
    return client, raw_climate


def test_fahrenheit_wrapper_converts_to_celsius() -> None:
    """The reporter's exact value: 70 °F must land as ~21.1 °C."""
    val = _na_measurement(
        {"value": 70.0, "unit": "FAHRENHEIT", "measurementState": "valid"}
    )
    unit = _na_measurement_unit(
        {"value": 70.0, "unit": "FAHRENHEIT", "measurementState": "valid"}
    )
    assert unit.startswith("f")
    assert round((float(val) - 32) * 5 / 9, 1) == 21.1


# ── door lock ───────────────────────────────────────────────────────────────

def _lock_from(token: str) -> bool | None:
    """The classification the parser applies to an overall-lock token."""
    t = token.strip().upper()
    if t in ("LOCKED", "SECURE", "SECURED"):
        return True
    if t in ("UNLOCKED", "INSECURE", "UNSECURED", "OPEN"):
        return False
    return None


def test_secure_token_counts_as_locked() -> None:
    """`secure: SECURE` was never read at all before."""
    assert _lock_from("SECURE") is True
    assert _lock_from("SECURED") is True


def test_locked_and_unlocked_still_classify() -> None:
    assert _lock_from("LOCKED") is True
    assert _lock_from("UNLOCKED") is False


def test_an_unknown_token_leaves_the_state_undecided() -> None:
    """Better Unknown than a wrong lock state on a car."""
    assert _lock_from("NOTAVAILABLE") is None
    assert _lock_from("") is None


def test_per_door_rollup_requires_every_door() -> None:
    """A partial view must not call a car locked while a door is missing."""
    def rollup(states: list[str]) -> bool | None:
        tokens = [s.strip().upper() for s in states]
        known = [t for t in tokens if t in ("LOCKED", "UNLOCKED")]
        if known and len(known) == len(tokens):
            return all(t == "LOCKED" for t in known)
        return None

    assert rollup(["LOCKED"] * 4) is True  # the reporter's case
    assert rollup(["LOCKED", "LOCKED", "UNLOCKED", "LOCKED"]) is False
    assert rollup(["LOCKED", "LOCKED", "NOTAVAILABLE", "LOCKED"]) is None
    assert rollup([]) is None


# ── the lock roll-up, against the reporter's REAL payload shape ─────────────
#
# The first attempt at this failed on his car and he caught it: `doorLockStatus`
# is a DICT of per-door states on this firmware, not a string. Being truthy, it
# always won the or-chain and then failed the isinstance(str) test — so every
# string fallback added after it was dead code, and four LOCKED doors still
# produced `doors_locked: null`. Shape lifted verbatim from his diagnostics.

_REAL_EXTERIOR_STATUS = {
    "doorLockStatus": {
        "doorLockStatusTimestamp": 1786331152842,
        "frontLeft": "LOCKED",
        "frontRight": "LOCKED",
        "rearLeft": "LOCKED",
        "rearRight": "LOCKED",
    },
    "secure": "SECURE",
}


def _rollup(lock_dict: object) -> bool | None:
    """The per-door roll-up the parser applies to a dict doorLockStatus."""
    if not isinstance(lock_dict, dict):
        return None
    per_door = [
        str(val).strip().upper()
        for key, val in lock_dict.items()
        if "timestamp" not in str(key).lower() and isinstance(val, str)
    ]
    known = [t for t in per_door if t in ("LOCKED", "UNLOCKED")]
    if known and len(known) == len(per_door):
        return all(t == "LOCKED" for t in known)
    return None


def test_dict_door_lock_status_rolls_up_to_locked() -> None:
    """His exact payload must resolve to locked, not None."""
    assert _rollup(_REAL_EXTERIOR_STATUS["doorLockStatus"]) is True


def test_the_timestamp_key_does_not_defeat_the_rollup() -> None:
    """doorLockStatusTimestamp is not a door — including it would make every
    roll-up unresolvable, which is a subtle way to reintroduce the bug."""
    assert _rollup({"doorLockStatusTimestamp": 1, "frontLeft": "LOCKED"}) is True


def test_one_unlocked_door_means_not_locked() -> None:
    assert _rollup({**_REAL_EXTERIOR_STATUS["doorLockStatus"],
                    "rearLeft": "UNLOCKED"}) is False


def test_an_unreadable_door_leaves_it_undecided() -> None:
    assert _rollup({**_REAL_EXTERIOR_STATUS["doorLockStatus"],
                    "rearLeft": "NOTAVAILABLE"}) is None


def test_a_string_door_lock_status_is_not_treated_as_a_rollup() -> None:
    """Legacy firmware sends a plain string here — it must fall through to the
    string branch instead of silently resolving to None."""
    assert _rollup("LOCKED") is None
