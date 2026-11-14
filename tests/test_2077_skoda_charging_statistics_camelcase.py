# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#2077 (@matroeh) part 2 — Škoda charging statistics: camelCase body + string values.

Established by the reporter's live response (with the duplicate timeout gone):
snake_case request keys returned HTTP 404, camelCase returned data;
``primaryValue`` is a formatted string such as ``"~ 16 kWh"``; session details
sit under ``details`` (incl. ``chargingPowerType``), there is no
``sessionDetails`` object. Field names follow myskoda PR #586
(``ChargingStatisticsRequest`` aliases, ``ChargingStatisticsSessionDetails``).
"""
from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import MagicMock

from custom_components.vag_connect.cariad.api.skoda import SkodaClient

VIN = "TMBJJ7NX1M0000009"

_CAMEL = {
    "startedAfter", "startedBefore", "selectedFilterOptions",
    "capabilities", "fetchFilterOptions",
}


def _client(stats: dict[str, Any]) -> SkodaClient:
    c = SkodaClient(MagicMock(), "u@t.de", "pw")

    async def _get(_url: str, **_kw: Any) -> Any:
        return {}

    async def _stats(_vin: str, *_a: Any, **_k: Any) -> dict[str, Any]:
        return stats

    c._get = _get  # type: ignore[method-assign]
    c.get_charging_statistics = _stats  # type: ignore[method-assign]
    return c


def _status(entries: list[dict[str, Any]]) -> Any:
    stats = {"monthSections": [{"title": "x", "entries": entries}]}
    return asyncio.run(_client(stats).get_status(VIN))


def _e(primary: Any, details: dict[str, Any] | None = None, key: str = "details") -> dict[str, Any]:
    e: dict[str, Any] = {"primaryValue": primary}
    if details is not None:
        e[key] = details
    return e


def test_a_request_body_is_camelcase_only() -> None:
    c = SkodaClient(MagicMock(), "u@t.de", "pw")
    seen: dict[str, Any] = {}

    async def _request(method: str, url: str, **kw: Any) -> Any:
        seen["method"], seen["url"], seen["json"] = method, url, kw.get("json")
        return {}

    c._request = _request  # type: ignore[method-assign]
    asyncio.run(c.get_charging_statistics(VIN))
    body = seen["json"]
    assert seen["method"] == "POST"
    assert set(body) == _CAMEL
    assert not any("_" in k for k in body)
    assert body["selectedFilterOptions"] == [{"filterType": "VEHICLE", "vin": VIN}]
    assert body["capabilities"] == []
    assert body["fetchFilterOptions"] is True
    assert isinstance(body["startedAfter"], str) and isinstance(body["startedBefore"], str)
    assert not any("_" in k for k in body["selectedFilterOptions"][0])


def test_b_string_primary_values_sum() -> None:
    d = _status([_e("~ 16 kWh"), _e("≈ 7,5 kWh"), _e("12.25 kWh")])
    assert d.total_charged_energy_kwh == 35.75


def test_c_old_value_unit_object_still_sums() -> None:
    d = _status([_e({"value": 12.5, "unit": "kWh"}), _e({"value": 7.5, "unit": "kWh"})])
    assert d.total_charged_energy_kwh == 20.0
    assert d.last_charging_session_kwh == 12.5


def test_d_junk_strings_add_nothing() -> None:
    d = _status([_e("n/a"), _e("16 km"), _e("1.234,5 kWh"), _e("~~ 3 kWh"), _e("5 kWh extra")])
    assert d.total_charged_energy_kwh is None
    # junk next to a good one: only the good one counts
    d2 = _status([_e("n/a"), _e("1.234,5 kWh"), _e("10 kWh")])
    assert d2.total_charged_energy_kwh == 10.0


def test_d2_three_fraction_digits_are_ambiguous_and_add_nothing() -> None:
    """"1,234 kWh" is 1.234 in one locale and 1234 in another — so it is neither."""
    d = _status([_e("1,234 kWh"), _e("12.345 kWh")])
    assert d.total_charged_energy_kwh is None
    # one and two fraction digits are unambiguous and still count
    d2 = _status([_e("7,5 kWh"), _e("12.25 kWh"), _e("1,234 kWh")])
    assert d2.total_charged_energy_kwh == 19.75


def test_d3_left_out_entries_are_counted_in_the_debug_log(caplog: Any) -> None:
    """A total that silently skips entries reads as complete when it is not."""
    import logging

    with caplog.at_level(logging.DEBUG, logger="custom_components.vag_connect.cariad.api.skoda"):
        d = _status([_e("10 kWh"), _e("n/a"), _e("1,234 kWh")])
    assert d.total_charged_energy_kwh == 10.0
    lines = [r.getMessage() for r in caplog.records if "left out of the total" in r.getMessage()]
    assert len(lines) == 1
    assert "2 of 3 entries" in lines[0]
    assert "1,234" not in lines[0] and "n/a" not in lines[0], "counts only, never the values"


def test_e_charging_power_type_from_details() -> None:
    d = _status([_e("~ 17 kWh", {"chargingPowerType": "AC"})])
    assert d.last_charging_session_current_type == "AC"
    assert d.last_charging_session_kwh == 17.0
    # legacy shape keeps working
    d2 = _status([_e({"value": 1, "unit": "kWh"}, {"currentType": "dc"}, key="sessionDetails")])
    assert d2.last_charging_session_current_type == "DC"


def test_f_live_shape_does_not_guess_a_start_time_or_a_duration() -> None:
    """The live shape carries start and duration only as display text.

    ``secondaryValue`` is a string such as "8h 16min", and the start is a
    locale-formatted local time with no zone. Neither is parsed: a guessed zone
    would put a wrong time on the sensor. The read must still not raise on
    those strings, and the energy and the AC/DC type must still fill.
    """
    d = _status([
        {
            "primaryValue": "~ 17 kWh",
            "secondaryValue": "8h 16min",
            "details": {
                "chargingPowerType": "AC",
                "formattedChargingStartTime": "10/06/2026, 05:14",
            },
        },
    ])
    assert d.last_charging_session_kwh == 17.0
    assert d.last_charging_session_current_type == "AC"
    assert d.last_charging_session_duration_min is None
    assert d.last_charging_session_start is None
    assert d.recent_charging_sessions == [
        {"started_at": None, "kwh": 17.0, "duration_min": None},
    ]
