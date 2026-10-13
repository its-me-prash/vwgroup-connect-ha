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
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable, Literal

from ..const import COMPANION_NAV_MAX_AGE_S

from .presets import (
    ACTION_TO_COMMAND,
    CLIMATE_SETTING_ACTIONS,
    ActionSelector,
    BrandPreset,
    NavReadSelector,
    app_version_covered,
    app_version_listed,
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
    DEPARTURE_TILE,
    DRIVING_TILE,
    driving_tile_text,
    find_app_alert,
    find_battery_control,
    find_battery_tile,
    find_request_limit,
    find_settings_entry,
    find_tile_entry,
    is_power_budget_alert,
    power_budget_labels,
    read_battery_resources,
    read_climate_resources,
    read_departure_timers,
    read_driving_data,
    read_health_resources,
    read_overview_resources,
    read_settings_resources,
    trip_carousel_row,
)
from .departure import (
    TIMER_CANCEL,
    TIMER_SAVE,
    WEEKDAYS,
    TimerPage,
    departure_rows,
    find_toolbar_text,
    page_fields,
    read_timer_page,
)
from .charging_locations import (
    LOCATION_PARTS,
    charging_section_visible,
    location_rows,
    location_settings,
    location_timers,
    location_title,
    on_location_list,
    on_location_settings,
    settings_icon,
)
from .app_sync import find_sync_button
from .sync_time import find_sync_line
from .charge_target import (
    ChargeTargetRow,
    find_charge_target_row,
    find_save_button,
    is_syncing,
    snap_target,
)
from .climate_settings import (
    NAMES as CLIMATE_SETTING_NAMES,
    TOGGLES as CLIMATE_TOGGLES,
    find_save as find_climate_save,
    find_toggle,
    find_zone_switch,
    find_zones_back,
    find_zones_row,
    on_settings_page,
    on_zones_page,
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
_LIMIT_PROBE_GAP_S = 4 * 3600      # a power-budget pause lets one sync probe
                                   # through per 4 h: at most two in a 12 h
                                   # pause, against one per sync interval before
_SYNC_CONFIRM_DUMPS = 2            # plain dumps after an accepted-looking sync
                                   # tap, for a limit alert that draws late
_SETTLE_MAX_DUMPS = 2              # dumps spent waiting for a Compose screen to
                                   # stop changing after a tap: one to read it,
                                   # one to confirm it stopped moving (v4.4.0).
                                   # Kept deliberately tight — over ADB a
                                   # uiautomator dump is a round trip of a
                                   # second or more, so a four-step walk would
                                   # otherwise spend half a minute dumping.
_SLIDER_TRIES = 3                  # charge-limit taps, each read back, before
                                   # giving up without saving
_SLIDER_READS = 3                  # dumps per slider tap to see it redrawn
_SAVE_POLLS = 15                   # dumps to wait for the app to confirm a save
_SYNC_SCROLLS = 3                  # swipes down vehicle Settings to reach
                                   # "Synchronise now" (one is enough on 4.3.2)
_SCREEN_TRIES = 5                  # dumps to wait for the screen a tap should
                                   # produce (a dump is about a second on ADB)
_LIMIT_READBACK_DUMPS = 3          # dumps after a one-tap command, looking for
                                   # the request-limit alert (about 1 s late)
_DAY_TAPS = 16                     # weekday/Repeat taps, each read back, before
                                   # giving up on a timer page without saving
_CLOCK_TAPS = 40                   # one-step time wheel taps, each read back
                                   # (24 h: up to 12 hour + 6 minute steps)
# Walks whose values change only after a trip or with new car data (driving
# data, parking position, Vehicle Health) skip polls that cannot have changed
# them (``_walk_reason``).
_WALK_REFRESH_S = 12 * 3600        # re-read anyway, well inside the 24 h expiry
_WALK_NO_TILE_S = 6 * 3600         # re-read a trip walk this often while the
                                   # Driving data tile is not on the overview
_WALK_SETTLE_S = 10 * 60           # new car data counts once the sync time has
                                   # stood still this long: the car is parked


_LIMIT_REASON = (
    "the car refused the request: its daily request budget is used up (the app "
    "says too many requests were sent to the vehicle). Start the car to reset it; "
    "commands are paused until then, or until you press Reset companion connection"
)


class CompanionWriteBlocked(RuntimeError):
    """A write was refused by the quarantine, with a human-readable reason."""


class CompanionAppVersionUnverified(CompanionWriteBlocked):
    """Rule 9: a write on an app build that was not verified for writes.

    Carries a translation key so the user sees the refusal in their language.
    """

    translation_key = "companion_app_version_unverified"

    def __init__(self, version: str | None) -> None:
        super().__init__(
            f"commands are off on app version {version}: it has not been "
            "verified for commands yet, and writes stay off until it is. "
            "Reads still work."
        )
        self.translation_placeholders = {"version": str(version)}


REQUESTS_AVAILABLE = "available"
REQUESTS_RESTRICTED = "restricted"
# What tripped a request-limit pause (see _limit_kind_on).
LIMIT_POWER_BUDGET = "power_budget"
LIMIT_BACKEND = "backend"


# Phones an unloaded client may have left mid-command, by phone key: the
# monotonic time until which the next client waits before its first walk.
_UNSETTLED: dict[str, float] = {}


@dataclass(frozen=True)
class _WalkBasis:
    """What a gated walk's last read saw (``CompanionChannel._walk_reason``)."""

    at: float                       # wall clock of the walk
    trip: str | None                # the Driving data tile then
    synced_at: datetime | None      # the car's sync time then
    synced_precision_s: int         # that time's rounding
    ranges: tuple[object, object]   # electric and petrol range then


def mark_unsettled(keys: "tuple[str, ...]", settle_s: float) -> None:
    """An unload could not confirm the phone finished its last command."""
    until = time.monotonic() + settle_s
    for key in keys:
        _UNSETTLED[key] = max(_UNSETTLED.get(key, 0.0), until)


class _ScreenLock(asyncio.Lock):
    """The channel's screen lock, which turns new walks away once closing.

    On entry unload the client takes the lock with ``acquire_to_close``: the
    walk holding it finishes, cleanup included, and every read or command that
    queued behind it is refused when its turn comes instead of driving the
    phone under the reloaded entry's new client.

    The other way round, a new client's walk first waits out any settle period
    an unload left on the same phone (``mark_unsettled``), so a command the old
    connection could not confirm is done before this one dumps and taps.
    """

    def __init__(self) -> None:
        super().__init__()
        self.closing = False
        self.phone_keys: tuple[str, ...] = ()

    async def acquire(self) -> Literal[True]:
        await super().acquire()
        try:
            if self.closing:
                raise CompanionTransportError(
                    "the companion connection was closed when the entry unloaded"
                )
            await self._settle()
        except BaseException:
            self.release()
            raise
        return True

    async def _settle(self) -> None:
        until = max((_UNSETTLED.get(k, 0.0) for k in self.phone_keys), default=0.0)
        wait = until - time.monotonic()
        if wait > 0:
            _LOGGER.info(
                "companion: the previous connection may still be finishing a "
                "command; waiting %.0fs before the first walk", wait,
            )
            await asyncio.sleep(wait)
        now = time.monotonic()
        for key in self.phone_keys:
            if _UNSETTLED.get(key, now + 1) <= now:
                del _UNSETTLED[key]

    async def acquire_to_close(self) -> None:
        self.closing = True
        await super().acquire()


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
        # Which alert tripped the pause: LIMIT_POWER_BUDGET only for the app's
        # own power-budget alert, which sends nothing; None (a restored pause)
        # or LIMIT_BACKEND never lets the sync probe through.
        self._limit_kind: str | None = None
        self._limit_seen_kind: str | None = None  # of the last limit on screen
        self._limit_probe_at: float = 0.0  # wall clock of the trip or last probe
        self._source_data_age_s: float | None = None  # from the app's sync line
        # #968 — when the car last sent the app data, from the same line read
        # through the app's own translation tables. Newest estimate wins.
        self._seen_at: datetime | None = None
        self._seen_precision_s: int | None = None  # the last line's rounding
        # Gated walks (``_walk_reason``): what each last saw, the Driving data
        # tile now and as last seen, and a manual refresh waiting to run.
        self._walk_basis: dict[str, _WalkBasis] = {}
        self._trip_tile_now: str | None = None
        self._trip_tile: str | None = None
        # The trip tile as first read during a request-limit pause: a later,
        # different trip means the car was driven, so the pause can end.
        self._pause_trip_tile: str | None = None
        self._walk_all_next = False
        # #968 — what the vehicle sync flow last found; None until it has run.
        self._request_state: str | None = None
        self._live_app_version: str | None = None
        self._newer_logged: str | None = None  # last newer build logged
        # v2.26.0 — "verified preset AND live app version matches the one it was
        # built against". Gates BOTH writes and forward-nav reads (C9); a wrong
        # tap is a wrong tap whether it is a command or a navigation. Decided on
        # first read/first command. NOT the same as writes_enabled, which also
        # requires ``writable`` — a verified-reads preset (VW today) has
        # version_ok True but no writes.
        self._version_ok: bool | None = None
        self._last_write_at: float | None = None  # write min-interval (ckomma #21)
        # The same moment as wall clock, persisted next to the pause so a
        # restart cannot shorten the gap.
        self._last_write_wall: float = 0.0
        self._limit_trips = 0  # counts trips, so a cleanup can tell it saw one
        # C9 nav-read cache: the opted-in detail screens are re-read on every
        # app refresh (the poll interval is the only read cadence), and the
        # values persist between reads so a walk that misses one does not make
        # the sensors flap.
        self._nav_cache: dict[str, object] = {}
        self._nav_read_at: dict[str, float] = {}
        # Which nav read last supplied each cached key, so switching a read off
        # drops exactly its values.
        self._nav_cache_from: dict[str, str] = {}
        # After a command, only the detail path that command used is re-read on
        # the readback poll that follows it; every other poll walks all of the
        # opted-in paths.
        self._nav_only: set[str] = set()
        self._screen_lock = _ScreenLock()
        self._app_strings: dict[str, set[str]] = {}
        # (app version, split list) the current table was successfully read for.
        self._strings_ok_key: tuple[str | None, tuple[str, ...]] | None = None
        self._strings_try_key: tuple[str | None, tuple[str, ...]] | None = None
        self._strings_fails = 0
        self._strings_retry_at = 0.0
        self._strings_paths_now: tuple[str, ...] | None = None

    @property
    def preset(self) -> BrandPreset:
        return self._preset

    @property
    def live_app_version(self) -> str | None:
        """The app version last read from the phone."""
        return self._live_app_version

    @property
    def writes_enabled(self) -> bool:
        """Whether writes are currently allowed, with all gates applied."""
        return (
            bool(self._version_ok)
            and self._preset.writable
            and app_version_listed(self._live_app_version, self._preset.verified_app_version)
            and any(
                a.app_versions is None
                or app_version_listed(self._live_app_version, a.app_versions)
                for a in self._preset.actions
            )
            and not self._is_rate_limited()
        )

    @property
    def nav_reads_enabled(self) -> bool:
        """Whether a forward-nav READ (C9) may run.

        Requires the user opt-in (it taps the app), the same version gate as a
        write (a wrong tile tap is as bad as a wrong command). NOT gated on
        ``writable``: reading the charge target is allowed even when command
        entities are quarantined.

        #968 — nor on the request-limit pause: opening a detail sheet is app
        navigation, not a request to the car, and on 4.3.2 the battery level is
        narrated only on the sheet behind the range tile, so blocking the walk
        froze it at its cached value while the overview's range kept moving. A
        walk that meets the limit alert still stops there.
        """
        return bool(self._nav_opt_ins) and bool(self._version_ok)

    def _nav_allowed(self, nav: "NavReadSelector") -> bool:
        """Whether this specific nav path's own opt-in is on.

        Each path is separately opted into (``charge_detail``, ``vehicle_health``,
        ``climate_detail``, ``parking_position``): a deeper walk taps the app
        more, so it must never ride along on a shallower opt-in.
        """
        return nav.opt_in in self._nav_opt_ins and bool(nav.path)

    @property
    def nav_opt_ins(self) -> frozenset[str]:
        """The nav-read opt-ins currently on."""
        return self._nav_opt_ins

    def set_nav_opt_in(self, opt_in: str, enabled: bool) -> None:
        """Turn one nav-read opt-in on or off while running.

        On: its paths are read on the next poll. Off: the values it supplied leave the cache, so its entities
        stop showing a reading nobody refreshes any more.
        """
        opt_ins = set(self._nav_opt_ins)
        if enabled:
            opt_ins.add(opt_in)
            self._nav_only |= {n.name for n in self._preset.nav_reads if n.opt_in == opt_in}
        else:
            opt_ins.discard(opt_in)
            for key in [k for k, src in self._nav_cache_from.items() if src == opt_in]:
                self._nav_cache.pop(key, None)
                self._nav_cache_from.pop(key, None)
                self._nav_read_at.pop(key, None)
            for nav in self._preset.nav_reads:
                if nav.opt_in == opt_in:
                    self._walk_basis.pop(nav.name, None)
        self._nav_opt_ins = frozenset(opt_ins)
        self._read_charge_detail = "charge_detail" in self._nav_opt_ins

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
            self._limit_kind = None  # unknown: no sync probe until it runs out

    @property
    def last_write_at(self) -> float:
        """Wall-clock unix time of the last command tap (0 = none this run).

        Persisted with the pause, so the minimum gap between commands holds
        across a restart.
        """
        return self._last_write_wall

    def restore_last_write(self, at: float) -> None:
        """Re-apply a persisted last command time at setup."""
        if not at:
            return
        # A time in the future (a clock step) counts as just now.
        ago = max(0.0, self._wall() - float(at))
        if ago < _WRITE_MIN_INTERVAL_S:
            self._last_write_at = self._now() - ago
            self._last_write_wall = float(at)

    def restore_synced_at(self, seen: datetime) -> None:
        """Re-apply the last known car sync time at setup.

        The sync line only narrows from below, so a run that starts from
        nothing would put the time back by up to the line's rounding after
        every restart or reload. A time in the future (a clock step) is
        ignored.
        """
        if seen.tzinfo is None or seen.timestamp() > self._wall():
            return
        if self._seen_at is None or seen > self._seen_at:
            self._seen_at = seen

    def _stamp_write(self) -> None:
        self._last_write_at = self._now()
        self._last_write_wall = self._wall()

    def _is_rate_limited(self) -> bool:
        return self._wall() < self._rate_limited_until

    def _trip_rate_limit(self) -> None:
        was_limited = self._is_rate_limited()
        kind, self._limit_seen_kind = self._limit_seen_kind or LIMIT_BACKEND, None
        # A power-budget alert never softens a pause already running for
        # another (or an unknown) reason.
        if not was_limited or kind == LIMIT_BACKEND:
            self._limit_kind = kind
        self._limit_probe_at = self._wall()
        self._rate_limited_until = self._wall() + _RATE_LIMIT_BACKOFF_S
        self._limit_trips += 1
        self._request_state = REQUESTS_RESTRICTED
        if was_limited:
            # One alert is often seen by a command and then by its cleanup.
            _LOGGER.debug("companion %s: request limit still up", self._preset.brand)
            return
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
        self._limit_kind = None
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
        # #968 — the request-limit pause stops commands, not reads: a screen
        # read never reaches the car, and the data age matters most exactly
        # while the car refuses requests.
        if self._in_cooldown():
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
        # v2.26.0 (ckomma #21) — a rate-limit / lockout banner means stop: trip
        # the long persisted backoff, which pauses commands. #968 — the alert
        # is a dialog left over from a request, so close it (and the generic
        # "Vehicle data unavailable" that follows it) and read the screen
        # behind it, instead of going blind for the whole pause. Closing it
        # trips the pause.
        if self._is_alert(nodes):
            nodes, closed = await self._close_dialogs(nodes)
            if not closed:
                return None  # nothing readable, and not a failed poll
        if cleared and nodes and self._preset.screen_anchor is not None and not has_anchor(
            nodes, self._preset
        ):
            # A sub-screen (behind a closed alert, or left by a walk that was
            # cut short): go home before reading, and never parse overview
            # selectors off another page. An empty dump is no screen at all,
            # and BACK there could leave the app. The walk back taps, so it
            # needs the same version gate as any other tap.
            if not self._version_ok:
                return {}
            await self._return_to_overview(3)
            nodes, cleared = await self._dump_and_clear_overlays()
            if self._limit_on_screen(nodes):
                self._trip_rate_limit()
            if cleared and not has_anchor(nodes, self._preset):
                return {}
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
            fields.update(read_battery_resources(nodes, self._app_strings))
            fields.update(read_overview_resources(nodes, self._app_strings))
            self._note_sync_line(nodes)
            self._trip_tile_now = driving_tile_text(nodes, self._app_strings)
            if self._trip_tile_now is not None:
                self._trip_tile = self._trip_tile_now
            self._lift_pause_on_new_trip(self._trip_tile_now)
        if self._seen_at is not None:
            fields["companion_app_synced_at"] = self._seen_at
        # v2.26.0 (C9) — values behind a detail screen (charge target/power/time
        # on VW) are read by tapping a tile, reading, and coming BACK. Only tap
        # when it is opted in and the version gate holds; the app refresh
        # interval is the cadence, with no separate floor. When a walk misses a
        # value the cache re-supplies it for up to 24 hours to limit flapping.
        # #1552 — run the scheduled refresh BEFORE re-applying the cache. Filling
        # from the cache first made _augment_via_nav see every target already
        # populated (its all()-guard) and skip the walk forever after the first
        # read, so the detail sensors froze. Refresh first (against the true
        # overview state), then let the cache only backfill gaps on non-due polls.
        if self._preset.nav_reads:
            if self.nav_reads_enabled:
                await self._augment_via_nav(fields)
            for key, val in self._nav_cache.items():
                if fields.get(key) is not None:
                    self._nav_cache[key] = fields[key]
                    self._nav_read_at[key] = self._wall()
                    continue
                # A cached value with no stamp is aged from first sight, so an
                # unstamped write path can never keep a value alive forever.
                if self._wall() - self._nav_read_at.setdefault(key, self._wall()) < COMPANION_NAV_MAX_AGE_S:
                    fields.setdefault(key, val)
        return fields

    @property
    def nav_read_at(self) -> dict[str, float]:
        """Per-field screen read times, retained after expiry for availability."""
        return dict(self._nav_read_at)

    @property
    def request_state(self) -> str | None:
        """What the vehicle sync flow last found (#968), or None.

        Any request-limit trip also sets it to restricted.

        Before the first sync of this session, a request-limit pause restored
        from the last run already says the car is restricted.
        """
        if self._request_state is None and self._is_rate_limited():
            return REQUESTS_RESTRICTED
        return self._request_state

    def _is_alert(self, nodes: list[UiNode]) -> bool:
        """The request-limit alert or the "Vehicle data unavailable" after it.

        On 4.3.2 a refused request shows both, one after the other, each as its
        own dialog window that BACK closes.
        """
        return self._limit_on_screen(nodes) or find_app_alert(nodes, self._app_strings)

    async def _close_dialogs(
        self, nodes: list[UiNode], *, trip: bool = True
    ) -> tuple[list[UiNode], bool]:
        """BACK past the app's alerts; (nodes, True) once none is left.

        A request-limit alert trips the pause before it is closed, unless the
        caller (the sync probe) decides that itself.
        """
        for _ in range(_OVERLAY_MAX_DISMISS):
            if not self._is_alert(nodes):
                return nodes, True
            if trip and self._limit_on_screen(nodes):
                self._trip_rate_limit()
            await self._t.key_back()
            nodes, _cleared = await self._dump_and_clear_overlays()
        return nodes, not self._is_alert(nodes)

    def _note_sync_line(self, nodes: list[UiNode]) -> None:
        """Turn "Synchronised … ago" into when the car last sent data.

        The app rounds the age down, so the earliest time it can mean is used:
        it never claims fresher data than the app has, and later reads only
        move it forward, closing in on the real time from below. A screen
        without the line (a sync in progress, a date-only line) changes nothing.
        """
        line = find_sync_line(nodes, self._app_strings)
        if line is None:
            return
        now = datetime.fromtimestamp(self._wall(), tz=timezone.utc).replace(microsecond=0)
        seen = now - timedelta(seconds=line.age_s + line.precision_s)
        self._seen_precision_s = line.precision_s
        if self._seen_at is None or seen > self._seen_at:
            self._seen_at = seen
        self._lift_pause_on_new_car_data(seen)

    def _lift_pause_on_new_car_data(self, seen: datetime) -> None:
        """End a request-limit pause once the car has sent data since it began.

        The app's limit alerts say starting the car makes everything available
        again, and a car that sent data after the alert is reachable. ``seen``
        is the earliest time the sync line can mean, so an older sync never
        lifts it. The start is derived from the deadline, so a pause restored
        after a restart lifts the same way.
        """
        if not self._is_rate_limited():
            return
        started = self._rate_limited_until - _RATE_LIMIT_BACKOFF_S
        if seen.timestamp() <= started:
            return
        self._lift_pause("the car sent new data after the request-limit alert")

    def _lift_pause_on_new_trip(self, tile: str | None) -> None:
        """End a request-limit pause once the overview shows a new trip.

        The alerts ask for the engine to be started, and a new trip is proof
        it was. The first tile read during the pause is the baseline, so a
        trip that ended before the alert (and first shows on the read that
        trips the pause) never lifts it. A screen without the tile changes
        nothing.
        """
        if not self._is_rate_limited():
            self._pause_trip_tile = None
            return
        if tile is None:
            return
        if self._pause_trip_tile is None:
            self._pause_trip_tile = tile
            return
        if tile != self._pause_trip_tile:
            self._lift_pause("a new trip shows the car was driven")

    def _lift_pause(self, why: str) -> None:
        self._rate_limited_until = 0.0
        self._limit_kind = None
        self._pause_trip_tile = None
        self._request_state = REQUESTS_AVAILABLE
        _LOGGER.info("companion %s: %s; pause lifted", self._preset.brand, why)

    async def _augment_via_nav(self, fields: dict[str, object]) -> None:
        """Fill missing nav-read targets by opening their detail screen.

        Best-effort: a nav-read that fails (tile not found, transport blip)
        leaves its fields absent rather than raising, and we always return to
        the overview afterwards so the next plain read sees the main screen.
        Successful values are cached and re-applied on later polls.
        """
        only, self._nav_only = self._nav_only, set()
        walk_all, self._walk_all_next = self._walk_all_next, False
        def wanted(nav: NavReadSelector) -> bool:
            if not self._nav_allowed(nav):
                return False  # this path's own opt-in is off
            if only:
                if nav.name not in only:
                    return False  # a command's readback re-reads its own path only
            elif not walk_all and not self._walk_due(nav, fields):
                return False  # nothing it shows can have changed since its last walk
            # Nothing to fetch from this detail when every value is known.
            targets = [v.target for v in nav.values] + list(nav.resource_targets)
            return not all(fields.get(t) is not None for t in targets)

        navs = list(self._preset.nav_reads)
        index = 0
        while index < len(navs):
            nav = navs[index]
            index += 1
            if not wanted(nav):
                continue
            # A path that continues another (the climate sheet, then its
            # Settings) is read on the same walk: one trip in, one way out.
            group = [nav]
            while (
                index < len(navs)
                and navs[index].path[: len(group[-1].path)] == group[-1].path
                and wanted(navs[index])
            ):
                group.append(navs[index])
                index += 1
            await self._read_nav_group(group, fields)

    async def _read_nav_group(
        self, group: list[NavReadSelector], fields: dict[str, object]
    ) -> None:
        """Walk to each detail of ``group`` in turn, reading as it goes.

        Each member's path extends the previous one's, so the walk only taps
        the steps the previous screen has not already reached.
        """
        walked = 0
        reached = group[0]
        here: list[UiNode] | None = None
        done = 0
        try:
            for nav in group:
                if nav.name == "parking_position":
                    detail, taps = await self._walk_to_detail(
                        nav.path[done:], here, agree_opt_in=nav.opt_in
                    )
                else:
                    detail, taps = await self._walk_to_detail(nav.path[done:], here)
                walked += taps
                if taps:
                    reached = nav
                if detail is None:
                    break
                extra: dict[str, object] = {}
                if self._preset.brand == "volkswagen" and nav.name == "driving_data":
                    extra = await self._read_driving_data(detail)
                if self._preset.brand == "volkswagen" and nav.name == "departure_times":
                    extra = await self._read_departure_pages(detail)
                if self._preset.brand == "volkswagen" and nav.name == "charging_locations":
                    # A preceding member opened climate timer pages; use the
                    # returned list, rather than its earlier dump.
                    if done:
                        detail, cleared = await self._dump_and_clear_overlays(await self._settle())
                        if not cleared:
                            break
                    extra = await self._read_charging_locations(detail)
                self._apply_nav_values(nav, detail, fields, extra)
                targets = [v.target for v in nav.values] + list(nav.resource_targets)
                if any(fields.get(t) is not None for t in targets):
                    self._walk_basis[nav.name] = _WalkBasis(
                        at=self._wall(),
                        trip=self._trip_tile,
                        synced_at=self._seen_at,
                        synced_precision_s=self._seen_precision_s or 60,
                        ranges=(fields.get("electric_range_km"), fields.get("combustion_range_km")),
                    )
                here, done = detail, len(nav.path)
        except CompanionTransportError:
            _LOGGER.debug(
                "companion %s: nav read '%s' hit a transport error; skipping",
                self._preset.brand, reached.name,
            )
        finally:
            # Back out exactly as far as we actually walked. A path that
            # stopped early (a step not on screen) must not press BACK for
            # taps it never made, or it would leave the app somewhere behind
            # the overview for the next poll.
            if any(nav.name == "charging_locations" for nav in group):
                await self._return_to_overview(min(walked, reached.back_presses), back_only=True)
            else:
                await self._return_to_overview(min(walked, reached.back_presses))

    def walk_details_next_read(self) -> None:
        """Have the next read walk every opted-in detail, gated or not."""
        self._walk_all_next = True

    def _walk_due(self, nav: NavReadSelector, fields: dict[str, object]) -> bool:
        if nav.cadence == "poll":
            return True
        reason = self._walk_reason(nav, fields)
        if reason is not None:
            _LOGGER.debug(
                "companion %s: reading %s: %s", self._preset.brand, nav.name, reason
            )
        return reason is not None

    def _walk_reason(self, nav: NavReadSelector, fields: dict[str, object]) -> str | None:
        """Why a gated walk is due on this poll, or None to skip it.

        Driving data and the parking position change only when a trip ends,
        which the overview's Driving data tile shows (its last-trip text
        changes). Vehicle Health changes with any data the car sends: the
        odometer after a trip, a warning even while parked. New car data counts
        once the sync time has stood still for ``_WALK_SETTLE_S``, so a car on
        the move, sending data every few minutes, is read once it has parked.
        Two trips with the same distance and consumption leave the tile as it
        was; a range drop since the last walk, with settled car data, catches
        that. Every gated walk also runs every 12 hours, and every 6 hours
        while the tile is off the overview.
        """
        basis = self._walk_basis.get(nav.name)
        if basis is None:
            return "no earlier read"
        now = self._wall()
        if now - basis.at >= _WALK_REFRESH_S:
            return "12 h refresh"
        if self._trip_tile is not None and self._trip_tile != basis.trip:
            return "trip ended"
        if (
            nav.cadence == "trip"
            and self._trip_tile_now is None
            and now - basis.at >= _WALK_NO_TILE_S
        ):
            return "Driving data tile not on the overview"
        if not self._new_car_data(basis, now):
            return None
        if nav.cadence == "car_data":
            return "new car data"
        if self._range_dropped(basis, fields):
            return "range dropped with new car data"
        return None

    def _new_car_data(self, basis: "_WalkBasis", now: float) -> bool:
        """The car has sent data since the walk, and then stopped sending.

        The recorded time only narrows within its rounding without a sync, so
        only a move past that rounding is new data.
        """
        seen = self._seen_at
        if seen is None or now - seen.timestamp() < _WALK_SETTLE_S:
            return False
        if basis.synced_at is None:
            return True
        return (seen - basis.synced_at).total_seconds() > basis.synced_precision_s

    @staticmethod
    def _range_dropped(basis: "_WalkBasis", fields: dict[str, object]) -> bool:
        if fields.get("is_charging"):
            return False
        for key, was in zip(("electric_range_km", "combustion_range_km"), basis.ranges):
            now = fields.get(key)
            if isinstance(now, (int, float)) and isinstance(was, (int, float)) and now < was:
                return True
        return False

    def _apply_nav_values(
        self, nav: NavReadSelector, detail: list[UiNode], fields: dict[str, object],
        extra: dict[str, object] | None = None,
    ) -> None:
        values = read_selectors(detail, nav.values)
        values.update(extra or {})
        if self._preset.brand == "volkswagen" and nav.name == "charge_detail":
            values.update(read_battery_resources(detail, self._app_strings))
        if self._preset.brand == "volkswagen" and nav.name == "vehicle_health":
            values.update(read_health_resources(detail, self._app_strings))
        if self._preset.brand == "volkswagen" and nav.name == "vehicle_settings":
            values.update(read_settings_resources(detail, self._app_strings))
        if self._preset.brand == "volkswagen" and nav.name == "departure_times":
            values.update(read_departure_timers(detail))
        if self._preset.brand == "volkswagen" and nav.name in (
            "climate_detail", "climate_settings",
        ):
            values.update(read_climate_resources(detail, self._app_strings))
        if self._preset.brand == "volkswagen" and nav.name == "climate_detail":
            # The dial's ends read LO / HI (15.5 / 30.0), not the number beside
            # them; a dial that is not the app's °C dial gives no target.
            from .climate import dial_is_celsius, read_dial  # noqa: PLC0415

            values.pop("target_temperature", None)
            target = read_dial(detail, self._app_strings)[0]
            if target is not None and dial_is_celsius(detail, self._app_strings):
                values["target_temperature"] = target
        if nav.name == "charging_locations":
            for slot in range(1, 6):
                prefix = f"charging_location_{slot}_"
                name = values.get(prefix + "name")
                previous = self._nav_cache.get(prefix + "name", fields.get(prefix + "name"))
                if name is not None and name != previous:
                    # A slot now names another location; old settings and
                    # timer values must not follow it through a partial read.
                    for part in LOCATION_PARTS:
                        values.setdefault(prefix + part, None)
        for key, val in values.items():
            # #1552 — a fresh detail-screen value wins over a stale
            # overview value for the same key (direct assign, not
            # setdefault); the overview reading is what goes stale.
            fields[key] = val
            self._nav_cache[key] = val
            self._nav_read_at[key] = self._wall()
            self._nav_cache_from[key] = nav.opt_in

    async def _walk_to_detail(
        self,
        steps: "tuple[ActionSelector, ...]",
        here: list[UiNode] | None = None,
        agree_opt_in: str | None = None,
    ) -> tuple[list[UiNode] | None, int]:
        """Tap an ordered path of controls and return (detail_nodes, taps_made).

        ``here`` is a screen the caller has just read and cleared, so a walk
        that continues from it does not dump it again.

        Stops without tapping as soon as a step is not on the current screen, so
        we never tap into the dark on a layout that moved; the caller backs out
        by however many taps actually happened. Overlays are cleared before
        every step and after the last one. ``agree_opt_in`` names the opt-in
        walk this is, so an overlay that needs a consent tap gets it only there.
        """
        taps = 0
        detail: list[UiNode] | None = None
        # What the previous step already settled, so a step never dumps a
        # screen its predecessor just finished reading.
        pending: str | None = None
        if here is not None and not steps:
            return here, 0
        for index, step in enumerate(steps):
            if index == 0 and here is not None:
                nodes, cleared = here, True
            else:
                nodes, cleared = await self._dump_and_clear_overlays(
                    pending, agree_opt_in
                )
            pending = None
            if not cleared:
                return None, taps
            if self._limit_on_screen(nodes):
                self._trip_rate_limit()
                return None, taps
            if step.scroll_first and find_node_for(nodes, step) is None:
                # The MEB overview keeps Vehicle Health and Settings below the
                # fold. Scroll once, then look again; a control that is still
                # absent stops the walk as usual.
                nodes = await self._scroll_up(nodes)
            node = self._step_node(nodes, step)
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
            # Between steps, the next control being drawn is settled enough;
            # the last screen is read, so it gets the full settle.
            ready: Callable[[list[UiNode]], bool] | None = None
            if index + 1 < len(steps):
                following = steps[index + 1]

                def ready(n: list[UiNode], s: ActionSelector = following) -> bool:
                    return self._step_node(n, s) is not None

            pending = await self._settle(ready)
        detail, cleared = await self._dump_and_clear_overlays(pending, agree_opt_in)
        return (detail if cleared else None), taps

    async def _read_driving_data(self, nodes: list[UiNode]) -> dict[str, object]:
        """Both trip cards: the first as drawn, the second after one swipe.

        The carousel shows the second card clipped at the edge, title and
        labels but no values. A sideways swipe inside the carousel brings it
        on screen; it moves the cards only and asks the car for nothing.
        """
        out = read_driving_data(nodes, self._app_strings)
        row = trip_carousel_row(nodes, self._app_strings)
        swipe = getattr(self._t, "swipe", None)
        if "refuel_trip_distance_km" in out or row is None or swipe is None:
            return out
        left, top, right, bottom = row
        y = (top + bottom) // 2
        try:
            await swipe(left + int((right - left) * 0.85), y, left + int((right - left) * 0.15), y, 400)
        except CompanionTransportError:
            return out
        swiped, cleared = await self._dump_and_clear_overlays(await self._settle())
        if cleared:
            for key, val in read_driving_data(swiped, self._app_strings).items():
                if key.startswith("refuel_trip_"):
                    out.setdefault(key, val)
        return out

    async def _read_departure_pages(self, nodes: list[UiNode]) -> dict[str, object]:
        """Each timer's days and Repeat, from its page; BACK after each.

        Opening a page and leaving it with BACK sends nothing: the app saves
        only from its toolbar's Save, which appears only after a change. A
        page that does not open, or a list that does not come back, ends the
        reading there; what was read is kept.
        """
        out: dict[str, object] = {}
        for slot in range(1, min(3, len(departure_rows(nodes))) + 1):
            page, nodes = await self._open_timer_page(nodes, slot)
            if page is None:
                if not departure_rows(nodes):
                    await self._back_to_timer_list()  # off the list: one step back
                break
            out.update(page_fields(page, slot))
            back = await self._back_to_timer_list()
            if back is None:
                break
            nodes = back
        return out

    async def _read_charging_locations(self, nodes: list[UiNode]) -> dict[str, object]:
        """Read names, timer labels and location settings; BACK after each page."""
        out: dict[str, object] = {}
        names: list[str] = []
        current = "none"
        complete = False
        depth = 0
        section_seen = False
        if not any(key.startswith("active_chargingtimes_option#") and labels
                   for key, labels in self._app_strings.items()):
            return out
        if not self._app_strings.get("common_status_active"):
            return out
        try:
            for _ in range(16):
                if not on_location_list(nodes, self._app_strings):
                    break
                section_seen |= charging_section_visible(nodes, self._app_strings)
                rows = location_rows(nodes, self._app_strings)
                visible = [row.name.text for row in rows]
                if len(set(visible)) != len(visible):
                    break  # ambiguous slots: keep only what was already read
                for row in rows:
                    name = row.name.text
                    if name in names:
                        continue
                    point = row.name.tap_point
                    if point is None or len(names) == 5:
                        return out
                    names.append(name)
                    slot = len(names)
                    prefix = f"charging_location_{slot}_"
                    out.update({prefix + "name": name, prefix + "active": row.active,
                                prefix + "active_timers": row.active_timers})
                    if row.active:
                        current = name
                    await self._t.tap(*point)
                    depth = 1
                    page, cleared = await self._dump_and_clear_overlays(await self._settle())
                    if on_location_list(page, self._app_strings):
                        depth = 0  # the tap did not open a page
                        return out
                    if not cleared or location_title(page, name) is None:
                        return out
                    out.update(location_timers(page, self._app_strings, slot))
                    icon = settings_icon(page, name)
                    if icon is not None and icon.tap_point is not None:
                        await self._t.tap(*icon.tap_point)
                        depth = 2
                        settings, cleared = await self._dump_and_clear_overlays(await self._settle())
                        if location_title(settings, name) is not None:
                            depth = 1  # settings did not open
                            return out
                        if not cleared or not on_location_settings(settings, self._app_strings):
                            return out
                        out.update(location_settings(settings, self._app_strings, slot, name))
                        await self._t.key_back()
                        depth = 1
                        page, cleared = await self._dump_and_clear_overlays(await self._settle())
                        if not cleared or location_title(page, name) is None:
                            return out
                    await self._t.key_back()
                    depth = 0
                    nodes, cleared = await self._dump_and_clear_overlays(await self._settle())
                    if not cleared or not on_location_list(nodes, self._app_strings):
                        return out
                    # Re-resolve every name on the returned screen; coordinates
                    # from a previous dump must not drive the next tap.
                    break
                else:
                    if len(names) == 5:
                        complete = True
                        break
                    if getattr(self._t, "swipe", None) is None or screen_bounds(nodes) is None:
                        break
                    await self._scroll_up(nodes, strict=True)
                    scrolled, cleared = await self._dump_and_clear_overlays(await self._settle())
                    if not cleared or not on_location_list(scrolled, self._app_strings):
                        break
                    if scrolled == nodes:
                        complete = True  # a swipe at the end of the list
                        break
                    nodes = scrolled
            # An empty list is ambiguous: the app shows the same "create your
            # charging locations" text when the car has none and when the
            # backend returned no departure data (live 2026-10-10, during a
            # request-limit pause). Only a list with rows is a full read.
            if complete and section_seen and names:
                out["charging_location_count"] = len(names)
                out["charging_location_current"] = current
                for slot in range(len(names) + 1, 6):
                    out.update({f"charging_location_{slot}_{part}": None for part in LOCATION_PARTS})
        except CompanionTransportError:
            _LOGGER.debug("companion volkswagen: charging locations read interrupted")
        finally:
            if depth:
                await self._reconnect_for_cleanup()
            for _ in range(depth):
                try:
                    here, _cleared = await self._dump_and_clear_overlays()
                    if on_location_list(here, self._app_strings) or has_anchor(here, self._preset):
                        break
                    await self._t.key_back()
                    await self._dump_and_clear_overlays(await self._settle())
                except CompanionTransportError:
                    break
        return out

    async def _open_timer_page(
        self, nodes: list[UiNode], slot: int
    ) -> tuple[TimerPage | None, list[UiNode]]:
        """Tap the slot's row (its time text, clear of the switch) and read the page."""
        rows = departure_rows(nodes)
        if len(rows) < slot:
            return None, nodes
        point = rows[slot - 1].clock.tap_point
        if point is None:
            return None, nodes
        await self._t.tap(*point)
        settled = await self._settle(lambda n: read_timer_page(n) is not None)
        page_nodes, cleared = await self._dump_and_clear_overlays(settled)
        if not cleared or self._limit_on_screen(page_nodes):
            return None, page_nodes
        return read_timer_page(page_nodes), page_nodes

    async def _back_to_timer_list(self) -> list[UiNode] | None:
        """BACK from a timer page; the list's nodes once it shows again."""
        await self._t.key_back()
        settled = await self._settle(lambda n: bool(departure_rows(n)))
        nodes, cleared = await self._dump_and_clear_overlays(settled)
        if cleared and departure_rows(nodes) and read_timer_page(nodes) is None:
            return nodes
        return None

    async def _scroll_up(self, nodes: list[UiNode], *, strict: bool = False) -> list[UiNode]:
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
            if strict:
                raise
            return nodes
        scrolled, cleared = await self._dump_and_clear_overlays()
        if strict and not cleared:
            raise CompanionTransportError("could not read the scrolled list")
        return scrolled if cleared else nodes

    def _step_node(self, nodes: list[UiNode], step: "ActionSelector") -> UiNode | None:
        node = find_node_for(nodes, step)
        if step.action == "open_charge_detail" and node is None:
            node = find_battery_tile(nodes, self._app_strings)
        if step.action == "open_vehicle_settings" and node is None:
            node = find_settings_entry(nodes, self._app_strings)
        if step.action == "open_departure_times" and node is None:
            node = find_tile_entry(nodes, self._app_strings, DEPARTURE_TILE)
        if step.action == "open_driving_data" and node is None:
            node = find_tile_entry(nodes, self._app_strings, DRIVING_TILE)
        return node

    async def _settle(
        self, ready: Callable[[list[UiNode]], bool] | None = None
    ) -> str | None:
        """Dump until the tree stops changing, and hand the result back.

        ``ready`` ends the wait after the first dump that satisfies it (with
        no overlay up), saving the confirming dump when the screen a caller
        needs is already drawn.

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
            if ready is not None:
                nodes = parse_ui_dump(current)
                if find_overlay(nodes, self._preset) is None and ready(nodes):
                    return current
            previous = current
        return previous

    async def _return_to_overview(self, presses: int = 1, *, back_only: bool = False) -> None:
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
        await self._reconnect_for_cleanup()
        for _ in range(max(0, presses)):
            try:
                nodes, _cleared = await self._dump_and_clear_overlays()
            except CompanionTransportError:
                return
            # The limit alert can land after the step that caused it; this
            # BACK would close it, so it trips the pause first.
            if self._limit_on_screen(nodes):
                self._trip_rate_limit()
            if self._preset.screen_anchor is not None and has_anchor(
                nodes, self._preset
            ):
                return
            up_point: tuple[int, int] | None = None
            for spec in (() if back_only else self._preset.up_controls):
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

    async def _reconnect_for_cleanup(self) -> None:
        """Reconnect once, so a dropped shell does not skip the cleanup.

        The direct ADB transport closes the device on any shell error, and
        every later call would fail as "not connected": a staged switch or a
        moved slider would then stay on screen for the next command.
        """
        if self._t.connected:
            return
        try:
            await self._t.connect()
        except CompanionTransportError:
            pass

    async def _dump_and_clear_overlays(
        self, known_xml: str | None = None, agree_opt_in: str | None = None
    ) -> tuple[list[UiNode], bool]:
        """Dump the screen; if a known overlay is up, BACK past it and re-dump.

        v2.26.0 (ckomma #8/#13/#20). Returns (parsed_nodes, cleared). ``cleared``
        is False when an overlay is still present after the capped retries or
        a consent was backed out of, so the caller can decline to read/tap the
        wrong screen. Only an opted-in parking walk may accept map consent.

        v4.4.0 — ``known_xml`` lets a caller that has just settled a screen pass
        what it already read instead of paying for another dump. Overlay
        handling is unchanged: if one turns out to be up, it is dismissed and
        the screen re-read as before.

        An overlay that carries a ``tap`` (the Google Maps consent) is tapped
        only when ``agree_opt_in`` is the opt-in it belongs to and the user has
        that opt-in on. Everywhere else it is backed out of and reported as
        not cleared: BACK can leave the map rather than reveal its contents.
        """
        xml = known_xml if known_xml is not None else await self._t.dump_ui()
        for _ in range(_OVERLAY_MAX_DISMISS):
            nodes = parse_ui_dump(xml)
            overlay = find_overlay(nodes, self._preset)
            if overlay is None:
                return nodes, True
            agree = (
                overlay.tap is not None
                and agree_opt_in is not None
                and overlay.tap_opt_in == agree_opt_in
                and agree_opt_in in self._nav_opt_ins
            )
            node = (
                find_node_for(nodes, overlay.tap)
                if agree and overlay.tap is not None
                else None
            )
            point = node.tap_point if node is not None else None
            if point is not None:
                _LOGGER.debug(
                    "companion %s: dismissing overlay '%s' with its '%s' button",
                    self._preset.brand, overlay.name, overlay.tap.action if overlay.tap else "",
                )
                await self._t.tap(*point)
            else:
                _LOGGER.debug(
                    "companion %s: dismissing overlay '%s' with BACK",
                    self._preset.brand, overlay.name,
                )
                await self._t.key_back()
            xml = await self._t.dump_ui()
            if overlay.tap is not None and point is None:
                # BACK leaves the consent's screen; do not continue a read or
                # command on the assumption that its intended screen is clear.
                return parse_ui_dump(xml), False
        nodes = parse_ui_dump(xml)
        still = find_overlay(nodes, self._preset)
        if still is not None:
            _LOGGER.warning(
                "companion %s: overlay '%s' did not clear after %d BACK presses",
                self._preset.brand, still.name, _OVERLAY_MAX_DISMISS,
            )
            return nodes, False
        return nodes, True

    def _limit_on_screen(self, nodes: list[UiNode]) -> bool:
        """The app's request-limit alert or banner, in any installed language.

        Also notes which kind it is, for the ``_trip_rate_limit`` that follows.
        """
        found = (
            find_rate_limit_banner(nodes, self._preset) is not None
            or find_request_limit(nodes, self._app_strings)
        )
        if found:
            self._limit_seen_kind = self._limit_kind_on(nodes)
        return found

    def _limit_kind_on(self, nodes: list[UiNode]) -> str:
        """LIMIT_POWER_BUDGET only when the app's own power-budget alert is the
        sole limit on screen; anything else is a backend limit."""
        if not is_power_budget_alert(nodes, self._app_strings):
            return LIMIT_BACKEND
        own = power_budget_labels(self._app_strings)
        others = [
            n for n in nodes
            if not any(t and t.strip().casefold() in own for t in (n.text, n.content_desc))
        ]
        if find_rate_limit_banner(others, self._preset) is not None:
            return LIMIT_BACKEND
        return LIMIT_POWER_BUDGET

    def _may_probe_limit(self) -> bool:
        """#968 — the sync may tap through a pause only when the app's own
        power-budget alert tripped it (the app then answers without sending
        anything), and at most once per ``_LIMIT_PROBE_GAP_S``. Never after a
        backend limit (HTTP 429 / too many requests): there the tap is a
        request and would extend the lockout."""
        return (
            self._limit_kind == LIMIT_POWER_BUDGET
            and self._wall() - self._limit_probe_at >= _LIMIT_PROBE_GAP_S
        )

    async def _refresh_version_gate(self) -> None:
        """Read the live app version and (re)decide whether the app matches the
        version this preset was verified against.

        Called on every read and command, including before the first poll.
        Resource labels refresh only when the installed version or split list
        changes. A failed extraction leaves the previous table intact.
        """
        self._live_app_version = await self._t.current_app_version(self._preset.package)
        self._version_ok = self._decide_version_ok(self._live_app_version)
        getter = getattr(self._t, "battery_strings", None)
        if self._preset.brand != "volkswagen" or getter is None:
            return
        self._strings_paths_now = None  # unknown until the split list is read
        try:
            path_getter = getattr(self._t, "app_resource_paths", None)
            paths = await path_getter(self._preset.package) if path_getter else ()
            self._strings_paths_now = paths
            key = (self._live_app_version, paths)
            if self._strings_ok_key == key:
                return
            if key != self._strings_try_key:
                self._strings_try_key, self._strings_fails = key, 0
            elif self._now() < self._strings_retry_at:
                return
            strings = await getter(self._preset.package)
            if strings:
                self._app_strings = strings
                self._strings_ok_key = key
                self._strings_fails = 0
            else:
                self._strings_failed()
        except CompanionTransportError:
            _LOGGER.debug("companion: app translation resources unavailable")
            self._strings_failed()
            # Direct ADB drops its socket on shell errors. Reconnect once for
            # the remaining screen read, without retrying the extraction.
            if not self._t.connected:
                await self._t.connect()

    def _strings_failed(self) -> None:
        """Back off a failed extraction: 15 min, then hourly, per (version, splits)."""
        self._strings_fails += 1
        self._strings_retry_at = self._now() + (900.0 if self._strings_fails == 1 else 3600.0)

    def _strings_current(self) -> bool:
        """True when the table was read for the installed version and splits.

        A stale table (from before an update or a new language split) may still
        serve reads, but must not vouch for limit detection on writes.
        """
        return bool(self._app_strings) and self._strings_ok_key == (
            self._live_app_version, self._strings_paths_now
        )

    def _require_limit_language(self, nodes: list[UiNode]) -> None:
        """Identify fallback coverage from known labels in the current dump.

        No device locale query: Android's per-app language can differ from it,
        and the relay has no locale verb. Unknown/ambiguous screens fail closed.
        Navigation accessibility descriptions may stay English in foreign UIs,
        so only visible app labels and known command labels are considered.
        """
        if self._strings_current():
            return
        labels = {
            "charging", "air conditioning", "klimatisierung", "climatización",
            "start charging", "stop charging",
            "klimatisierung starten", "klimatisierung stoppen",
        }
        for node in nodes:
            rid = node.resource_id.rsplit("/", 1)[-1]
            if rid in {"title", "vwd_title", "cta_start", "cta_stop"}:
                if node.text.strip().casefold() in labels:
                    return
            if node.clickable and node.content_desc.strip().casefold() in labels:
                return
            desc = node.content_desc.strip()
            if node.clickable and desc in {
                "Departure times. Open details", "Abfahrtszeiten. Details öffnen",
            }:
                return
            # These localized range-tile descriptions already identify the
            # overview in the fallback parser. Unlike "Laden" / "Carga", the
            # complete labels are not shared with unsupported UI languages.
            if (desc.startswith("Range overview.") and desc.endswith("Open details")) or (
                desc.startswith("Übersicht Reichweite.") and desc.endswith("Details öffnen")
            ):
                return
        from homeassistant.exceptions import HomeAssistantError  # noqa: PLC0415

        raise HomeAssistantError(
            "Writes and synchronisation are disabled: app translation resources "
            "are unavailable and the current UI language cannot be confirmed as "
            "English, German or Spanish. Reads continue.",
            translation_domain="vag_connect",
            translation_key="companion_limit_language_unavailable",
        )

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
        if not app_version_covered(live_version, want_set):
            _LOGGER.warning(
                "companion %s: app is %s, older than or unknown to this preset "
                "(built for %s); taps (writes and nav reads) are disabled. "
                "Overview reads keep working.",
                self._preset.brand, live_version, "/".join(want_set),
            )
            return False
        if live_version not in want_set and live_version != self._newer_logged:
            self._newer_logged = live_version
            _LOGGER.info(
                "companion %s: app %s is newer than the verified %s; nav reads "
                "rely on finding each control on screen, commands stay off "
                "until this version is verified",
                self._preset.brand, live_version, "/".join(want_set),
            )
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
        if action == "sync_vehicle":
            raise CompanionWriteBlocked("a vehicle sync runs through sync_vehicle")
        if action in CLIMATE_SETTING_ACTIONS.values():
            raise CompanionWriteBlocked("a climate setting needs its on/off value")
        if action in ("toggle_departure_timer", "edit_departure_timer"):
            raise CompanionWriteBlocked("a departure timer is set through set_departure_timer")
        spec, nodes = await self._command_gate(action)
        walked = 0
        nav = next((n for n in self._preset.nav_reads if n.name == spec.nav_read), None)
        on_detail = False
        trips = self._limit_trips
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
            if self._limit_on_screen(nodes):
                self._trip_rate_limit()
                raise CompanionWriteBlocked(_LIMIT_REASON)
            if self._app_strings and action in ("start_charging", "stop_charging"):
                node = find_battery_control(nodes, self._app_strings, action)
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
            self._stamp_write()
            # Re-read this command's own detail path on the next poll: a
            # delivered tap is not proof that the vehicle accepted it, and the
            # cached pre-command values are not readback. Only that path is
            # walked on the readback, so a command never triggers a walk of
            # every screen; the next app refresh walks them all as usual.
            if nav is not None:
                for value in nav.values:
                    self._nav_cache.pop(value.target, None)
                self._nav_only.add(nav.name)
            await self._t.tap(*node.tap_point)
            # The app shows the request-limit alert about a second after the
            # tap; look for it, so it trips the pause and fails the command.
            # The tap is delivered, so a failed look does not fail the command.
            for _ in range(_LIMIT_READBACK_DUMPS):
                try:
                    after, _cleared = await self._dump_and_clear_overlays()
                except CompanionTransportError:
                    break
                if self._limit_on_screen(after):
                    self._trip_rate_limit()
                    raise CompanionWriteBlocked(_LIMIT_REASON)
        except CompanionTransportError as err:
            raise CompanionWriteBlocked(str(err)) from err
        finally:
            if nav is not None:
                # A command started on the sheet still closes it (review B12).
                await self._return_to_overview(
                    min(max(walked, int(on_detail)), nav.back_presses)
                )
        if self._limit_trips != trips:
            # The limit alert arrived after the readback, and the walk back
            # closed it: the car refused the command after all.
            raise CompanionWriteBlocked(_LIMIT_REASON)

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
        # The saved value while a slider position may be pending; None once
        # there is nothing to discard (not moved yet, or Save was pressed).
        unsaved_from: int | None = None
        leave = True
        try:
            row = find_charge_target_row(nodes)
            if row is None:
                detail, _walked = await self._walk_to_detail(nav.path)
                if detail is not None and self._limit_on_screen(detail):
                    self._trip_rate_limit()
                    raise CompanionWriteBlocked(_LIMIT_REASON)
                row = find_charge_target_row(detail) if detail is not None else None
            if row is None:
                raise CompanionWriteBlocked(
                    "could not find the charge limit on the vehicle Settings screen"
                )
            if row.current == target:
                return target  # nothing to change, nothing sent
            unsaved_from = row.current
            await self._move_charge_slider(row, target)
            # Save is the one tap that sends, so the dump right before it must
            # show exactly the target (review B3). Stamp first, so a transport
            # that fails after delivery still blocks an immediate repeat.
            nodes, _cleared = await self._dump_and_clear_overlays()
            ready = find_charge_target_row(nodes)
            if ready is None or ready.current != target:
                shown = "no charge limit" if ready is None else f"{ready.current} %"
                raise CompanionWriteBlocked(
                    f"the app shows {shown} before Save, not {target} %; nothing was saved"
                )
            save = find_save_button(nodes)
            if save is None or save.tap_point is None:
                raise CompanionWriteBlocked("the app did not offer Save for the new limit")
            unsaved_from = None
            self._stamp_write()
            self._nav_cache.pop("target_soc", None)
            await self._t.tap(*save.tap_point)
            await self._await_charge_target_saved(target)
            self._nav_cache["target_soc"] = target
            self._nav_read_at["target_soc"] = self._wall()
            return target
        except (CompanionWriteBlocked, CompanionTransportError) as err:
            if unsaved_from is not None and not await self._discard_charge_target(unsaved_from):
                # Cancel did not take: another press of the same control
                # proves nothing more, so tap nothing else.
                leave = False
                raise CompanionWriteBlocked(
                    f"{err}; the app did not confirm discarding the change, check it in the app"
                ) from err
            if isinstance(err, CompanionTransportError):
                raise CompanionWriteBlocked(str(err)) from err
            raise
        finally:
            # The app's own toolbar button: Back after a save, and Cancel (which
            # discards the unsaved position) if anything stopped us before it.
            if leave:
                await self._return_to_overview(2)

    async def _move_charge_slider(self, row: ChargeTargetRow, target: int) -> None:
        """Tap the track until the row reads ``target``; a tap sends nothing.

        A dump can predate the tap's redraw (review B3), so a reading counts
        only once it differs from the value before the tap, or two dumps in a
        row agree. A tap that changed nothing is never corrected from.
        """
        aim = target
        for _ in range(_SLIDER_TRIES):
            before = row.current
            await self._t.tap(*row.tap_point(aim))
            seen = await self._read_slider(before)
            if seen is None or seen.current == before:
                break
            if seen.current == target:
                return
            # Correct by what the slider actually did; the steps are wide, so
            # this only matters if the layout drifted.
            aim = snap_target(aim + (target - seen.current))
            row = seen
        raise CompanionWriteBlocked(
            f"the charge limit slider did not reach {target} %; nothing was saved"
        )

    async def _read_slider(self, before: int) -> ChargeTargetRow | None:
        """The row once it is redrawn after a tap; None if that is not proven."""
        previous: int | None = None
        for _ in range(_SLIDER_READS):
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
            if seen.current != before or seen.current == previous:
                return seen
            previous = seen.current
        return None

    async def _discard_charge_target(self, saved: int) -> bool:
        """Cancel a pending slider position with the app's own toolbar X.

        True once the row shows ``saved`` again with no Save pending. Taps
        only when Save is pending, and then only the cancel the walk back
        would have pressed anyway.
        """
        try:
            nodes, _cleared = await self._dump_and_clear_overlays()
            if find_save_button(nodes) is not None:
                cancel = next((
                    node for node in (find_node_for(nodes, s) for s in self._preset.up_controls)
                    if node is not None and node.tap_point is not None
                ), None)
                if cancel is None or cancel.tap_point is None:
                    return False
                await self._t.tap(*cancel.tap_point)
                nodes = await self._await_screen(lambda n: find_save_button(n) is None)
            row = find_charge_target_row(nodes)
            return row is not None and row.current == saved and find_save_button(nodes) is None
        except CompanionTransportError:
            return False

    async def _await_charge_target_saved(self, target: int) -> None:
        """Wait for the app to finish sending; fail unless it confirms."""
        for _ in range(_SAVE_POLLS):
            nodes, _cleared = await self._dump_and_clear_overlays()
            if self._limit_on_screen(nodes):
                self._trip_rate_limit()
                raise CompanionWriteBlocked(_LIMIT_REASON)
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

    async def set_climate_setting(self, key: str, enabled: bool) -> bool:
        """Switch one Climate Settings value and save it; True when it changed.

        ``key`` is the field the read fills: ``climate_at_unlock``,
        ``window_heating_enabled``, ``climate_zone_front_left`` or
        ``climate_zone_front_right``. A value already in place sends nothing.
        Otherwise the switch is tapped (which only stages it), Save must appear,
        Save is tapped, and the page is opened again to read the saved state.
        Nothing is ever left staged: an abort un-stages a switch it tapped and
        leaves the page without Save, which keeps what was saved.
        """
        async with self._screen_lock:
            return await self._set_climate_setting_serialized(key, bool(enabled))

    async def _set_climate_setting_serialized(self, key: str, enabled: bool) -> bool:
        action = CLIMATE_SETTING_ACTIONS.get(key)
        if action is None:
            raise CompanionWriteBlocked(f"'{key}' is not a climate setting the app can change")
        name = CLIMATE_SETTING_NAMES[key]
        zone = key not in CLIMATE_TOGGLES
        spec, nodes = await self._command_gate(action)
        nav = next((n for n in self._preset.nav_reads if n.name == spec.nav_read), None)
        if nav is None or not nav.path:
            raise CompanionWriteBlocked("the Climate Settings path is not mapped")
        if zone and not self._app_strings:
            raise CompanionWriteBlocked(
                "the zones are found by the app's own labels, and its translation "
                "tables could not be read; nothing was changed"
            )
        # The switch this call tapped and has not saved, with its saved value,
        # so an abort can put it back before leaving.
        staged: bool | None = None
        try:
            page = await self._open_climate_settings(nav, nodes)
            current, page = await self._read_climate_setting(key, page)
            if current == enabled:
                return False  # nothing to change, nothing sent
            staged = current
            page = await self._stage_climate_setting(key, enabled, page)
            save = find_climate_save(page)
            if save is None:
                page = await self._await_screen(lambda n: find_climate_save(n) is not None)
                save = find_climate_save(page)
            if self._limit_on_screen(page):
                self._trip_rate_limit()
                raise CompanionWriteBlocked(_LIMIT_REASON)
            if save is None or save.tap_point is None:
                raise CompanionWriteBlocked(
                    f"the app did not offer Save after switching the {name}; nothing was sent"
                )
            # Save is the one tap that sends. Stamp first, so a transport that
            # fails after delivery still blocks an immediate repeat.
            self._stamp_write()
            self._nav_cache.pop(key, None)
            # The readback refresh re-reads this page only, not every path.
            self._nav_only.add(nav.name)
            await self._t.tap(*save.tap_point)
            staged = None
            after = await self._await_climate_settings_saved(nav, name)
            page = await self._open_climate_settings(nav, after)
            seen, page = await self._read_climate_setting(key, page)
            if seen != enabled:
                raise CompanionWriteBlocked(
                    f"the app shows the {name} {'on' if seen else 'off'} after saving, "
                    f"not {'on' if enabled else 'off'}; check it in the app"
                )
            self._nav_cache[key] = enabled
            self._nav_read_at[key] = self._wall()
            self._nav_cache_from[key] = nav.opt_in
            return True
        except CompanionTransportError as err:
            raise CompanionWriteBlocked(str(err)) from err
        finally:
            await self._leave_climate_settings(key, staged)

    async def _await_screen(self, done: Callable[[list[UiNode]], bool]) -> list[UiNode]:
        """Dump until the screen a tap should produce is there (bounded)."""
        nodes: list[UiNode] = []
        for _ in range(_SCREEN_TRIES):
            nodes, _cleared = await self._dump_and_clear_overlays()
            if done(nodes) or self._limit_on_screen(nodes):
                break
        return nodes

    async def _open_climate_settings(
        self, nav: NavReadSelector, nodes: list[UiNode]
    ) -> list[UiNode]:
        """Reach the Settings page from wherever ``nodes`` shows: it, the sheet, or home."""
        if on_settings_page(nodes):
            return nodes
        # From the sheet only its Settings row is left to tap.
        on_sheet = find_node_for(nodes, nav.path[-1]) is not None
        steps = nav.path[-1:] if on_sheet else nav.path
        detail, _walked = await self._walk_to_detail(steps, nodes)
        if detail is not None and not on_settings_page(detail) and not self._limit_on_screen(detail):
            # A Compose page can be caught before its toolbar is drawn.
            detail = await self._await_screen(on_settings_page)
        if detail is not None and self._limit_on_screen(detail):
            self._trip_rate_limit()
            raise CompanionWriteBlocked(_LIMIT_REASON)
        if detail is None or not on_settings_page(detail):
            raise CompanionWriteBlocked("could not open the Climate Settings page")
        return detail

    async def _read_climate_setting(
        self, key: str, page: list[UiNode]
    ) -> tuple[bool, list[UiNode]]:
        """The setting as the page shows it; a zone is read on the Zones page."""
        name = CLIMATE_SETTING_NAMES[key]
        if key in CLIMATE_TOGGLES:
            toggle = find_toggle(page, key)
            if toggle is None:
                page = await self._await_screen(lambda n: find_toggle(n, key) is not None)
                toggle = find_toggle(page, key)
            if toggle is None:
                raise CompanionWriteBlocked(
                    f"the {name} switch is not on the Climate Settings page; this car "
                    "may not have it"
                )
            return toggle.checked, page
        strings = self._app_strings
        if not on_zones_page(page, strings):
            row = find_zones_row(page, strings)
            if row is None or row.tap_point is None:
                raise CompanionWriteBlocked(
                    "the Zones row is not on the Climate Settings page; this car may "
                    "not have zones"
                )
            await self._t.tap(*row.tap_point)
            page = await self._await_screen(
                lambda n: find_zone_switch(n, strings, key) is not None
            )
        if self._limit_on_screen(page):
            self._trip_rate_limit()
            raise CompanionWriteBlocked(_LIMIT_REASON)
        switch = find_zone_switch(page, strings, key)
        if switch is None:
            raise CompanionWriteBlocked(f"the Zones page does not show the {name}")
        return switch.checked, page

    async def _stage_climate_setting(
        self, key: str, enabled: bool, page: list[UiNode]
    ) -> list[UiNode]:
        """Tap the switch and see it flip; a zone is carried back to Settings."""
        name = CLIMATE_SETTING_NAMES[key]
        strings = self._app_strings
        if key in CLIMATE_TOGGLES:
            def find(n: list[UiNode]) -> UiNode | None:
                return find_toggle(n, key)
        else:
            def find(n: list[UiNode]) -> UiNode | None:
                return find_zone_switch(n, strings, key)
        switch = find(page)
        if switch is None or switch.tap_point is None:
            raise CompanionWriteBlocked(f"the {name} switch cannot be tapped")
        await self._t.tap(*switch.tap_point)
        page = await self._await_screen(
            lambda n: (s := find(n)) is not None and s.checked == enabled
        )
        flipped = find(page)
        if flipped is None or flipped.checked != enabled:
            raise CompanionWriteBlocked(f"the {name} switch did not change; nothing was sent")
        if key in CLIMATE_TOGGLES:
            return page
        # The toolbar arrow keeps the zone change; Android BACK would drop it.
        back = find_zones_back(page, strings)
        if back is None or back.tap_point is None:
            raise CompanionWriteBlocked(
                "could not find the Zones page's back arrow; nothing was sent"
            )
        await self._t.tap(*back.tap_point)
        page = await self._await_screen(
            lambda n: on_settings_page(n) and find_climate_save(n) is not None
        )
        if not on_settings_page(page) and not self._limit_on_screen(page):
            raise CompanionWriteBlocked(
                "the app did not return to Climate Settings from Zones; nothing was sent"
            )
        return page

    async def _await_climate_settings_saved(
        self, nav: NavReadSelector, name: str
    ) -> list[UiNode]:
        """Wait for Save to be taken: the app closes Settings onto the sheet."""
        nodes: list[UiNode] = []
        for _ in range(_SAVE_POLLS):
            nodes, _cleared = await self._dump_and_clear_overlays()
            if self._limit_on_screen(nodes):
                self._trip_rate_limit()
                raise CompanionWriteBlocked(_LIMIT_REASON)
            if self._is_alert(nodes):
                raise CompanionWriteBlocked(
                    f"the app reported a problem saving the {name}; check it in the app"
                )
            if on_settings_page(nodes):
                if find_climate_save(nodes) is None:
                    return nodes  # stayed on the page, nothing left to save
                continue  # Save not taken yet
            if find_node_for(nodes, nav.path[-1]) is not None:
                return nodes  # back on the sheet: saved
            if self._preset.screen_anchor is not None and has_anchor(nodes, self._preset):
                return nodes
            # Between screens: dump again.
        raise CompanionWriteBlocked(
            f"the app did not confirm saving the {name}; check it in the app"
        )

    async def _leave_climate_settings(self, key: str, staged: bool | None) -> None:
        """Back to the overview without saving anything left staged.

        A switch this call tapped but did not save is switched back first,
        which on the 4.6.4 page also takes Save away again. A zone needs
        nothing: Android BACK leaves the Zones page without the change, and
        ``climatisationSettingsLeading`` leaves Settings without Save.
        """
        if staged is not None and key in CLIMATE_TOGGLES:
            await self._reconnect_for_cleanup()
            try:
                nodes, _cleared = await self._dump_and_clear_overlays()
                toggle = find_toggle(nodes, key)
                if toggle is not None and toggle.checked != staged and toggle.tap_point:
                    await self._t.tap(*toggle.tap_point)
                    await self._await_screen(lambda n: find_climate_save(n) is None)
            except CompanionTransportError:
                pass
        # Zones → Settings → sheet → overview, stopping once home.
        await self._return_to_overview(3)

    async def set_departure_timer(
        self,
        slot: int,
        *,
        enabled: bool | None = None,
        time: str | None = None,
        weekdays: "tuple[str, ...] | list[str] | None" = None,
        repeat: bool | None = None,
    ) -> None:
        """Set one Departure times timer (1-3) the way the app does.

        ``enabled`` taps the timer's switch on the list, which the app sends
        at once. ``time`` ("HH:MM", 24-hour), ``weekdays`` (Home Assistant
        codes, "mon" … "sun") and ``repeat`` are set on the timer's page, one
        read-back tap at a time, and sent with the page's Save only when the
        page shows exactly what was asked; otherwise the page is cancelled and
        nothing is sent. Both are read back after sending. Assumes the car and
        Home Assistant share a time zone: the time is the car's local time.

        The app's Save sends the timer switched on (4.6.4 ``saveSettings``), so
        a page edit leaves it on; an edit with ``enabled=False`` would need a
        second request straight after the first and is refused.
        """
        async with self._screen_lock:
            await self._set_departure_timer_serialized(slot, enabled, time, weekdays, repeat)

    async def _set_departure_timer_serialized(
        self,
        slot: int,
        enabled: bool | None,
        time: str | None,
        weekdays: "tuple[str, ...] | list[str] | None",
        repeat: bool | None,
    ) -> None:
        if slot not in (1, 2, 3):
            raise CompanionWriteBlocked(f"there is no departure timer {slot}; the app has 1, 2 and 3")
        clock = _hhmm(time) if time is not None else None
        days = _weekdays(weekdays) if weekdays is not None else None
        edit = clock is not None or days is not None or repeat is not None
        if not edit and enabled is None:
            raise CompanionWriteBlocked("nothing to set on the departure timer")
        if edit and enabled is False:
            raise CompanionWriteBlocked(
                "the app's Save switches the timer on; switch it off in a separate "
                "command after the edit"
            )
        spec, nodes = await self._command_gate(
            "edit_departure_timer" if edit else "toggle_departure_timer"
        )
        if edit and enabled is not None:
            toggle = next((a for a in self._preset.actions if a.action == "toggle_departure_timer"), None)
            if toggle is None or (toggle.app_versions and not app_version_listed(
                self._live_app_version, toggle.app_versions
            )):
                raise CompanionWriteBlocked(
                    f"switching a departure timer is not mapped for app version {self._live_app_version}"
                )
        nav = next((n for n in self._preset.nav_reads if n.name == spec.nav_read), None)
        if nav is None:
            raise CompanionWriteBlocked("the Departure times path is not mapped")
        try:
            listing: list[UiNode] | None = nodes if departure_rows(nodes) else None
            if listing is None:
                listing, _walked = await self._walk_to_detail(nav.path)
                if listing is not None and self._limit_on_screen(listing):
                    self._trip_rate_limit()
                    raise CompanionWriteBlocked(_LIMIT_REASON)
            if listing is None or len(departure_rows(listing)) < slot:
                raise CompanionWriteBlocked(
                    f"could not find departure timer {slot} on the Departure times screen"
                )
            # A row is found by position; an unread row would shift the rest.
            rows = departure_rows(listing)
            if len(rows) != 3:
                raise CompanionWriteBlocked(
                    "could not read all three timers on the Departure times screen; "
                    "nothing was sent"
                )
            # The page shows no timer number: its time, checked against the
            # row, is the only identity both share (the row's recurrence is
            # app text, and the page has no switch). Two rows at one time
            # cannot be told apart, so a page edit is refused before opening.
            twin = next((i + 1 for i, row in enumerate(rows)
                         if i != slot - 1 and row.time == rows[slot - 1].time), None)
            if edit and twin is not None:
                raise CompanionWriteBlocked(
                    f"departure timers {slot} and {twin} show the same time, so the "
                    "app's page cannot be matched to one; give one of them another "
                    "time first"
                )
            if edit:
                listing = await self._edit_timer(listing, slot, clock, days, repeat)
            if enabled is not None:
                await self._switch_timer(listing, slot, enabled)
        except CompanionTransportError as err:
            raise CompanionWriteBlocked(str(err)) from err
        finally:
            # Page → list → overview. Stops at the overview; BACK on a page
            # never saves (only Save does), so nothing unconfirmed is sent.
            await self._return_to_overview(3)

    async def _edit_timer(
        self,
        listing: list[UiNode],
        slot: int,
        clock: tuple[int, int] | None,
        days: tuple[str, ...] | None,
        repeat: bool | None,
    ) -> list[UiNode]:
        """Set the timer's page, Save, and read it back; the list after."""
        page, nodes = await self._open_timer_page(listing, slot)
        if page is None:
            raise CompanionWriteBlocked(f"could not open departure timer {slot} in the app")
        if page.time != departure_rows(listing)[slot - 1].time:
            raise CompanionWriteBlocked(
                f"the page that opened does not match departure timer {slot}'s row; "
                "nothing was changed"
            )
        want_clock = clock if clock is not None else (page.hour, page.minute)
        want_days = days if days is not None else page.weekdays
        want_repeat = page.repeat if repeat is None else repeat
        want = (f"{want_clock[0]:02d}:{want_clock[1]:02d}", want_days, want_repeat)
        if not want_repeat and len(want_days) != 1:
            raise CompanionWriteBlocked(
                "a departure timer without Repeat runs once, on exactly one weekday"
            )
        if want_clock[1] % page.minute_step:
            raise CompanionWriteBlocked(
                f"the app sets departure times in {page.minute_step}-minute steps"
            )
        if (page.time, page.weekdays, page.repeat) == want:
            back = await self._back_to_timer_list()
            if back is None:
                raise CompanionWriteBlocked("the app did not return to the Departure times list")
            return back  # nothing to change, nothing sent
        try:
            page, nodes = await self._set_timer_days(page, nodes, want_days, want_repeat)
            page, nodes = await self._set_timer_clock(page, nodes, *want_clock)
            if (page.time, page.weekdays, page.repeat) != want:
                raise CompanionWriteBlocked(
                    f"departure timer {slot} did not take the new setting; nothing was saved"
                )
            save = find_toolbar_text(nodes, self._toolbar_labels(TIMER_SAVE, "save"), page.top)
            if save is None or save.tap_point is None:
                raise CompanionWriteBlocked("the app did not offer Save for the departure timer")
        except (CompanionWriteBlocked, CompanionTransportError):
            await self._cancel_timer_page()
            raise
        # Save is the one tap that sends. Stamp first, so a transport that
        # fails after delivery still blocks an immediate repeat.
        self._stamp_write()
        for part in ("time", "weekdays", "repeat", "enabled"):
            self._nav_cache.pop(f"departure_timer_{slot}_{part}", None)
        self._nav_cache.pop("departure_timer_enabled_count", None)  # Save switches it on
        self._nav_only.add("departure_times")
        await self._t.tap(*save.tap_point)
        listing = await self._await_timer_saved(slot, want[0])
        # The list shows the time; the page shows days and Repeat.
        page, nodes = await self._open_timer_page(listing, slot)
        if page is None:
            raise CompanionWriteBlocked(
                f"departure timer {slot} was saved, but its page did not open to check it"
            )
        back = await self._back_to_timer_list()
        if (page.time, page.weekdays, page.repeat) != want:
            raise CompanionWriteBlocked(
                f"the app shows departure timer {slot} as {page.time} "
                f"{','.join(page.weekdays)} repeat={page.repeat} after saving"
            )
        for key, val in {f"departure_timer_{slot}_time": want[0], **page_fields(page, slot)}.items():
            self._nav_cache[key] = val
            self._nav_read_at[key] = self._wall()
            self._nav_cache_from[key] = "departure_times"
        if back is None:
            raise CompanionWriteBlocked("the app did not return to the Departure times list")
        return back

    def _toolbar_labels(self, key: str, fallback: str) -> set[str]:
        """The installed app's word for a toolbar item; English without tables."""
        labels = {
            label.strip().casefold() for label in self._app_strings.get(key, ()) if label.strip()
        }
        return labels or {fallback}

    async def _tap_timer_page(self, node: UiNode) -> tuple[TimerPage, list[UiNode]]:
        """Tap one control on the timer page and read the page back."""
        if node.tap_point is None:
            raise CompanionWriteBlocked("a departure timer control has no place on screen")
        await self._t.tap(*node.tap_point)
        nodes, cleared = await self._dump_and_clear_overlays(await self._settle())
        if self._limit_on_screen(nodes):
            self._trip_rate_limit()
            raise CompanionWriteBlocked(_LIMIT_REASON)
        page = read_timer_page(nodes) if cleared else None
        if page is None:
            raise CompanionWriteBlocked("a message covered the departure timer; nothing was saved")
        return page, nodes

    async def _set_timer_days(
        self, page: TimerPage, nodes: list[UiNode], days: tuple[str, ...], repeat: bool
    ) -> tuple[TimerPage, list[UiNode]]:
        """Days first (add before removing, so one is always on), then Repeat.

        The app refuses a timer without a day, and turns Repeat back on when
        a second day is picked; reading the whole page after every tap lets
        each step see what the app actually did.
        """
        for _ in range(_DAY_TAPS):
            missing = [d for d in days if d not in page.weekdays]
            extra = [d for d in page.weekdays if d not in days]
            if missing:
                node = page.days[missing[0]]
            elif extra:
                node = page.days[extra[0]]
            elif page.repeat != repeat:
                node = page.repeat_switch
            else:
                return page, nodes
            page, nodes = await self._tap_timer_page(node)
        raise CompanionWriteBlocked("the departure timer's days did not take; nothing was saved")

    async def _set_timer_clock(
        self, page: TimerPage, nodes: list[UiNode], hour: int, minute: int
    ) -> tuple[TimerPage, list[UiNode]]:
        """Step the wheels one value per tap: minutes, then hours, then AM/PM.

        Every tap is read back from the wheels' own values, so a wheel that
        carries over (minutes past :55, hours past 11 on a 12-hour phone)
        is simply corrected by the next steps.
        """
        for _ in range(_CLOCK_TAPS):
            node: UiNode | None
            if page.minute != minute:
                count = 60 // page.minute_step
                forward = (minute // page.minute_step - page.minute // page.minute_step) % count
                wheel = page.minute_wheel
                node = wheel.following if forward <= count - forward else wheel.previous
            elif page.meridiem_wheel is not None and page.hour % 12 == hour % 12 and page.hour != hour:
                wheel = page.meridiem_wheel
                node = wheel.following or wheel.previous
            elif page.hour != hour:
                count = 12 if page.meridiem_wheel is not None else 24
                forward = (hour % count - page.hour % count) % count
                wheel = page.hour_wheel
                node = wheel.following if forward <= count - forward else wheel.previous
            else:
                return page, nodes
            if node is None:
                raise CompanionWriteBlocked("a departure time wheel cannot move; nothing was saved")
            page, nodes = await self._tap_timer_page(node)
        raise CompanionWriteBlocked("the departure time wheels did not settle; nothing was saved")

    async def _cancel_timer_page(self) -> None:
        """Undo unsaved changes with the page's own Cancel, best-effort.

        A dropped link gets one reconnect, so a transport error mid-edit
        still leaves the page as it was saved. Cancel sends nothing.
        """
        for attempt in range(2):
            try:
                if attempt:
                    await self._t.connect()
                nodes, _cleared = await self._dump_and_clear_overlays()
                page = read_timer_page(nodes)
                if page is None:
                    return
                cancel = find_toolbar_text(nodes, self._toolbar_labels(TIMER_CANCEL, "cancel"), page.top)
                if cancel is not None and cancel.tap_point is not None:
                    await self._t.tap(*cancel.tap_point)
                    await self._settle()
                return
            except CompanionTransportError:
                continue

    async def _await_timer_saved(self, slot: int, time: str) -> list[UiNode]:
        """Wait for the app to send and return to the list; fail unless it does."""
        for _ in range(_SAVE_POLLS):
            nodes, cleared = await self._dump_and_clear_overlays()
            if self._limit_on_screen(nodes):
                self._trip_rate_limit()
                raise CompanionWriteBlocked(_LIMIT_REASON)
            if read_timer_page(nodes) is not None:
                continue  # still sending, or the app kept the page
            rows = departure_rows(nodes)
            if cleared and len(rows) >= slot:
                if rows[slot - 1].time != time:
                    raise CompanionWriteBlocked(
                        f"the app shows departure timer {slot} at {rows[slot - 1].time} "
                        f"after saving, not {time}"
                    )
                return nodes
            raise CompanionWriteBlocked(
                f"the app reported a problem saving departure timer {slot}"
            )
        raise CompanionWriteBlocked(
            f"the app did not confirm saving departure timer {slot}; check it in the app"
        )

    async def _switch_timer(self, listing: list[UiNode], slot: int, enabled: bool) -> None:
        """Tap the list's switch, which the app sends at once, and watch it.

        The app flips the switch straight away and flips it back if the car
        refuses. The change counts once the switch shows the new state on two
        identical dumps in a row; a flip back is a refusal.
        """
        row = departure_rows(listing)[slot - 1]
        if row.enabled == enabled:
            return  # nothing to change, nothing sent
        if row.switch.tap_point is None:
            raise CompanionWriteBlocked(f"departure timer {slot}'s switch has no place on screen")
        key = f"departure_timer_{slot}_enabled"
        self._stamp_write()
        self._nav_cache.pop(key, None)
        self._nav_cache.pop("departure_timer_enabled_count", None)
        self._nav_only.add("departure_times")
        await self._t.tap(*row.switch.tap_point)
        seen = False
        previous: str | None = None
        for _ in range(_SAVE_POLLS):
            xml = await self._t.dump_ui()
            nodes, cleared = await self._dump_and_clear_overlays(xml)
            if self._limit_on_screen(nodes):
                self._trip_rate_limit()
                raise CompanionWriteBlocked(_LIMIT_REASON)
            rows = departure_rows(nodes) if cleared else []
            index = slot - 1
            if not 0 <= index < len(rows):
                raise CompanionWriteBlocked(
                    f"the app showed a message instead of switching departure timer {slot}"
                )
            if rows[index].enabled == enabled:
                if seen and xml == previous:
                    break
                seen = True
            elif seen:
                raise CompanionWriteBlocked(
                    f"the app switched departure timer {slot} back: the car did not accept it"
                )
            previous = xml
        if not seen:
            raise CompanionWriteBlocked(
                f"the app did not switch departure timer {slot}; check it in the app"
            )
        self._nav_cache[key] = enabled
        self._nav_read_at[key] = self._wall()
        self._nav_cache_from[key] = "departure_times"

    async def sync_vehicle(self) -> bool:
        """Tap vehicle Settings → "Synchronise now", so the car sends fresh data.

        Unlike a screen read this wakes the car, so it is a write: it passes the
        same gate (verified preset, matching app version, no rate-limit, the
        minimum gap between commands). Returns True when the app started a sync,
        False when one was already running and nothing was tapped.
        """
        async with self._screen_lock:
            return await self._sync_vehicle_serialized()

    async def _sync_vehicle_serialized(self) -> bool:
        # #968 — the sync is also the probe that ends a power-budget pause:
        # while the car's power budget is used up, the app checks its own
        # capability status (1010, PowerBudgetReached) and answers the tap
        # with its alert without sending anything. Only that kind, and at most
        # once per _LIMIT_PROBE_GAP_S (see _may_probe_limit).
        spec, nodes = await self._command_gate("sync_vehicle", probe=True)
        nav = next((n for n in self._preset.nav_reads if n.name == spec.nav_read), None)
        if nav is None:
            raise CompanionWriteBlocked("the vehicle Settings path is not mapped")
        trips = self._limit_trips
        try:
            button = find_sync_button(nodes)
            if button is None:
                detail, _walked = await self._walk_to_detail(nav.path)
                if detail is None:
                    raise CompanionWriteBlocked("could not open the vehicle Settings")
                # The button is below the fold; swipe until it shows.
                for _ in range(_SYNC_SCROLLS):
                    if self._limit_on_screen(detail):
                        self._trip_rate_limit()
                        self._request_state = REQUESTS_RESTRICTED
                        raise CompanionWriteBlocked(_LIMIT_REASON)
                    button = find_sync_button(detail)
                    if button is not None:
                        break
                    detail = await self._scroll_up(detail)
                else:
                    button = find_sync_button(detail)
            if button is None or button.tap_point is None:
                raise CompanionWriteBlocked(
                    "could not find 'Synchronise now' on the vehicle Settings screen"
                )
            if not button.enabled:
                return False  # the app is already waiting for the car
            # Stamp first, so a transport that fails after delivery still
            # blocks an immediate repeat.
            self._stamp_write()
            await self._t.tap(*button.tap_point)
            nodes, _cleared = await self._dump_and_clear_overlays(await self._settle())
            if self._limit_on_screen(nodes):
                self._trip_rate_limit()
                self._request_state = REQUESTS_RESTRICTED
                raise CompanionWriteBlocked(_LIMIT_REASON)
            after = find_sync_button(nodes)
            # Positive evidence only: the limit alert can draw after the settle
            # dumps, so look a little longer (plain dumps, no taps) and count
            # the sync as taken only if the button is still disabled then.
            for _ in range(_SYNC_CONFIRM_DUMPS):
                if after is None or after.enabled:
                    break
                nodes = parse_ui_dump(await self._t.dump_ui())
                if self._limit_on_screen(nodes):
                    self._trip_rate_limit()
                    self._request_state = REQUESTS_RESTRICTED
                    raise CompanionWriteBlocked(_LIMIT_REASON)
                after = find_sync_button(nodes)
            if after is None or after.enabled:
                raise CompanionWriteBlocked("the app did not start the vehicle sync")
        except CompanionTransportError as err:
            raise CompanionWriteBlocked(str(err)) from err
        finally:
            try:
                left, _cleared = await self._dump_and_clear_overlays()
                await self._close_dialogs(left)
            except CompanionTransportError:
                pass
            await self._return_to_overview(2)
        if self._limit_trips != trips:
            # The limit alert arrived after the button changed, and the
            # cleanup closed it: the car refused the sync after all.
            self._request_state = REQUESTS_RESTRICTED
            raise CompanionWriteBlocked(_LIMIT_REASON)
        # Accepted: the car takes requests again, so the pause is over.
        self._rate_limited_until = 0.0
        self._limit_kind = None
        self._request_state = REQUESTS_AVAILABLE
        return True

    async def _command_gate(
        self, action: str, *, probe: bool = False
    ) -> tuple[ActionSelector, list[UiNode]]:
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
        # Rule 9: a newer build keeps reads, but writes need a listed build.
        if not app_version_listed(self._live_app_version, self._preset.verified_app_version):
            raise CompanionAppVersionUnverified(self._live_app_version)
        spec = next((a for a in self._preset.actions if a.action == action), None)
        if spec is None:
            raise CompanionWriteBlocked(f"no confirmed control for '{action}'")
        if spec.app_versions and not app_version_listed(
            self._live_app_version, spec.app_versions
        ):
            raise CompanionWriteBlocked(
                f"'{action}' is not mapped for app version {self._live_app_version}"
            )
        # v2.26.0 (ckomma #21) — if a rate-limit backoff is active, do not send.
        # #968 — except the sync probe through a power-budget pause, which the
        # app itself stops while the budget is used up; one per window, counted
        # here, before anything else can refuse it.
        if self._is_rate_limited():
            if probe and self._may_probe_limit():
                self._limit_probe_at = self._wall()
            else:
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
            if probe and cleared and self._is_alert(nodes):
                # An alert left over from an earlier request; the probe's own
                # tap is what tells whether the limit still holds.
                nodes, cleared = await self._close_dialogs(nodes, trip=False)
        except CompanionTransportError as err:
            raise CompanionWriteBlocked(str(err)) from err
        if not cleared:
            raise CompanionWriteBlocked(
                "a nag screen is up and did not clear; not tapping blind"
            )
        # Before the walk home below, whose BACK would close the alert unseen.
        if self._limit_on_screen(nodes):
            self._trip_rate_limit()
            raise CompanionWriteBlocked(_LIMIT_REASON)
        if self._preset.screen_anchor is not None and not has_anchor(nodes, self._preset):
            # Every command starts from the overview. A walk cut short can
            # leave a sub-screen with a change staged but not saved, which the
            # next Save would send too; the app's own up/Cancel discards it.
            # An empty dump is no screen to walk back from.
            if not nodes:
                raise CompanionWriteBlocked(
                    "the app's screen could not be read; not tapping blind"
                )
            await self._return_to_overview(3)
            try:
                nodes, cleared = await self._dump_and_clear_overlays()
            except CompanionTransportError as err:
                raise CompanionWriteBlocked(str(err)) from err
            if not cleared or not has_anchor(nodes, self._preset):
                raise CompanionWriteBlocked(
                    "the app did not return to its overview; not tapping blind"
                )
        if self._limit_on_screen(nodes):
            self._trip_rate_limit()
            raise CompanionWriteBlocked(_LIMIT_REASON)
        self._require_limit_language(nodes)
        return spec, nodes


def _hhmm(raw: str) -> tuple[int, int]:
    """ "07:30" (or "07:30:00") as (hour, minute); refuses anything else."""
    parts = raw.strip().split(":")
    if len(parts) in (2, 3) and all(p.isdigit() for p in parts):
        hour, minute = int(parts[0]), int(parts[1])
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            return hour, minute
    raise CompanionWriteBlocked(f"'{raw}' is not a departure time (HH:MM)")


def _weekdays(raw: "tuple[str, ...] | list[str]") -> tuple[str, ...]:
    """Day codes in the app's order; "MONDAY" and "mon" alike."""
    picked = set()
    for day in raw:
        code = str(day).strip().lower()[:3]
        if code not in WEEKDAYS:
            raise CompanionWriteBlocked(f"'{day}' is not a weekday")
        picked.add(code)
    if not picked:
        raise CompanionWriteBlocked("a departure timer needs at least one weekday")
    return tuple(code for code in WEEKDAYS if code in picked)
