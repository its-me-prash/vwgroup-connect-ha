# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Companion overlay/nag-screen recovery, mined from
ckomma/charge-app-connector-vw (Apache-2.0) #8/#13/#20.

A power-saving prompt or a "delayed execution" notice sits on top of the data
screen; we dismiss it with BACK (which can never actuate the car) and re-dump.
If it will not clear, a read returns no fields and a write is refused, rather
than parsing or tapping the wrong screen.
"""
from __future__ import annotations

import time

import pytest

from custom_components.vag_connect.companion.channel import (
    CompanionChannel,
    CompanionWriteBlocked,
)
from custom_components.vag_connect.companion.presets import PRESETS
from custom_components.vag_connect.companion.screen import find_overlay, parse_ui_dump


def _dump(nodes: str) -> str:
    return f'<?xml version="1.0"?><hierarchy>{nodes}</hierarchy>'


# A VW power-saving nag (ckomma #13) and the clean data screen.
NAG = _dump(
    '<node content-desc="Intelligentes Stromsparen ist aktiv" text="" '
    'class="TextView" clickable="false" bounds="[0,0][500,80]" />'
)
CLEAN = _dump(
    '<node content-desc="Ladezustand 74 %" text="" class="TextView" '
    'clickable="false" bounds="[0,0][100,50]" />'
    '<node content-desc="Klimatisierung starten" text="Klima" '
    'class="android.widget.Button" clickable="true" bounds="[0,200][200,260]" />'
)


class _SeqTransport:
    """Returns dump_ui() outputs from a queue; records key_back presses."""

    def __init__(self, dumps: list[str], version: str = "4.2.1") -> None:
        self._dumps = list(dumps)
        self._version = version
        self.backs = 0
        self.taps: list[tuple[int, int]] = []
        self.connected = True

    async def connect(self) -> None:
        self.connected = True

    async def foreground_app(self, package: str) -> None:  # noqa: ARG002
        return None

    async def current_app_version(self, package: str) -> str | None:  # noqa: ARG002
        return self._version

    async def dump_ui(self) -> str:
        return self._dumps.pop(0) if len(self._dumps) > 1 else self._dumps[0]

    async def key_back(self) -> None:
        self.backs += 1

    async def tap(self, x: int, y: int) -> None:
        self.taps.append((x, y))


def _channel(transport):
    return CompanionChannel(transport, PRESETS["volkswagen"], time_fn=time.monotonic)


def _make_writable_vw():
    """A synthetic WRITABLE VW. The shipped VW preset quarantines writes (no
    actions, v2.26.0); the overlay-before-tap and min-interval write mechanisms
    still need coverage, so restore a climate action here."""
    from dataclasses import replace

    from custom_components.vag_connect.companion.presets import ActionSelector

    return replace(
        PRESETS["volkswagen"],
        actions=(
            ActionSelector(
                action="start_climate",
                content_desc_re=r"(?:Klima\w*\s*(?:starten|ein)|Start climate)",
            ),
        ),
    )


_WRITABLE_VW = _make_writable_vw()


class TestOverlayDetection:
    def test_vw_power_saving_is_detected(self) -> None:
        ov = find_overlay(parse_ui_dump(NAG), PRESETS["volkswagen"])
        assert ov is not None and ov.name == "power_saving"

    def test_clean_screen_has_no_overlay(self) -> None:
        assert find_overlay(parse_ui_dump(CLEAN), PRESETS["volkswagen"]) is None

    def test_every_brand_has_a_powersaving_overlay(self) -> None:
        for brand, p in PRESETS.items():
            assert any(o.name == "power_saving" for o in p.overlays), brand


class TestOverlayRecovery:
    @pytest.mark.asyncio
    async def test_read_dismisses_overlay_then_reads(self) -> None:
        # nag first, clean after one BACK
        t = _SeqTransport([NAG, CLEAN])
        fields = await _channel(t).read()
        assert t.backs == 1
        assert fields.get("battery_soc") == 74

    @pytest.mark.asyncio
    async def test_read_returns_empty_when_overlay_will_not_clear(self) -> None:
        # nag on every dump → cannot clear → no fields, not the overlay parsed
        t = _SeqTransport([NAG])
        fields = await _channel(t).read()
        assert fields == {}
        assert t.backs == 3  # tried the cap

    @pytest.mark.asyncio
    async def test_write_blocked_when_overlay_will_not_clear(self) -> None:
        t = _SeqTransport([NAG])
        ch = CompanionChannel(t, _WRITABLE_VW, time_fn=time.monotonic)
        await ch.read()  # decide version gate (returns {} but sets version ok)
        # writes_enabled needs a clean read; here the nag blocks, so force the
        # version gate on to isolate the overlay check (not the version check):
        ch._version_ok = True
        with pytest.raises(CompanionWriteBlocked):
            await ch.do_action("start_climate")
        assert t.taps == []

    @pytest.mark.asyncio
    async def test_write_proceeds_after_overlay_cleared(self) -> None:
        # nag, then clean (with the climate button) for the write dump
        t = _SeqTransport([CLEAN])  # already clean
        ch = CompanionChannel(t, _WRITABLE_VW, time_fn=time.monotonic)
        await ch.read()
        ch._version_ok = True
        await ch.do_action("start_climate")
        assert t.taps == [(100, 230)]


class TestWriteMinInterval:
    """ckomma #21 — never drive INTO a backend lockout with rapid taps."""

    def _clock(self):
        t = {"v": 1000.0}
        return (lambda: t["v"]), t

    @pytest.mark.asyncio
    async def test_second_tap_too_soon_is_blocked(self) -> None:
        from custom_components.vag_connect.companion.channel import (
            _WRITE_MIN_INTERVAL_S,
        )

        now, t = self._clock()
        tr = _SeqTransport([CLEAN])
        ch = CompanionChannel(tr, _WRITABLE_VW, time_fn=now)
        ch._version_ok = True
        await ch.do_action("start_climate")
        assert len(tr.taps) == 1
        t["v"] += _WRITE_MIN_INTERVAL_S / 2  # still inside the window
        with pytest.raises(CompanionWriteBlocked):
            await ch.do_action("start_climate")
        assert len(tr.taps) == 1  # the second tap never happened

    @pytest.mark.asyncio
    async def test_tap_allowed_after_the_interval(self) -> None:
        from custom_components.vag_connect.companion.channel import (
            _WRITE_MIN_INTERVAL_S,
        )

        now, t = self._clock()
        tr = _SeqTransport([CLEAN])
        ch = CompanionChannel(tr, _WRITABLE_VW, time_fn=now)
        ch._version_ok = True
        await ch.do_action("start_climate")
        t["v"] += _WRITE_MIN_INTERVAL_S + 1
        await ch.do_action("start_climate")
        assert len(tr.taps) == 2
