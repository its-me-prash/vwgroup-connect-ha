# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#1881 — the climate capture stamps must not change the stale verdict.

``_capture_age_s`` takes the NEWEST entry of ``field_captured_ts``. The climate
state and reason now record a stamp for diagnostics; if those entries counted,
a car whose odometer is 82 h old but whose climate state is 1 h old would stop
reading as stale. The stamps stay in the map, the age verdict ignores them.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from custom_components.vag_connect.coordinator import _capture_age_s

H = 3600.0


def _ago(hours: float) -> str:
    return (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()


def _near(actual: float | None, expected_hours: float, tol_h: float = 0.3) -> bool:
    return actual is not None and abs(actual - expected_hours * H) < tol_h * H


def test_a_fresh_climate_stamp_does_not_rejuvenate_an_old_feed() -> None:
    base = {"source_channel": "eu_data_act", "last_seen_at": _ago(82)}
    without = _capture_age_s({**base, "field_captured_ts": {"odometer_km": _ago(82)}})
    with_climate = _capture_age_s({
        **base,
        "field_captured_ts": {
            "odometer_km": _ago(82),
            "climatisation_state": _ago(1),
            "climatisation_reason": _ago(1),
        },
    })
    assert _near(without, 82)
    assert _near(with_climate, 82)
    assert with_climate is not None and without is not None
    assert abs(with_climate - without) < 60  # the same verdict, to the minute


def test_a_map_with_only_climate_stamps_falls_through_to_last_seen_at() -> None:
    age = _capture_age_s({
        "last_seen_at": _ago(30),
        "field_captured_ts": {"climatisation_state": _ago(1)},
    })
    assert _near(age, 30)


def test_other_stamps_still_count() -> None:
    age = _capture_age_s({
        "source_channel": "eu_data_act",
        "last_seen_at": _ago(2),
        "field_captured_ts": {"odometer_km": _ago(5), "climatisation_state": _ago(1)},
    })
    assert _near(age, 5)
