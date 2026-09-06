# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Base entity class for all VW Group Connect entities."""

from __future__ import annotations
from typing import Any

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .cariad.api.graphql import VehicleImageFetcher
from .const import DOMAIN
from .coordinator import VagConnectCoordinator


# #1316 — brands whose slug title-cases badly (underscores / mixed case). This
# display override keeps the device page + entity names clean; every other brand
# falls back to ``brand.title()`` unchanged, so no existing device is renamed.
_BRAND_DISPLAY: dict[str, str] = {
    "volkswagen_commercial": "Volkswagen Commercial Vehicles",
}


def _brand_display(brand: str) -> str:
    """Human-readable brand label for the HA device (manufacturer + name).

    HA registry ``manufacturer``/``name`` are plain strings (not translatable),
    so this is one canonical English label — consistent with ``const.BRANDS``."""
    return _BRAND_DISPLAY.get((brand or "").lower()) or brand.title()


def _device_name(vehicle: dict, brand: str) -> str:
    """Return "{Brand} {Model}" or "{Brand} {VIN[-6:]}" as device name."""
    label = _brand_display(brand)
    model = (vehicle.get("model") or "").strip()
    if model and model.lower() not in ("vag vehicle", "unknown", ""):
        return f"{label} {model}"
    vin = vehicle.get("vin", "")
    return f"{label} {vin[-6:]}" if vin else label


# Connection-status diagnostics that must stay AVAILABLE even when the vehicle
# poll is failing — otherwise the user is blinded to WHY the car went
# unavailable exactly when they need to read it (the whole car went dark, so did
# the "last reported", "data source", error-reporter and connectivity entities).
# Keyed by entity_description.key; custom classes set ``_stay_available_on_poll_failure``.
_CONNECTION_STATUS_KEYS = frozenset({
    "last_updated_at",
    "last_seen_at",
    "data_source_channel",
    "error_reporter_count",
    "connection_active",
})


class VagConnectEntity(CoordinatorEntity[VagConnectCoordinator]):
    """Base entity shared by all VW Group Connect platforms.

    Parallel updates: the coordinator's background poll loop owns all API
    calls, so entity updates need no throttling. HA reads that from a
    MODULE-level ``PARALLEL_UPDATES = 0`` in each platform file (an entity
    attribute is a no-op), so it is declared there, not here.

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

        Connection-status diagnostics (``_CONNECTION_STATUS_KEYS`` / classes that
        set ``_stay_available_on_poll_failure``) stay available regardless of the
        poll outcome, so a car going unreachable doesn't also hide the very
        entities that explain why.
        """
        desc = getattr(self, "entity_description", None)
        if getattr(self, "_stay_available_on_poll_failure", False) or (
            desc is not None and getattr(desc, "key", "") in _CONNECTION_STATUS_KEYS
        ):
            return True
        if not super().available:
            # Connector-level failure (``last_update_success``). That is a
            # statement about the poll, not about this car: a single-vehicle
            # account hits it on any transient 5xx or timeout, and every
            # account hits it during a backend-wide outage. Returning here
            # made the coordinator's own two-stage tolerance unreachable for
            # exactly those cases, even though the poll-failure path promises
            # it (coordinator.py, "is_vehicle_available still tolerates this").
            # Fall through to that policy, but only when we actually hold a
            # last-known-good snapshot for this VIN, so a car that has never
            # polled successfully still reports unavailable as before.
            last_good = (
                getattr(self.coordinator, "vehicle_last_good_at", {}) or {}
            ).get(self._vin)
            if last_good is None:
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
        # #1001 — three of these had gone 404 (brands reorganise their sites).
        # Every entry below was checked to answer 200 on 2026-08-01; prefer a
        # durable section landing page over a deep link that gets renamed.
        "audi":          "https://my.audi.com/",
        "volkswagen":    "https://www.volkswagen.de/de/besitzer-und-nutzer.html",
        "volkswagen_commercial": "https://www.volkswagen-nutzfahrzeuge.de/",  # #1316
        "skoda":         "https://www.skoda-auto.com/",
        "seat":          "https://www.seat.com/owners",
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
        # v2.18.2 — device model string. CARIAD often returns the model with a
        # redundant leading brand ("Audi S6 Avant …") while ``manufacturer`` is
        # already the brand, so strip that prefix, then append the model year →
        # "S6 Avant TDI quattro tiptronic (2021)". Year is null-guarded (a missing
        # year must NOT render "(None)"). ``serial_number`` stays the VIN.
        _model_raw = (vehicle.get("model") or "").strip()
        if _model_raw and _model_raw.lower().startswith(brand.lower() + " "):
            _model_raw = _model_raw[len(brand) + 1:].strip()
        _year = vehicle.get("model_year")
        if _model_raw:
            _model_str = f"{_model_raw} ({_year})" if _year else _model_raw
        else:
            # No model name available (e.g. a VW-EU portal-only car, whose feed
            # carries no model field at all) — fall back to a clean brand label
            # rather than the generic "VAG Vehicle".
            _brand_label = (
                brand.replace("_", " ").title() if brand and brand != "vag"
                else "VAG Vehicle"
            )
            # #1229 — never render the bare brand alone when we at least know the
            # model year; qualify it ("Audi (2024)") so the device page is more
            # specific than "Audi" even while the richer model name is missing.
            _model_str = f"{_brand_label} ({_year})" if _year else _brand_label

        return DeviceInfo(
            identifiers={(DOMAIN, self._vin)},
            name=name,
            model=_model_str,
            # Prefer an explicit manufacturer the reader resolved (e.g. acpp maps
            # brandCode "A" → "Audi"); else the display label for the config brand
            # (#1316: "Volkswagen Commercial Vehicles", not "Volkswagen_Commercial";
            # unmapped brands stay title-cased as before).
            manufacturer=vehicle.get("manufacturer") or _brand_display(brand),
            serial_number=self._vin,
            hw_version=(str(_year) if _year else None),
            sw_version=vehicle.get("firmware_version"),
            configuration_url=self._BRAND_PORTAL.get(brand.lower()),
            suggested_area="Garage",
        )

    # #1229 (Ra72xx) — the vehicle render is exposed as its own Image entity
    # (image.py) and, for the entities that opt in below, as the device/map
    # picture. Previously EVERY entity returned it, which replaced the icon of
    # all 100+ sensors in dashboards (mushroom/glance) with the car photo — noisy
    # and unwanted. Now only entities that set ``_show_vehicle_picture = True``
    # (the device tracker, so the device page + map marker keep the car photo)
    # carry it; every other entity falls back to its own icon.
    _show_vehicle_picture: bool = False

    @property
    def entity_picture(self) -> str | None:
        """Vehicle render as entity picture, only for opt-in entities.

        Returns None for regular entities so HA uses their icon; the dedicated
        Image entity (image.py) is the way to display the render on a dashboard.
        """
        if not self._show_vehicle_picture:
            return None
        vehicle = self._vehicle
        image_urls: dict = vehicle.get("image_urls") or {}
        return VehicleImageFetcher.best_url(image_urls) if image_urls else None

    @property
    def _field_source(self) -> str | None:
        """Which read channel produced THIS entity's value.

        v2.18.0 (B1) — a car can be read over several channels at once and no
        channel is complete, so on a Golf GTE the fuel level and the SoC
        legitimately come from different places. ``source_channel`` only says
        which channels fed the car; the per-field map says which one produced
        this particular reading. ``None`` when the field carries no value or
        the entity isn't backed by a data_key.

        ``entity_description`` is read defensively because not every entity has
        one: HA's ``Entity`` does not define it at class level, and our image
        entities never assign it. This used to reach straight through it, which
        was survivable only while the platform overrides shadowed this property
        away — the moment the base actually ran for every entity, it became an
        AttributeError on the image platform. The existing widget-image test
        caught exactly that.
        """
        desc = getattr(self, "entity_description", None)
        key = getattr(desc, "data_key", None) if desc is not None else None
        if not key:
            return None
        sources = self._vehicle.get("field_sources")
        if not isinstance(sources, dict):
            return None
        source = sources.get(key)
        return source if isinstance(source, str) else None

    def _platform_attributes(self) -> dict[str, Any] | None:
        """Per-platform attributes, merged into ``extra_state_attributes``.

        Platforms override THIS, not ``extra_state_attributes``. That is the
        whole point of it existing — see the note there.
        """
        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Surface ``image_url`` + the reading's ``source``, plus the
        platform's own attributes from ``_platform_attributes``.

        v1.25.0 PR-F (Audit Agent E #5 win): Cards like Ultra-Vehicle-Card,
        vehicle-info-card, mushroom-template-card consume an ``image_url``
        attribute to render the car photo next to the entity. By centrally
        adding it here, every entity (sensor, binary_sensor, switch, etc.)
        becomes a valid source for those cards.

        v2.18.0 (B1) — ``source`` names the read channel this value came from,
        so "where is this number from" is answerable per entity instead of only
        per car, and templates/automations can key on it.

        v2.18.0 — this used to say "subclasses can override + call
        ``super().extra_state_attributes`` to merge in their own attributes",
        and not one of the seven subclasses that override it ever did. Python
        does not warn about that: the subclass property simply wins the MRO and
        the base never runs. So sensors, binary_sensors, device_tracker and the
        image entities — which is to say nearly every entity we create — got
        neither ``image_url`` nor ``source``. ``image_url`` had been dead that
        way since v1.25.0, under a docstring claiming the opposite, and
        ``source`` was born dead in this very release.

        Hence the inversion: the base owns the property and calls a hook.
        A platform can no longer shadow the shared attributes by forgetting to
        call ``super()``, because there is nothing left to forget.
        """
        attrs: dict[str, Any] = {}

        image_urls: dict = self._vehicle.get("image_urls") or {}
        if image_urls:
            url = VehicleImageFetcher.best_url(image_urls)
            if url:
                attrs["image_url"] = url

        source = self._field_source
        if source:
            # friendly channel name ("Car-Net"), not the raw token ("mbb").
            # _field_source stays the raw token for internal keying.
            from ._channel_labels import channel_display_name  # noqa: PLC0415
            attrs["source"] = channel_display_name(source)

        own = self._platform_attributes()
        if own:
            attrs.update(own)

        return attrs or None


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

    The set of "already-spawned" ENTITIES is tracked by unique_id in a closure,
    and the build is re-evaluated on every coordinator update — so an entity
    whose data only appears on a later poll (e.g. a sensor gated on data-present)
    still spawns the moment its value arrives, while entities already added are
    never duplicated. Initial pass runs synchronously so already-present entities
    spawn immediately instead of waiting for the first refresh.

    v2.15.0b3 — switched from per-VIN to per-unique_id tracking to support the
    "hide entities without data" gating, where build_for_vin may legitimately
    return a growing set for a VIN across polls as fields populate.
    """
    added: set[str] = set()

    def _spawn() -> None:
        new_entities: list[Any] = []
        for vin, vehicle in coordinator.vehicles.items():
            for ent in build_for_vin(vin, vehicle):
                uid = getattr(ent, "unique_id", None) or getattr(
                    ent, "_attr_unique_id", None
                )
                if not uid or uid in added:
                    continue
                new_entities.append(ent)
                added.add(uid)
        if new_entities:
            async_add_entities(new_entities)

    # Initial pass — vehicles already in coordinator data spawn immediately
    _spawn()
    # Listener pass — new vehicles or wake-ups spawn on the next poll
    entry.async_on_unload(coordinator.async_add_listener(_spawn))
