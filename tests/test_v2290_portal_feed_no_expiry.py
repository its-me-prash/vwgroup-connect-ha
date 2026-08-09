# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The portal feed must not be created with a four-week expiry.

Every 15-minute feed used to be created as ``Duration: "One Month"`` with a
matching 31-day window, so roughly four weeks after setup the portal stopped
delivering and the sensors went quiet with no error anywhere: the integration
was healthy, the session was valid, and the data simply ended. The portal's own
rejection message lists ``No Expiry`` as an allowed value, so that is what we
ask for.

We cannot re-verify the exact no-expiry body shape against the live portal from
here, and a rejected kickoff means NO feed at all, which is worse than a feed
that has to be re-kicked. So the old shape stays as a fallback, and these tests
pin both halves: ask for no expiry first, fall back rather than give up.
"""
from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest

from custom_components.vag_connect.cariad.auth._data_act_scraper import (
    DataActScraper,
)

_VIN = "WVWZZZAUZFW805377"


class _Resp:
    def __init__(self, status: int) -> None:
        self.status = status

    async def __aenter__(self) -> "_Resp":
        return self

    async def __aexit__(self, *_a: Any) -> bool:
        return False

    async def text(self, errors: str | None = None) -> str:
        return "Invalid Duration"

    async def json(self, content_type: Any = None) -> Any:
        return {}


class _ScriptedSession:
    """Answers each POST with the next status in ``statuses``."""

    def __init__(self, statuses: list[int]) -> None:
        self.statuses = statuses
        self.post_calls: list[tuple[str, dict]] = []

    def post(self, url: str, **kw: Any) -> _Resp:
        self.post_calls.append((url, kw))
        index = min(len(self.post_calls) - 1, len(self.statuses) - 1)
        return _Resp(self.statuses[index])


def _scraper(sess: Any, readback: Any = "READBACK_IDENTIFIER_0001") -> DataActScraper:
    s = DataActScraper(sess, brand_name="volkswagen")
    s._fetch_csrf_token = AsyncMock(return_value="csrf")  # type: ignore[method-assign]
    # #957/#966 — kickoff now reads the request back after a 2xx to confirm it
    # actually landed. Default: the create is confirmed. Tests that exercise the
    # accepted-but-inert path pass readback=None or a side_effect list.
    s.get_active_custom_request_identifier = AsyncMock(  # type: ignore[method-assign]
        return_value=readback if not isinstance(readback, list) else None,
        side_effect=readback if isinstance(readback, list) else None,
    )
    return s


@pytest.mark.asyncio
async def test_no_expiry_is_asked_for_first() -> None:
    sess = _ScriptedSession([201])
    ident = await _scraper(sess).kickoff_custom_data_request(_VIN)
    assert ident
    assert len(sess.post_calls) == 1
    assert sess.post_calls[0][1]["json"]["Duration"] == "No Expiry"


@pytest.mark.asyncio
async def test_no_expiry_sends_no_enddate() -> None:
    """#957/#966 — the portal UI's "unlimited" sends NO EndDate; pairing
    "No Expiry" with a literal 10-year EndDate was the self-contradicting shape.
    The no-expiry body must omit EndDate entirely."""
    sess = _ScriptedSession([201])
    await _scraper(sess).kickoff_custom_data_request(_VIN)
    body = sess.post_calls[0][1]["json"]
    assert body["Duration"] == "No Expiry"
    assert "EndDate" not in body


@pytest.mark.asyncio
async def test_one_month_fallback_keeps_an_enddate() -> None:
    sess = _ScriptedSession([400, 201])
    await _scraper(sess).kickoff_custom_data_request(_VIN)
    body = sess.post_calls[1][1]["json"]
    assert body["Duration"] == "One Month"
    assert "EndDate" in body


@pytest.mark.asyncio
async def test_a_rejected_no_expiry_falls_back_instead_of_giving_up() -> None:
    """Asking for less beats asking for nothing: a portal that refuses the new
    shape still gets a working feed out of us."""
    sess = _ScriptedSession([400, 201])
    ident = await _scraper(sess).kickoff_custom_data_request(_VIN)
    assert ident, "fallback did not produce a feed"
    assert len(sess.post_calls) == 2
    assert sess.post_calls[1][1]["json"]["Duration"] == "One Month"


@pytest.mark.asyncio
async def test_2xx_but_inert_request_falls_back_to_one_month() -> None:
    """#957/#966 — a 2xx that does not actually register a request (readback
    finds nothing) must fall through to the proven "One Month", not be trusted."""
    sess = _ScriptedSession([201, 201])
    # attempt 1 readback: nothing landed; attempt 2 readback: it did.
    s = _scraper(sess, readback=[None, "READBACK_IDENTIFIER_0002"])
    ident = await s.kickoff_custom_data_request(_VIN)
    assert ident == "READBACK_IDENTIFIER_0002"
    assert len(sess.post_calls) == 2
    assert sess.post_calls[1][1]["json"]["Duration"] == "One Month"


@pytest.mark.asyncio
async def test_2xx_but_inert_on_both_reports_no_feed() -> None:
    sess = _ScriptedSession([201, 201])
    s = _scraper(sess, readback=None)
    assert await s.kickoff_custom_data_request(_VIN) is None
    assert len(sess.post_calls) == 2


@pytest.mark.asyncio
async def test_both_rejected_reports_no_feed() -> None:
    sess = _ScriptedSession([400, 400])
    assert await _scraper(sess).kickoff_custom_data_request(_VIN) is None
    assert len(sess.post_calls) == 2


@pytest.mark.asyncio
async def test_a_401_is_not_retried_as_a_format_problem() -> None:
    """An expired session must surface as an expired session, not be spent on
    a second doomed attempt."""
    from custom_components.vag_connect.cariad.auth._data_act_scraper import (
        DataActSessionExpiredError,
    )

    sess = _ScriptedSession([401])
    with pytest.raises(DataActSessionExpiredError):
        await _scraper(sess).kickoff_custom_data_request(_VIN)
    assert len(sess.post_calls) == 1
