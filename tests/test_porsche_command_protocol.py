# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Porsche remote-command protocol — the "key" field-name fix, SPIN-challenge
unlock, bounded command-status polling, and target-SoC branching/clamping.

b19 (#1337, CJNE-comparison, 2026-09-07): found while porting SPIN support
for unlock — every single Porsche command was sending the wire field
``commandName`` instead of ``key`` (confirmed against CJNE/pyporscheconnectapi's
``remote_services.py``, every payload). Since Porsche's login was blocked
until #1337's fix the same day, no command had ever been live-tested, so this
was never caught. NOT LIVE-VERIFIED beyond the login test — needs a real
account with a car to confirm the wire format is now actually accepted.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest

from custom_components.vag_connect.cariad.api.porsche import PorscheClient
from custom_components.vag_connect.cariad.exceptions import SpinError, VehicleCommandError

_VIN = "WP0ZZZ99ZTS300001"


def _client() -> PorscheClient:
    c = PorscheClient.__new__(PorscheClient)
    return c


class TestCommandKeyField:
    @pytest.mark.asyncio
    async def test_command_lock_sends_key_not_command_name(self):
        c = _client()
        c._post = AsyncMock(return_value={"status": {"result": "PERFORMED"}})
        await c.command_lock(_VIN)
        _, kwargs = c._post.call_args
        body = kwargs["json"]
        assert body["key"] == "LOCK"
        assert "commandName" not in body
        assert body["payload"] == {"spin": None}

    @pytest.mark.asyncio
    async def test_flash_honk_mode(self):
        c = _client()
        c._post = AsyncMock(return_value={"status": {"result": "PERFORMED"}})
        await c.command_flash(_VIN, honk=True)
        body = c._post.call_args.kwargs["json"]
        assert body["key"] == "HONK_FLASH"
        assert body["payload"]["mode"] == "HONK_AND_FLASH"

        c._post.reset_mock()
        await c.command_flash(_VIN, honk=False)
        body = c._post.call_args.kwargs["json"]
        assert body["payload"]["mode"] == "FLASH"


class TestUnlockSpinChallenge:
    @pytest.mark.asyncio
    async def test_unlock_without_spin_raises(self):
        c = _client()
        with pytest.raises(SpinError):
            await c.command_unlock(_VIN, spin="")

    @pytest.mark.asyncio
    async def test_unlock_full_challenge_response_flow(self):
        c = _client()
        # 1st POST: SPIN_CHALLENGE → returns a challenge. 2nd POST: UNLOCK.
        c._post = AsyncMock(side_effect=[
            {"data": {"challenge": "AABBCCDD"}},
            {"status": {"result": "PERFORMED"}},
        ])
        await c.command_unlock(_VIN, spin="1234")

        first_call = c._post.call_args_list[0].kwargs["json"]
        assert first_call == {"key": "SPIN_CHALLENGE", "payload": {"spin": None}}

        second_call = c._post.call_args_list[1].kwargs["json"]
        assert second_call["key"] == "UNLOCK"
        assert second_call["payload"]["spin"]["challenge"] == "AABBCCDD"
        # sha512(bytes.fromhex(pin + challenge)).hexdigest().upper()
        import hashlib
        expected = hashlib.sha512(bytes.fromhex("1234" + "AABBCCDD")).hexdigest().upper()
        assert second_call["payload"]["spin"]["hash"] == expected

    @pytest.mark.asyncio
    async def test_unlock_missing_challenge_raises(self):
        c = _client()
        c._post = AsyncMock(return_value={"data": {}})  # no "challenge"
        with pytest.raises(VehicleCommandError):
            await c.command_unlock(_VIN, spin="1234")


class TestTrunkUnlockAndWindows:
    """b20 (2026-09-08, androguard enum dump) — TRUNK_UNLOCK and the three
    WINDOWS_SUNROOF_* commands are real (dedicated model classes in the
    app), requested by neither CJNE nor this project before now."""

    @pytest.mark.asyncio
    async def test_trunk_unlock_without_spin_raises(self):
        c = _client()
        with pytest.raises(SpinError):
            await c.command_unlock_trunk(_VIN, spin="")

    @pytest.mark.asyncio
    async def test_trunk_unlock_runs_same_spin_protocol_as_unlock(self):
        c = _client()
        c._post = AsyncMock(side_effect=[
            {"data": {"challenge": "AABBCCDD"}},
            {"status": {"result": "PERFORMED"}},
        ])
        await c.command_unlock_trunk(_VIN, spin="1234")
        second_call = c._post.call_args_list[1].kwargs["json"]
        assert second_call["key"] == "TRUNK_UNLOCK"
        assert "hash" in second_call["payload"]["spin"]

    @pytest.mark.asyncio
    async def test_window_commands_send_correct_keys(self):
        c = _client()
        c._post = AsyncMock(return_value={"status": {"result": "PERFORMED"}})
        await c.command_open_windows(_VIN)
        await c.command_close_windows(_VIN)
        await c.command_vent_windows(_VIN)
        keys = [call.kwargs["json"]["key"] for call in c._post.call_args_list]
        assert keys == ["WINDOWS_SUNROOF_OPEN", "WINDOWS_SUNROOF_CLOSE", "WINDOWS_SUNROOF_VENT"]


class TestCommandStatusPolling:
    @pytest.mark.asyncio
    async def test_immediate_error_raises(self):
        c = _client()
        c._post = AsyncMock(return_value={"status": {"result": "ERROR"}})
        with pytest.raises(VehicleCommandError):
            await c.command_lock(_VIN)

    @pytest.mark.asyncio
    async def test_accepted_then_performed_returns_cleanly(self, monkeypatch):
        c = _client()
        c._post = AsyncMock(
            return_value={"status": {"id": "job-1", "result": "ACCEPTED"}}
        )
        c._get = AsyncMock(return_value={"status": {"result": "PERFORMED"}})
        monkeypatch.setattr(asyncio, "sleep", AsyncMock())
        await c.command_lock(_VIN)
        c._get.assert_awaited()

    @pytest.mark.asyncio
    async def test_accepted_then_error_raises(self, monkeypatch):
        c = _client()
        c._post = AsyncMock(
            return_value={"status": {"id": "job-1", "result": "ACCEPTED"}}
        )
        c._get = AsyncMock(return_value={"status": {"result": "ERROR"}})
        monkeypatch.setattr(asyncio, "sleep", AsyncMock())
        with pytest.raises(VehicleCommandError):
            await c.command_lock(_VIN)

    @pytest.mark.asyncio
    async def test_accepted_but_never_terminal_does_not_raise(self, monkeypatch):
        """Still-pending after the (short, deliberate) poll window is left
        for the next coordinator poll rather than raised as a timeout."""
        c = _client()
        c._post = AsyncMock(
            return_value={"status": {"id": "job-1", "result": "ACCEPTED"}}
        )
        c._get = AsyncMock(return_value={"status": {"result": "PENDING"}})
        # Make the poll loop finish instantly instead of really waiting.
        clock = iter([0, 100])  # first check inside deadline, second past it

        def _fake_monotonic():
            return next(clock, 100)

        monkeypatch.setattr(
            "custom_components.vag_connect.cariad.api.porsche.time.monotonic",
            _fake_monotonic,
        )
        monkeypatch.setattr(asyncio, "sleep", AsyncMock())
        await c.command_lock(_VIN)  # must not raise


class TestTargetSocBranching:
    @pytest.mark.asyncio
    async def test_clamped_to_valid_range(self):
        c = _client()
        c._get = AsyncMock(return_value={"measurements": [
            {"key": "DEPARTURES", "value": {}},
        ]})
        c._post = AsyncMock(return_value={"status": {"result": "PERFORMED"}})
        await c.command_set_target_soc(_VIN, 5)  # below 25
        body = c._post.call_args.kwargs["json"]
        assert body["payload"]["targetSoc"] == 25

        c._post.reset_mock()
        await c.command_set_target_soc(_VIN, 500)  # above 100
        body = c._post.call_args.kwargs["json"]
        assert body["payload"]["targetSoc"] == 100

    @pytest.mark.asyncio
    async def test_departures_vehicle_uses_charging_settings_edit(self):
        c = _client()
        c._get = AsyncMock(return_value={"measurements": [
            {"key": "DEPARTURES", "value": {}},
        ]})
        c._post = AsyncMock(return_value={"status": {"result": "PERFORMED"}})
        await c.command_set_target_soc(_VIN, 80)
        body = c._post.call_args.kwargs["json"]
        assert body["key"] == "CHARGING_SETTINGS_EDIT"
        assert body["payload"] == {"targetSoc": 80, "spin": None}

    @pytest.mark.asyncio
    async def test_profile_vehicle_uses_charging_profiles_edit(self):
        c = _client()
        profiles = [
            {"id": 1, "isEnabled": False, "minSoc": 50},
            {"id": 2, "isEnabled": True, "minSoc": 60},
        ]
        c._get = AsyncMock(return_value={"measurements": [
            {"key": "CHARGING_PROFILES", "value": {"list": profiles}},
        ]})
        c._post = AsyncMock(return_value={"status": {"result": "PERFORMED"}})
        await c.command_set_target_soc(_VIN, 80)
        body = c._post.call_args.kwargs["json"]
        assert body["key"] == "CHARGING_PROFILES_EDIT"
        edited = body["payload"]["list"]
        assert edited[1]["minSoc"] == 80  # the isEnabled=True profile was mutated
        assert edited[0]["minSoc"] == 50  # the other profile untouched

    @pytest.mark.asyncio
    async def test_profile_vehicle_no_active_profile_raises(self):
        c = _client()
        c._get = AsyncMock(return_value={"measurements": [
            {"key": "CHARGING_PROFILES", "value": {"list": [
                {"id": 1, "isEnabled": False, "minSoc": 50},
            ]}},
        ]})
        c._post = AsyncMock()
        with pytest.raises(VehicleCommandError):
            await c.command_set_target_soc(_VIN, 80)


class TestRetryAfterHeader:
    @pytest.mark.asyncio
    async def test_429_honors_retry_after_header(self, monkeypatch):
        c = _client()
        c._tokens = type("T", (), {
            "access_token": "tok", "needs_refresh": lambda self: False,
        })()

        calls = {"n": 0}

        class _Resp:
            def __init__(self, status, headers):
                self.status = status
                self.headers = headers

            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return False

            async def json(self):
                return {}

            async def text(self):
                return ""

        class _Session:
            def request(self, method, url, **kwargs):
                calls["n"] += 1
                if calls["n"] == 1:
                    return _Resp(429, {"Retry-After": "7"})
                return _Resp(200, {})

        c._session = _Session()
        sleeps: list[float] = []

        async def _fake_sleep(secs):
            sleeps.append(secs)

        monkeypatch.setattr(asyncio, "sleep", _fake_sleep)
        await c._request("GET", "https://api.ppa.porsche.com/x")
        assert sleeps[0] == 7  # not the fixed (2**0)*5 == 5s fallback
