# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#1218 (Lagaff86) — the EU Data Act freshness age was anchored to a capture
timestamp picked by field-NAME preference (``car_captured_utc_timestamp`` first),
not by which capture instant is actually the newest in the packet. VW's export
mixes subreports from different capture times, so a fresh ``car_captured_time``
could sit next to a much older ``car_captured_utc_timestamp``; the name-preference
pick latched the stale one and reported the feed ~91 h old while same-day captures
were present.

The fix anchors ``last_seen_at`` on the FRESHEST capture value present, order- and
name-independent (same log-reordering quirk family as the #465 SoC work).
"""
from __future__ import annotations

from custom_components.vag_connect.cariad.auth._eu_data_act import (
    map_dataset_to_vehicle_data,
    _walk_fields,
)
from custom_components.vag_connect.cariad.models import VehicleData

# Lagaff86's shape: a fresh same-day capture next to a multi-day-old UTC marker.
_FRESH = ("car_captured_time", "2026-08-17T16:10:45+02:00")   # 14:10:45Z
_STALE_UTC = ("car_captured_utc_timestamp", "2026-08-14T05:56:00Z")


def _flat(pairs: list[tuple[str, str]]) -> dict:
    return {"data": [{"dataFieldName": n, "value": v} for n, v in pairs]}


def _last_seen(pairs: list[tuple[str, str]]) -> str | None:
    field_ts: dict = {}
    fields = _walk_fields(_flat(pairs), field_ts)
    d = map_dataset_to_vehicle_data(fields, VehicleData(vin="X"), field_ts)
    return d.last_seen_at


def test_fresh_capture_wins_over_stale_utc_marker() -> None:
    """The core #1218 case: fresh car_captured_time must anchor last_seen, not the
    older car_captured_utc_timestamp that merely sorts first by name."""
    ls = _last_seen([_STALE_UTC, _FRESH])
    assert ls is not None and ls.startswith("2026-08-17"), ls


def test_order_independent_fresh_still_wins() -> None:
    """Whatever order VW ships the two markers in, freshness (not array/name
    order) decides — the permutation invariant."""
    for order in ([_STALE_UTC, _FRESH], [_FRESH, _STALE_UTC]):
        ls = _last_seen(order)
        assert ls is not None and ls.startswith("2026-08-17"), order


def test_single_utc_marker_still_used() -> None:
    """No regression: with only the UTC marker present it is still the anchor."""
    ls = _last_seen([_STALE_UTC])
    assert ls is not None and ls.startswith("2026-08-14"), ls


def test_single_fresh_marker_used() -> None:
    """With only car_captured_time present it is the anchor (unchanged)."""
    ls = _last_seen([_FRESH])
    assert ls is not None and ls.startswith("2026-08-17"), ls


def test_agreeing_markers_resolve_to_that_instant() -> None:
    """Both markers on the same instant → that instant (the normal, non-mixed
    packet), identical to the old behaviour."""
    same = "2026-08-17T14:10:45Z"
    ls = _last_seen([("car_captured_utc_timestamp", same), ("car_captured_time", same)])
    assert ls is not None and ls.startswith("2026-08-17T14:10:45"), ls
