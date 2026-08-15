# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Don't spawn a Standheizung switch on a Škoda that has no aux heater.

A diesel Octavia owner (via the HA Tipps und Tricks Facebook group) got a
non-working "auxiliary heating" switch. Škoda declares auxiliary_heating=False
and has no aux-heating cap-id, so command_capability_supported returns None
(don't-hide) and the switch spawned anyway. The gate now requires positive
evidence on a declared-False brand, while brands that declare True (VW/Audi) or
carry a mapped cap-id (SEAT/CUPRA) are untouched.
"""
from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import MagicMock

VIN = "TMBJJ7NX1M0000001"


def _has(added: list[Any], name: str) -> bool:
    return any(type(e).__name__ == name for e in added)


def _coord(vehicle: dict) -> Any:
    c = MagicMock()
    c.vehicles = {VIN: vehicle}
    c.data = c.vehicles
    c.is_read_only = MagicMock(return_value=False)
    # A real backend client so hasattr(client, "command_start_aux_heating") is
    # true; command_capability_supported → None mirrors "cap-id absent, don't
    # hide" for Škoda and "present but unknown" for VW.
    c._cariad_client = MagicMock()
    c.command_capability_supported = MagicMock(return_value=None)
    c.async_add_listener = MagicMock(return_value=lambda: None)
    return c


def _run(brand: str, vehicle: dict) -> list[Any]:
    from custom_components.vag_connect.switch import async_setup_entry

    entry = MagicMock()
    coord = _coord(vehicle)
    entry.runtime_data = coord
    entry.data = {"brand": brand}
    entry.options = {}
    entry.async_on_unload = lambda x: None
    added: list[Any] = []
    asyncio.run(async_setup_entry(MagicMock(), entry, lambda e: added.extend(e)))
    return added


def test_skoda_diesel_no_evidence_no_aux_switch() -> None:
    added = _run("skoda", {"vin": VIN})
    assert not _has(added, "VagAuxHeatingSwitch")


def test_skoda_with_positive_evidence_spawns_aux() -> None:
    added = _run("skoda", {"vin": VIN, "aux_heating_active": True})
    assert _has(added, "VagAuxHeatingSwitch")
    added = _run("skoda", {"vin": VIN, "auxiliary_heating_status": "off"})
    assert _has(added, "VagAuxHeatingSwitch")


def test_volkswagen_always_spawns_aux() -> None:
    # VW declares auxiliary_heating=True → the backend cap-doc arbitrates it,
    # exactly as before; the gate must not regress it away.
    added = _run("volkswagen", {"vin": VIN})
    assert _has(added, "VagAuxHeatingSwitch")


def test_skoda_cap_doc_true_overrides_missing_read() -> None:
    # If the backend ever DOES report the capability true for a Škoda, honour it
    # even without a read value.
    from custom_components.vag_connect.switch import async_setup_entry

    entry = MagicMock()
    coord = _coord({"vin": VIN})
    coord.command_capability_supported = MagicMock(
        side_effect=lambda vin, cmd: True if cmd == "command_start_aux_heating" else None
    )
    entry.runtime_data = coord
    entry.data = {"brand": "skoda"}
    entry.options = {}
    entry.async_on_unload = lambda x: None
    added: list[Any] = []
    asyncio.run(async_setup_entry(MagicMock(), entry, lambda e: added.extend(e)))
    assert _has(added, "VagAuxHeatingSwitch")
