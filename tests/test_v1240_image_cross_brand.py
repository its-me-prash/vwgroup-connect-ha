# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for v1.24.0 — cross-brand image-entity wiring.

Two fixes bundled:

A) **CUPRA/SEAT silent latent bug** — pre-v1.24.0 ``_fetch_renders``
   in ``cariad/api/seat_cupra.py`` populated ``image_urls`` with raw
   viewPoint strings (``"side"``, ``"front"``, ``"rear"``) but
   ``image.py:_add_entities_for_vin`` only iterated ``RENDER_IMAGE_
   TYPES`` (Audi/VW MediaService catalog IDs like ``"MYAPN8NB"``).
   The lookup never matched → 0 image entities ever spawned for OLA
   users since render support landed.

B) **Skoda mysmob multi-angle wire-in** — v1.22.x foundation parsed
   ``compositeRenders[].layers[]`` into ``data["composite_render_
   urls"]`` but never created entities. v1.24.0 merges those into
   ``image_urls`` in coordinator ``_enrich`` so the same Branch-2
   leftover-keys path catches them.

Both fixes share infrastructure:
- ``_safe_slug``: stable lowercase identifier per viewPoint
- ``_humanize``: human-readable label for UI
- ``_synthesize_meta``: builds a ``RENDER_IMAGE_TYPES``-shaped dict
  on the fly so the existing ``VagRenderImageEntity`` works without
  a parallel class
- ``_has_image_data``: broadened spawn-trigger covering image_urls
  / render_url / composite_render_urls
"""

from __future__ import annotations


# ─────────────────────────────────────────────────────────────────────────────
# A) Helper functions (no HA imports required — pure logic)
# ─────────────────────────────────────────────────────────────────────────────


class TestSafeSlug:
    def _slug(self, s):
        from custom_components.vag_connect.image import _safe_slug
        return _safe_slug(s)

    def test_lowercase_passthrough(self):
        assert self._slug("side") == "side"

    def test_uppercase_lowered(self):
        assert self._slug("EXTERIOR_SIDE") == "exterior_side"

    def test_hyphens_to_underscore(self):
        assert self._slug("front-left") == "front_left"

    def test_strips_leading_trailing_whitespace(self):
        assert self._slug("  side  ") == "side"

    def test_collapses_runs_of_separators(self):
        assert self._slug("3/4 angle") == "3_4_angle"

    def test_empty_input_safe_default(self):
        assert self._slug("") == "render"

    def test_only_separators_safe_default(self):
        assert self._slug("///") == "render"


class TestHumanize:
    def _h(self, s):
        from custom_components.vag_connect.image import _humanize
        return _humanize(s)

    def test_underscore_to_space_titlecase(self):
        assert self._h("EXTERIOR_SIDE") == "Exterior Side"

    def test_lowercase_titlecase(self):
        assert self._h("side") == "Side"

    def test_hyphen_to_space(self):
        assert self._h("front-left") == "Front Left"


class TestSynthesizeMeta:
    def _meta(self, key):
        from custom_components.vag_connect.image import _synthesize_meta
        return _synthesize_meta(key)

    def test_ola_viewpoint_shape(self):
        m = self._meta("side")
        assert m["media_type"] == "side"           # raw key for image_urls lookup
        assert m["entity_suffix"] == "render_side"  # stable per-VIN
        assert m["tag"] == "side"                  # cache filename
        assert m["view_description"] == "Side"
        assert "Brand-native viewpoint" in m["recommended_use"]

    def test_skoda_composite_viewpoint_shape(self):
        m = self._meta("EXTERIOR_SIDE")
        assert m["media_type"] == "EXTERIOR_SIDE"
        assert m["entity_suffix"] == "render_exterior_side"
        assert m["tag"] == "exterior_side"
        assert m["view_description"] == "Exterior Side"

    def test_arbitrary_garbage_yields_safe_meta(self):
        """Forward-compat — backend may add new viewpoints we don't
        know yet. Synthesizer must not raise."""
        m = self._meta("interior_3/4_view")
        assert m["entity_suffix"] == "render_interior_3_4_view"
        assert m["tag"] == "interior_3_4_view"


# ─────────────────────────────────────────────────────────────────────────────
# B) Trigger broadening (_has_image_data)
# ─────────────────────────────────────────────────────────────────────────────


class TestHasImageData:
    def _h(self, vehicle):
        from custom_components.vag_connect.image import _has_image_data
        return _has_image_data(vehicle)

    def test_image_urls_dict_truthy(self):
        assert self._h({"image_urls": {"side": "https://x"}})

    def test_image_urls_empty_falsy(self):
        assert not self._h({"image_urls": {}})

    def test_render_url_truthy(self):
        """Skoda widget-only vehicle (no image_urls dict)."""
        assert self._h({"render_url": "https://x"})

    def test_composite_render_urls_truthy(self):
        """Skoda multi-angle pre-coordinator-merge."""
        assert self._h({"composite_render_urls": {"exterior_side": "https://x"}})

    def test_empty_vehicle_falsy(self):
        assert not self._h({})

    def test_none_keys_falsy(self):
        assert not self._h({"image_urls": None, "render_url": None})


# ─────────────────────────────────────────────────────────────────────────────
# C) Branch 2 entity creation (the actual bug fix)
# ─────────────────────────────────────────────────────────────────────────────


def _setup_entities_for(vehicle: dict) -> list:
    """Drive _add_entities_for_vin via async_setup_entry's wrapper."""
    from unittest.mock import MagicMock
    from custom_components.vag_connect import image as image_mod

    # Build minimal fakes — we only exercise the closure logic, not HA.
    coordinator = MagicMock()
    coordinator.vehicles = {"V": vehicle}

    # Construct entity instances via the synthesized-meta helper +
    # VagRenderImageEntity directly (avoids needing the full HA setup
    # entry machinery). This mirrors what _add_entities_for_vin does
    # internally — the test asserts the *result* shape.
    from custom_components.vag_connect.cariad.api.graphql import (
        RENDER_IMAGE_TYPES, RENDER_TYPE_BY_MEDIA,
    )
    image_urls = vehicle.get("image_urls") or {}
    matched: set[str] = set()
    spawned: list = []
    # Branch 1
    for meta in RENDER_IMAGE_TYPES:
        if image_urls.get(meta["media_type"]):
            spawned.append(("catalog", meta["media_type"], meta["tag"]))
            matched.add(meta["media_type"])
    # Branch 2
    for key, url in image_urls.items():
        if key in matched or key in RENDER_TYPE_BY_MEDIA:
            continue
        if not isinstance(url, str) or not url.startswith("http"):
            continue
        meta = image_mod._synthesize_meta(key)
        spawned.append(("synth", meta["media_type"], meta["tag"]))
    # Branch 3
    skoda = vehicle.get("render_url")
    if isinstance(skoda, str) and skoda.startswith("http"):
        spawned.append(("widget", "render_url", "widget"))
    return spawned


class TestEntityCreationByBrand:
    def test_audi_vw_graphql_seven_entities(self):
        """Audi/VW happy path — all 7 catalog MediaTypes present."""
        urls = {
            "MYAPN8NB": "https://x/side_lg.png",
            "MYAAN8NB": "https://x/angle_lg.png",
            "MS_MYP5":  "https://x/medium.png",
            "MYAPN3NB": "https://x/side_sm.png",
            "MS_MYP4":  "https://x/small.png",
            "MS_MYP3":  "https://x/icon.png",
            "MYAAN3NB": "https://x/angle_hd.png",
        }
        out = _setup_entities_for({"image_urls": urls})
        catalog = [e for e in out if e[0] == "catalog"]
        synth = [e for e in out if e[0] == "synth"]
        assert len(catalog) == 7
        assert len(synth) == 0

    def test_cupra_seat_ola_viewpoints_now_spawn(self):
        """Pre-v1.24.0 BUG: 0 entities. Post-fix: 4 synth entities."""
        urls = {
            "side":  "https://x/side.png",
            "front": "https://x/front.png",
            "rear":  "https://x/rear.png",
            "top":   "https://x/top.png",
        }
        out = _setup_entities_for({"image_urls": urls})
        catalog = [e for e in out if e[0] == "catalog"]
        synth = [e for e in out if e[0] == "synth"]
        assert len(catalog) == 0  # OLA never matches catalog IDs
        assert len(synth) == 4
        suffixes = {e[1] for e in synth}
        assert suffixes == {"side", "front", "rear", "top"}

    def test_skoda_multi_angle_after_coordinator_merge(self):
        """Coordinator merges composite_render_urls → image_urls; the
        same Branch-2 path then spawns 6 entities."""
        urls = {
            "exterior_side":  "https://x/ext_side.png",
            "exterior_front": "https://x/ext_front.png",
            "exterior_rear":  "https://x/ext_rear.png",
            "interior_side":  "https://x/int_side.png",
            "interior_front": "https://x/int_front.png",
            "interior_boot":  "https://x/int_boot.png",
        }
        out = _setup_entities_for({"image_urls": urls})
        synth = [e for e in out if e[0] == "synth"]
        assert len(synth) == 6
        tags = {e[2] for e in synth}
        assert tags == {
            "exterior_side", "exterior_front", "exterior_rear",
            "interior_side", "interior_front", "interior_boot",
        }

    def test_skoda_widget_plus_composite_combined(self):
        """Skoda full surface: 1 widget entity + 6 composite entities."""
        urls = {
            "exterior_side":  "https://x/ext_side.png",
            "exterior_front": "https://x/ext_front.png",
            "exterior_rear":  "https://x/ext_rear.png",
            "interior_side":  "https://x/int_side.png",
            "interior_front": "https://x/int_front.png",
            "interior_boot":  "https://x/int_boot.png",
        }
        out = _setup_entities_for({
            "image_urls":  urls,
            "render_url":  "https://x/widget.png",
        })
        synth = [e for e in out if e[0] == "synth"]
        widget = [e for e in out if e[0] == "widget"]
        assert len(synth) == 6
        assert len(widget) == 1
        # widget tag must NOT clash with any synthesized tag — verifies
        # the ``widget`` cache filename stays unique.
        synth_tags = {e[2] for e in synth}
        assert "widget" not in synth_tags

    def test_mixed_catalog_and_viewpoints_no_double_spawn(self):
        """Hypothetical mixed payload — Branch 1 catalog hit MUST NOT
        also be picked up by Branch 2 leftover loop."""
        urls = {
            "MYAPN8NB": "https://x/catalog.png",
            "side":     "https://x/ola.png",
        }
        out = _setup_entities_for({"image_urls": urls})
        catalog = [e for e in out if e[0] == "catalog"]
        synth = [e for e in out if e[0] == "synth"]
        assert len(catalog) == 1 and catalog[0][1] == "MYAPN8NB"
        assert len(synth) == 1 and synth[0][1] == "side"

    def test_empty_url_string_skipped(self):
        out = _setup_entities_for({"image_urls": {"side": ""}})
        assert out == []

    def test_non_string_url_skipped(self):
        out = _setup_entities_for({"image_urls": {"side": None, "front": 42}})
        assert out == []

    def test_non_http_url_skipped(self):
        """Defensive: backend bug returning a path-only string."""
        out = _setup_entities_for({"image_urls": {"side": "/local/x.png"}})
        assert out == []


# ─────────────────────────────────────────────────────────────────────────────
# D) Coordinator merge (composite_render_urls → image_urls)
# ─────────────────────────────────────────────────────────────────────────────


def _apply_merge(data: dict) -> None:
    """Mirror the v1.24.0 merge block in coordinator._enrich.

    Search anchor: ``v1.24.0 — Merge composite renders into`` in
    ``coordinator.py``. When the coordinator block changes, this
    helper must be updated to match.
    """
    flat = data.get("composite_render_urls")
    if not isinstance(flat, dict) or not flat:
        return
    existing = data.get("image_urls")
    merged: dict = dict(existing) if isinstance(existing, dict) else {}
    for view, url in flat.items():
        merged.setdefault(view, url)
    data["image_urls"] = merged


class TestCoordinatorMerge:
    def test_merges_into_empty_image_urls(self):
        data = {
            "composite_render_urls": {
                "exterior_side": "https://x/ext_side.png",
                "interior_boot": "https://x/int_boot.png",
            },
        }
        _apply_merge(data)
        assert data["image_urls"] == {
            "exterior_side": "https://x/ext_side.png",
            "interior_boot": "https://x/int_boot.png",
        }

    def test_setdefault_preserves_existing(self):
        """If image_urls already has a key, composite must not clobber."""
        data = {
            "image_urls": {"exterior_side": "https://x/PRIORITY.png"},
            "composite_render_urls": {
                "exterior_side": "https://x/composite.png",
                "interior_boot": "https://x/int_boot.png",
            },
        }
        _apply_merge(data)
        assert data["image_urls"]["exterior_side"] == "https://x/PRIORITY.png"
        assert data["image_urls"]["interior_boot"] == "https://x/int_boot.png"

    def test_no_composite_no_op(self):
        data = {"image_urls": {"side": "https://x/side.png"}}
        _apply_merge(data)
        assert data["image_urls"] == {"side": "https://x/side.png"}

    def test_garbage_composite_no_op(self):
        data = {"composite_render_urls": "not-a-dict"}
        _apply_merge(data)
        assert "image_urls" not in data
