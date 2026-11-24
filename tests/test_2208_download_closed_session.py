# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#2208 — a session closed DURING the poll reached the dataset download.

The error report: ``get_status`` → ``get_vehicle_data`` →
``_download_dataset_raw`` → ``self._session.get`` → aiohttp's bare
``RuntimeError("Session is closed")``, filed as a crash on 5.5.0.

The guard in ``_get_json`` (#1834) runs on every attempt of every JSON read,
but the download bypasses ``_get_json`` for its own headers. The metadata and
listing reads succeed, the entry unloads while one of them (or a download) is
awaited, and the next download meets a closed session. These tests close the
session at exactly those two points, use the REAL ``_download_dataset_raw``
and a session that raises like aiohttp does, so a missing guard fails here with
the RuntimeError from the report.
"""
from __future__ import annotations

import asyncio
from typing import Any

_VIN = "WVWZZZ000M0000001"


class _ClosedCtx:
    """What aiohttp does: the error surfaces on entry, not on ``.get()``."""

    async def __aenter__(self) -> Any:
        raise RuntimeError("Session is closed")

    async def __aexit__(self, *_a: object) -> None:
        return None


class _Resp:
    def __init__(self, status: int) -> None:
        self.status = status

    async def __aenter__(self) -> _Resp:
        return self

    async def __aexit__(self, *_a: object) -> None:
        return None

    async def read(self) -> bytes:
        return b""


class _Session:
    """Answers each GET with ``status`` while open, raises once closed.

    ``close_after_gets`` closes the session after that many answered GETs,
    the way an unload closes it while the poll awaits the response.
    """

    def __init__(self, *, status: int = 503, close_after_gets: int | None = None) -> None:
        self.closed = False
        self.calls = 0
        self._status = status
        self._close_after = close_after_gets
        self.cookie_jar = type(
            "_J", (), {"filter_cookies": lambda *_a: {}, "update_cookies": lambda *_a: None}
        )()

    def get(self, *_a: object, **_k: object) -> Any:
        self.calls += 1
        if self.closed:
            return _ClosedCtx()
        if self._close_after is not None and self.calls >= self._close_after:
            self.closed = True
        return _Resp(self._status)

    post = get


def _connector(session: _Session, *, close_on_listing: bool) -> Any:
    """A connector whose metadata and listing reads succeed.

    Two dataset files are listed, so the download loop has a second candidate
    to move on to after a transient answer.
    """
    from custom_components.vag_connect.cariad.auth._eu_data_act import (
        EUDataActConnector,
    )

    conn = EUDataActConnector(session, brand="volkswagen")  # type: ignore[arg-type]
    reads: list[str] = []

    async def _fake_get_json(url: str, **_k: object) -> Any:
        reads.append(url)
        if len(reads) == 1:
            return {"identifier": "REQ-1"}
        if close_on_listing:
            session.closed = True  # the unload lands while the listing is awaited
        return [
            {"name": "newer.zip", "createdOn": "2026-11-23T16:30:00Z"},
            {"name": "older.zip", "createdOn": "2026-11-23T16:15:00Z"},
        ]

    conn._get_json = _fake_get_json  # type: ignore[method-assign]
    return conn


def _run(coro: Any) -> Any:
    return asyncio.new_event_loop().run_until_complete(coro)


def test_session_closed_during_the_listing_downloads_nothing() -> None:
    session = _Session()
    conn = _connector(session, close_on_listing=True)

    data = _run(conn.get_vehicle_data(_VIN))

    assert session.calls == 0, "a download was attempted on a closed session"
    assert data.vin == _VIN
    assert data.no_data is True
    # The portal was not asked, so no outcome is recorded for this poll.
    assert conn.no_data_count == 0
    assert conn.last_no_data_reason == ""


def test_session_closed_between_two_downloads_stops_the_loop() -> None:
    # The newest file answers 503, so the loop would fall back to the older
    # one; the session closes while that first answer is awaited.
    session = _Session(status=503, close_after_gets=1)
    conn = _connector(session, close_on_listing=False)

    data = _run(conn.get_vehicle_data(_VIN))

    assert session.calls == 1, "the loop went on to a closed session"
    assert data.no_data is True
    assert conn.no_data_count == 0


def test_an_open_session_still_falls_back_to_the_older_file() -> None:
    # Control: with the session open, a transient answer on the newest file
    # still moves on to the next candidate, as before the guard.
    session = _Session(status=503)
    conn = _connector(session, close_on_listing=False)

    data = _run(conn.get_vehicle_data(_VIN))

    assert session.calls == 2
    assert data.no_data is True
    assert conn.last_no_data_reason == "portal_error"
