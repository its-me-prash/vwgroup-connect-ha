# Copyright 2026 Prash Balan (@its-me-prash) — Apache License 2.0
# SPDX-License-Identifier: Apache-2.0
"""Base entity class for all VAG Connect entities."""

from __future__ import annotations
from typing import Any

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .cariad.api.graphql import VehicleImageFetcher
from .const import DOMAIN
from .coordinator import VagConnectCoordinator


def _device_name(vehicle: dict, brand: str) -> str:
    """Return "{Brand} {Model}" or "{Brand} {VIN[-6:]}" as device name."""
    model = (vehicle.get("model") or "").strip()
    if model and model.lower() not in ("vag vehicle", "unknown", ""):
        return f"{brand.title()} {model}"
    vin = vehicle.get("vin", "")
    return f"{brand.title()} {vin[-6:]}" if vin else brand.title()


class VagConnectEntity(CoordinatorEntity[VagConnectCoordinator]):
    """Base entity shared by all VAG Connect platforms.

    parallel_updates=0: the coordinator's background poll loop owns all API
    calls.  HA entities never initiate requests directly.

    available: per-VIN — entity is unavailable when its vehicle's last poll
    failed, even if other vehicles in the same account succeeded.

    v1.9.1 (Capability-Filter Phase 2, #56) — command-bound entities can
    set ``_command_id`` on subclass init. When set, the ``available``
    property additionally consults
    ``coordinator.is_command_known_unsupported(vin, command)`` and returns
    ``False`` once the backend has explicitly rejected the command (missing
    capability, subscription expired, not entitled). Entities without a
    command (sensors, binary sensors) leave ``_command_id`` as ``None``
    and behave exactly as before.
    """

    _attr_has_entity_name = True
    _attr_parallel_updates = 0  # coordinator owns all API requests
    # v1.9.1 — set on subclasses that map 1:1 to a coordinator command.
    # ``None`` means "not a command-bound entity, never use Phase-2 gating".
    _command_id: str | None = None

    def __init__(
        self,
        coordinator: VagConnectCoordinator,
        vin: str,
        key: str,
    ) -> None:
        """Initialise entity."""
        super().__init__(coordinator)
        self._vin = vin
        self._key = key

        self._attr_unique_id = f"{vin}_{key}"

    @property
    def _vehicle(self) -> dict[str, Any]:
        """Current vehicle data dict."""
        data: dict[str, Any] = self.coordinator.data or {}
        result: dict[str, Any] = data.get(self._vin, {})
        return result

    @property
    def available(self) -> bool:
        """Per-VIN availability — falls back to coordinator default if unknown.

        Reflects the success of the last per-vehicle poll, so that a single
        failing vehicle does not affect entities for other vehicles in the
        same account.

        v1.9.1 (Capability-Filter Phase 2): for command-bound entities,
        also returns False if the coordinator's ``FeatureState`` records a
        definitive "command not supported" outcome from a previous attempt.
        """
        if not super().available:
            return False
        if not self.coordinator.is_vehicle_available(self._vin):
            return False
        if self._command_id is not None:
            try:
                if self.coordinator.is_command_known_unsupported(
                    self._vin, self._command_id
                ):
                    return False
            except Exception:  # noqa: BLE001
                # Bookkeeping must never affect availability negatively
                pass
        return True

    # v1.25.0 PR-F: brand-aware "Open in App" deep-links for the
    # ``configuration_url`` button on the device page.
    _BRAND_PORTAL: dict[str, str] = {
        "audi":          "https://my.audi.com/",
        "volkswagen":    "https://www.volkswagen.de/de/myvolkswagen.html",
        "skoda":         "https://www.skoda-auto.com/myskoda",
        "seat":          "https://www.seat.com/owners/myseat.html",
        "cupra":         "https://www.cupraofficial.com/services/mycupra.html",
        "porsche":       "https://my.porsche.com/",
        "volkswagen_na": "https://www.vw.com/myvw/",
    }

    @property
    def device_info(self) -> DeviceInfo:
        """Return HA DeviceInfo keyed by VIN.

        v1.25.0 PR-F changes:
        - Added ``configuration_url`` (brand-aware) → "Open in App" button
        - Added ``suggested_area="Garage"`` → auto-Area on first setup
        - Removed broken ``info["entity_picture"]`` no-op (Audit Agent E)
        - Vehicle-render is exposed via ``entity_picture`` property below,
          which is the actual mechanism HA reads for entity-detail pictures
          AND the source for device-default-picture when this entity becomes
          the device's "primary" entity (Lovelace heuristic).
        """
        vehicle = self._vehicle
        brand = self.coordinator.entry.data.get("brand", "vag")
        name = _device_name(vehicle, brand)

        # v2.0.0 (Big-Bang): Re-introduce ``configuration_url`` (brand-aware
        # "Open in App" button on device page) + ``suggested_area="Garage"``
        # (auto-Area on first setup). These were reverted in v1.26.1 along
        # with manifest ``quality_scale: platinum`` after a user reported
        # "Nicht geladen". v1.26.2 root-cause analysis confirmed the actual
        # culprit was ``hacs.json`` ``zip_release: true``, NOT these
        # DeviceInfo fields. Verified safe under HA 2026.x core via CI
        # Hassfest + HACS Validation since v1.27.0.
        return DeviceInfo(
            identifiers={(DOMAIN, self._vin)},
            name=name,
            model=vehicle.get("model") or "VAG Vehicle",
            manufacturer=brand.title(),
            serial_number=self._vin,
            hw_version=(
                str(vehicle.get("model_year"))
                if vehicle.get("model_year")
                else None
            ),
            sw_version=vehicle.get("firmware_version"),
            configuration_url=self._BRAND_PORTAL.get(brand.lower()),
            suggested_area="Garage",
        )

    @property
    def entity_picture(self) -> str | None:
        """Return vehicle render image URL as entity picture.

        Shows the car photo on the entity detail page and in dashboards
        that display entity pictures (e.g. mushroom cards, glance, etc.).
        Falls back to None so HA uses the entity's icon instead.
        """
        vehicle = self._vehicle
        image_urls: dict = vehicle.get("image_urls") or {}
        return VehicleImageFetcher.best_url(image_urls) if image_urls else None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Surface ``image_url`` so Custom Lovelace Cards can read it.

        v1.25.0 PR-F (Audit Agent E #5 win): Cards like Ultra-Vehicle-Card,
        vehicle-info-card, mushroom-template-card consume an ``image_url``
        attribute to render the car photo next to the entity. By centrally
        adding it here, every entity (sensor, binary_sensor, switch, etc.)
        becomes a valid source for those cards.

        Subclasses can override + call ``super().extra_state_attributes``
        to merge in their own attributes.
        """
        vehicle = self._vehicle
        image_urls: dict = vehicle.get("image_urls") or {}
        if not image_urls:
            return None
        url = VehicleImageFetcher.best_url(image_urls)
        return {"image_url": url} if url else None


# v1.25.0 PR-C — Listener-Pattern helper. Adopts the volkswagencarnet
# PR #943 pattern (open as of audit 2026-05-08): platforms register
# a coordinator listener so vehicles that wake LATER (was asleep at
# HA startup) get their entities spawned mid-session, instead of
# users having to restart HA after the car wakes.
#
# Usage in a platform's `async_setup_entry`:
#
#     from .entity_base import register_dynamic_spawner
#
#     def _build_for_vin(vin, vehicle):
#         entities = []
#         for desc in MY_DESCRIPTIONS:
#             if desc.condition(vehicle):
#                 entities.append(MyEntity(coordinator, vin, desc))
#         return entities
#
#     register_dynamic_spawner(entry, coordinator, async_add_entities,
#                              _build_for_vin)
#
# Idempotent: each VIN is spawned exactly once. Safe to call without
# any vehicles in coordinator.vehicles yet (initial setup before first
# poll).
def register_dynamic_spawner(
    entry: Any,
    coordinator: VagConnectCoordinator,
    async_add_entities: Any,
    build_for_vin: Any,
) -> None:
    """Register a coordinator listener that spawns entities for new VINs.

    ``build_for_vin(vin: str, vehicle: dict) -> list[Entity]``
        Called once per VIN that hasn't been spawned yet. Return the
        list of entities to add for that VIN. Return an empty list if
        the vehicle isn't yet ready (no data) — listener will retry on
        next coordinator update.

    The set of "already-spawned" VINs is tracked in a closure so each
    listener invocation only adds NEW VINs. Initial pass is also
    performed synchronously here, so platforms that already-have-data
    spawn immediately instead of waiting for the first refresh.
    """
    added: set[str] = set()

    def _spawn() -> None:
        new_entities: list[Any] = []
        for vin, vehicle in coordinator.vehicles.items():
            if vin in added:
                continue
            built = build_for_vin(vin, vehicle)
            if built:
                new_entities.extend(built)
                added.add(vin)
        if new_entities:
            async_add_entities(new_entities)

    # Initial pass — vehicles already in coordinator data spawn immediately
    _spawn()
    # Listener pass — new vehicles or wake-ups spawn on the next poll
    entry.async_on_unload(coordinator.async_add_listener(_spawn))
