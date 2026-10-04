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

import asyncio
import logging
import time
from typing import Callable

from .presets import (
    ACTION_TO_COMMAND,
    ActionSelector,
    BrandPreset,
    NavReadSelector,
)
from .screen import (
    UiNode,
    find_action_node,
    find_node_for,
    find_overlay,
    find_rate_limit_banner,
    find_sync_age,
    has_anchor,
    parse_ui_dump,
    read_fields,
    read_selectors,
    screen_bounds,
    tap_point_for,
)
from .transport import CompanionTransportError, NetworkAdbTransport
from .resources import (
    find_battery_control,
    find_battery_tile,
    find_settings_entry,
    read_battery_resources,
)
from .charge_target import (
    ChargeTargetRow,
    find_charge_target_row,
    find_save_button,
    is_syncing,
    snap_target,
)

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
_SETTLE_MAX_DUMPS = 2              # dumps spent waiting for a Compose screen to
                                   # stop changing after a tap: one to read it,
                                   # one to confirm it stopped moving (v4.4.0).
                                   # Kept deliberately tight — over ADB a
                                   # uiautomator dump is a round trip of a
                                   # second or more, so a four-step walk would
                                   # otherwise spend half a minute dumping.
_NAV_READ_INTERVAL_S = 900.0       # C9: a forward-nav READ (into charge detail)
                                   # runs at most every 15 min, NOT every poll —
                                   # it taps the app, so it stays infrequent and
                                   # the value is cached in between
_SLIDER_TRIES = 3                  # charge-limit taps, each read back, before
                                   # giving up without saving
_SAVE_POLLS = 15                   # dumps to wait for the app to confirm a save


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
        nav_opt_ins: "frozenset[str] | set[str] | None" = None,
    ) -> None:
        self._t = transport
        self._preset = preset
        self._now = time_fn
        # C9 opt-in. A forward-nav read TAPS the app on a schedule, so it stays
        # OFF by default until a user opts in (and until the flow is confirmed on
        # a real device). Off ⇒ the read path never taps forward at all.
        self._read_charge_detail = read_charge_detail
        # v4.4.0 — nav paths are grouped, and every group has its own opt-in, so
        # enabling the one-tap charge-detail read never starts a three-tap walk
        # through the navigation screens. ``read_charge_detail`` remains the
        # spelling of the original C9 group.
        opt_ins = set(nav_opt_ins or ())
        if read_charge_detail:
            opt_ins.add("charge_detail")
        self._nav_opt_ins = frozenset(opt_ins)
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
        # After a command, only the detail path that command used is re-read on
        # the next poll; the other opted-in paths keep their own cadence.
        self._nav_only: set[str] = set()
        self._screen_lock = asyncio.Lock()
        self._battery_strings: dict[str, set[str]] = {}
        self._strings_version: str | None = None
        self._strings_at: float | None = None

    @property
    def preset(self) -> BrandPreset:
        return self._preset

    @property
    def writes_enabled(self) -> bool:
        """Whether writes are currently allowed, with all gates applied."""
        return (
            bool(self._version_ok)
            and self._preset.writable
            and any(
                a.app_versions is None or self._live_app_version in a.app_versions
                for a in self._preset.actions
            )
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
            bool(self._nav_opt_ins)
            and bool(self._version_ok)
            and not self._is_rate_limited()
        )

    def _nav_allowed(self, nav: "NavReadSelector") -> bool:
        """Whether this specific nav path's own opt-in is on.

        Each path is separately opted into (``charge_detail``, ``vehicle_health``,
        ``climate_detail``, ``parking_position``): a deeper walk taps the app
        more, so it must never ride along on a shallower opt-in.
        """
        return nav.opt_in in self._nav_opt_ins and bool(nav.path)

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
        """Serialize the entire screen read with command navigation."""
        async with self._screen_lock:
            return await self._read_serialized()

    async def _read_serialized(self) -> dict[str, object] | None:
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
            # v4.9.0 (#1552) — if the close-app opt-in is on, force-stop the car
            # app after every poll so the next read relaunches it fresh instead of
            # scraping a stale cached screen. No-op otherwise. Optional transport
            # capability, so guard for a transport that does not implement it.
            _fstop = getattr(self._t, "force_stop_if_enabled", None)
            if _fstop is not None:
                await _fstop(self._preset.package)
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
        if self._preset.brand == "volkswagen":
            fields.update(read_battery_resources(nodes, self._battery_strings))
        # v2.26.0 (C9) — values behind a detail screen (charge target/power/time
        # on VW) are read by tapping a tile, reading, and coming BACK. Only tap
        # when it is opted in, the version gate holds, and the cadence window has
        # elapsed; between those refreshes the cache re-supplies the detail values
        # so the sensors don't flap.
        # #1552 — run the scheduled refresh BEFORE re-applying the cache. Filling
        # from the cache first made _augment_via_nav see every target already
        # populated (its all()-guard) and skip the walk forever after the first
        # read, so the detail sensors froze. Refresh first (against the true
        # overview state), then let the cache only backfill gaps on non-due polls.
        if self._preset.nav_reads:
            if self.nav_reads_enabled and (self._nav_due() or self._nav_only):
                await self._augment_via_nav(fields)
            for key, val in self._nav_cache.items():
                fields.setdefault(key, val)
        return fields

    async def _augment_via_nav(self, fields: dict[str, object]) -> None:
        """Fill missing nav-read targets by opening their detail screen.

        Best-effort: a nav-read that fails (tile not found, transport blip)
        leaves its fields absent rather than raising, and we always return to
        the overview afterwards so the next plain read sees the main screen.
        Successful values are cached and re-applied on later polls.
        """
        only, self._nav_only = self._nav_only, set()
        if not only or self._nav_due():
            only = set()
            self._last_nav_at = self._now()
        for nav in self._preset.nav_reads:
            if not self._nav_allowed(nav):
                continue  # this path's own opt-in is off
            if only and nav.name not in only:
                continue  # a command's readback re-reads its own path only
            if all(fields.get(v.target) is not None for v in nav.values):
                continue  # nothing to fetch from this detail
            walked = 0
            try:
                detail, walked = await self._walk_to_detail(nav.path)
                if detail is not None:
                    values = read_selectors(detail, nav.values)
                    if self._preset.brand == "volkswagen" and nav.name == "charge_detail":
                        values.update(read_battery_resources(detail, self._battery_strings))
                    for key, val in values.items():
                        # #1552 — a fresh detail-screen value wins over a stale
                        # overview value for the same key (direct assign, not
                        # setdefault); the overview reading is what goes stale.
                        fields[key] = val
                        self._nav_cache[key] = val
            except CompanionTransportError:
                _LOGGER.debug(
                    "companion %s: nav read '%s' hit a transport error; skipping",
                    self._preset.brand, nav.name,
                )
            finally:
                # Back out exactly as far as we actually walked. A path that
                # stopped early (a step not on screen) must not press BACK for
                # taps it never made, or it would leave the app somewhere behind
                # the overview for the next poll.
                await self._return_to_overview(min(walked, nav.back_presses))

    async def _walk_to_detail(
        self, steps: "tuple[ActionSelector, ...]"
    ) -> tuple[list[UiNode] | None, int]:
        """Tap an ordered path of controls and return (detail_nodes, taps_made).

        Stops without tapping as soon as a step is not on the current screen, so
        we never tap into the dark on a layout that moved; the caller backs out
        by however many taps actually happened. Overlays are cleared before
        every step and after the last one.
        """
        taps = 0
        detail: list[UiNode] | None = None
        # What the previous step already settled, so a step never dumps a
        # screen its predecessor just finished reading.
        pending: str | None = None
        for step in steps:
            nodes, cleared = await self._dump_and_clear_overlays(pending)
            pending = None
            if not cleared:
                return None, taps
            if find_rate_limit_banner(nodes, self._preset) is not None:
                self._trip_rate_limit()
                return None, taps
            if step.scroll_first and find_node_for(nodes, step) is None:
                # The MEB overview keeps Vehicle Health and Settings below the
                # fold. Scroll once, then look again; a control that is still
                # absent stops the walk as usual.
                nodes = await self._scroll_up(nodes)
            node = find_node_for(nodes, step)
            if step.action == "open_charge_detail" and node is None:
                node = find_battery_tile(nodes, self._battery_strings)
            if step.action == "open_vehicle_settings" and node is None:
                node = find_settings_entry(nodes, self._battery_strings)
            point = tap_point_for(node, step.tap_fraction) if node is not None else None
            if point is None:
                _LOGGER.debug(
                    "companion %s: nav step '%s' is not on the current screen; "
                    "stopping the walk here rather than tapping blind",
                    self._preset.brand, step.action,
                )
                return None, taps
            await self._t.tap(*point)
            taps += 1
            # A Compose screen renders in stages, so the tree right after a tap
            # is routinely half-built. Wait for it to stop changing before the
            # next step reads it, or a step lands on a screen that has moved.
            pending = await self._settle()
        detail, cleared = await self._dump_and_clear_overlays(pending)
        return (detail if cleared else None), taps

    async def _scroll_up(self, nodes: list[UiNode]) -> list[UiNode]:
        """Swipe the current screen up by half a display, best-effort.

        Expressed in fractions of the screen the phone actually reports, so it
        does not depend on the display the flow was first written against. A
        transport without ``swipe`` (or a screen we cannot measure) simply
        leaves the tree as it was.
        """
        box = screen_bounds(nodes)
        swipe = getattr(self._t, "swipe", None)
        if box is None or swipe is None:
            return nodes
        left, top, right, bottom = box
        mid_x = (left + right) // 2
        height = bottom - top
        try:
            await swipe(
                mid_x, top + int(height * 0.80),
                mid_x, top + int(height * 0.35),
                500,
            )
        except CompanionTransportError:
            return nodes
        scrolled, cleared = await self._dump_and_clear_overlays()
        return scrolled if cleared else nodes

    async def _settle(self) -> str | None:
        """Dump until the tree stops changing, and hand the result back.

        Returns the settled XML so the caller can read the screen it just
        waited for instead of dumping it a third time. That matters on ADB,
        where every dump is a round trip: re-reading what we already have is
        the difference between a walk that takes a few seconds and one that
        takes most of a minute.
        """
        previous: str | None = None
        for _ in range(_SETTLE_MAX_DUMPS):
            try:
                current = await self._t.dump_ui()
            except CompanionTransportError:
                return previous
            if current == previous:
                return current
            previous = current
        return previous

    async def _return_to_overview(self, presses: int = 1) -> None:
        """Walk back to the overview so the next plain read sees the main screen.

        v4.4.0 — prefer the app's OWN up/close control over Android's global
        BACK wherever the preset names one. Global BACK is not bounded by the
        app: from a shallow navigation stack (or from the share sheet at the
        end of the position walk) it can leave the app entirely, and the next
        poll then finds a launcher instead of a car. Tapping the app's own
        close button cannot do that.

        Stops early once the overview's anchor is on screen, so a path that
        came back on its own does not get pressed past it. Bounded and
        failure-soft throughout: a transport blip here must not turn a good
        read into an error.
        """
        for _ in range(max(0, presses)):
            try:
                nodes, _cleared = await self._dump_and_clear_overlays()
            except CompanionTransportError:
                return
            if self._preset.screen_anchor is not None and has_anchor(
                nodes, self._preset
            ):
                return
            up_point: tuple[int, int] | None = None
            for spec in self._preset.up_controls:
                candidate = find_node_for(nodes, spec)
                if candidate is not None and candidate.tap_point is not None:
                    up_point = candidate.tap_point
                    break
            try:
                if up_point is not None:
                    await self._t.tap(*up_point)
                else:
                    await self._t.key_back()
            except CompanionTransportError:
                return

    async def _dump_and_clear_overlays(
        self, known_xml: str | None = None
    ) -> tuple[list[UiNode], bool]:
        """Dump the screen; if a known overlay is up, BACK past it and re-dump.

        v2.26.0 (ckomma #8/#13/#20). Returns (parsed_nodes, cleared). ``cleared``
        is False when an overlay is still present after the capped retries, so
        the caller can decline to read/tap the wrong screen. BACK-only, so this
        is safe to run on the read-only brands too.

        v4.4.0 — ``known_xml`` lets a caller that has just settled a screen pass
        what it already read instead of paying for another dump. Overlay
        handling is unchanged: if one turns out to be up, it is dismissed and
        the screen re-read as before.
        """
        xml = known_xml if known_xml is not None else await self._t.dump_ui()
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

        Called on every read and command, including before the first poll.
        Resource labels refresh on a version change or once an hour so newly
        installed language splits can be picked up without restarting HA.
        """
        self._live_app_version = await self._t.current_app_version(self._preset.package)
        self._version_ok = self._decide_version_ok(self._live_app_version)
        getter = getattr(self._t, "battery_strings", None)
        if self._preset.brand == "volkswagen" and getter is not None and (
            self._strings_at is None or self._strings_version != self._live_app_version
            or self._now() - self._strings_at >= 3600
        ):
            self._strings_at = self._now()
            self._strings_version = self._live_app_version
            self._battery_strings = {}
            try:
                self._battery_strings = await getter(self._preset.package)
            except CompanionTransportError:
                _LOGGER.debug("companion: app translation resources unavailable")

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
        """Keep polling from moving the screen during a command."""
        async with self._screen_lock:
            await self._do_action_serialized(action)

    async def _do_action_serialized(self, action: str) -> None:
        """Tap the control for a logical action, subject to the quarantine.

        Raises ``CompanionWriteBlocked`` with a clear reason rather than tapping
        into the dark. That reason is what the coordinator surfaces to the user.
        """
        if action == "set_charge_target":
            raise CompanionWriteBlocked("the charge limit needs a target value")
        spec, nodes = await self._command_gate(action)
        walked = 0
        nav = next((n for n in self._preset.nav_reads if n.name == spec.nav_read), None)
        try:
            if spec.nav_read:
                if nav is None:
                    raise CompanionWriteBlocked("command detail path is not mapped")
                # A detail already open needs no forward tap. The SoC node
                # proves this is the charge sheet, not an overview label.
                on_detail = any(
                    n.resource_id == "rangeArcBatterySoc"
                    or n.resource_id.endswith("/rangeArcBatterySoc") for n in nodes
                )
                if not on_detail:
                    detail, walked = await self._walk_to_detail(nav.path)
                    if detail is None:
                        raise CompanionWriteBlocked("could not open the charge detail")
                    nodes = detail
            if find_rate_limit_banner(nodes, self._preset) is not None:
                self._trip_rate_limit()
                raise CompanionWriteBlocked("a rate-limit banner is up; commands paused")
            if self._battery_strings and action in ("start_charging", "stop_charging"):
                node = find_battery_control(nodes, self._battery_strings, action)
            else:
                node = find_action_node(nodes, self._preset, action)
                # The Compose enabled flag stays true even for a disabled CTA
                # (@gszigethy, target reached). Its hint is the actual gate.
                if node is not None and "Check charging status" in node.content_desc:
                    node = None
            if node is None or node.tap_point is None:
                raise CompanionWriteBlocked(
                    f"could not find the '{action}' control on the current screen"
                )
            # Prevent repeated taps even if a transport fails after delivery.
            self._last_write_at = self._now()
            # Re-read this command's own detail path on the next poll: a
            # delivered tap is not proof that the vehicle accepted it, and the
            # cached pre-command values are not readback. Other paths keep
            # their cadence, so a command never triggers a walk of every screen.
            if nav is not None:
                for value in nav.values:
                    self._nav_cache.pop(value.target, None)
                self._nav_only.add(nav.name)
            await self._t.tap(*node.tap_point)
        except CompanionTransportError as err:
            raise CompanionWriteBlocked(str(err)) from err
        finally:
            if nav is not None:
                await self._return_to_overview(min(walked, nav.back_presses))

    async def set_charge_target(self, target: float) -> int:
        """Set the vehicle Settings charge limit; returns the value saved.

        The slider snaps to 50 … 100 % in 10 % steps, so the request is snapped
        the same way. Moving the slider sends nothing; Save does. Every slider
        tap is read back from the row's own percentage before Save is pressed,
        and the change counts only once the app leaves edit mode with the new
        value on screen.
        """
        async with self._screen_lock:
            return await self._set_charge_target_serialized(snap_target(target))

    async def _set_charge_target_serialized(self, target: int) -> int:
        spec, nodes = await self._command_gate("set_charge_target")
        nav = next((n for n in self._preset.nav_reads if n.name == spec.nav_read), None)
        if nav is None:
            raise CompanionWriteBlocked("the vehicle Settings path is not mapped")
        try:
            row = find_charge_target_row(nodes)
            if row is None:
                detail, _walked = await self._walk_to_detail(nav.path)
                row = find_charge_target_row(detail) if detail is not None else None
            if row is None:
                raise CompanionWriteBlocked(
                    "could not find the charge limit on the vehicle Settings screen"
                )
            if row.current == target:
                return target  # nothing to change, nothing sent
            await self._move_charge_slider(row, target)
            # Save is the one tap that sends. Stamp first, so a transport that
            # fails after delivery still blocks an immediate repeat.
            nodes, _cleared = await self._dump_and_clear_overlays()
            save = find_save_button(nodes)
            if save is None or save.tap_point is None:
                raise CompanionWriteBlocked("the app did not offer Save for the new limit")
            self._last_write_at = self._now()
            self._nav_cache.pop("target_soc", None)
            await self._t.tap(*save.tap_point)
            await self._await_charge_target_saved(target)
            self._nav_cache["target_soc"] = target
            return target
        except CompanionTransportError as err:
            raise CompanionWriteBlocked(str(err)) from err
        finally:
            # The app's own toolbar button: Back after a save, and Cancel (which
            # discards the unsaved position) if anything stopped us before it.
            await self._return_to_overview(2)

    async def _move_charge_slider(self, row: ChargeTargetRow, target: int) -> None:
        """Tap the track until the row reads ``target``; a tap sends nothing."""
        aim = target
        for _ in range(_SLIDER_TRIES):
            await self._t.tap(*row.tap_point(aim))
            nodes, cleared = await self._dump_and_clear_overlays()
            seen = find_charge_target_row(nodes)
            if seen is None and not cleared:
                raise CompanionWriteBlocked("a dialog covered the charge limit")
            if seen is None:
                # A Compose screen can be caught half-drawn; look once more
                # before deciding something is in the way.
                settled = await self._settle()
                seen = find_charge_target_row(parse_ui_dump(settled or ""))
            if seen is None:
                # The Battery Care note can open over the row once, after the
                # value is already set. It is information, not a question; the
                # one BACK closes only it, and the row must then be there again.
                await self._t.key_back()
                nodes, _cleared = await self._dump_and_clear_overlays()
                seen = find_charge_target_row(nodes)
                if seen is None:
                    raise CompanionWriteBlocked(
                        "the app showed a note over the charge limit that did not close"
                    )
            if seen.current == target:
                return
            # Correct by what the slider actually did; the steps are wide, so
            # this only matters if the layout drifted.
            aim = snap_target(aim + (target - seen.current))
            row = seen
        raise CompanionWriteBlocked(
            f"the charge limit slider did not reach {target} %; nothing was saved"
        )

    async def _await_charge_target_saved(self, target: int) -> None:
        """Wait for the app to finish sending; fail unless it confirms."""
        for _ in range(_SAVE_POLLS):
            nodes, _cleared = await self._dump_and_clear_overlays()
            if find_rate_limit_banner(nodes, self._preset) is not None:
                self._trip_rate_limit()
                raise CompanionWriteBlocked("a rate-limit banner is up; commands paused")
            if is_syncing(nodes):
                continue
            if self._preset.screen_anchor is not None and has_anchor(nodes, self._preset):
                return  # the app closed Settings after saving
            row = find_charge_target_row(nodes)
            if row is not None and find_save_button(nodes) is None:
                if row.current == target:
                    return
                raise CompanionWriteBlocked(
                    f"the app shows {row.current} % after saving, not {target} %"
                )
            if row is None:
                # Neither Settings nor the overview: the app's error screen.
                raise CompanionWriteBlocked(
                    "the app reported a problem saving the charge limit"
                )
        raise CompanionWriteBlocked(
            "the app did not confirm saving the charge limit; check it in the app"
        )

    async def _command_gate(self, action: str) -> tuple[ActionSelector, list[UiNode]]:
        """Every guard a command passes before its first tap.

        Returns the action's selector and the current screen with any nag
        screen cleared.
        """
        if action not in ACTION_TO_COMMAND:
            raise CompanionWriteBlocked(f"unknown companion action: {action}")
        if not self._preset.writable:
            raise CompanionWriteBlocked(
                f"the {self._preset.brand} companion preset is experimental and "
                "read-only; writing would risk tapping the wrong control. It "
                "needs a confirmed screen map from a real device first."
            )
        # Refresh before EVERY command: an app update between polls must not
        # inherit the previous version's permission to tap.
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
        spec = next((a for a in self._preset.actions if a.action == action), None)
        if spec is None:
            raise CompanionWriteBlocked(f"no confirmed control for '{action}'")
        if spec.app_versions and self._live_app_version not in spec.app_versions:
            raise CompanionWriteBlocked(
                f"'{action}' is not mapped for app version {self._live_app_version}"
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
        if find_rate_limit_banner(nodes, self._preset) is not None:
            self._trip_rate_limit()
            raise CompanionWriteBlocked("a rate-limit banner is up; commands paused")
        return spec, nodes
