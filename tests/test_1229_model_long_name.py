# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#1229 — device model prefers the richest MEDIA long name, consistently across
brands. The marketing long name ("Audi Q4 50 e-tron quattro") beats a garage
nickname / carModel / bare brand. It arrives either on the vgql image fetch
(_image_data.long_name, VW/Audi) or as media_long_name (SEAT/CUPRA); the resolver
in coordinator._enrich unifies both plus a media-short and brand-model fallback.
"""
from __future__ import annotations

import asyncio
import threading
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from custom_components.vag_connect.coordinator import VagConnectCoordinator


def _make_coord(image_data=None):
    coord = VagConnectCoordinator.__new__(VagConnectCoordinator)
    coord.hass = MagicMock()
    coord.hass.async_add_executor_job = AsyncMock(return_value=None)
    coord.entry = MagicMock()
    coord.entry.data = {"brand": "audi", "username": "t@t.com", "password": "x",
                        "spin": "", "update_interval": 300}
    coord._vehicles_lock = threading.Lock()
    coord._cariad_client = MagicMock()
    coord._cariad_client._image_data = image_data if image_data is not None else {}
    coord.vehicle_static_info = {}
    coord._was_available = True
    coord.data = None
    return coord


def _enrich(coord, data):
    data.setdefault("latitude", None)
    data.setdefault("longitude", None)
    return asyncio.run(coord._enrich(data))


class TestModelLongName:
    def test_vgql_long_name_wins_over_nickname(self) -> None:
        # VW/Audi: the vgql media.longName beats the carModel/nickname already set.
        coord = _make_coord({"V1": SimpleNamespace(
            long_name="Audi Q4 50 e-tron quattro", short_name="Q4 e-tron",
            model_year=2024)})
        out = _enrich(coord, {"vin": "V1", "model": "Q4"})
        assert out["model"] == "Audi Q4 50 e-tron quattro"
        assert out["model_year"] == 2024

    def test_media_long_name_field_wins_seat_cupra(self) -> None:
        # SEAT/CUPRA set media_long_name from their own image fetch (no _image_data).
        coord = _make_coord()
        out = _enrich(coord, {"vin": "V1", "media_long_name": "CUPRA Born 58 kWh",
                              "model": "Born"})
        assert out["model"] == "CUPRA Born 58 kWh"

    def test_media_long_beats_vgql_short(self) -> None:
        coord = _make_coord({"V1": SimpleNamespace(
            long_name=None, short_name="Q4", model_year=None)})
        out = _enrich(coord, {"vin": "V1", "media_long_name": "Audi Q4 e-tron",
                              "model": "Z"})
        assert out["model"] == "Audi Q4 e-tron"

    def test_falls_back_to_brand_model_when_no_media(self) -> None:
        # Skoda etc: no media name, keep the spec model already set.
        coord = _make_coord()
        out = _enrich(coord, {"vin": "V1", "model": "Octavia Combi iV Style"})
        assert out["model"] == "Octavia Combi iV Style"

    def test_short_name_used_when_no_long(self) -> None:
        coord = _make_coord({"V1": SimpleNamespace(
            long_name=None, short_name="e-tron GT", model_year=None)})
        out = _enrich(coord, {"vin": "V1", "model": ""})
        assert out["model"] == "e-tron GT"
