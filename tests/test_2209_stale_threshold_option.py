# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#2209 (@borpin) — the stale threshold is an option, 72 h stays the default.

"Data stale" and the portal health state "Stale" used to switch on at a capture
age of ``max(72 h, 8 x scan interval)``, with no way to shorten that for a car
whose charging schedule cannot wait three days. The figure now comes from one
helper that reads the option ``stale_threshold_hours`` (default 72, 1 to 168).
The ``8 x scan interval`` rule stays on top of it, and the Repair keeps its own
72 h floor: lowering the option never raises a Repair earlier.
"""
from __future__ import annotations

import asyncio
import json
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.vag_connect.config_flow import VagConnectOptionsFlow
from custom_components.vag_connect.coordinator import VagConnectCoordinator

VIN = "WVWZZZ0000000345"
OPT = "stale_threshold_hours"
INTEGRATION = Path(__file__).resolve().parent.parent / "custom_components" / "vag_connect"


def _iso(hours_ago: float) -> str:
    dt = datetime.now(tz=timezone.utc) - timedelta(hours=hours_ago)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _coord(options: dict | None = None, interval_min: int = 10) -> VagConnectCoordinator:
    c = VagConnectCoordinator.__new__(VagConnectCoordinator)
    c.hass = MagicMock()
    c.hass.async_add_executor_job = AsyncMock(return_value=None)
    c.entry = MagicMock()
    c.entry.data = {"brand": "volkswagen", "username": "t@t.com", "password": "x", "spin": ""}
    c.entry.options = {"scan_interval": interval_min, **(options or {})}
    c.entry.entry_id = "entryX"
    c._vehicles_lock = threading.Lock()
    c._cariad_client = MagicMock()
    c._cariad_client._image_data = {}
    c._cariad_client._eu_portal = None
    c._cariad_client._supplementary_eu_portal = None
    c.vehicle_static_info = {}
    c._was_available = True
    c.data = None
    c.vehicles = {}
    return c


def _enrich(c: VagConnectCoordinator, age_h: float):
    data = {"vin": VIN, "latitude": None, "longitude": None, "last_seen_at": _iso(age_h)}
    with patch("custom_components.vag_connect.repairs.raise_issue_stale_data") as raise_m, \
            patch("custom_components.vag_connect.repairs.clear_stale_data_issue") as clear_m:
        out = asyncio.run(c._enrich(data))
    return out, raise_m, clear_m


# ── the helper ─────────────────────────────────────────────────────────────


def test_default_is_unchanged_72_hours() -> None:
    assert _coord()._stale_threshold_s() == 72 * 3600


def test_the_option_moves_the_threshold_both_ways() -> None:
    assert _coord({OPT: 24})._stale_threshold_s() == 24 * 3600
    assert _coord({OPT: 120})._stale_threshold_s() == 120 * 3600


def test_the_scan_interval_rule_stays_on_top() -> None:
    # 10 h interval -> 8 x = 80 h beats a 24 h option, but not a 168 h one
    assert _coord({OPT: 24}, interval_min=600)._stale_threshold_s() == 80 * 3600
    assert _coord({OPT: 168}, interval_min=600)._stale_threshold_s() == 168 * 3600


def test_the_option_is_read_from_data_when_options_hold_none() -> None:
    c = _coord()
    c.entry.options = {"scan_interval": 10}
    c.entry.data = {**c.entry.data, OPT: 48}
    assert c._stale_threshold_s() == 48 * 3600


@pytest.mark.parametrize(
    ("raw", "hours"),
    [(0, 1), (-5, 1), (500, 168), (36.0, 36), ("abc", 72), (None, 72), (True, 72)],
)
def test_a_value_outside_the_range_is_clamped_or_ignored(raw, hours) -> None:
    # a 1 h floor sits under the 8 x 10 min interval rule (80 min), which wins
    expected = max(hours * 3600, 8 * 10 * 60)
    assert _coord({OPT: raw})._stale_threshold_s() == expected


# ── the "Data stale" verdict ───────────────────────────────────────────────


def test_a_lower_option_flags_a_30_hour_old_capture() -> None:
    assert _enrich(_coord(), 30)[0]["data_stale"] is False
    assert _enrich(_coord({OPT: 24}), 30)[0]["data_stale"] is True


def test_a_higher_option_holds_a_100_hour_old_capture() -> None:
    assert _enrich(_coord(), 100)[0]["data_stale"] is True
    assert _enrich(_coord({OPT: 168}), 100)[0]["data_stale"] is False


def test_a_republished_snapshot_follows_the_option() -> None:
    snap = {"vin": VIN, "last_seen_at": _iso(30)}
    _coord({OPT: 24})._redecide_stale(snap)
    assert snap["data_stale"] is True
    snap = {"vin": VIN, "last_seen_at": _iso(30)}
    _coord()._redecide_stale(snap)
    assert snap["data_stale"] is False


# ── the portal health state ────────────────────────────────────────────────


def test_portal_health_gets_the_option_threshold() -> None:
    c = _coord({OPT: 24})
    seen: list[float] = []

    def _spy(data, age_s, threshold_s):
        seen.append(threshold_s)
        return None

    with patch.object(c, "_apply_portal_diagnostics", side_effect=_spy):
        _enrich(c, 30)
    assert seen == [24 * 3600]


# ── the Repair keeps its own 72 h floor ────────────────────────────────────


def test_lowering_the_option_does_not_raise_the_repair_earlier() -> None:
    out, raise_m, clear_m = _enrich(_coord({OPT: 24}), 30)
    assert out["data_stale"] is True
    raise_m.assert_not_called()
    clear_m.assert_called_once()


def test_the_repair_still_fires_at_72_hours_with_a_low_option() -> None:
    _out, raise_m, _clear = _enrich(_coord({OPT: 24}), 80)
    raise_m.assert_called_once()


def test_the_repair_still_fires_at_72_hours_by_default() -> None:
    _out, raise_m, _clear = _enrich(_coord(), 80)
    raise_m.assert_called_once()


def test_a_higher_option_holds_the_repair_back_with_the_verdict() -> None:
    out, raise_m, _clear = _enrich(_coord({OPT: 168}), 80)
    assert out["data_stale"] is False
    raise_m.assert_not_called()


# ── the options flow ───────────────────────────────────────────────────────


def _flow(options: dict | None = None) -> VagConnectOptionsFlow:
    entry = MagicMock()
    entry.entry_id = "E1"
    entry.data = {"brand": "volkswagen", "scan_interval": 10}
    entry.options = options or {}
    entry.runtime_data = MagicMock(vehicles={})
    flow = VagConnectOptionsFlow(entry)
    hass = MagicMock()
    hass.config_entries.async_entries = MagicMock(return_value=[entry])
    flow.hass = hass
    return flow


def test_the_form_offers_the_option_with_72_as_default() -> None:
    flow = _flow()
    result = asyncio.run(flow.async_step_init(None))
    keys = {getattr(k, "schema", None): k for k in result["data_schema"].schema}
    assert OPT in keys
    assert keys[OPT].default() == 72
    sel = result["data_schema"].schema[keys[OPT]]
    assert sel.config["min"] == 1
    assert sel.config["max"] == 168
    assert sel.config["unit_of_measurement"] == "h"


def test_the_flow_stores_the_value() -> None:
    flow = _flow()
    with patch.object(flow, "async_create_entry", return_value={"type": "create_entry"}) as create:
        asyncio.run(flow.async_step_init({"scan_interval": 10, OPT: 24}))
    assert create.call_args.kwargs["data"][OPT] == 24


# ── wording ────────────────────────────────────────────────────────────────


def _init(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))["options"]["step"]["init"]


@pytest.mark.parametrize(
    "path",
    [INTEGRATION / "strings.json", *sorted((INTEGRATION / "translations").glob("*.json"))],
    ids=lambda p: p.name,
)
def test_label_and_description_exist_in_every_language(path: Path) -> None:
    init = _init(path)
    assert init["data"].get(OPT, "").strip()
    desc = init["data_description"].get(OPT, "")
    assert "72" in desc


def test_all_twelve_translations_are_there() -> None:
    names = {p.stem for p in (INTEGRATION / "translations").glob("*.json")}
    assert {"cs", "da", "de", "en", "es", "fi", "fr", "it", "nb", "nl", "pl", "sv"} <= names
