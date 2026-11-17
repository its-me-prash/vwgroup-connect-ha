# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#2164 — the official Škoda API's ``UNKNOWN`` lock state stays unknown.

@matroeh found that ``SkodaOfficialClient._parse_vehicle`` turned every
``doorsLocked`` string other than ``YES`` into ``doors_locked = False``, the
documented ``UNKNOWN`` ("the system cannot determine the state") included.
The live overlay (``coordinator._merge_official_live``) skips ``None`` but
not ``False``, so an unknown official answer overwrote a known "locked" from
the primary channel and the lock entity showed the car unlocked.

``NO`` and ``OPENED`` still mean not locked; anything else is left ``None``,
which the overlay leaves alone.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any

import pytest

_VIN = "TMBZZZ00000000000"


def _parse(value: Any) -> Any:
    from custom_components.vag_connect.cariad.api.skoda_official import SkodaOfficialClient

    return SkodaOfficialClient._parse_vehicle(_VIN, {"status": {"overall": {"doorsLocked": value}}})


@pytest.mark.parametrize(
    ("value", "expect"),
    [("YES", True), ("NO", False), ("OPENED", False), (" yes ", True),
     ("UNKNOWN", None), ("SOMETHING_NEW", None), ("", None)],
)
def test_parse_maps_only_the_known_states(value: str, expect: bool | None) -> None:
    assert _parse(value).doors_locked is expect


def test_the_locked_alias_is_read_the_same_way() -> None:
    from custom_components.vag_connect.cariad.api.skoda_official import SkodaOfficialClient

    d = SkodaOfficialClient._parse_vehicle(_VIN, {"status": {"overall": {"locked": "UNKNOWN"}}})
    assert d.doors_locked is None


def _overlay(official_value: str, primary: bool | None) -> dict[str, Any]:
    from custom_components.vag_connect.coordinator import VagConnectCoordinator

    official = _parse(official_value)

    async def _read(_vin: str) -> Any:
        return official

    fake = SimpleNamespace(_cariad_client=SimpleNamespace(official_live_read=_read))
    enriched: dict[str, Any] = {"doors_locked": primary, "field_sources": {"doors_locked": "skoda"}}
    asyncio.new_event_loop().run_until_complete(
        VagConnectCoordinator._merge_official_live(fake, _VIN, enriched)  # type: ignore[arg-type]
    )
    return enriched


@pytest.mark.parametrize("primary", [True, False, None])
def test_an_unknown_official_state_does_not_overwrite_the_primary(primary: bool | None) -> None:
    out = _overlay("UNKNOWN", primary)
    assert out["doors_locked"] is primary
    assert out["field_sources"]["doors_locked"] == "skoda"


def test_a_known_official_state_still_wins() -> None:
    out = _overlay("NO", True)
    assert out["doors_locked"] is False
    assert out["field_sources"]["doors_locked"] == "skoda_official"
