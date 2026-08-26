# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""A vehicle the user disabled in HA stops being polled.

Marco Schmidt (HA Tipps und Tricks Facebook group) disabled his second car but
it kept updating — disabling a device removes its entities without stopping the
coordinator from polling the VIN. _active_vins drops VINs whose device is
disabled; a car with no device yet is always polled; the poll resumes on
re-enable.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

pytestmark = pytest.mark.ha_required

_MOD = "custom_components.vag_connect.coordinator"


def _coord():
    from custom_components.vag_connect.coordinator import VagConnectCoordinator

    c = VagConnectCoordinator.__new__(VagConnectCoordinator)
    c.hass = MagicMock()
    return c


def _registry(disabled: set[str], missing: set[str] = frozenset()):
    from homeassistant.helpers import device_registry as dr

    reg = MagicMock()

    def _get(identifiers):
        (_domain, vin), = identifiers
        if vin in missing:
            return None
        dev = MagicMock()
        # only a real DeviceEntryDisabler counts as disabled (a bare MagicMock
        # never should — that is exactly the robustness the coordinator relies on)
        dev.disabled_by = dr.DeviceEntryDisabler.USER if vin in disabled else None
        return dev

    reg.async_get_device.side_effect = _get
    return reg


def test_disabled_vehicle_is_skipped():
    c = _coord()
    with patch(f"{_MOD}.dr.async_get", return_value=_registry({"VIN_B"})):
        assert c._active_vins(["VIN_A", "VIN_B"]) == ["VIN_A"]


def test_vehicle_without_device_is_still_polled():
    c = _coord()
    with patch(f"{_MOD}.dr.async_get", return_value=_registry(set(), {"VIN_NEW"})):
        assert c._active_vins(["VIN_A", "VIN_NEW"]) == ["VIN_A", "VIN_NEW"]


def test_all_enabled_unchanged():
    c = _coord()
    with patch(f"{_MOD}.dr.async_get", return_value=_registry(set())):
        assert c._active_vins(["VIN_A", "VIN_B"]) == ["VIN_A", "VIN_B"]


def test_all_disabled_returns_empty():
    c = _coord()
    with patch(f"{_MOD}.dr.async_get", return_value=_registry({"VIN_A", "VIN_B"})):
        assert c._active_vins(["VIN_A", "VIN_B"]) == []


def test_registry_error_falls_back_to_polling_all():
    c = _coord()
    with patch(f"{_MOD}.dr.async_get", side_effect=RuntimeError("no registry")):
        assert c._active_vins(["VIN_A", "VIN_B"]) == ["VIN_A", "VIN_B"]


def test_system_disabled_device_is_still_polled():
    # #1234 — a device HA disabled for its OWN reasons (not the user) must NOT
    # fall out of rotation, or one car on a multi-car account goes silently quiet
    # and a restart won't bring it back. Only a USER-disabled device is skipped.
    from homeassistant.helpers import device_registry as dr

    reg = MagicMock()

    def _get(identifiers):
        (_domain, vin), = identifiers
        dev = MagicMock()
        dev.disabled_by = {
            "VIN_USER": dr.DeviceEntryDisabler.USER,
            "VIN_INT": dr.DeviceEntryDisabler.INTEGRATION,
            "VIN_CE": dr.DeviceEntryDisabler.CONFIG_ENTRY,
        }.get(vin)
        return dev

    reg.async_get_device.side_effect = _get
    c = _coord()
    with patch(f"{_MOD}.dr.async_get", return_value=reg):
        # only the user-disabled one drops; integration/config-entry keep polling
        assert c._active_vins(["VIN_A", "VIN_USER", "VIN_INT", "VIN_CE"]) == [
            "VIN_A", "VIN_INT", "VIN_CE",
        ]
