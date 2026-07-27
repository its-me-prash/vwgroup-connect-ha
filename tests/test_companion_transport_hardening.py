# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Companion transport hardening, adapted from ckomma/charge-app-connector-vw
(Apache-2.0) issue reports. The device is mocked; only the shell command
SEQUENCE and the resulting behaviour are asserted.
"""
from __future__ import annotations

import pytest

from custom_components.vag_connect.companion.transport import (
    CompanionTransportError,
    NetworkAdbTransport,
)


class _RecordingDevice:
    """Stands in for adb-shell's AdbDeviceTcp. Records every shell() command
    and returns canned output per command substring."""

    def __init__(self, responses: dict[str, str]) -> None:
        self.calls: list[str] = []
        self._responses = responses
        self.available = True

    def shell(self, cmd: str, *_a, **_k) -> str:
        self.calls.append(cmd)
        for needle, out in self._responses.items():
            if needle in cmd:
                return out
        return ""


def _transport(device) -> NetworkAdbTransport:
    t = NetworkAdbTransport("1.2.3.4", 5555, "/tmp/key")
    t._device = device
    return t


class TestStaleDumpFileGuard:
    """ckomma #20/#22 — a failed dump must not resurface the previous screen."""

    @pytest.mark.asyncio
    async def test_dump_is_removed_before_it_is_written(self) -> None:
        dev = _RecordingDevice({
            "cat": '<?xml version="1.0"?><hierarchy><node/></hierarchy>',
        })
        t = _transport(dev)
        await t.dump_ui()
        rm_idx = next(i for i, c in enumerate(dev.calls) if c.startswith("rm -f"))
        dump_idx = next(i for i, c in enumerate(dev.calls) if "uiautomator dump" in c)
        cat_idx = next(i for i, c in enumerate(dev.calls) if c.startswith("cat "))
        assert rm_idx < dump_idx < cat_idx, (
            "the stale dump must be removed BEFORE the new dump and cat"
        )

    @pytest.mark.asyncio
    async def test_failed_dump_yields_no_data_not_stale(self) -> None:
        # rm succeeded, uiautomator failed to write, so cat returns empty (the
        # file is gone). Must raise, not return a previous <hierarchy>.
        dev = _RecordingDevice({"cat": ""})  # empty file after rm + failed dump
        t = _transport(dev)
        with pytest.raises(CompanionTransportError):
            await t.dump_ui()

    @pytest.mark.asyncio
    async def test_a_good_dump_still_returns_the_xml(self) -> None:
        xml = '<?xml version="1.0"?><hierarchy rotation="0"><node text="x"/></hierarchy>'
        dev = _RecordingDevice({"cat": xml})
        t = _transport(dev)
        assert await t.dump_ui() == xml


class TestReliabilityPrimitives:
    """ckomma #21 / #23a — wake, foreground-skip, back key."""

    @pytest.mark.asyncio
    async def test_wake_sends_wakeup_keyevent(self) -> None:
        dev = _RecordingDevice({})
        await _transport(dev).wake()
        assert any("keyevent 224" in c for c in dev.calls)

    @pytest.mark.asyncio
    async def test_key_back_sends_back_keyevent(self) -> None:
        dev = _RecordingDevice({})
        await _transport(dev).key_back()
        assert any("keyevent 4" in c for c in dev.calls)

    @pytest.mark.asyncio
    async def test_foreground_skips_relaunch_when_already_frontmost(self) -> None:
        pkg = "com.volkswagen.weconnect"
        dev = _RecordingDevice({
            "dumpsys": f"  mResumedActivity: ActivityRecord{{{pkg}/.MainActivity}}",
        })
        await _transport(dev).foreground_app(pkg)
        assert not any("monkey" in c for c in dev.calls), (
            "must not relaunch an already-foreground app"
        )
        assert any("keyevent 224" in c for c in dev.calls), "must still wake"

    @pytest.mark.asyncio
    async def test_foreground_relaunches_when_not_frontmost(self) -> None:
        pkg = "com.volkswagen.weconnect"
        dev = _RecordingDevice({"dumpsys": "  mResumedActivity: something.else/.X"})
        await _transport(dev).foreground_app(pkg)
        assert any("monkey" in c and pkg in c for c in dev.calls)

    @pytest.mark.asyncio
    async def test_swipe_emits_input_swipe(self) -> None:
        dev = _RecordingDevice({})
        await _transport(dev).swipe(100, 800, 100, 400, 300)
        assert any(c.startswith("input swipe 100 800 100 400 300") for c in dev.calls)
