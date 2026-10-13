# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#968 (Philip-Wiege) — the companion VW preset must accept the 4.3.2 app.

We Connect updated 4.2.1 → 4.3.2 and the single-value app-version quarantine then
disabled every nav-read ("app 4.3.2 > preset 4.2.1"). The quarantine now accepts a
SET of known-compatible versions (the Play "4.3.2" and the internal versionName
forms that ship the same accessibility tree), so 4.3.2 users get nav-reads back
while genuinely-unknown versions stay quarantined.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from custom_components.vag_connect.companion.channel import CompanionChannel, CompanionWriteBlocked
from custom_components.vag_connect.companion.charge_target import CHARGE_TARGET_APP_VERSIONS
from custom_components.vag_connect.companion.climate import CLIMATE_APP_VERSIONS
from custom_components.vag_connect.companion.presets import PRESETS
from custom_components.vag_connect.companion.transport import CompanionTransportError


def _vw_channel() -> CompanionChannel:
    return CompanionChannel(MagicMock(), PRESETS["volkswagen"], time_fn=lambda: 0.0)


def test_accepts_4_3_2_and_internal_version_strings() -> None:
    ch = _vw_channel()
    assert ch._decide_version_ok("4.3.2") is True
    assert ch._decide_version_ok("3.64.0") is True
    assert ch._decide_version_ok("3.63.2") is True
    assert ch._decide_version_ok("4.2.1") is True  # backward compatibility


def test_rejects_an_unknown_older_or_unreadable_version() -> None:
    ch = _vw_channel()
    assert ch._decide_version_ok("4.3.1") is False
    assert ch._decide_version_ok("1.0.0") is False
    assert ch._decide_version_ok("4.7.0-beta") is False
    assert ch._decide_version_ok(None) is False


def test_accepts_a_build_newer_than_every_verified_one() -> None:
    # 2026-10-07 — an app update no longer switches taps off; each control is
    # still found on screen before it is tapped.
    ch = _vw_channel()
    assert ch._decide_version_ok("4.6.5") is True
    assert ch._decide_version_ok("5.0.0") is True


def test_preset_lists_4_3_2_and_tile_is_resource_id_hardened() -> None:
    vw = PRESETS["volkswagen"]
    assert isinstance(vw.verified_app_version, tuple)
    assert "4.3.2" in vw.verified_app_version
    # #968 — the charge-detail nav tile now leads with the stable resource-id.
    assert vw.nav_reads[0].tile.resource_id == "rangeTile"


def test_read_only_brands_keep_single_or_none_version() -> None:
    """The unverified brands are unchanged (None) — the set is a VW widening."""
    for brand in ("audi", "skoda", "seat", "cupra"):
        assert PRESETS[brand].verified_app_version is None


def test_accepts_4_6_4() -> None:
    # 2026-10-07 — regression-tested live on 4.6.4; same tree as 4.3.2.
    assert _vw_channel()._decide_version_ok("4.6.4") is True


# ── per-action pins: the write gate on 4.6.4 ─────────────────────────────────
# 4.6.4 dumps (phone-ui-capture-4.6.4/charging, settings-save) show the same
# controls: "Stop charging", vwd_save_button, subtitle_cta, cta_start.

_PINNED = ("start_charging", "stop_charging", "set_charge_target", "sync_vehicle")


class _GatePhone:
    """Answers the version read; the screen read marks the gate as passed."""

    connected = True

    def __init__(self, version: str) -> None:
        self.version = version

    async def foreground_app(self, package):
        pass

    async def current_app_version(self, package):
        return self.version

    async def dump_ui(self):
        raise CompanionTransportError("gate passed")


async def _gate(version: str, action: str) -> str:
    ch = CompanionChannel(_GatePhone(version), PRESETS["volkswagen"], time_fn=lambda: 0.0)
    with pytest.raises(CompanionWriteBlocked) as err:
        await ch._command_gate(action)
    return str(err.value)


def test_battery_actions_and_climate_are_pinned_to_4_6_4_and_4_3_2() -> None:
    specs = {a.action: a for a in PRESETS["volkswagen"].actions}
    for action in _PINNED:
        assert specs[action].app_versions == ("4.6.4", "4.3.2"), action
    assert CHARGE_TARGET_APP_VERSIONS == ("4.6.4", "4.3.2")
    assert CLIMATE_APP_VERSIONS == ("4.6.4", "4.3.2")


@pytest.mark.asyncio
@pytest.mark.parametrize("action", _PINNED)
@pytest.mark.parametrize("version", ["4.6.4", "4.3.2"])
async def test_write_gate_accepts_the_verified_builds(version, action) -> None:
    assert await _gate(version, action) == "gate passed"


@pytest.mark.asyncio
@pytest.mark.parametrize("action", _PINNED)
@pytest.mark.parametrize("version", ["4.4.0", "4.3.1", "4.7.0-beta"])
async def test_write_gate_refuses_an_unknown_build_before_the_screen(version, action) -> None:
    assert "app version" in await _gate(version, action)
