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
import time
from typing import Callable

from .presets import ACTION_TO_COMMAND, ActionSelector, BrandPreset
from .screen import (
    UiNode,
    find_action_node,
    find_node_for,
    find_overlay,
    find_rate_limit_banner,
    find_sync_age,
    parse_ui_dump,
    read_fields,
    read_selectors,
)
from .transport import CompanionTransportError, NetworkAdbTransport

_LOGGER = logging.getLogger(__name__)

_FAILURE_COOLDOWN_S = 1800.0        # 30 min base; the cooldown is ADAPTIVE and
_MAX_COOLDOWN_S = 6 * 3600.0       # doubles per consecutive failure up to 6 h,
                                   # so a phone that is off does not get retried
                                   # every 30 min forever (ckomma #16)
_OVERLAY_MAX_DISMISS = 3            # BACK presses before giving up on a nag screen
_WRITE_MIN_INTERVAL_S = 60.0       # min gap between taps, so we never drive into
                                   # a backend rate-limit / lockout (ckomma #21)
_RATE_LIMIT_BACKOFF_S = 12 * 3600  # 12 h after a rate-limit banner. Uses wall
                                   # clock so it can be PERSISTED across restarts
                                   # (ckomma #21: an account lockout must NOT be
                                   # cleared by a restart the way a TCP blip is)
_NAV_READ_INTERVAL_S = 900.0       # C9: a forward-nav READ (into charge detail)
                                   # runs at most every 15 min, NOT every poll —
                                   # it taps the app, so it stays infrequent and
                                   # the value is cached in between


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
        wall_clock_fn: Callable[[], float] | None = None,
        read_charge_detail: bool = False,
    ) -> None:
        self._t = transport
        self._preset = preset
        self._now = time_fn
        # C9 opt-in. A forward-nav read TAPS the app on a schedule, so it stays
        # OFF by default until a user opts in (and until the flow is confirmed on
        # a real device). Off ⇒ the read path never taps forward at all.
        self._read_charge_detail = read_charge_detail
        # Wall clock (unix seconds) for the rate-limit backoff only, because that
        # one must be persistable across restarts; ``_now`` (monotonic) is right
        # for the in-session failure cooldown. Injected for tests.
        self._wall = wall_clock_fn or time.time
        self._cooldown_until: float = 0.0
        self._consecutive_failures: int = 0  # drives the adaptive cooldown (#16)
        self._rate_limited_until: float = 0.0  # wall-clock; persisted (ckomma #21)
        self._source_data_age_s: float | None = None  # from the app's sync line
        self._live_app_version: str | None = None
        # v2.26.0 — "verified preset AND live app version matches the one it was
        # built against". Gates BOTH writes and forward-nav reads (C9); a wrong
        # tap is a wrong tap whether it is a command or a navigation. Decided on
        # first read/first command. NOT the same as writes_enabled, which also
        # requires ``writable`` — a verified-reads preset (VW today) has
        # version_ok True but no writes.
        self._version_ok: bool | None = None
        self._last_write_at: float | None = None  # write min-interval (ckomma #21)
        # C9 nav-read cadence + cache: nav taps at most every _NAV_READ_INTERVAL_S
        # and the values persist in between so the sensors don't flap.
        self._nav_cache: dict[str, object] = {}
        self._last_nav_at: float | None = None

    @property
    def preset(self) -> BrandPreset:
        return self._preset

    @property
    def writes_enabled(self) -> bool:
        """Whether writes are currently allowed, with all gates applied."""
        return (
            bool(self._version_ok)
            and self._preset.writable
            and not self._is_rate_limited()
        )

    @property
    def nav_reads_enabled(self) -> bool:
        """Whether a forward-nav READ (C9) may run.

        Requires the user opt-in (it taps the app), the same version gate as a
        write (a wrong tile tap is as bad as a wrong command), and no active
        rate-limit. NOT gated on ``writable``: reading the charge target is
        allowed even when command entities are quarantined.
        """
        return (
            self._read_charge_detail
            and bool(self._version_ok)
            and not self._is_rate_limited()
        )

    def _nav_due(self) -> bool:
        """True when a nav-read has never run or the cadence window elapsed."""
        return (
            self._last_nav_at is None
            or self._now() - self._last_nav_at >= _NAV_READ_INTERVAL_S
        )

    # -- rate-limit backoff (ckomma #21), wall-clock so it can be persisted ----

    @property
    def rate_limited_until(self) -> float:
        """Wall-clock unix time until which the channel is backed off (0 = not).

        The coordinator persists this so an account lockout survives a restart.
        """
        return self._rate_limited_until

    def restore_rate_limit(self, until: float) -> None:
        """Re-apply a persisted rate-limit backoff at setup."""
        if until and until > self._wall():
            self._rate_limited_until = float(until)

    def _is_rate_limited(self) -> bool:
        return self._wall() < self._rate_limited_until

    def _trip_rate_limit(self) -> None:
        self._rate_limited_until = self._wall() + _RATE_LIMIT_BACKOFF_S
        _LOGGER.warning(
            "companion %s: a rate-limit / lockout banner is up; backing off for "
            "%d h and disabling writes. This is a backend limit on the account, "
            "not a phone problem.", self._preset.brand, _RATE_LIMIT_BACKOFF_S // 3600,
        )

    # -- degraded / out-of-sync (ckomma #22/#16) ------------------------------

    @property
    def source_data_age_s(self) -> float | None:
        """Age of the CAR's data as the app itself reports it, or None.

        This is "how old is the data VW has", distinct from connector health: a
        working companion can still be showing a car that has not synced in
        hours. Exposed so the entity layer can surface a stale-data signal.
        """
        return self._source_data_age_s

    def reset_cooldown(self) -> None:
        """Clear any failure/rate-limit backoff (a user-initiated retry).

        Lets a stuck channel recover without waiting out the adaptive or
        rate-limit window (wired to an HA button/service on the entry).
        """
        self._cooldown_until = 0.0
        self._consecutive_failures = 0
        self._rate_limited_until = 0.0
        _LOGGER.debug("companion %s: backoff reset by request", self._preset.brand)

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
        if self._in_cooldown() or self._is_rate_limited():
            return None
        try:
            return await self._read_once()
        finally:
            # v2.26.0 (#974) — if the wake/sleep opt-in is on, put the display
            # back to sleep after every poll that woke it (including a failed or
            # nav-tapping one). No-op otherwise. Optional transport capability,
            # so guard for a transport that does not implement it.
            _sleep = getattr(self._t, "sleep_if_enabled", None)
            if _sleep is not None:
                await _sleep()

    async def _read_once(self) -> dict[str, object] | None:
        """The read body. ``read`` wraps this with the #974 sleep-after."""
        try:
            if not self._t.connected:
                await self._t.connect()
            await self._t.foreground_app(self._preset.package)
            # Decide the version gate on every read: the app can be updated
            # under us at any time.
            await self._refresh_version_gate()
            nodes, cleared = await self._dump_and_clear_overlays()
        except CompanionTransportError:
            # v2.26.0 (ckomma #16) — adaptive backoff: double the cooldown per
            # consecutive failure (capped), so a phone that is off / asleep is
            # not retried every 30 min indefinitely.
            self._consecutive_failures += 1
            backoff = min(
                _FAILURE_COOLDOWN_S * (2 ** (self._consecutive_failures - 1)),
                _MAX_COOLDOWN_S,
            )
            self._cooldown_until = self._now() + backoff
            raise
        # v2.26.0 (ckomma #21) — a rate-limit / lockout banner is not a nag to
        # dismiss; it means stop. Trip the long persisted backoff and return
        # no-data (last-known-good stays visible) rather than reading the
        # lockout screen.
        if find_rate_limit_banner(nodes, self._preset) is not None:
            self._trip_rate_limit()
            return None
        if not cleared:
            # A nag/interstitial we could not dismiss is up; the screen behind it
            # is not the data screen. Return no fields rather than parsing the
            # overlay. The coordinator keeps last-known-good visible.
            return {}
        # A real read succeeded: clear the adaptive backoff and record how old
        # the CAR's data is (ckomma #22, separate from connector health).
        self._consecutive_failures = 0
        self._source_data_age_s = find_sync_age(nodes, self._preset)
        fields = read_fields(nodes, self._preset)
        # v2.26.0 (C9) — values behind a detail screen (charge target/power/time
        # on VW) are read by tapping a tile, reading, and coming BACK. Re-apply
        # the cached detail values every poll so the sensors don't flap between
        # the (infrequent) nav refreshes; only actually tap when it is opted in,
        # the version gate holds, and the cadence window has elapsed.
        if self._preset.nav_reads:
            for key, val in self._nav_cache.items():
                fields.setdefault(key, val)
            if self.nav_reads_enabled and self._nav_due():
                await self._augment_via_nav(fields)
        return fields

    async def _augment_via_nav(self, fields: dict[str, object]) -> None:
        """Fill missing nav-read targets by opening their detail screen.

        Best-effort: a nav-read that fails (tile not found, transport blip)
        leaves its fields absent rather than raising, and we always return to
        the overview afterwards so the next plain read sees the main screen.
        Successful values are cached and re-applied on later polls.
        """
        self._last_nav_at = self._now()
        for nav in self._preset.nav_reads:
            if all(fields.get(v.target) is not None for v in nav.values):
                continue  # nothing to fetch from this detail
            try:
                detail = await self._open_detail(nav.tile)
                if detail is not None:
                    for key, val in read_selectors(detail, nav.values).items():
                        fields.setdefault(key, val)
                        self._nav_cache[key] = val
            except CompanionTransportError:
                _LOGGER.debug(
                    "companion %s: nav read '%s' hit a transport error; skipping",
                    self._preset.brand, nav.name,
                )
            finally:
                await self._return_to_overview()

    async def _open_detail(self, tile: ActionSelector) -> list[UiNode] | None:
        """Tap a tile to open its detail screen and return the parsed detail.

        Returns None (without tapping) when the tile is not on the current
        screen, so we never tap into the dark. Clears overlays before and after.
        """
        nodes, cleared = await self._dump_and_clear_overlays()
        if not cleared:
            return None
        node = find_node_for(nodes, tile)
        if node is None or node.tap_point is None:
            return None
        x, y = node.tap_point
        await self._t.tap(x, y)
        detail, cleared = await self._dump_and_clear_overlays()
        return detail if cleared else None

    async def _return_to_overview(self) -> None:
        """BACK out of a detail screen so the next plain read sees the overview.

        Bounded and failure-soft: a transport blip here must not turn a good
        read into an error.
        """
        try:
            await self._t.key_back()
        except CompanionTransportError:
            pass

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

    async def _refresh_version_gate(self) -> None:
        """Read the live app version and (re)decide whether the app matches the
        version this preset was verified against.

        Called on every read, and lazily by ``do_action`` when a command is
        issued before the first scheduled poll — otherwise ``_version_ok`` would
        still be ``None`` and a perfectly valid command on the verified VW at the
        right version would be rejected as a version mismatch until the first
        poll (up to a full scan interval, and again after every restart).
        """
        self._live_app_version = await self._t.current_app_version(self._preset.package)
        self._version_ok = self._decide_version_ok(self._live_app_version)

    def _decide_version_ok(self, live_version: str | None) -> bool:
        """True when this is a verified preset AND the live app version matches.

        Gates both writes and forward-nav reads. Independent of ``writable`` so
        a verified-reads preset (writes quarantined) can still nav-read.
        """
        if not self._preset.verified:
            return False
        want = self._preset.verified_app_version
        if want is None:
            return False
        # #968 — accept a SET of known-compatible versions (We Connect reports its
        # version inconsistently); a bare string stays a one-element set.
        want_set: tuple[str, ...] = (want,) if isinstance(want, str) else tuple(want)
        if live_version is None:
            # Could not read the version → do not risk a tap.
            _LOGGER.debug(
                "companion %s: could not read the app version; taps (writes and "
                "nav reads) disabled until it is confirmed", self._preset.brand,
            )
            return False
        if live_version not in want_set:
            _LOGGER.warning(
                "companion %s: app is %s but this preset was built for %s; "
                "taps (writes and nav reads) are disabled until the preset is "
                "confirmed against the new version. Overview reads keep working.",
                self._preset.brand, live_version, "/".join(want_set),
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
        # v3.0.0a1 — if no poll has decided the version gate yet (e.g. a command
        # issued right after startup, before the first scheduled read), decide
        # it now from the live app version rather than rejecting on the initial
        # ``None``. Needs the connection up first.
        if self._version_ok is None:
            try:
                if not self._t.connected:
                    await self._t.connect()
                await self._t.foreground_app(self._preset.package)
                await self._refresh_version_gate()
            except CompanionTransportError as err:
                raise CompanionWriteBlocked(str(err)) from err
        if not self._version_ok:
            _want = self._preset.verified_app_version
            _want_str = _want if isinstance(_want, str) else " / ".join(_want or ())
            raise CompanionWriteBlocked(
                f"writes are disabled for {self._preset.brand}: the app version "
                f"on the phone ({self._live_app_version or 'unknown'}) does not "
                f"match the one this preset was verified against "
                f"({_want_str}). Reads still work."
            )
        # v2.26.0 (ckomma #21) — if a rate-limit backoff is active, do not send.
        if self._is_rate_limited():
            raise CompanionWriteBlocked(
                f"the {self._preset.brand} companion channel is backed off after "
                "a rate-limit or lockout from the backend; commands are paused "
                "until it clears (this is an account-side limit, not the phone)"
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
