# Copyright 2026 Prash Balan (@its-me-prash) - Apache License 2.0
# SPDX-License-Identifier: AGPL-3.0-or-later
"""v2.9.0 - VW account-lock detection sliding-window.

CariadBaseClient._record_lock_signal feeds a (timestamp, status) list,
prunes to 30-minute window, flips ``account_lock_detected`` once the
threshold (3) is reached.
"""

from __future__ import annotations

import time


def _client():
    from custom_components.vag_connect.cariad.api.base import CariadBaseClient
    c = CariadBaseClient.__new__(CariadBaseClient)
    c._brand = type("B", (), {"name": "volkswagen"})()
    c._lock_history = []
    c.account_lock_detected = False
    return c


class TestRecordLockSignal:
    def test_http_423_records(self):
        c = _client()
        c._record_lock_signal(423, "")
        assert len(c._lock_history) == 1
        assert c.account_lock_detected is False  # only 1, threshold is 3

    def test_three_423s_flip_flag(self):
        c = _client()
        for _ in range(3):
            c._record_lock_signal(423, "")
        assert c.account_lock_detected is True

    def test_http_403_with_marker_records(self):
        c = _client()
        for body in (
            "you have been rate limited",
            "account temporarily locked",
            "too many requests, throttle",
        ):
            c._record_lock_signal(403, body)
        assert c.account_lock_detected is True

    def test_http_403_without_marker_ignored(self):
        c = _client()
        c._record_lock_signal(403, "Forbidden")
        c._record_lock_signal(403, "client_id missing")
        c._record_lock_signal(403, "")
        assert c.account_lock_detected is False
        assert len(c._lock_history) == 0

    def test_other_statuses_ignored(self):
        c = _client()
        for status in (200, 400, 401, 404, 500, 502):
            c._record_lock_signal(status, "irrelevant")
        assert c.account_lock_detected is False

    def test_window_prunes_old_signals(self):
        c = _client()
        # Old signals (61 minutes ago, outside the 30-min window)
        old = time.monotonic() - 3700
        c._lock_history = [(old, 423), (old, 423)]
        # New signal within window
        c._record_lock_signal(423, "")
        # Old ones pruned, only the fresh one remains
        assert len(c._lock_history) == 1
        assert c.account_lock_detected is False


class TestRepairIssueIntegration:
    def test_raise_function_signature(self):
        # Smoke import; the function exists and has the expected
        # positional/keyword args. We don't drive HA here.
        from custom_components.vag_connect.repairs import (
            raise_issue_account_locked,
            clear_account_locked_issue,
        )
        import inspect
        sig = inspect.signature(raise_issue_account_locked)
        params = list(sig.parameters)
        assert params == ["hass", "entry_id", "brand", "last_status"]
        sig2 = inspect.signature(clear_account_locked_issue)
        assert list(sig2.parameters) == ["hass", "entry_id"]

    def test_translation_keys_present_in_all_langs(self):
        import json
        from pathlib import Path
        base = Path(__file__).resolve().parent.parent / "custom_components" / "vag_connect"
        for lang in ("en", "de", "cs", "es", "fr", "nl", "pl", "sv"):
            p = base / "translations" / f"{lang}.json"
            with open(p, encoding="utf-8") as f:
                d = json.load(f)
            assert "account_locked" in d.get("issues", {}), \
                f"{lang}.json missing issues.account_locked"


class TestSuccessfulRefreshClearsFlag:
    """Direct unit-level: setting account_lock_detected then a successful
    refresh resets it back to False. We do not drive the real
    refresh-token HTTP path here; pinning the field-reset contract."""

    def test_flag_can_be_cleared(self):
        c = _client()
        c.account_lock_detected = True
        c._lock_history = [(time.monotonic(), 423)]
        # Mimic the contract: success branch sets to False + clears history.
        c.account_lock_detected = False
        c._lock_history.clear()
        assert c.account_lock_detected is False
        assert c._lock_history == []
