# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#2241 — the Škoda warning-lights read is asked at most every 6 hours.

In @driemeier's log the read ``vehicle-health-report/warning-lights`` answered
429 on all four tries at start-up, the account lockout followed, and a flash a
minute later was refused locally. The read went out on every poll for every
car. ``SkodaClient.get_warning_lights`` now:

- skips a car whose known capability list has none of the three
  ``VEHICLE_HEALTH_*`` ids (an unknown list is still asked);
- sends one request per car per 6 h, counted from each attempt;
- sends it with ``send_once=True`` (one request on a 429, no pause; the
  shared path is pinned in ``test_2241_command_not_repeated_after_429``);
- returns the last payload in between and after a failure;
- does not count a poll in an active account lockout as an attempt.
"""
from __future__ import annotations

import asyncio
import time
from typing import Any
from unittest.mock import MagicMock

import pytest

from custom_components.vag_connect.cariad.api.skoda import (
    _WARNING_LIGHTS_EVERY_S,
    APIError,
    SkodaClient,
)

VIN = "TMBJJ7NX1M0000009"
_PATH = f"/api/v1/vehicle-health-report/warning-lights/{VIN}"
_ENGINE_DEFECT = {
    "warningLights": [
        {"category": "ENGINE", "defects": [{"text": "Check engine"}]},
        {"category": "BRAKES", "defects": []},
    ]
}


class _Backend:
    """``_get`` stand-in: records URL and keywords, answers per path fragment.
    A route value that is a list is answered step by step."""

    def __init__(self, routes: dict[str, Any]) -> None:
        self.routes = routes
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def get(self, url: str, **kw: Any) -> Any:
        self.calls.append((url, kw))
        for frag, result in self.routes.items():
            if frag in url:
                if isinstance(result, list):
                    result = result.pop(0)
                if isinstance(result, Exception):
                    raise result
                return result
        return {}

    @property
    def lights(self) -> list[dict[str, Any]]:
        return [kw for url, kw in self.calls if _PATH in url]


def _client(routes: dict[str, Any]) -> tuple[SkodaClient, _Backend]:
    c = SkodaClient(MagicMock(), "u@t.de", "pw")
    backend = _Backend(routes)
    c._get = backend.get  # type: ignore[method-assign]
    c.get_charging_statistics = _no_stats  # type: ignore[method-assign]
    return c, backend


async def _no_stats(_vin: str) -> dict[str, Any]:
    return {}


def _lights(c: SkodaClient) -> Any:
    return asyncio.run(c.get_warning_lights(VIN))


def _age(c: SkodaClient, seconds: float) -> None:
    """Move the last attempt ``seconds`` into the past."""
    stamp, payload = c._warning_lights_seen[VIN]
    c._warning_lights_seen[VIN] = (stamp - seconds, payload)


# ── capability gate ─────────────────────────────────────────────────────────


def test_a_car_that_lists_none_of_the_three_is_not_asked() -> None:
    c, backend = _client({_PATH: _ENGINE_DEFECT})
    c._capability_ids[VIN] = {"PARKING_POSITION", "BATTERY_HEALTH_STATE"}

    assert _lights(c) is None
    assert backend.lights == []


@pytest.mark.parametrize(
    "cap",
    ["VEHICLE_HEALTH_INSPECTION", "VEHICLE_HEALTH_WARNINGS",
     "VEHICLE_HEALTH_WARNINGS_WITH_WAKE_UP"],
)
def test_a_car_that_lists_one_of_them_is_asked(cap: str) -> None:
    c, backend = _client({_PATH: _ENGINE_DEFECT})
    c._capability_ids[VIN] = {"PARKING_POSITION", cap}

    assert _lights(c) == _ENGINE_DEFECT
    assert len(backend.lights) == 1


def test_an_empty_capability_list_is_still_asked() -> None:
    """An empty set is more likely a list that did not parse than a car with
    no capabilities at all, so it does not switch the read off."""
    c, backend = _client({_PATH: _ENGINE_DEFECT})
    c._capability_ids[VIN] = set()

    assert _lights(c) == _ENGINE_DEFECT
    assert len(backend.lights) == 1


def test_an_unknown_capability_list_is_still_asked() -> None:
    c, backend = _client({_PATH: _ENGINE_DEFECT})
    assert VIN not in c._capability_ids

    assert _lights(c) == _ENGINE_DEFECT
    assert len(backend.lights) == 1


def test_the_read_is_sent_once_on_a_429() -> None:
    c, backend = _client({_PATH: _ENGINE_DEFECT})

    _lights(c)

    assert backend.lights[0].get("send_once") is True


# ── every 6 hours ───────────────────────────────────────────────────────────


def test_within_6_hours_the_last_payload_comes_back_without_a_request() -> None:
    c, backend = _client({_PATH: _ENGINE_DEFECT})

    first = _lights(c)
    _age(c, _WARNING_LIGHTS_EVERY_S - 60)
    second = _lights(c)

    assert first == second == _ENGINE_DEFECT
    assert len(backend.lights) == 1


def test_after_6_hours_it_is_asked_again() -> None:
    c, backend = _client({_PATH: [_ENGINE_DEFECT, {"warningLights": []}]})

    _lights(c)
    _age(c, _WARNING_LIGHTS_EVERY_S + 1)

    assert _lights(c) == {"warningLights": []}
    assert len(backend.lights) == 2


def test_each_car_has_its_own_clock() -> None:
    other = "TMBZZZ00000000000"
    c, backend = _client({"/warning-lights/": _ENGINE_DEFECT})

    asyncio.run(c.get_warning_lights(VIN))
    asyncio.run(c.get_warning_lights(other))

    assert len([u for u, _ in backend.calls if "/warning-lights/" in u]) == 2


@pytest.mark.parametrize(
    "error",
    [APIError(429, "https://x/warning-lights", "Too Many Requests"),
     APIError(500, "https://x/warning-lights", "boom"),
     TimeoutError()],
    ids=["429", "500", "timeout"],
)
def test_a_failure_keeps_the_last_payload_and_waits_6_hours(error: Exception) -> None:
    c, backend = _client({_PATH: [_ENGINE_DEFECT, error, {"warningLights": []}]})

    _lights(c)
    _age(c, _WARNING_LIGHTS_EVERY_S + 1)
    assert _lights(c) == _ENGINE_DEFECT
    assert _lights(c) == _ENGINE_DEFECT

    assert len(backend.lights) == 2


def test_a_first_failure_gives_none_and_also_waits() -> None:
    c, backend = _client({_PATH: [APIError(429, "https://x", ""), _ENGINE_DEFECT]})

    assert _lights(c) is None
    assert _lights(c) is None
    assert len(backend.lights) == 1


def test_a_non_dict_answer_keeps_the_last_payload() -> None:
    c, backend = _client({_PATH: [_ENGINE_DEFECT, "not json"]})

    _lights(c)
    _age(c, _WARNING_LIGHTS_EVERY_S + 1)

    assert _lights(c) == _ENGINE_DEFECT
    assert len(backend.lights) == 2


def test_an_active_lockout_is_not_counted_as_an_attempt() -> None:
    c, backend = _client({_PATH: [_ENGINE_DEFECT, {"warningLights": []}]})
    _lights(c)
    _age(c, _WARNING_LIGHTS_EVERY_S + 1)

    c._rate_limit_locked_until = time.monotonic() + 600
    assert _lights(c) == _ENGINE_DEFECT
    assert len(backend.lights) == 1

    c._rate_limit_locked_until = None
    assert _lights(c) == {"warningLights": []}
    assert len(backend.lights) == 2


@pytest.mark.parametrize("had_payload", [False, True], ids=["first-read", "later-read"])
def test_a_lockout_that_comes_up_during_the_read_is_not_counted(had_payload: bool) -> None:
    """Another read (or a 430 / Retry-After on this one) arms the lockout
    while this read is under way; its next try is refused locally. The slot
    is given back, so the read is asked on the first poll after the lockout."""
    c, backend = _client({})
    if had_payload:
        backend.routes[_PATH] = [_ENGINE_DEFECT]
        _lights(c)
        _age(c, _WARNING_LIGHTS_EVERY_S + 1)
    before = c._warning_lights_seen.get(VIN)

    async def _arming_get(url: str, **kw: Any) -> Any:
        backend.calls.append((url, kw))
        c._rate_limit_locked_until = time.monotonic() + 600
        raise APIError(429, url, "rate-limit lockout active — 600s remaining")

    c._get = _arming_get  # type: ignore[method-assign]
    expected = _ENGINE_DEFECT if had_payload else None
    assert _lights(c) == expected
    assert c._warning_lights_seen.get(VIN) == before

    c._rate_limit_locked_until = None
    c._get = backend.get  # type: ignore[method-assign]
    backend.routes[_PATH] = {"warningLights": []}
    assert _lights(c) == {"warningLights": []}


def test_two_overlapping_polls_of_one_car_send_one_request() -> None:
    c, backend = _client({})
    sent: list[str] = []

    async def _slow_get(url: str, **_kw: Any) -> Any:
        sent.append(url)
        await asyncio.sleep(0)
        return _ENGINE_DEFECT

    c._get = _slow_get  # type: ignore[method-assign]

    async def _both() -> list[Any]:
        return list(await asyncio.gather(
            c.get_warning_lights(VIN), c.get_warning_lights(VIN)))

    results = asyncio.run(_both())

    assert len(sent) == 1
    assert _ENGINE_DEFECT in results


# ── through get_status ──────────────────────────────────────────────────────


def test_get_status_reads_it_once_and_keeps_the_warning_between_reads() -> None:
    c, backend = _client({_PATH: _ENGINE_DEFECT})

    first = asyncio.run(c.get_status(VIN))
    second = asyncio.run(c.get_status(VIN))

    assert len(backend.lights) == 1
    for d in (first, second):
        assert d.warning_active is True
        assert d.warning_engine is True
        assert d.warning_count == 1


def test_get_status_skips_it_for_a_car_without_the_capability() -> None:
    c, backend = _client({_PATH: _ENGINE_DEFECT})
    c._capability_ids[VIN] = {"PARKING_POSITION"}

    d = asyncio.run(c.get_status(VIN))

    assert backend.lights == []
    assert d.warning_active is None
