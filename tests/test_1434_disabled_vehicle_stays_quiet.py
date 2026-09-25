# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#1434 — a user-disabled vehicle must stay fully quiet, not just skipped by
the one-time setup prefetch.

``async_setup()``'s background prefetch already filtered its VIN list through
``_active_vins()``, but the actual periodic driver — ``_poll_loop()``, since
``update_interval`` is ``None`` here — built its VIN list straight from
``self.vehicles.keys()`` with no filtering at all, and so did two other call
sites: ``_async_update_data()`` (the manual-refresh path ``async_request_
refresh()`` triggers after every command against ANY vehicle on the account)
and ``_refresh_mbb_command_capabilities()`` (called from both loops to keep
the MBB operationList warm). A vehicle the user disabled in HA — because they
sold it — kept being polled by all three, every cycle / every command, weeks
after being disabled.

This file covers the two call sites that are practical to drive directly in
isolation (``_async_update_data`` and ``_refresh_mbb_command_capabilities``);
``_poll_loop`` itself applies the identical, already-unit-tested
``_active_vins()`` one-liner (see ``test_active_vins_poll_optout.py``) and
isn't separately re-tested here to avoid mocking its much larger surface.
"""
from __future__ import annotations

import asyncio
import threading
from unittest.mock import AsyncMock, MagicMock, patch

from custom_components.vag_connect.coordinator import VagConnectCoordinator

_MOD = "custom_components.vag_connect.coordinator"

VIN_ACTIVE = "WVWZZZ3CZ9W025570"
VIN_DISABLED = "WVGZZZE27PP016396"  # e.g. a sold car, device disabled by the user


def _coord() -> VagConnectCoordinator:
    c = VagConnectCoordinator.__new__(VagConnectCoordinator)
    c._started = True
    c.hass = MagicMock()
    c.entry = MagicMock()
    c._vehicles_lock = threading.Lock()
    c.vehicles = {
        VIN_ACTIVE: {"cached": True},
        VIN_DISABLED: {"cached": True},
    }
    return c


def _registry_with_disabled(vin: str):
    """A device registry where only *vin* is disabled_by=USER."""
    from homeassistant.helpers import device_registry as dr

    reg = MagicMock()

    def _get(identifier, _entry_id):
        _domain, this_vin = identifier
        dev = MagicMock()
        dev.disabled_by = dr.DeviceEntryDisabler.USER if this_vin == vin else None
        return dev

    reg.async_get_device_by_identifier.side_effect = _get
    return reg


class TestAsyncUpdateDataSkipsDisabledVehicle:
    """_async_update_data() is the manual-refresh path fired by
    async_request_refresh() after every command — e.g. locking the ACTIVE
    car used to silently re-poll the DISABLED one too."""

    def test_disabled_vin_excluded_from_manual_refresh(self) -> None:
        client = AsyncMock()
        client.get_status = AsyncMock(return_value=object())  # non-VehicleData → skipped downstream, mirrors #584's test trick
        coord = _coord()
        coord._cariad_client = client
        coord._refresh_mbb_command_capabilities = AsyncMock()
        coord._persist_website_cookies = lambda: None

        with patch(f"{_MOD}.dr.async_get", return_value=_registry_with_disabled(VIN_DISABLED)):
            result = asyncio.run(coord._async_update_data())

        polled = {call.args[0] for call in client.get_status.await_args_list}
        assert polled == {VIN_ACTIVE}
        # the disabled vehicle's cached entry must survive untouched, not
        # disappear just because it was excluded from this refresh
        assert result[VIN_DISABLED] == {"cached": True}

    def test_all_vehicles_polled_when_none_disabled(self) -> None:
        """Sanity check — the filter must not accidentally drop active VINs."""
        client = AsyncMock()
        client.get_status = AsyncMock(return_value=object())
        coord = _coord()
        coord._cariad_client = client
        coord._refresh_mbb_command_capabilities = AsyncMock()
        coord._persist_website_cookies = lambda: None

        with patch(f"{_MOD}.dr.async_get", return_value=_registry_with_disabled("")):
            asyncio.run(coord._async_update_data())

        polled = {call.args[0] for call in client.get_status.await_args_list}
        assert polled == {VIN_ACTIVE, VIN_DISABLED}


class TestMbbCommandCapabilitiesSkipsDisabledVehicle:
    """Called every cycle from both _poll_loop() and _async_update_data() to
    warm the per-VIN MBB operationList — was unfiltered even though it's
    supposed to leave a disabled vehicle alone."""

    def test_disabled_vin_excluded_from_operationlist_warm(self) -> None:
        coord = _coord()
        getter = AsyncMock()
        cmd = MagicMock()
        cmd._get_mbb_operationlist = getter
        cmd._mbb_manual_vins = None  # → falls back to self.vehicles.keys()
        cmd.mbb_no_legacy_vins = ()

        with patch(f"{_MOD}._mbb_command_channel_client", return_value=cmd), \
             patch(f"{_MOD}.dr.async_get", return_value=_registry_with_disabled(VIN_DISABLED)):
            asyncio.run(coord._refresh_mbb_command_capabilities())

        polled = {call.args[0] for call in getter.await_args_list}
        assert polled == {VIN_ACTIVE}

    def test_explicit_manual_vins_bypasses_the_filter(self) -> None:
        """_mbb_manual_vins is an explicit opt-in list (a user manually pinned
        a VIN for MBB) and must be honoured even if that VIN's device is
        disabled — same contract the docstring already states."""
        coord = _coord()
        getter = AsyncMock()
        cmd = MagicMock()
        cmd._get_mbb_operationlist = getter
        cmd._mbb_manual_vins = [VIN_DISABLED]
        cmd.mbb_no_legacy_vins = ()

        with patch(f"{_MOD}._mbb_command_channel_client", return_value=cmd), \
             patch(f"{_MOD}.dr.async_get", return_value=_registry_with_disabled(VIN_DISABLED)):
            asyncio.run(coord._refresh_mbb_command_capabilities())

        polled = {call.args[0] for call in getter.await_args_list}
        assert polled == {VIN_DISABLED}
