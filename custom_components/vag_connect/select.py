# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Select entities for VAG Connect — Lademodus."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import VagConnectCoordinator
from .entity_base import VagConnectEntity, register_dynamic_spawner

# CARIAD charge modes — values as returned by API
_CHARGE_MODES: dict[str, str] = {
    "MANUAL":                    "Manuell",
    "TIMER":                     "Timer",
    "PREFERRED_CHARGING_TIMES":  "Bevorzugte Ladezeiten",
    "ONLY_OWN_CURRENT":          "Nur Eigenstrom",
    "IMMEDIATE_DISCHARGING":     "Sofort entladen",
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up charge-mode selects. v1.25.0 PR-C: dynamic listener spawn."""
    coordinator: VagConnectCoordinator = entry.runtime_data

    def _build_for_vin(vin: str, vehicle: dict) -> list:
        if vehicle.get("has_battery"):
            return [VagChargeModeSelect(coordinator, vin)]
        return []

    register_dynamic_spawner(entry, coordinator, async_add_entities, _build_for_vin)


class VagChargeModeSelect(VagConnectEntity, SelectEntity):
    """Select entity for charging mode (MANUAL / TIMER / PREFERRED_CHARGING_TIMES)."""

    _attr_translation_key = "charge_mode_select"
    _attr_icon = "mdi:ev-plug-type2"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_options = list(_CHARGE_MODES.values())  # HA shows translated labels

    def __init__(self, coordinator: VagConnectCoordinator, vin: str) -> None:
        super().__init__(coordinator, vin, "charge_mode_select")

    @property
    def current_option(self) -> str | None:
        """Return the current charge mode as a human-readable label."""
        raw = self._vehicle.get("charge_mode")
        if raw is None:
            return None
        result = _CHARGE_MODES.get(str(raw).upper(), str(raw))
        return str(result) if result else None

    async def async_select_option(self, option: str) -> None:
        """Set the charging mode — translates label back to API key."""
        # Reverse lookup: label → API key
        reverse = {v: k for k, v in _CHARGE_MODES.items()}
        api_key = reverse.get(option, option.upper())
        await self.coordinator.async_set_charge_mode(self._vin, api_key)
