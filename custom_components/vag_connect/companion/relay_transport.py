# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Companion transport that speaks to an agent app over the outbound relay.

Where ``AddOnAdbTransport`` swaps the wire but keeps ADB's shell (it replaces
the four connection primitives and lets ``shell()`` carry everything), this one
cannot: a non-rooted phone has no shell for an app to run. It therefore
overrides the VERBS instead — dump, tap, back, foreground, version — and leaves
``shell()`` refusing, which is honest rather than silently broken.

Everything above the transport is unchanged. ``CompanionChannel`` calls the same
method names it always has, so the screen parsing, the presets, the nav walk and
the write quarantine neither know nor care that the phone is driving the
conversation.
"""
from __future__ import annotations

import logging

from .relay import CompanionRelayBroker
from .transport import CompanionTransportError, NetworkAdbTransport

_LOGGER = logging.getLogger(__name__)


class AgentRelayTransport(NetworkAdbTransport):
    """Drives the phone through its agent's outbound poll."""

    def __init__(
        self, broker: CompanionRelayBroker, *, wake_sleep: bool = False
    ) -> None:
        # No host/port and no ADB key: there is nothing for HA to dial. The base
        # class only stores them, and every method that used them is overridden.
        super().__init__("", 0, "", wake_sleep=wake_sleep)
        self._broker = broker

    # -- connection -----------------------------------------------------------

    async def connect(self, timeout_s: float = 10.0) -> None:
        """"Connected" means an agent is calling in, so wait for its poll."""
        await self._broker.wait_online(timeout_s)
        self._device = True

    async def close(self) -> None:
        self._device = None

    @property
    def connected(self) -> bool:
        return self._device is not None and self._broker.online

    # -- the shell is deliberately absent -------------------------------------

    async def shell(self, cmd: str, timeout_s: float = 10.0) -> str:
        raise CompanionTransportError(
            "the companion agent speaks a fixed set of screen verbs, not a "
            "shell; this transport cannot run arbitrary commands"
        )

    # -- operations -----------------------------------------------------------

    async def dump_ui(self, timeout_s: float = 15.0) -> str:
        """Ask the agent for the visible accessibility tree as uiautomator XML.

        The agent serialises Android's live accessibility node tree into the same
        XML shape ``uiautomator dump`` produces, so ``screen.parse_ui_dump`` and
        every selector in the presets work unchanged across all three transports.
        """
        xml = await self._broker.command("dump_ui", timeout_s=timeout_s)
        return str(xml or "")

    async def foreground_app(self, package: str, timeout_s: float = 10.0) -> None:
        await self._broker.command(
            "foreground", {"package": package}, timeout_s=timeout_s
        )

    async def is_foreground(self, package: str, timeout_s: float = 10.0) -> bool:
        got = await self._broker.command(
            "is_foreground", {"package": package}, timeout_s=timeout_s
        )
        return bool(got)

    async def current_app_version(self, package: str) -> str | None:
        """The manufacturer app's version, as the agent reads it on-device.

        Returns None on any failure rather than raising: the channel treats an
        unknown version as "do not tap", which is the safe outcome, and a plain
        overview read keeps working.
        """
        try:
            got = await self._broker.command("app_version", {"package": package})
        except CompanionTransportError:
            _LOGGER.debug("companion relay: could not read the app version")
            return None
        return str(got) if got else None

    async def tap(self, x: int, y: int, timeout_s: float = 10.0) -> None:
        await self._broker.command(
            "tap", {"x": int(x), "y": int(y)}, timeout_s=timeout_s
        )

    async def swipe(
        self,
        x1: int,
        y1: int,
        x2: int,
        y2: int,
        duration_ms: int = 300,
        timeout_s: float = 10.0,
    ) -> None:
        await self._broker.command(
            "swipe",
            {
                "x1": int(x1),
                "y1": int(y1),
                "x2": int(x2),
                "y2": int(y2),
                "duration_ms": int(duration_ms),
            },
            timeout_s=timeout_s,
        )

    async def key_back(self, timeout_s: float = 10.0) -> None:
        await self._broker.command("back", timeout_s=timeout_s)

    async def wake(self, timeout_s: float = 10.0) -> None:
        await self._broker.command("wake", timeout_s=timeout_s)

    async def sleep_if_enabled(self, timeout_s: float = 10.0) -> None:
        """Put the display back to sleep after a read, when the user opted in.

        Best-effort exactly like the ADB transports: failing to dim a screen must
        never turn a good read into a failed poll.
        """
        if not self._wake_sleep:
            return
        try:
            await self._broker.command("sleep", timeout_s=timeout_s)
        except CompanionTransportError:
            _LOGGER.debug("companion relay: sleep-after-read did not go through")
