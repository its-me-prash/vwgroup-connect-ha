# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""v2.20.0 — durable-MBB per-VIN command pre-test.

When commands route through the durable MBB (legacy Car-Net) channel, the
CARIAD-BFF ``/capabilities`` document is empty (the MBB bearer is ACL-closed on
the data plane — every read 403s ``XID_APP_VW``, live-confirmed on a Golf 7 GTE
2026-07-19). So ``command_capability_supported`` gates strictly on the MBB
``operationList`` (the rolesrights service directory the MBB bearer CAN read).

Policy = *maximal streng* (Prash, 2026-07-19): a command entity is created ONLY
on positive operationList proof that the car currently grants that command's
service. No proof → hide (never invent a two-way control the car can't run).

The Golf 7 GTE live operationList granted rclima_v1 (climate) + rbatterycharge_v1
(charge) + timerprogramming_v1 (departure timer) but did NOT list rlu_v1 (lock)
→ the lock entity must be hidden while climate/charge show.
"""

from __future__ import annotations

import asyncio
import threading
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from custom_components.vag_connect.cariad._mbb import parse_mbb_operationlist
from custom_components.vag_connect.coordinator import (
    VagConnectCoordinator,
    _mbb_command_capability,
)

VIN = "WVWZZZAUZFW805377"


def _oplist(services: list[dict]):
    """Build a real MbbOperationList from a synthetic operationList response."""
    return parse_mbb_operationlist(
        {"operationList": {"vin": VIN, "role": "PRIMARY_USER",
                           "status": "ENABLED", "serviceInfo": services}},
        VIN,
    )


# The Golf 7 GTE live shape: climate + charge + timer Enabled, NO rlu_v1.
_GOLF_SERVICES = [
    {"serviceId": "rclima_v1", "serviceStatus": {"status": "Enabled"},
     "operation": [{"id": "P_START_CLIMA_NOSET", "permission": "granted"}]},
    {"serviceId": "rbatterycharge_v1", "serviceStatus": {"status": "Enabled"},
     "operation": [{"id": "P_START", "permission": "granted"}]},
    {"serviceId": "timerprogramming_v1", "serviceStatus": {"status": "Enabled"},
     "operation": [{"id": "P_SETTINGS_EL", "permission": "granted"}]},
]


def _coord(*, mbb_armed: bool, strategy: str = "device_grant_portal",
           oplist=None, brand: str = "volkswagen"):
    """Real coordinator instance (via __new__, no __init__) so bound self-method
    calls inside the gate resolve normally."""
    stub = VagConnectCoordinator.__new__(VagConnectCoordinator)
    stub.entry = MagicMock()
    # CONF_MBB_COMMAND_CHANNEL == "mbb_command_channel"; the armed-alongside
    # path is gated on this explicit flag, not on the mock client attribute.
    stub.entry.data = {"brand": brand, "mbb_command_channel": mbb_armed}
    stub.vehicles = {VIN: {}}

    client = SimpleNamespace()
    client._tokens = SimpleNamespace(strategy=strategy)
    if mbb_armed:
        cmd = SimpleNamespace()
        cmd._mbb_manual_vins = [VIN]
        if oplist is not None:
            future = datetime.now(tz=timezone.utc) + timedelta(hours=12)
            cmd._mbb_oplist_cache = {VIN: (oplist, future)}
        else:
            cmd._mbb_oplist_cache = {}
        client._mbb_command = cmd
    else:
        client._mbb_command = None
    stub._cariad_client = client
    return stub


def _cap(stub, command_id):
    return _mbb_command_capability(stub, VIN, command_id)


class TestMbbGateGolfScenario:
    def test_climate_granted_shows(self) -> None:
        stub = _coord(mbb_armed=True, oplist=_oplist(_GOLF_SERVICES))
        assert _cap(stub, "command_start_climate") is True

    def test_charge_granted_shows(self) -> None:
        stub = _coord(mbb_armed=True, oplist=_oplist(_GOLF_SERVICES))
        assert _cap(stub, "command_start_charging") is True

    def test_target_soc_granted_shows(self) -> None:
        # target-soc IS a real MBB op (charge_target_soc / P_SETTINGS).
        stub = _coord(mbb_armed=True, oplist=_oplist(_GOLF_SERVICES))
        assert _cap(stub, "command_set_target_soc") is True

    def test_lock_absent_service_hidden(self) -> None:
        # rlu_v1 not in the operationList → lock must be hidden.
        stub = _coord(mbb_armed=True, oplist=_oplist(_GOLF_SERVICES))
        assert _cap(stub, "command_lock") is False


class TestMbbGateBffOnlyCommandsHidden:
    """Commands that route to the CARIAD BFF (which rejects the MBB bearer) or
    have no VW-EU method must be hidden on an MBB-command entry even when the
    operationList grants a related service — they could only ever error."""

    def test_departure_timer_hidden_despite_service_granted(self) -> None:
        # timerprogramming_v1 IS granted, but command_set_departure_timer is
        # BFF-backed → hide (no MBB command wired to it).
        stub = _coord(mbb_armed=True, oplist=_oplist(_GOLF_SERVICES))
        assert _cap(stub, "command_set_departure_timer") is False

    def test_climate_temperature_hidden(self) -> None:
        # MBB climate is temperature-less (P_START_CLIMA_NOSET); set-temp is BFF.
        stub = _coord(mbb_armed=True, oplist=_oplist(_GOLF_SERVICES))
        assert _cap(stub, "command_set_climate_temperature") is False

    def test_charge_settings_bff_only_hidden(self) -> None:
        # min-soc / max-current / battery-care are BFF-backed or unimplemented →
        # hidden even though rbatterycharge_v1 is granted.
        stub = _coord(mbb_armed=True, oplist=_oplist(_GOLF_SERVICES))
        assert _cap(stub, "command_set_min_soc") is False
        assert _cap(stub, "command_set_max_charge_current") is False
        assert _cap(stub, "command_set_battery_care") is False

    def test_aux_heating_and_ventilation_hidden(self) -> None:
        stub = _coord(mbb_armed=True, oplist=_oplist(_GOLF_SERVICES))
        assert _cap(stub, "command_start_aux_heating") is False
        assert _cap(stub, "command_start_ventilation") is False


class TestMbbGateStrictness:
    def test_no_oplist_cached_hidden(self) -> None:
        # MEB / not-yet-fetched → no proof → strict hide.
        stub = _coord(mbb_armed=True, oplist=None)
        assert _cap(stub, "command_start_climate") is False
        assert _cap(stub, "command_start_charging") is False

    def test_disabled_service_hidden(self) -> None:
        services = [
            {"serviceId": "rclima_v1", "serviceStatus": {"status": "Disabled"},
             "operation": [{"id": "P_START_CLIMA_NOSET", "permission": "granted"}]},
        ]
        stub = _coord(mbb_armed=True, oplist=_oplist(services))
        assert _cap(stub, "command_start_climate") is False

    def test_flash_and_wake_never_on_mbb(self) -> None:
        stub = _coord(mbb_armed=True, oplist=_oplist(_GOLF_SERVICES))
        assert _cap(stub, "command_flash") is False
        assert _cap(stub, "command_wake") is False


class TestMbbGateScoping:
    def test_non_mbb_returns_none(self) -> None:
        # No MBB command channel + non-mbb strategy → gate abstains (None) so
        # the BFF capability gate applies unchanged.
        stub = _coord(mbb_armed=False, strategy="device_grant_portal")
        assert _cap(stub, "command_start_climate") is None
        assert _cap(stub, "command_lock") is None

    def test_mbb_primary_uses_own_cache(self) -> None:
        # Audi-Car-Net-style: strategy == 'mbb', the primary client itself holds
        # the operationList cache.
        stub = VagConnectCoordinator.__new__(VagConnectCoordinator)
        stub.entry = MagicMock()
        stub.entry.data = {"brand": "audi"}
        stub.vehicles = {VIN: {}}
        client = SimpleNamespace()
        client._tokens = SimpleNamespace(strategy="mbb")
        client._mbb_command = None
        future = datetime.now(tz=timezone.utc) + timedelta(hours=12)
        client._mbb_oplist_cache = {VIN: (_oplist(_GOLF_SERVICES), future)}
        stub._cariad_client = client
        assert _mbb_command_capability(stub, VIN, "command_start_climate") is True
        assert _mbb_command_capability(stub, VIN, "command_lock") is False

    def test_unmapped_command_abstains(self) -> None:
        # A command not in the MBB map must not be force-hidden by this gate.
        stub = _coord(mbb_armed=True, oplist=_oplist(_GOLF_SERVICES))
        assert _cap(stub, "command_some_future_thing") is None


class TestCommandCapabilitySupportedIntegration:
    """The public entry point must return the strict MBB verdict for MBB cars,
    bypassing the (empty) BFF capability gate."""

    def test_public_gate_hides_lock_shows_climate(self) -> None:
        stub = _coord(mbb_armed=True, oplist=_oplist(_GOLF_SERVICES))
        # command_capability_supported also consults the quirk table + brand;
        # brand=volkswagen, no quirk suppresses these.
        assert stub.command_capability_supported(
            VIN, "command_start_climate") is True
        assert stub.command_capability_supported(VIN, "command_lock") is False

    def test_public_gate_meb_hides_all(self) -> None:
        stub = _coord(mbb_armed=True, oplist=None)
        assert stub.command_capability_supported(
            VIN, "command_start_climate") is False
        assert stub.command_capability_supported(
            VIN, "command_start_charging") is False


class TestRefreshWarmVinFallback:
    """v2.20.0 Bug-1 fix — the portal-primary + MBB-command config never sets
    CONF_MBB_VINS, so the armed connector's _mbb_manual_vins is empty. The warm
    must then fall back to self.vehicles (populated by setup before the warm
    now runs) — otherwise the operationList is never fetched and every command
    entity is strict-hidden on first setup."""

    def test_warm_falls_back_to_self_vehicles(self) -> None:
        stub = VagConnectCoordinator.__new__(VagConnectCoordinator)
        stub.entry = MagicMock()
        stub.entry.data = {"brand": "volkswagen", "mbb_command_channel": True}
        stub.vehicles = {VIN: {}, "WVWZZZ2NDVIN00000": {}}
        stub._vehicles_lock = threading.Lock()
        cmd = SimpleNamespace()
        cmd._mbb_manual_vins = []          # portal+MBB config: no CONF_MBB_VINS
        cmd._get_mbb_operationlist = AsyncMock(return_value=None)
        client = SimpleNamespace()
        client._tokens = SimpleNamespace(strategy="device_grant_portal")
        client._mbb_command = cmd
        stub._cariad_client = client

        asyncio.run(stub._refresh_mbb_command_capabilities())

        # Warmed BOTH VINs from self.vehicles despite empty _mbb_manual_vins.
        called_vins = {c.args[0] for c in cmd._get_mbb_operationlist.call_args_list}
        assert called_vins == set(stub.vehicles)
        for c in cmd._get_mbb_operationlist.call_args_list:
            assert c.kwargs.get("for_command") is True

    def test_warm_noop_for_non_mbb(self) -> None:
        # Non-MBB entry → no command connector → warm does nothing, never raises.
        stub = VagConnectCoordinator.__new__(VagConnectCoordinator)
        stub.entry = MagicMock()
        stub.entry.data = {"brand": "skoda"}
        stub.vehicles = {VIN: {}}
        stub._vehicles_lock = threading.Lock()
        client = SimpleNamespace()
        client._tokens = SimpleNamespace(strategy="hybrid_full")
        client._mbb_command = None
        stub._cariad_client = client
        asyncio.run(stub._refresh_mbb_command_capabilities())  # must not raise
