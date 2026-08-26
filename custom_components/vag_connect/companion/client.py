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

import logging
from typing import Any, Callable

from ..cariad.models import VehicleData
from .channel import CompanionChannel, CompanionWriteBlocked
from .presets import ACTION_TO_COMMAND, PRESETS
from .transport import NetworkAdbTransport

_LOGGER = logging.getLogger(__name__)


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
                relay_broker, wake_sleep=wake_sleep
            )
            self._source_channel = "companion_relay"
        elif use_addon:
            # host/port address the ADB Bridge add-on, which owns the phone
            # connection. Everything above the wire is identical, so the
            # channel below neither knows nor cares which transport it got.
            from .addon_transport import AddOnAdbTransport  # noqa: PLC0415

            self._transport = AddOnAdbTransport(
                host, port, token=addon_token, wake_sleep=wake_sleep
            )
        else:
            self._transport = NetworkAdbTransport(
                host, port, adbkey_path, wake_sleep=wake_sleep
            )
        self._channel = CompanionChannel(
            self._transport, preset, time_fn=time_fn,
            read_charge_detail=read_charge_detail,
            nav_opt_ins=nav_opt_ins,
        )
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
        fields = await self._channel.read()
        # None = the channel is in its post-failure cooldown. Return the last
        # snapshot we actually took so the coordinator sees unchanged-but-valid
        # data, not a no_data its poll loop would count as a failure (which
        # would self-reinforce the cooldown). On the very first poll (nothing
        # read yet) fall through to a no_data VehicleData.
        if fields is None and self._last_data is not None:
            return self._last_data
        data = VehicleData(vin=vin.upper())
        data.source_channel = self._source_channel
        if not fields:  # None (first-ever throttle) or {} (empty screen)
            data.no_data = True
            return data
        for key, val in fields.items():
            if hasattr(data, key):
                setattr(data, key, val)
        # A companion read is a two-way-capable source only when writes are on;
        # expose that so the entity layer can reflect it.
        data.companion_writes_enabled = self._channel.writes_enabled
        data.companion_source_age_s = self._channel.source_data_age_s
        self._last_data = data
        return data

    # -- the command surface --------------------------------------------------

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

    async def command_start_climate(self, vin: str, *_a: Any, **_k: Any) -> None:
        await self._dispatch("command_start_climate")

    async def command_start_climate_control(self, vin: str, *_a: Any, **_k: Any) -> None:
        await self._dispatch("command_start_climate")

    async def command_stop_climate(self, vin: str, *_a: Any, **_k: Any) -> None:
        await self._dispatch("command_stop_climate")

    async def command_start_charging(self, vin: str, *_a: Any, **_k: Any) -> None:
        await self._dispatch("command_start_charging")

    async def command_stop_charging(self, vin: str, *_a: Any, **_k: Any) -> None:
        await self._dispatch("command_stop_charging")

    # -- rate-limit persistence + manual reset (delegated to the channel) ------

    @property
    def companion_rate_limited_until(self) -> float:
        """Wall-clock time until the channel is backed off (0 = not). The
        coordinator persists this so a lockout survives a restart."""
        return self._channel.rate_limited_until

    def restore_rate_limit(self, until: float) -> None:
        """Re-apply a persisted rate-limit backoff at setup."""
        self._channel.restore_rate_limit(until)

    def reset_cooldown(self) -> None:
        """Clear a stuck failure/rate-limit backoff (user-initiated retry)."""
        self._channel.reset_cooldown()

    async def close(self) -> None:
        await self._transport.close()
