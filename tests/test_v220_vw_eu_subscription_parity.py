# Copyright 2026 Prash Balan (@its-me-prash) — Apache License 2.0
# SPDX-License-Identifier: Apache-2.0
"""v2.2.0 Phase 2 PR #10/20 — VW EU/Audi subscription parity.

Mirrors the SEAT/CUPRA aggregation from PR #8/#9 but reads from the
CARIAD-BFF capabilities endpoint where each capability carries its
own ``expirationDate`` for subscription-gated services
(``honkAndFlash``, ``parkingPosition``, ``access``, etc.).

Tri-state semantics preserved: perpetual capabilities (no expiry
leaf) stay None instead of False to avoid false-alarming users with
lifetime entitlements.

"You'd be amazed how much research you can get done when you have
no life whatsoever." — Sheldon Cooper, on capability-expiry parsing
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone


def _aggregate_caps(caps: list) -> str | None:
    """Pure mirror of vw_eu.py's earliest-wins loop (lines ~1320-1335).

    Kept in-test so we can exercise the logic without invoking the
    full async-fetch machinery.
    """
    if not isinstance(caps, list):
        return None
    earliest: str | None = None
    for cap in caps:
        if not isinstance(cap, dict):
            continue
        cap_exp = (
            cap.get("expirationDate")
            or cap.get("validUntil")
            or cap.get("expiresAt")
        )
        if not isinstance(cap_exp, str) or not cap_exp:
            continue
        if earliest is None or cap_exp < earliest:
            earliest = cap_exp
    return earliest


def _compute_active(earliest: str | None) -> bool | None:
    if earliest is None:
        return None
    try:
        parsed = datetime.fromisoformat(earliest.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed > datetime.now(tz=timezone.utc)
    except (ValueError, TypeError):
        return None


class TestCapabilityAggregation:
    """Same earliest-wins logic as PR #8, applied to caps array."""

    def test_single_capability_expirationDate(self) -> None:
        caps = [{"id": "honkAndFlash", "expirationDate": "2027-03-15T00:00:00Z"}]
        assert _aggregate_caps(caps) == "2027-03-15T00:00:00Z"

    def test_earliest_across_multiple_caps_wins(self) -> None:
        caps = [
            {"id": "honkAndFlash", "expirationDate": "2027-03-15T00:00:00Z"},
            {"id": "parkingPosition", "expirationDate": "2026-08-01T00:00:00Z"},
            {"id": "access", "expirationDate": "2029-01-01T00:00:00Z"},
        ]
        assert _aggregate_caps(caps) == "2026-08-01T00:00:00Z"

    def test_mixed_variants_compose(self) -> None:
        # CARIAD-BFF has shipped all three spellings in different revs
        caps = [
            {"id": "a", "expirationDate": "2027-06-01T00:00:00Z"},
            {"id": "b", "validUntil": "2026-12-01T00:00:00Z"},
            {"id": "c", "expiresAt": "2028-01-01T00:00:00Z"},
        ]
        assert _aggregate_caps(caps) == "2026-12-01T00:00:00Z"

    def test_perpetual_caps_no_expiry_returns_none(self) -> None:
        caps = [
            {"id": "honkAndFlash", "status": []},
            {"id": "parkingPosition", "status": []},
        ]
        assert _aggregate_caps(caps) is None


class TestCapabilityDefensive:
    def test_non_list_returns_none(self) -> None:
        assert _aggregate_caps(None) is None
        assert _aggregate_caps({}) is None
        assert _aggregate_caps("not-a-list") is None

    def test_empty_list_returns_none(self) -> None:
        assert _aggregate_caps([]) is None

    def test_non_dict_cap_skipped(self) -> None:
        caps = ["honkAndFlash", {"id": "access", "expirationDate": "2027-01-01T00:00:00Z"}]
        assert _aggregate_caps(caps) == "2027-01-01T00:00:00Z"

    def test_int_expiry_skipped(self) -> None:
        caps = [{"id": "access", "expirationDate": 1735689600}]
        assert _aggregate_caps(caps) is None

    def test_empty_string_expiry_skipped(self) -> None:
        caps = [{"id": "access", "expirationDate": ""}]
        assert _aggregate_caps(caps) is None


class TestParitySemantics:
    """The aggregation here must produce the same result-shape as the
    SEAT/CUPRA aggregation in PR #8 — same tri-state, same earliest-
    wins, same defensive-skip semantics."""

    def test_future_expiry_yields_active_true(self) -> None:
        future = (
            datetime.now(tz=timezone.utc) + timedelta(days=180)
        ).strftime("%Y-%m-%dT%H:%M:%SZ")
        caps = [{"id": "access", "expirationDate": future}]
        agg = _aggregate_caps(caps)
        assert agg == future
        assert _compute_active(agg) is True

    def test_past_expiry_yields_active_false(self) -> None:
        past = (
            datetime.now(tz=timezone.utc) - timedelta(days=1)
        ).strftime("%Y-%m-%dT%H:%M:%SZ")
        caps = [{"id": "access", "expirationDate": past}]
        agg = _aggregate_caps(caps)
        assert agg == past
        assert _compute_active(agg) is False

    def test_perpetual_yields_active_none(self) -> None:
        # No expiry leaf anywhere → both fields stay None
        caps = [{"id": "honkAndFlash"}]
        assert _aggregate_caps(caps) is None
        assert _compute_active(None) is None


class TestPhantomGateUnchanged:
    """The gate entries from PR #8/#9 still cover this brand expansion."""

    def test_subscription_expiry_at_still_gated(self) -> None:
        from custom_components.vag_connect.sensor import _DATA_PRESENT_REQUIRED

        # PR #10 widens populating brands to VW EU + Audi, but the gate
        # itself stays unchanged — gate just means "skip phantom if
        # field is None", which still applies to Skoda/Porsche/VW NA.
        assert "subscription_expiry_at" in _DATA_PRESENT_REQUIRED

    def test_subscription_active_still_gated(self) -> None:
        from custom_components.vag_connect.binary_sensor import (
            _DATA_PRESENT_REQUIRED,
        )

        assert "subscription_active" in _DATA_PRESENT_REQUIRED
