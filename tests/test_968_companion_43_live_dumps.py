# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""v4.4.0 (#968) — the companion selectors against REAL We Connect 4.3.2 screens.

Everything here is taken from the `uiautomator` dumps @plainmad captured on a
live Mk8 Golf GTE running We Connect 4.3.2 in English/imperial: the vehicle
overview, the charge-detail sheet behind the range tile, the Air Conditioning
sheet, and the Vehicle Health Report. Until these, the 4.3.2 selectors were
modelled rather than observed, and modelling got several of them wrong:

- the service countdown reads "71 days / 12,100 mi" — one string with a day
  count AND a distance, so taking the first number found returned 12,100;
- the lock tile narrates "Vehicle. Locked. Open details", not "Vehicle is
  locked", so the previous pattern matched nothing at all;
- the charge state is not on the overview on this layout, only on the detail
  sheet, so reading it from the overview could never have worked;
- the two climate switches carry their state in ``checked``, never in text.

Per CONTRIBUTING's privacy rules these fragments are redacted: the outside
temperature line carried the tester's town, which is location data, so it reads
``Somewhere`` here. Node attributes are otherwise verbatim, because the exact
strings are the whole point.
"""
from __future__ import annotations

import time

import pytest

from custom_components.vag_connect.companion.channel import CompanionChannel
from custom_components.vag_connect.companion.presets import PRESETS
from custom_components.vag_connect.companion.screen import parse_ui_dump, read_fields

_VW = PRESETS["volkswagen"]


def _dump(nodes_xml: str) -> str:
    return (
        "<?xml version='1.0' encoding='UTF-8' standalone='yes' ?>"
        '<hierarchy rotation="0">' + nodes_xml + "</hierarchy>"
    )


def _n(
    *,
    rid: str = "",
    text: str = "",
    desc: str = "",
    bounds: str = "[0,0][720,100]",
    clickable: str = "false",
    checkable: str = "false",
    checked: str = "false",
    enabled: str = "true",
) -> str:
    return (
        f'<node index="0" text="{text}" resource-id="{rid}" '
        f'class="android.view.View" package="com.volkswagen.weconnect" '
        f'content-desc="{desc}" checkable="{checkable}" checked="{checked}" '
        f'clickable="{clickable}" enabled="{enabled}" bounds="{bounds}" />'
    )


# ── the four live screens ────────────────────────────────────────────────────
#
# Note what is NOT here: nothing on the overview is clickable="true" except the
# bottom tabs. Compose renders the tiles without the flag even though they open
# on tap ("Open details" in their description), which is why the walk must fall
# back to a matching non-clickable node instead of requiring clickable.

OVERVIEW = _dump(
    _n(rid="com.volkswagen.weconnect:id/composeView", bounds="[0,0][720,1327]")
    + _n(rid="rangeTile", bounds="[43,549][334,842]")
    + _n(
        desc="Range overview. Battery range: 29 miles. Fuel range: 420 miles. Open details",
        bounds="[43,549][334,842]",
    )
    + _n(rid="climateTile", bounds="[386,549][677,842]")
    + _n(desc="Climate control. Off. Open details", bounds="[386,549][677,842]")
    + _n(desc="Vehicle. Locked. Open details", bounds="[43,893][677,1029]")
    + _n(text="Locked", bounds="[496,941][583,974]")
    + _n(desc="Horn and Turn Signals. Open details", bounds="[43,1029][677,1165]")
    + _n(desc="Departure times. Open details", bounds="[43,1165][677,1301]")
    + _n(
        desc=(
            "Driving data. Last driven: 1.2 miles. Average consumption: "
            "313.9 miles per gallon. Open details"
        ),
        bounds="[43,1301][677,1327]",
    )
    + _n(
        desc="Your vehicle: Golf GTE. Synchronised 21 minutes ago",
        bounds="[111,83][601,121]",
    )
    + _n(
        rid="cat_nav_map_tab_navigation",
        desc="Navigation Tab",
        clickable="true",
        bounds="[240,1346][480,1431]",
    )
)

CHARGE_SHEET = _dump(
    _n(desc="Close sheet", clickable="true", bounds="[0,0][720,669]")
    + _n(desc="Close", bounds="[44,713][95,764]")
    + _n(desc="Range overview. Battery range: 29 miles", bounds="[85,798][635,1073]")
    + _n(rid="rangeArcRangeAndUnit", bounds="[256,909][481,1065]")
    + _n(
        rid="rangeArcBatterySoc",
        text="Battery 79 %",
        desc="Charging status. Battery charge level: 79 per cent. Charging stopped",
        bounds="[268,1105][452,1144]",
    )
    + _n(desc="Start charging", bounds="[85,1278][635,1380]")
)

CLIMATE_SHEET = _dump(
    _n(rid="vwd_navigation_button", clickable="true", bounds="[17,339][119,441]")
    + _n(rid="vwd_title", text="Air Conditioning", bounds="[245,371][475,409]")
    + _n(rid="outside_temperature_layout", bounds="[0,416][720,445]")
    # Redacted: the live string named the tester's town.
    + _n(text="Somewhere: 22°C", bounds="[283,416][438,445]")
    + _n(rid="clima_compose_view", bounds="[0,501][720,728]")
    + _n(text="19.5", bounds="[0,518][123,617]")
    + _n(text="°", bounds="[123,518][145,587]")
    + _n(text="20", bounds="[281,501][409,634]")
    + _n(text="°", bounds="[409,501][439,593]")
    + _n(text="20.5", bounds="[576,518][720,617]")
    + _n(rid="air_conditioning_title", text="Air conditioning", bounds="[163,866][515,899]")
    + _n(
        rid="air_conditioning_toggle",
        clickable="true",
        checkable="true",
        checked="true",
        bounds="[532,855][634,912]",
    )
    + _n(rid="window_heating_title", text="Window heating", bounds="[163,1006][515,1039]")
    + _n(
        rid="window_heating_toggle",
        clickable="true",
        checkable="true",
        checked="false",
        bounds="[532,995][634,1052]",
    )
    + _n(rid="cta_start", text="Start", clickable="true", bounds="[85,1278][635,1380]")
)

HEALTH_REPORT = _dump(
    _n(rid="vehicleHealthBack", clickable="true", bounds="[17,120][119,222]")
    + _n(desc="Vehicle Health Report", bounds="[162,152][558,190]")
    + _n(rid="totalDistance", bounds="[43,300][677,400]")
    + _n(text="Total distance", bounds="[86,320][400,360]")
    + _n(text="22,015 mi", bounds="[400,320][634,360]")
    + _n(rid="nextInspection", bounds="[43,400][677,500]")
    + _n(text="Next service", bounds="[86,420][400,460]")
    + _n(text="71 days / 12,100 mi", bounds="[400,420][634,460]")
    + _n(rid="oilService", bounds="[43,500][677,600]")
    + _n(text="Next oil service", bounds="[86,520][400,560]")
    + _n(text="71 days / 1,500 mi", bounds="[400,520][634,560]")
    + _n(rid="warningHeaderTitle", text="No issues found", bounds="[43,620][677,660]")
    + _n(
        rid="warningHeaderSubtitle",
        text="Synchronised: Just now",
        bounds="[43,660][677,700]",
    )
)


class TestLiveOverview:
    def test_range_is_the_battery_one_converted_from_miles(self) -> None:
        fields = read_fields(parse_ui_dump(OVERVIEW), _VW)
        assert fields["electric_range_km"] == 47  # 29 mi, not the 420 mi fuel range

    def test_lock_state_reads_from_the_real_tile_wording(self) -> None:
        # "Vehicle. Locked. Open details" — sentence fragments, not "Vehicle is
        # locked". The modelled pattern matched nothing on this screen.
        assert read_fields(parse_ui_dump(OVERVIEW), _VW)["doors_locked"] is True

    def test_an_unlocked_car_is_not_read_as_locked(self) -> None:
        unlocked = OVERVIEW.replace("Vehicle. Locked.", "Vehicle. Unlocked.")
        assert read_fields(parse_ui_dump(unlocked), _VW)["doors_locked"] is False

    def test_climate_tile_state(self) -> None:
        assert read_fields(parse_ui_dump(OVERVIEW), _VW)["climatisation_active"] is False

    def test_sync_age_from_the_vehicle_header(self) -> None:
        from custom_components.vag_connect.companion.screen import find_sync_age

        assert find_sync_age(parse_ui_dump(OVERVIEW), _VW) == 21 * 60

    def test_the_last_trip_tile_is_never_read_as_the_odometer(self) -> None:
        # "Last driven: 1.2 miles" is a trip. 4.3.2 has no odometer here at all.
        assert "odometer_km" not in read_fields(parse_ui_dump(OVERVIEW), _VW)

    def test_no_charge_state_is_invented_from_a_screen_that_lacks_it(self) -> None:
        # The overview carries no charge sentence on this layout: reading one
        # anyway would mean inventing it.
        fields = read_fields(parse_ui_dump(OVERVIEW), _VW)
        assert "battery_soc" not in fields
        assert "is_charging" not in fields


class TestLiveChargeSheet:
    @staticmethod
    def _nav_values() -> tuple:
        nav = next(n for n in _VW.nav_reads if n.name == "charge_detail")
        return nav.values

    def test_soc_state_and_range_come_off_the_detail_sheet(self) -> None:
        from custom_components.vag_connect.companion.screen import read_selectors

        fields = read_selectors(parse_ui_dump(CHARGE_SHEET), self._nav_values())
        assert fields["battery_soc"] == 79
        assert fields["is_charging"] is False
        assert "stopped" in str(fields["charging_state"]).lower()

    def test_a_car_that_is_actually_charging_reads_as_charging(self) -> None:
        from custom_components.vag_connect.companion.screen import read_selectors

        charging = CHARGE_SHEET.replace(
            "Charging stopped", "Currently charging"
        )
        fields = read_selectors(parse_ui_dump(charging), self._nav_values())
        assert fields["is_charging"] is True

    def test_absent_values_stay_absent_rather_than_reading_zero(self) -> None:
        # The car was unplugged, so there is no target SoC, power or remaining
        # time on this sheet. None of them may be invented.
        from custom_components.vag_connect.companion.screen import read_selectors

        fields = read_selectors(parse_ui_dump(CHARGE_SHEET), self._nav_values())
        for absent in ("target_soc", "charging_power_kw", "remaining_charge_time_min"):
            assert absent not in fields

    def test_the_sheet_offers_a_close_control_the_walk_can_use(self) -> None:
        from custom_components.vag_connect.companion.screen import find_node_for

        nodes = parse_ui_dump(CHARGE_SHEET)
        assert any(
            find_node_for(nodes, spec) is not None for spec in _VW.up_controls
        ), "no up control matched the charge sheet; the walk would fall back to BACK"


class TestLiveClimateSheet:
    @staticmethod
    def _nav_values() -> tuple:
        nav = next(n for n in _VW.nav_reads if n.name == "climate_detail")
        return nav.values

    def test_target_temperature_is_the_middle_number_of_the_dial(self) -> None:
        from custom_components.vag_connect.companion.screen import read_selectors

        # The dial renders three bare numbers side by side (19.5 | 20 | 20.5)
        # with no label, no id and nothing beside them. Only the middle one is
        # the setting.
        fields = read_selectors(parse_ui_dump(CLIMATE_SHEET), self._nav_values())
        assert fields["target_temperature"] == 20.0

    def test_outside_temperature_is_read_despite_the_text_around_it(self) -> None:
        from custom_components.vag_connect.companion.screen import read_selectors

        fields = read_selectors(parse_ui_dump(CLIMATE_SHEET), self._nav_values())
        assert fields["outside_temp"] == 22.0

    def test_switch_states_come_from_checked_not_from_their_labels(self) -> None:
        from custom_components.vag_connect.companion.screen import read_selectors

        fields = read_selectors(parse_ui_dump(CLIMATE_SHEET), self._nav_values())
        assert fields["climatisation_active"] is True    # air conditioning on
        assert fields["window_heating_enabled"] is False  # window heating off

    def test_a_container_sharing_a_switch_id_cannot_read_as_off(self) -> None:
        from custom_components.vag_connect.companion.screen import read_selectors

        # The row wrapper is not checkable; only the switch itself is.
        rowed = CLIMATE_SHEET.replace(
            '<node index="0" text="" resource-id="air_conditioning_toggle"',
            '<node index="0" text="" resource-id="air_conditioning_toggle_row"',
        )
        fields = read_selectors(parse_ui_dump(rowed), self._nav_values())
        assert fields.get("climatisation_active") is None

    def test_the_sheet_offers_its_own_up_control(self) -> None:
        from custom_components.vag_connect.companion.screen import find_node_for

        nodes = parse_ui_dump(CLIMATE_SHEET)
        assert find_node_for(nodes, _VW.up_controls[0]) is not None


class TestLiveHealthReport:
    @staticmethod
    def _nav_values() -> tuple:
        nav = next(n for n in _VW.nav_reads if n.name == "vehicle_health")
        return nav.values

    def test_odometer_survives_both_the_comma_and_the_miles(self) -> None:
        from custom_components.vag_connect.companion.screen import read_selectors

        # "22,015 mi" → 22015 miles → 35,430 km. Before the comma fix this read
        # back as 22 km: the comma was matched as a thousands separator but not
        # stripped, so int() threw and the fallback took the first digit run.
        fields = read_selectors(parse_ui_dump(HEALTH_REPORT), self._nav_values())
        assert fields["odometer_km"] == 35430

    def test_the_service_countdown_is_days_not_the_mileage_beside_it(self) -> None:
        from custom_components.vag_connect.companion.screen import read_selectors

        # "71 days / 12,100 mi" — first-number-wins returned 12,100, which then
        # failed the sanity range, so the value silently never appeared.
        fields = read_selectors(parse_ui_dump(HEALTH_REPORT), self._nav_values())
        assert fields["service_due_in_days"] == 71
        assert fields["oil_service_due_in_days"] == 71

    def test_the_report_offers_its_own_back_control(self) -> None:
        from custom_components.vag_connect.companion.screen import find_node_for

        nodes = parse_ui_dump(HEALTH_REPORT)
        assert any(find_node_for(nodes, spec) is not None for spec in _VW.up_controls)


class _ScreenSequence:
    """Replays the live screens in the order a real walk would meet them."""

    def __init__(self, screens: list[str]) -> None:
        self._screens = screens
        self._at = 0
        self.taps: list[tuple[int, int]] = []
        self.backs = 0
        self.connected = True

    async def connect(self) -> None:
        self.connected = True

    async def foreground_app(self, package: str) -> None:  # noqa: ARG002
        return None

    async def current_app_version(self, package: str) -> str | None:  # noqa: ARG002
        return "4.3.2"

    async def dump_ui(self) -> str:
        return self._screens[min(self._at, len(self._screens) - 1)]

    async def tap(self, x: int, y: int) -> None:
        self.taps.append((x, y))
        self._at += 1

    async def key_back(self) -> None:
        self.backs += 1
        self._at = max(0, self._at - 1)


class TestLiveWalk:
    @pytest.mark.asyncio
    async def test_the_charge_detail_walk_on_the_real_screens(self) -> None:
        transport = _ScreenSequence([OVERVIEW, CHARGE_SHEET])
        channel = CompanionChannel(
            transport,  # type: ignore[arg-type]
            _VW,
            time_fn=time.monotonic,
            read_charge_detail=True,
        )
        fields = await channel.read()
        assert fields is not None
        # Overview values and detail values end up in one snapshot.
        assert fields["electric_range_km"] == 47
        assert fields["doors_locked"] is True
        assert fields["battery_soc"] == 79
        assert fields["is_charging"] is False
        # One tap in on the range tile, and the sheet's own Close on the way out.
        assert len(transport.taps) == 2
        assert transport.backs == 0

    @pytest.mark.asyncio
    async def test_a_tile_without_the_clickable_flag_is_still_reachable(self) -> None:
        # Nothing on the live overview is clickable="true" except the bottom
        # tabs, so requiring the flag would strand every nav read.
        transport = _ScreenSequence([OVERVIEW, CHARGE_SHEET])
        channel = CompanionChannel(
            transport,  # type: ignore[arg-type]
            _VW,
            time_fn=time.monotonic,
            read_charge_detail=True,
        )
        await channel.read()
        assert transport.taps, "the range tile was never tapped"
