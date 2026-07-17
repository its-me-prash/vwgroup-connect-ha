# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#584 — the MBB refresh sent a malformed body: no refresh_token parameter.

`refresh()` inherited the shape of `exchange_id_token()` and sent
`{grant_type: refresh_token, token: <RT>}` — the value under `token`, no
`refresh_token` parameter at all, no scope. For a refresh grant that is
malformed: the request says "refresh" and carries nothing to refresh with.
@Mattheisen87's diagnostics show the result — a 500 IllegalStateException on
every refresh, expiry frozen four days on a 60-minute token, i.e. it never
once succeeded.

What these tests DO establish: the request we now send is spec-conformant —
grant_type + refresh_token + scope — matching evcc and every other refresh
path in this codebase (idk / device-grant / porsche). That is the real reason
to prefer `refresh_token`.

What they do NOT establish, and must not be read as: that the field name was
provably the cause of the 500. A 500 is a server-side crash we can't attribute
from the outside, and the .bru's own note records that BOTH `token` and
`refresh_token` have been reported working upstream — so the .bru is a
hand-authored reference, not a capture, and it does not by itself convict the
field name. An earlier version of this file called it "a capture of the real
request" and "the source of truth"; that was wrong on both counts.

LIVE-GATED: the fix makes the request well-formed and standard; whether that
clears @Mattheisen87's 500 needs one real MBB round-trip to confirm. The
current path has a 0% success rate, so there is nothing to regress.
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


def test_matches_the_bru_reference_shape() -> None:
    # The .bru is a hand-authored reference, NOT a capture (its own docs block
    # ends "zu erstellen v1.27" — to be created — and its note says both field
    # names have been reported working). So this pins that our request agrees
    # with the reference's documented shape; it is not evidence that the field
    # name was the fault. That case rests on standards-conformance + parity with
    # evcc and our other refresh paths, asserted in the tests above.
    import pathlib

    bru = pathlib.Path("tests/bruno/mbb_legacy/02_POST_token_refresh.bru").read_text(
        encoding="utf-8"
    )
    assert "grant_type: refresh_token" in bru
    assert "refresh_token: {{vw_refresh_token}}" in bru
    assert "scope: sc2:fal" in bru
