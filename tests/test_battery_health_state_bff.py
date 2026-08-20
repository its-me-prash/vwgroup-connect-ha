# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""4.0.x — battery State-of-Health fetched from the BFF batteryHealthState sub-job.

We Connect 4.3.2 reads SoH via ``selectivestatus?jobs=batteryHealthState`` (RE
2026-08-12), separate from the main selectivestatus bundle. It is attestation-
walled (403) for VW EU passenger cars but served for Audi device-grant reads, so
``get_status`` now fetches it best-effort and maps ``stateOfHealth.ubeIndicator_pct``
onto ``battery_soh_pct``. The fetch mirrors the parkingposition/tripstatistics
best-effort pattern (a 403/404 never breaks the poll).
"""
from __future__ import annotations

from custom_components.vag_connect.cariad._authproxy import parse_battery_health


def test_parses_soh_from_bff_envelope() -> None:
    # The BFF wraps the job under stateOfHealth.value; parse_battery_health walks
    # for ubeIndicator_pct regardless of the exact nesting.
    body = {
        "batteryHealthState": {
            "stateOfHealth": {
                "value": {
                    "ubeIndicator_pct": 87,
                    "usableBatteryCapacity": 52.0,
                    "carCapturedTimestamp": "2026-08-20T06:00:00Z",
                },
            },
        },
    }
    assert parse_battery_health(body) == 87.0


def test_parses_soh_when_flatter() -> None:
    assert parse_battery_health({"stateOfHealth": {"ubeIndicator_pct": 91.4}}) == 91.4


def test_rejects_missing_or_implausible() -> None:
    assert parse_battery_health({}) is None
    assert parse_battery_health({"stateOfHealth": {"value": {}}}) is None
    assert parse_battery_health({"ubeIndicator_pct": 0}) is None      # 0 is not plausible
    assert parse_battery_health({"ubeIndicator_pct": 150}) is None    # >100
    assert parse_battery_health({"ubeIndicator_pct": True}) is None   # bool guard


def test_int_round_matches_get_status_mapping() -> None:
    # get_status stores int(round(_soh)) into battery_soh_pct.
    assert int(round(parse_battery_health({"ubeIndicator_pct": 87.6}))) == 88
