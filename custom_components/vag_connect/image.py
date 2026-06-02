# Copyright 2026 Prash Balan (@its-me-prash) — Apache License 2.0
# SPDX-License-Identifier: Apache-2.0
"""Image entities for VAG Connect — 7 vehicle render images per vehicle.

Creates one ImageEntity per MediaType per vehicle:
  image.{vehicle}_render_icon       (MS_MYP3,   76 KB)
  image.{vehicle}_render_small      (MS_MYP4,  117 KB)
  image.{vehicle}_render_medium     (MS_MYP5,  196 KB)
  image.{vehicle}_render_side_sm    (MYAPN3NB, 158 KB)
  image.{vehicle}_render_side_lg    (MYAPN8NB, 309 KB) ← recommended
  image.{vehicle}_render_angle_hd   (MYAAN3NB, 1.7 MB)
  image.{vehicle}_render_angle_lg   (MYAAN8NB, 879 KB)

All images are cached locally under /config/www/vehicles/{vin}_{tag}.png
for offline use and fast Lovelace card loading.
"""

from __future__ import annotations

import logging

import asyncio
import os
from datetime import datetime, timezone

from homeassistant.components.image import ImageEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .cariad._util import mask_vin
from .cariad.api.graphql import RENDER_IMAGE_TYPES, RENDER_TYPE_BY_MEDIA
from .coordinator import VagConnectCoordinator
from .entity_base import VagConnectEntity

_LOGGER = logging.getLogger(__name__)

# Local cache directory under HA's /config/www/
_CACHE_SUBDIR = "vehicles"


def _local_path(hass: HomeAssistant, vin: str, tag: str) -> str:
    """Return absolute path to local cached PNG file."""
    www_dir = hass.config.path("www", _CACHE_SUBDIR)
    return os.path.join(www_dir, f"{vin}_{tag}.png")


def _local_url(vin: str, tag: str) -> str:
    """Return HA /local/ URL for the cached image (for Lovelace use)."""
    return f"/local/{_CACHE_SUBDIR}/{vin}_{tag}.png"


def _safe_slug(s: str) -> str:
    """Lowercase + collapse non-identifier chars to underscore.

    Used to derive stable ``entity_suffix`` / cache filename from a
    raw viewPoint string returned by a brand backend. Examples:

      "side"           -> "side"
      "EXTERIOR_SIDE"  -> "exterior_side"
      "front-left"     -> "front_left"
      " 3/4 angle "    -> "3_4_angle"
    """
    out = []
    prev_under = False
    for ch in s.strip().lower():
        if ch.isalnum():
            out.append(ch)
            prev_under = False
        elif not prev_under:
            out.append("_")
            prev_under = True
    return "".join(out).strip("_") or "render"


def _humanize(s: str) -> str:
    """Render a viewPoint string as a human-readable label.

    "EXTERIOR_SIDE" -> "Exterior Side"
    "side"          -> "Side"
    """
    return s.replace("_", " ").replace("-", " ").strip().title() or s


def _synthesize_meta(view_key: str) -> dict[str, str]:
    """Build a ``RENDER_IMAGE_TYPES``-shaped meta dict for a viewPoint
    string that isn't in the Audi/VW GraphQL MediaService catalog.

    v1.24.0 — used for two brand-tracks that report renders via flat
    viewPoint dicts instead of named MediaTypes:

    - **CUPRA/SEAT** (OLA backend): ``GET /v2/vehicles/{vin}/renders``
      returns ``[{viewPoint, type, url}]``. ``_fetch_renders`` (in
      ``seat_cupra.py``) writes those into ``image_urls`` keyed by the
      raw viewPoint string. Pre-v1.24.0 this data was silently
      dropped because ``_add_entities_for_vin`` only iterated
      ``RENDER_IMAGE_TYPES`` (Audi/VW MediaType IDs like ``"MS_MYP3"``)
      and never matched.
    - **Skoda** (mysmob backend): ``GET /api/v1/vehicle-information/
      {vin}/renders`` returns ``compositeRenders[].layers[].url``
      keyed by ``viewPoint`` like ``"EXTERIOR_SIDE"``. The v1.22.x
      foundation parser flattens that into ``data["composite_render_
      urls"]`` and the coordinator merges into ``image_urls``.

    The synthesized meta uses the raw ``view_key`` as ``media_type``
    so ``VagRenderImageEntity.image_url`` looks it up in the same
    ``image_urls`` dict via the existing code path. Slug + label are
    derived defensively for arbitrary backend strings.
    """
    slug = _safe_slug(view_key)
    return {
        "media_type":       view_key,
        "entity_suffix":    f"render_{slug}",
        "tag":              slug,
        "view_description": _humanize(view_key),
        "recommended_use":  "Brand-native viewpoint (OLA / mysmob)",
        "file_size_approx": "n/a",
    }


def _has_image_data(vehicle: dict) -> bool:
    """Return True if the vehicle has *any* render-image source.

    v1.24.0 — broadened from the earlier ``vehicle.get("image_urls")``
    check so that vehicles which only have ``render_url`` (Skoda
    widget per-tick) or ``composite_render_urls`` (Skoda multi-angle,
    pre-coordinator-merge) also trigger entity creation.
    """
    return bool(
        vehicle.get("image_urls")
        or vehicle.get("render_url")
        or vehicle.get("composite_render_urls")
    )


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up image entities — 7 per vehicle that has render images.

    If image_urls are not yet available at setup time (GraphQL fetch pending
    or failed), a coordinator listener will retry once data arrives.
    """
    coordinator: VagConnectCoordinator = entry.runtime_data
    added_vins: set[str] = set()

    # Ensure cache dir exists
    www_dir = hass.config.path("www", _CACHE_SUBDIR)
    await hass.async_add_executor_job(os.makedirs, www_dir, 0o755, True)

    def _add_entities_for_vin(vin: str, vehicle: dict) -> list[ImageEntity]:
        image_urls: dict[str, str] = vehicle.get("image_urls") or {}
        entities: list[ImageEntity] = []
        # ── Branch 1: Audi/VW GraphQL MediaService catalog ──────────────
        # 7 named MediaTypes (MYAPN8NB, MS_MYP3, ...) populated by
        # ``cariad/api/graphql.py``. Order matters — RENDER_IMAGE_TYPES
        # lists best-for-Lovelace first.
        matched_keys: set[str] = set()
        for meta in RENDER_IMAGE_TYPES:
            url = image_urls.get(meta["media_type"])
            if url:
                entities.append(VagRenderImageEntity(
                    hass, coordinator, vin, meta, url,
                ))
                matched_keys.add(meta["media_type"])
        # ── Branch 2 (v1.24.0): brand-native viewpoints not in the ──────
        # GraphQL catalog. Two backends report renders this way:
        #   • CUPRA/SEAT OLA: ``_fetch_renders`` writes viewPoint
        #     strings like ``"side"`` / ``"front"`` / ``"rear"``.
        #     Pre-v1.24.0 this dict was populated but no entities ever
        #     spawned because the loop above only matched MediaType IDs
        #     — silent latent bug since OLA support landed.
        #   • Skoda mysmob: ``compositeRenders[].layers[]`` parsed by
        #     coordinator into ``data["composite_render_urls"]`` then
        #     merged into ``image_urls`` (v1.22.x foundation +
        #     v1.24.0 wire-in). Keys look like ``"exterior_side"``,
        #     ``"interior_boot"``, etc.
        # Synthesize a meta on the fly so the existing
        # ``VagRenderImageEntity`` works without a parallel class.
        for key, url in image_urls.items():
            if key in matched_keys:
                continue
            if key in RENDER_TYPE_BY_MEDIA:
                # Defensive: skip catalog IDs even if Branch 1 missed
                # them (e.g. backend returned an empty URL string).
                continue
            if not isinstance(url, str) or not url.startswith("http"):
                continue
            entities.append(VagRenderImageEntity(
                hass, coordinator, vin, _synthesize_meta(key), url,
            ))
        # ── Branch 3 (v1.22.0): Skoda widget single-render ──────────────
        # ``data["render_url"]`` is populated per-tick by the v1.20.0
        # widget endpoint (myskoda PR #557 — ``vehicle.renderUrl``).
        # Separate class because it has its own URL refresh path
        # (reads ``render_url`` not ``image_urls``) and a fixed
        # ``widget`` cache filename for backward-compat with the
        # entity ID introduced in v1.22.0.
        skoda_render = vehicle.get("render_url")
        if isinstance(skoda_render, str) and skoda_render.startswith("http"):
            entities.append(VagSkodaWidgetImageEntity(
                hass, coordinator, vin, skoda_render,
            ))
        return entities

    # Initial setup — add entities for vehicles with any render-image data.
    # v1.24.0: trigger broadened from ``image_urls`` only to also catch
    # Skoda widget-only and Skoda pre-merge composite cases.
    entities = []
    for vin, vehicle in coordinator.vehicles.items():
        if _has_image_data(vehicle):
            new = _add_entities_for_vin(vin, vehicle)
            if new:
                entities.extend(new)
                added_vins.add(vin)
                _LOGGER.debug(
                    "Image entities created for %s (%d entities)",
                    mask_vin(vin), len(new),
                )
        else:
            _LOGGER.debug(
                "No render-image data for %s at setup — will retry on next coordinator update",
                mask_vin(vin),
            )

    if entities:
        async_add_entities(entities)
        asyncio.ensure_future(_cache_all_images(hass, coordinator))

    # Listener: create entities if any render-image data arrives on a
    # subsequent poll (v1.24.0 — same broadened trigger as setup).
    def _on_coordinator_update() -> None:
        new_entities = []
        for vin, vehicle in coordinator.vehicles.items():
            if vin in added_vins:
                continue
            if _has_image_data(vehicle):
                new = _add_entities_for_vin(vin, vehicle)
                if new:
                    new_entities.extend(new)
                    added_vins.add(vin)
                    _LOGGER.info(
                        "Image entities created for %s on coordinator update (%d entities)",
                        mask_vin(vin), len(new),
                    )
        if new_entities:
            async_add_entities(new_entities)
            asyncio.ensure_future(_cache_all_images(hass, coordinator))

    entry.async_on_unload(coordinator.async_add_listener(_on_coordinator_update))


async def _cache_all_images(
    hass: HomeAssistant,
    coordinator: VagConnectCoordinator,
) -> None:
    """Download and cache all render images locally (background task)."""
    from homeassistant.helpers.aiohttp_client import async_get_clientsession  # noqa: PLC0415
    session = async_get_clientsession(hass)

    for vin, vehicle in coordinator.vehicles.items():
        image_urls: dict[str, str] = vehicle.get("image_urls") or {}
        # Branch 1: Audi/VW catalog tags (best-known cache filenames).
        cached_keys: set[str] = set()
        for meta in RENDER_IMAGE_TYPES:
            url = image_urls.get(meta["media_type"])
            if not url:
                continue
            cached_keys.add(meta["media_type"])
            local = _local_path(hass, vin, meta["tag"])
            if await hass.async_add_executor_job(os.path.exists, local):
                continue  # Already cached
            try:
                async with session.get(url, timeout=None) as resp:
                    if resp.status == 200:
                        content = await resp.read()
                        await hass.async_add_executor_job(
                            _write_file, local, content
                        )
                        _LOGGER.debug(
                            "Cached %s → %s (%d KB)",
                            meta["tag"], local, len(content) // 1024,
                        )
            except Exception:  # noqa: BLE001
                pass  # Cache failure is non-critical
        # v1.24.0 — Branch 2: cache OLA viewPoints + Skoda mysmob
        # composites (anything in image_urls not covered by Branch 1).
        # Tag derived via the same _safe_slug used to build entity_suffix
        # so the local file aligns 1:1 with the entity attribute.
        for key, url in image_urls.items():
            if key in cached_keys or key in RENDER_TYPE_BY_MEDIA:
                continue
            if not isinstance(url, str) or not url.startswith("http"):
                continue
            tag = _safe_slug(key)
            local = _local_path(hass, vin, tag)
            if await hass.async_add_executor_job(os.path.exists, local):
                continue
            try:
                async with session.get(url, timeout=None) as resp:
                    if resp.status == 200:
                        content = await resp.read()
                        await hass.async_add_executor_job(
                            _write_file, local, content
                        )
                        _LOGGER.debug(
                            "Cached %s → %s (%d KB)",
                            tag, local, len(content) // 1024,
                        )
            except Exception:  # noqa: BLE001
                pass
        # v1.22.0 (Bundle 2 Phase B) — cache Skoda widget render too
        skoda_url = vehicle.get("render_url")
        if isinstance(skoda_url, str) and skoda_url.startswith("http"):
            local = _local_path(hass, vin, "widget")
            if not await hass.async_add_executor_job(os.path.exists, local):
                try:
                    async with session.get(skoda_url, timeout=None) as resp:
                        if resp.status == 200:
                            content = await resp.read()
                            await hass.async_add_executor_job(
                                _write_file, local, content
                            )
                            _LOGGER.debug(
                                "Cached Skoda widget render → %s (%d KB)",
                                local, len(content) // 1024,
                            )
                except Exception:  # noqa: BLE001
                    pass


def _write_file(path: str, content: bytes) -> None:
    """Write bytes to file (runs in executor)."""
    with open(path, "wb") as f:
        f.write(content)




class VagRenderImageEntity(VagConnectEntity, ImageEntity):
    """One render image entity for a single MediaType + vehicle combination.

    Attributes expose all metadata for Lovelace use:
      - source_url: the original public URL from mediaservice
      - local_path: /local/vehicles/{vin}_{tag}.png (usable in picture-entity)
      - tag, media_type, view_description, recommended_use, file_size_approx
      - vehicle_name, vin, media_short_name, media_long_name
    """

    _attr_content_type = "image/png"

    def __init__(
        self,
        hass: HomeAssistant,
        coordinator: VagConnectCoordinator,
        vin: str,
        meta: dict[str, str],
        initial_url: str,
    ) -> None:
        VagConnectEntity.__init__(self, coordinator, vin, meta["entity_suffix"])
        ImageEntity.__init__(self, hass, verify_ssl=True)
        self._meta = meta
        self._attr_name = self._label_for(meta)
        self._attr_image_url = initial_url
        self._attr_image_last_updated = datetime.now(tz=timezone.utc)

    @staticmethod
    def _label_for(meta: dict[str, str]) -> str:
        """Human-readable name, e.g. 'Seitenprofil groß'."""
        return meta["view_description"]

    @property
    def image_url(self) -> str | None:
        """Return current URL — refreshes if vehicle config changed."""
        vehicle = self._vehicle
        image_urls: dict[str, str] = vehicle.get("image_urls") or {}
        fresh = image_urls.get(self._meta["media_type"])
        if fresh and fresh != self._attr_image_url:
            self._attr_image_url = fresh
            self._attr_image_last_updated = datetime.now(tz=timezone.utc)
            self._cached_image = None  # type: ignore[assignment]
            # Delete stale local cache so it gets re-downloaded
            local = _local_path(self.hass, self._vin, self._meta["tag"])
            try:
                if os.path.exists(local):
                    os.remove(local)
            except OSError:
                pass
        return self._attr_image_url if isinstance(self._attr_image_url, str) else None

    @property
    def extra_state_attributes(self) -> dict:
        """Full metadata for Lovelace and automations."""
        vehicle = self._vehicle
        image_urls: dict[str, str] = vehicle.get("image_urls") or {}
        url = image_urls.get(self._meta["media_type"])
        local = _local_url(self._vin, self._meta["tag"])
        local_abs = _local_path(self.hass, self._vin, self._meta["tag"])

        attrs: dict = {
            "media_type":       self._meta["media_type"],
            "tag":              self._meta["tag"],
            "view_description": self._meta["view_description"],
            "recommended_use":  self._meta["recommended_use"],
            "file_size_approx": self._meta["file_size_approx"],
            "source_url":       url,
            "local_path":       local,
            "local_cached":     os.path.exists(local_abs),
            "vin":              self._vin,
        }

        # Media names from GraphQL
        if vehicle.get("media_short_name"):
            attrs["vehicle_short_name"] = vehicle["media_short_name"]
        if vehicle.get("media_long_name"):
            attrs["vehicle_long_name"] = vehicle["media_long_name"]
        if vehicle.get("media_exterior_color"):
            attrs["exterior_color"] = vehicle["media_exterior_color"]

        return attrs


class VagSkodaWidgetImageEntity(VagConnectEntity, ImageEntity):
    """v1.22.0 (Bundle 2 Phase B) — Skoda widget render image.

    Single ImageEntity per Skoda VIN, populated from
    ``data["render_url"]`` (which v1.20.0 widget endpoint set from
    ``vehicle.renderUrl`` per myskoda PR #557).

    Differences vs ``VagRenderImageEntity``:
    - Skoda exposes ONE render URL (not 7 MediaType variants like
      Audi/VW GraphQL)
    - URL refresh check uses ``data["render_url"]`` instead of
      ``image_urls`` dict lookup
    - Cached locally as ``{vin}_widget.png`` (single file per VIN)
    """

    _attr_content_type = "image/png"
    _SKODA_TAG = "widget"

    def __init__(
        self,
        hass: HomeAssistant,
        coordinator: VagConnectCoordinator,
        vin: str,
        initial_url: str,
    ) -> None:
        VagConnectEntity.__init__(self, coordinator, vin, "render_widget")
        ImageEntity.__init__(self, hass, verify_ssl=True)
        self._attr_name = "Vehicle Render"
        self._attr_image_url = initial_url
        self._attr_image_last_updated = datetime.now(tz=timezone.utc)

    @property
    def image_url(self) -> str | None:
        """Return current URL — refreshes if widget endpoint published
        a new renderUrl (e.g. user changed paint via app)."""
        vehicle = self._vehicle
        fresh = vehicle.get("render_url")
        if (
            isinstance(fresh, str)
            and fresh.startswith("http")
            and fresh != self._attr_image_url
        ):
            self._attr_image_url = fresh
            self._attr_image_last_updated = datetime.now(tz=timezone.utc)
            self._cached_image = None  # type: ignore[assignment]
            local = _local_path(self.hass, self._vin, self._SKODA_TAG)
            try:
                if os.path.exists(local):
                    os.remove(local)
            except OSError:
                pass
        return (
            self._attr_image_url
            if isinstance(self._attr_image_url, str)
            else None
        )

    @property
    def extra_state_attributes(self) -> dict:
        """Skoda widget metadata for Lovelace use."""
        vehicle = self._vehicle
        url = vehicle.get("render_url")
        local = _local_url(self._vin, self._SKODA_TAG)
        local_abs = _local_path(self.hass, self._vin, self._SKODA_TAG)
        attrs: dict = {
            "tag":              self._SKODA_TAG,
            "view_description": "Skoda widget render",
            "source":           "myskoda widget endpoint (v1.20.0)",
            "source_url":       url,
            "local_path":       local,
            "local_cached":     os.path.exists(local_abs),
            "vin":              self._vin,
        }
        if vehicle.get("license_plate"):
            attrs["license_plate"] = vehicle["license_plate"]
        if vehicle.get("model"):
            attrs["model"] = vehicle["model"]
        return attrs
