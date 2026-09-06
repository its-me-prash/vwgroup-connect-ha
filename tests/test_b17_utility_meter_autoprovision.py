# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Opt-in auto-provisioning of monthly utility_meter helpers (TommiG1-style).

Wires HA's built-in ``utility_meter`` helper to the TOTAL_INCREASING sensors we
already emit (charged energy kWh, odometer km). Verifies the offline-testable
core: it provisions one monthly meter per present source sensor, de-dups against
existing meters, skips a car whose source sensor isn't registered yet, and
swallows any HA-side failure. The live flow-init + provisioning timing is verified
on a real HA install.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.vag_connect.utility_meter import async_ensure_utility_meters

VIN = "WVWZZZTESTVIN0001"
_UIDS = {
    f"{VIN}_total_charged_energy_kwh": "sensor.a_charged",
    f"{VIN}_odometer_km": "sensor.a_odo",
}


def _hass(existing_entries: list) -> MagicMock:
    hass = MagicMock()
    hass.config_entries.async_entries.return_value = existing_entries
    hass.config_entries.flow.async_init = AsyncMock()
    return hass


def _registry(resolver) -> MagicMock:
    reg = MagicMock()
    reg.async_get_entity_id.side_effect = resolver
    return reg


@pytest.mark.asyncio
async def test_provisions_a_monthly_meter_per_source() -> None:
    hass = _hass([])
    reg = _registry(lambda d, i, uid: _UIDS.get(uid))
    with patch(
        "homeassistant.helpers.entity_registry.async_get", return_value=reg
    ):
        await async_ensure_utility_meters(hass, MagicMock(), [VIN])
    calls = hass.config_entries.flow.async_init.call_args_list
    assert len(calls) == 2  # one per spec
    for c in calls:
        assert c.args[0] == "utility_meter"
        assert c.kwargs["context"] == {"source": "user"}
        data = c.kwargs["data"]
        assert data["cycle"] == "monthly"                 # CONF_METER_TYPE
        assert data["source"].startswith("sensor.a_")     # CONF_SOURCE_SENSOR
        assert data["periodically_resetting"] is True
        assert data["tariffs"] == []


@pytest.mark.asyncio
async def test_skips_a_source_that_already_has_a_monthly_meter() -> None:
    existing = MagicMock()
    existing.data = {"source": "sensor.a_charged", "cycle": "monthly"}
    existing.options = {}
    hass = _hass([existing])
    reg = _registry(lambda d, i, uid: _UIDS.get(uid))
    with patch(
        "homeassistant.helpers.entity_registry.async_get", return_value=reg
    ):
        await async_ensure_utility_meters(hass, MagicMock(), [VIN])
    calls = hass.config_entries.flow.async_init.call_args_list
    assert len(calls) == 1                                  # only the odometer one
    assert calls[0].kwargs["data"]["source"] == "sensor.a_odo"


@pytest.mark.asyncio
async def test_skips_car_whose_source_sensor_is_not_registered() -> None:
    hass = _hass([])
    reg = _registry(lambda d, i, uid: None)                 # nothing registered yet
    with patch(
        "homeassistant.helpers.entity_registry.async_get", return_value=reg
    ):
        await async_ensure_utility_meters(hass, MagicMock(), [VIN])
    hass.config_entries.flow.async_init.assert_not_called()


@pytest.mark.asyncio
async def test_flow_init_failure_never_breaks_setup() -> None:
    hass = _hass([])
    hass.config_entries.flow.async_init = AsyncMock(side_effect=RuntimeError("boom"))
    reg = _registry(lambda d, i, uid: _UIDS.get(uid))
    with patch(
        "homeassistant.helpers.entity_registry.async_get", return_value=reg
    ):
        await async_ensure_utility_meters(hass, MagicMock(), [VIN])  # must not raise
