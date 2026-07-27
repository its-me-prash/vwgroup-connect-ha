# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Companion channel orchestration — v3.0.0-alpha.

Ties the transport and the screen parser to a brand preset, and adds the two
safety layers that keep this from misbehaving against the car:

- **Failure cooldown.** After a transport failure the channel backs off for a
  fixed window instead of retrying every poll, so a phone that is asleep or off
  the network does not turn into a per-poll error storm. Read cadence in the
  healthy case is simply the coordinator's ``scan_interval`` — a uiautomator
  dump reads the LOCAL screen and generates no manufacturer-backend traffic of
  its own, so there is no abuse argument for a second, private read budget on
  top of the interval the user already controls.
- **Write quarantine.** Writes require a verified preset AND a live app version
  that matches the one the preset was built against. A version drift disables
  writes but leaves reads running, because a stale tap map is how you tap the
  wrong control on a real car.

The cooldown clock is injected (``time_fn``) so the whole thing is testable
without sleeping or touching a device.
"""
from __future__ import annotations

import logging
from typing import Callable

from .presets import ACTION_TO_COMMAND, BrandPreset
from .screen import (
    UiNode,
    find_action_node,
    find_overlay,
    parse_ui_dump,
    read_fields,
)
from .transport import CompanionTransportError, NetworkAdbTransport

_LOGGER = logging.getLogger(__name__)

_FAILURE_COOLDOWN_S = 1800.0        # 30 min after any transport failure
_OVERLAY_MAX_DISMISS = 3            # BACK presses before giving up on a nag screen
_WRITE_MIN_INTERVAL_S = 60.0       # min gap between taps, so we never drive into
                                   # a backend rate-limit / lockout (ckomma #21)


class CompanionWriteBlocked(RuntimeError):
    """A write was refused by the quarantine, with a human-readable reason."""


class CompanionChannel:
    """One brand's read/write flow over one phone."""

    def __init__(
        self,
        transport: NetworkAdbTransport,
        preset: BrandPreset,
        *,
        time_fn: Callable[[], float],
    ) -> None:
        self._t = transport
        self._preset = preset
        self._now = time_fn
        self._cooldown_until: float = 0.0
        self._live_app_version: str | None = None
        self._writes_ok: bool | None = None  # decided on first read
        self._last_write_at: float | None = None  # write min-interval (ckomma #21)

    @property
    def preset(self) -> BrandPreset:
        return self._preset

    @property
    def writes_enabled(self) -> bool:
        """Whether writes are currently allowed, with all gates applied."""
        return bool(self._writes_ok) and self._preset.writable

    # -- read -----------------------------------------------------------------

    def _in_cooldown(self) -> bool:
        return self._now() < self._cooldown_until

    async def read(self) -> dict[str, object] | None:
        """Bring the app forward, dump the screen, resolve the preset fields.

        Returns:
          - ``None`` when the channel is in its post-failure cooldown: nothing
            was done, and the caller must NOT treat this as a failed or empty
            poll (otherwise a single failure would self-reinforce into a
            permanent "failed" state). The cooldown is short and clears on an
            HA restart, so it self-heals without user action.
          - ``{}`` when a read ran but matched no fields (a genuine empty
            screen).
          - a dict of matched fields otherwise.

        Read cadence in the healthy case is just the coordinator's poll
        interval; there is no separate per-read throttle. A transport failure
        trips the cooldown and re-raises, so the coordinator counts a real
        failure as a failed poll rather than a blank overwrite.
        """
        if self._in_cooldown():
            return None
        try:
            if not self._t.connected:
                await self._t.connect()
            await self._t.foreground_app(self._preset.package)
            # Decide the write quarantine on every read: the app can be updated
            # under us at any time.
            await self._refresh_write_gate()
            nodes, cleared = await self._dump_and_clear_overlays()
        except CompanionTransportError:
            self._cooldown_until = self._now() + _FAILURE_COOLDOWN_S
            raise
        if not cleared:
            # A nag/interstitial we could not dismiss is up; the screen behind it
            # is not the data screen. Return no fields rather than parsing the
            # overlay. The coordinator keeps last-known-good visible.
            return {}
        return read_fields(nodes, self._preset)

    async def _dump_and_clear_overlays(self) -> tuple[list[UiNode], bool]:
        """Dump the screen; if a known overlay is up, BACK past it and re-dump.

        v2.26.0 (ckomma #8/#13/#20). Returns (parsed_nodes, cleared). ``cleared``
        is False when an overlay is still present after the capped retries, so
        the caller can decline to read/tap the wrong screen. BACK-only, so this
        is safe to run on the read-only brands too.
        """
        xml = await self._t.dump_ui()
        for _ in range(_OVERLAY_MAX_DISMISS):
            nodes = parse_ui_dump(xml)
            overlay = find_overlay(nodes, self._preset)
            if overlay is None:
                return nodes, True
            _LOGGER.debug(
                "companion %s: dismissing overlay '%s' with BACK",
                self._preset.brand, overlay.name,
            )
            await self._t.key_back()
            xml = await self._t.dump_ui()
        nodes = parse_ui_dump(xml)
        still = find_overlay(nodes, self._preset)
        if still is not None:
            _LOGGER.warning(
                "companion %s: overlay '%s' did not clear after %d BACK presses",
                self._preset.brand, still.name, _OVERLAY_MAX_DISMISS,
            )
            return nodes, False
        return nodes, True

    async def _refresh_write_gate(self) -> None:
        """Read the live app version and (re)decide whether writes are allowed.

        Called on every read, and lazily by ``do_action`` when a command is
        issued before the first scheduled poll — otherwise ``_writes_ok`` would
        still be ``None`` and a perfectly valid command on the verified VW at the
        right version would be rejected as a version mismatch until the first
        poll (up to a full scan interval, and again after every restart).
        """
        self._live_app_version = await self._t.current_app_version(self._preset.package)
        self._writes_ok = self._decide_writes(self._live_app_version)

    def _decide_writes(self, live_version: str | None) -> bool:
        if not self._preset.writable:
            return False
        want = self._preset.verified_app_version
        if want is None:
            return False
        if live_version is None:
            # Could not read the version → do not risk a tap.
            _LOGGER.debug(
                "companion %s: could not read the app version; writes disabled "
                "until it is confirmed", self._preset.brand,
            )
            return False
        if live_version != want:
            _LOGGER.warning(
                "companion %s: app is %s but this preset was built for %s; "
                "writes are disabled until the preset is confirmed against the "
                "new version. Reads keep working.",
                self._preset.brand, live_version, want,
            )
            return False
        return True

    # -- write ----------------------------------------------------------------

    async def do_action(self, action: str) -> None:
        """Tap the control for a logical action, subject to the quarantine.

        Raises ``CompanionWriteBlocked`` with a clear reason rather than tapping
        into the dark. That reason is what the coordinator surfaces to the user.
        """
        if action not in ACTION_TO_COMMAND:
            raise CompanionWriteBlocked(f"unknown companion action: {action}")
        if not self._preset.writable:
            raise CompanionWriteBlocked(
                f"the {self._preset.brand} companion preset is experimental and "
                "read-only; writing would risk tapping the wrong control. It "
                "needs a confirmed screen map from a real device first."
            )
        # v3.0.0a1 — if no poll has decided the write gate yet (e.g. a command
        # issued right after startup, before the first scheduled read), decide
        # it now from the live app version rather than rejecting on the initial
        # ``None``. Needs the connection up first.
        if self._writes_ok is None:
            try:
                if not self._t.connected:
                    await self._t.connect()
                await self._t.foreground_app(self._preset.package)
                await self._refresh_write_gate()
            except CompanionTransportError as err:
                raise CompanionWriteBlocked(str(err)) from err
        if not self._writes_ok:
            raise CompanionWriteBlocked(
                f"writes are disabled for {self._preset.brand}: the app version "
                f"on the phone ({self._live_app_version or 'unknown'}) does not "
                f"match the one this preset was verified against "
                f"({self._preset.verified_app_version}). Reads still work."
            )
        # v2.26.0 (ckomma #21) — enforce a minimum gap between taps so a rapid
        # repeat (a stuck automation, a double press) can never drive the account
        # into a backend rate-limit or lockout.
        if self._last_write_at is not None:
            since = self._now() - self._last_write_at
            if since < _WRITE_MIN_INTERVAL_S:
                raise CompanionWriteBlocked(
                    f"a command was sent {int(since)}s ago; the companion "
                    f"channel keeps at least {int(_WRITE_MIN_INTERVAL_S)}s between "
                    "commands so it never looks like abuse to the backend"
                )
        try:
            if not self._t.connected:
                await self._t.connect()
            await self._t.foreground_app(self._preset.package)
            # v2.26.0 — dismiss any nag screen before locating the control, or
            # the BACK-safe overlay would sit on top of the button we tap.
            nodes, cleared = await self._dump_and_clear_overlays()
        except CompanionTransportError as err:
            raise CompanionWriteBlocked(str(err)) from err
        if not cleared:
            raise CompanionWriteBlocked(
                "a nag screen is up and did not clear; not tapping blind"
            )
        node = find_action_node(nodes, self._preset, action)
        if node is None or node.tap_point is None:
            raise CompanionWriteBlocked(
                f"could not find the '{action}' control on the current screen; "
                "the app may be on a different view than expected"
            )
        x, y = node.tap_point
        await self._t.tap(x, y)
        self._last_write_at = self._now()
