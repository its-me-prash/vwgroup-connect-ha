# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""v2.15.13 — proactive vw.de authproxy SSO session roll (maybe_roll).

The authproxy session's downstream tokens die ~30 min after the last login
and aren't renewed by data reads; the identity SSO behind the silent refresh
lapses if unused. Poll cadence ~15 min, so a slow cycle can let the SSO die
between polls → the next read eats a guaranteed auth-fail and (if the identity
twin lapsed too) forces a re-OTP. maybe_roll() rolls the session proactively,
debounced so a multi-VIN poll rolls at most once per window, best-effort so a
failed roll never breaks the poll. (Mirrors the technique rafaelhutter's
volkswagen_connect documents; reimplemented independently.)

Uses the real monotonic clock + _last_roll manipulation (no clock patching).
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

from custom_components.vag_connect.cariad.auth._website_authproxy import (
    WebsiteAuthProxyConnector,
)


def _conn() -> WebsiteAuthProxyConnector:
    c = WebsiteAuthProxyConnector(MagicMock(), "u@t.de", "pw")  # type: ignore[arg-type]
    c.logged_in = True  # maybe_roll is a no-op until a session exists
    return c


def test_first_call_rolls() -> None:
    c = _conn()
    c.refresh = AsyncMock()  # type: ignore[method-assign]
    asyncio.run(c.maybe_roll())
    c.refresh.assert_awaited_once()


def test_second_call_within_window_is_debounced() -> None:
    c = _conn()
    c.refresh = AsyncMock()  # type: ignore[method-assign]
    asyncio.run(c.maybe_roll())  # rolls, stamps _last_roll = now
    asyncio.run(c.maybe_roll())  # microseconds later → inside 600 s → skip
    c.refresh.assert_awaited_once()


def test_rolls_again_after_the_window() -> None:
    c = _conn()
    c.refresh = AsyncMock()  # type: ignore[method-assign]
    asyncio.run(c.maybe_roll())
    c._last_roll -= 700.0  # pretend the last roll was 700 s ago (> 600 s)
    asyncio.run(c.maybe_roll())
    assert c.refresh.await_count == 2


def test_force_bypasses_the_debounce() -> None:
    c = _conn()
    c.refresh = AsyncMock()  # type: ignore[method-assign]
    asyncio.run(c.maybe_roll())
    asyncio.run(c.maybe_roll(force=True))
    assert c.refresh.await_count == 2


def test_never_rolls_before_first_login() -> None:
    c = _conn()
    c.logged_in = False
    c.refresh = AsyncMock()  # type: ignore[method-assign]
    asyncio.run(c.maybe_roll())
    c.refresh.assert_not_awaited()


def test_failed_roll_is_swallowed_not_raised() -> None:
    c = _conn()
    c.refresh = AsyncMock(side_effect=RuntimeError("boom"))  # type: ignore[method-assign]
    # Must NOT raise — the reactive refresh() in get_status is the safety net.
    asyncio.run(c.maybe_roll())
    c.refresh.assert_awaited_once()
