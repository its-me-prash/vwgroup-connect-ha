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

# CARIAD charge modes.
#
# #589 — HA localises SelectEntity options ONLY when ``options`` are stable
# canonical keys that it can look up via
# ``component.vag_connect.entity.select.charge_mode_select.state.<key>``.
# Previously ``options`` held hardcoded German labels ("Manuell", …), so a
# UK user saw German verbatim. We now expose snake_case canonical keys
# (aligned with ``eu_data_dictionary.json`` →
# ``charge_mode_selection_options.*``) and ship the per-key ``state``
# translations in strings.json + all 8 locales.
#
# Canonical option keys (order = display order):
_CHARGE_MODE_OPTIONS: list[str] = [
    "manual",
    "timer",
    "preferred_charging_times",
    "only_own_current",
    "immediate_discharging",
    "timer_charging_climatization",
]

# Raw API value (per data-plane) → canonical key. The raw side is
# normalised (casefold + strip non-alphanumerics) before lookup, so both
# the VW-EU BFF uppercase enum ("PREFERRED_CHARGING_TIMES") and the
# CUPRA/SEAT OLA lowercase camelCase ("preferredChargingTimes") resolve to
# the same key. Keys here are the pre-normalised alias forms.
_RAW_TO_CANONICAL: dict[str, str] = {
    # manual
    "manual": "manual",
    # timer
    "timer": "timer",
    # preferred charging times
    "preferredchargingtimes": "preferred_charging_times",
    # only own current / eigenstrom (CUPRA OLA: automaticUnlocked)
    "onlyowncurrent": "only_own_current",
    "automaticunlocked": "only_own_current",
    # immediate discharging
    "immediatedischarging": "immediate_discharging",
    # timer charging with climatisation (VW-EU BFF)
    "timerchargingwithclimatisation": "timer_charging_climatization",
    "timerchargingclimatization": "timer_charging_climatization",
}

# Canonical key → API command token. ``command_set_charge_mode`` upper-cases
# the token before sending, so these are the pre-upper snake forms the
# backend expects on write (VW-EU BFF chargeMode enum; SEAT/CUPRA inherit
# the same command). Keeping the exact tokens the API accepted before #589
# preserves SEAT/CUPRA charge-mode commands.
_CANONICAL_TO_API: dict[str, str] = {
    "manual": "manual",
    "timer": "timer",
    "preferred_charging_times": "preferred_charging_times",
    "only_own_current": "only_own_current",
    "immediate_discharging": "immediate_discharging",
    "timer_charging_climatization": "timer_charging_with_climatisation",
}


def _normalise_raw_mode(raw: object) -> str | None:
    """Map any raw API charge-mode value to a canonical option key.

    Accepts both data-plane dialects (VW-EU uppercase enum + CUPRA/SEAT
    camelCase) by casefolding and stripping non-alphanumeric separators
    before the alias lookup. Returns ``None`` for unknown / empty values.
    """
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    key = "".join(ch for ch in text.casefold() if ch.isalnum())
    return _RAW_TO_CANONICAL.get(key)


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
    """Select entity for charging mode (manual / timer / preferred_charging_times…).

    #589 — ``options`` are canonical snake_case keys that HA localises via
    the entity's ``state`` translation map; the German option strings are
    no longer baked into the entity.
    """

    _attr_translation_key = "charge_mode_select"
    _attr_icon = "mdi:ev-plug-type2"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_options = list(_CHARGE_MODE_OPTIONS)  # canonical keys → HA localises

    def __init__(self, coordinator: VagConnectCoordinator, vin: str) -> None:
        super().__init__(coordinator, vin, "charge_mode_select")

    @property
    def current_option(self) -> str | None:
        """Return the current charge mode as a canonical option key.

        Normalises the raw API value (either data-plane dialect) so HA can
        localise it; unknown / unmapped raw values return ``None`` rather
        than leaking a raw string into the UI.
        """
        return _normalise_raw_mode(self._vehicle.get("charge_mode"))

    async def async_select_option(self, option: str) -> None:
        """Set the charging mode — maps canonical key back to the API token."""
        api_token = _CANONICAL_TO_API.get(option, option)
        await self.coordinator.async_set_charge_mode(self._vin, api_token)
