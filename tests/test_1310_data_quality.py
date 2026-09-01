# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#1310 (indigomejor) — three Škoda data-quality fixes from his v4.5.0 findings.

1. The account-level "latest fill-up" (no VIN) bled an old session from a previous
   car onto a brand-new one — a 2024 fill-up on a 2026 car. Suppress an implausibly
   old (>1 year) latest fill-up.
2. Service reminders the owner never configured came back as the raw sentinel
   "NOT_SET" — a truthy string automations mistake for a real reading. Drop it.
3. Fields that come and go with a richer/leaner payload but don't actually change
   (equipment count, the last fill-up) flapped to "unknown"; carry them forward.
"""
from __future__ import annotations

from datetime import datetime, timezone

from custom_components.vag_connect.cariad.vehicle_cache import (
    CARRY_FORWARD_FIELDS,
    reconcile,
)
from custom_components.vag_connect.coordinator import (
    _parse_fueling,
    _parse_predictive_maintenance,
)

NOW = datetime(2026, 9, 1, tzinfo=timezone.utc)


# ── 1. fill-up staleness ────────────────────────────────────────────────────

def test_recent_fueling_is_parsed() -> None:
    out = _parse_fueling(
        {"dateTime": "2026-08-29T10:00:00Z", "gasStation": {"name": "Tank ONO"}},
        now=NOW,
    )
    assert out["last_refuel_at"] == "2026-08-29T10:00:00Z"
    assert out["last_refuel_station"] == "Tank ONO"


def test_stale_account_fueling_is_suppressed() -> None:
    # indigomejor's exact case: a 2024 session on a car delivered 2026 → >1yr → drop
    out = _parse_fueling(
        {"dateTime": "2024-10-25T14:49:40Z", "gasStation": {"name": "OMV"},
         "fuelName": "Diesel"},
        now=NOW,
    )
    assert out == {}


def test_fueling_under_a_year_is_kept() -> None:
    out = _parse_fueling({"dateTime": "2025-11-01T00:00:00Z"}, now=NOW)
    assert out.get("last_refuel_at") == "2025-11-01T00:00:00Z"


def test_fueling_unparseable_date_is_not_suppressed() -> None:
    # no age signal → keep what we got rather than guess
    out = _parse_fueling({"dateTime": "garbage", "quantity": 40.0}, now=NOW)
    assert out["last_refuel_at"] == "garbage"
    assert out["last_refuel_quantity"] == 40.0


# ── 2. NOT_SET reminder sentinel ────────────────────────────────────────────

def test_not_set_reminder_is_dropped() -> None:
    assert _parse_predictive_maintenance(
        {"reminders": [{"type": "FIRST_AID_KIT", "status": "NOT_SET"}]}
    ) == {}


def test_real_reminder_status_is_kept() -> None:
    assert _parse_predictive_maintenance(
        {"reminders": [{"type": "TECHNICAL_INSPECTION", "status": "DUE"}]}
    ) == {"reminder_technical_inspection": "DUE"}


def test_reminder_due_date_is_kept() -> None:
    assert _parse_predictive_maintenance(
        {"reminders": [{"type": "TYRE_REPAIR_KIT", "dueDate": "2027-01-01"}]}
    ) == {"reminder_tyre_repair_kit": "2027-01-01"}


def test_not_set_dropped_but_real_ones_kept() -> None:
    out = _parse_predictive_maintenance({"reminders": [
        {"type": "FIRST_AID_KIT", "status": "NOT_SET"},
        {"type": "TECHNICAL_INSPECTION", "dueDate": "2027-03-01"},
    ]})
    assert out == {"reminder_technical_inspection": "2027-03-01"}


# ── 3. carry-forward ────────────────────────────────────────────────────────

def test_equipment_count_is_carried_forward_but_not_fill_up() -> None:
    # equipment_count is stable → carry forward. The last-fill-up fields are NOT:
    # carrying them would resurrect a session that staleness-suppression dropped.
    assert "equipment_count" in CARRY_FORWARD_FIELDS
    assert "last_refuel_at" not in CARRY_FORWARD_FIELDS
    assert "last_refuel_station" not in CARRY_FORWARD_FIELDS


def test_reconcile_holds_equipment_count_but_not_fill_up() -> None:
    prev = {"equipment_count": 9, "last_refuel_at": "2026-08-29T10:00:00Z"}
    fresh = {"battery_soc": 80}  # this poll omitted both
    out, _disc = reconcile(prev, fresh)
    assert out["equipment_count"] == 9  # held, not blanked to unknown
    # the fill-up is NOT resurrected — carry-forward must not defeat staleness
    assert out.get("last_refuel_at") is None
