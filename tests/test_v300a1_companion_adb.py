# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""v3.0.0-alpha — companion (ADB) channel.

The device-touching layer (``transport``) is not tested here; it needs a phone.
Everything above it is pure and is tested hard, because that is where a wrong
decision would ship a bad read or, worse, a tap onto the wrong control:

- screen parsing and selector resolution (resource-id / content-desc / label);
- the value coercions (percent bounds, first-int, charging bool);
- the write quarantine: unverified brand never writes, version drift disables
  writes but not reads, unknown version disables writes;
- the post-failure cooldown clock (no per-read throttle: scan_interval is the
  cadence, and a cooldown read must not itself count as a failed poll);
- the client adapter mapping a screen read onto VehicleData, and refusing
  commands with a clean VehicleCommandError rather than a raw crash;
- every brand preset is structurally complete, and exactly one is verified.
"""
from __future__ import annotations


import pytest

from custom_components.vag_connect.companion.channel import (
    CompanionChannel,
    CompanionWriteBlocked,
)
from custom_components.vag_connect.companion.presets import (
    ACTION_TO_COMMAND,
    PRESETS,
    coerce,
)
from custom_components.vag_connect.companion.screen import (
    parse_ui_dump,
    read_fields,
)


# ── a realistic uiautomator dump fragment for the VW app ────────────────────

def _dump(nodes_xml: str) -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<hierarchy rotation="0">' + nodes_xml + "</hierarchy>"
    )


VW_SCREEN = _dump(
    '<node resource-id="" content-desc="Ladezustand 74 %" text="" '
    'class="android.widget.TextView" clickable="false" bounds="[0,0][100,50]" />'
    '<node resource-id="" content-desc="Reichweite 312 km" text="" '
    'class="android.widget.TextView" clickable="false" bounds="[0,60][100,110]" />'
    '<node resource-id="" content-desc="Wird geladen" text="" '
    'class="android.widget.TextView" clickable="false" bounds="[0,120][100,170]" />'
    '<node resource-id="" content-desc="Klimatisierung starten" text="Klima" '
    'class="android.widget.Button" clickable="true" bounds="[0,200][200,260]" />'
)


class TestScreenParsing:
    def test_empty_and_garbage_dumps_do_not_raise(self) -> None:
        assert parse_ui_dump("") == []
        assert parse_ui_dump("not xml") == []
        assert parse_ui_dump("<hierarchy></hierarchy>") == []

    def test_bounds_and_tap_point(self) -> None:
        nodes = parse_ui_dump(VW_SCREEN)
        btn = next(n for n in nodes if n.clazz.endswith("Button"))
        assert btn.bounds == (0, 200, 200, 260)
        assert btn.tap_point == (100, 230)

    def test_vw_read_pulls_soc_range_and_state(self) -> None:
        fields = read_fields(parse_ui_dump(VW_SCREEN), PRESETS["volkswagen"])
        assert fields["battery_soc"] == 74
        assert fields["electric_range_km"] == 312
        assert fields["is_charging"] is True
        assert "Wird geladen" in str(fields["charging_state"])

    def test_partial_screen_yields_only_what_matched(self) -> None:
        # No range node → range simply absent, never a spurious None/0.
        screen = _dump(
            '<node resource-id="" content-desc="Ladezustand 55 %" text="" '
            'class="TextView" clickable="false" bounds="[0,0][10,10]" />'
        )
        fields = read_fields(parse_ui_dump(screen), PRESETS["volkswagen"])
        assert fields == {"battery_soc": 55}


class TestCoercion:
    def test_percent_rejects_implausible_values(self) -> None:
        assert coerce("percent", "74 %") == 74
        assert coerce("percent", "0 %") == 0
        assert coerce("percent", "100 %") == 100
        assert coerce("percent", "312 km") is None  # a range wrongly matched

    def test_int_km_takes_the_first_integer(self) -> None:
        assert coerce("int_km", "312 km") == 312
        assert coerce("int_km", "noch 45 min") == 45

    def test_bool_charging(self) -> None:
        assert coerce("bool_charging", "Wird geladen") is True
        assert coerce("bool_charging", "Nicht verbunden") is False

    def test_blank_is_none(self) -> None:
        assert coerce("percent", "") is None
        assert coerce("str", None) is None


# ── the write quarantine — the part that must never tap in the dark ─────────

class _FakeTransport:
    """A transport stub: canned dump + version, records taps. No device."""

    def __init__(self, *, version: str | None, dump: str) -> None:
        self._version = version
        self._dump = dump
        self.taps: list[tuple[int, int]] = []
        self.connected = True

    async def connect(self) -> None:
        self.connected = True

    async def foreground_app(self, package: str) -> None:  # noqa: ARG002
        return None

    async def current_app_version(self, package: str) -> str | None:  # noqa: ARG002
        return self._version

    async def dump_ui(self) -> str:
        return self._dump

    async def tap(self, x: int, y: int) -> None:
        self.taps.append((x, y))


def _clock():
    t = {"v": 10_000.0}

    def now() -> float:
        return t["v"]

    def advance(dt: float) -> None:
        t["v"] += dt

    return now, advance


def _writable_vw():
    """VW with its climate/charge tap actions restored, for exercising the WRITE
    mechanism directly. The SHIPPED VW preset quarantines writes (no actions,
    v2.26.0) until the two-step nav is confirmed on a real device; the write
    path (version gate, min-interval, overlay-before-tap) still needs coverage."""
    from dataclasses import replace

    from custom_components.vag_connect.companion.presets import ActionSelector

    return replace(
        PRESETS["volkswagen"],
        actions=(
            ActionSelector(
                action="start_climate",
                content_desc_re=r"(?:Klima\w*\s*(?:starten|ein)|Start climate)",
            ),
            ActionSelector(
                action="stop_climate",
                content_desc_re=r"(?:Klima\w*\s*stoppen|Stop climate)",
            ),
            ActionSelector(
                action="start_charging",
                content_desc_re=r"(?:Laden\s*starten|Start charging)",
            ),
            ActionSelector(
                action="stop_charging",
                content_desc_re=r"(?:Laden\s*stoppen|Stop charging)",
            ),
        ),
    )


class TestWriteQuarantine:
    @pytest.mark.asyncio
    async def test_verified_matching_version_allows_a_tap(self) -> None:
        # Uses a synthetic WRITABLE preset: the shipped VW quarantines writes.
        now, _ = _clock()
        t = _FakeTransport(version="4.2.1", dump=VW_SCREEN)
        ch = CompanionChannel(t, _writable_vw(), time_fn=now)
        await ch.read()
        assert ch.writes_enabled is True
        await ch.do_action("start_climate")
        assert t.taps == [(100, 230)]

    @pytest.mark.asyncio
    async def test_shipped_vw_quarantines_writes_but_still_reads(self) -> None:
        # v2.26.0 — the real VW preset carries NO actions (writes quarantined
        # until the 2-step nav is confirmed), but a verified matching version
        # still reads AND may nav-read.
        now, _ = _clock()
        t = _FakeTransport(version="4.2.1", dump=VW_SCREEN)
        ch = CompanionChannel(t, PRESETS["volkswagen"], time_fn=now)
        fields = await ch.read()
        assert fields["battery_soc"] == 74
        assert ch.writes_enabled is False
        with pytest.raises(CompanionWriteBlocked):
            await ch.do_action("start_climate")
        assert t.taps == []

    @pytest.mark.asyncio
    async def test_version_drift_disables_writes_but_not_reads(self) -> None:
        now, _ = _clock()
        t = _FakeTransport(version="4.3.0", dump=VW_SCREEN)
        ch = CompanionChannel(t, PRESETS["volkswagen"], time_fn=now)
        fields = await ch.read()
        assert fields["battery_soc"] == 74, "reads must keep working on drift"
        assert ch.writes_enabled is False
        with pytest.raises(CompanionWriteBlocked):
            await ch.do_action("start_climate")
        assert t.taps == []

    @pytest.mark.asyncio
    async def test_unknown_version_disables_writes(self) -> None:
        now, _ = _clock()
        t = _FakeTransport(version=None, dump=VW_SCREEN)
        ch = CompanionChannel(t, PRESETS["volkswagen"], time_fn=now)
        await ch.read()
        assert ch.writes_enabled is False

    @pytest.mark.asyncio
    async def test_unverified_brand_never_writes(self) -> None:
        # Even with a matching version, an unverified preset must refuse to tap.
        now, _ = _clock()
        t = _FakeTransport(version="anything", dump=VW_SCREEN)
        ch = CompanionChannel(t, PRESETS["audi"], time_fn=now)
        await ch.read()
        assert ch.writes_enabled is False
        with pytest.raises(CompanionWriteBlocked):
            await ch.do_action("start_climate")


class TestFailureCooldown:
    """No per-read throttle anymore (scan_interval is the cadence); only a
    post-failure cooldown, which must NOT read as a failed poll while active."""

    @pytest.mark.asyncio
    async def test_back_to_back_reads_are_not_throttled(self) -> None:
        # Two reads with no failure in between both run — the old 15-min budget
        # (which mis-counted the second as a failure) is gone.
        now, _ = _clock()
        t = _FakeTransport(version="4.2.1", dump=VW_SCREEN)
        ch = CompanionChannel(t, PRESETS["volkswagen"], time_fn=now)
        assert await ch.read()
        assert await ch.read()  # not None, not throttled

    @pytest.mark.asyncio
    async def test_a_transport_failure_trips_a_cooldown(self) -> None:
        from custom_components.vag_connect.companion.transport import (
            CompanionTransportError,
        )

        now, advance = _clock()

        class _Flaky(_FakeTransport):
            async def dump_ui(self) -> str:
                raise CompanionTransportError("phone asleep")

        t = _Flaky(version="4.2.1", dump=VW_SCREEN)
        ch = CompanionChannel(t, PRESETS["volkswagen"], time_fn=now)
        with pytest.raises(CompanionTransportError):
            await ch.read()
        # next read inside the cooldown window returns None (not a re-raise, not
        # a blank) so the coordinator does not stack failures
        assert await ch.read() is None

    @pytest.mark.asyncio
    async def test_cooldown_clears_after_the_window(self) -> None:
        from custom_components.vag_connect.companion.channel import (
            _FAILURE_COOLDOWN_S,
        )
        from custom_components.vag_connect.companion.transport import (
            CompanionTransportError,
        )

        now, advance = _clock()
        state = {"fail": True}

        class _Recovers(_FakeTransport):
            async def dump_ui(self) -> str:
                if state["fail"]:
                    raise CompanionTransportError("phone asleep")
                return VW_SCREEN

        t = _Recovers(version="4.2.1", dump=VW_SCREEN)
        ch = CompanionChannel(t, PRESETS["volkswagen"], time_fn=now)
        with pytest.raises(CompanionTransportError):
            await ch.read()
        state["fail"] = False
        assert await ch.read() is None  # still cooling down
        advance(_FAILURE_COOLDOWN_S + 1)
        assert await ch.read()  # window elapsed, reads again


# ── the client adapter ──────────────────────────────────────────────────────

class TestCompanionClient:
    def _client(self, transport, brand="volkswagen"):
        from custom_components.vag_connect.companion.client import CompanionClient

        c = CompanionClient.__new__(CompanionClient)
        # wire the internals without touching a real transport
        import time

        from custom_components.vag_connect.companion.channel import CompanionChannel

        c._brand = brand
        c._vin = "WVWZZZAUZFW805377"
        c._transport = transport
        c._channel = CompanionChannel(transport, PRESETS[brand], time_fn=time.monotonic)
        c.on_tokens_changed = None
        c._eu_portal = None
        c._tokens = None
        c._last_data = None
        return c

    @pytest.mark.asyncio
    async def test_get_status_maps_a_read_onto_vehicledata(self) -> None:
        t = _FakeTransport(version="4.2.1", dump=VW_SCREEN)
        c = self._client(t)
        data = await c.get_status("WVWZZZAUZFW805377")
        assert data.battery_soc == 74
        assert data.electric_range_km == 312
        assert data.source_channel == "companion_adb"
        assert data.no_data is False

    @pytest.mark.asyncio
    async def test_empty_read_returns_no_data_not_a_raise(self) -> None:
        t = _FakeTransport(version="4.2.1", dump=_dump(""))
        c = self._client(t)
        data = await c.get_status("WVWZZZAUZFW805377")
        assert data.no_data is True

    @pytest.mark.asyncio
    async def test_get_vehicles_returns_the_configured_vin(self) -> None:
        t = _FakeTransport(version="4.2.1", dump=VW_SCREEN)
        c = self._client(t)
        assert await c.get_vehicles() == ["WVWZZZAUZFW805377"]

    @pytest.mark.asyncio
    async def test_cooldown_poll_returns_last_data_not_no_data(self) -> None:
        # S3: a poll during the post-failure cooldown must not read as a failed
        # poll. The client hands back the last real snapshot, unchanged.
        from custom_components.vag_connect.companion.transport import (
            CompanionTransportError,
        )

        state = {"fail": False}

        class _Flaky(_FakeTransport):
            async def dump_ui(self) -> str:
                if state["fail"]:
                    raise CompanionTransportError("asleep")
                return VW_SCREEN

        t = _Flaky(version="4.2.1", dump=VW_SCREEN)
        c = self._client(t)
        first = await c.get_status("WVWZZZAUZFW805377")
        assert first.battery_soc == 74 and first.no_data is False
        # trip the cooldown, then poll again while it is active
        state["fail"] = True
        try:
            await c.get_status("WVWZZZAUZFW805377")
        except CompanionTransportError:
            pass
        during = await c.get_status("WVWZZZAUZFW805377")
        assert during is first, "cooldown poll should hand back the last snapshot"
        assert during.no_data is False

    @pytest.mark.asyncio
    async def test_cooldown_with_no_history_is_no_data(self) -> None:
        # If the very first poll fails and there is nothing cached, a subsequent
        # cooldown poll returns a clean no_data rather than None.
        from custom_components.vag_connect.companion.transport import (
            CompanionTransportError,
        )

        class _DeadOnArrival(_FakeTransport):
            async def dump_ui(self) -> str:
                raise CompanionTransportError("asleep")

        t = _DeadOnArrival(version="4.2.1", dump=VW_SCREEN)
        c = self._client(t)
        try:
            await c.get_status("WVWZZZAUZFW805377")
        except CompanionTransportError:
            pass
        data = await c.get_status("WVWZZZAUZFW805377")  # in cooldown, no history
        assert data.no_data is True

    @pytest.mark.asyncio
    async def test_command_before_first_poll_still_works_on_a_writable_preset(self) -> None:
        # S4: a command issued before any scheduled read must decide the version
        # gate itself, not reject on the initial None. Exercised on a synthetic
        # writable preset since the shipped VW quarantines writes (v2.26.0).
        now, _ = _clock()
        t = _FakeTransport(version="4.2.1", dump=VW_SCREEN)
        ch = CompanionChannel(t, _writable_vw(), time_fn=now)  # no read() yet
        await ch.do_action("start_climate")
        assert t.taps == [(100, 230)]

    @pytest.mark.asyncio
    async def test_unverified_brand_command_raises_clean_vehiclecommanderror(self) -> None:
        from custom_components.vag_connect.cariad.exceptions import VehicleCommandError

        t = _FakeTransport(version="x", dump=VW_SCREEN)
        c = self._client(t, brand="audi")
        await c.get_status("WVWZZZAUZFW805377")  # decide writes
        with pytest.raises(VehicleCommandError):
            await c.command_start_climate("WVWZZZAUZFW805377")


# ── coordinator integration: B1 (spawn guard) + S1 (read-only) ──────────────

class TestCoordinatorGuards:
    def _coord(self, *, brand: str, client: object):
        from unittest.mock import MagicMock

        from custom_components.vag_connect.coordinator import VagConnectCoordinator
        from custom_components.vag_connect.const import STRATEGY_COMPANION_ADB

        c = VagConnectCoordinator.__new__(VagConnectCoordinator)
        c._cariad_client = client
        c.entry = MagicMock()
        c.entry.data = {"brand": brand, "strategy": STRATEGY_COMPANION_ADB}
        c.entry.options = {}
        c.vehicles = {}
        return c

    def _companion_client(self, brand: str):

        from custom_components.vag_connect.companion.client import CompanionClient

        cl = CompanionClient.__new__(CompanionClient)
        cl._brand = brand
        cl._vin = "V"
        # only the methods a real CompanionClient has
        return cl

    def test_b1_missing_command_method_reported_unavailable(self) -> None:
        # command_lock/flash/wake are not implemented by CompanionClient → the
        # spawn-site guard hides them, so no entity spawns to crash on press.
        c = self._coord(brand="volkswagen", client=self._companion_client("volkswagen"))
        assert c.command_method_available("command_lock") is False
        assert c.command_method_available("command_flash") is False
        assert c.command_method_available("command_wake") is False
        assert c.command_method_available("command_set_target_soc") is False
        assert c.command_method_available("command_set_climate_temperature") is False

    def test_b1_present_command_method_reported_available(self) -> None:
        # climate + charge ARE implemented by the companion adapter.
        c = self._coord(brand="volkswagen", client=self._companion_client("volkswagen"))
        assert c.command_method_available("command_start_climate") is True
        assert c.command_method_available("command_stop_climate") is True
        assert c.command_method_available("command_start_charging") is True

    def test_b1_no_client_defers_to_capability(self) -> None:
        # Before the client is built, the method-availability guard must not
        # hide entities (the capability check still applies).
        c = self._coord(brand="volkswagen", client=None)
        c._cariad_client = None
        assert c.command_method_available("command_lock") is True

    def test_s1_unverified_brand_is_read_only(self) -> None:
        c = self._coord(brand="audi", client=self._companion_client("audi"))
        assert c.is_read_only() is True

    def test_s1_verified_vw_writes_quarantined_is_read_only(self) -> None:
        # v2.26.0 — VW reads are verified but WRITES are quarantined (no actions
        # until the 2-step nav is confirmed on a device), so the companion entry
        # is read-only for now: no command entities spawn.
        c = self._coord(brand="volkswagen", client=self._companion_client("volkswagen"))
        assert c.is_read_only() is True


# ── preset integrity ────────────────────────────────────────────────────────

class TestPresetIntegrity:
    def test_all_five_brands_present(self) -> None:
        assert set(PRESETS) == {"volkswagen", "audi", "skoda", "seat", "cupra"}

    def test_exactly_one_brand_is_verified(self) -> None:
        verified = [b for b, p in PRESETS.items() if p.verified]
        assert verified == ["volkswagen"], (
            "only the brand actually tested on hardware may be verified; "
            f"got {verified}"
        )

    def test_only_verified_presets_are_writable(self) -> None:
        for brand, p in PRESETS.items():
            if p.writable:
                assert p.verified, f"{brand} is writable without being verified"

    def test_unverified_presets_have_no_actions(self) -> None:
        for brand, p in PRESETS.items():
            if not p.verified:
                assert p.actions == (), f"{brand} ships tap actions unverified"

    def test_every_preset_reads_soc_and_range(self) -> None:
        for brand, p in PRESETS.items():
            targets = {f.target for f in p.fields}
            assert "battery_soc" in targets, brand
            assert "electric_range_km" in targets, brand

    def test_every_action_maps_to_a_known_command(self) -> None:
        for brand, p in PRESETS.items():
            for a in p.actions:
                assert a.action in ACTION_TO_COMMAND, f"{brand}:{a.action}"

    def test_packages_are_distinct_and_plausible(self) -> None:
        pkgs = {p.package for p in PRESETS.values()}
        assert len(pkgs) == len(PRESETS)
        assert PRESETS["volkswagen"].package == "com.volkswagen.weconnect"
