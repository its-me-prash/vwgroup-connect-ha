# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""v2.13.0 (#446 + #448) — 4-segment chargingTimers/chargingProfiles silencer.

The Audi selectivestatus backend started nesting these one level deeper than
v2.12.1 covered: e.g. ``chargingTimers.chargingTimersStatus.value.timers``
(4 segments). The equal-depth wildcard matcher needs a 4-deep pattern; this
pins that the Scout no longer flags them.
"""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

import pytest

_CAR = Path(__file__).resolve().parent.parent / "custom_components" / "vag_connect" / "cariad"


def _load_uk():
    def fake(name, path):
        m = types.ModuleType(name)
        m.__path__ = [str(path)]
        sys.modules[name] = m

    fake("_uk2130", _CAR.parent.parent)
    fake("_uk2130.vag_connect", _CAR.parent)
    fake("_uk2130.vag_connect.cariad", _CAR)

    def load(n, f):
        spec = importlib.util.spec_from_file_location(n, f)
        mod = importlib.util.module_from_spec(spec)
        sys.modules[n] = mod
        spec.loader.exec_module(mod)
        return mod

    load("_uk2130.vag_connect.cariad._util", _CAR / "_util.py")
    return load("_uk2130.vag_connect.cariad._unexpected_keys", _CAR / "_unexpected_keys.py")


_SCOUT_PATHS = [
    "chargingTimers.chargingTimersStatus.value.carCapturedTimestamp",
    "chargingTimers.chargingTimersStatus.value.timeInCar",
    "chargingTimers.chargingTimersStatus.value.timers",
    "chargingProfiles.chargingProfilesStatus.value.carCapturedTimestamp",
    "chargingProfiles.chargingProfilesStatus.value.timeInCar",
    "chargingProfiles.chargingProfilesStatus.value.nextChargingTimer",
    "chargingProfiles.chargingProfilesStatus.value.profiles",
]


@pytest.mark.parametrize("path", _SCOUT_PATHS)
def test_4segment_charging_paths_silenced_audi(path: str) -> None:
    uk = _load_uk()
    expected = uk.EXPECTED_KEYS["audi"]["selectivestatus"]
    assert uk._path_matches(path, expected), f"Scout still flags {path}"


def test_audi_inherits_volkswagen_selectivestatus() -> None:
    uk = _load_uk()
    assert uk.EXPECTED_KEYS["audi"] is uk.EXPECTED_KEYS["volkswagen"]
