# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""v2.15.9 (#589) — charge-mode select localisation.

Reported by @ColinSainsbury: ``select.<car>_charging_mode`` showed German
option strings ("Manuell", "Bevorzugte Ladezeiten", …) to a UK user because
the entity baked German labels straight into ``options`` — HA can only
localise *canonical keys*, not human strings.

These tests pin the contract of the fix:
  1. ``_attr_options`` are canonical snake_case keys (NOT raw German).
  2. Every canonical option key has a ``state`` translation in strings.json
     and in all 8 shipped locales (parity).
  3. Raw API values from BOTH data-plane dialects (VW-EU uppercase enum +
     SEAT/CUPRA lowercase camelCase) normalise to the same canonical key.
  4. canonical key -> API write token round-trips back to the exact
     uppercase token the backend accepted before #589 (no SEAT/CUPRA break).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("homeassistant")
pytestmark = pytest.mark.ha_required

from custom_components.vag_connect.select import (  # noqa: E402
    _CANONICAL_TO_API,
    _CHARGE_MODE_OPTIONS,
    _normalise_raw_mode,
)

_COMP = Path(__file__).resolve().parent.parent / "custom_components" / "vag_connect"
_LOCALES = ("en", "de", "fr", "es", "nl", "pl", "cs", "sv")


def test_options_are_canonical_keys_not_german() -> None:
    """options must be stable snake_case keys, never raw German labels."""
    assert _CHARGE_MODE_OPTIONS == [
        "manual",
        "timer",
        "preferred_charging_times",
        "only_own_current",
        "immediate_discharging",
        "timer_charging_climatization",
    ]
    # Guard against the #589 regression: no human German label leaks in.
    for german in ("Manuell", "Bevorzugte Ladezeiten", "Nur Eigenstrom", "Sofort entladen"):
        assert german not in _CHARGE_MODE_OPTIONS


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        # VW-EU BFF uppercase enum
        ("MANUAL", "manual"),
        ("TIMER", "timer"),
        ("PREFERRED_CHARGING_TIMES", "preferred_charging_times"),
        ("ONLY_OWN_CURRENT", "only_own_current"),
        ("IMMEDIATE_DISCHARGING", "immediate_discharging"),
        ("TIMER_CHARGING_WITH_CLIMATISATION", "timer_charging_climatization"),
        # SEAT/CUPRA OLA lowercase camelCase
        ("manual", "manual"),
        ("timer", "timer"),
        ("preferredChargingTimes", "preferred_charging_times"),
        ("automaticUnlocked", "only_own_current"),
        ("timerChargingWithClimatisation", "timer_charging_climatization"),
    ],
)
def test_raw_normalises_to_canonical(raw: str, expected: str) -> None:
    """Both data-plane dialects resolve to the same canonical option key."""
    assert _normalise_raw_mode(raw) == expected


@pytest.mark.parametrize("bad", [None, "", "   ", "somethingUnknown"])
def test_unknown_raw_returns_none(bad: object) -> None:
    """Unknown/empty raw values yield None (never leak a raw string)."""
    assert _normalise_raw_mode(bad) is None


def test_write_token_roundtrips_to_backend_enum() -> None:
    """canonical key -> API token -> .upper() == the enum the backend expects.

    ``command_set_charge_mode`` upper-cases the token before POSTing
    ``{"chargeMode": token.upper()}``. These are the exact strings the API
    accepted before #589, so SEAT/CUPRA (which inherit the VW-EU command)
    keep working.
    """
    expected_backend = {
        "manual": "MANUAL",
        "timer": "TIMER",
        "preferred_charging_times": "PREFERRED_CHARGING_TIMES",
        "only_own_current": "ONLY_OWN_CURRENT",
        "immediate_discharging": "IMMEDIATE_DISCHARGING",
        "timer_charging_climatization": "TIMER_CHARGING_WITH_CLIMATISATION",
    }
    for key in _CHARGE_MODE_OPTIONS:
        assert key in _CANONICAL_TO_API, f"{key} missing API token"
        assert _CANONICAL_TO_API[key].upper() == expected_backend[key]


def test_full_roundtrip_raw_to_canonical_to_backend() -> None:
    """A raw API value read back normalises, then re-writes to the same enum."""
    # e.g. CUPRA sends "preferredChargingTimes" on read; a user re-selecting
    # that option must POST "PREFERRED_CHARGING_TIMES".
    canonical = _normalise_raw_mode("preferredChargingTimes")
    assert canonical == "preferred_charging_times"
    assert _CANONICAL_TO_API[canonical].upper() == "PREFERRED_CHARGING_TIMES"


def _state_map(locale_path: Path) -> dict[str, str]:
    data = json.loads(locale_path.read_text(encoding="utf-8"))
    return data["entity"]["select"]["charge_mode_select"]["state"]


def test_strings_json_has_all_state_translations() -> None:
    states = _state_map(_COMP / "strings.json")
    assert set(states) == set(_CHARGE_MODE_OPTIONS)


def test_eight_locale_state_parity() -> None:
    """Every locale ships a state label for every canonical option key."""
    for loc in _LOCALES:
        states = _state_map(_COMP / "translations" / f"{loc}.json")
        assert set(states) == set(_CHARGE_MODE_OPTIONS), f"{loc} missing keys"
        for key in _CHARGE_MODE_OPTIONS:
            assert states[key].strip(), f"{loc}.{key} empty"


def test_german_labels_preserved() -> None:
    """DE keeps the original human strings that #589 reported."""
    de = _state_map(_COMP / "translations" / "de.json")
    assert de["manual"] == "Manuell"
    assert de["preferred_charging_times"] == "Bevorzugte Ladezeiten"
    assert de["only_own_current"] == "Nur Eigenstrom"
    assert de["immediate_discharging"] == "Sofort entladen"
