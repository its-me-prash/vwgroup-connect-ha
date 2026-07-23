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
    # v2.18.0 (#702) — Touareg-era legacy Car-Net spells the same timer mode
    # TIMER_BASED_CHARGING. Read-side alias only; the write tokens below are
    # untouched, so nothing changes for cars that can actually set the mode.
    "timerbasedcharging": "timer",
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

# Canonical key → API command token (snake_case). ``command_set_charge_mode``
# (VW-EU / Audi only) converts these to lowerCamelCase and PUTs
# ``{"preferredChargeMode": <value>}`` to ``charging/mode`` — the exact enum the
# decoded Audi app writes (ChargeModes$Mode wire values: manual, timer,
# preferredChargingTimes, onlyOwnCurrent, immediateDischarging,
# timerChargingWithClimatisation). NOTE: SEAT/CUPRA do NOT inherit this command
# (SeatCupraClient extends CariadBaseClient, not VWEUClient); the read-side
# localisation below is what they share via _RAW_TO_CANONICAL. (Pre-v2.19.1 this
# wrongly UPPER-cased the token onto charging/settings — don't reintroduce that.)
_CANONICAL_TO_API: dict[str, str] = {
    "manual": "manual",
    "timer": "timer",
    "preferred_charging_times": "preferred_charging_times",
    "only_own_current": "only_own_current",
    "immediate_discharging": "immediate_discharging",
    "timer_charging_climatization": "timer_charging_with_climatisation",
}


# ── v2.15.10 — Skoda max-charging-current select ─────────────────────────
#
# Skoda's charging plan exposes AC max current as a two-value enum
# (``MAXIMUM`` | ``REDUCED``) rather than an integer amperage. This is
# grounded in the read side (``get_charging_profiles`` →
# ``settings.maxChargingCurrent``) and the write side (POST
# /api/v1/charging/{vin}/set-charging-current). We surface it as canonical
# snake_case option keys so HA localises them via the entity ``state`` map.
_SKODA_CURRENT_OPTIONS: list[str] = ["maximum", "reduced"]

# Raw API enum (``MAXIMUM``/``REDUCED``) → canonical key. Normalised by
# casefold before lookup so we tolerate either casing.
_SKODA_CURRENT_RAW_TO_CANONICAL: dict[str, str] = {
    "maximum": "maximum",
    "reduced": "reduced",
}

# Canonical key → API enum token sent on write.
_SKODA_CURRENT_CANONICAL_TO_API: dict[str, str] = {
    "maximum": "MAXIMUM",
    "reduced": "REDUCED",
}


def _normalise_skoda_current(raw: object) -> str | None:
    """Map a raw Skoda ``maxChargingCurrent`` value to a canonical key."""
    if raw is None:
        return None
    key = str(raw).strip().casefold()
    if not key:
        return None
    return _SKODA_CURRENT_RAW_TO_CANONICAL.get(key)


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
    # v2.23.3 (#63) — Read-only Mode: the charge-mode select sends a command,
    # so skip it in read-only mode, matching number/switch/button/climate/lock.
    if coordinator.is_read_only():
        return

    from .const import CONF_BRAND  # noqa: PLC0415

    is_skoda = str(entry.data.get(CONF_BRAND, "")).lower() == "skoda"

    def _build_for_vin(vin: str, vehicle: dict) -> list:
        entities: list = []
        if vehicle.get("has_battery"):
            entities.append(VagChargeModeSelect(coordinator, vin))
            # v2.15.10 — Skoda-only max-charging-current select (enum plane).
            if is_skoda:
                entities.append(VagSkodaChargeCurrentSelect(coordinator, vin))
        return entities

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


class VagSkodaChargeCurrentSelect(VagConnectEntity, SelectEntity):
    """Skoda AC max-charging-current select (``maximum`` / ``reduced``).

    v2.15.10 — Skoda exposes AC current as a two-value enum instead of an
    integer amperage. Read from ``max_charging_current`` (populated by the
    charging-profiles parser); written via
    ``async_update_charging_settings`` which dispatches the brand-polymorphic
    ``command_update_charging_settings`` to the Skoda client
    (POST /api/v1/charging/{vin}/set-charging-current).
    """

    _attr_translation_key = "skoda_charge_current_select"
    _attr_icon = "mdi:current-ac"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_options = list(_SKODA_CURRENT_OPTIONS)

    def __init__(self, coordinator: VagConnectCoordinator, vin: str) -> None:
        super().__init__(coordinator, vin, "skoda_charge_current_select")

    @property
    def current_option(self) -> str | None:
        """Return the current max-charging-current as a canonical key."""
        return _normalise_skoda_current(self._vehicle.get("max_charging_current"))

    async def async_select_option(self, option: str) -> None:
        """Set AC max charging current — maps canonical key to API enum."""
        api_token = _SKODA_CURRENT_CANONICAL_TO_API.get(option)
        if api_token is None:
            return
        await self.coordinator.async_update_charging_settings(
            self._vin, max_charge_current=api_token
        )
