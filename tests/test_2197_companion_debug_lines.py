# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#2197 / #968 — a companion read that finds nothing now says so at DEBUG.

The parking-position read keeps only a Google Maps link out of the shared text.
When the share preview holds something else, no value came out and nothing was
logged. The climate, departure and charge-target steps had no logging at all.
The lines log facts and counts only, never screen text or a coordinate.
"""
from __future__ import annotations

import asyncio
import logging

from custom_components.vag_connect.companion.channel import CompanionChannel
from custom_components.vag_connect.companion.charge_target import find_charge_target_row
from custom_components.vag_connect.companion.climate import ClimateController
from custom_components.vag_connect.companion.departure import (
    departure_rows,
    read_timer_details,
)
from custom_components.vag_connect.companion.presets import PRESETS
from custom_components.vag_connect.companion.screen import UiNode

VW = PRESETS["volkswagen"]
PARKING = next(n for n in VW.nav_reads if n.name == "parking_position")
SECRET = "Teststrasse 12 47.123456, 8.654321"
_PKG = "custom_components.vag_connect.companion"


def _text(text: str) -> UiNode:
    return UiNode("", "", text, "android.widget.TextView", False, (0, 0, 100, 50))


def _channel() -> CompanionChannel:
    return CompanionChannel(object(), VW, time_fn=lambda: 0)


def test_empty_parking_read_logs_the_fact_and_the_length_only(caplog) -> None:
    caplog.set_level(logging.DEBUG)
    fields: dict = {}
    _channel()._apply_nav_values(PARKING, [_text(SECRET), _text("Share")], fields)
    lines = [r.getMessage() for r in caplog.records if "parking_position" in r.getMessage()]
    assert len(lines) == 1
    assert "no Maps link" in lines[0]
    assert str(len(SECRET)) in lines[0]
    assert "47.12" not in caplog.text and "Teststrasse" not in caplog.text
    assert fields == {}


def test_a_maps_link_logs_nothing(caplog) -> None:
    caplog.set_level(logging.DEBUG)
    fields: dict = {}
    _channel()._apply_nav_values(PARKING, [_text("https://www.google.com/maps?q=47.1,8.6")], fields)
    assert "no Maps link" not in caplog.text
    assert fields["latitude"] == 47.1


def test_other_nav_reads_are_not_logged_as_parking(caplog) -> None:
    caplog.set_level(logging.DEBUG)
    other = next(n for n in VW.nav_reads if n.name != "parking_position" and n.values)
    _channel()._apply_nav_values(other, [], {})
    assert "no Maps link" not in caplog.text


def test_charge_target_step_logs_when_the_row_is_missing(caplog) -> None:
    caplog.set_level(logging.DEBUG, logger=f"{_PKG}.charge_target")
    assert find_charge_target_row([_text("hello")]) is None
    msgs = [r.getMessage() for r in caplog.records]
    assert len(msgs) == 1 and "charge target" in msgs[0] and "hello" not in msgs[0]


def test_departure_steps_log_their_counts(caplog) -> None:
    caplog.set_level(logging.DEBUG, logger=f"{_PKG}.departure")
    assert departure_rows([_text("hello")]) == []
    assert read_timer_details([_text("hello")], 1) == {}
    msgs = [r.getMessage() for r in caplog.records]
    assert len(msgs) == 2
    assert all("departure" in m and "hello" not in m for m in msgs)


def test_climate_sheet_step_logs(caplog) -> None:
    caplog.set_level(logging.DEBUG, logger=f"{_PKG}.climate")
    ch = _channel()
    ctrl = ClimateController(ch)

    async def _gate() -> None:
        return None

    async def _dump(*_a: object, **_k: object) -> tuple[list[UiNode], bool]:
        return [_text("hello")], True

    async def _back(*_a: object, **_k: object) -> None:
        return None

    ctrl._gate = _gate  # type: ignore[method-assign]
    ch._dump_and_clear_overlays = _dump  # type: ignore[method-assign]
    ch._require_limit_language = lambda nodes: None  # type: ignore[method-assign]
    ch._return_to_overview = _back  # type: ignore[method-assign]

    async def run() -> None:
        try:
            async with ctrl._on_sheet():
                pass
        except Exception:  # noqa: BLE001
            pass

    asyncio.run(run())
    msgs = [r.getMessage() for r in caplog.records]
    assert any("climate" in m and "tile" in m for m in msgs)
    assert not any("hello" in m for m in msgs)
