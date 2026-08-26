# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Companion agent / add-on tokens must never reach a diagnostics download.

The companion agent relay endpoint is unauthenticated in HA's sense and gated
ENTIRELY by a per-entry token: anyone who holds it can bind a phone to the car's
app. That token (and the ADB-bridge add-on token) live in ``entry.data``, so
without an explicit redaction rule they land in the diagnostics file users attach
to public GitHub issues — a live credential disclosure, not a cosmetic one.

Everything here is synthetic — never put a real token in a test.
"""
from __future__ import annotations

from custom_components.vag_connect.diagnostics import _scrub

_ENTRY_DATA = {
    "brand": "volkswagen",
    "username": "someone@example.com",
    "companion_agent_token": "SYNTHETIC_AGENT_TOKEN_0123456789abcdef",
    "companion_addon_token": "SYNTHETIC_ADDON_TOKEN_0123456789abcdef",
}


def _dump() -> str:
    return repr(_scrub(dict(_ENTRY_DATA), gps_round=False))


def test_agent_token_not_leaked() -> None:
    assert "SYNTHETIC_AGENT_TOKEN_0123456789abcdef" not in _dump()


def test_addon_token_not_leaked() -> None:
    assert "SYNTHETIC_ADDON_TOKEN_0123456789abcdef" not in _dump()


def test_brand_still_reported() -> None:
    # Redaction must not gut the useful half of the dump.
    assert "volkswagen" in _dump()
