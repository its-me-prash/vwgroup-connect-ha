# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""2.31.0 wave — per-location target SoC + seat-heating services (HA wiring)."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

import pytest

import yaml

VIN = "TMBJJ7NX1M0000002"
_ROOT = Path(__file__).resolve().parents[1] / "custom_components/vag_connect"


def _coord():
    from custom_components.vag_connect.coordinator import VagConnectCoordinator

    c = VagConnectCoordinator.__new__(VagConnectCoordinator)
    c._cariad_cmd = AsyncMock()
    return c


@pytest.mark.asyncio
async def test_profile_target_soc_dispatch() -> None:
    c = _coord()
    await c.async_set_profile_target_soc(VIN, 2, 90)
    args, kwargs = c._cariad_cmd.call_args
    assert args[:2] == (VIN, "command_set_profile_target_soc")
    assert kwargs == {"profile_id": 2, "target": 90}


@pytest.mark.asyncio
async def test_seat_heating_dispatch_passes_only_given_seats() -> None:
    c = _coord()
    await c.async_set_seat_heating(VIN, front_left=True)
    _, kwargs = c._cariad_cmd.call_args
    # all four seats are forwarded (client sends only the non-None ones)
    assert kwargs == {
        "front_left": True, "front_right": None,
        "rear_left": None, "rear_right": None,
    }


def test_both_services_are_in_services_yaml() -> None:
    doc = yaml.safe_load((_ROOT / "services.yaml").read_text(encoding="utf-8"))
    assert "set_location_target_soc" in doc
    assert "set_seat_heating" in doc
    # required fields declared
    assert doc["set_location_target_soc"]["fields"]["profile_id"]["required"] is True


def test_both_services_are_registered() -> None:
    src = (_ROOT / "__init__.py").read_text(encoding="utf-8")
    assert '"set_location_target_soc"' in src
    assert '"set_seat_heating"' in src
