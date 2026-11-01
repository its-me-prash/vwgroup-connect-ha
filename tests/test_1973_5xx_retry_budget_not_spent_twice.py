# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#1973 — a URL that spends its whole 5xx retry budget does not get it again.

@indigomejor measured this on a Škoda Octavia (petrol, MySkoda app login plus
EU Data Act portal), parked, over four polls, by temporarily adding the request
path to the "Server error" debug line. Two endpoints answered 500 on every
attempt of every poll:

* ``GET /api/v2/connection-status/{vin}/readiness``
* ``GET /api/v1/vehicle-information/{vin}/software-version/update-status``

and a third, ``/api/v1/vehicle-automatization/{vin}/departure/timers``, once
right after startup. His own correction of the arithmetic is the point of this
file: "the 4th attempt also goes out and then raises, so each chain is 4
requests and it is 8 failed requests per poll" — not the six the issue title
was opened with. ``base._request`` retries a 5xx while ``_attempt < 3`` with
``(2 ** _attempt) * 3`` seconds between, which is attempts at 0/3/6/12 s, so
four requests buy exactly what the first one already said.

**What is pinned here, and what deliberately is not.** Only the RETRIES are
withheld, and only from a URL that already spent the whole budget for nothing.
One attempt still goes out on every poll. That is what makes the change safe
without answering the question #1973 could not settle — whether such an
endpoint is merely unprovisioned for that car, in which case the 500 is
permanent, or genuinely flapping. A transient outage recovers on the next poll
and clears the mark (``test_a_success_restores_the_budget``); a permanent one
costs one request per poll instead of four. Skipping the call outright is NOT
done: it would need a re-probe schedule and could only save one more request.

The other unknown from #1973 is also still open and not pinned here: whether
"more during a drive" means more polls or more failures per poll. He measured a
parked car.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest

# A self-evidently synthetic VIN. It appears in the URLs below so the test can
# prove the suppression log does not carry it.
_VIN = "WVWZZZAUZFW000000"
_READINESS = f"https://mysmob.api.connect.skoda-auto.cz/api/v2/connection-status/{_VIN}/readiness"
_UPDATE = (
    "https://mysmob.api.connect.skoda-auto.cz/api/v1/vehicle-information/"
    f"{_VIN}/software-version/update-status"
)


class _Resp:
    def __init__(self, status: int) -> None:
        self.status = status
        # ``_request`` decides between .json() and .text() on this header, so a
        # 2xx double without it comes back as the error string and the test
        # reads like a product failure. Measured the hard way.
        self.headers: dict[str, str] = {"Content-Type": "application/json"}

    async def text(self, **_kw: Any) -> str:
        return "upstream said 500"

    async def json(self, **_kw: Any) -> Any:
        return {"ok": True}

    async def __aenter__(self) -> _Resp:
        return self

    async def __aexit__(self, *_exc: Any) -> None:
        return None


class _Session:
    """Counts requests per URL and answers from a per-URL script."""

    def __init__(self, script: dict[str, list[int]] | None = None,
                 default: int = 500) -> None:
        self.script = {k: list(v) for k, v in (script or {}).items()}
        self.default = default
        self.calls: list[str] = []

    def request(self, method: str, url: str, **_kw: Any) -> _Resp:
        self.calls.append(url)
        queue = self.script.get(url)
        status = queue.pop(0) if queue else self.default
        return _Resp(status)

    def count(self, url: str) -> int:
        return sum(1 for u in self.calls if u == url)


def _client(session: _Session) -> Any:
    """A Škoda client: its brand is not ``volkswagen``, so ``_request``'s
    proactive VW-EU re-mint branch cannot fire and no auth runs in the test."""
    from custom_components.vag_connect.cariad.api.skoda import SkodaClient

    c = SkodaClient(session, "u@t.invalid", "pw")  # type: ignore[arg-type]
    c._session = session  # type: ignore[assignment]
    c._tokens = SimpleNamespace(access_token="tok")  # type: ignore[assignment]
    return c


@pytest.fixture(autouse=True)
def _no_real_sleeping(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    """The real ladder waits 3+6+12 s per chain. Record the waits instead.

    Recorded rather than merely silenced, because one test asserts that a
    suppressed poll does not sleep at all — a suppression that still waited
    would keep the poll slow while hiding it from a request count.
    """
    from custom_components.vag_connect.cariad.api import base

    waits: list[float] = []

    async def _fake_sleep(seconds: float) -> None:
        waits.append(seconds)

    monkeypatch.setattr(base.asyncio, "sleep", _fake_sleep)
    return waits


def _get(c: Any, url: str) -> Any:
    from custom_components.vag_connect.cariad.exceptions import APIError

    try:
        return asyncio.new_event_loop().run_until_complete(c._request("GET", url))
    except APIError as err:
        return err


class TestTheFirstPollStillSpendsTheBudget:
    """The positive control. Without this, a passing suppression test could
    just mean the request never went out at all."""

    def test_four_requests_on_the_first_poll(self) -> None:
        s = _Session()
        c = _client(s)
        _get(c, _READINESS)
        assert s.count(_READINESS) == 4, "0/3/6/12 s ladder = four requests"

    def test_the_ladder_waits_three_six_twelve(self, _no_real_sleeping: list[float]) -> None:
        s = _Session()
        c = _client(s)
        _get(c, _READINESS)
        assert _no_real_sleeping == [3, 6, 12]

    def test_the_caller_still_gets_the_api_error(self) -> None:
        from custom_components.vag_connect.cariad.exceptions import APIError

        s = _Session()
        c = _client(s)
        err = _get(c, _READINESS)
        assert isinstance(err, APIError)
        assert err.status == 500


class TestTheSecondPollDoesNotSpendItAgain:
    """The change itself."""

    def test_one_request_on_the_second_poll(self) -> None:
        s = _Session()
        c = _client(s)
        _get(c, _READINESS)          # poll 1 — budget spent
        before = s.count(_READINESS)
        _get(c, _READINESS)          # poll 2
        assert s.count(_READINESS) - before == 1

    def test_and_on_every_poll_after_that(self) -> None:
        s = _Session()
        c = _client(s)
        _get(c, _READINESS)
        for poll in range(2, 7):
            before = s.count(_READINESS)
            _get(c, _READINESS)
            assert s.count(_READINESS) - before == 1, f"poll {poll}"
        # 4 for the first poll, then one each for five more
        assert s.count(_READINESS) == 9

    def test_his_two_endpoints_together_cost_two_instead_of_eight(self) -> None:
        """The number from the report: 8 failed requests per poll."""
        s = _Session()
        c = _client(s)
        _get(c, _READINESS)
        _get(c, _UPDATE)
        assert len(s.calls) == 8, "the measured steady state before the change"
        s.calls.clear()
        _get(c, _READINESS)
        _get(c, _UPDATE)
        assert len(s.calls) == 2, "the steady state after it"

    def test_a_suppressed_poll_does_not_sleep(self, _no_real_sleeping: list[float]) -> None:
        s = _Session()
        c = _client(s)
        _get(c, _READINESS)
        _no_real_sleeping.clear()
        _get(c, _READINESS)
        assert _no_real_sleeping == []

    def test_the_caller_still_gets_the_api_error(self) -> None:
        """Suppressing retries must not change what the caller sees."""
        from custom_components.vag_connect.cariad.exceptions import APIError

        s = _Session()
        c = _client(s)
        _get(c, _READINESS)
        err = _get(c, _READINESS)
        assert isinstance(err, APIError)
        assert err.status == 500

    def test_the_suppression_is_not_a_skip(self) -> None:
        """One attempt per poll is what lets a recovery be noticed at all."""
        s = _Session(script={_READINESS: [500, 500, 500, 500, 200]})
        c = _client(s)
        _get(c, _READINESS)                     # spends the budget
        assert _get(c, _READINESS) == {"ok": True}, (
            "the single attempt of the next poll must still go out"
        )


class TestOnlyAFullySpentBudgetMarks:
    def test_a_500_that_recovers_on_the_second_attempt_does_not_mark(self) -> None:
        s = _Session(script={_READINESS: [500, 200]})
        c = _client(s)
        assert _get(c, _READINESS) == {"ok": True}
        before = s.count(_READINESS)
        _get(c, _READINESS)   # now 500s all the way
        assert s.count(_READINESS) - before == 4, (
            "a budget that was never fully spent must still be available"
        )

    def test_a_success_restores_the_budget(self) -> None:
        s = _Session(script={_READINESS: [500, 500, 500, 500, 200]})
        c = _client(s)
        _get(c, _READINESS)   # spent
        _get(c, _READINESS)   # the 200 — withdraws the mark
        before = s.count(_READINESS)
        _get(c, _READINESS)
        assert s.count(_READINESS) - before == 4, (
            "a transient outage must cost the suppression only until it clears"
        )

    def test_a_204_also_restores_it(self) -> None:
        """204 is a success that returns None, not an absence of an answer."""
        s = _Session(script={_READINESS: [500, 500, 500, 500, 204]})
        c = _client(s)
        _get(c, _READINESS)
        assert _get(c, _READINESS) is None
        before = s.count(_READINESS)
        _get(c, _READINESS)
        assert s.count(_READINESS) - before == 4

    def test_a_404_does_not_restore_it(self) -> None:
        """A 4xx never consumed the 5xx budget, so it says nothing about it.

        Pinned so the clear stays on the success statuses only: widening it to
        "any non-5xx" would let a 404 hand the budget back to an endpoint that
        is failing in both ways.
        """
        s = _Session(script={_READINESS: [500, 500, 500, 500, 404]})
        c = _client(s)
        _get(c, _READINESS)
        _get(c, _READINESS)   # the 404
        before = s.count(_READINESS)
        _get(c, _READINESS)
        assert s.count(_READINESS) - before == 1


class TestTheKey:
    def test_the_query_string_is_not_part_of_it(self) -> None:
        """Otherwise a cursor or timestamp in the query mints a fresh key every
        poll: the memory grows without bound and never matches."""
        from custom_components.vag_connect.cariad.api.base import _5xx_budget_key

        assert _5xx_budget_key("GET", "https://h/p?a=1") == _5xx_budget_key(
            "GET", "https://h/p?a=2"
        )

    def test_the_method_is_part_of_it(self) -> None:
        from custom_components.vag_connect.cariad.api.base import _5xx_budget_key

        assert _5xx_budget_key("GET", "https://h/p") != _5xx_budget_key(
            "POST", "https://h/p"
        )

    def test_a_changing_query_shares_one_suppression(self) -> None:
        s = _Session()
        c = _client(s)
        _get(c, "https://h/trip-statistics?offset=0")
        before = len(s.calls)
        _get(c, "https://h/trip-statistics?offset=1")
        assert len(s.calls) - before == 1

    def test_a_different_endpoint_keeps_its_own_budget(self) -> None:
        s = _Session()
        c = _client(s)
        _get(c, _READINESS)
        before = s.count(_UPDATE)
        _get(c, _UPDATE)
        assert s.count(_UPDATE) - before == 4


class TestAClientBuiltWithoutInit:
    """Regression pin. The first cut of this fix read ``self._5xx_spent``
    directly and broke four unrelated tests in ``test_vweu_remint.py``, which
    build their client via ``VWEUClient.__new__`` to skip the HA setup chain.
    The repo already carries that convention in production code ("Defensive:
    when the client was instantiated via ``__new__``", with a getattr default),
    so the memory is created on first use."""

    @staticmethod
    def _bare(session: _Session) -> Any:
        from custom_components.vag_connect.cariad.api.skoda import SkodaClient

        c = SkodaClient.__new__(SkodaClient)
        c._session = session  # type: ignore[assignment]
        c._tokens = SimpleNamespace(access_token="tok")  # type: ignore[assignment]
        c._brand = MagicMock()
        c._rate_lockout_remaining = MagicMock(return_value=0)  # type: ignore[assignment]
        c._capture_rate_limit_headers = MagicMock()  # type: ignore[assignment]
        return c

    def test_a_success_does_not_raise_attributeerror(self) -> None:
        s = _Session(default=204)
        c = self._bare(s)
        assert _get(c, _READINESS) is None, "a 204 must still return None"

    def test_the_suppression_still_works_on_such_a_client(self) -> None:
        s = _Session()
        c = self._bare(s)
        _get(c, _READINESS)
        before = s.count(_READINESS)
        _get(c, _READINESS)
        assert s.count(_READINESS) - before == 1


class TestTheLogDoesNotLeak:
    def test_the_suppression_line_does_not_carry_the_vin(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """The key is built from the path, and the path contains the VIN."""
        import logging

        s = _Session()
        c = _client(s)
        _get(c, _READINESS)
        with caplog.at_level(logging.DEBUG, logger="custom_components.vag_connect"):
            _get(c, _READINESS)
        text = caplog.text
        assert "not retrying" in text, "positive control: the line was emitted"
        assert _VIN not in text
        assert "readiness" not in text
