# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#957/#966 — the 15-min poll must adopt the identifier from a LIST-shaped
``metadata/partial`` payload, not only from a bare dict.

The portal returns the active Custom Data Request descriptors as a *list*
(``[{"Frequency": "15mins", "Identifier": …}]``). The poll path used to read
the identifier dict-only (``if isinstance(meta, dict): meta.get("identifier")``),
so a list-shaped payload skipped the branch entirely, ``identifier`` stayed
empty, and every poll reported ``no_request`` — a false "no data-request yet"
even though an active feed existed. The kickoff walker
(``get_active_custom_request_identifier``) always parsed the list correctly, so
the two diverged.

The fix shares ONE walker (``pick_active_15min_identifier``) between both paths.
These tests pin: (a) a list-shaped payload is adopted on the poll,
(b) a rotated identifier is picked up automatically (delete+recreate self-heals
next poll), (c) a wrapped-dict shape is adopted, and (d) an expired-only list
still correctly reports ``no_request`` so a fresh feed is kicked off.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import pytest

from custom_components.vag_connect.cariad.auth._eu_data_act import EUDataActConnector

_VIN = "WVWZZZAAAA0000001"
_ID_A = "aaaaaaaa1111bbbb2222cccc3333dddd"  # 32 hex, >= 16 chars
_ID_B = "eeeeeeee4444ffff5555000011112222"


def _past_iso() -> str:
    return (datetime.now(tz=timezone.utc) - timedelta(days=1)).isoformat()


class _Resp:
    def __init__(self, *, json_data: Any = None) -> None:
        self.status = 200
        self._json = json_data

    async def __aenter__(self) -> "_Resp":
        return self

    async def __aexit__(self, *_a: Any) -> bool:
        return False

    async def text(self, errors: str | None = None) -> str:
        return ""

    async def json(self, content_type: Any = None) -> Any:
        return self._json

    async def read(self) -> bytes:
        return b""


class _Session:
    """Serves a caller-supplied metadata payload; the listing is always an
    empty list so the poll terminates right after the identifier is resolved
    (reaching ``/list`` proves the identifier was adopted)."""

    def __init__(self, meta_payload: Any) -> None:
        self._meta = meta_payload
        self.gets: list[str] = []

    def get(self, url: str, **kw: Any) -> _Resp:
        self.gets.append(url)
        if "metadata" in url:
            return _Resp(json_data=self._meta)
        if url.endswith("/list"):
            return _Resp(json_data=[])
        raise AssertionError(f"unexpected GET {url}")

    def _list_url(self) -> str | None:
        return next((u for u in self.gets if u.endswith("/list")), None)


async def _poll(meta_payload: Any) -> tuple[EUDataActConnector, _Session]:
    sess = _Session(meta_payload)
    conn = EUDataActConnector(sess)  # type: ignore[arg-type]
    await conn.get_vehicle_data(_VIN)
    return conn, sess


@pytest.mark.asyncio
async def test_list_shaped_metadata_is_adopted_on_poll() -> None:
    conn, sess = await _poll(
        [{"Frequency": "15mins", "Identifier": _ID_A}]
    )
    # The core #957/#966 regression: a list payload must NOT read as no_request.
    assert conn.last_no_data_reason != "no_request"
    list_url = sess._list_url()
    assert list_url is not None, "poll bailed before reaching the listing"
    assert _ID_A in list_url  # the walked identifier was used


@pytest.mark.asyncio
async def test_rotated_identifier_is_picked_up_next_poll() -> None:
    # delete+recreate in the portal mints a new Identifier; because metadata is
    # re-fetched each poll, the very next poll adopts it — no restart needed.
    _, sess_a = await _poll([{"Frequency": "15mins", "Identifier": _ID_A}])
    _, sess_b = await _poll([{"Frequency": "15mins", "Identifier": _ID_B}])
    assert _ID_A in (sess_a._list_url() or "")
    assert _ID_B in (sess_b._list_url() or "")


@pytest.mark.asyncio
async def test_wrapped_dict_shape_is_adopted() -> None:
    conn, sess = await _poll(
        {"items": [{"Frequency": "15mins", "Identifier": _ID_A}]}
    )
    assert conn.last_no_data_reason != "no_request"
    assert _ID_A in (sess._list_url() or "")


@pytest.mark.asyncio
async def test_expired_only_list_reports_no_request() -> None:
    # An expired descriptor must be skipped so a fresh feed is kicked off (#465);
    # with nothing else in the list the poll correctly reports no_request.
    conn, sess = await _poll(
        [{"Frequency": "15mins", "Identifier": _ID_A, "EndDate": _past_iso()}]
    )
    assert conn.last_no_data_reason == "no_request"
    assert sess._list_url() is None  # never reached the listing


@pytest.mark.asyncio
async def test_bare_dict_identifier_still_works() -> None:
    # Backward-compat: a bare dict carrying the identifier at the top level
    # (no 15-min descriptor to walk) is still honoured via the dict fallback.
    conn, sess = await _poll({"identifier": "ID-legacy-000000"})
    assert conn.last_no_data_reason != "no_request"
    assert sess._list_url() is not None
