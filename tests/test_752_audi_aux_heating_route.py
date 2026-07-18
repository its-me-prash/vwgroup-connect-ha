# Copyright 2026 Prash Balan (@its-me-prash) - Apache License 2.0
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#752 — Audi / VW-EU auxiliary heating (Standheizung) route + payload fix.

heyensh-sys's Audi returned HTTP 404 for aux-heating on the CARIAD BFF. The
resource is spelled ``auxiliaryheating`` (one word — the same as the read field
``auxiliaryHeating``); our write path used the hyphenated ``auxiliary-heating``
on v1 AND v2, which does not resolve. The body is the minimal
``{duration_min, spin}`` a working myAudi client sends, not the old
``{command, duration_in_min, target_temperature_in_kelvin}`` guess. There was no
VW-EU/Audi aux-heating test before (the existing ones cover SEAT/CUPRA), which
is why the hyphen slipped through.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

from custom_components.vag_connect.cariad.api.vw_eu import VWEUClient


def _client() -> VWEUClient:
    client = VWEUClient.__new__(VWEUClient)
    client._tokens = None
    client._post = AsyncMock(return_value=None)
    client._v2_command_paths = {}
    client._spin = "1234"
    client._mbb_command_target = lambda: None  # non-MBB → hits the CARIAD BFF
    return client


def test_start_uses_one_word_path_not_hyphenated() -> None:
    client = _client()
    asyncio.run(client.command_start_aux_heating("VINX", duration_min=30))
    url = client._post.call_args[0][0]
    assert "/vehicle/v1/vehicles/VINX/auxiliaryheating/start" in url
    assert "auxiliary-heating" not in url  # the old 404 spelling is gone


def test_start_body_is_min_duration_plus_spin() -> None:
    client = _client()
    asyncio.run(client.command_start_aux_heating("VINX", duration_min=30))
    body = client._post.call_args.kwargs["json"]
    assert body == {"duration_min": 30, "spin": "1234"}


def test_start_omits_spin_when_unset() -> None:
    client = _client()
    client._spin = ""
    asyncio.run(client.command_start_aux_heating("VINX", duration_min=45))
    assert client._post.call_args.kwargs["json"] == {"duration_min": 45}


def test_stop_one_word_path_empty_body() -> None:
    client = _client()
    asyncio.run(client.command_stop_aux_heating("VINX"))
    url = client._post.call_args[0][0]
    assert "/vehicle/v1/vehicles/VINX/auxiliaryheating/stop" in url
    assert client._post.call_args.kwargs["json"] == {}
