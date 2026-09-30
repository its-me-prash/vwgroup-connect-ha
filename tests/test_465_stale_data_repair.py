# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#465 (@TomJonesGreggs) — capture-age staleness detection.

On a frozen-but-non-empty EU Data Act feed the poll keeps succeeding
(``last_updated_at`` stays fresh) while the car's own capture time
(``last_seen_at``) is days old. ``_capture_age_s`` measures that age across the
heterogeneous ``last_seen_at`` typing (datetime / ISO-string / None), and a per-VIN
WARNING repair flags it past a generous floor, auto-clearing when data refreshes.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from custom_components.vag_connect.coordinator import _capture_age_s
from custom_components.vag_connect import repairs


def test_capture_age_from_aware_and_naive_datetime() -> None:
    now = datetime.now(tz=timezone.utc)
    assert abs(_capture_age_s({"last_seen_at": now - timedelta(hours=5)}) - 5 * 3600) < 5
    naive = (now - timedelta(hours=2)).replace(tzinfo=None)   # treated as UTC
    assert abs(_capture_age_s({"last_seen_at": naive}) - 2 * 3600) < 5


def test_capture_age_from_iso_string_the_euda_channel_shape() -> None:
    now = datetime.now(tz=timezone.utc)
    iso_z = (now - timedelta(hours=48)).strftime("%Y-%m-%dT%H:%M:%SZ")
    age = _capture_age_s({"last_seen_at": iso_z})
    assert abs(age - 48 * 3600) < 60


def test_capture_age_none_when_absent_or_untyped() -> None:
    assert _capture_age_s({}) is None
    assert _capture_age_s({"last_seen_at": None}) is None
    assert _capture_age_s({"last_seen_at": 12345}) is None      # not datetime/str
    assert _capture_age_s({"last_seen_at": "not-a-date"}) is None


def test_future_capture_time_yields_negative_age_no_false_alarm() -> None:
    future = datetime.now(tz=timezone.utc) + timedelta(hours=3)
    assert _capture_age_s({"last_seen_at": future}) < 0


def test_min_age_floor_is_well_past_a_parked_car_heartbeat() -> None:
    # 72h — a parked/asleep car legitimately goes ~24h between captures.
    assert repairs.STALE_DATA_MIN_AGE_S == 72 * 3600


def test_repair_issue_id_is_per_vin() -> None:
    # #1626 — the id is keyed per VIN (so a multi-car account isolates the stale
    # one) but on the MASKED VIN, never the raw one: the id is dumped verbatim in a
    # diagnostics download and a full VIN there is a leak. Deliberate change from
    # the pre-fix raw-VIN id.
    hass = MagicMock()
    vin = "WVWZZZAUZ1234567"
    masked = repairs.mask_vin(vin)
    with patch.object(repairs.ir, "async_create_issue") as create, \
            patch.object(repairs.ir, "async_delete_issue") as rdelete:
        repairs.raise_issue_stale_data(
            hass, "entryX", vin, masked_vin="…4567", age_hours=80,
        )
    kwargs = create.call_args.kwargs
    assert create.call_args.args[2] == f"entryX_stale_data_{masked}"
    assert vin not in create.call_args.args[2]  # never the raw VIN
    assert kwargs["translation_key"] == "stale_data"
    assert kwargs["translation_placeholders"] == {"vin": "…4567", "age": "80"}
    assert kwargs["severity"] == repairs.ir.IssueSeverity.WARNING
    # raise clears the legacy raw-VIN id so a pre-fix repair does not linger
    assert f"entryX_stale_data_{vin}" in [c.args[2] for c in rdelete.call_args_list]

    with patch.object(repairs.ir, "async_delete_issue") as delete:
        repairs.clear_stale_data_issue(hass, "entryX", vin)
    _deleted = [c.args[2] for c in delete.call_args_list]
    assert f"entryX_stale_data_{masked}" in _deleted  # matches the raised id
    assert f"entryX_stale_data_{vin}" in _deleted      # + legacy cleanup
