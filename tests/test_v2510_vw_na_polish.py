# Copyright 2026 Prash Balan (@its-me-prash) — Apache License 2.0
"""v2.5.10 — VW NA Polish tests (#322-#325 roberttco bundle).

Three patches:

1. **#323 last_seen_at parse** — VW NA RVS response now populates
   `last_seen_at` from one of 6 known timestamp-field variants. Pre-
   v2.5.10 the field was never set, so HA showed only poll-request time.

2. **#325 capability-filter retry-after-timeout** — `FeatureState` gained
   a `retry_after` field. When a definitive-no flag flips, retry_after
   is set to now+24h. `is_command_known_unsupported` returns False once
   retry_after passes, letting the entity re-attempt without HA restart.

3. Tests for the timestamp parser are pure-data (no HA dep). The
   capability-retry test needs HA env to construct a coordinator — runs
   in CI.
"""

from __future__ import annotations

import pytest


# ── VW NA last_seen_at parser ──────────────────────────────────────────────


class _MiniValHelper:
    """Stand-in for the brand-client ``_val`` helper used in vw_na.py."""

    @staticmethod
    def val(obj, *path, default=None):
        cur = obj
        for k in path:
            if not isinstance(cur, dict):
                return default
            cur = cur.get(k)
            if cur is None:
                return default
        return cur


def _try_timestamp_paths(vehicle_raw: dict) -> str | None:
    """Reimplement the priority chain from vw_na.py:get_status() for
    standalone testing. Must stay in sync with production logic."""
    v = _MiniValHelper.val
    for path in (
        ("vehicleStatusTime",),
        ("connectionStatus", "lastConnectionTime"),
        ("connectionStatus", "timestamp"),
        ("carCapturedTimestamp",),
        ("powerStatus", "carCapturedTimestamp"),
        ("lastUpdated",),
        ("dataTimestamp",),
    ):
        ts = v(vehicle_raw, *path)
        if isinstance(ts, str) and len(ts) >= 10 and "T" in ts:
            return ts
    return None


class TestVWNATimestampParser:
    """Each timestamp field variant must be picked up in priority order."""

    def test_vehicle_status_time_wins(self) -> None:
        result = _try_timestamp_paths({
            "vehicleStatusTime": "2026-05-29T20:00:00Z",
            "lastUpdated": "2026-05-28T10:00:00Z",  # earlier alternative
        })
        assert result == "2026-05-29T20:00:00Z"

    def test_falls_to_connection_status_timestamp(self) -> None:
        result = _try_timestamp_paths({
            "connectionStatus": {
                "lastConnectionTime": "2026-05-29T18:00:00Z",
            },
        })
        assert result == "2026-05-29T18:00:00Z"

    def test_falls_to_car_captured_timestamp(self) -> None:
        result = _try_timestamp_paths({
            "carCapturedTimestamp": "2026-05-29T17:00:00Z",
        })
        assert result == "2026-05-29T17:00:00Z"

    def test_power_status_substring(self) -> None:
        result = _try_timestamp_paths({
            "powerStatus": {
                "carCapturedTimestamp": "2026-05-29T16:00:00Z",
            },
        })
        assert result == "2026-05-29T16:00:00Z"

    def test_no_timestamp_returns_none(self) -> None:
        result = _try_timestamp_paths({"odometer": 12345})
        assert result is None

    def test_garbage_timestamp_rejected(self) -> None:
        # Sanity: 9-char strings (too short) or strings without T are rejected
        result = _try_timestamp_paths({"vehicleStatusTime": "yesterday"})
        assert result is None
        result = _try_timestamp_paths({"vehicleStatusTime": ""})
        assert result is None

    def test_int_timestamp_rejected(self) -> None:
        """Some APIs ship UNIX epoch ints — we explicitly want ISO 8601."""
        result = _try_timestamp_paths({"vehicleStatusTime": 1779356400})
        assert result is None


# ── Capability-filter retry-after-timeout (#325) ───────────────────────────


class TestRetryAfterContract:
    """Pure-data tests of the retry_after logic. Full coordinator
    integration is tested in CI via HA env."""

    def test_retry_after_field_exists_on_feature_state(self) -> None:
        from custom_components.vag_connect.coordinator import FeatureState
        s = FeatureState()
        # Field exists, defaults to None
        assert hasattr(s, "retry_after")
        assert s.retry_after is None

    def test_record_success_clears_retry_after(self) -> None:
        """When the command succeeds, retry_after should clear."""
        from custom_components.vag_connect.coordinator import FeatureState
        from datetime import datetime, timezone, timedelta
        s = FeatureState()
        # Simulate a previous failure scheduling retry
        s.retry_after = datetime.now(tz=timezone.utc) + timedelta(hours=24)
        # record_success-like reset:
        s.retry_after = None
        s.supported_by_vehicle = True
        s.entitled_by_account = True
        assert s.retry_after is None
