# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Maintainer rule 9 (core M9 / battery B5) — writes are pinned to verified apps.

A newer app build still runs the overview and nav reads (each control is found
on screen), but no command, Save tap or sync runs on a build that is not
explicitly listed: the charge slider and the climate dial are walked with
geometry measured on the listed builds, and a changed layout would put those
taps on the wrong step.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.exceptions import ServiceValidationError

from custom_components.vag_connect.companion.channel import (
    CompanionAppVersionUnverified,
    CompanionChannel,
    CompanionWriteBlocked,
)
from custom_components.vag_connect.companion.climate import ClimateController
from custom_components.vag_connect.companion.presets import (
    PRESETS,
    app_version_covered,
    app_version_listed,
)
from custom_components.vag_connect.companion.transport import CompanionTransportError

VIN = "WVWZZZAUZFW805377"


class _Phone:
    """Answers the version read; any screen read or tap is recorded."""

    connected = True

    def __init__(self, version: str) -> None:
        self.version = version
        self.screen_calls: list[str] = []

    async def foreground_app(self, package):
        pass

    async def current_app_version(self, package):
        return self.version

    async def dump_ui(self):
        self.screen_calls.append("dump")
        raise CompanionTransportError("gate passed")

    async def tap(self, *a, **k):
        self.screen_calls.append("tap")

    async def swipe(self, *a, **k):
        self.screen_calls.append("swipe")


def _channel(version: str) -> tuple[CompanionChannel, _Phone]:
    phone = _Phone(version)
    return CompanionChannel(phone, PRESETS["volkswagen"], time_fn=lambda: 0.0), phone


@pytest.mark.parametrize(
    ("live", "verified", "ok"),
    [
        ("4.6.4", ("4.6.4", "4.3.2"), True),
        ("4.3.2", ("4.6.4", "4.3.2"), True),
        ("4.7.0", ("4.6.4", "4.3.2"), False),
        ("4.6.5", ("4.6.4",), False),
        ("4.3.1", ("4.6.4",), False),
        (None, ("4.6.4",), False),
        ("4.6.4", None, False),
        ("4.6.4", "4.6.4", True),
    ],
)
def test_app_version_listed_is_exact(live, verified, ok) -> None:
    assert app_version_listed(live, verified) is ok


def test_a_newer_build_still_counts_for_reads() -> None:
    assert app_version_covered("4.7.0", ("4.6.4", "4.3.2")) is True


async def _refused(run, phone: _Phone) -> CompanionWriteBlocked:
    with pytest.raises(CompanionAppVersionUnverified) as err:
        await run()
    assert phone.screen_calls == []  # refused before any screen read or tap
    return err.value


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "action", ["start_charging", "stop_charging", "start_climate", "stop_climate"]
)
async def test_4_7_0_refuses_do_action_before_the_screen(action) -> None:
    ch, phone = _channel("4.7.0")
    err = await _refused(lambda: ch.do_action(action), phone)
    assert "4.7.0" in str(err)
    assert err.translation_key == "companion_app_version_unverified"
    assert err.translation_placeholders == {"version": "4.7.0"}


@pytest.mark.asyncio
async def test_4_7_0_refuses_charge_target_sync_and_settings_saves() -> None:
    ch, phone = _channel("4.7.0")
    await _refused(lambda: ch.set_charge_target(80), phone)
    await _refused(ch.sync_vehicle, phone)
    await _refused(lambda: ch.set_climate_setting("climate_at_unlock", True), phone)


@pytest.mark.asyncio
async def test_4_7_0_refuses_departure_writes() -> None:
    ch, phone = _channel("4.7.0")
    await _refused(lambda: ch.set_departure_timer(1, enabled=True), phone)
    await _refused(lambda: ch.set_departure_timer(1, time="07:30"), phone)


@pytest.mark.asyncio
async def test_4_7_0_refuses_climate_sheet_commands() -> None:
    ch, phone = _channel("4.7.0")
    climate = ClimateController(ch, sleep=AsyncMock())
    await _refused(lambda: climate.start(temp_c=21.0), phone)
    await _refused(climate.stop, phone)


@pytest.mark.asyncio
async def test_4_7_0_still_runs_reads_and_reports_writes_off() -> None:
    ch, _phone = _channel("4.7.0")
    await ch._refresh_version_gate()
    ch.set_nav_opt_in("charge_detail", True)
    assert ch._version_ok is True  # overview + nav-read gate
    assert ch.nav_reads_enabled is True
    assert ch.writes_enabled is False
    assert ch.live_app_version == "4.7.0"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "action", ["start_charging", "set_charge_target", "sync_vehicle", "toggle_departure_timer"]
)
async def test_4_6_4_stays_writable(action) -> None:
    ch, phone = _channel("4.6.4")
    with pytest.raises(CompanionWriteBlocked, match="gate passed"):
        await ch._command_gate(action)
    assert phone.screen_calls == ["dump"]
    assert ch.writes_enabled is True


@pytest.mark.asyncio
async def test_4_6_4_climate_gate_passes() -> None:
    ch, _phone = _channel("4.6.4")
    await ClimateController(ch, sleep=AsyncMock())._gate()


@pytest.mark.asyncio
async def test_the_refusal_reaches_the_user_translated() -> None:
    from custom_components.vag_connect.cariad.exceptions import VehicleCommandError
    from custom_components.vag_connect.coordinator import VagConnectCoordinator

    def _raise(*_a, **_k):
        try:
            raise CompanionAppVersionUnverified("4.7.0")
        except CompanionAppVersionUnverified as err:
            raise VehicleCommandError("command_start_charging", str(err)) from err

    c = VagConnectCoordinator.__new__(VagConnectCoordinator)
    c._cariad_client = MagicMock()
    c._cariad_client.command_start_charging = AsyncMock(side_effect=_raise)
    c.record_command_success = MagicMock()
    c.record_command_failure = MagicMock()
    c.is_companion = MagicMock(return_value=True)
    with pytest.raises(ServiceValidationError) as ei:
        await VagConnectCoordinator._dispatch_cmd_locked(c, VIN, "command_start_charging")
    assert ei.value.translation_key == "companion_app_version_unverified"
    assert ei.value.translation_placeholders == {"version": "4.7.0"}


def test_new_strings_exist_in_every_translation() -> None:
    import json
    from pathlib import Path

    root = Path(__file__).parents[1] / "custom_components" / "vag_connect"
    files = [root / "strings.json", *sorted((root / "translations").glob("*.json"))]
    for path in files:
        data = json.loads(path.read_text(encoding="utf-8"))
        msg = data["exceptions"]["companion_app_version_unverified"]["message"]
        assert "{version}" in msg, path.name


def test_app_request_status_shows_why_commands_are_off() -> None:
    from custom_components.vag_connect.sensor import VagAppRequestStatusSensor

    class _Sensor(VagAppRequestStatusSensor):
        _vehicle = {"companion_app_version": "4.7.0", "companion_writes_enabled": False}

    sensor = _Sensor.__new__(_Sensor)
    assert sensor._platform_attributes() == {"app_version": "4.7.0", "commands_enabled": False}
