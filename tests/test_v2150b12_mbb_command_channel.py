# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""b12 — MBB COMMAND CHANNEL on a read-only primary.

A portal-primary entry (reads) can arm a durable-MBB connector so lock/climate/
charge route to MBB while reads stay on the portal. These pin the routing
(_mbb_command_target), the arming, the command dispatch, and the is_read_only
gate — and guard that an MBB-PRIMARY entry's behaviour is unchanged.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

from custom_components.vag_connect.cariad.api.vw_eu import VWEUClient
from custom_components.vag_connect.cariad.models import TokenSet
from custom_components.vag_connect.coordinator import VagConnectCoordinator


def _client(strategy: str) -> VWEUClient:
    c = VWEUClient(MagicMock(), "u@t.de", "pw")
    c._tokens = TokenSet(
        access_token="a", refresh_token="r", id_token="i", strategy=strategy,
    )
    return c


def _mbb_tokens() -> TokenSet:
    return TokenSet(
        access_token="mbb-acc", refresh_token="mbb-ref", id_token="mbb-id",
        expires_at=0.0, strategy="mbb",
    )


# ── _mbb_command_target ──────────────────────────────────────────────────────

def test_target_is_self_for_mbb_primary() -> None:
    c = _client("mbb")
    assert c._mbb_command_target() is c  # MBB-primary unchanged


def test_target_none_for_portal_without_channel() -> None:
    c = _client("data_act_portal")
    assert c._mbb_command_target() is None  # no MBB path → BFF fallback


# ── arm_mbb_command_channel ──────────────────────────────────────────────────

def test_arm_builds_channel_and_routes_to_it() -> None:
    c = _client("data_act_portal")
    ok = asyncio.run(
        c.arm_mbb_command_channel(_mbb_tokens(), "client-id", ["VIN1"], "1234")
    )
    assert ok is True
    assert c._mbb_command is not None
    assert c._mbb_command_target() is c._mbb_command  # portal now routes to it
    assert c._mbb_command._tokens.strategy == "mbb"
    assert c._mbb_command._mbb_client_id == "client-id"


def test_arm_skipped_when_already_mbb_primary() -> None:
    c = _client("mbb")
    ok = asyncio.run(
        c.arm_mbb_command_channel(_mbb_tokens(), "cid", ["V"], "")
    )
    assert ok is False
    assert c._mbb_command is None


def test_arm_failsoft_on_empty_tokens() -> None:
    c = _client("data_act_portal")
    empty = TokenSet(access_token="", refresh_token="", id_token="", strategy="mbb")
    ok = asyncio.run(c.arm_mbb_command_channel(empty, "cid", ["V"], ""))
    assert ok is False
    assert c._mbb_command is None


# ── command dispatch routes to the armed channel ─────────────────────────────

def test_command_lock_routes_to_command_channel() -> None:
    c = _client("data_act_portal")
    asyncio.run(c.arm_mbb_command_channel(_mbb_tokens(), "cid", ["VIN1"], "1234"))
    c._mbb_command._command_rlu_mbb = AsyncMock()
    asyncio.run(c.command_lock("VIN1", spin="1234"))
    c._mbb_command._command_rlu_mbb.assert_awaited_once()


def test_command_start_climate_routes_to_command_channel() -> None:
    c = _client("data_act_portal")
    asyncio.run(c.arm_mbb_command_channel(_mbb_tokens(), "cid", ["VIN1"], "1234"))
    c._mbb_command._command_mbb_op = AsyncMock()
    asyncio.run(c.command_start_climate("VIN1"))
    c._mbb_command._command_mbb_op.assert_awaited_once()


def test_mbb_primary_command_still_routes_to_self() -> None:
    # regression guard: an MBB-primary entry dispatches on itself, unchanged.
    c = _client("mbb")
    c._command_rlu_mbb = AsyncMock()
    asyncio.run(c.command_lock("VIN1", spin="1234"))
    c._command_rlu_mbb.assert_awaited_once()


# ── is_read_only gate ────────────────────────────────────────────────────────

def _coord(strategy: str, *, channel_flag: bool, channel_armed: bool) -> object:
    stub = type("S", (), {})()
    stub.entry = MagicMock()
    stub.entry.data = {"mbb_command_channel": channel_flag, "read_only_mode": False}
    stub.entry.options = {}
    client = MagicMock()
    client._tokens = TokenSet(
        access_token="a", refresh_token="r", id_token="i", strategy=strategy,
    )
    client._mbb_command = MagicMock() if channel_armed else None
    stub._cariad_client = client
    return stub


def test_is_read_only_opens_when_command_channel_armed() -> None:
    stub = _coord("data_act_portal", channel_flag=True, channel_armed=True)
    assert VagConnectCoordinator.is_read_only(stub) is False  # commands enabled


def test_is_read_only_true_for_portal_without_channel() -> None:
    stub = _coord("data_act_portal", channel_flag=False, channel_armed=False)
    assert VagConnectCoordinator.is_read_only(stub) is True  # structural read-only


def test_is_read_only_true_when_flag_set_but_not_armed() -> None:
    # flag in data but arming failed → still structurally read-only (no path).
    stub = _coord("data_act_portal", channel_flag=True, channel_armed=False)
    assert VagConnectCoordinator.is_read_only(stub) is True
