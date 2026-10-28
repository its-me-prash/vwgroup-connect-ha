# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#1942 — the "raise your update interval" card could latch on for good, and
recommend a bigger number every time it came back.

@clipse2004 (CUPRA Formentor, DE) reported the card returning after every
increase, with a higher recommendation each time. The escalation is not evidence
of repeated storms: the advice ladder in ``const.py`` derives the number from the
*current* interval, so **one** flag that never clears produces 40 → 55 → 60 and
then goes quiet at the cap. A single latched boolean explains the whole symptom.

**The latch was introduced by the v5.1.2 fix for #1918, in this repository.**
That fix added an early ``return`` to ``_refresh_tokens`` so a bearer-less
cookie session stops paying for a re-login that cannot work. The return is
correct, but it sits *before* the budget check **and before all five paths that
clear** ``refresh_storm_detected`` — the flag has exactly one setter and five
clearers, every one of them downstream of that return.

So this sequence latched:

1. the client holds a real bearer, the native plane 401s repeatedly, three
   refreshes land inside the rolling hour and the budget trips — the flag goes
   True, correctly;
2. still in the same session the native plane answers 403, the attestation
   wall, and ``seat_cupra`` arms the portal fallback, which installs the
   bearer-less sentinel;
3. from then on every ``_refresh_tokens`` leaves through the early return, so
   no clearer can ever run again.

The flag stays True for the life of the client, the coordinator reads it on
every poll, and the card is raised forever with no storm behind it. That is the
one state in which the advice is pure noise: a cookie session spends no budget
at all, so raising the interval cannot change anything.

Clearing the flag in that branch is a **measurement, not an assumption** — the
branch returns precisely because it will not spend a slot. ``account_lock_
detected`` is deliberately left alone, and that is pinned below: nothing on this
path measured whether the account is locked, so clearing it would fabricate an
all-clear. A restart re-authenticates and clears it honestly.

Why the #1918 tests could not see this: every one of them starts from a client
that was constructed moments earlier, where the flag has never been anything but
False. Asserting that it is still False proves nothing about a flag that was
True. The sequence above is the only way to see it, and nothing drove it.
"""
from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.vag_connect.cariad.api import base as _base
from custom_components.vag_connect.cariad.api.vw_eu import VWEUClient
from custom_components.vag_connect.cariad.exceptions import AuthenticationError
from custom_components.vag_connect.cariad.models import TokenSet

_PORTAL_SENTINEL = "eu-data-act-portal-cookie-session"
_AUTHPROXY_SENTINEL = "vw-website-authproxy-cookie-session"

_FALLBACKS = [
    (_PORTAL_SENTINEL, "data_act_portal"),
    (_AUTHPROXY_SENTINEL, "website_authproxy"),
]


class _Sess:
    def get(self, url: str, headers: Any = None) -> Any:  # pragma: no cover
        raise AssertionError("no network in these tests")

    def post(self, *a: Any, **k: Any) -> Any:  # pragma: no cover
        raise AssertionError("no network in these tests")


def _client_on_a_real_bearer() -> VWEUClient:
    c = VWEUClient(_Sess(), "u@t.de", "pw")
    c._tokens = TokenSet(
        access_token="REAL_BEARER",
        refresh_token="",
        id_token="REAL_BEARER",
        expires_at=0.0,
        strategy="",
    )
    c.authenticate = AsyncMock(return_value=None)  # type: ignore[method-assign]
    return c


def _fall_back_to(c: VWEUClient, sentinel: str, strategy: str) -> None:
    """What ``_arm_eu_portal`` does mid-session on a 403: swap in a cookie
    session with no bearer. The client object is the same one."""
    c._tokens = TokenSet(
        access_token=sentinel,
        refresh_token="",
        id_token=sentinel,
        expires_at=0.0,
        strategy=strategy,
    )


def _trip_the_budget(c: VWEUClient) -> None:
    async def _hammer() -> None:
        for _ in range(_base._REFRESH_MAX_PER_HOUR):
            await c._refresh_tokens()
        with pytest.raises(AuthenticationError):
            await c._refresh_tokens()

    asyncio.run(_hammer())
    assert c.refresh_storm_detected is True, "precondition not reached"


# ── the latch ───────────────────────────────────────────────────────────────


@pytest.mark.parametrize(("sentinel", "strategy"), _FALLBACKS,
                         ids=["eu-data-act-portal", "website-authproxy"])
def test_falling_back_mid_session_clears_a_storm_that_can_no_longer_happen(
    sentinel: str, strategy: str
) -> None:
    """The reported sequence, end to end: trip it on a real bearer, fall back,
    refresh once more. The flag the Repair reads must be False afterwards."""
    c = _client_on_a_real_bearer()
    _trip_the_budget(c)

    _fall_back_to(c, sentinel, strategy)
    asyncio.run(c._refresh_tokens(stale_access_token=sentinel))

    assert c.refresh_storm_detected is False, (
        "the storm flag latched: this channel spends no budget, so the "
        "'raise your update interval' Repair would be raised forever with "
        "nothing behind it"
    )


@pytest.mark.parametrize(("sentinel", "strategy"), _FALLBACKS,
                         ids=["eu-data-act-portal", "website-authproxy"])
def test_it_stays_cleared_across_later_polls(sentinel: str, strategy: str) -> None:
    """Every later poll takes the same early return, so the clear must not be a
    one-shot that a second pass undoes."""
    c = _client_on_a_real_bearer()
    _trip_the_budget(c)
    _fall_back_to(c, sentinel, strategy)

    async def _three_more_polls() -> None:
        for _ in range(3):
            await c._refresh_tokens(stale_access_token=sentinel)

    asyncio.run(_three_more_polls())

    assert c.refresh_storm_detected is False


def test_the_consumer_the_coordinator_reads_is_the_one_that_clears() -> None:
    """The card's condition is ``getattr(client, "refresh_storm_detected",
    False)``. Pin the attribute name, so a rename cannot leave the clear
    writing to something nothing reads."""
    c = _client_on_a_real_bearer()
    _trip_the_budget(c)
    assert getattr(c, "refresh_storm_detected", False) is True

    _fall_back_to(c, _PORTAL_SENTINEL, "data_act_portal")
    asyncio.run(c._refresh_tokens(stale_access_token=_PORTAL_SENTINEL))

    assert getattr(c, "refresh_storm_detected", False) is False


# ── what must NOT be cleared along with it ──────────────────────────────────


def test_an_account_lock_is_not_cleared_by_a_path_that_never_checked() -> None:
    """The five real clearers also clear ``account_lock_detected``, because each
    one sits after a *successful* rotation that proves the account is usable.
    This branch proves nothing of the kind, so it must leave that flag where it
    is rather than fabricate an all-clear."""
    c = _client_on_a_real_bearer()
    c.account_lock_detected = True

    _fall_back_to(c, _PORTAL_SENTINEL, "data_act_portal")
    asyncio.run(c._refresh_tokens(stale_access_token=_PORTAL_SENTINEL))

    assert c.account_lock_detected is True, (
        "a path that made no request just declared the account unlocked"
    )


def test_the_command_plane_does_not_clear_the_data_plane_flag() -> None:
    """``refresh_storm_detected`` is set only for the data plane (commands have
    their own bounded budget and their own remedy), so only the data plane may
    clear it. Symmetry with the setter, not decoration."""
    c = _client_on_a_real_bearer()
    _trip_the_budget(c)

    _fall_back_to(c, _PORTAL_SENTINEL, "data_act_portal")
    asyncio.run(c._refresh_tokens(for_command=True))

    assert c.refresh_storm_detected is True


# ── the #1918 property this must not trade away ─────────────────────────────


@pytest.mark.parametrize(("sentinel", "strategy"), _FALLBACKS,
                         ids=["eu-data-act-portal", "website-authproxy"])
def test_clearing_the_flag_still_spends_nothing(sentinel: str, strategy: str) -> None:
    """#1918's whole point. The clear happens on the way out of the branch, so
    it must not re-introduce a booking or a re-login."""
    c = VWEUClient(_Sess(), "u@t.de", "pw")
    c.authenticate = AsyncMock(return_value=None)  # type: ignore[method-assign]
    _fall_back_to(c, sentinel, strategy)

    asyncio.run(c._refresh_tokens(stale_access_token=sentinel))

    assert c._refresh_history == []
    c.authenticate.assert_not_awaited()


def test_the_guard_still_trips_on_a_token_that_could_be_refreshed() -> None:
    """#1078 must keep working. A real bearer hammering the budget is exactly
    the case the Repair exists for, and the clear must not reach it."""
    c = _client_on_a_real_bearer()
    _trip_the_budget(c)

    assert c.refresh_storm_detected is True
    assert len(c._refresh_history) == _base._REFRESH_MAX_PER_HOUR


# ── the half the first fix missed: nothing guarantees a later refresh ───────


def _arm_portal(c: VWEUClient) -> None:
    """Drive the real ``_arm_eu_portal`` with only the network faked, so the
    clear is observed where it actually has to happen."""
    conn = MagicMock()
    conn.login = AsyncMock(return_value=None)
    with patch(
        "custom_components.vag_connect.cariad.auth._eu_data_act.EUDataActConnector",
        return_value=conn,
    ):
        asyncio.run(c._arm_eu_portal())


def test_arming_the_portal_fallback_clears_the_flag_by_itself() -> None:
    """Clearing it inside ``_refresh_tokens`` was not enough, and this is the
    test that says why.

    The data path calls ``_refresh_tokens`` only on a 401 (the proactive re-mint
    is gated to one strategy and one brand). The native block that sends a
    SEAT/CUPRA car to this fallback is a **403**. So on exactly the car this
    fallback exists for, nothing re-enters the refresh path, the clear there
    never runs, and the Repair stays raised until a restart.

    ``tests/test_reactive_session_recovery.py::
    test_a_403_does_not_recover_and_that_is_the_known_gap`` pins that premise.
    """
    c = _client_on_a_real_bearer()
    _trip_the_budget(c)
    c._refresh_tokens = AsyncMock(  # type: ignore[method-assign]
        side_effect=AssertionError("arming must not depend on a refresh")
    )

    _arm_portal(c)

    assert c.refresh_storm_detected is False, (
        "the flag survived the switch to a channel that spends no budget, and "
        "nothing on a 403 path would ever come back to clear it"
    )


def test_arming_installs_the_sentinel_and_clears_in_the_same_step() -> None:
    """Pin the pairing, not just the flag: the clear belongs to the moment the
    bearer-less session is installed."""
    c = _client_on_a_real_bearer()
    _trip_the_budget(c)

    _arm_portal(c)

    assert c._tokens is not None
    assert c._tokens.strategy == "data_act_portal"
    assert c._tokens.refresh_token == ""
    assert c.refresh_storm_detected is False


def _arm_website(c: VWEUClient) -> None:
    conn = MagicMock()
    conn.begin_login = AsyncMock(return_value="ok")
    with patch(
        "custom_components.vag_connect.cariad.auth._website_authproxy"
        ".WebsiteAuthProxyConnector",
        return_value=conn,
    ):
        asyncio.run(c._arm_website_proxy())


def test_arming_the_website_fallback_clears_the_flag_by_itself() -> None:
    """The website-authproxy channel is the same shape — a bearer-less cookie
    session that spends no refresh budget — so it needs the same clear.

    This test exists because a mutation run found that line unpinned: deleting
    it left every test green. An unpinned line is one a later tidy-up removes.
    """
    c = _client_on_a_real_bearer()
    c._website_cookies = None
    _trip_the_budget(c)

    _arm_website(c)

    assert c._tokens is not None
    assert c._tokens.strategy == "website_authproxy"
    assert c._tokens.refresh_token == ""
    assert c.refresh_storm_detected is False


def test_arming_does_not_declare_the_account_unlocked() -> None:
    """Same boundary as the refresh path: arming a fallback measures nothing
    about an account lock."""
    c = _client_on_a_real_bearer()
    c.account_lock_detected = True

    _arm_portal(c)

    assert c.account_lock_detected is True


def test_a_real_bearer_keeps_the_flag_after_a_later_refusal() -> None:
    """The clear must be reachable only through the cookie-session branch. A
    client that stays on a real bearer and keeps being refused has a genuine
    storm, and the advice is right for it."""
    c = _client_on_a_real_bearer()
    _trip_the_budget(c)

    with pytest.raises(AuthenticationError):
        asyncio.run(c._refresh_tokens())

    assert c.refresh_storm_detected is True
