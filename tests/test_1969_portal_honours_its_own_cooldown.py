"""#1969 — the portal says how long to wait on a 429, and we ignored it.

Measured from the outside by a reader of the same portal on 2026-10-30: it
answers a burst with 429 and a short explicit ``Retry-After`` ("try again in
4 seconds"), with a per-endpoint ``RateLimit-Limit`` and no window header. Our
portal path parsed none of it. 429 is deliberately kept out of the retriable
set — "one quiet skip, no backoff-retry" — which is the right refusal to hammer
a server and the wrong answer to one that has just named its own cooldown. The
poll was simply lost: soft returned no-data, hard reported an outage, and on a
multi-vehicle account the newest dataset was never reached.

What is pinned here: one wait per call, only on a parseable header inside the
cap, and every other status untouched. The parsing itself lives in
``cariad/_util`` now because two channels need it and only the app backend had
it (#1850); its staticmethod on the base client stays, delegating, because a
test pins that shape.
"""
from __future__ import annotations

import asyncio
from typing import Any

import pytest

from custom_components.vag_connect.cariad._util import retry_after_seconds
from custom_components.vag_connect.cariad.auth import _eu_data_act as mod
from custom_components.vag_connect.cariad.auth._eu_data_act import (
    EUDataActConnector,
)
from custom_components.vag_connect.cariad.exceptions import (
    UpstreamUnavailableError,
)


class _Resp:
    def __init__(self, status: int, headers: dict[str, str], payload: Any) -> None:
        self.status = status
        self.headers = headers
        self._payload = payload
        self.url = "https://portal.invalid/x"

    async def __aenter__(self) -> "_Resp":
        return self

    async def __aexit__(self, *_exc: object) -> bool:
        return False

    async def json(self, content_type: str | None = None) -> Any:
        return self._payload

    async def text(self, errors: str | None = None) -> str:
        return "{}"

    async def read(self) -> bytes:
        return b""


class _Session:
    """Answers with a scripted sequence of (status, headers)."""

    def __init__(self, script: list[tuple[int, dict[str, str]]], payload: Any) -> None:
        self.script = list(script)
        self.payload = payload
        self.calls = 0

    def _next(self) -> _Resp:
        self.calls += 1
        status, headers = self.script[min(self.calls - 1, len(self.script) - 1)]
        return _Resp(status, headers, self.payload)

    def get(self, url: str, **_kw: Any) -> _Resp:
        return self._next()

    def post(self, url: str, **_kw: Any) -> _Resp:
        return self._next()


@pytest.fixture
def slept(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    """Record every sleep instead of taking it, so the tests stay fast."""
    seen: list[float] = []

    async def _fake(seconds: float) -> None:
        seen.append(seconds)

    monkeypatch.setattr(mod.asyncio, "sleep", _fake)
    return seen


def _run(coro: Any) -> Any:
    return asyncio.new_event_loop().run_until_complete(coro)


def _conn(script: list[tuple[int, dict[str, str]]], payload: Any = None) -> Any:
    s = _Session(script, payload if payload is not None else {})
    return EUDataActConnector(s), s  # type: ignore[arg-type]


class TestTheCooldownIsHonoured:
    def test_a_short_retry_after_is_waited_out_and_the_call_succeeds(
        self, slept: list[float]
    ) -> None:
        c, s = _conn(
            [(429, {"Retry-After": "4"}), (200, {})],
            {"vehicles": [{"vin": "WVWZZZAUZFW000000"}]},
        )
        assert _run(c.list_vehicle_vins()) == ["WVWZZZAUZFW000000"]
        assert slept == [4], f"expected one 4 s wait, got {slept}"
        assert s.calls == 2, "the request was not retried after the cooldown"

    def test_the_wait_is_taken_at_most_once(self, slept: list[float]) -> None:
        """A server that keeps throttling must not hold the poll open."""
        c, s = _conn([(429, {"Retry-After": "2"})])
        with pytest.raises(UpstreamUnavailableError):
            _run(c.list_vehicle_vins())
        assert slept == [2], f"more than one cooldown was taken: {slept}"


class TestWhenItMustNotWait:
    def test_a_429_without_the_header_behaves_exactly_as_before(
        self, slept: list[float]
    ) -> None:
        c, s = _conn([(429, {})])
        with pytest.raises(UpstreamUnavailableError):
            _run(c.list_vehicle_vins())
        assert slept == [], "waited without being told to"
        assert s.calls == 1

    @pytest.mark.parametrize("value", ["0", "31", "9999", "soon", "", "Wed, 21 Oct"])
    def test_an_unusable_cooldown_is_ignored(
        self, value: str, slept: list[float]
    ) -> None:
        """Zero, over the cap, and the HTTP-date form all leave it alone."""
        c, _s = _conn([(429, {"Retry-After": value})])
        with pytest.raises(UpstreamUnavailableError):
            _run(c.list_vehicle_vins())
        assert slept == [], f"{value!r} should not have produced a wait: {slept}"

    def test_a_5xx_still_uses_the_existing_backoff(self, slept: list[float]) -> None:
        """Control: the retriable family is untouched, header or no header."""
        c, _s = _conn([(503, {"Retry-After": "4"})])
        with pytest.raises(UpstreamUnavailableError):
            _run(c.list_vehicle_vins())
        assert slept == list(mod._PORTAL_RETRY_DELAYS), slept

    def test_a_404_does_not_wait(self, slept: list[float]) -> None:
        """Control: #1964's verdict stays immediate, no latency added."""
        c, _s = _conn([(404, {"Retry-After": "4"})])
        with pytest.raises(UpstreamUnavailableError):
            _run(c.list_vehicle_vins())
        assert slept == []

    def test_the_happy_path_never_sleeps(self, slept: list[float]) -> None:
        c, _s = _conn([(200, {})], {"vehicles": []})
        assert _run(c.list_vehicle_vins()) == []
        assert slept == []


class TestTheSoftPathToo:
    def test_a_soft_call_also_waits_and_then_returns_the_data(
        self, slept: list[float]
    ) -> None:
        """The data polls are the soft ones — they are what was losing polls."""
        c, s = _conn([(429, {"Retry-After": "3"}), (200, {})], {"ok": True})
        got = _run(c._get_json("https://portal.invalid/list", soft=True))
        assert got == {"ok": True}
        assert slept == [3]
        assert s.calls == 2

    def test_a_soft_call_still_gives_up_quietly_when_told_nothing(
        self, slept: list[float]
    ) -> None:
        c, _s = _conn([(429, {})])
        assert _run(c._get_json("https://portal.invalid/list", soft=True)) is None
        assert slept == []


class TestTheParserIsSharedNotCopied:
    def test_the_base_client_delegates_to_the_util(self) -> None:
        """One implementation. #1850's staticmethod shape is kept on purpose."""
        import inspect

        from custom_components.vag_connect.cariad.api.base import CariadBaseClient

        attr = inspect.getattr_static(CariadBaseClient, "_retry_after_seconds")
        assert isinstance(attr, staticmethod), "the shape #1850 pins was lost"
        assert CariadBaseClient._retry_after_seconds({"Retry-After": "7"}) == 7

    @pytest.mark.parametrize(
        ("raw", "want"),
        [({"Retry-After": "4"}, 4), ({"Retry-After": " 9 "}, 9),
         ({"Retry-After": "x"}, None), ({}, None), (None, None)],
    )
    def test_the_util_parses_only_delta_seconds(self, raw: Any, want: Any) -> None:
        assert retry_after_seconds(raw) == want
