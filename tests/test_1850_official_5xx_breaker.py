# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#1850 — a 500-looping official channel breached its own quota sevenfold.

@indigomejor measured it on a Škoda Octavia MY26 over three days: the
``skoda_official`` channel answered 500 for every read, each read retried the
ladder for two endpoints (8 HTTP requests per cycle), at ~17.6 cycles an hour.
That is ~140 requests an hour against a documented 20/hour/key budget, and it
ended in HTTP 429 and then a hard 430 that pauses the account for two hours.

The guard that was supposed to prevent this is REACTIVE: it skips only once the
server has said "too many" — ``RateLimit-Remaining: 0``, or a 429/503 with
Retry-After. A 5xx says nothing of the kind, so a 500-looping endpoint is
invisible to it, and the docstring's claim that the read "honours the
20/hour/key budget" was true only of a quota the server itself enforces. Nothing
counted.

What makes this worth a breaker rather than a retry tweak: the channel is a
supplement. His primary channels were healthy throughout, his ``source_channel``
was ``eu_data_act+skoda``, and the official channel's data was not used. Every
one of those ~140 requests bought nothing and cost him the account.

The brake is per-channel on purpose. The portal's own 5xx breaker raises the
whole poll cycle's sleep, which is right when the portal IS the primary source;
doing that here would have slowed his two working channels to protect the broken
one.
"""
from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import MagicMock


def _client() -> Any:
    from custom_components.vag_connect.cariad.api.skoda import SkodaClient

    return SkodaClient(MagicMock(), "u@t.invalid", "pw")


class _Official:
    """The official sub-client: counts reads and fails the way a 5xx does."""

    def __init__(self, *, fail: bool) -> None:
        self.fail = fail
        self.reads = 0
        self.over_rate_limit = False

    async def get_status(self, vin: str) -> Any:
        self.reads += 1
        if self.fail:
            raise RuntimeError("Server error 500")
        return object()


def _run(coro: Any) -> Any:
    return asyncio.new_event_loop().run_until_complete(coro)


def test_a_failing_channel_is_not_called_again_straight_away() -> None:
    """The core of it. RED before the change: every cycle calls through."""
    c = _client()
    off = _Official(fail=True)
    c._supplementary_official = off

    assert _run(c.official_live_read("WVWZZZ000M0000001")) is None
    assert off.reads == 1, "first read must happen — that is how we learn it fails"

    for _ in range(5):
        assert _run(c.official_live_read("WVWZZZ000M0000001")) is None
    assert off.reads == 1, (
        f"{off.reads} reads: the channel was called again inside its backoff window"
    )


def test_the_window_escalates_five_fifteen_thirty() -> None:
    """Same spacing as the portal breaker, so there is one shape in the codebase."""
    from custom_components.vag_connect.cariad.api.skoda import (
        _OFFICIAL_5XX_BACKOFF_S,
    )

    assert _OFFICIAL_5XX_BACKOFF_S == (300.0, 900.0, 1800.0)

    c = _client()
    off = _Official(fail=True)
    c._supplementary_official = off

    seen = []
    for expected in _OFFICIAL_5XX_BACKOFF_S:
        c._official_skip_until = 0.0  # let the next attempt through
        _run(c.official_live_read("WVWZZZ000M0000001"))
        seen.append(expected)
    assert c._official_5xx_streak == len(_OFFICIAL_5XX_BACKOFF_S)

    # saturates rather than growing without bound
    c._official_skip_until = 0.0
    _run(c.official_live_read("WVWZZZ000M0000001"))
    assert c._official_5xx_streak == len(_OFFICIAL_5XX_BACKOFF_S)


def test_a_good_read_clears_the_streak() -> None:
    """A channel that recovers must not stay penalised."""
    c = _client()
    off = _Official(fail=True)
    c._supplementary_official = off
    _run(c.official_live_read("WVWZZZ000M0000001"))
    assert c._official_5xx_streak == 1

    off.fail = False
    c._official_skip_until = 0.0
    assert _run(c.official_live_read("WVWZZZ000M0000001")) is not None
    assert c._official_5xx_streak == 0
    assert c._official_skip_until == 0.0


def test_no_data_counts_as_a_failure_too() -> None:
    """A None answer is not an error, and it still cost a request to get. The
    reporter's waste was requests, not exceptions, so requests are what is
    counted."""
    c = _client()

    class _Empty(_Official):
        async def get_status(self, vin: str) -> Any:
            self.reads += 1
            return None

    off = _Empty(fail=False)
    c._supplementary_official = off
    assert _run(c.official_live_read("WVWZZZ000M0000001")) is None
    assert c._official_5xx_streak == 1


def test_the_reactive_quota_guard_still_comes_first() -> None:
    """The new brake is in addition to the old one, not instead of it: once the
    server has said RateLimit-Remaining 0, no read is attempted at all."""
    c = _client()
    off = _Official(fail=False)
    off.over_rate_limit = True
    c._supplementary_official = off
    assert _run(c.official_live_read("WVWZZZ000M0000001")) is None
    assert off.reads == 0


def test_the_failover_path_shares_the_brake() -> None:
    """Both read paths go through the same body, so a channel skipped for the
    live merge is also skipped for the failover read — otherwise a hard primary
    failure would walk straight back into the loop."""
    c = _client()
    off = _Official(fail=True)
    c._supplementary_official = off
    _run(c.official_live_read("WVWZZZ000M0000001"))
    assert off.reads == 1
    assert _run(c.official_failover_read("WVWZZZ000M0000001")) is None
    assert off.reads == 1, "failover read ignored the backoff window"
