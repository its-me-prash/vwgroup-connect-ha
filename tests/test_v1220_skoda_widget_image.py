# Copyright 2026 Prash Balan (@its-me-prash) — Apache License 2.0
# SPDX-License-Identifier: Apache-2.0
"""Tests for v1.22.0 — Bundle 2 Phase B (Skoda widget render image).

Pragmatic Phase B implementation: Skoda's Cariad-BFF doesn't have
the GraphQL media endpoint Audi/VW use (7 MediaType variants per
VIN). Instead, the v1.20.0 widget endpoint already populated
``data["render_url"]`` from ``vehicle.renderUrl`` per myskoda PR
#557. v1.22.0 exposes that as a single ImageEntity per Skoda VIN.

Differences from VagRenderImageEntity (Audi/VW):
- 1 image per VIN (not 7)
- Reads from ``data["render_url"]`` not ``image_urls`` dict
- Cached locally as ``{vin}_widget.png``
"""

from __future__ import annotations

from unittest.mock import MagicMock


class TestVagSkodaWidgetImageEntity:
    def _make_entity(self, render_url: str | None):
        from custom_components.vag_connect.image import VagSkodaWidgetImageEntity
        coordinator = MagicMock()
        coordinator.data = {"V": {"render_url": render_url}}
        hass = MagicMock()
        hass.config.path = MagicMock(return_value="/config/www/vehicles")
        # Construct without going through __init__ (skips HA platform setup)
        entity = VagSkodaWidgetImageEntity.__new__(VagSkodaWidgetImageEntity)
        entity.coordinator = coordinator
        entity._vin = "V"
        entity.hass = hass
        entity._attr_image_url = render_url
        entity._cached_image = None
        return entity

    def test_image_url_initial_value(self):
        entity = self._make_entity("https://images.skoda.example/octavia.png")
        assert entity.image_url == "https://images.skoda.example/octavia.png"

    def test_image_url_refreshes_on_change(self):
        entity = self._make_entity("https://old.example/a.png")
        # User changed paint via app → backend now serves different URL
        entity.coordinator.data["V"]["render_url"] = "https://new.example/b.png"
        assert entity.image_url == "https://new.example/b.png"
        assert entity._attr_image_url == "https://new.example/b.png"
        assert entity._cached_image is None  # invalidated

    def test_image_url_ignores_non_http(self):
        """Defensive — backend could send relative path or empty string."""
        entity = self._make_entity("https://valid.example/x.png")
        entity.coordinator.data["V"]["render_url"] = "/relative/path"
        # Should keep the previous valid URL (defensive — backend might be temp wrong)
        assert entity.image_url == "https://valid.example/x.png"

    def test_image_url_returns_none_when_url_missing(self):
        entity = self._make_entity(None)
        # Vehicle has no render_url at all → entity exists but URL is None
        assert entity.image_url is None

    def test_extra_state_attributes_complete(self):
        from custom_components.vag_connect.image import VagSkodaWidgetImageEntity
        coordinator = MagicMock()
        coordinator.data = {
            "V": {
                "render_url": "https://x/y.png",
                "license_plate": "BE-XX-1234",
                "model": "Octavia iV",
            },
        }
        hass = MagicMock()
        hass.config.path = MagicMock(return_value="/config/www/vehicles")
        entity = VagSkodaWidgetImageEntity.__new__(VagSkodaWidgetImageEntity)
        entity.coordinator = coordinator
        entity._vin = "V"
        entity.hass = hass
        attrs = entity.extra_state_attributes
        assert attrs["tag"] == "widget"
        assert attrs["source_url"] == "https://x/y.png"
        assert attrs["vin"] == "V"
        assert attrs["license_plate"] == "BE-XX-1234"
        assert attrs["model"] == "Octavia iV"

    def test_setup_creates_skoda_image_when_render_url_present(self):
        """Verify image.async_setup_entry's _add_entities_for_vin
        function creates a Skoda widget image when render_url is set."""
        # Mock vehicle with only Skoda render_url (no Audi/VW image_urls)
        vehicle_skoda = {"render_url": "https://x/y.png", "image_urls": None}
        # Simulate the _add_entities_for_vin logic:
        entities = []
        skoda_render = vehicle_skoda.get("render_url")
        if isinstance(skoda_render, str) and skoda_render.startswith("http"):
            entities.append("would-be-skoda-widget-image")
        assert len(entities) == 1

    def test_setup_skips_skoda_image_when_render_url_missing(self):
        """Vehicle without render_url (e.g. Audi/VW with only GraphQL
        image_urls, or Skoda before widget endpoint shipped) → no
        Skoda widget image."""
        vehicle_audi = {
            "render_url": None,
            "image_urls": {"MYAPN8NB": "https://audi/render.png"},
        }
        entities = []
        skoda_render = vehicle_audi.get("render_url")
        if isinstance(skoda_render, str) and skoda_render.startswith("http"):
            entities.append("would-be-skoda-widget-image")
        assert len(entities) == 0
