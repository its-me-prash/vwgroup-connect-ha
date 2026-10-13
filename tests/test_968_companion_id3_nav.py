# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""v4.4.0 (#968) — We Connect 4.3.2 / MEB reads and the multi-step nav walk.

Two things changed with 4.3.2 and neither is cosmetic:

1. **Labels merged.** State and value now share one narration ("Charging status.
   Battery charge level: 79 per cent. Charging stopped"), which is how a car
   that is plainly NOT charging could be read as charging — the word is in the
   sentence either way.
2. **Values moved off the overview.** The odometer is gone from the main screen
   (a "Driving data" tile shows the last trip instead), so mileage and the
   service countdown are only reachable by walking to the Vehicle Health screen.

The walk is the risky part, so it is tested for what it must never do: tap a
step that is not on screen, press BACK for taps it never made, or start walking
at all on an opt-in the user did not give.

The parking-position read is the same machinery pointed at a gap we have long
documented as unreadable: the app draws the parked car as a map with no
coordinate text, but its own share link carries the coordinates.

HONESTY: none of this is confirmed in-house — our reference car is a Golf GTE.
The overview selectors come from 4.3.2 trees reported in #968; the deeper paths
are modelled on an MEB layout documented elsewhere in the open-source
ecosystem. What is asserted here is the parsing and the navigation contract,
which is exactly the part that must already be right when a tester's dump
confirms the rest.
"""
from __future__ import annotations

import time

import pytest

from custom_components.vag_connect.companion.channel import CompanionChannel
from custom_components.vag_connect.companion.presets import PRESETS, coerce
from custom_components.vag_connect.companion.screen import parse_ui_dump, read_fields

_VW = PRESETS["volkswagen"]


def _dump(nodes_xml: str) -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<hierarchy rotation="0">' + nodes_xml + "</hierarchy>"
    )


def _node(
    desc: str = "",
    *,
    rid: str = "",
    text: str = "",
    clickable: bool = False,
    bounds: str = "[0,0][100,50]",
) -> str:
    return (
        f'<node resource-id="{rid}" content-desc="{desc}" text="{text}" '
        f'class="android.widget.TextView" clickable="{str(clickable).lower()}" '
        f'bounds="{bounds}" />'
    )


# An imperial 4.3.2 overview, in the shape reported for a car on English units:
# every tile narrates one merged sentence.
ID_OVERVIEW_IMPERIAL = _dump(
    _node("Charging status. Battery charge level: 79 per cent. Charging stopped")
    + _node("Range overview. Battery range: 29 miles. Fuel range: 420 miles")
    + _node("Vehicle is locked")
    + _node("Climate. Climate control off", rid="com.volkswagen.weconnect:id/climateTile",
            clickable=True, bounds="[0,200][200,260]")
    + _node("Driving data. Last driven: 1.2 miles. Average consumption: 313.9 mpg")
)

ID_OVERVIEW_CHARGING = _dump(
    _node("Charging status. Battery charge level: 42 per cent. Charging")
    + _node("Range overview. Battery range: 210 Kilometer")
    + _node("Vehicle is unlocked")
    + _node("Climate. Climate control on", rid="climateTile")
)


class TestMergedLabels:
    def test_soc_and_battery_range_come_out_of_the_merged_sentences(self) -> None:
        fields = read_fields(parse_ui_dump(ID_OVERVIEW_IMPERIAL), _VW)
        assert fields["battery_soc"] == 79
        # 29 miles, stored in km — never 29 mislabelled as km.
        assert fields["electric_range_km"] == 47

    def test_the_fuel_range_in_the_same_sentence_is_not_read_as_the_ev_range(
        self,
    ) -> None:
        # "Battery range: 29 miles. Fuel range: 420 miles" — a greedy match here
        # would report a 675 km EV range on a car that has 47.
        fields = read_fields(parse_ui_dump(ID_OVERVIEW_IMPERIAL), _VW)
        assert fields["electric_range_km"] == 47

    def test_a_stopped_charge_is_not_read_as_charging(self) -> None:
        # The regression the merged label caused: "Charging status … Charging
        # stopped" contains the word either way.
        fields = read_fields(parse_ui_dump(ID_OVERVIEW_IMPERIAL), _VW)
        assert fields["is_charging"] is False
        assert "stopped" in str(fields["charging_state"]).lower()

    def test_an_actually_charging_car_still_reads_as_charging(self) -> None:
        fields = read_fields(parse_ui_dump(ID_OVERVIEW_CHARGING), _VW)
        assert fields["is_charging"] is True
        assert fields["battery_soc"] == 42
        assert fields["electric_range_km"] == 210

    def test_lock_state_is_read_and_unlocked_never_matches_locked(self) -> None:
        assert read_fields(parse_ui_dump(ID_OVERVIEW_IMPERIAL), _VW)["doors_locked"] is True
        assert read_fields(parse_ui_dump(ID_OVERVIEW_CHARGING), _VW)["doors_locked"] is False

    def test_climate_tile_state(self) -> None:
        off = read_fields(parse_ui_dump(ID_OVERVIEW_IMPERIAL), _VW)
        on = read_fields(parse_ui_dump(ID_OVERVIEW_CHARGING), _VW)
        assert off["climatisation_active"] is False
        assert on["climatisation_active"] is True

    def test_the_driving_data_tile_is_never_read_as_the_odometer(self) -> None:
        # "Last driven: 1.2 miles" is a trip, not a mileage. Reading it as the
        # odometer would drag that sensor backwards by tens of thousands.
        fields = read_fields(parse_ui_dump(ID_OVERVIEW_IMPERIAL), _VW)
        assert "odometer_km" not in fields

    def test_a_4_2_1_metric_screen_still_reads_through_the_old_selectors(self) -> None:
        old = _dump(
            _node("Ladezustand 74 %")
            + _node("Batteriereichweite: 253 Kilometer")
            + _node("Wird geladen")
            + _node("Kilometerstand 27 886 km")
        )
        fields = read_fields(parse_ui_dump(old), _VW)
        assert fields["battery_soc"] == 74
        assert fields["electric_range_km"] == 253
        assert fields["is_charging"] is True
        assert fields["odometer_km"] == 27886


class TestMapsCoordinates:
    @pytest.mark.parametrize(
        "url",
        [
            "https://www.google.com/maps/place/48.208174,16.373819",
            "https://maps.google.de/maps?q=48.208174,16.373819&z=17",
            "https://www.google.com/maps/@48.208174,16.373819,17z",
            "https://www.google.com/maps/data=!3m1!4b1!3d48.208174!4d16.373819",
        ],
    )
    def test_every_share_link_spelling_yields_the_same_pair(self, url: str) -> None:
        assert coerce("maps_lat", url) == pytest.approx(48.208174)
        assert coerce("maps_lon", url) == pytest.approx(16.373819)

    def test_a_zoom_level_is_never_mistaken_for_a_coordinate(self) -> None:
        assert coerce("maps_lat", "https://maps.google.com/?z=17") is None

    def test_out_of_range_values_are_refused(self) -> None:
        assert coerce("maps_lat", "https://www.google.com/maps/place/948.2,16.3") is None
        assert coerce("maps_lon", "https://www.google.com/maps/place/48.2,916.3") is None

    def test_negative_and_southern_coordinates_survive(self) -> None:
        url = "https://www.google.com/maps/place/-33.868820,-151.209290"
        assert coerce("maps_lat", url) == pytest.approx(-33.86882)
        assert coerce("maps_lon", url) == pytest.approx(-151.20929)


_UP_RIDS = {"vehicleHealthBack", "vwd_navigation_button"}


class _WalkTransport:
    """A phone that changes screen when something is tapped or swiped.

    Dumping does not advance anything, which is what makes it a fair model: the
    walk re-dumps freely (to settle a Compose screen, to look for an up
    control) and only a real interaction moves it on. BACK steps back one
    screen, so a return walk can actually arrive somewhere.
    """

    def __init__(self, screens: list[str], version: str = "4.3.2") -> None:
        self._screens = list(screens)
        self._at = 0
        self._version = version
        self.taps: list[tuple[int, int]] = []
        self.swipes: list[tuple[int, int, int, int]] = []
        self.backs = 0
        self.connected = True

    async def connect(self) -> None:
        self.connected = True

    async def foreground_app(self, package: str) -> None:  # noqa: ARG002
        return None

    async def current_app_version(self, package: str) -> str | None:  # noqa: ARG002
        return self._version

    async def dump_ui(self) -> str:
        return self._screens[min(self._at, len(self._screens) - 1)]

    async def key_back(self) -> None:
        self.backs += 1
        self._at = max(0, self._at - 1)

    async def tap(self, x: int, y: int) -> None:
        self.taps.append((x, y))
        # The app's own up control steps back like BACK does.
        for node in parse_ui_dump(await self.dump_ui()):
            if node.resource_id in _UP_RIDS and node.bounds is not None:
                left, top, right, bottom = node.bounds
                if left <= x <= right and top <= y <= bottom:
                    self._at = max(0, self._at - 1)
                    return
        self._at += 1

    async def swipe(
        self, x1: int, y1: int, x2: int, y2: int, duration_ms: int = 300
    ) -> None:
        self.swipes.append((x1, y1, x2, y2))
        self._at += 1


def _channel(transport: object, opt_ins: set[str]) -> CompanionChannel:
    return CompanionChannel(
        transport,  # type: ignore[arg-type]
        _VW,
        time_fn=time.monotonic,
        nav_opt_ins=opt_ins,
    )


# The screen the walk starts and ends on. ``rangeTile`` is the anchor the
# return walk stops at, and the full-screen root gives the scroll something to
# measure itself against.
def _overview(extra: str = "", scrolled: bool = False) -> str:
    below_fold = (
        _node("Vehicle Health Report. Open details", clickable=True,
              bounds="[0,1400][1080,1600]")
        + _node("Settings. Open details", clickable=True, bounds="[0,1600][1080,1800]")
        if scrolled
        else ""
    )
    return _dump(
        _node(bounds="[0,0][1080,2200]")
        + _node("Range overview. Battery range: 210 Kilometer", rid="rangeTile",
                clickable=True, bounds="[0,200][540,400]")
        + _node("Climate. Climate control off", rid="climateTile", clickable=True,
                bounds="[540,200][1080,400]")
        + below_fold
        + extra
    )


HEALTH_SCREEN = _dump(
    _node(rid="vehicleHealthBack", clickable=True, bounds="[0,100][120,220]")
    + _node(text="Total distance", bounds="[0,300][540,360]")
    + _node(text="27,886 km", bounds="[540,300][1080,360]")
    + _node(text="Next service", bounds="[0,400][540,460]")
    + _node(text="in 320 days", bounds="[540,400][1080,460]")
)

SETTINGS_SCREEN = _dump(
    _node(rid="vwd_navigation_button", clickable=True, bounds="[0,100][120,220]")
    + _node(text="Charging up to", bounds="[0,300][540,360]")
    + _node(text="80 %", bounds="[540,300][1080,360]")
)

# The climate dial: a bare number in the middle of the container, with a
# decoy number off to the side that a naive parse would pick up first.
CLIMATE_SCREEN = _dump(
    _node(rid="vwd_navigation_button", clickable=True, bounds="[0,100][120,220]")
    + _node(rid="clima_compose_view", bounds="[0,400][1000,1000]")
    + _node(text="16", bounds="[40,600][140,700]")
    + _node(text="21.5", bounds="[450,600][550,700]")
    + _node(text="22°C", bounds="[0,1100][300,1160]")
)

MAP_TAB = _dump(
    _node(bounds="[0,0][1080,2200]")
    + _node("Find vehicle", clickable=True, bounds="[800,1800][1040,1900]")
)
MAP_CENTRED = _dump(
    _node(bounds="[0,0][1080,2200]")
    + _node("Google Map", bounds="[0,200][1000,1200]")
)
VEHICLE_CARD = _dump(
    _node(bounds="[0,0][1080,2200]")
    + _node(text="Share", clickable=True, bounds="[800,1500][1000,1600]")
)
SHARE_SHEET = _dump(
    _node(
        rid="content_preview_text",
        text="Parking position https://www.google.com/maps/place/48.208174,16.373819",
        bounds="[0,1700][1080,1800]",
    )
)


class TestNavWalk:
    @pytest.mark.asyncio
    async def test_vehicle_health_needs_a_scroll_and_yields_odometer_and_service(
        self,
    ) -> None:
        # The MEB overview keeps this entry point below the fold: without the
        # scroll the walk correctly refuses to tap, and correctly never arrives.
        transport = _WalkTransport(
            [_overview(), _overview(scrolled=True), HEALTH_SCREEN]
        )
        fields = await _channel(transport, {"vehicle_health"}).read()
        assert fields is not None
        assert transport.swipes, "the below-the-fold tile needs a scroll first"
        assert fields["odometer_km"] == 27886      # not 27, from "27,886 km"
        assert fields["service_due_in_days"] == 320
        assert len(transport.taps) >= 1

    @pytest.mark.asyncio
    async def test_the_scroll_is_measured_from_the_screen_the_phone_reports(
        self,
    ) -> None:
        # A swipe in fixed pixels only works on the display it was written on.
        transport = _WalkTransport(
            [_overview(), _overview(scrolled=True), HEALTH_SCREEN]
        )
        await _channel(transport, {"vehicle_health"}).read()
        x1, y1, x2, y2 = transport.swipes[0]
        assert x1 == x2 == 540           # horizontal centre of a 1080-wide screen
        assert y1 == 1760 and y2 == 770  # 80% -> 35% of a 2200-tall one
        assert y1 > y2                   # upwards, i.e. content moves up

    @pytest.mark.asyncio
    async def test_charge_limit_comes_off_the_settings_screen(self) -> None:
        # Only the Settings entry is below the fold here, so the walk that
        # reaches it is unambiguously the settings one.
        scrolled = _dump(
            _node(bounds="[0,0][1080,2200]")
            + _node("Range overview.", rid="rangeTile", bounds="[0,200][540,400]")
            + _node("Settings. Open details", clickable=True,
                    bounds="[0,1600][1080,1800]")
        )
        transport = _WalkTransport([_overview(), scrolled, SETTINGS_SCREEN])
        fields = await _channel(transport, {"vehicle_health"}).read()
        assert fields is not None
        assert fields["target_soc"] == 80

    @pytest.mark.asyncio
    async def test_climate_target_is_the_number_in_the_middle_of_the_dial(
        self,
    ) -> None:
        # No label, no id, nothing beside it — only its position identifies it.
        # The decoy "16" sits inside the same container, further from centre.
        transport = _WalkTransport([_overview(), CLIMATE_SCREEN])
        fields = await _channel(transport, {"climate_detail"}).read()
        assert fields is not None
        assert fields["target_temperature"] == 21.5
        assert fields["outside_temp"] == 22.0

    @pytest.mark.asyncio
    async def test_parking_position_walks_the_map_and_reads_the_share_link(
        self,
    ) -> None:
        transport = _WalkTransport(
            [
                _overview(
                    _node("Map", rid="cat_nav_map_tab_navigation", clickable=True,
                          bounds="[400,2100][600,2200]")
                ),
                MAP_TAB,
                MAP_CENTRED,
                VEHICLE_CARD,
                SHARE_SHEET,
            ]
        )
        fields = await _channel(transport, {"parking_position"}).read()
        assert fields is not None
        assert fields["latitude"] == pytest.approx(48.208174)
        assert fields["longitude"] == pytest.approx(16.373819)
        assert len(transport.taps) == 4

    @pytest.mark.asyncio
    async def test_the_map_marker_is_tapped_by_position_because_it_has_no_node(
        self,
    ) -> None:
        # "Find vehicle" centres the marker in the upper half of the map view;
        # the marker itself is absent from the accessibility tree, so the tap
        # has to be a fraction of the map's own box.
        transport = _WalkTransport(
            [
                _overview(
                    _node("Map", rid="cat_nav_map_tab_navigation", clickable=True,
                          bounds="[400,2100][600,2200]")
                ),
                MAP_TAB,
                MAP_CENTRED,
                VEHICLE_CARD,
                SHARE_SHEET,
            ]
        )
        await _channel(transport, {"parking_position"}).read()
        # Third tap lands inside the "Google Map" node [0,200][1000,1200], at
        # half its width and 43% of its height — not at its centre.
        assert transport.taps[2] == (500, 630)

    @pytest.mark.asyncio
    async def test_the_return_walk_uses_the_apps_own_close_button_not_back(
        self,
    ) -> None:
        # Android's global BACK is not bounded by the app: from a shallow stack
        # it leaves it, and the next poll finds a launcher instead of a car.
        transport = _WalkTransport(
            [_overview(), _overview(scrolled=True), HEALTH_SCREEN]
        )
        await _channel(transport, {"vehicle_health"}).read()
        assert transport.backs == 0
        # The last tap is the health screen's own back control.
        assert transport.taps[-1] == (60, 160)

    @pytest.mark.asyncio
    async def test_back_is_still_used_when_the_screen_offers_no_up_control(
        self,
    ) -> None:
        bare_detail = _dump(_node(text="nothing to close this with"))
        transport = _WalkTransport(
            [_overview(), _overview(scrolled=True), bare_detail]
        )
        await _channel(transport, {"vehicle_health"}).read()
        assert transport.backs >= 1

    @pytest.mark.asyncio
    async def test_the_return_walk_stops_once_the_overview_is_back(self) -> None:
        # The position path allows four presses; arriving early must not send
        # the app four screens past home.
        transport = _WalkTransport(
            [
                _overview(
                    _node("Map", rid="cat_nav_map_tab_navigation", clickable=True,
                          bounds="[400,2100][600,2200]")
                ),
                MAP_TAB,
            ]
        )
        await _channel(transport, {"parking_position"}).read()
        # Two taps got in, so at most two are needed to get out — the walk must
        # not spend its full four-press budget and end up two screens past home.
        assert transport.backs == 2

    @pytest.mark.asyncio
    async def test_a_path_that_stops_early_backs_out_only_as_far_as_it_walked(
        self,
    ) -> None:
        transport = _WalkTransport(
            [
                _overview(
                    _node("Map", rid="cat_nav_map_tab_navigation", clickable=True,
                          bounds="[400,2100][600,2200]")
                ),
                _dump(_node("a screen with no Find vehicle on it")),
            ]
        )
        fields = await _channel(transport, {"parking_position"}).read()
        assert fields is not None
        assert "latitude" not in fields
        assert len(transport.taps) == 1
        assert transport.backs == 1

    @pytest.mark.asyncio
    async def test_a_missing_first_step_taps_nothing_at_all(self) -> None:
        transport = _WalkTransport([_overview()])
        await _channel(transport, {"vehicle_health", "parking_position"}).read()
        assert transport.taps == []
        assert transport.backs == 0

    @pytest.mark.asyncio
    async def test_each_path_needs_its_own_opt_in(self) -> None:
        # Enabling the charge-detail read must not start a walk to the map or
        # the health report: those are deeper paths with their own consent.
        map_tab = _node("Map", rid="cat_nav_map_tab_navigation", clickable=True,
                        bounds="[400,2100][600,2200]")
        health = _node("Vehicle Health Report. Open details", clickable=True,
                       bounds="[0,1400][1080,1600]")
        transport = _WalkTransport([_overview(map_tab + health)] * 2)
        await _channel(transport, {"charge_detail"}).read()
        # The only forward tap is the charge-detail tile itself.
        assert transport.taps == [(270, 300)]
        assert transport.swipes == []

    @pytest.mark.asyncio
    async def test_no_opt_in_means_no_forward_tap_ever(self) -> None:
        transport = _WalkTransport([_overview(scrolled=True)])
        channel = _channel(transport, set())
        await channel.read()
        assert channel.nav_reads_enabled is False
        assert transport.taps == []

    @pytest.mark.asyncio
    async def test_an_app_version_the_preset_does_not_know_disables_the_walk(
        self,
    ) -> None:
        # Same gate as a write. Newer builds are allowed (each control is found
        # on screen); an unknown OLDER build is not.
        transport = _WalkTransport(
            [_overview(), _overview(scrolled=True), HEALTH_SCREEN], version="1.0.0"
        )
        await _channel(transport, {"vehicle_health"}).read()
        assert transport.taps == []

    @pytest.mark.asyncio
    async def test_a_disabled_control_is_not_treated_as_a_tap_target(self) -> None:
        greyed = _dump(
            _node(bounds="[0,0][1080,2200]")
            + _node("Range overview.", rid="rangeTile", bounds="[0,200][540,400]")
            + '<node resource-id="" content-desc="Vehicle Health Report. Open '
              'details" text="" class="android.widget.TextView" clickable="true" '
              'enabled="false" bounds="[0,1400][1080,1600]" />'
        )
        transport = _WalkTransport([greyed])
        await _channel(transport, {"vehicle_health"}).read()
        assert transport.taps == []

    @pytest.mark.asyncio
    async def test_a_due_walk_starts_from_the_overview_again(self) -> None:
        transport = _WalkTransport(
            [_overview(), _overview(scrolled=True), HEALTH_SCREEN]
        )
        channel = _channel(transport, {"vehicle_health"})
        first = await channel.read()
        assert first is not None and first["odometer_km"] == 27886
        health_tile = transport.taps[0]
        first_taps = list(transport.taps)
        # Nothing new from the car: the report is not walked again, and the
        # value stays from the last walk. Vehicle Settings, under the same
        # switch, is still read every poll.
        second = await channel.read()
        assert second is not None and second["odometer_km"] == 27886
        assert health_tile not in transport.taps[len(first_taps):]
        # A requested refresh walks it again, starting from the overview
        # (#1552; this once passed with no taps only because the poll read
        # the overview selectors off the Health screen it was left on).
        before = len(transport.taps)
        channel.walk_details_next_read()
        third = await channel.read()
        assert third is not None and third["odometer_km"] == 27886
        assert transport.taps[before:] == first_taps


class TestPresetShape:
    def test_every_nav_path_declares_an_opt_in_and_a_walkable_path(self) -> None:
        for preset in PRESETS.values():
            for nav in preset.nav_reads:
                assert nav.path, f"{preset.brand}/{nav.name} has no steps"
                assert nav.opt_in, f"{preset.brand}/{nav.name} has no opt-in"
                assert nav.back_presses >= len(nav.path) or nav.back_presses >= 1

    def test_only_grounded_commands_are_mapped(self) -> None:
        # Charging (#968 Golf GTE / Tiguan charge sheets), the charge limit on
        # vehicle Settings, and the climate sheet (#968 captures + 4.3.2 APK)
        # are grounded; nothing else is mapped.
        from custom_components.vag_connect.companion.climate import CLIMATE_APP_VERSIONS

        battery = {a for a in _VW.actions if a.nav_read in ("charge_detail", "vehicle_settings")}
        assert {a.action: a.nav_read for a in battery} == {
            "start_charging": "charge_detail",
            "stop_charging": "charge_detail",
            "set_charge_target": "vehicle_settings",
            "sync_vehicle": "vehicle_settings",
        }
        assert all(a.app_versions == ("4.6.4", "4.3.2") for a in battery)
        # The Climate Settings switches and zones: grounded in the 4.6.4
        # captures (settings-save and the zone round trips), pinned to 4.6.4.
        settings = {a for a in _VW.actions if a.nav_read == "climate_settings"}
        assert {a.action for a in settings} == {
            "set_climate_at_unlock", "set_window_heating_auto",
            "set_climate_zone_front_left", "set_climate_zone_front_right",
        }
        assert all(a.app_versions == ("4.6.4",) for a in settings)
        # Departure timers: the list switch (4.6.4 and 4.3.2 captures) and the
        # timer page (4.6.4 captures only).
        departure = {a.action: a.app_versions for a in _VW.actions if a.nav_read == "departure_times"}
        assert departure == {
            "toggle_departure_timer": ("4.6.4", "4.3.2"),
            "edit_departure_timer": ("4.6.4",),
        }
        assert {a.action for a in _VW.actions} - {a.action for a in battery | settings} - set(departure) == {
            "start_climate", "stop_climate", "start_window_heating",
            "stop_window_heating", "set_climate_temperature",
        }
        assert CLIMATE_APP_VERSIONS == ("4.6.4", "4.3.2")
