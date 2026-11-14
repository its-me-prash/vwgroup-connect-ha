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


def _kwhs(d: Any) -> list[Any]:
    """Per-session energy as the parser read it, newest first."""
    return [s["kwh"] for s in d.recent_charging_sessions]


def test_b_string_primary_values_are_read_per_session() -> None:
    d = _status([_e("~ 16 kWh"), _e("≈ 7,5 kWh"), _e("12.25 kWh")])
    assert _kwhs(d) == [16.0, 7.5, 12.25]
    assert d.last_charging_session_kwh == 16.0


def test_c_old_value_unit_object_is_still_read() -> None:
    d = _status([_e({"value": 12.5, "unit": "kWh"}), _e({"value": 7.5, "unit": "kWh"})])
    assert _kwhs(d) == [12.5, 7.5]
    assert d.last_charging_session_kwh == 12.5


def test_c2_an_object_counts_as_energy_only_with_a_kwh_unit() -> None:
    """The per-session list and the last-session value read through one reader.

    Before, the list took ``value`` from any object, so a duration in minutes
    or a bare ``True`` would have been listed as kWh while the last-session
    value rejected the same entry.
    """
    d = _status([
        _e({"value": 45, "unit": "MINUTES"}),
        _e({"value": True, "unit": "kWh"}),
        _e({"value": 9}),
        _e({"value": 12.5, "unit": "kWh"}),
    ])
    assert _kwhs(d) == [None, None, None, 12.5]
    assert d.last_charging_session_kwh is None


def test_d_junk_strings_are_not_read_as_energy() -> None:
    d = _status([
        _e("n/a"), _e("16 km"), _e("1.234,5 kWh"), _e("~~ 3 kWh"), _e("5 kWh extra"),
        _e("10 kWh"),
    ])
    assert _kwhs(d) == [None, None, None, None, None, 10.0]
    assert d.last_charging_session_kwh is None, (
        "the newest entry is unreadable, so there is no last-session energy — "
        "not the next readable one passed off as the last"
    )


def test_d2_three_fraction_digits_are_ambiguous_and_not_read() -> None:
    """"1,234 kWh" is 1.234 in one locale and 1234 in another — so it is neither."""
    d = _status([_e("1,234 kWh"), _e("12.345 kWh"), _e("7,5 kWh"), _e("12.25 kWh")])
    # one and two fraction digits are unambiguous; three are not
    assert _kwhs(d) == [None, None, 7.5, 12.25]


def test_d3_no_total_is_published_from_the_90_day_window() -> None:
    """A sum over a trailing window is not a lifetime counter.

    ``total_charged_energy_kwh`` feeds a TOTAL_INCREASING energy sensor, and the
    cache clamps it so it cannot fall. A 90-day sum would therefore rise once
    and then stall near its peak while sessions age out as fast as new ones
    arrive — the Energy dashboard would record almost no charging. So the
    sessions are read and the total is left alone, in either response shape.
    """
    d = _status([_e("~ 16 kWh"), _e("~ 20 kWh"), _e({"value": 12.5, "unit": "kWh"})])
    assert d.total_charged_energy_kwh is None
    assert _kwhs(d) == [16.0, 20.0, 12.5], "the sessions themselves are still read"


def test_d4_the_request_asks_for_a_trailing_window_not_a_lifetime() -> None:
    """The fact the test above rests on: the body spans 90 days ending today."""
    from datetime import date

    c = SkodaClient(MagicMock(), "u@t.de", "pw")
    seen: dict[str, Any] = {}

    async def _request(_method: str, _url: str, **kw: Any) -> Any:
        seen["json"] = kw.get("json")
        return {}

    c._request = _request  # type: ignore[method-assign]
    asyncio.run(c.get_charging_statistics(VIN))
    after = date.fromisoformat(seen["json"]["startedAfter"])
    before = date.fromisoformat(seen["json"]["startedBefore"])
    assert (before - after).days == 90


def test_e_charging_power_type_from_details() -> None:
    d = _status([_e("~ 17 kWh", {"chargingPowerType": "AC"})])
    assert d.last_charging_session_current_type == "AC"
    assert d.last_charging_session_kwh == 17.0
    # legacy shape keeps working
    d2 = _status([_e({"value": 1, "unit": "kWh"}, {"currentType": "dc"}, key="sessionDetails")])
    assert d2.last_charging_session_current_type == "DC"


def test_e2_an_empty_details_object_does_not_hide_the_legacy_one() -> None:
    d = _status([{
        "primaryValue": {"value": 3, "unit": "kWh"},
        "details": {},
        "sessionDetails": {"currentType": "dc", "startedAt": "2026-06-10T05:14:00Z"},
    }])
    assert d.last_charging_session_current_type == "DC"
    assert d.last_charging_session_start == "2026-06-10T05:14:00Z"
    assert d.recent_charging_sessions[0]["started_at"] == "2026-06-10T05:14:00Z"


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
