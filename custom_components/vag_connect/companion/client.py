# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Companion (ADB) client adapter — v3.0.0-alpha.

Presents the same duck-typed surface the coordinator already expects from a
CARIAD client (``authenticate`` / ``get_vehicles`` / ``get_status`` /
``command_*``), so the companion channel slots in as just another source with
no special-casing in the poll loop. The token/portal/MBB attributes the
coordinator touches via ``getattr(..., default)`` simply are not here, so those
paths fall through cleanly.

There is no network login: the "auth" is the phone already being signed into the
app. ``get_vehicles`` returns the single VIN the user entered at setup, because
this channel reads one phone showing one account's car.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Awaitable, Callable

from ..cariad.models import VehicleData
from .channel import CompanionChannel, CompanionWriteBlocked, mark_unsettled
from .climate import ClimateController, snap_temperature
from .presets import ACTION_TO_COMMAND, PRESETS
from .transport import NetworkAdbTransport

_LOGGER = logging.getLogger(__name__)

# How long an unload waits for a running screen walk before closing under it.
# The same bound the coordinator gives a command waiting for the poll.
_CLOSE_WAIT_S = 60.0
# After an unload that could not confirm the phone finished its last command,
# the next client on the same phone waits this long before its first walk.
_SETTLE_S = 30.0


@dataclass
class ClimateTargets:
    """The climate Start's mode and temperature, as HA holds them.

    ``temp_c`` None means none was set yet: Start leaves the dial alone.
    ``app_dial_c`` is the dial value last read from the app. A read that
    differs from it means the dial was changed in the app (the app saves
    every dial change to the car), so that value becomes the held one.
    """

    window_heating_only: bool = False
    temp_c: float | None = None
    app_dial_c: float | None = None
    # A held value restored without the dial it was held against: the next
    # read cannot be compared, so it wins.
    adopt_next_dial: bool = False

    def note_app_dial(self, value: object) -> bool:
        """Take in a dial read; True when it replaced the held temperature."""
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            return False
        read = float(value)
        changed = self.adopt_next_dial or (
            self.app_dial_c is not None and read != self.app_dial_c
        )
        self.app_dial_c = read
        self.adopt_next_dial = False
        if changed and self.temp_c is not None and self.temp_c != read:
            self.temp_c = read
            return True
        return False

    def restore(self, held: float, app_dial_c: float | None) -> None:
        """Restore a held temperature saved with the dial it was held against."""
        if self.temp_c is not None:
            return  # set since startup
        if self.app_dial_c is None:
            # No read yet: the first one is compared with the saved dial.
            self.temp_c = held
            self.app_dial_c = app_dial_c
            self.adopt_next_dial = app_dial_c is None
        elif app_dial_c is not None and app_dial_c == self.app_dial_c:
            # Read already, and the dial is where it was: still held.
            self.temp_c = held
        # Otherwise the dial moved in the app while HA was down: it wins.


def climate_targets_of(coordinator: Any) -> ClimateTargets | None:
    """The companion client's held climate targets, or None for any other entry."""
    if not coordinator.is_companion():
        return None
    targets = getattr(getattr(coordinator, "_cariad_client", None), "climate_targets", None)
    return targets if isinstance(targets, ClimateTargets) else None


# start_climate_control fields the Air Conditioning sheet has no control for.
_RICH_CLIMATE_ONLY = (
    "glass_heating", "seat_fl", "seat_fr", "seat_rl", "seat_rr",
    "climatisation_at_unlock", "climatisation_mode",
)

# VehicleData flags that default to False; only the opt-in departure-times
# read supplies them.
_UNREAD_FLAGS = (
    "departure_timer_1_enabled", "departure_timer_2_enabled", "departure_timer_3_enabled",
)


class CompanionClient:
    """Coordinator-compatible client backed by a companion phone."""

    # Which companion transport produced a reading, surfaced on VehicleData and
    # in diagnostics. A class default so it holds for any instance, including
    # the relay path overriding it below.
    _source_channel = "companion_adb"

    def __init__(
        self,
        *,
        brand: str,
        vin: str,
        host: str,
        port: int,
        adbkey_path: str,
        time_fn: Callable[[], float],
        read_charge_detail: bool = False,
        wake_sleep: bool = False,
        close_app: bool = False,
        use_addon: bool = False,
        addon_token: str = "",
        relay_broker: object | None = None,
        nav_opt_ins: "frozenset[str] | set[str] | None" = None,
    ) -> None:
        self._brand = brand.lower()
        self._vin = vin.upper()
        preset = PRESETS.get(self._brand)
        if preset is None:
            raise ValueError(f"no companion preset for brand {brand!r}")
        if relay_broker is not None:
            # v4.4.0 (#968) — the phone drives the connection: its agent app
            # long-polls HA and we answer with screen verbs. There is nothing to
            # dial, so host/port/adbkey go unused on this path.
            from .relay import CompanionRelayBroker  # noqa: PLC0415
            from .relay_transport import AgentRelayTransport  # noqa: PLC0415

            if not isinstance(relay_broker, CompanionRelayBroker):  # pragma: no cover
                raise TypeError("relay_broker must be a CompanionRelayBroker")
            self._transport: NetworkAdbTransport = AgentRelayTransport(
                relay_broker, wake_sleep=wake_sleep, close_app=close_app
            )
            self._source_channel = "companion_relay"
        elif use_addon:
            # host/port address the ADB Bridge add-on, which owns the phone
            # connection. Everything above the wire is identical, so the
            # channel below neither knows nor cares which transport it got.
            from .addon_transport import AddOnAdbTransport  # noqa: PLC0415

            self._transport = AddOnAdbTransport(
                host, port, token=addon_token, wake_sleep=wake_sleep,
                close_app=close_app,
            )
        else:
            self._transport = NetworkAdbTransport(
                host, port, adbkey_path, wake_sleep=wake_sleep, close_app=close_app
            )
        self._channel = CompanionChannel(
            self._transport, preset, time_fn=time_fn,
            read_charge_detail=read_charge_detail,
            nav_opt_ins=nav_opt_ins,
        )
        # Who else could be driving this phone: an unloaded client under the
        # same VIN or the same ADB address (see ``close``).
        self._phone_keys = (f"vin:{self._vin}",) + (
            (f"adb:{host}:{port}",) if host and relay_broker is None else ()
        )
        self._channel._screen_lock.phone_keys = self._phone_keys
        # Last snapshot we actually read, so a throttled poll can return the
        # known values instead of a spurious no_data that the coordinator would
        # count as a failed poll (the channel reads far less often than the poll
        # interval on purpose).
        self._last_data: VehicleData | None = None
        # Attributes the coordinator reads via getattr with a default; declared
        # here so a plain attribute access also works.
        self.on_tokens_changed: Callable[[Any], None] | None = None
        self._eu_portal = None
        self._tokens = None

    async def set_transport_flags(self, *, wake_sleep: bool, close_app: bool) -> None:
        """Apply the wake/sleep and close-app options live, between screen uses."""
        async with self._channel._screen_lock:
            self._channel._t._wake_sleep = bool(wake_sleep)
            self._channel._t._close_app = bool(close_app)

    # -- token/portal no-ops the coordinator may call directly ----------------

    def set_persisted_tokens(self, _tokens: Any) -> None:
        """No stored tokens on this channel; nothing to restore."""

    def set_website_authproxy_mode(self, *_args: Any, **_kwargs: Any) -> None:
        """No supplementary web channel on this channel."""

    # -- the read surface -----------------------------------------------------

    async def authenticate(self) -> None:
        """'Auth' is the phone being signed in; just open the ADB connection."""
        await self._transport.connect()

    async def get_vehicles(self) -> list[str]:
        return [self._vin]

    async def get_status(self, vin: str) -> VehicleData:
        """Read the app screen and map it onto a VehicleData for this VIN.

        A read that matches nothing returns a ``no_data`` VehicleData rather
        than raising, so the coordinator's own no-data failsafe (keep
        last-known-good visible) applies exactly as it does for a portal outage.
        """
        async with self._screen():
            fields = await self._channel.read()
        # None = the channel is in its post-failure cooldown. Return the last
        # snapshot we actually took so the coordinator sees unchanged-but-valid
        # data, not a no_data its poll loop would count as a failure (which
        # would self-reinforce the cooldown). On the very first poll (nothing
        # read yet) fall through to a no_data VehicleData.
        if fields is None and self._last_data is not None:
            return self._last_data
        data = VehicleData(vin=vin.upper())
        # The model defaults these to False for the cloud parsers; without
        # the departure-times read "off" would be a value nobody read.
        # Unknown keeps the entities hidden; a read overwrites them below.
        for key in _UNREAD_FLAGS:
            setattr(data, key, None)
        data.companion_nav_read_at = getattr(self._channel, "nav_read_at", None) or {}
        data.source_channel = self._source_channel
        # #968 — what the vehicle sync flow last found, kept with every read.
        data.companion_request_state = getattr(self._channel, "request_state", None)
        if not fields:  # None (first-ever throttle) or {} (empty screen)
            data.no_data = True
            return data
        for key, val in fields.items():
            if hasattr(data, key):
                setattr(data, key, val)
        # #1552 — companion is a single source with no merge pass, so it never
        # reaches the multi-channel drivetrain inference (_channel_merge). A parsed
        # SoC or range still means this car has a traction battery, so set the flag
        # here (mirrors the brand parsers, e.g. skoda.py / seat_cupra.py) — without
        # it the electric entities stay hidden behind their has_battery gate.
        if data.battery_soc is not None or data.electric_range_km is not None:
            data.has_battery = True
        # A PHEV's petrol range must unlock the existing combustion sensors;
        # fuel percentage is optional and must never be inferred from range.
        if data.fuel_level is not None or data.combustion_range_km is not None:
            data.has_combustion = True
        data.is_hybrid = data.has_battery and data.has_combustion
        # A companion read is a two-way-capable source only when writes are on;
        # expose that so the entity layer can reflect it.
        data.companion_writes_enabled = self._channel.writes_enabled
        data.companion_app_version = getattr(self._channel, "live_app_version", None)
        data.companion_source_age_s = self._channel.source_data_age_s
        if "target_temperature" in fields:
            self.climate_targets.note_app_dial(fields["target_temperature"])
        self._last_data = data
        return data

    def set_nav_opt_in(self, opt_in: str, enabled: bool) -> None:
        """Turn one companion nav read on or off without a reload."""
        self._channel.set_nav_opt_in(opt_in, enabled)

    # -- the command surface --------------------------------------------------

    def supports_command(self, command_name: str) -> bool:
        """Expose only commands with an actual control in this brand preset."""
        return any(
            ACTION_TO_COMMAND.get(a.action) == command_name
            for a in PRESETS[self._brand].actions
        )

    async def _dispatch(self, command_name: str) -> None:
        action = next(
            (a for a, cmd in ACTION_TO_COMMAND.items() if cmd == command_name), None
        )
        if action is None:
            from ..cariad.exceptions import VehicleCommandError  # noqa: PLC0415

            raise VehicleCommandError(
                command_name,
                "this command is not available on the companion (ADB) channel",
            )
        try:
            await self._channel.do_action(action)
        except CompanionWriteBlocked as err:
            from ..cariad.exceptions import VehicleCommandError  # noqa: PLC0415

            raise VehicleCommandError(command_name, str(err)) from err

    def _screen(self) -> asyncio.Lock:
        """Climate commands walk the app's screens; polls must not interleave."""
        lock = self.__dict__.get("_screen_lock")
        if lock is None:
            lock = self.__dict__["_screen_lock"] = asyncio.Lock()
        return lock

    @property
    def _climate(self) -> ClimateController:
        ctrl = self.__dict__.get("_climate_ctrl")
        if ctrl is None:
            ctrl = self.__dict__["_climate_ctrl"] = ClimateController(self._channel)
        return ctrl

    async def _climate_command(
        self, command_name: str, run: Callable[[], Awaitable[Any]]
    ) -> None:
        """Run one Air Conditioning sheet command, serialised with polling."""
        from ..cariad.exceptions import VehicleCommandError  # noqa: PLC0415

        if not self.supports_command(command_name):
            raise VehicleCommandError(
                command_name,
                "this command is not available on the companion (ADB) channel",
            )
        # Charge commands hold the channel's own lock where it has one; share it
        # so a climate walk and a charge walk can never overlap either.
        channel_lock = getattr(self._channel, "_screen_lock", None)
        try:
            async with self._screen():
                if isinstance(channel_lock, asyncio.Lock):
                    async with channel_lock:
                        await run()
                else:
                    await run()
        except CompanionWriteBlocked as err:
            raise VehicleCommandError(command_name, str(err)) from err

    # -- what the next climate Start applies (held in HA) -----------------------

    @property
    def climate_targets(self) -> ClimateTargets:
        """The mode and temperature the next climate Start applies.

        Set by the climate entity (restored across restarts by it); a poll
        only replaces the temperature when the dial was changed in the app.
        Storing them sends nothing.
        """
        targets = self.__dict__.get("_climate_targets")
        if targets is None:
            targets = self.__dict__["_climate_targets"] = ClimateTargets()
        return targets

    def store_climate_start_mode(self, window_heating_only: bool) -> None:
        """Store the mode for the next Start. No phone or car traffic."""
        self.climate_targets.window_heating_only = bool(window_heating_only)

    def store_climate_target_temperature(self, temp_c: float) -> float:
        """Store the temperature for the next Start, on the app's 0.5 °C grid."""
        target = snap_temperature(float(temp_c))
        self.climate_targets.temp_c = target
        # Chosen in HA: the next read of the unchanged dial must not undo it.
        self.climate_targets.adopt_next_dial = False
        return target

    def restore_climate_target_temperature(
        self, temp_c: float, app_dial_c: float | None,
    ) -> None:
        """Restore a held temperature with the app dial it was held against."""
        self.climate_targets.restore(snap_temperature(float(temp_c)), app_dial_c)

    def _start_with_targets(self) -> Awaitable[None]:
        targets = self.climate_targets
        return self._climate.start(
            window_heating_only=targets.window_heating_only, temp_c=targets.temp_c,
        )

    async def command_start_climate(self, vin: str, *_a: Any, **_k: Any) -> None:
        await self._climate_command("command_start_climate", self._start_with_targets)

    async def command_start_climate_control(
        self, vin: str, *_a: Any, temp_c: float | None = None, **kwargs: Any
    ) -> None:
        from ..cariad.exceptions import VehicleCommandError  # noqa: PLC0415

        # The sheet has a mode, a dial and Start: the rest of the rich payload
        # has no control there, so a call that sets any of it is refused.
        unsupported = [key for key in _RICH_CLIMATE_ONLY if kwargs.get(key) is not None]
        if unsupported:
            raise VehicleCommandError(
                "command_start_climate_control",
                f"the companion (ADB) channel cannot set {', '.join(unsupported)}; "
                "nothing was sent",
            )

        async def run() -> None:
            # temp_c becomes the held temperature, which Start then applies.
            if temp_c is not None:
                self.store_climate_target_temperature(float(temp_c))
            await self._start_with_targets()

        await self._climate_command("command_start_climate", run)

    async def command_stop_climate(self, vin: str, *_a: Any, **_k: Any) -> None:
        await self._climate_command("command_stop_climate", self._climate.stop)

    async def command_start_window_heating(self, vin: str, *_a: Any, **_k: Any) -> None:
        # A one-off override: window heating alone, whatever mode HA holds for
        # the climate Start, and the held mode is left as it is.
        await self._climate_command(
            "command_start_window_heating",
            lambda: self._climate.start(window_heating_only=True),
        )

    async def command_stop_window_heating(self, vin: str, *_a: Any, **_k: Any) -> None:
        await self._climate_command(
            "command_stop_window_heating",
            lambda: self._climate.stop(window_heating_only=True),
        )

    async def command_set_climate_temperature(
        self, vin: str, *_a: Any, temp_c: float | None = None, **_k: Any
    ) -> None:
        from ..cariad.exceptions import VehicleCommandError  # noqa: PLC0415

        if not self.supports_command("command_set_climate_temperature"):
            raise VehicleCommandError(
                "command_set_climate_temperature",
                "this command is not available on the companion (ADB) channel",
            )
        if temp_c is None:
            raise VehicleCommandError(
                "command_set_climate_temperature", "no target temperature given"
            )
        # Held for the next Start either way. A running air conditioning also
        # gets the dial moved now: the app sends that change to the car itself
        # (one request). Off, or window heating alone, nothing is tapped.
        target = self.store_climate_target_temperature(float(temp_c))

        async def run() -> None:
            if await self._climate.adjust(target):
                self.climate_targets.app_dial_c = target

        await self._climate_command("command_set_climate_temperature", run)

    async def command_start_charging(self, vin: str, *_a: Any, **_k: Any) -> None:
        await self._dispatch("command_start_charging")

    async def command_stop_charging(self, vin: str, *_a: Any, **_k: Any) -> None:
        await self._dispatch("command_stop_charging")

    # The app's slider takes 50 … 100 % in 10 % steps; the number entity reads
    # these bounds so it offers exactly what the slider can save.
    target_soc_bounds = (50, 100, 10)

    async def command_set_target_soc(self, vin: str, target: int) -> None:
        from ..cariad.exceptions import VehicleCommandError  # noqa: PLC0415

        if not self.supports_command("command_set_target_soc"):
            raise VehicleCommandError(
                "command_set_target_soc",
                "this command is not available on the companion (ADB) channel",
            )
        try:
            await self._channel.set_charge_target(target)
        except CompanionWriteBlocked as err:
            raise VehicleCommandError("command_set_target_soc", str(err)) from err

    async def _climate_setting(self, command_name: str, key: str, enabled: bool) -> None:
        """One Climate Settings switch, saved and read back by the channel."""
        from ..cariad.exceptions import VehicleCommandError  # noqa: PLC0415

        if not self.supports_command(command_name):
            raise VehicleCommandError(
                command_name,
                "this command is not available on the companion (ADB) channel",
            )
        try:
            # The channel's screen lock keeps polls and other commands out.
            await self._channel.set_climate_setting(key, enabled)
        except CompanionWriteBlocked as err:
            raise VehicleCommandError(command_name, str(err)) from err

    async def command_set_climate_at_unlock(
        self, vin: str, *_a: Any, enabled: bool, **_k: Any
    ) -> None:
        await self._climate_setting("command_set_climate_at_unlock", "climate_at_unlock", enabled)

    async def command_set_window_heating_auto(
        self, vin: str, *_a: Any, enabled: bool, **_k: Any
    ) -> None:
        await self._climate_setting(
            "command_set_window_heating_auto", "window_heating_enabled", enabled
        )

    async def command_set_climate_zone_front_left(
        self, vin: str, *_a: Any, enabled: bool, **_k: Any
    ) -> None:
        await self._climate_setting(
            "command_set_climate_zone_front_left", "climate_zone_front_left", enabled
        )

    async def command_set_climate_zone_front_right(
        self, vin: str, *_a: Any, enabled: bool, **_k: Any
    ) -> None:
        await self._climate_setting(
            "command_set_climate_zone_front_right", "climate_zone_front_right", enabled
        )

    async def command_set_departure_timer(
        self,
        vin: str,
        timer_id: int,
        enabled: bool | None = None,
        departure_time: str | None = None,
        recurring_on: list[str] | None = None,
        charging: bool | None = None,
        climatisation: bool | None = None,
        target_soc_pct: int | None = None,
        one_off_day: str | None = None,
        **_k: Any,
    ) -> None:
        """One Departure times timer, through the VW app's own screens.

        ``enabled`` is the list's switch; ``departure_time`` ("HH:MM" or an
        ISO datetime, the car's local time), ``recurring_on`` (weekdays, with
        Repeat on) and ``one_off_day`` (a date within the next week, Repeat
        off: the app's one-time timer is a weekday, not a date) are set on
        the timer's page. Charging, climatisation and target charge level are
        not on that page in app 4.6.4, so they are refused, not ignored.
        """
        from ..cariad.exceptions import VehicleCommandError  # noqa: PLC0415

        command = "command_set_departure_timer"
        if not self.supports_command(command):
            raise VehicleCommandError(
                command, "this command is not available on the companion (ADB) channel"
            )
        if charging is not None or climatisation is not None or target_soc_pct is not None:
            raise VehicleCommandError(
                command,
                "the app's departure timer page has no charging, climatisation or "
                "target charge level setting; leave those empty on the companion channel",
            )
        if recurring_on and one_off_day:
            raise VehicleCommandError(command, "give either recurring_on or one_off_day, not both")
        time = departure_time
        if isinstance(time, str) and "T" in time:
            time = time.split("T", 1)[1][:5]
        weekdays: list[str] | None = list(recurring_on) if recurring_on else None
        repeat: bool | None = True if weekdays else None
        if one_off_day:
            day = _one_off_weekday(one_off_day)
            if day is None:
                raise VehicleCommandError(
                    command,
                    f"one_off_day '{one_off_day}' must be a date (YYYY-MM-DD) within the next "
                    "seven days: the app's one-time timer runs on the next such weekday",
                )
            weekdays, repeat = [day], False
        try:
            await self._channel.set_departure_timer(
                int(timer_id), enabled=enabled, time=time, weekdays=weekdays, repeat=repeat,
            )
        except CompanionWriteBlocked as err:
            raise VehicleCommandError(command, str(err)) from err

    async def command_sync_vehicle(self, vin: str, *_a: Any, **_k: Any) -> bool:
        """Ask the car for fresh data via the app's "Synchronise now".

        True when a sync started, False when the app was already running one.
        """
        from ..cariad.exceptions import VehicleCommandError  # noqa: PLC0415

        if not self.supports_command("command_sync_vehicle"):
            raise VehicleCommandError(
                "command_sync_vehicle",
                "this command is not available on the companion (ADB) channel",
            )
        try:
            # The channel's screen lock keeps polls and other commands out.
            return await self._channel.sync_vehicle()
        except CompanionWriteBlocked as err:
            raise VehicleCommandError("command_sync_vehicle", str(err)) from err

    # -- rate-limit persistence + manual reset (delegated to the channel) ------

    @property
    def companion_rate_limited_until(self) -> float:
        """Wall-clock time until the channel is backed off (0 = not). The
        coordinator persists this so a lockout survives a restart."""
        return self._channel.rate_limited_until

    def restore_rate_limit(self, until: float) -> None:
        """Re-apply a persisted rate-limit backoff at setup."""
        self._channel.restore_rate_limit(until)

    @property
    def companion_last_write_at(self) -> float:
        """Wall-clock time of the last command tap (0 = none). Persisted with
        the backoff so the gap between commands survives a restart."""
        return self._channel.last_write_at

    def restore_last_write(self, at: float) -> None:
        """Re-apply a persisted last command time at setup."""
        self._channel.restore_last_write(at)

    def restore_synced_at(self, seen: datetime) -> None:
        """Re-apply the last known car sync time at setup."""
        self._channel.restore_synced_at(seen)

    def walk_details_next_read(self) -> None:
        """Have the next read walk every opted-in detail screen."""
        self._channel.walk_details_next_read()

    def reset_cooldown(self) -> None:
        """Clear a stuck failure/rate-limit backoff (user-initiated retry)."""
        self._channel.reset_cooldown()

    async def close(self) -> None:
        """Entry unload/reload: let a running walk finish, then close for good.

        A read or command that holds the screen lock gets up to
        ``_CLOSE_WAIT_S`` to finish, its cleanup included, so the reloaded
        entry's first read never interleaves with it. Anything queued behind it
        is refused (see ``_ScreenLock``), and the transport never reconnects.

        When the phone cannot be confirmed idle (the wait ran out, the close was
        cancelled, or a command sent did not answer), the next client on this
        phone waits ``_SETTLE_S`` before its first walk, which starts from a
        fresh dump.
        """
        lock = getattr(self._channel, "_screen_lock", None)
        held = False
        settled = False
        try:
            if isinstance(lock, asyncio.Lock):
                take = getattr(lock, "acquire_to_close", lock.acquire)
                try:
                    async with asyncio.timeout(_CLOSE_WAIT_S):
                        await take()
                    held = True
                except TimeoutError:
                    _LOGGER.warning(
                        "companion: a screen walk was still running %.0fs into "
                        "the unload; closing the connection under it",
                        _CLOSE_WAIT_S,
                    )
            else:
                held = True
        finally:
            # Also on cancellation: the transport must still shut down.
            try:
                shutdown = getattr(self._transport, "shutdown", None)
                if callable(shutdown):
                    answered = await shutdown()
                else:
                    await self._transport.close()
                    answered = True
                settled = held and answered is not False
            finally:
                if held and isinstance(lock, asyncio.Lock):
                    lock.release()
                if not settled:
                    mark_unsettled(getattr(self, "_phone_keys", ()), _SETTLE_S)


def _one_off_weekday(raw: str, today: "date | None" = None) -> str | None:
    """The weekday code of a one-off date, if the app can express it.

    The app's one-time timer is a weekday that fires at its next occurrence,
    so only today and the six days after it map onto one. "Today" is Home
    Assistant's local date: the car and Home Assistant are assumed to share a
    time zone.
    """
    try:
        day = date.fromisoformat(str(raw).strip()[:10])
    except ValueError:
        return None
    if today is None:
        try:
            from homeassistant.util import dt as dt_util  # noqa: PLC0415

            today = dt_util.now().date()
        except ImportError:  # pragma: no cover - outside Home Assistant
            today = date.today()
    if not 0 <= (day - today).days <= 6:
        return None
    return ("mon", "tue", "wed", "thu", "fri", "sat", "sun")[day.weekday()]
