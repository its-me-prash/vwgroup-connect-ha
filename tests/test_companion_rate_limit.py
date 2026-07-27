# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Companion rate-limit backoff, mined from ckomma/charge-app-connector-vw
(Apache-2.0) #21. A "too many requests / temporarily blocked" banner trips a
long, wall-clock (persistable) backoff that also disables writes, so we never
drive further into a real account lockout.
"""
from __future__ import annotations

import pytest

from custom_components.vag_connect.companion.channel import (
    _RATE_LIMIT_BACKOFF_S,
    CompanionChannel,
    CompanionWriteBlocked,
)
from custom_components.vag_connect.companion.presets import PRESETS
from custom_components.vag_connect.companion.screen import (
    find_rate_limit_banner,
    parse_ui_dump,
)


def _dump(nodes: str) -> str:
    return f'<?xml version="1.0"?><hierarchy>{nodes}</hierarchy>'


LOCKOUT = _dump(
    '<node content-desc="Zu viele Anfragen, bitte später erneut versuchen" '
    'text="" class="TextView" clickable="false" bounds="[0,0][500,80]" />'
)
CLEAN = _dump(
    '<node content-desc="Ladezustand 74 %" text="" class="TextView" '
    'clickable="false" bounds="[0,0][100,50]" />'
    '<node content-desc="Klimatisierung starten" text="Klima" '
    'class="android.widget.Button" clickable="true" bounds="[0,200][200,260]" />'
)


class _SeqTransport:
    def __init__(self, dumps: list[str]) -> None:
        self._dumps = list(dumps)
        self.taps: list[tuple[int, int]] = []
        self.backs = 0
        self.connected = True

    async def connect(self) -> None:
        self.connected = True

    async def foreground_app(self, package: str) -> None:  # noqa: ARG002
        return None

    async def current_app_version(self, package: str) -> str | None:  # noqa: ARG002
        return "4.2.1"

    async def dump_ui(self) -> str:
        return self._dumps.pop(0) if len(self._dumps) > 1 else self._dumps[0]

    async def key_back(self) -> None:
        self.backs += 1

    async def tap(self, x: int, y: int) -> None:
        self.taps.append((x, y))


def _clocks():
    mono = {"v": 1000.0}
    wall = {"v": 1_700_000_000.0}
    return (lambda: mono["v"]), (lambda: wall["v"]), mono, wall


def _channel(transport, wall_fn, mono_fn):
    return CompanionChannel(
        transport, PRESETS["volkswagen"], time_fn=mono_fn, wall_clock_fn=wall_fn,
    )


class TestBannerDetection:
    def test_lockout_banner_detected(self) -> None:
        b = find_rate_limit_banner(parse_ui_dump(LOCKOUT), PRESETS["volkswagen"])
        assert b is not None and b.name == "rate_limited"

    def test_clean_screen_no_banner(self) -> None:
        assert find_rate_limit_banner(parse_ui_dump(CLEAN), PRESETS["volkswagen"]) is None

    def test_every_brand_has_a_rate_limit_banner(self) -> None:
        for brand, p in PRESETS.items():
            assert p.rate_limit_banners, brand


class TestRateLimitBackoff:
    @pytest.mark.asyncio
    async def test_banner_trips_backoff_and_returns_no_data(self) -> None:
        mono, wall, _, _ = _clocks()
        ch = _channel(_SeqTransport([LOCKOUT]), wall, mono)
        result = await ch.read()
        assert result is None
        assert ch.rate_limited_until > wall()

    @pytest.mark.asyncio
    async def test_backoff_skips_subsequent_reads(self) -> None:
        mono, wall, _, wall_d = _clocks()
        ch = _channel(_SeqTransport([LOCKOUT, CLEAN]), wall, mono)
        await ch.read()  # trips
        # even though a clean screen is now available, we stay backed off
        assert await ch.read() is None
        wall_d["v"] += _RATE_LIMIT_BACKOFF_S + 1  # window elapsed
        # a fresh transport with the clean screen now reads
        ch._t = _SeqTransport([CLEAN])
        assert await ch.read()

    @pytest.mark.asyncio
    async def test_writes_blocked_and_disabled_while_backed_off(self) -> None:
        # Use a synthetic WRITABLE preset so the ONLY thing disabling writes here
        # is the rate-limit backoff (the shipped VW quarantines writes anyway).
        from dataclasses import replace

        from custom_components.vag_connect.companion.presets import ActionSelector

        writable = replace(
            PRESETS["volkswagen"],
            actions=(
                ActionSelector(
                    action="start_climate",
                    content_desc_re=r"(?:Klima\w*\s*starten|Start climate)",
                ),
            ),
        )
        mono, wall, _, _ = _clocks()
        ch = CompanionChannel(
            _SeqTransport([LOCKOUT]), writable, time_fn=mono, wall_clock_fn=wall,
        )
        await ch.read()  # trips backoff
        ch._version_ok = True  # even with the version gate open
        assert ch.writes_enabled is False
        with pytest.raises(CompanionWriteBlocked):
            await ch.do_action("start_climate")

    @pytest.mark.asyncio
    async def test_restore_reapplies_a_persisted_backoff(self) -> None:
        mono, wall, _, _ = _clocks()
        ch = _channel(_SeqTransport([CLEAN]), wall, mono)
        # simulate a backoff persisted before an HA restart
        ch.restore_rate_limit(wall() + 3600)
        assert ch._is_rate_limited() is True
        assert await ch.read() is None

    @pytest.mark.asyncio
    async def test_restore_ignores_an_expired_backoff(self) -> None:
        mono, wall, _, _ = _clocks()
        ch = _channel(_SeqTransport([CLEAN]), wall, mono)
        ch.restore_rate_limit(wall() - 100)  # already in the past
        assert ch._is_rate_limited() is False
