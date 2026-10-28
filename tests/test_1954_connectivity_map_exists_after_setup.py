# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#1954 (@InfObject, VW ID. Buzz) — the per-source connectivity map must exist
by the time ``async_setup`` returns, not only after the first poll tick.

The per-source connectivity binary_sensors (``VagSourceConnectivitySensor``) are
created one per key of the vehicle's ``channel_status`` map. That map was computed
on the poll path only, so after every setup and every reload the sensors sat at
"unavailable (restored)" for up to a whole poll interval — which reads as "this
source is broken" rather than "not measured yet". ``_compute_channel_status`` is
local-only (no await, no network), so the setup reconcile block now computes it
too, fail-soft, just before ``_apply_optimistic_hold``.

Harness mirrors tests/test_companion_nonblocking_startup.py (coordinator via
``__new__``, factory/client patched, ``asyncio.run(coord.async_setup())``) and
the bare ``_coord``/``_client`` pair of tests/test_source_connectivity.py for the
reference compute.
"""
from __future__ import annotations

import asyncio
import threading
import time
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from custom_components.vag_connect.cariad.models import VehicleData

VIN = "TMBEL9NEXP1001954"


def _coord(entry_data: dict[str, Any], restored: dict[str, Any] | None = None) -> Any:
    from custom_components.vag_connect.coordinator import VagConnectCoordinator

    coord = VagConnectCoordinator.__new__(VagConnectCoordinator)
    coord.hass = MagicMock()
    coord.hass.loop = MagicMock()
    coord.hass.loop.call_soon_threadsafe = MagicMock()
    coord.entry = MagicMock()
    coord.entry.entry_id = "test"
    coord.entry.data = dict(entry_data)
    coord.entry.options = {}
    coord._vehicles_lock = threading.Lock()
    coord._cariad_client = None
    coord._started = False
    coord._was_available = True
    coord.vehicles = {VIN: dict(restored)} if restored else {}
    coord.vehicle_success = {}
    coord.data = None
    coord.async_set_updated_data = MagicMock()
    coord.async_request_refresh = AsyncMock()
    coord.logger = MagicMock()
    return coord


def _entry() -> dict[str, Any]:
    return {
        "brand": "skoda", "username": "u@t.de",
        "password": "pw", "spin": "", "scan_interval": 5,
    }


def _client(status: Any = None, **armed: Any) -> MagicMock:
    """A client with EXPLICIT channel arming.

    Every attribute ``_armed_data_channels`` and ``_primary_channel_name`` read
    is pinned here: a bare MagicMock auto-creates them, which would arm every
    channel by accident and make the armed set untestable. ``_eu_portal`` is
    None so the primary stays the brand channel, and ``supplementary_readers``
    is None so the merge takes its no-suppliers branch (still provenance-
    annotated — that is what gives ``field_sources`` its primary-channel
    entries) instead of calling into a mock reader.
    """
    client = MagicMock()
    client.authenticate = AsyncMock()
    client.get_vehicles = AsyncMock(return_value=[VIN])
    client.get_status = AsyncMock(
        return_value=status
        or VehicleData(vin=VIN, battery_soc=55, odometer_km=1234)
    )
    client.supplementary_readers = None
    client.set_official_mode = None
    client.arm_supplementary_official = None
    client._eu_portal = None
    channels = dict(
        _supplementary_authproxy=None,
        _supplementary_eu_portal=object(),
        _supplementary_tibber=None,
        _supplementary_official=object(),
    )
    channels.update(armed)
    for attr, value in channels.items():
        setattr(client, attr, value)
    return client


def _run_setup(coord: Any, client: MagicMock) -> bool:
    from custom_components.vag_connect.cariad.api.factory import CariadClientFactory

    with patch.object(CariadClientFactory, "create", return_value=client), \
         patch(
             "homeassistant.helpers.aiohttp_client.async_get_clientsession",
             return_value=MagicMock(),
         ):
        return asyncio.run(coord.async_setup())


def _close_background_coros(coord: Any) -> None:
    """The scheduled background coroutines never ran (hass is a mock)."""
    for call in coord.hass.async_create_background_task.call_args_list:
        coro = call.args[0]
        if asyncio.iscoroutine(coro):
            coro.close()


def _setup(coord: Any, client: MagicMock) -> bool:
    try:
        return _run_setup(coord, client)
    finally:
        _close_background_coros(coord)


def _reference_coord(entry_data: dict[str, Any], client: Any) -> Any:
    """A bare coordinator for computing the reference map, same shape as the
    ``_coord`` helper in tests/test_source_connectivity.py. Deliberately NOT the
    coordinator under test: a fresh ``_channel_last_active`` keeps the reference
    independent of the setup run's bookkeeping."""
    from custom_components.vag_connect.coordinator import VagConnectCoordinator

    ref = VagConnectCoordinator.__new__(VagConnectCoordinator)
    ref.hass = MagicMock()
    ref.entry = MagicMock()
    ref.entry.data = dict(entry_data)
    ref._cariad_client = client
    return ref


def _without_timestamps(status: dict[str, Any]) -> dict[str, Any]:
    """``last_active`` is wall-clock and per-coordinator, so it is the one field
    a reference compute cannot reproduce; everything else must match exactly."""
    return {
        token: {k: v for k, v in entry.items() if k != "last_active"}
        for token, entry in status.items()
    }


# ── the map exists when setup returns ───────────────────────────────────────


class TestChannelStatusPresentAfterSetup:
    def test_stored_vehicle_has_a_non_empty_channel_status(self) -> None:
        entry_data = _entry()
        coord = _coord(entry_data)
        client = _client()
        assert _setup(coord, client) is True
        stored = coord.vehicles[VIN]
        assert "channel_status" in stored, (
            "#1954: the per-source connectivity map is missing right after "
            "setup, so every connectivity sensor stays unavailable until the "
            "first poll tick"
        )
        status = stored["channel_status"]
        assert isinstance(status, dict)
        assert status, "armed channels exist, so the map must not be empty"

    def test_every_armed_channel_has_an_entry(self) -> None:
        """Three channels are armed here (brand primary + portal supplementary +
        the Škoda official one), so the map is a real multi-source map, not a
        single-key accident."""
        coord = _coord(_entry())
        client = _client()
        assert _setup(coord, client) is True
        armed = coord._armed_data_channels(VIN)
        assert len(armed) >= 3  # the fixture really does arm several channels
        assert set(coord.vehicles[VIN]["channel_status"]) == set(armed)


# ── it is the poll path's value, not a placeholder ──────────────────────────


class TestSetupValueMatchesPollPath:
    def test_keys_and_counts_match_a_direct_compute(self) -> None:
        entry_data = _entry()
        coord = _coord(entry_data)
        client = _client()
        assert _setup(coord, client) is True
        stored = coord.vehicles[VIN]
        reference = _reference_coord(entry_data, client)._compute_channel_status(
            VIN, stored
        )
        assert set(stored["channel_status"]) == set(reference)
        assert _without_timestamps(stored["channel_status"]) == _without_timestamps(
            reference
        )

    def test_not_a_degenerate_placeholder(self) -> None:
        """A placeholder (empty dict, or entries with nothing counted) would pass
        a bare key check. Pin the substance: the primary channel is active, owns
        the readings the setup fetch produced, and the totals come from the real
        ``field_sources`` map."""
        coord = _coord(_entry())
        client = _client()
        assert _setup(coord, client) is True
        stored = coord.vehicles[VIN]
        field_sources = stored["field_sources"]
        assert field_sources, "provenance is the input the map is computed from"
        status = stored["channel_status"]
        primary = status["skoda"]
        assert primary["armed"] is True
        assert primary["active"] is True
        assert primary["active_values"] == sum(
            1 for token in field_sources.values() if token == "skoda"
        )
        assert primary["total_values"] == len(field_sources)
        assert primary["last_active"] is not None
        # an armed-but-idle channel is reported as armed standby, counted at 0
        idle = status["eu_data_act"]
        assert idle["armed"] is True
        assert idle["active"] is False
        assert idle["active_values"] == 0
        assert idle["total_values"] == len(field_sources)


# ── fail-soft: a compute hiccup must not sink setup ─────────────────────────


class TestComputeFailureDoesNotSinkSetup:
    def test_setup_completes_and_stores_the_vehicle(self) -> None:
        coord = _coord(_entry())
        client = _client()
        calls: list[str] = []

        def _boom(vin: str, data: dict[str, Any]) -> dict[str, Any]:
            calls.append(vin)
            raise RuntimeError("channel-status compute exploded")

        coord._compute_channel_status = _boom  # type: ignore[method-assign]
        assert _setup(coord, client) is True
        assert calls == [VIN], "the setup path really did attempt the compute"
        stored = coord.vehicles[VIN]
        assert stored["battery_soc"] == 55
        assert stored["odometer_km"] == 1234
        assert coord.vehicle_success[VIN] is True
        # the key is simply absent — no half-written map left behind
        assert "channel_status" not in stored


# ── the optimistic hold must not drop the map ───────────────────────────────


class TestOptimisticHoldKeepsTheMap:
    def test_key_survives_apply_optimistic_hold(self) -> None:
        coord = _coord(_entry())
        client = _client()
        # a real pending hold, so _apply_optimistic_hold actually does work on
        # this dict rather than returning early on an empty hold root
        coord._optimistic_hold = {VIN: {"doors_locked": (True, time.monotonic() + 300)}}
        assert _setup(coord, client) is True
        stored = coord.vehicles[VIN]
        assert stored["doors_locked"] is True  # the hold was applied
        assert coord._optimistic_hold[VIN]["doors_locked"][0] is True  # still pending
        assert "channel_status" in stored, (
            "the hold reconcile must not drop the connectivity map"
        )
        assert stored["channel_status"], "and must not blank it either"
