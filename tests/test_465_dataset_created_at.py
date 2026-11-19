# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#465 — "Last snapshot received" could not show whether a NEW delivery came.

``last_snapshot_at`` is the time of our last successful poll. It moves on every
poll, also when the portal handed us the very same file again, so a user could
not tell a fresh delivery from a re-read. The listing's ``createdOn`` was only a
sort key. The connector now keeps the ``createdOn`` of the file it parsed as
``last_dataset_created_at``: it stays put on a re-read and jumps on a new file.
``last_snapshot_at`` keeps its meaning.
"""
from __future__ import annotations

import asyncio
import io
import json
import zipfile
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from custom_components.vag_connect.cariad.auth import _eu_data_act as m
from custom_components.vag_connect.cariad.auth._eu_data_act import (
    EUDataActConnector,
)
from custom_components.vag_connect.sensor import _DATA_PRESENT_REQUIRED
from tests.test_1932_an_unreachable_portal_is_not_a_missing_request import (
    _LIVE_META,
    _VIN,
    _Portal,
)

_SLEEP = f"{m.__name__}.asyncio.sleep"
_PAYLOAD = {
    "data": [
        {
            "dataFieldName": "mileage.odometer",
            "carCapturedTimestamp": "2026-11-19T09:00:00Z",
            "value": "12345",
        }
    ]
}


def _zip() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("data.json", json.dumps(_PAYLOAD))
    return buf.getvalue()


def _poll(conn: EUDataActConnector, listing: list[dict[str, Any]], now: str) -> None:
    conn._session = _Portal(meta=_LIVE_META, listing=listing)  # type: ignore[assignment]
    with (
        patch(_SLEEP, new=AsyncMock()),
        patch.object(
            EUDataActConnector,
            "_download_dataset_raw",
            new=AsyncMock(return_value=(_zip(), False, 200)),
        ),
        patch.object(EUDataActConnector, "_now_iso", staticmethod(lambda: now)),
    ):
        asyncio.run(conn.get_vehicle_data(_VIN))


def _conn() -> EUDataActConnector:
    return EUDataActConnector(MagicMock(), brand="volkswagen")  # type: ignore[arg-type]


def test_re_read_of_the_same_file_moves_the_snapshot_not_the_creation_time():
    conn = _conn()
    listing = [{"name": "a.zip", "createdOn": "2026-11-19T10:00:00Z"}]
    _poll(conn, listing, "2026-11-19T10:15:00+00:00")
    first_created = conn.last_dataset_created_at
    assert first_created == "2026-11-19T10:00:00+00:00"
    assert conn.last_snapshot_at == "2026-11-19T10:15:00+00:00"

    _poll(conn, listing, "2026-11-19T10:30:00+00:00")
    assert conn.last_snapshot_at == "2026-11-19T10:30:00+00:00"  # moved
    assert conn.last_dataset_created_at == first_created  # did not


def test_a_new_file_moves_the_creation_time():
    conn = _conn()
    _poll(
        conn,
        [{"name": "a.zip", "createdOn": "2026-11-19T10:00:00Z"}],
        "2026-11-19T10:15:00+00:00",
    )
    _poll(
        conn,
        [
            {"name": "a.zip", "createdOn": "2026-11-19T10:00:00Z"},
            {"name": "b.zip", "createdOn": "2026-11-19T10:15:00Z"},
        ],
        "2026-11-19T10:20:00+00:00",
    )
    assert conn.last_dataset_created_at == "2026-11-19T10:15:00+00:00"


def test_epoch_created_on_is_normalised_to_utc_iso():
    conn = _conn()
    ts = datetime(2026, 11, 19, 8, 0, tzinfo=timezone.utc)
    _poll(
        conn,
        [{"name": "a.zip", "createdOn": int(ts.timestamp() * 1000)}],
        "2026-11-19T10:15:00+00:00",
    )
    assert conn.last_dataset_created_at == ts.isoformat()


def test_a_file_without_created_on_reads_unknown_not_the_previous_time():
    conn = _conn()
    _poll(
        conn,
        [{"name": "a.zip", "createdOn": "2026-11-19T10:00:00Z"}],
        "2026-11-19T10:15:00+00:00",
    )
    _poll(conn, [{"name": "b.zip"}], "2026-11-19T10:30:00+00:00")
    assert conn.last_dataset_created_at is None


def test_the_sensor_spawns_only_when_the_value_arrives():
    assert "last_dataset_created_at" in _DATA_PRESENT_REQUIRED


def _enrich_with_portal(portal: Any) -> dict[str, Any]:
    import threading
    from types import SimpleNamespace

    from custom_components.vag_connect.coordinator import VagConnectCoordinator

    coord = VagConnectCoordinator.__new__(VagConnectCoordinator)
    coord.hass = MagicMock()
    coord.hass.async_add_executor_job = AsyncMock(return_value=None)
    coord.entry = MagicMock()
    coord.entry.data = {"brand": "volkswagen", "username": "t@t.com",
                        "password": "x", "spin": "", "update_interval": 300}
    coord._vehicles_lock = threading.Lock()
    coord._cariad_client = SimpleNamespace(
        _image_data={}, _eu_portal=portal, _supplementary_eu_portal=None
    )
    coord.vehicle_static_info = {}
    coord._was_available = True
    coord.data = None
    data = {"vin": _VIN, "latitude": None, "longitude": None}
    return asyncio.run(coord._enrich(data))


def test_the_coordinator_hands_the_creation_time_to_the_sensor_data():
    from types import SimpleNamespace

    portal = SimpleNamespace(
        last_dataset_created_at="2026-11-19T10:00:00+00:00",
        last_snapshot_at="2026-11-19T10:15:00+00:00",
    )
    out = _enrich_with_portal(portal)
    assert out["last_dataset_created_at"] == "2026-11-19T10:00:00+00:00"
    assert out["last_snapshot_at"] == "2026-11-19T10:15:00+00:00"


def test_the_sensor_description_reads_that_data_key():
    from custom_components.vag_connect.sensor import SENSOR_DESCRIPTIONS

    d = next(x for x in SENSOR_DESCRIPTIONS if x.key == "last_dataset_created_at")
    assert d.data_key == "last_dataset_created_at"
