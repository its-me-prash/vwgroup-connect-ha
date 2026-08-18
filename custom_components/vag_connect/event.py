# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Event platform for VW Group Connect — first-class push events per vehicle.

The coordinator already fires manufacturer push notifications onto the HA bus as
``vag_connect_push_event`` (``coordinator._on_push_event``). This platform gives
each vehicle a first-class ``event`` entity so those pushes land in the Logbook,
can trigger automations without a YAML bus filter, and carry per-car history.

Each entity subscribes to the bus event, filters to its own VIN, and re-emits via
``_trigger_event``. Push ``event_type`` values are backend-defined strings; the
Audi/VW kebab ``type`` and CUPRA/SEAT OLA ``type`` cannot be enumerated
off-device, so any value not in the declared list is fired under the ``other``
catch-all with the real value preserved in ``event_type_raw`` — never dropping an
event and never raising ``ValueError`` inside ``_trigger_event``.
"""
from __future__ import annotations

from typing import Any

from homeassistant.components.event import EventEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .cariad._util import json_safe_dict
from .const import CONF_BRAND, EVENT_PUSH
from .coordinator import VagConnectCoordinator
from .entity_base import VagConnectEntity, register_dynamic_spawner

# Catch-all so an open-ended backend ``event_type`` can never raise inside
# EventEntity._trigger_event (which rejects any type not in event_types).
EVENT_TYPE_OTHER = "other"

# HA translation state keys must match [a-z0-9-_], so the Audi/VW FCM
# camelCase fallback keys are normalised to snake_case for the entity's declared
# types; the original value is still preserved verbatim in ``event_type_raw``.
_NORMALIZE: dict[str, str] = {
    "lockState": "lock_state",
    "chargingState": "charging_state",
    "climateState": "climate_state",
}

# Grounded event_type values per brand. ``other`` is appended as the safety net.
_BRAND_EVENT_TYPES: dict[str, list[str]] = {
    # Skoda MQTT topic category (myskoda BaseEvent categories).
    "skoda": ["operation-request", "service-event", "account-event", "vehicle-event"],
    # Audi/VW FCM legacy fallback keys (normalised to snake_case via _NORMALIZE);
    # the primary kebab ``type`` is backend-defined → handled via OTHER.
    "audi": ["lock_state", "charging_state", "climate_state", "alarm"],
    "volkswagen": ["lock_state", "charging_state", "climate_state", "alarm"],
    # CUPRA/SEAT OLA ``type`` is backend-defined and not enumerable from the
    # codebase → declared empty; everything arrives via OTHER + event_type_raw.
    "cupra": [],
    "seat": [],
}

# Only brands with a real push manager get an event entity; the others
# (volkswagen_na, porsche, vag) have no push source, so it would never fire.
PUSH_CAPABLE_BRANDS = frozenset(_BRAND_EVENT_TYPES)


async def async_setup_entry(
    hass: HomeAssistant,  # noqa: ARG001
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up one push-event entity per vehicle (push-capable brands only)."""
    coordinator: VagConnectCoordinator = entry.runtime_data
    brand = str(entry.data.get(CONF_BRAND, "")).strip().lower()
    if brand not in PUSH_CAPABLE_BRANDS:
        return

    event_types = [*_BRAND_EVENT_TYPES[brand], EVENT_TYPE_OTHER]

    def _build_for_vin(vin: str, _vehicle: dict) -> list[Any]:
        # Not gated on any data field — the event stream exists for every
        # vehicle of a push-capable brand, independent of poll contents.
        return [VagConnectPushEventEntity(coordinator, vin, event_types)]

    register_dynamic_spawner(entry, coordinator, async_add_entities, _build_for_vin)


class VagConnectPushEventEntity(VagConnectEntity, EventEntity):
    """First-class push-event entity for a single vehicle."""

    _attr_translation_key = "push_event"
    _attr_icon = "mdi:car-connected"

    def __init__(
        self,
        coordinator: VagConnectCoordinator,
        vin: str,
        event_types: list[str],
    ) -> None:
        super().__init__(coordinator, vin, "push_event")
        self._attr_event_types = event_types

    @property
    def available(self) -> bool:
        """Always available — a push can arrive while the last poll failed, which
        is exactly when it matters; gating on poll success would drop it."""
        return True

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(
            self.hass.bus.async_listen(
                EVENT_PUSH, self._handle_push_event, event_filter=self._match_vin,
            )
        )

    @callback
    def _match_vin(self, event: Event[Any]) -> bool:
        """Bus event_filter — only wake this entity for its own VIN."""
        return bool(event.data.get("vin") == self._vin)

    @callback
    def _handle_push_event(self, event: Event[Any]) -> None:
        """Re-emit a matching bus event as this entity's native event."""
        data = event.data
        raw_type = data.get("event_type") or EVENT_TYPE_OTHER
        attributes: dict[str, Any] = {
            "topic": data.get("topic"),
            "timestamp": data.get("timestamp"),
            "brand": data.get("brand"),
            "event_type_raw": raw_type,
        }
        payload = data.get("raw_payload")
        if isinstance(payload, dict):
            attributes["payload"] = json_safe_dict(payload)

        norm = _NORMALIZE.get(raw_type, raw_type)
        event_type = norm if norm in self.event_types else EVENT_TYPE_OTHER
        self._trigger_event(event_type, attributes)
        self.async_write_ha_state()
