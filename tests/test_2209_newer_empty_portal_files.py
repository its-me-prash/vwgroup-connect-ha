# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#2209 — how many empty portal files are newer than the one that was read.

``*_no_content_found.zip`` placeholders are dropped before the ranking, so a
real file counts as the newest even when the portal has listed newer empty
ones. The connector now counts those placeholders (by ``createdOn``) against
the file it read and exposes the count as a diagnostic. Health and values are
unchanged.
"""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from homeassistant.components.sensor import SensorStateClass
from homeassistant.const import EntityCategory

from custom_components.vag_connect.entity_base import _CONNECTION_STATUS_KEYS
from custom_components.vag_connect.sensor import _DATA_PRESENT_REQUIRED, SENSOR_DESCRIPTIONS
from tests.test_465_dataset_created_at import _conn, _poll

KEY = "newer_empty_portal_files"
_ROOT = Path(__file__).parent.parent / "custom_components" / "vag_connect"


def _count(listing: list[dict[str, Any]]) -> Any:
    conn = _conn()
    _poll(conn, listing, "2026-11-19T10:15:00+00:00")
    return conn.last_newer_empty_files


def test_counts_the_placeholders_newer_than_the_file_read() -> None:
    listing = [
        {"name": "a.zip", "createdOn": "2026-11-19T10:00:00Z"},
        {"name": "b_no_content_found.zip", "createdOn": "2026-11-19T10:15:00Z"},
        {"name": "c_no_content_found.zip", "createdOn": "2026-11-19T10:30:00Z"},
        {"name": "d_no_content_found.zip", "createdOn": "2026-11-19T09:45:00Z"},
    ]
    assert _count(listing) == 2


def test_older_placeholders_do_not_count() -> None:
    listing = [
        {"name": "a.zip", "createdOn": "2026-11-19T10:00:00Z"},
        {"name": "d_no_content_found.zip", "createdOn": "2026-11-19T09:45:00Z"},
    ]
    assert _count(listing) == 0


def test_no_placeholders_reads_zero() -> None:
    assert _count([{"name": "a.zip", "createdOn": "2026-11-19T10:00:00Z"}]) == 0


def test_a_file_without_a_creation_time_reads_unknown() -> None:
    listing = [
        {"name": "a.zip"},
        {"name": "b_no_content_found.zip", "createdOn": "2026-11-19T10:15:00Z"},
    ]
    assert _count(listing) is None


def test_a_placeholder_without_a_creation_time_is_not_counted() -> None:
    listing = [
        {"name": "a.zip", "createdOn": "2026-11-19T10:00:00Z"},
        {"name": "b_no_content_found.zip"},
    ]
    assert _count(listing) == 0


def test_the_count_follows_the_next_poll() -> None:
    conn = _conn()
    newer = {"name": "b_no_content_found.zip", "createdOn": "2026-11-19T10:15:00Z"}
    _poll(conn, [{"name": "a.zip", "createdOn": "2026-11-19T10:00:00Z"}, newer],
          "2026-11-19T10:20:00+00:00")
    assert conn.last_newer_empty_files == 1
    _poll(conn, [{"name": "e.zip", "createdOn": "2026-11-19T10:30:00Z"}, newer],
          "2026-11-19T10:35:00+00:00")
    assert conn.last_newer_empty_files == 0


def test_health_and_values_are_unchanged_by_newer_placeholders() -> None:
    conn = _conn()
    _poll(
        conn,
        [
            {"name": "a.zip", "createdOn": "2026-11-19T10:00:00Z"},
            {"name": "b_no_content_found.zip", "createdOn": "2026-11-19T10:15:00Z"},
        ],
        "2026-11-19T10:20:00+00:00",
    )
    assert conn.last_no_data_reason == ""
    assert conn.no_data_count == 0
    assert conn.last_dataset_created_at == "2026-11-19T10:00:00+00:00"


# ── exposure ─────────────────────────────────────────────────────────────────


def _publish(portal: object) -> dict[str, Any]:
    from custom_components.vag_connect.coordinator import VagConnectCoordinator

    coord = VagConnectCoordinator.__new__(VagConnectCoordinator)
    coord._cariad_client = SimpleNamespace(_eu_portal=portal)  # type: ignore[attr-defined]
    data: dict[str, Any] = {"vin": "VIN1"}
    coord._apply_portal_diagnostics(data, None, 72 * 3600)
    return data


def test_the_coordinator_helper_publishes_the_count() -> None:
    data = _publish(SimpleNamespace(last_no_data_reason="", last_newer_empty_files=3))
    assert data[KEY] == 3


def test_a_portal_that_has_no_count_yet_publishes_none() -> None:
    assert _publish(SimpleNamespace(last_no_data_reason=""))[KEY] is None


def test_the_sensor_is_a_gated_measurement_diagnostic() -> None:
    desc = next(d for d in SENSOR_DESCRIPTIONS if d.key == KEY)
    assert desc.data_key == KEY
    assert desc.translation_key == KEY
    assert desc.entity_category is EntityCategory.DIAGNOSTIC
    assert desc.state_class is SensorStateClass.MEASUREMENT
    assert desc.native_unit_of_measurement is None
    assert KEY in _DATA_PRESENT_REQUIRED


def test_it_stays_available_while_the_poll_fails() -> None:
    assert KEY in _CONNECTION_STATUS_KEYS


def test_every_language_names_it() -> None:
    files = [_ROOT / "strings.json", *sorted((_ROOT / "translations").glob("*.json"))]
    assert len(files) == 13
    for f in files:
        name = json.loads(f.read_text(encoding="utf-8"))["entity"]["sensor"][KEY]["name"]
        assert name.strip(), f.name


# ── a later poll that lists only placeholders ────────────────────────────────


def test_a_placeholders_only_poll_replaces_the_old_count() -> None:
    conn = _conn()
    _poll(conn, [{"name": "a.zip", "createdOn": "2026-11-19T10:00:00Z"},
                 {"name": "b_no_content_found.zip", "createdOn": "2026-11-19T10:15:00Z"}],
          "2026-11-19T10:20:00+00:00")
    assert conn.last_newer_empty_files == 1
    _poll(conn, [{"name": "b_no_content_found.zip", "createdOn": "2026-11-19T10:15:00Z"},
                 {"name": "c_no_content_found.zip", "createdOn": "2026-11-19T10:30:00Z"},
                 {"name": "d_no_content_found.zip"}],
          "2026-11-19T10:35:00+00:00")
    assert conn.last_newer_empty_files == 3


def test_an_empty_listing_after_a_file_poll_reads_unknown() -> None:
    conn = _conn()
    _poll(conn, [{"name": "a.zip", "createdOn": "2026-11-19T10:00:00Z"},
                 {"name": "b_no_content_found.zip", "createdOn": "2026-11-19T10:15:00Z"}],
          "2026-11-19T10:20:00+00:00")
    assert conn.last_newer_empty_files == 1
    _poll(conn, [], "2026-11-19T10:35:00+00:00")
    assert conn.last_newer_empty_files is None


# ── every path of the CURRENT poll sets the count ────────────────────────────

_FILE = {"name": "a.zip", "createdOn": "2026-11-19T10:00:00Z"}
_NEWER = {"name": "b_no_content_found.zip", "createdOn": "2026-11-19T10:15:00Z"}


def _poll_with(conn: Any, listing: list[dict[str, Any]], download: tuple[Any, ...]) -> None:
    import asyncio
    from unittest.mock import AsyncMock, patch

    from custom_components.vag_connect.cariad.auth._eu_data_act import EUDataActConnector
    from tests.test_465_dataset_created_at import _SLEEP, _VIN, _LIVE_META, _Portal

    conn._session = _Portal(meta=_LIVE_META, listing=listing)
    with (
        patch(_SLEEP, new=AsyncMock()),
        patch.object(
            EUDataActConnector, "_download_dataset_raw", new=AsyncMock(return_value=download)
        ),
        patch.object(EUDataActConnector, "_now_iso", staticmethod(lambda: "2026-11-19T10:40:00+00:00")),
    ):
        asyncio.run(conn.get_vehicle_data(_VIN))


def _empty_zip() -> bytes:
    import io
    import zipfile

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("data.json", json.dumps({"data": []}))
    return buf.getvalue()


def test_a_poll_whose_file_parses_to_no_fields_follows_its_own_listing() -> None:
    conn = _conn()
    _poll(conn, [_FILE, _NEWER], "2026-11-19T10:20:00+00:00")
    assert conn.last_newer_empty_files == 1
    second = [
        {"name": "e.zip", "createdOn": "2026-11-19T10:30:00Z"},
        {"name": "f_no_content_found.zip", "createdOn": "2026-11-19T10:35:00Z"},
        {"name": "g_no_content_found.zip", "createdOn": "2026-11-19T10:36:00Z"},
        {"name": "h_no_content_found.zip", "createdOn": "2026-11-19T10:10:00Z"},
    ]
    _poll_with(conn, second, (_empty_zip(), False, 200))
    assert conn.last_no_data_reason == "empty"
    assert conn.last_newer_empty_files == 2


def test_a_poll_where_every_download_fails_counts_all_listed_placeholders() -> None:
    conn = _conn()
    _poll(conn, [_FILE, _NEWER], "2026-11-19T10:20:00+00:00")
    assert conn.last_newer_empty_files == 1
    _poll_with(
        conn,
        [_FILE, _NEWER, {"name": "c_no_content_found.zip"}, {"name": "x_no_content_found.zip"}],
        (None, True, 503),
    )
    assert conn.last_newer_empty_files == 3


def test_a_failed_download_with_no_placeholders_reads_zero() -> None:
    conn = _conn()
    _poll(conn, [_FILE, _NEWER], "2026-11-19T10:20:00+00:00")
    _poll_with(conn, [_FILE], (None, True, 503))
    assert conn.last_newer_empty_files == 0


def test_a_placeholders_only_poll_counts_the_listed_placeholders() -> None:
    conn = _conn()
    _poll(conn, [{"name": "p_no_content_found.zip"}, _NEWER], "2026-11-19T10:20:00+00:00")
    assert conn.last_newer_empty_files == 2


def test_an_empty_listing_reads_unknown_after_a_failed_download_poll() -> None:
    conn = _conn()
    _poll_with(conn, [_FILE, _NEWER], (None, True, 503))
    assert conn.last_newer_empty_files == 1
    _poll(conn, [], "2026-11-19T10:50:00+00:00")
    assert conn.last_newer_empty_files is None
