# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""v2.15.12 (#584 follow-up) — aux-heating must not leak the MBB bearer.

CyberChris79's log showed a "start climate" on a diesel Passat (= engine
pre-heater / aux-heating) returning ``400 missing or invalid auth header``.
Root cause: on a legacy MBB-primary entry ``self._access_token`` is the MBB
bearer, but ``command_start_aux_heating`` sent it to the CARIAD BFF, which
rejects it. There is no verified MBB aux-heating (rheating) route, so instead
of leaking the wrong bearer the command now fails cleanly on MBB entries.

Non-MBB (portal / BFF / Audi) entries keep the existing BFF path unchanged.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from custom_components.vag_connect.cariad.api.vw_eu import VWEUClient
from custom_components.vag_connect.cariad.exceptions import VehicleCommandError
from custom_components.vag_connect.cariad.models import TokenSet


class _Sess:
    def get(self, url: str, headers: Any = None) -> Any:  # pragma: no cover
        raise AssertionError("no network in these tests")


def _client() -> VWEUClient:
    c = VWEUClient(_Sess(), "u@t.de", "pw")
    c._tokens = TokenSet(
        access_token="BEARER", refresh_token="RT", id_token="i",
        expires_at=0.0, strategy="mbb",
    )
    return c


async def _boom(*a: Any, **k: Any) -> None:  # pragma: no cover
    raise AssertionError("CARIAD BFF must NOT be called on an MBB entry")


def test_start_aux_heating_blocked_on_mbb_entry(monkeypatch) -> None:
    """MBB-primary → raise VehicleCommandError, never touch the BFF."""
    c = _client()
    monkeypatch.setattr(c, "_mbb_command_target", lambda: c)
    c._post_command = _boom
    with pytest.raises(VehicleCommandError):
        asyncio.run(c.command_start_aux_heating("VINX"))


def test_stop_aux_heating_blocked_on_mbb_entry(monkeypatch) -> None:
    c = _client()
    monkeypatch.setattr(c, "_mbb_command_target", lambda: c)
    c._post_command = _boom
    with pytest.raises(VehicleCommandError):
        asyncio.run(c.command_stop_aux_heating("VINX"))


def test_start_aux_heating_hits_bff_on_non_mbb_entry(monkeypatch) -> None:
    """Non-MBB entry (target is None) → existing CARIAD BFF path, unchanged."""
    c = _client()
    monkeypatch.setattr(c, "_mbb_command_target", lambda: None)
    calls: list[tuple[str, str]] = []

    async def _cap(vin: str, path: str, **kw: Any) -> None:
        calls.append((vin, path))

    c._post_command = _cap
    asyncio.run(c.command_start_aux_heating("VINX"))
    assert calls == [("VINX", "auxiliary-heating/start")]


def test_stop_aux_heating_hits_bff_on_non_mbb_entry(monkeypatch) -> None:
    c = _client()
    monkeypatch.setattr(c, "_mbb_command_target", lambda: None)
    calls: list[tuple[str, str]] = []

    async def _cap(vin: str, path: str, **kw: Any) -> None:
        calls.append((vin, path))

    c._post_command = _cap
    asyncio.run(c.command_stop_aux_heating("VINX"))
    assert calls == [("VINX", "auxiliary-heating/stop")]
