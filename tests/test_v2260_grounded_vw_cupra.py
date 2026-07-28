# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""v2.26.0 — companion reads re-grounded against real references:

- VW read vocabulary + the C9 charge-detail nav-read, grounded in
  ckomma/charge-app-connector-vw (real VW app 4.2.x).
- CUPRA overview read, grounded in the real uiautomator dump attached to #968
  (split "51"/"%" nodes, "Estimated range", "Vehicle locked", "Engine on",
  "Last updated: N ago"). The old German-label seed read NOTHING from it.
- The #974 wake/sleep opt-in and the C9 opt-in gating.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from custom_components.vag_connect.companion.channel import (
    _NAV_READ_INTERVAL_S,
    CompanionChannel,
)
from custom_components.vag_connect.companion.presets import PRESETS, coerce
from custom_components.vag_connect.companion.screen import (
    find_sync_age,
    parse_ui_dump,
    read_fields,
    read_selectors,
)

_FIXTURES = Path(__file__).parent / "fixtures"


def _dump(nodes: str) -> str:
    return f'<?xml version="1.0"?><hierarchy>{nodes}</hierarchy>'


def _cd(desc: str, bounds: str = "[0,0][10,10]", clickable: str = "false") -> str:
    return (
        f'<node content-desc="{desc}" text="" class="TextView" '
        f'clickable="{clickable}" bounds="{bounds}" />'
    )


def _txt(text: str, bounds: str = "[0,0][10,10]") -> str:
    return (
        f'<node content-desc="" text="{text}" class="TextView" '
        f'clickable="false" bounds="{bounds}" />'
    )


# ── VW: grounded read vocabulary (ckomma) ────────────────────────────────────

class TestVwGroundedVocabulary:
    def test_battery_charge_level_wording(self) -> None:
        # ckomma's verified word is "Battery charge level", not our old
        # "Ladezustand"/"Ladung".
        nodes = parse_ui_dump(_dump(_cd("Battery charge level: 74 %")))
        assert read_fields(nodes, PRESETS["volkswagen"])["battery_soc"] == 74

    def test_battery_range_wording(self) -> None:
        nodes = parse_ui_dump(_dump(_cd("Battery range 320 km")))
        assert read_fields(nodes, PRESETS["volkswagen"])["electric_range_km"] == 320

    def test_german_batterieladung_wording(self) -> None:
        nodes = parse_ui_dump(_dump(_cd("Batterieladung 61 %")))
        assert read_fields(nodes, PRESETS["volkswagen"])["battery_soc"] == 61

    def test_old_vocabulary_still_matches(self) -> None:
        # kept as fallbacks so a differently-worded build still reads.
        nodes = parse_ui_dump(_dump(_cd("Ladezustand 55 %") + _cd("Reichweite 210 km")))
        got = read_fields(nodes, PRESETS["volkswagen"])
        assert got["battery_soc"] == 55
        assert got["electric_range_km"] == 210


# ── VW: the C9 charge-detail nav read values ─────────────────────────────────

class TestVwChargeDetailValues:
    def _detail(self) -> list:
        return parse_ui_dump(_dump(
            _cd("Target charge level: 80 %")
            + _cd("Charging power 11,0 kW")
            + _cd("2 hours and 15 minutes remaining")
        ))

    def test_reads_target_soc_power_and_time(self) -> None:
        nav = PRESETS["volkswagen"].nav_reads[0]
        got = read_selectors(self._detail(), nav.values)
        assert got["target_soc"] == 80
        assert got["charging_power_kw"] == 11.0
        assert got["remaining_charge_time_min"] == 135

    def test_upper_charge_limit_wording(self) -> None:
        nav = PRESETS["volkswagen"].nav_reads[0]
        nodes = parse_ui_dump(_dump(_cd("Upper charge limit: 90 %")))
        assert read_selectors(nodes, nav.values)["target_soc"] == 90

    def test_hm_minutes_compact_form(self) -> None:
        assert coerce("hm_minutes", "1:45 h") == 105
        assert coerce("hm_minutes", "noch 90 min") == 90
        assert coerce("hm_minutes", "2 Stunden und 5 Minuten") == 125


# ── VW: nav-read is opt-in and version-gated ─────────────────────────────────

class _NavTransport:
    """Overview first, then a charge-detail screen after a tap. Records taps/back."""

    def __init__(self, overview: str, detail: str, version: str = "4.2.1") -> None:
        self._overview = overview
        self._detail = detail
        self._version = version
        self.taps: list[tuple[int, int]] = []
        self.backs = 0
        self.connected = True
        self._tapped = False

    async def connect(self) -> None:
        self.connected = True

    async def foreground_app(self, package: str) -> None:  # noqa: ARG002
        return None

    async def current_app_version(self, package: str) -> str | None:  # noqa: ARG002
        return self._version

    async def dump_ui(self) -> str:
        return self._detail if self._tapped else self._overview

    async def tap(self, x: int, y: int) -> None:
        self.taps.append((x, y))
        self._tapped = True

    async def key_back(self) -> None:
        self.backs += 1
        self._tapped = False

    async def sleep_if_enabled(self) -> None:
        return None


_VW_OVERVIEW = _dump(
    _cd("Battery charge level: 74 %")
    + _cd("Battery range 300 km", bounds="[0,60][200,110]", clickable="true")
)
_VW_DETAIL = _dump(_cd("Target charge level: 80 %"))


def _clock():
    t = {"v": 1000.0}
    return (lambda: t["v"]), t


class TestNavReadOptIn:
    @pytest.mark.asyncio
    async def test_off_by_default_never_taps(self) -> None:
        now, _ = _clock()
        t = _NavTransport(_VW_OVERVIEW, _VW_DETAIL)
        ch = CompanionChannel(t, PRESETS["volkswagen"], time_fn=now)  # opt-in off
        got = await ch.read()
        assert "target_soc" not in got
        assert t.taps == []

    @pytest.mark.asyncio
    async def test_opt_in_reads_target_soc_and_returns_back(self) -> None:
        now, _ = _clock()
        t = _NavTransport(_VW_OVERVIEW, _VW_DETAIL)
        ch = CompanionChannel(
            t, PRESETS["volkswagen"], time_fn=now, read_charge_detail=True,
        )
        got = await ch.read()
        assert got["target_soc"] == 80
        assert t.taps  # it navigated
        assert t.backs == 1  # and returned to the overview

    @pytest.mark.asyncio
    async def test_version_drift_blocks_nav_even_if_opted_in(self) -> None:
        now, _ = _clock()
        t = _NavTransport(_VW_OVERVIEW, _VW_DETAIL, version="9.9.9")
        ch = CompanionChannel(
            t, PRESETS["volkswagen"], time_fn=now, read_charge_detail=True,
        )
        got = await ch.read()
        assert "target_soc" not in got
        assert t.taps == []

    @pytest.mark.asyncio
    async def test_cadence_caches_between_navs(self) -> None:
        now, tt = _clock()
        t = _NavTransport(_VW_OVERVIEW, _VW_DETAIL)
        ch = CompanionChannel(
            t, PRESETS["volkswagen"], time_fn=now, read_charge_detail=True,
        )
        await ch.read()
        assert len(t.taps) == 1
        # a second read within the cadence window must NOT tap again, but must
        # still expose the cached target_soc
        got = await ch.read()
        assert len(t.taps) == 1
        assert got["target_soc"] == 80
        # after the window, it navigates again
        tt["v"] += _NAV_READ_INTERVAL_S + 1
        await ch.read()
        assert len(t.taps) == 2


# ── CUPRA: grounded from the real #968 dump ──────────────────────────────────

class TestCupraGroundedFromRealDump:
    def _nodes(self):
        xml = (_FIXTURES / "cupra_main_968.xml").read_text(encoding="utf-8")
        return parse_ui_dump(xml)

    def test_reads_soc_from_split_nodes(self) -> None:
        got = read_fields(self._nodes(), PRESETS["cupra"])
        assert got["battery_soc"] == 51

    def test_reads_range_from_split_nodes(self) -> None:
        got = read_fields(self._nodes(), PRESETS["cupra"])
        assert got["electric_range_km"] == 182

    def test_reads_lock_and_engine(self) -> None:
        got = read_fields(self._nodes(), PRESETS["cupra"])
        assert got["doors_locked"] is True   # "Vehicle locked"
        assert got["ignition_on"] is True    # "Engine on"

    def test_sync_age_from_doors_screen(self) -> None:
        xml = (_FIXTURES / "cupra_doors_968.xml").read_text(encoding="utf-8")
        # "Last updated: 1 Minute ago"
        assert find_sync_age(parse_ui_dump(xml), PRESETS["cupra"]) == 60.0

    def test_old_german_seed_would_have_read_nothing(self) -> None:
        # Guard the regression: a label-sibling German seed finds no SoC/range
        # in this English split-node app. Our grounded preset must.
        got = read_fields(self._nodes(), PRESETS["cupra"])
        assert got.get("battery_soc") == 51 and got.get("electric_range_km") == 182


class TestWakeSleepOptIn:
    """#974 — opt-in: put the display back to sleep after a poll."""

    def _transport(self, wake_sleep: bool):
        from custom_components.vag_connect.companion.transport import (
            NetworkAdbTransport,
        )

        t = NetworkAdbTransport("h", 5555, "k", wake_sleep=wake_sleep)
        sent: list[str] = []

        async def _fake_shell(cmd: str, timeout_s: float = 10.0) -> str:
            sent.append(cmd)
            return ""

        t.shell = _fake_shell  # type: ignore[assignment]
        return t, sent

    @pytest.mark.asyncio
    async def test_sleep_sent_when_enabled(self) -> None:
        t, sent = self._transport(wake_sleep=True)
        await t.sleep_if_enabled()
        assert sent == ["input keyevent 223"]  # KEYCODE_SLEEP

    @pytest.mark.asyncio
    async def test_noop_when_disabled(self) -> None:
        t, sent = self._transport(wake_sleep=False)
        await t.sleep_if_enabled()
        assert sent == []


class TestBoolCoercions:
    @pytest.mark.parametrize(("raw", "expected"), [
        ("Vehicle locked", True),
        ("Vehicle unlocked", False),
        ("Fahrzeug verriegelt", True),
        ("Fahrzeug entriegelt", False),
    ])
    def test_bool_locked(self, raw: str, expected: bool) -> None:
        assert coerce("bool_locked", raw) is expected

    @pytest.mark.parametrize(("raw", "expected"), [
        ("Engine on", True),
        ("Engine off", False),
        ("Motor an", True),
        ("Motor aus", False),
    ])
    def test_bool_ignition(self, raw: str, expected: bool) -> None:
        assert coerce("bool_ignition", raw) is expected
