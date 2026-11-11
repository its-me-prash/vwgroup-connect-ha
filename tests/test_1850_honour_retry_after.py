# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#1850 — spending requests against an explicit "too many" is how a 429
becomes a 430.

@indigomejor measured an account-level lockout on a Škoda Octavia, and then —
after the first half of #1850 was addressed — a hard 430 again, at a LOWER
request rate, with no second client on the account. That ruled out the
shared-budget explanation and pointed at this path.

Two faults on the shared request code, both visible in his log:

* A 429 was retried three times at 5/10/20 s before the account lockout
  engaged. So a throttled call spent three MORE requests at the precise moment
  the backend had said "too many".
* ``Retry-After`` was never read here at all. It is honoured on the official
  Škoda channel and on the Porsche client, which carry their own request code —
  the shared path that produced his 429s simply did not look at it. The wait
  that followed was our 30 minutes rather than the server's number, which can
  be wrong in either direction.

With the header present there is nothing left to probe for: the answer is in
hand. The retries are skipped and the client holds for what was asked, clamped
at both ends. Without the header the old behaviour stands unchanged — a bare
429 can still be a momentary burst, and giving up on it would lose reads that
work today.

The value is read off THIS response, by a staticmethod that has no instance to
consult. The official Škoda channel keeps a ``retry_after_s`` attribute and had
to learn that reading it at this point is wrong — it is set on a 429 and never
cleared, so any later 4xx inherited the old window. This class holds no such
attribute, and the signature is what keeps it that way.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.vag_connect.cariad.api.base import (
    _LOCKOUT_429_S,
    _LOCKOUT_430_S,
    _RETRY_AFTER_MIN_S,
)
from custom_components.vag_connect.cariad.api.vw_eu import VWEUClient
from custom_components.vag_connect.cariad.exceptions import APIError
from custom_components.vag_connect.cariad.models import TokenSet

_SLEEP = "custom_components.vag_connect.cariad.api.base.asyncio.sleep"


def _resp(status: int, headers: dict[str, str] | None = None) -> AsyncMock:
    resp = AsyncMock()
    resp.status = status
    resp.headers = {"Content-Type": "application/json", **(headers or {})}
    resp.json = AsyncMock(return_value={})
    resp.text = AsyncMock(return_value="")
    resp.__aenter__ = AsyncMock(return_value=resp)
    resp.__aexit__ = AsyncMock(return_value=False)
    return resp


def _client_with(responses: list[AsyncMock]) -> tuple[VWEUClient, dict]:
    """A client whose session hands back `responses` in order.

    ``calls["i"]`` is the instrument this file turns on: it counts how many
    requests actually left, which is the thing the reporter was being billed
    for.
    """
    calls = {"i": 0}

    def side_effect(*_a: object, **_k: object) -> AsyncMock:
        r = responses[min(calls["i"], len(responses) - 1)]
        calls["i"] += 1
        return r

    session = MagicMock()
    session.request = MagicMock(side_effect=side_effect)
    client = VWEUClient(session, "u@t.de", "pw")
    client._tokens = TokenSet("acc", "ref", "id")
    return client, calls


async def _get(client: VWEUClient) -> None:
    with patch(_SLEEP, new=AsyncMock()):
        with pytest.raises(APIError):
            await client._request("GET", "https://example.invalid/x")


# ── the measured harm ────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_a_429_with_retry_after_costs_exactly_one_request() -> None:
    """The load-bearing one. Three extra requests at the moment the backend
    said stop is what turned his 429 into a 430; with an instruction in hand
    there is nothing to discover by asking again."""
    client, calls = _client_with([_resp(429, {"Retry-After": "600"})])
    await _get(client)

    assert calls["i"] == 1, (
        f"the 429 was retried {calls['i'] - 1} more time(s) although the server "
        "had said how long to wait"
    )
    remaining = client._rate_lockout_remaining()
    assert 590 < remaining <= 600, remaining


@pytest.mark.asyncio
async def test_without_the_header_the_old_behaviour_is_untouched() -> None:
    """A bare 429 carries no instruction, so it may still be a momentary burst.
    Changing this too would lose reads that work today — the regression half."""
    client, calls = _client_with([_resp(429)])
    await _get(client)

    assert calls["i"] == 4, f"expected the original plus three retries, got {calls['i']}"
    remaining = client._rate_lockout_remaining()
    assert _LOCKOUT_429_S - 10 < remaining <= _LOCKOUT_429_S, remaining


@pytest.mark.asyncio
async def test_the_retries_are_skipped_not_merely_shortened() -> None:
    """Belt and braces on the sleep itself: with the header present the backoff
    sleep must not run at all, not even once."""
    client, _ = _client_with([_resp(429, {"Retry-After": "120"})])
    sleeper = AsyncMock()
    with patch(_SLEEP, new=sleeper):
        with pytest.raises(APIError):
            await client._request("GET", "https://example.invalid/x")
    assert sleeper.await_count == 0, "a backoff sleep ran despite Retry-After"


# ── the clamp ────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_a_tiny_retry_after_is_floored() -> None:
    """``Retry-After: 1`` honoured literally is a thrash loop, so the floor
    wins — while still being far short of the 30-minute blanket hold."""
    client, calls = _client_with([_resp(429, {"Retry-After": "1"})])
    await _get(client)
    assert calls["i"] == 1
    remaining = client._rate_lockout_remaining()
    assert _RETRY_AFTER_MIN_S - 5 < remaining <= _RETRY_AFTER_MIN_S, remaining
    assert _RETRY_AFTER_MIN_S < _LOCKOUT_429_S, (
        "the floor must not exceed the no-header hold, or a short honest wait "
        "would be punished harder than silence"
    )


@pytest.mark.asyncio
async def test_an_absurd_retry_after_cannot_exceed_what_a_429_already_held() -> None:
    """The ceiling, and the first version of this test had it wrong.

    It clamped to ``_LOCKOUT_430_S`` and called that a safety bound, on the
    reasoning that no header should be worse than an explicit hard refusal.
    Wrong comparison: the bound worth keeping is what a soft 429 could do
    BEFORE this change, which was ``_LOCKOUT_429_S``. At 7200 a single header
    value could have taken the whole account dark for two hours — four times
    longer than any number of 429s had ever managed — while the pull request
    described the ceiling as protective.

    A backend asking for longer is therefore not honoured in full, and that is
    the deliberate choice: resuming at 30 minutes sends ONE request, because
    the retries are gone, and a refusal of that one is honoured in turn.
    """
    client, calls = _client_with([_resp(429, {"Retry-After": "86400"})])
    await _get(client)
    assert calls["i"] == 1
    remaining = client._rate_lockout_remaining()
    assert _LOCKOUT_429_S - 10 < remaining <= _LOCKOUT_429_S, remaining
    assert remaining < _LOCKOUT_430_S, (
        "a soft 429 armed a hold as long as an explicit 430 — the account-wide "
        "two-hour stall must stay reachable only from a real 430"
    )


@pytest.mark.asyncio
async def test_an_explicit_430_still_gets_the_full_hard_hold() -> None:
    """The other side of the same bound: narrowing the 429 ceiling must not
    shorten what an explicit hard refusal arms."""
    client, _ = _client_with([_resp(430, {"Retry-After": "60"})])
    await _get(client)
    remaining = client._rate_lockout_remaining()
    assert _LOCKOUT_430_S - 10 < remaining <= _LOCKOUT_430_S, remaining


def test_a_short_hold_is_not_logged_as_zero_minutes() -> None:
    """The second thing the pre-merge review caught.

    ``_enter_rate_lockout`` rendered its duration as ``seconds // 60``, so
    every hold under a minute — which is the entire band the 30-second floor
    creates — logged "pausing all requests for 0 min", in a sentence that goes
    on to say "to avoid a multi-hour account lock". The one line a reporter
    pastes claimed both no wait and a multi-hour threat at once.
    """
    from custom_components.vag_connect.cariad.api.base import _format_duration

    assert _format_duration(_RETRY_AFTER_MIN_S) == "30s"
    assert _format_duration(45) == "45s"
    assert _format_duration(59) == "59s"
    assert _format_duration(60) == "1 min"
    assert _format_duration(_LOCKOUT_429_S) == "30 min"
    assert _format_duration(_LOCKOUT_430_S) == "2h"
    assert "0 min" not in _format_duration(_RETRY_AFTER_MIN_S)


def test_the_lockout_warning_states_the_duration_it_actually_set(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Through the real call, not only the formatter: a floored hold has to read
    as a short wait in the log a user sees."""
    import logging

    client, _ = _client_with([_resp(200)])
    with caplog.at_level(logging.WARNING, logger="custom_components.vag_connect.cariad.api.base"):
        client._enter_rate_lockout(_RETRY_AFTER_MIN_S, 429, "api.example/x")
    logged = " ".join(r.getMessage() for r in caplog.records)
    assert "30s" in logged, logged
    assert "0 min" not in logged, logged


@pytest.mark.asyncio
async def test_an_http_date_is_treated_as_absent() -> None:
    """RFC 9110 allows a date form too. A half-parsed date is worse than no
    value, so an unparsed header leaves the existing backoff in charge rather
    than producing a hold of zero — or of some accidental integer."""
    client, calls = _client_with([_resp(429, {"Retry-After": "Wed, 21 Oct 2026 07:28:00 GMT"})])
    await _get(client)
    assert calls["i"] == 4, "the date form was parsed as a number"
    remaining = client._rate_lockout_remaining()
    assert _LOCKOUT_429_S - 10 < remaining <= _LOCKOUT_429_S, remaining


@pytest.mark.asyncio
async def test_a_negative_or_empty_value_is_treated_as_absent() -> None:
    for value in ("-5", "", "   ", "abc", "6.5"):
        client, calls = _client_with([_resp(429, {"Retry-After": value})])
        await _get(client)
        assert calls["i"] == 4, f"{value!r} was taken as a number"


# ── the trap the official Skoda channel already documented ───────────────────
def test_the_parser_has_no_instance_to_remember_anything_with() -> None:
    """Written this way after the first attempt at it was vacuous.

    That attempt set ``client.retry_after_s = 3600`` and asserted the retries
    still ran — but this client has no such attribute, so the test created one
    that nothing reads and would have passed against any implementation. The
    attribute lives on the official Škoda client, which is where the precedent
    was read from, and that is also where the trap was learnt: it is set on a
    429, never cleared, and reading it at decision time parked a healthy read
    channel on the next unrelated 4xx.

    The property that is actually true here, and actually prevents it, is the
    signature: a staticmethod taking headers has no ``self`` to consult.
    """
    import inspect

    from custom_components.vag_connect.cariad.api.base import CariadBaseClient

    attr = inspect.getattr_static(CariadBaseClient, "_retry_after_seconds")
    assert isinstance(attr, staticmethod), (
        "_retry_after_seconds gained access to instance state — the stale-value "
        "trap becomes reachable again"
    )
    params = list(inspect.signature(CariadBaseClient._retry_after_seconds).parameters)
    assert params == ["headers"], params

    # And the client genuinely carries no such attribute to be tempted by.
    client, _ = _client_with([_resp(200)])
    assert not hasattr(client, "retry_after_s")


# ── the quota headers, now kept where they matter ────────────────────────────
@pytest.mark.asyncio
async def test_the_quota_is_recorded_on_a_429() -> None:
    """These two statuses are the ones whose headers are ABOUT the rate limit.
    Discarding them here meant a reporter attaching diagnostics after a lockout
    could not show us their remaining budget at all."""
    client, _ = _client_with([
        _resp(429, {"Retry-After": "60", "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Limit": "200"}),
    ])
    await _get(client)
    assert client.last_rate_limit_remaining == 0
    assert client.last_rate_limit_limit == 200


@pytest.mark.asyncio
async def test_the_quota_is_recorded_on_a_430_too() -> None:
    client, _ = _client_with([_resp(430, {"X-RateLimit-Remaining": "0"})])
    await _get(client)
    assert client.last_rate_limit_remaining == 0
    remaining = client._rate_lockout_remaining()
    assert _LOCKOUT_430_S - 10 < remaining <= _LOCKOUT_430_S, remaining


# ── what must not have moved ─────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_a_server_error_still_retries_on_its_own_schedule() -> None:
    """The 5xx path shares this function and was not the subject. A 503 with a
    Retry-After must keep its own backoff — narrowing the change to 429 is what
    keeps this patch small enough to reason about."""
    client, calls = _client_with([_resp(503, {"Retry-After": "600"})])
    await _get(client)
    assert calls["i"] == 4, "the 5xx retry schedule changed"
    assert client._rate_lockout_remaining() == 0, "a 503 armed the account lockout"


@pytest.mark.asyncio
async def test_a_plain_success_is_unaffected() -> None:
    client, calls = _client_with([_resp(200, {"X-RateLimit-Remaining": "199"})])
    with patch(_SLEEP, new=AsyncMock()):
        await client._request("GET", "https://example.invalid/x")
    assert calls["i"] == 1
    assert client._rate_lockout_remaining() == 0
    assert client.last_rate_limit_remaining == 199


def test_the_header_is_parsed_off_the_response_argument() -> None:
    """The parsing itself, including the forms that must read as absent."""
    from custom_components.vag_connect.cariad.api.base import CariadBaseClient

    parse = CariadBaseClient._retry_after_seconds
    assert parse({"Retry-After": "90"}) == 90
    assert parse({"retry-after": "90"}) is None or parse({"retry-after": "90"}) == 90
    assert parse({}) is None
    assert parse(None) is None
    assert parse({"Retry-After": "0"}) == 0
    assert parse({"Retry-After": " 45 "}) == 45
