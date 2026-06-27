# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#543 — honest read-only message for STRUCTURALLY read-only (portal) cars.

A portal/website-authproxy primary (data_act_portal / device_grant_portal /
website_authproxy, no MBB command channel armed) is read-only because its
token has NO command path — not because the user flipped a switch. The
service handler must surface ``read_only_portal_active`` ("can't be toggled")
for that case, and keep ``read_only_mode_active`` ("disable it in options")
for a genuine user-toggle read-only car.

These pin (a) the new ``is_structural_read_only`` coordinator helper and
(b) the translation_key the service raise picks based on it.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from homeassistant.exceptions import ServiceValidationError

from custom_components.vag_connect.cariad.models import TokenSet
from custom_components.vag_connect.coordinator import VagConnectCoordinator


def _coord(
    strategy: str,
    *,
    channel_flag: bool = False,
    channel_armed: bool = False,
    read_only: bool | None = None,
) -> object:
    """Build a stub on which the real (unbound) coordinator methods run."""
    stub = type("S", (), {})()
    stub.entry = MagicMock()
    data: dict[str, object] = {"mbb_command_channel": channel_flag}
    if read_only is not None:
        data["read_only_mode"] = read_only
    stub.entry.data = data
    stub.entry.options = {}
    client = MagicMock()
    client._tokens = TokenSet(
        access_token="a", refresh_token="r", id_token="i", strategy=strategy,
    )
    client._mbb_command = MagicMock() if channel_armed else None
    stub._cariad_client = client
    return stub


# ── is_structural_read_only ──────────────────────────────────────────────────

def test_structural_true_for_portal_without_channel() -> None:
    stub = _coord("data_act_portal")
    assert VagConnectCoordinator.is_structural_read_only(stub) is True


def test_structural_true_for_device_grant_and_authproxy() -> None:
    for strat in ("device_grant_portal", "website_authproxy"):
        stub = _coord(strat)
        assert VagConnectCoordinator.is_structural_read_only(stub) is True


def test_structural_false_when_command_channel_armed() -> None:
    stub = _coord("data_act_portal", channel_flag=True, channel_armed=True)
    assert VagConnectCoordinator.is_structural_read_only(stub) is False


def test_structural_false_for_user_toggle_readonly() -> None:
    # A normal (non-portal) car the user flipped read-only on is NOT structural.
    stub = _coord("mbb", read_only=True)
    assert VagConnectCoordinator.is_read_only(stub) is True
    assert VagConnectCoordinator.is_structural_read_only(stub) is False


# ── the service raise picks the right translation_key ────────────────────────

def _raise_like_coord_writeable(coord: object) -> None:
    """Mirror __init__._coord_writeable's branch using the REAL coord methods."""
    if VagConnectCoordinator.is_read_only(coord):
        if VagConnectCoordinator.is_structural_read_only(coord):
            raise ServiceValidationError(
                "portal read-only",
                translation_domain="vag_connect",
                translation_key="read_only_portal_active",
            )
        raise ServiceValidationError(
            "user toggle read-only",
            translation_domain="vag_connect",
            translation_key="read_only_mode_active",
        )


def test_portal_car_raises_portal_key() -> None:
    coord = _coord("data_act_portal")
    with pytest.raises(ServiceValidationError) as exc:
        _raise_like_coord_writeable(coord)
    assert exc.value.translation_key == "read_only_portal_active"


def test_user_toggle_car_raises_mode_key() -> None:
    coord = _coord("mbb", read_only=True)
    with pytest.raises(ServiceValidationError) as exc:
        _raise_like_coord_writeable(coord)
    assert exc.value.translation_key == "read_only_mode_active"
