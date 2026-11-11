# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#2059/#2061/#2062/#2063/#2065/#2070 — Skoda moved the plug fields onto the
charging endpoint, and the Scout kept re-filing them as new on every car.

skoda.py has read ``status.plugConnectionState`` / ``plugLockState`` /
``chargingErrorReason`` since 32392abb (→ ``plug_state`` / ``plug_lock_state`` /
``charging_error_code``, with sensors), but ``EXPECTED_KEYS`` lagged the parser —
the "silencer-lag-behind-parser" pattern this file keeps catching — so the Scout
flagged them regardless. They are now registered, so the six duplicate issues
stop re-opening while the data stays surfaced.
"""
from __future__ import annotations

from custom_components.vag_connect.cariad._unexpected_keys import detect_unexpected


def test_skoda_plug_and_charging_error_fields_are_not_flagged() -> None:
    payload = {
        "status": {
            "plugConnectionState": "DISCONNECTED",
            "plugLockState": "UNLOCKED",
            "chargingErrorReason": "ERROR_CHARGING_SYSTEM",
        }
    }
    flagged = [f.path for f in detect_unexpected("skoda", "charging", payload)]
    assert flagged == [], f"expected plug/charging-error fields silenced, got {flagged}"


def test_a_genuinely_new_charging_status_field_is_still_flagged() -> None:
    """Targeted silence — an unrelated new child must still surface for the Scout."""
    payload = {"status": {"somethingBrandNew": 1}}
    flagged = [f.path for f in detect_unexpected("skoda", "charging", payload)]
    assert any("somethingBrandNew" in p for p in flagged)
