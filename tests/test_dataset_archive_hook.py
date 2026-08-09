# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""P1-5 — the connector hands the RAW dataset ZIP to the archive hook, but only
for a genuine dataset, and only when the hook is wired.

The hook is the seam the coordinator uses to feed the opt-in on-disk archive.
It must receive the exact bytes downloaded (so they can be re-parsed later), it
must NOT fire on an empty / no-content poll (nothing worth archiving), and a
connector with no hook (the default) must behave exactly as before.
"""
from __future__ import annotations

import io
import json
import zipfile
from typing import Any

import pytest

from custom_components.vag_connect.cariad.auth._eu_data_act import EUDataActConnector


def _zip_with_soc() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(
            "charging/data.json",
            json.dumps({"vin": "V", "Data": [
                {"dataFieldName": "battery_state_report.soc", "value": "55"},
            ]}),
        )
    return buf.getvalue()


def _empty_zip() -> bytes:
    # An empty JSON object → the walker yields zero fields → "no data this poll".
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("charging/data.json", json.dumps({}))
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


class _Session:
    def __init__(self, zip_bytes: bytes) -> None:
        self._zip = zip_bytes

    def get(self, url: str, **kw: Any) -> _Resp:
        if "metadata" in url:
            return _Resp(json_data={"identifier": "ID-abc-000000000"})
        if url.endswith("/list"):
            return _Resp(json_data=[{"name": "20260807_V.zip"}])
        if url.endswith("/download"):
            return _Resp(body=self._zip)
        raise AssertionError(f"unexpected GET {url}")


@pytest.mark.asyncio
async def test_hook_receives_raw_bytes_of_a_genuine_dataset() -> None:
    zip_bytes = _zip_with_soc()
    conn = EUDataActConnector(_Session(zip_bytes))  # type: ignore[arg-type]
    captured: list[tuple[str, bytes, str]] = []
    conn.on_raw_dataset = lambda vin, raw, name: captured.append((vin, raw, name))

    d = await conn.get_vehicle_data("VINX")

    assert d.no_data is False  # genuine dataset parsed
    assert len(captured) == 1
    vin, raw, name = captured[0]
    assert vin == "VINX"
    assert raw == zip_bytes          # the EXACT downloaded bytes, for re-parsing
    assert name == "20260807_V.zip"


@pytest.mark.asyncio
async def test_hook_does_not_fire_on_empty_dataset() -> None:
    conn = EUDataActConnector(_Session(_empty_zip()))  # type: ignore[arg-type]
    calls: list[Any] = []
    conn.on_raw_dataset = lambda *a: calls.append(a)

    d = await conn.get_vehicle_data("VINX")

    assert d.no_data is True         # empty ZIP → no data this poll
    assert calls == []               # nothing genuine to archive


@pytest.mark.asyncio
async def test_no_hook_is_the_safe_default() -> None:
    # A connector with no hook wired (the default) must not raise.
    conn = EUDataActConnector(_Session(_zip_with_soc()))  # type: ignore[arg-type]
    assert conn.on_raw_dataset is None
    d = await conn.get_vehicle_data("VINX")
    assert d.no_data is False
