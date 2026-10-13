"""A car in a read-only entry and a companion entry: commands go to the companion.

The coordinator lookup used to return the first entry that owns the VIN. With
an EU Data Act (read-only) entry set up before the companion entry, every
VIN-addressed command (start/stop charging, climate, set_departure_timer, …)
failed with "read-only EU Data Act portal" although the companion could send it.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.exceptions import ServiceValidationError

VIN = "WVGZZZTEST0000001"


def _coord(read_only: bool) -> MagicMock:
    c = MagicMock()
    c.vehicles = {VIN: {}}
    c.is_read_only = MagicMock(return_value=read_only)
    c.is_structural_read_only = MagicMock(return_value=read_only)
    c.entry.data = {}
    c.async_start_charging = AsyncMock()
    return c


def _hass(*coords: MagicMock):
    entries = []
    for c in coords:
        e = MagicMock()
        e.runtime_data = c
        entries.append(e)
    hass = MagicMock()
    hass.config_entries.async_entries = MagicMock(return_value=entries)
    hass.services.has_service = MagicMock(return_value=False)
    registered = {}

    def _register(domain, name, handler, schema=None, supports_response=None):
        registered[(domain, name)] = handler

    hass.services.async_register = MagicMock(side_effect=_register)
    return hass, registered


def _start_charging(registered) -> None:
    call = MagicMock()
    call.data = {"vin": VIN}
    asyncio.run(registered[("vag_connect", "start_charging")](call))


def test_command_skips_the_read_only_entry() -> None:
    from custom_components.vag_connect import _register_services

    portal, companion = _coord(True), _coord(False)
    hass, registered = _hass(portal, companion)
    _register_services(hass)
    _start_charging(registered)
    companion.async_start_charging.assert_awaited_once_with(VIN)
    portal.async_start_charging.assert_not_awaited()


def test_first_writable_entry_wins_order_independent() -> None:
    from custom_components.vag_connect import _register_services

    companion, portal = _coord(False), _coord(True)
    hass, registered = _hass(companion, portal)
    _register_services(hass)
    _start_charging(registered)
    companion.async_start_charging.assert_awaited_once_with(VIN)


def test_only_read_only_entries_still_refuse() -> None:
    from custom_components.vag_connect import _register_services

    portal = _coord(True)
    hass, registered = _hass(portal)
    _register_services(hass)
    with pytest.raises(ServiceValidationError):
        _start_charging(registered)
    portal.async_start_charging.assert_not_awaited()
