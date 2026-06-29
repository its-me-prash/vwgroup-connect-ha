# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""v2.2.0 Phase 2 PR #11/20 — subscription_days_remaining derived sensor.

Closes the subscription-feature triangle:
  - PR #8:  ``subscription_expiry_at``  (TIMESTAMP — when does it expire?)
  - PR #9:  ``subscription_active``     (BOOL — is it currently valid?)
  - PR #11: ``subscription_days_remaining`` (INT — how many days left?)

The int sensor is **automation-friendly**: threshold triggers like
``if state(...) < 30 → notify`` are trivial against an integer
sensor, much easier than templating against a TIMESTAMP.

Negative values when expired (e.g. -3 means "expired 3 days ago"),
so the same sensor doubles as a "how long ago did it lapse" alarm.

"Bazinga! Now THAT'S what I call a renewable resource."
— Sheldon Cooper, on the day his Wolowitz-bot's Connect sub auto-renewed
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone


def _compute_days(earliest: str | None) -> int | None:
    """Pure mirror of the inline computation in seat_cupra.py + vw_eu.py."""
    if earliest is None:
        return None
    try:
        exp_dt = datetime.fromisoformat(earliest.replace("Z", "+00:00"))
        if exp_dt.tzinfo is None:
            exp_dt = exp_dt.replace(tzinfo=timezone.utc)
        return (exp_dt - datetime.now(tz=timezone.utc)).days
    except (ValueError, TypeError):
        return None


class TestDaysRemainingArithmetic:
    """``timedelta.days`` floor-divides, so partial days don't inflate."""

    def test_far_future_positive_days(self) -> None:
        future = (
            datetime.now(tz=timezone.utc) + timedelta(days=365)
        ).strftime("%Y-%m-%dT%H:%M:%SZ")
        result = _compute_days(future)
        # Allow ±1 day tolerance for test-runtime drift
        assert result is not None
        assert 363 <= result <= 365

    def test_near_future_small_positive(self) -> None:
        future = (
            datetime.now(tz=timezone.utc) + timedelta(days=10)
        ).strftime("%Y-%m-%dT%H:%M:%SZ")
        result = _compute_days(future)
        assert result is not None
        assert 8 <= result <= 10

    def test_past_expiry_negative_days(self) -> None:
        # Expired 5 days ago — should be -5 or -6 depending on hours
        past = (
            datetime.now(tz=timezone.utc) - timedelta(days=5)
        ).strftime("%Y-%m-%dT%H:%M:%SZ")
        result = _compute_days(past)
        assert result is not None
        assert -6 <= result <= -4

    def test_far_past_large_negative(self) -> None:
        # 2 years ago — should be ~-730
        past = (
            datetime.now(tz=timezone.utc) - timedelta(days=730)
        ).strftime("%Y-%m-%dT%H:%M:%SZ")
        result = _compute_days(past)
        assert result is not None
        assert -732 <= result <= -728

    def test_partial_day_floored_down(self) -> None:
        # 12 hours from now → 0 days (floor-divide)
        future = (
            datetime.now(tz=timezone.utc) + timedelta(hours=12)
        ).strftime("%Y-%m-%dT%H:%M:%SZ")
        result = _compute_days(future)
        assert result == 0


class TestDaysRemainingDefensive:
    def test_none_input_returns_none(self) -> None:
        # Perpetual entitlement → MUST stay None (not 0)
        assert _compute_days(None) is None

    def test_empty_string_returns_none(self) -> None:
        assert _compute_days("") is None

    def test_garbage_string_returns_none(self) -> None:
        assert _compute_days("not-a-date") is None

    def test_partial_iso_returns_none(self) -> None:
        assert _compute_days("2026") is None

    def test_iso_with_z_suffix(self) -> None:
        # Z must normalise to +00:00
        future = (
            datetime.now(tz=timezone.utc) + timedelta(days=30)
        ).strftime("%Y-%m-%dT%H:%M:%SZ")
        result = _compute_days(future)
        assert result is not None
        assert 28 <= result <= 30

    def test_naive_iso_treated_as_utc(self) -> None:
        # Naive datetime → tagged as UTC. Use far-future to avoid race.
        assert _compute_days("2099-01-01T00:00:00") is not None


class TestSensorRegistration:
    def test_described(self) -> None:
        from custom_components.vag_connect.sensor import SENSOR_DESCRIPTIONS

        keys = {desc.key for desc in SENSOR_DESCRIPTIONS}
        assert "subscription_days_remaining" in keys

    def test_uses_measurement_state_class(self) -> None:
        from homeassistant.components.sensor import SensorStateClass

        from custom_components.vag_connect.sensor import SENSOR_DESCRIPTIONS

        desc = next(
            d
            for d in SENSOR_DESCRIPTIONS
            if d.key == "subscription_days_remaining"
        )
        assert desc.state_class == SensorStateClass.MEASUREMENT

    def test_phantom_gated(self) -> None:
        from custom_components.vag_connect.sensor import _DATA_PRESENT_REQUIRED

        assert "subscription_days_remaining" in _DATA_PRESENT_REQUIRED
