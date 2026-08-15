# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#1078 single-flight refresh coalescing.

One Škoda poll fires ~14 concurrent GETs (get_status asyncio.gather). On a
just-expired bearer they all 401 at once and each calls ``_refresh_tokens`` with
the same stale token. They serialise on the refresh lock, but before this fix
each still booked a refresh, so ONE expiry event spent the whole 3/hour budget in
seconds and self-tripped the storm guard at a perfectly healthy interval (foobarth
#1078). The single-flight guard collapses them to one real rotation; a genuine
storm (the token never changes) still trips.
"""
from __future__ import annotations

import asyncio
from typing import Any

import pytest

from custom_components.vag_connect.cariad.api import base as _base
from custom_components.vag_connect.cariad.api.vw_eu import VWEUClient
from custom_components.vag_connect.cariad.auth import _mbboauth
from custom_components.vag_connect.cariad.exceptions import AuthenticationError
from custom_components.vag_connect.cariad.models import TokenSet


class _Sess:
    def get(self, url: str, headers: Any = None) -> Any:  # pragma: no cover
        raise AssertionError("no network in these tests")


def _mbb_client() -> VWEUClient:
    c = VWEUClient(_Sess(), "u@t.de", "pw")
    c._tokens = TokenSet(
        access_token="STALE_BEARER", refresh_token="RT", id_token="i",
        expires_at=0.0, strategy="mbb",
    )
    c._mbb_client_id = "CID"
    return c


def test_concurrent_401s_coalesce_to_one_refresh(monkeypatch) -> None:
    """The fan-out case: many concurrent 401s carrying the same expired bearer
    collapse to exactly one real rotation and one budget slot; no storm."""
    c = _mbb_client()
    old = c._tokens.access_token
    calls: list[int] = []

    async def _fake(session, refresh_token, *, client_id):
        calls.append(1)  # rotate to a NEW token so queued waiters see the change
        return _mbboauth.MbbTokenSet(
            access_token=f"NEW{len(calls)}", refresh_token="RT",
            token_type="Bearer", expires_at=0.0,
        )

    monkeypatch.setattr(_mbboauth, "refresh", _fake)

    async def _run() -> None:
        await asyncio.gather(*[
            c._refresh_tokens(stale_access_token=old)
            for _ in range(_base._REFRESH_MAX_PER_HOUR + 3)  # 6 concurrent 401s
        ])

    asyncio.run(_run())

    assert len(calls) == 1                    # one real rotation, not six
    assert len(c._refresh_history) == 1       # one budget slot spent
    assert c.refresh_storm_detected is False
    assert c._tokens.access_token == "NEW1"


def test_genuine_storm_still_trips(monkeypatch) -> None:
    """When rotation is a no-op (token keeps coming back unchanged, i.e. a real
    storm), the guard is NOT suppressed and still raises after the cap."""
    c = _mbb_client()
    old = c._tokens.access_token

    async def _noop(session, refresh_token, *, client_id):
        # returns the SAME bearer → self._tokens.access_token stays == old,
        # so the coalesce guard never fires and each attempt is counted.
        return _mbboauth.MbbTokenSet(
            access_token=old, refresh_token="RT",
            token_type="Bearer", expires_at=0.0,
        )

    monkeypatch.setattr(_mbboauth, "refresh", _noop)

    for _ in range(_base._REFRESH_MAX_PER_HOUR):
        asyncio.run(c._refresh_tokens(stale_access_token=old))
    with pytest.raises(AuthenticationError, match="storm"):
        asyncio.run(c._refresh_tokens(stale_access_token=old))
    assert c.refresh_storm_detected is True


def test_no_stale_token_keeps_old_behaviour(monkeypatch) -> None:
    """Command / pre-flight callers pass no stale token, so the guard is inert
    and every attempt still counts (byte-for-byte the previous behaviour)."""
    c = _mbb_client()

    async def _fake(session, refresh_token, *, client_id):
        return _mbboauth.MbbTokenSet(
            access_token="ROT", refresh_token="RT",
            token_type="Bearer", expires_at=0.0,
        )

    monkeypatch.setattr(_mbboauth, "refresh", _fake)
    asyncio.run(c._refresh_tokens())          # stale_access_token=None
    asyncio.run(c._refresh_tokens())
    assert len(c._refresh_history) == 2       # both counted, no coalesce
