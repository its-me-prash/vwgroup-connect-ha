# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for v1.22.x foundation — multi-angle Skoda renders.

Adopts ``GET /api/v1/vehicle-information/{vin}/renders`` per myskoda
PR #571 (merged 2026-05-02T21:12:05Z, endpoint marked verified ✅
upstream). Foundation only — adds API method, gather entry, parser
+ cache wiring. Image-platform entity expansion deferred to next
MINOR (would add ~6 new ImageEntity per Skoda VIN).

Verified response shape (from PR #571 example payload, Enyaq 2021):

    {
      "renders": [],
      "compositeRenders": [
        {
          "layers": [
            {"url": "https://...png", "viewPoint": "EXTERIOR_SIDE",
             "type": "REAL", "order": 0}
          ],
          "viewType": "UNMODIFIED_EXTERIOR_SIDE"
        },
        ...
      ]
    }

Six view points observed in fixture: EXTERIOR_{SIDE,FRONT,REAR},
INTERIOR_{SIDE,FRONT,BOOT}.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest


# Shared fixture mimicking the upstream Enyaq 2021 example payload.
_RENDERS_PAYLOAD: dict[str, Any] = {
    "renders": [],
    "compositeRenders": [
        {
            "layers": [
                {
                    "url": "https://iprenders.example/ext_side.png",
                    "viewPoint": "EXTERIOR_SIDE",
                    "type": "REAL",
                    "order": 0,
                },
            ],
            "viewType": "UNMODIFIED_EXTERIOR_SIDE",
        },
        {
            "layers": [
                {
                    "url": "https://iprenders.example/ext_front.png",
                    "viewPoint": "EXTERIOR_FRONT",
                    "type": "REAL",
                    "order": 0,
                },
            ],
            "viewType": "UNMODIFIED_EXTERIOR_FRONT",
        },
        {
            "layers": [
                {
                    "url": "https://iprenders.example/ext_rear.png",
                    "viewPoint": "EXTERIOR_REAR",
                    "type": "REAL",
                    "order": 0,
                },
            ],
            "viewType": "UNMODIFIED_EXTERIOR_REAR",
        },
        {
            "layers": [
                {
                    "url": "https://iprenders.example/int_side.png",
                    "viewPoint": "INTERIOR_SIDE",
                    "type": "REAL",
                    "order": 0,
                },
            ],
            "viewType": "UNMODIFIED_INTERIOR_SIDE",
        },
        {
            "layers": [
                {
                    "url": "https://iprenders.example/int_front.png",
                    "viewPoint": "INTERIOR_FRONT",
                    "type": "REAL",
                    "order": 0,
                },
            ],
            "viewType": "UNMODIFIED_INTERIOR_FRONT",
        },
        {
            "layers": [
                {
                    "url": "https://iprenders.example/int_boot.png",
                    "viewPoint": "INTERIOR_BOOT",
                    "type": "REAL",
                    "order": 0,
                },
            ],
            "viewType": "UNMODIFIED_INTERIOR_BOOT",
        },
    ],
}


# ─────────────────────────────────────────────────────────────────────────────
# A) Model field present
# ─────────────────────────────────────────────────────────────────────────────


class TestModelField:
    def test_composite_render_urls_field_exists(self):
        from custom_components.vag_connect.cariad.models import VehicleData
        d = VehicleData(vin="V")
        assert hasattr(d, "composite_render_urls")
        assert d.composite_render_urls is None

    def test_composite_render_urls_assignable(self):
        from custom_components.vag_connect.cariad.models import VehicleData
        d = VehicleData(vin="V")
        d.composite_render_urls = {"exterior_side": "https://x"}
        assert d.composite_render_urls == {"exterior_side": "https://x"}


# ─────────────────────────────────────────────────────────────────────────────
# B) API method present + best-effort
# ─────────────────────────────────────────────────────────────────────────────


class TestSkodaApiMethod:
    @pytest.mark.asyncio
    async def test_get_vehicle_renders_happy(self):
        from custom_components.vag_connect.cariad.api.skoda import SkodaClient
        client = SkodaClient.__new__(SkodaClient)
        client._get = AsyncMock(return_value=_RENDERS_PAYLOAD)  # type: ignore[method-assign]
        out = await client.get_vehicle_renders("V")
        assert out == _RENDERS_PAYLOAD
        client._get.assert_awaited_once()
        url = client._get.await_args.args[0]
        assert url.endswith("/api/v1/vehicle-information/V/renders")

    @pytest.mark.asyncio
    async def test_get_vehicle_renders_404_returns_empty(self):
        from custom_components.vag_connect.cariad.api.skoda import SkodaClient
        client = SkodaClient.__new__(SkodaClient)
        client._get = AsyncMock(side_effect=Exception("404"))  # type: ignore[method-assign]
        out = await client.get_vehicle_renders("V")
        assert out == {}

    @pytest.mark.asyncio
    async def test_get_vehicle_renders_garbage_returns_empty(self):
        from custom_components.vag_connect.cariad.api.skoda import SkodaClient
        client = SkodaClient.__new__(SkodaClient)
        client._get = AsyncMock(return_value="not-a-dict")  # type: ignore[method-assign]
        out = await client.get_vehicle_renders("V")
        assert out == {}


# ─────────────────────────────────────────────────────────────────────────────
# C) Static-info gather includes renders
# ─────────────────────────────────────────────────────────────────────────────


class TestGatherIntegration:
    @pytest.mark.asyncio
    async def test_static_info_includes_renders_key(self):
        from custom_components.vag_connect.cariad.api.skoda import SkodaClient
        client = SkodaClient.__new__(SkodaClient)
        client.get_vehicle_info = AsyncMock(return_value={"model": "Enyaq"})  # type: ignore[method-assign]
        client.get_vehicle_equipment = AsyncMock(return_value={"equipment": []})  # type: ignore[method-assign]
        client.get_vehicle_renders = AsyncMock(return_value=_RENDERS_PAYLOAD)  # type: ignore[method-assign]
        out = await client.get_vehicle_static_info("V")
        assert "renders" in out
        assert out["renders"] == _RENDERS_PAYLOAD

    @pytest.mark.asyncio
    async def test_static_info_omits_renders_when_empty(self):
        """404 / empty → key omitted (not present as ``{}``)."""
        from custom_components.vag_connect.cariad.api.skoda import SkodaClient
        client = SkodaClient.__new__(SkodaClient)
        client.get_vehicle_info = AsyncMock(return_value={"model": "Enyaq"})  # type: ignore[method-assign]
        client.get_vehicle_equipment = AsyncMock(return_value={"equipment": []})  # type: ignore[method-assign]
        client.get_vehicle_renders = AsyncMock(return_value={})  # type: ignore[method-assign]
        out = await client.get_vehicle_static_info("V")
        assert "renders" not in out

    @pytest.mark.asyncio
    async def test_static_info_renders_failure_does_not_block_others(self):
        """An exception inside renders fetch must not break info/equip."""
        from custom_components.vag_connect.cariad.api.skoda import SkodaClient
        client = SkodaClient.__new__(SkodaClient)
        client.get_vehicle_info = AsyncMock(return_value={"model": "Enyaq"})  # type: ignore[method-assign]
        client.get_vehicle_equipment = AsyncMock(return_value={"equipment": []})  # type: ignore[method-assign]
        client.get_vehicle_renders = AsyncMock(side_effect=RuntimeError("boom"))  # type: ignore[method-assign]
        out = await client.get_vehicle_static_info("V")
        # info/equipment still present; renders absent
        assert out.get("info") == {"model": "Enyaq"}
        assert "renders" not in out


# ─────────────────────────────────────────────────────────────────────────────
# D) Parser — defensive against shape variations
# ─────────────────────────────────────────────────────────────────────────────


def _parse_composite_renders(static: dict[str, Any]) -> dict[str, str] | None:
    """Mirror of the parser block in coordinator._enrich.

    Tests the exact same flat-dict construction logic used at runtime —
    when the parser is updated, both the runtime branch and this test
    helper must be kept in sync (search anchor: ``v1.22.x foundation``
    in ``coordinator.py``).
    """
    renders = static.get("renders") or {}
    if not isinstance(renders, dict):
        return None
    composites = renders.get("compositeRenders")
    if not isinstance(composites, list) or not composites:
        return None
    flat: dict[str, str] = {}
    for entry in composites:
        if not isinstance(entry, dict):
            continue
        layers = entry.get("layers")
        if not isinstance(layers, list) or not layers:
            continue
        real_layers = [
            layer for layer in layers
            if isinstance(layer, dict)
            and layer.get("type") == "REAL"
            and isinstance(layer.get("url"), str)
            and isinstance(layer.get("viewPoint"), str)
        ]
        if not real_layers:
            continue
        base = min(
            real_layers,
            key=lambda layer: layer.get("order", 0)
            if isinstance(layer.get("order"), int) else 0,
        )
        view = base["viewPoint"].lower()
        flat[view] = base["url"]
    return flat or None


class TestParser:
    def test_six_views_extracted(self):
        out = _parse_composite_renders({"renders": _RENDERS_PAYLOAD})
        assert out is not None
        assert set(out.keys()) == {
            "exterior_side", "exterior_front", "exterior_rear",
            "interior_side", "interior_front", "interior_boot",
        }
        assert out["exterior_side"] == "https://iprenders.example/ext_side.png"

    def test_empty_composites_returns_none(self):
        out = _parse_composite_renders({"renders": {"compositeRenders": []}})
        assert out is None

    def test_missing_renders_key_returns_none(self):
        out = _parse_composite_renders({})
        assert out is None

    def test_skips_non_real_layer_types(self):
        payload = {
            "renders": {
                "compositeRenders": [
                    {
                        "layers": [
                            {"url": "https://x", "viewPoint": "EXTERIOR_SIDE",
                             "type": "GENERATED", "order": 0},
                        ],
                    },
                ],
            },
        }
        # No REAL layers → no entries
        assert _parse_composite_renders(payload) is None

    def test_picks_lowest_order_when_multiple_real_layers(self):
        payload = {
            "renders": {
                "compositeRenders": [
                    {
                        "layers": [
                            {"url": "https://overlay", "viewPoint": "EXTERIOR_SIDE",
                             "type": "REAL", "order": 5},
                            {"url": "https://base", "viewPoint": "EXTERIOR_SIDE",
                             "type": "REAL", "order": 0},
                        ],
                    },
                ],
            },
        }
        out = _parse_composite_renders(payload)
        assert out == {"exterior_side": "https://base"}

    def test_tolerates_malformed_entries(self):
        """Backend hiccups: non-dict entries, missing fields, garbage."""
        payload = {
            "renders": {
                "compositeRenders": [
                    "not-a-dict",
                    {"layers": "not-a-list"},
                    {"layers": []},
                    {"layers": [{"no_url_key": True}]},
                    {"layers": [{"url": 42, "viewPoint": "EXTERIOR_SIDE",
                                 "type": "REAL"}]},  # url not string
                    {"layers": [{"url": "https://ok",
                                 "viewPoint": "EXTERIOR_FRONT",
                                 "type": "REAL", "order": 0}]},
                ],
            },
        }
        out = _parse_composite_renders(payload)
        assert out == {"exterior_front": "https://ok"}

    def test_lowercases_viewpoint(self):
        payload = {
            "renders": {
                "compositeRenders": [
                    {"layers": [{"url": "https://x",
                                 "viewPoint": "EXTERIOR_SIDE",
                                 "type": "REAL", "order": 0}]},
                ],
            },
        }
        out = _parse_composite_renders(payload)
        assert out is not None
        assert "exterior_side" in out
        assert "EXTERIOR_SIDE" not in out

    def test_renders_not_a_dict_returns_none(self):
        out = _parse_composite_renders({"renders": "garbage"})
        assert out is None
