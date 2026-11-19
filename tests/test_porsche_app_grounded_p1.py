# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Porsche read and command shapes, checked against My Porsche 21.26.46.

Each case below follows the app's own models (com.porsche.one /
de.porsche.one 21.26.46, kotlinx serializers).

- Tyre pressure: ``TIRE_PRESSURE_<CORNER>.value`` is
  ``{lastModified?, differenceBar, actualPressureBar?}`` in bar. There is no
  ``currentPressure`` and no per-corner ``warning`` member in the app model;
  the car's own tyre warning sits in ``INSTRUMENT_CLUSTER_ALERTS`` as
  ``TIRE_PRESSURE_WARNING`` / ``TIRE_PRESSURE_CRITICAL``.
- Target temperature: ``REMOTE_CLIMATIZER_START`` takes
  ``{spin?, targetTemperature (Kelvin), climateZonesEnabled?}``; the read side
  (``CLIMATIZER_STATE.targetTemperature``) is already parsed as Kelvin.
- Wake: the app wakes the car by reading ``GET /v1/vehicles/{vin}`` with a
  fresh ``wakeUpJob`` UUID from its refresh service; ``HONK_FLASH`` is a
  light/horn command and needs a ``mode``.
- S-PIN: when ``SPIN_CHALLENGE`` answers with a ``userChallenge``, the app
  hashes ``SHA-512(PBKDF2-HMAC-SHA512(pin, hex(userChallenge), 100000, 64) ||
  hex(challenge))``; without it the plain ``SHA-512(hex(pin) || hex(challenge))``
  stays, upper-case hex in both cases.
"""
from __future__ import annotations

import hashlib
import uuid
from unittest.mock import AsyncMock

import pytest

from custom_components.vag_connect.cariad.api.porsche import PorscheClient

_VIN = "WP0ZZZ99ZTS300001"


def _client() -> PorscheClient:
    return PorscheClient.__new__(PorscheClient)


async def _status(measurements: list[dict]) -> object:
    c = _client()
    c._get = AsyncMock(return_value={"measurements": measurements})
    return await c.get_status(_VIN)


def _tyre(corner: str, actual: float, difference: float) -> dict:
    return {
        "key": f"TIRE_PRESSURE_{corner}",
        "status": {"isEnabled": True},
        "value": {
            "lastModified": "2026-11-18T08:00:00Z",
            "differenceBar": difference,
            "actualPressureBar": actual,
        },
    }


_FOUR_TYRES = [
    _tyre("FRONT_LEFT", 2.6, -0.1),
    _tyre("FRONT_RIGHT", 2.5, -0.2),
    _tyre("REAR_LEFT", 2.9, 0.0),
    _tyre("REAR_RIGHT", 2.8, -0.1),
]


def _alerts(warnings: list[str], criticals: list[str] | None = None, enabled: bool = True) -> dict:
    return {
        "key": "INSTRUMENT_CLUSTER_ALERTS",
        "status": {"isEnabled": enabled},
        "value": {"infos": [], "warnings": warnings, "criticals": criticals or []},
    }


class TestTyrePressureAppShape:
    @pytest.mark.asyncio
    async def test_actual_pressure_bar_fills_each_corner(self) -> None:
        d = await _status(_FOUR_TYRES)
        assert d.tire_pressure_front_left_bar == 2.6
        assert d.tire_pressure_front_right_bar == 2.5
        assert d.tire_pressure_rear_left_bar == 2.9
        assert d.tire_pressure_rear_right_bar == 2.8

    @pytest.mark.asyncio
    async def test_no_alert_measurement_leaves_warning_unknown(self) -> None:
        """Pressures alone carry no warning flag; claiming "no warning" would
        be a value the car never sent."""
        d = await _status(_FOUR_TYRES)
        assert d.tire_pressure_warning is None

    @pytest.mark.asyncio
    async def test_tyre_warning_from_cluster_alerts(self) -> None:
        d = await _status([*_FOUR_TYRES, _alerts(["TIRE_PRESSURE_WARNING"])])
        assert d.tire_pressure_warning is True

    @pytest.mark.asyncio
    async def test_tyre_critical_counts_as_warning(self) -> None:
        d = await _status([*_FOUR_TYRES, _alerts([], ["TIRE_PRESSURE_CRITICAL"])])
        assert d.tire_pressure_warning is True

    @pytest.mark.asyncio
    async def test_alerts_without_a_tyre_entry_mean_no_warning(self) -> None:
        d = await _status([*_FOUR_TYRES, _alerts(["OIL_LEVEL_LOW"])])
        assert d.tire_pressure_warning is False

    @pytest.mark.asyncio
    async def test_disabled_alert_measurement_is_not_a_no(self) -> None:
        d = await _status([*_FOUR_TYRES, _alerts([], enabled=False)])
        assert d.tire_pressure_warning is None

    @pytest.mark.asyncio
    async def test_legacy_current_pressure_still_read(self) -> None:
        """The earlier member name stays as a fallback for older payloads."""
        d = await _status([
            {"key": "TIRE_PRESSURE_FRONT_LEFT", "value": {"currentPressure": 235.0}},
        ])
        assert d.tire_pressure_front_left_bar == 2.35


class TestClimateTargetTemperature:
    @pytest.mark.asyncio
    async def test_target_temperature_goes_out_in_kelvin(self) -> None:
        c = _client()
        c._post = AsyncMock(return_value={"status": {"result": "PERFORMED"}})
        await c.command_set_climate_temperature(_VIN, 21.5)
        body = c._post.call_args.kwargs["json"]
        assert body["key"] == "REMOTE_CLIMATIZER_START"
        assert body["payload"] == {"spin": None, "targetTemperature": 294.65}


class TestWakeIsAFreshStatusRead:
    @pytest.mark.asyncio
    async def test_wake_reads_status_with_a_wake_up_job_and_sends_no_command(self) -> None:
        c = _client()
        c._get = AsyncMock(return_value={})
        c._post = AsyncMock()
        await c.command_wake(_VIN)
        c._post.assert_not_called()
        args, kwargs = c._get.call_args
        assert args[0].endswith(f"/app/connect/v1/vehicles/{_VIN}")
        params = dict(kwargs["params"])
        uuid.UUID(params["wakeUpJob"])
        assert "mf" in params

    @pytest.mark.asyncio
    async def test_wake_asks_for_the_same_measurements_as_a_poll(self) -> None:
        # The app's refresh service sends wakeUpJob with its full measurement
        # set, not with one key, so the wake read must not shrink to one key.
        from custom_components.vag_connect.cariad.api.porsche import _MEASUREMENTS

        c = _client()
        c._get = AsyncMock(return_value={})
        await c.command_wake(_VIN)
        params = c._get.call_args.kwargs["params"]
        assert [v for k, v in params if k == "mf"] == list(_MEASUREMENTS)
        assert [k for k, _ in params].count("wakeUpJob") == 1

    @pytest.mark.asyncio
    async def test_every_wake_uses_its_own_job(self) -> None:
        c = _client()
        c._get = AsyncMock(return_value={})
        await c.command_wake(_VIN)
        await c.command_wake(_VIN)
        jobs = [dict(call.kwargs["params"])["wakeUpJob"] for call in c._get.call_args_list]
        assert jobs[0] != jobs[1]


def _app_hash_with_user_challenge(pin: str, challenge: str, user_challenge: str) -> str:
    key = hashlib.pbkdf2_hmac("sha512", pin.encode("utf-8"), bytes.fromhex(user_challenge), 100000, 64)
    return hashlib.sha512(key + bytes.fromhex(challenge)).hexdigest().upper()


class TestSpinUserChallenge:
    @pytest.mark.asyncio
    async def test_unlock_uses_pbkdf2_when_user_challenge_is_sent(self) -> None:
        c = _client()
        c._post = AsyncMock(side_effect=[
            {"data": {"challenge": "AABBCCDD", "userChallenge": "00112233445566778899AABBCCDDEEFF"}},
            {"status": {"result": "PERFORMED"}},
        ])
        await c.command_unlock(_VIN, spin="1234")
        spin = c._post.call_args_list[1].kwargs["json"]["payload"]["spin"]
        assert spin["challenge"] == "AABBCCDD"
        assert spin["hash"] == _app_hash_with_user_challenge(
            "1234", "AABBCCDD", "00112233445566778899AABBCCDDEEFF",
        )
        plain = hashlib.sha512(bytes.fromhex("1234" + "AABBCCDD")).hexdigest().upper()
        assert spin["hash"] != plain

    @pytest.mark.asyncio
    async def test_trunk_unlock_honours_user_challenge_too(self) -> None:
        c = _client()
        c._post = AsyncMock(side_effect=[
            {"data": {"challenge": "0A0B", "userChallenge": "CAFE"}},
            {"status": {"result": "PERFORMED"}},
        ])
        await c.command_unlock_trunk(_VIN, spin="9876")
        body = c._post.call_args_list[1].kwargs["json"]
        assert body["key"] == "TRUNK_UNLOCK"
        assert body["payload"]["spin"]["hash"] == _app_hash_with_user_challenge("9876", "0A0B", "CAFE")

    @pytest.mark.asyncio
    async def test_empty_user_challenge_keeps_the_plain_hash(self) -> None:
        c = _client()
        c._post = AsyncMock(side_effect=[
            {"data": {"challenge": "AABBCCDD", "userChallenge": None}},
            {"status": {"result": "PERFORMED"}},
        ])
        await c.command_unlock(_VIN, spin="1234")
        spin = c._post.call_args_list[1].kwargs["json"]["payload"]["spin"]
        assert spin["hash"] == hashlib.sha512(bytes.fromhex("1234" + "AABBCCDD")).hexdigest().upper()
