# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Phase C — get_vehicle_data(request_type="all") reads the historical export.

The one-time export shares the whole read path with the 15-min feed; only two
things differ, both proven from a real portal trace (2026-07-17):

* metadata comes from ``.../metadata/all`` (not ``/metadata/partial``)
* the datadelivery list + download carry ``type: all`` (not ``type: partial``)

The download endpoint and the parse are identical. These tests pin the two
differences and, crucially, that the default (partial — the coordinator's live
poll) is untouched.
"""
from __future__ import annotations

import io
import json
import zipfile
from typing import Any

import pytest

from custom_components.vag_connect.cariad.auth._eu_data_act import EUDataActConnector


def _zip() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(
            "charging/data.json",
            json.dumps({"vin": "V", "userId": "u", "Data": [
                {"dataFieldName": "RDT.timerBasicSettings.[0].chargeMinLimit",
                 "value": "50", "key": "k"},
            ]}),
        )
    return buf.getvalue()


class _Resp:
    def __init__(self, *, json_data: Any = None, body: bytes = b"") -> None:
        self.status = 200
        self._json = json_data
        self._body = body

    async def __aenter__(self) -> "_Resp":
        return self

    async def __aexit__(self, *_a: Any) -> bool:
        return False

    async def text(self, errors: str | None = None) -> str:
        return ""

    async def json(self, content_type: Any = None) -> Any:
        return self._json

    async def read(self) -> bytes:
        return self._body


class _CaptureSession:
    """Records every GET's url + headers so the type header is assertable."""

    def __init__(self) -> None:
        self.gets: list[tuple[str, dict]] = []

    def get(self, url: str, **kw: Any) -> _Resp:
        self.gets.append((url, kw.get("headers") or {}))
        if "metadata" in url:
            return _Resp(json_data={"identifier": "ID123"})
        if url.endswith("/list"):
            return _Resp(json_data=[{"name": "20260711_V.zip"}])
        if url.endswith("/download"):
            return _Resp(body=_zip())
        raise AssertionError(f"unmatched GET {url}")


async def _run(request_type: str) -> _CaptureSession:
    sess = _CaptureSession()
    conn = EUDataActConnector(sess)  # type: ignore[arg-type]
    await conn.get_vehicle_data("VINX", request_type=request_type)
    return sess


def _url_with(sess: _CaptureSession, needle: str) -> tuple[str, dict]:
    for url, headers in sess.gets:
        if needle in url:
            return url, headers
    raise AssertionError(f"no GET containing {needle!r}; got {[u for u, _ in sess.gets]}")


@pytest.mark.asyncio
async def test_all_reads_metadata_all() -> None:
    sess = await _run("all")
    url, _ = _url_with(sess, "metadata")
    assert url.endswith("/metadata/all")
    assert "/metadata/partial" not in url


@pytest.mark.asyncio
async def test_all_sends_type_all_on_list_and_download() -> None:
    sess = await _run("all")
    _, list_h = _url_with(sess, "/list")
    _, dl_h = _url_with(sess, "/download")
    assert list_h.get("type") == "all"
    assert dl_h.get("type") == "all"
    assert dl_h.get("filename") == "20260711_V.zip"  # the download needs the name


@pytest.mark.asyncio
async def test_all_parses_the_legacy_field() -> None:
    # End-to-end through the shared parser: the legacy chargeMinLimit → min_soc.
    sess = _CaptureSession()
    conn = EUDataActConnector(sess)  # type: ignore[arg-type]
    result = await conn.get_vehicle_data("VINX", request_type="all")
    assert result.min_soc == 50


@pytest.mark.asyncio
async def test_partial_default_is_unchanged() -> None:
    # The coordinator's live poll must be byte-for-byte the old behaviour.
    sess = await _run("partial")
    meta_url, _ = _url_with(sess, "metadata")
    assert meta_url.endswith("/metadata/partial")
    _, list_h = _url_with(sess, "/list")
    _, dl_h = _url_with(sess, "/download")
    assert list_h.get("type") == "partial"
    assert dl_h.get("type") == "partial"


@pytest.mark.asyncio
async def test_default_arg_is_partial() -> None:
    # Calling without the arg (as the coordinator does) must stay partial.
    sess = _CaptureSession()
    conn = EUDataActConnector(sess)  # type: ignore[arg-type]
    await conn.get_vehicle_data("VINX")
    meta_url = next(u for u, _ in sess.gets if "metadata" in u)
    assert meta_url.endswith("/metadata/partial")
