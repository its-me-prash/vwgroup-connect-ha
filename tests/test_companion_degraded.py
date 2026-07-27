# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Companion degraded / out-of-sync self-heal, mined from
ckomma/charge-app-connector-vw (Apache-2.0) #22 (connector degraded) and #16
(server lock-ups): parse the app's own sync-age line so "the car's data is old"
is distinct from "the connector is unhealthy", and back off adaptively instead
of retrying a dead phone every 30 minutes forever.
"""
from __future__ import annotations

import pytest

from custom_components.vag_connect.companion.channel import (
    _FAILURE_COOLDOWN_S,
    _MAX_COOLDOWN_S,
    CompanionChannel,
)
from custom_components.vag_connect.companion.presets import PRESETS
from custom_components.vag_connect.companion.screen import (
    find_sync_age,
    parse_ui_dump,
)
from custom_components.vag_connect.companion.transport import (
    CompanionTransportError,
)


def _dump(nodes: str) -> str:
    return f'<?xml version="1.0"?><hierarchy>{nodes}</hierarchy>'


def _node(text: str) -> str:
    return (
        f'<node content-desc="{text}" text="" class="TextView" '
        'clickable="false" bounds="[0,0][10,10]" />'
    )


CLEAN = _dump(
    _node("Ladezustand 74 %") + _node("Aktualisiert vor 5 Minuten")
)


class TestSyncAgeParsing:
    @pytest.mark.parametrize(("text", "expected"), [
        ("Aktualisiert vor 5 Minuten", 300.0),
        ("Synchronised 2 hours ago", 7200.0),
        ("Aktualisiert vor 30 Sekunden", 30.0),
        ("Aktualisiert vor 1 Tag", 86400.0),
        ("Updated 45 min ago", 2700.0),
    ])
    def test_parses(self, text: str, expected: float) -> None:
        nodes = parse_ui_dump(_dump(_node(text)))
        assert find_sync_age(nodes, PRESETS["volkswagen"]) == expected

    def test_no_sync_line_is_none(self) -> None:
        nodes = parse_ui_dump(_dump(_node("Ladezustand 74 %")))
        assert find_sync_age(nodes, PRESETS["volkswagen"]) is None


class _FlakyTransport:
    def __init__(self, fail: bool, dump: str = CLEAN) -> None:
        self.fail = fail
        self._dump = dump
        self.connected = True

    async def connect(self) -> None:
        self.connected = True

    async def foreground_app(self, package: str) -> None:  # noqa: ARG002
        return None

    async def current_app_version(self, package: str) -> str | None:  # noqa: ARG002
        return "4.2.1"

    async def dump_ui(self) -> str:
        if self.fail:
            raise CompanionTransportError("phone off")
        return self._dump

    async def key_back(self) -> None:
        return None


def _clock():
    t = {"v": 1000.0}
    return (lambda: t["v"]), t


class TestAdaptiveCooldown:
    @pytest.mark.asyncio
    async def test_cooldown_doubles_per_consecutive_failure(self) -> None:
        now, t = _clock()
        tr = _FlakyTransport(fail=True)
        ch = CompanionChannel(tr, PRESETS["volkswagen"], time_fn=now)
        # 1st failure -> base
        with pytest.raises(CompanionTransportError):
            await ch.read()
        first = ch._cooldown_until - now()
        assert first == _FAILURE_COOLDOWN_S
        # move past it, 2nd failure -> 2x
        t["v"] += first + 1
        with pytest.raises(CompanionTransportError):
            await ch.read()
        assert (ch._cooldown_until - now()) == _FAILURE_COOLDOWN_S * 2

    @pytest.mark.asyncio
    async def test_cooldown_is_capped(self) -> None:
        now, t = _clock()
        ch = CompanionChannel(_FlakyTransport(fail=True), PRESETS["volkswagen"], time_fn=now)
        for _ in range(20):
            with pytest.raises(CompanionTransportError):
                await ch.read()
            t["v"] += _MAX_COOLDOWN_S + 1
        assert (ch._cooldown_until - now()) <= _MAX_COOLDOWN_S

    @pytest.mark.asyncio
    async def test_success_resets_the_failure_count(self) -> None:
        now, t = _clock()
        tr = _FlakyTransport(fail=True)
        ch = CompanionChannel(tr, PRESETS["volkswagen"], time_fn=now)
        with pytest.raises(CompanionTransportError):
            await ch.read()
        t["v"] += _FAILURE_COOLDOWN_S + 1
        tr.fail = False
        await ch.read()  # success
        assert ch._consecutive_failures == 0

    @pytest.mark.asyncio
    async def test_reset_cooldown_clears_backoff(self) -> None:
        now, t = _clock()
        ch = CompanionChannel(_FlakyTransport(fail=True), PRESETS["volkswagen"], time_fn=now)
        with pytest.raises(CompanionTransportError):
            await ch.read()
        assert ch._in_cooldown()
        ch.reset_cooldown()
        assert not ch._in_cooldown()
        assert ch._consecutive_failures == 0


class TestSourceDataAge:
    @pytest.mark.asyncio
    async def test_read_captures_source_data_age(self) -> None:
        now, _ = _clock()
        ch = CompanionChannel(_FlakyTransport(fail=False), PRESETS["volkswagen"], time_fn=now)
        await ch.read()
        assert ch.source_data_age_s == 300.0  # "vor 5 Minuten"
