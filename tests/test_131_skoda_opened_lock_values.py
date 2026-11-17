# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#131 — Skoda lock status ``OPENED`` / ``TRUNK_OPENED`` is a known value.

The official spec lists ``YES | NO | OPENED | TRUNK_OPENED | UNKNOWN`` for
``overall.doorsLocked``; ``YES`` means every supported door AND the trunk are
locked and closed. ``OPENED`` and ``TRUNK_OPENED`` therefore mean "not fully
locked" (``skoda_official`` already maps everything but ``YES`` to False).
The mysmob parser logged them as unknown and left ``doors_locked`` as None.

The tests drive ``SkodaClient.get_status`` with a payload, not the source.
"""
from __future__ import annotations

import asyncio
import logging
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.vag_connect.cariad.api.skoda import SkodaClient
from custom_components.vag_connect.cariad.models import VehicleData

_VIN = "WVWZZZAUZFW000000"


def _run(overall: dict) -> VehicleData:
    c = SkodaClient(MagicMock(), "u@t.de", "pw")
    c._powertrain = {}
    c._official_mode = "mysmob_only"
    c._eu_portal = None

    async def fake_get(url: str, *a: object, **k: object) -> dict:
        if url.endswith(f"/api/v2/vehicle-status/{_VIN}"):
            return {"overall": overall}
        return {}

    c._get = AsyncMock(side_effect=fake_get)  # type: ignore[method-assign]
    return asyncio.run(c.get_status(_VIN))


@pytest.mark.parametrize("value", ["OPENED", "TRUNK_OPENED", "trunk_opened"])
def test_opened_values_mean_not_locked(value: str) -> None:
    assert _run({"doorsLocked": value}).doors_locked is False


def test_opened_values_are_not_logged_as_unknown(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.INFO):
        _run({"doorsLocked": "TRUNK_OPENED"})
    assert "unknown value" not in caplog.text


def test_yes_still_locked_and_no_still_unlocked() -> None:
    assert _run({"doorsLocked": "YES"}).doors_locked is True
    assert _run({"doorsLocked": "NO"}).doors_locked is False


def test_unknown_stays_none() -> None:
    assert _run({"doorsLocked": "UNKNOWN"}).doors_locked is None
