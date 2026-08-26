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

HONESTY: these selectors are seeded from 4.3.2 trees reported by users, not
confirmed in-house on an ID.3. What is asserted here is the parsing and the
navigation contract, which is exactly the part that must not be wrong when a
tester's dump confirms the rest.
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


class _WalkTransport:
    """Serves a scripted sequence of screens and records taps and BACKs."""

    def __init__(self, screens: list[str], version: str = "4.3.2") -> None:
        self._screens = list(screens)
        self._version = version
        self.taps: list[tuple[int, int]] = []
        self.backs = 0
        self.connected = True

    async def connect(self) -> None:
        self.connected = True

    async def foreground_app(self, package: str) -> None:  # noqa: ARG002
        return None

    async def current_app_version(self, package: str) -> str | None:  # noqa: ARG002
        return self._version

    async def dump_ui(self) -> str:
        return self._screens.pop(0) if len(self._screens) > 1 else self._screens[0]

    async def key_back(self) -> None:
        self.backs += 1

    async def tap(self, x: int, y: int) -> None:
        self.taps.append((x, y))


def _channel(transport: object, opt_ins: set[str]) -> CompanionChannel:
    return CompanionChannel(
        transport,  # type: ignore[arg-type]
        _VW,
        time_fn=time.monotonic,
        nav_opt_ins=opt_ins,
    )


HEALTH_SCREEN = _dump(
    _node("Total distance 27 886 km", rid="totalDistance")
    + _node("Next service in 320 days", rid="nextInspection")
)

SHARE_SHEET = _dump(
    _node(
        "Parking position https://www.google.com/maps/place/48.208174,16.373819",
        rid="content_preview_text",
    )
)


class TestNavWalk:
    @pytest.mark.asyncio
    async def test_vehicle_health_supplies_the_odometer_the_overview_lost(self) -> None:
        overview = _dump(
            _node("Charging status. Battery charge level: 79 per cent. Charging stopped")
            + _node("Vehicle Health", rid="vehicleHealthTile", clickable=True,
                    bounds="[0,300][200,360]")
        )
        transport = _WalkTransport([overview, overview, HEALTH_SCREEN])
        fields = await _channel(transport, {"vehicle_health"}).read()
        assert fields is not None
        assert fields["odometer_km"] == 27886
        assert fields["service_due_in_days"] == 320
        assert transport.taps == [(100, 330)]
        assert transport.backs == 1  # exactly as deep as we walked

    @pytest.mark.asyncio
    async def test_parking_position_is_read_from_the_share_link(self) -> None:
        overview = _dump(
            _node("Navigation", rid="navigationTile", clickable=True,
                  bounds="[0,0][100,50]")
        )
        map_screen = _dump(
            _node("Parking position", rid="parkingPositionMarker", clickable=True,
                  bounds="[0,60][100,110]")
        )
        marker_screen = _dump(
            _node("Share", rid="shareButton", clickable=True, bounds="[0,120][100,170]")
        )
        transport = _WalkTransport(
            [overview, overview, map_screen, marker_screen, SHARE_SHEET]
        )
        fields = await _channel(transport, {"parking_position"}).read()
        assert fields is not None
        assert fields["latitude"] == pytest.approx(48.208174)
        assert fields["longitude"] == pytest.approx(16.373819)
        assert len(transport.taps) == 3
        assert transport.backs == 3  # all the way back out of the share sheet

    @pytest.mark.asyncio
    async def test_a_path_that_stops_early_backs_out_only_as_far_as_it_walked(
        self,
    ) -> None:
        # The share button never appears. Pressing BACK three times here would
        # leave the app somewhere behind the overview for the next poll.
        overview = _dump(
            _node("Navigation", rid="navigationTile", clickable=True,
                  bounds="[0,0][100,50]")
        )
        map_screen = _dump(
            _node("Parking position", rid="parkingPositionMarker", clickable=True,
                  bounds="[0,60][100,110]")
        )
        dead_end = _dump(_node("Something else entirely"))
        transport = _WalkTransport([overview, overview, map_screen, dead_end, dead_end])
        fields = await _channel(transport, {"parking_position"}).read()
        assert fields is not None
        assert "latitude" not in fields
        assert len(transport.taps) == 2
        assert transport.backs == 2

    @pytest.mark.asyncio
    async def test_a_missing_first_step_taps_nothing_at_all(self) -> None:
        overview = _dump(_node("Charging status. Battery charge level: 50 per cent."))
        transport = _WalkTransport([overview])
        await _channel(transport, {"vehicle_health", "parking_position"}).read()
        assert transport.taps == []
        assert transport.backs == 0

    @pytest.mark.asyncio
    async def test_each_path_needs_its_own_opt_in(self) -> None:
        # Enabling the charge-detail read must not start a walk through the
        # navigation screens: it is a deeper path with its own consent.
        overview = _dump(
            _node("Navigation", rid="navigationTile", clickable=True)
            + _node("Vehicle Health", rid="vehicleHealthTile", clickable=True)
        )
        transport = _WalkTransport([overview])
        await _channel(transport, {"charge_detail"}).read()
        assert transport.taps == []

    @pytest.mark.asyncio
    async def test_no_opt_in_means_no_forward_tap_ever(self) -> None:
        overview = _dump(_node("Vehicle Health", rid="vehicleHealthTile", clickable=True))
        transport = _WalkTransport([overview])
        channel = _channel(transport, set())
        await channel.read()
        assert channel.nav_reads_enabled is False
        assert transport.taps == []

    @pytest.mark.asyncio
    async def test_an_app_version_the_preset_does_not_know_disables_the_walk(
        self,
    ) -> None:
        # Same gate as a write: a drifted layout means a stale map, and a tap on
        # a stale map is a tap on the wrong control.
        overview = _dump(
            _node("Vehicle Health", rid="vehicleHealthTile", clickable=True,
                  bounds="[0,300][200,360]")
        )
        transport = _WalkTransport([overview, overview, HEALTH_SCREEN], version="9.9.9")
        await _channel(transport, {"vehicle_health"}).read()
        assert transport.taps == []

    @pytest.mark.asyncio
    async def test_nav_values_are_cached_between_the_15_minute_walks(self) -> None:
        overview = _dump(
            _node("Charging status. Battery charge level: 79 per cent. Charging stopped")
            + _node("Vehicle Health", rid="vehicleHealthTile", clickable=True,
                    bounds="[0,300][200,360]")
        )
        transport = _WalkTransport([overview, overview, HEALTH_SCREEN, overview])
        channel = _channel(transport, {"vehicle_health"})
        first = await channel.read()
        assert first is not None and first["odometer_km"] == 27886
        second = await channel.read()
        assert second is not None
        # Second poll is inside the cadence window: no new taps, value retained.
        assert second["odometer_km"] == 27886
        assert len(transport.taps) == 1


class TestPresetShape:
    def test_every_nav_path_declares_an_opt_in_and_a_walkable_path(self) -> None:
        for preset in PRESETS.values():
            for nav in preset.nav_reads:
                assert nav.path, f"{preset.brand}/{nav.name} has no steps"
                assert nav.opt_in, f"{preset.brand}/{nav.name} has no opt-in"
                assert nav.back_presses >= len(nav.path) or nav.back_presses >= 1

    def test_no_write_action_was_inferred_from_the_unconfirmed_4_3_2_tree(self) -> None:
        # Reads seeded from a reported dump are recoverable if wrong; a tap is
        # not. VW stays read-only until a real device confirms the tap map.
        assert _VW.actions == ()
        assert _VW.writable is False
