# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Opt-in auto-provisioning of monthly ``utility_meter`` helpers.

TommiG1-style convenience: for each vehicle, wire Home Assistant's built-in
``utility_meter`` helper to the TOTAL_INCREASING sensors we already emit (charged
energy kWh, odometer km) so a user gets monthly counters without hand-building
them. Opt-in and **default OFF** — these are persistent config-entry helpers the
user must remove themselves, so we never create them silently. Fully guarded: a
Home-Assistant flow-init failure must never break integration setup. Version-
adaptive: the ``CONF_*`` keys are imported from HA's own ``utility_meter`` const,
and its config flow is a single "user" step, so one ``async_init`` completes it.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class _MeterSpec:
    """One auto-provisioned meter: our source sensor ``data_key`` + a name."""

    suffix: str
    name: str


# Keyed to our existing TOTAL_INCREASING sensors (sensor.py). Their unique_id is
# ``{vin}_{data_key}`` (entity_base.py), which we resolve to an entity_id below.
_SPECS: tuple[_MeterSpec, ...] = (
    _MeterSpec("total_charged_energy_kwh", "Monthly charged energy"),
    _MeterSpec("odometer_km", "Monthly mileage"),
)

_CYCLE = "monthly"


async def async_ensure_utility_meters(
    hass: HomeAssistant, entry: ConfigEntry, vins: list[str]
) -> None:
    """Create one monthly ``utility_meter`` per (vin, spec) that isn't present yet.

    The caller gates on the opt-in flag; this only acts on vehicles whose source
    sensor exists in the registry, and skips any source that already has a monthly
    meter (idempotent). Guarded so any HA-side failure is a no-op, never a setup
    break.
    """
    try:
        from homeassistant.components.utility_meter.const import (  # noqa: PLC0415
            CONF_METER_DELTA_VALUES,
            CONF_METER_NET_CONSUMPTION,
            CONF_METER_OFFSET,
            CONF_METER_PERIODICALLY_RESETTING,
            CONF_METER_TYPE,
            CONF_SOURCE_SENSOR,
            CONF_TARIFFS,
        )
        from homeassistant.const import CONF_NAME  # noqa: PLC0415

        registry = er.async_get(hass)
        # Existing (source_entity_id, cycle) pairs, so we never double-provision.
        existing: set[tuple[str, str]] = set()
        for ce in hass.config_entries.async_entries("utility_meter"):
            opts = {**ce.data, **ce.options}
            src = opts.get(CONF_SOURCE_SENSOR)
            if src:
                existing.add((src, opts.get(CONF_METER_TYPE, "")))

        for vin in vins:
            for spec in _SPECS:
                source_eid = registry.async_get_entity_id(
                    "sensor", DOMAIN, f"{vin}_{spec.suffix}"
                )
                if source_eid is None:
                    continue  # source sensor not present for this car
                if (source_eid, _CYCLE) in existing:
                    continue  # already provisioned
                await hass.config_entries.flow.async_init(
                    "utility_meter",
                    context={"source": "user"},
                    data={
                        CONF_NAME: f"{spec.name} …{vin[-6:]}",
                        CONF_SOURCE_SENSOR: source_eid,
                        CONF_METER_TYPE: _CYCLE,
                        CONF_METER_OFFSET: 0,
                        CONF_TARIFFS: [],
                        CONF_METER_NET_CONSUMPTION: False,
                        CONF_METER_DELTA_VALUES: False,
                        CONF_METER_PERIODICALLY_RESETTING: True,
                    },
                )
                existing.add((source_eid, _CYCLE))
                _LOGGER.info(
                    "VW Group Connect: auto-provisioned a monthly utility_meter "
                    "for %s", source_eid,
                )
    except Exception as exc:  # noqa: BLE001 — provisioning must never break setup
        _LOGGER.debug(
            "utility_meter auto-provisioning skipped (%s)", type(exc).__name__
        )
