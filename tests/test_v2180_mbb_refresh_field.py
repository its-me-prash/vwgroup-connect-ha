# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#584 — the MBB refresh sent the token under the wrong field name.

`refresh()` inherited the shape of `exchange_id_token()`, where putting the
value in `token` is genuinely correct (that's the classic MBB id_token grant).
The refresh grant needs `refresh_token`, and it needs the scope, which was
dropped in the same copy.

So the backend received `grant_type=refresh_token` with no refresh_token in
it and crashed server-side — HTTP 500 IllegalStateException instead of a
clean 401. MBB therefore died about an hour after every setup and never once
refreshed, and the v2.15.12 5xx retry couldn't help: it re-sent a
deterministically malformed request three times and gave up.

Our own recorded request has had the right shape all along —
`tests/bruno/mbb_legacy/02_POST_token_refresh.bru` sends grant_type +
refresh_token + scope, and its note even predicted this exact ambiguity.
Every other refresh path in the codebase already sends `refresh_token`; this
was the only one that didn't.

LIVE-GATED: verified against our recorded request and the surrounding code,
NOT against a live MBB round-trip. The current path has a 0% success rate, so
there is nothing to regress — but a reporter still has to confirm the fix.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest


async def _capture_refresh(refresh_token: str = "RT-SYNTHETIC") -> dict:
    """Run refresh() with the HTTP layer stubbed and return the posted body."""
    from custom_components.vag_connect.cariad.auth import _mbboauth

    with patch.object(_mbboauth, "_post_token", new=AsyncMock(return_value=None)) as pt:
        await _mbboauth.refresh(object(), refresh_token)
    return pt.await_args.args[1]


@pytest.mark.asyncio
async def test_token_travels_under_refresh_token() -> None:
    body = await _capture_refresh()
    assert body["refresh_token"] == "RT-SYNTHETIC"


@pytest.mark.asyncio
async def test_the_old_token_field_is_gone() -> None:
    # The bug: grant_type said refresh_token, the value sat in `token`, and the
    # server had nothing to refresh with.
    body = await _capture_refresh()
    assert "token" not in body


@pytest.mark.asyncio
async def test_scope_is_sent() -> None:
    # Dropped in the same copy-paste. Our recorded request sends it.
    body = await _capture_refresh()
    assert body["scope"] == "sc2:fal"


@pytest.mark.asyncio
async def test_grant_type_unchanged() -> None:
    body = await _capture_refresh()
    assert body["grant_type"] == "refresh_token"


@pytest.mark.asyncio
async def test_empty_refresh_token_still_rejected_locally() -> None:
    from custom_components.vag_connect.cariad.auth._mbboauth import refresh
    from custom_components.vag_connect.cariad.exceptions import AuthenticationError

    with pytest.raises(AuthenticationError):
        await refresh(object(), "")


@pytest.mark.asyncio
async def test_id_token_exchange_keeps_its_own_shape() -> None:
    # `token` IS correct for the id_token grant — the fix must not "tidy" the
    # working path into the same shape as the broken one.
    from custom_components.vag_connect.cariad.auth import _mbboauth

    with patch.object(_mbboauth, "_post_token", new=AsyncMock(return_value=None)) as pt:
        await _mbboauth.exchange_id_token(object(), "ID-SYNTHETIC")
    body = pt.await_args.args[1]
    assert body["grant_type"] == "id_token"
    assert body["token"] == "ID-SYNTHETIC"
    assert body["scope"] == "sc2:fal"


def test_matches_our_recorded_request() -> None:
    # The Bruno collection is the source of truth here: it's a capture of the
    # real request. If someone changes the field names again, this fails.
    import pathlib

    bru = pathlib.Path("tests/bruno/mbb_legacy/02_POST_token_refresh.bru").read_text(
        encoding="utf-8"
    )
    assert "grant_type: refresh_token" in bru
    assert "refresh_token: {{vw_refresh_token}}" in bru
    assert "scope: sc2:fal" in bru
