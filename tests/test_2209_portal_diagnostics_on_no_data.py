# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#2209 — the portal's own diagnostics described the poll before the empty one.

A poll whose portal file list holds only ``_no_content_found`` placeholders
returns no data. For a car the integration already has data for, the
coordinator then republishes the previous snapshot ("old but visible") and
counts a failed poll. Two things went wrong with the portal diagnostics on
that path:

1. They are written in ``_enrich``, which only runs on a poll that parsed
   data. The republished snapshot kept "Portal feed health" from the last
   good poll (usually "Live") and the no-data counters stood still, while the
   connector had already recorded "no_content" and counted the poll.
2. After the failure tolerance and the stale-cache window, these entities went
   unavailable with the rest of the car, at the one moment they explain why.

Pinned here: the shared helper, the manual-refresh path end to end, the poll
loop's no-data branch (structurally, the loop does not return), and the
availability exemption.
"""
from __future__ import annotations

import asyncio
import pathlib
import threading
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from custom_components.vag_connect.cariad.models import VehicleData
from custom_components.vag_connect.entity_base import (
    _CONNECTION_STATUS_KEYS,
    VagConnectEntity,
)

_PORTAL_KEYS = (
    "portal_health",
    "minutes_since_last_snapshot",
    "last_snapshot_at",
    "last_dataset_created_at",
    "last_no_data_at",
    "no_data_count",
)


def _portal(**kw: object) -> SimpleNamespace:
    """A portal connector after an all-placeholder poll."""
    base = {
        "last_no_data_reason": "no_content",
        "no_data_count": 4,
        "last_no_data_at": "2026-11-24T13:00:00+00:00",
        "last_snapshot_at": "2026-11-24T10:00:00+00:00",
        "last_dataset_created_at": "2026-11-24T09:58:00+00:00",
        "data_request_started_at": None,
        "last_valued_count": None,
        "last_valueless_count": None,
        "last_valueless_fields": None,
    }
    base.update(kw)
    return SimpleNamespace(**base)


def _snapshot_after_a_good_poll() -> dict:
    return {
        "vin": "VIN1",
        "battery_soc": 80,
        "odometer_km": 12345,
        "portal_health": "ok",
        "no_data_count": 0,
        "last_no_data_at": None,
    }


# ── the helper ───────────────────────────────────────────────────────────────


def _bare_coordinator(client: object) -> object:
    from custom_components.vag_connect.coordinator import VagConnectCoordinator

    coord = VagConnectCoordinator.__new__(VagConnectCoordinator)
    coord._cariad_client = client
    return coord


def test_the_helper_writes_the_connectors_current_outcome() -> None:
    coord = _bare_coordinator(SimpleNamespace(_eu_portal=_portal()))
    data = _snapshot_after_a_good_poll()

    got = coord._apply_portal_diagnostics(data, None, 72 * 3600)

    assert got is not None
    assert data["portal_health"] == "empty_snapshots"
    assert data["no_data_count"] == 4
    assert data["last_no_data_at"] == "2026-11-24T13:00:00+00:00"
    assert data["last_snapshot_at"] == "2026-11-24T10:00:00+00:00"
    assert data["battery_soc"] == 80, "only the portal diagnostics change"


def test_the_helper_leaves_a_non_portal_car_alone() -> None:
    coord = _bare_coordinator(SimpleNamespace())  # no portal connector
    data = _snapshot_after_a_good_poll()
    before = dict(data)

    assert coord._apply_portal_diagnostics(data, None, 72 * 3600) is None
    assert data == before


def test_a_supplementary_portal_is_used_too() -> None:
    coord = _bare_coordinator(SimpleNamespace(_supplementary_eu_portal=_portal()))
    data = _snapshot_after_a_good_poll()
    coord._apply_portal_diagnostics(data, None, 72 * 3600)
    assert data["portal_health"] == "empty_snapshots"


# ── the manual refresh, end to end ───────────────────────────────────────────


def _refresh_coordinator() -> object:
    from custom_components.vag_connect.coordinator import VagConnectCoordinator

    coord = VagConnectCoordinator.__new__(VagConnectCoordinator)
    coord.hass = MagicMock()
    coord.entry = MagicMock()
    coord._vehicles_lock = threading.Lock()
    coord._was_available = True
    coord._started = True
    coord._cariad_client = MagicMock()
    coord._cariad_client._eu_portal = _portal()
    coord._persist_website_cookies = MagicMock()
    coord._persist_supplementary_cookies = MagicMock()
    coord._persist_companion_rate_limit = MagicMock()
    coord.vehicles = {"VIN1": _snapshot_after_a_good_poll()}
    return coord


def test_a_no_data_refresh_shows_this_refreshs_portal_outcome() -> None:
    coord = _refresh_coordinator()
    coord._cariad_client.get_status = AsyncMock(
        return_value=VehicleData(vin="VIN1", no_data=True)
    )

    result = asyncio.run(coord._async_update_data())

    kept = coord.vehicles["VIN1"]
    assert kept["portal_health"] == "empty_snapshots"
    assert kept["no_data_count"] == 4
    assert kept["last_no_data_at"] == "2026-11-24T13:00:00+00:00"
    # the last good values stay visible (#702), unchanged by this fix
    assert kept["battery_soc"] == 80
    assert result["VIN1"]["portal_health"] == "empty_snapshots"


# ── the poll loop's no-data branch ───────────────────────────────────────────


def test_the_poll_loops_no_data_branch_refreshes_the_diagnostics() -> None:
    """``_poll_loop`` never returns, so its branch is pinned by its source.

    The branch that republishes ``old`` after a no-data poll must call the
    helper before the snapshot goes out. Matched on the republish line that
    follows the supplementary revive, which only the no-data branch has.
    """
    import custom_components.vag_connect.coordinator as coord_mod

    lines = pathlib.Path(coord_mod.__file__).read_text(encoding="utf-8").splitlines()
    anchors = [
        i for i, line in enumerate(lines)
        if line.strip() == "fresh[vin] = old"
        and any("_revive_from_supplementary" in lines[j] for j in range(max(0, i - 15), i))
    ]
    assert len(anchors) == 1, f"expected the one revive-then-republish branch, got {anchors}"
    window = "\n".join(lines[anchors[0] - 10:anchors[0] + 1])
    assert "self._apply_portal_diagnostics(" in window


# ── availability ─────────────────────────────────────────────────────────────


def _entity(key: str) -> VagConnectEntity:
    coord = MagicMock()
    coord.last_update_success = False
    coord.is_vehicle_available.return_value = False
    coord.vehicle_last_good_at = {}
    e = VagConnectEntity.__new__(VagConnectEntity)
    e.coordinator = coord
    e._vin = "VIN1"
    e._command_id = None
    desc = MagicMock()
    desc.key = key
    e.entity_description = desc  # type: ignore[attr-defined]
    return e


def test_the_portal_diagnostics_stay_available_when_the_car_goes_dark() -> None:
    for key in _PORTAL_KEYS:
        assert key in _CONNECTION_STATUS_KEYS, key
        assert _entity(key).available is True, key


def test_an_ordinary_reading_still_goes_unavailable() -> None:
    assert _entity("battery_soc").available is False
