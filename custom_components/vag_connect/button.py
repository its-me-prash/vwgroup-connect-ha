# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Button entities for VW Group Connect (flash lights, force refresh, wake)."""

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import VagConnectCoordinator
from .entity_base import VagConnectEntity, register_dynamic_spawner

# v1.13.0 (#56 Phase 3) — capability filtering moved to coordinator's
# ``command_capability_supported(vin, command_id)`` helper, which uses
# the per-brand mapping in ``cariad/_capabilities.py``. This replaces
# the brand-allowlist + cap-id-string approach below.
#
# Phase 2 (v1.9.1) brand-allowlist (now superseded but kept for reference):
#   Pre-1.13.0 only SEAT/CUPRA were gated because we had verified their
#   OLA capability vocabulary. v1.13.0 ships verified vocabularies for
#   VW EU + Audi + Skoda (via the new Skoda capabilities endpoint) so
#   the allowlist becomes the implicit "any brand with a registered
#   command-id mapping in CAPABILITY_MAP".


# b13 — platinum parallel-updates rule: the coordinator's background poll
# loop owns every API request, so entity updates need no throttling. HA reads
# this MODULE-level constant (an entity attr is a no-op).
PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up button entities. v1.25.0 PR-C: dynamic listener spawn."""
    coordinator: VagConnectCoordinator = entry.runtime_data
    # v1.12.0 (#63) — Read-only Mode: skip vehicle-command buttons
    # (Flash, Wake) but ALWAYS keep VagRefreshButton — refresh is a
    # coordinator-level cloud poll, doesn't send any vehicle command.
    read_only = coordinator.is_read_only()

    def _build_for_vin(vin: str, vehicle: dict) -> list:  # noqa: ARG001
        entities: list = []
        # Refresh button never gates — coordinator-level operation.
        if coordinator.is_companion():
            entities.append(VagCompanionRefreshButton(coordinator, vin))
        else:
            entities.append(VagRefreshButton(coordinator, vin))
        # v2.26.0 — companion (ADB) entries have no portal, so they must NOT
        # get the EU-Data-Act request button (it would call a portal that
        # isn't there). Instead they get a reset button to clear a stuck
        # failure/rate-limit backoff. Handle before the read_only branch,
        # because an unverified-brand companion is read_only too.
        if coordinator.is_companion():
            entities.append(VagCompanionResetButton(coordinator, vin))
            # #968 — "Synchronise now" wakes the car, so like the sync slider
            # it needs a preset that maps it and an entry outside Read-only Mode.
            if not read_only and _companion_can_sync(entry):
                entities.append(VagCompanionForceRefreshButton(coordinator, vin))
            return entities
        # v2.17.1 / #923 — EU-Data-Act portal buttons appear whenever this entry
        # reads the portal: as its PRIMARY (read-only) channel OR as a
        # SUPPLEMENTARY channel merged onto a command primary. They used to be
        # gated on read-only-portal mode only, so a merged
        # ``eu_data_act+website_authproxy`` setup (@naked-head, @dazzzl) never
        # got the one-time export button even though the export works identically
        # there — the kickoff scraper is authed on the shared session either way.
        if coordinator.has_data_act_portal_channel():
            # Create/refresh the continuous data request on demand, so a user
            # whose portal has no active request can fix "no data" from inside
            # Home Assistant instead of the portal UI.
            entities.append(VagDataActRequestButton(coordinator, vin))
            # Stage-1 — a one-time historical-export trigger, unless the whole
            # lifecycle is disabled by the kill-switch.
            from .const import ONETIME_EXPORT_DISABLED  # noqa: PLC0415
            if not ONETIME_EXPORT_DISABLED:
                entities.append(VagHistoricalExportButton(coordinator, vin))
        if read_only:
            # A read-only entry has no vehicle commands to add below.
            return entities
        # v3.0.0a1 — also require the client to implement the command, else the
        # button raises AttributeError on press (companion/ADB has neither).
        if (
            coordinator.command_capability_supported(vin, "command_flash") is not False
            and coordinator.command_method_available("command_flash")
        ):
            entities.append(VagFlashButton(coordinator, vin))
        if (
            coordinator.command_capability_supported(vin, "command_wake") is not False
            and coordinator.command_method_available("command_wake")
        ):
            entities.append(VagWakeButton(coordinator, vin))
        return entities

    register_dynamic_spawner(entry, coordinator, async_add_entities, _build_for_vin)


def _companion_can_sync(entry: ConfigEntry) -> bool:
    """True when this companion entry's brand preset maps "Synchronise now"."""
    from .companion.app_sync import preset_can_sync  # noqa: PLC0415
    from .const import CONF_BRAND  # noqa: PLC0415

    return preset_can_sync(str(entry.data.get(CONF_BRAND, "")))


class VagFlashButton(VagConnectEntity, ButtonEntity):
    """Trigger a honk-and-flash sequence."""

    _attr_translation_key = "flash_button"
    _attr_icon = "mdi:car-light-high"
    # v1.9.1 — Phase 2 gating: hide once a 403/missing-capability is seen.
    _command_id = "command_flash"

    def __init__(self, coordinator: VagConnectCoordinator, vin: str) -> None:
        super().__init__(coordinator, vin, "flash_button")

    async def async_press(self) -> None:
        await self.coordinator.async_flash_lights(self._vin)


class VagRefreshButton(VagConnectEntity, ButtonEntity):
    """Force an immediate data refresh from the cloud."""

    _attr_translation_key = "refresh_button"
    _attr_icon = "mdi:refresh"

    def __init__(self, coordinator: VagConnectCoordinator, vin: str) -> None:
        super().__init__(coordinator, vin, "refresh_button")

    async def async_press(self) -> None:
        # A requested refresh also reads the companion detail screens that
        # otherwise wait for a trip or new car data.
        self.coordinator.companion_walk_details_next()
        await self.coordinator.async_request_refresh()


class VagCompanionRefreshButton(VagRefreshButton):
    """The companion's Refresh: re-reads the app's screens, nothing reaches the car.

    Same unique id as the shared Refresh button, so entity ids are kept. It
    maintains the data rather than using the car, so it sits in the device's
    Configuration section, next to the reset button.
    """

    _attr_translation_key = "companion_refresh_button"
    _attr_entity_category = EntityCategory.CONFIG


class VagWakeButton(VagConnectEntity, ButtonEntity):
    """Wake the vehicle from sleep."""

    _attr_translation_key = "wake_button"
    _attr_icon = "mdi:car-connected"
    # v1.9.1 — Phase 2 gating.
    _command_id = "command_wake"

    def __init__(self, coordinator: VagConnectCoordinator, vin: str) -> None:
        super().__init__(coordinator, vin, "wake_button")

    async def async_press(self) -> None:
        await self.coordinator.async_wake_vehicle(self._vin)


class VagDataActRequestButton(VagConnectEntity, ButtonEntity):
    """Create/refresh the EU Data Act continuous data request on the portal."""

    _attr_translation_key = "data_act_request_button"
    _attr_icon = "mdi:cloud-sync"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: VagConnectCoordinator, vin: str) -> None:
        super().__init__(coordinator, vin, "data_act_request_button")

    async def async_press(self) -> None:
        await self.coordinator.async_create_data_act_request()


class VagHistoricalExportButton(VagConnectEntity, ButtonEntity):
    """Request a ONE-TIME EU Data Act historical export for this car.

    Refused (with a clear message) only while the user already has a one-time
    export of their own pending, because the portal enforces one PENDING custom
    request per VIN at a time. It runs ALONGSIDE the active 15-min continuous feed
    and does not suspend it (field-corrected under #923). The ``historical_export``
    sensor tracks the resulting pending/done/timed_out state.
    """

    _attr_translation_key = "historical_export_button"
    _attr_icon = "mdi:history"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: VagConnectCoordinator, vin: str) -> None:
        super().__init__(coordinator, vin, "historical_export_button")

    async def async_press(self) -> None:
        await self.coordinator.async_request_historical_export(self._vin)


class VagCompanionResetButton(VagConnectEntity, ButtonEntity):
    """v2.26.0 — clear a stuck companion (ADB) failure/rate-limit backoff.

    The companion channel backs off adaptively after failures and for hours
    after the app shows a rate-limit banner. If the cause is gone (phone
    rebooted, app reopened) this button clears the backoff and re-reads now.
    """

    _attr_translation_key = "companion_reset_button"
    _attr_icon = "mdi:restart-alert"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: VagConnectCoordinator, vin: str) -> None:
        super().__init__(coordinator, vin, "reset_button")

    async def async_press(self) -> None:
        await self.coordinator.async_reset_companion_cooldown()


class VagCompanionForceRefreshButton(VagConnectEntity, ButtonEntity):
    """#968 — tap the app's "Synchronise now", then re-read the app.

    The Refresh button only re-reads what the app already shows; this one first
    makes the car send fresh data (vehicle Settings → Synchronise now) and
    re-reads the app once the car has had time to answer.
    """

    _attr_translation_key = "companion_force_refresh_button"
    _attr_icon = "mdi:car-clock"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: VagConnectCoordinator, vin: str) -> None:
        super().__init__(coordinator, vin, "force_refresh_button")

    async def async_press(self) -> None:
        await self.coordinator.async_companion_force_refresh()
