# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#1429 — a device of the integration can be deleted from the UI.

Home Assistant hides "Delete" unless the integration implements
``async_remove_config_entry_device``. A car that no longer delivers data, or a
switched-off device, may go; a live car, the account settings device and a
foreign device stay.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any

from custom_components.vag_connect import async_remove_config_entry_device
from custom_components.vag_connect.const import DOMAIN

VIN_LIVE = "WVWLIVE0000000001"
VIN_GONE = "WVWGONE0000000002"


def _entry(data: Any, vehicles: Any = None, loaded: bool = True) -> Any:
    e = SimpleNamespace(entry_id="E1")
    if loaded:
        e.runtime_data = SimpleNamespace(data=data, vehicles=vehicles or {})
    return e


def _dev(identifiers: set, disabled_by: Any = None) -> Any:
    return SimpleNamespace(identifiers=identifiers, disabled_by=disabled_by)


def _run(entry: Any, dev: Any) -> bool:
    return asyncio.run(async_remove_config_entry_device(None, entry, dev))  # type: ignore[arg-type]


def test_active_vehicle_with_data_is_kept() -> None:
    e = _entry({VIN_LIVE: {}, "_meta": {}})
    assert _run(e, _dev({(DOMAIN, VIN_LIVE)})) is False


def test_vin_missing_from_data_may_go() -> None:
    e = _entry({VIN_LIVE: {}, "_meta": {}}, {VIN_LIVE: {}})
    assert _run(e, _dev({(DOMAIN, VIN_GONE)})) is True


def test_vin_still_polled_is_kept_even_without_data_yet() -> None:
    e = _entry({}, {VIN_LIVE: {}})
    assert _run(e, _dev({(DOMAIN, VIN_LIVE)})) is False


def test_disabled_device_may_go_even_if_vin_has_data() -> None:
    e = _entry({VIN_LIVE: {}})
    assert _run(e, _dev({(DOMAIN, VIN_LIVE)}, disabled_by="user")) is True


def test_settings_device_is_never_removable() -> None:
    e = _entry({VIN_LIVE: {}})
    d = _dev({(DOMAIN, "E1_settings")}, disabled_by="user")
    assert _run(e, d) is False
    assert _run(e, _dev({(DOMAIN, "E1_settings")})) is False


def test_foreign_domain_device_is_kept() -> None:
    e = _entry({VIN_LIVE: {}})
    assert _run(e, _dev({("drivepulse", VIN_GONE)})) is False
    assert _run(e, _dev({("drivepulse", VIN_GONE)}, disabled_by="user")) is False


def test_unloaded_entry_cannot_be_judged_unless_disabled() -> None:
    e = _entry(None, loaded=False)
    assert _run(e, _dev({(DOMAIN, VIN_GONE)})) is False
    assert _run(e, _dev({(DOMAIN, VIN_GONE)}, disabled_by="user")) is True
