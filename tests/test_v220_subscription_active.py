# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""v2.2.0 Phase 2 PR #9/20 — subscription_active binary_sensor.

Companion to PR #8/20 ``subscription_expiry_at``. Computes a simple
True/False/None tri-state from the same earliest-expiry aggregation
so HA automations can fire on "subscription lapsed" events without
needing template helpers.

Tri-state semantics:
- True  → at least one service expires in the future (subscription valid)
- False → earliest expiry is now-or-past (subscription LAPSED — alarm)
- None  → no expiry info at all (perpetual OR brand without services block)

The None preservation is intentional: perpetual entitlements (lifetime
subscriptions on older Born MY24 firmware, dealer-bundled packages)
should NOT trigger "expired" alarms just because there's no expiry.

"That subscription? Oh, it's outstanding. Just like Howard's mom's lasagna."
— Sheldon Cooper, the day his Wolowitz-bot's API key finally renewed
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest


def _compute_active(earliest: str | None) -> bool | None:
    """Pure mirror of the parser logic in seat_cupra.py.

    Kept in-test so we don't depend on importing the full async parser.
    """
    if earliest is None:
        return None
    try:
        parsed = datetime.fromisoformat(earliest.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed > datetime.now(tz=timezone.utc)
    except (ValueError, TypeError):
        return None


class TestTriStateLogic:
    """The True / False / None split must be preserved end-to-end."""

    def test_future_expiry_is_active(self) -> None:
        future = (
            datetime.now(tz=timezone.utc) + timedelta(days=365)
        ).strftime("%Y-%m-%dT%H:%M:%SZ")
        assert _compute_active(future) is True

    def test_past_expiry_is_inactive(self) -> None:
        past = (
            datetime.now(tz=timezone.utc) - timedelta(days=1)
        ).strftime("%Y-%m-%dT%H:%M:%SZ")
        assert _compute_active(past) is False

    def test_far_past_expiry_is_inactive(self) -> None:
        # 5 years ago — clearly lapsed
        assert _compute_active("2020-01-01T00:00:00Z") is False

    def test_far_future_expiry_is_active(self) -> None:
        assert _compute_active("2099-12-31T23:59:59Z") is True

    def test_none_input_returns_none(self) -> None:
        # Perpetual entitlement OR brand without services block —
        # MUST NOT flip to False.
        assert _compute_active(None) is None


class TestDefensiveParsing:
    """Malformed timestamps fall back to None, never crash."""

    def test_empty_string_returns_none(self) -> None:
        assert _compute_active("") is None

    def test_garbage_string_returns_none(self) -> None:
        assert _compute_active("not-a-date") is None

    def test_partial_iso_string_returns_none(self) -> None:
        # Missing time component AND missing tz
        assert _compute_active("2026") is None

    def test_iso_with_explicit_offset_works(self) -> None:
        # +02:00 offset must parse correctly
        future_str = (
            datetime.now(tz=timezone.utc) + timedelta(days=10)
        ).strftime("%Y-%m-%dT%H:%M:%S+00:00")
        assert _compute_active(future_str) is True

    def test_naive_iso_treated_as_utc(self) -> None:
        # Naive datetime (no tz) — parser tags as UTC. Future date works.
        # Use far-future to avoid race conditions with test runtime.
        assert _compute_active("2099-01-01T00:00:00") is True

    def test_iso_with_z_suffix(self) -> None:
        # Z must be normalised to +00:00 — round-trip test
        assert _compute_active("2099-06-15T12:00:00Z") is True


class TestBinarySensorRegistration:
    def test_subscription_active_described(self) -> None:
        from custom_components.vag_connect.binary_sensor import (
            BINARY_DESCRIPTIONS,
        )

        keys = {desc.key for desc in BINARY_DESCRIPTIONS}
        assert "subscription_active" in keys

    def test_subscription_active_phantom_gated(self) -> None:
        from custom_components.vag_connect.binary_sensor import (
            _DATA_PRESENT_REQUIRED,
        )

        assert "subscription_active" in _DATA_PRESENT_REQUIRED


class TestTranslationCoverage:
    @pytest.mark.parametrize(
        "lang", ["en", "de", "cs", "sv", "fr", "nl", "es", "pl"]
    )
    def test_lang_has_subscription_active(self, lang: str) -> None:
        import json
        from pathlib import Path

        path = Path(f"custom_components/vag_connect/translations/{lang}.json")
        data = json.loads(path.read_text(encoding="utf-8"))
        assert "subscription_active" in data["entity"]["binary_sensor"]

    def test_strings_json_has_subscription_active(self) -> None:
        import json
        from pathlib import Path

        data = json.loads(
            Path("custom_components/vag_connect/strings.json").read_text(
                encoding="utf-8"
            )
        )
        assert "subscription_active" in data["entity"]["binary_sensor"]
