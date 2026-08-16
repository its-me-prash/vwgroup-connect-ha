# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Škoda aux-heating (Standheizung) switch is gated on the REAL capability.

History: v3.2.0 shipped a "positive-evidence" heuristic that hid the aux switch
on Škodas that showed no aux telemetry. That was a misdiagnosis — a diesel
Octavia reporter and a gasoline Octavia owner (both aux-equipped) presented
byte-identical telemetry, both with the AC subsystem in a transient INVALID /
403-degraded state, so there was no groundable "no aux heater" signal. The
heuristic wrongly hid a real, wanted feature.

v3.2.1 replaces it with capability gating on the androguard-verified mysmob
CapabilityId ``AUXILIARY_HEATING``:
  - capability unknown (empty / unfetched cache -> None): SHOW (never hide on
    unknown — the universal rule for every other switch)
  - capability explicitly absent from a populated list (False): HIDE
  - capability present (True): SHOW
"""
from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import MagicMock

from custom_components.vag_connect.cariad._capabilities import cap_id_for

VIN = "TMBJJ7NX1M0000001"


def _has(added: list[Any], name: str) -> bool:
    return any(type(e).__name__ == name for e in added)


def _coord(vehicle: dict, aux_cap: bool | None) -> Any:
    c = MagicMock()
    c.vehicles = {VIN: vehicle}
    c.data = c.vehicles
    c.is_read_only = MagicMock(return_value=False)
    c._cariad_client = MagicMock()  # hasattr(client, "command_start_aux_heating") -> True

    def _cap(vin: str, cmd: str):
        # Only the aux command carries the test's capability verdict; every
        # other switch sees None (permissive) so it spawns normally.
        return aux_cap if cmd == "command_start_aux_heating" else None

    c.command_capability_supported = MagicMock(side_effect=_cap)
    c.async_add_listener = MagicMock(return_value=lambda: None)
    return c


def _run(vehicle: dict, aux_cap: bool | None) -> list[Any]:
    from custom_components.vag_connect.switch import async_setup_entry

    entry = MagicMock()
    entry.runtime_data = _coord(vehicle, aux_cap)
    entry.data = {"brand": "skoda"}
    entry.options = {}
    entry.async_on_unload = lambda x: None
    added: list[Any] = []
    asyncio.run(async_setup_entry(MagicMock(), entry, lambda e: added.extend(e)))
    return added


def test_aux_cap_unknown_shows_switch() -> None:
    # Marco's + Wehrfried's degraded/403 Octavias: cache empty -> None -> SHOW.
    added = _run({"vin": VIN}, aux_cap=None)
    assert _has(added, "VagAuxHeatingSwitch")


def test_aux_cap_absent_hides_switch() -> None:
    # A populated capability list that does NOT advertise AUXILIARY_HEATING.
    added = _run({"vin": VIN}, aux_cap=False)
    assert not _has(added, "VagAuxHeatingSwitch")


def test_aux_cap_present_shows_switch() -> None:
    added = _run({"vin": VIN}, aux_cap=True)
    assert _has(added, "VagAuxHeatingSwitch")


def test_skoda_capability_ids_are_real_mysmob_enum_values() -> None:
    # androguard-verified against the 8.15.0 CapabilityId enum (Lnj0/b;).
    assert cap_id_for("skoda", "command_start_aux_heating") == "AUXILIARY_HEATING"
    assert cap_id_for("skoda", "command_start_active_ventilation") == "ACTIVE_VENTILATION"
    assert cap_id_for("skoda", "command_start_window_heating") == "WINDOW_HEATING"
    assert cap_id_for("skoda", "command_start_climate") == "AIR_CONDITIONING"
