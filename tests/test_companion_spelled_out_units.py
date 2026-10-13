# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""We Connect narrates its units in words, so matching only "km" read nothing.

The Volkswagen preset is the one verified against a real device, and its range
selector still required the literal unit "km". Two accessibility dumps from We
Connect 4.2.1, an ID.4 and an e-up on the same app version, show the overview
tile actually narrating "Batteriereichweite: 253 Kilometer". The selector could
not match that, so on those cars the companion channel read no range at all
while reporting itself healthy.

The strings below are verbatim from those two dumps.

Also pinned here: the e-up's trip tile narrates "Zuletzt 234 Kilometer
gefahren", which is the last trip distance and NOT the odometer. Widening the
unit must not turn that tile into a mileage reading.
"""
from __future__ import annotations

import re

import pytest

from custom_components.vag_connect.companion.presets import PRESETS, coerce
from custom_components.vag_connect.companion.screen import UiNode, read_selectors

_ID4_RANGE = "Übersicht Reichweite. Batteriereichweite: 253 Kilometer. Details öffnen"
_EUP_RANGE = "Übersicht Reichweite. Batteriereichweite: 41 Kilometer. Details öffnen"
_EUP_TRIP = (
    "Fahrdaten. Zuletzt 234 Kilometer gefahren. Durchschnittlicher Verbrauch: "
    "9,8 Kilowattstunden pro 100 Kilometer. Details öffnen"
)


def _field(target: str):
    vw = PRESETS["volkswagen"]
    for field in vw.fields:
        if field.target == target:
            return field
    raise AssertionError(f"no {target} selector on the volkswagen preset")


def _selector(target: str):
    return re.compile(_field(target).content_desc_re)


class TestRangeReadsTheSpelledOutUnit:
    # #968 — the range selector now captures the number AND the spelled-out unit
    # into group(1) so ``range_km`` can convert imperial; assert the coerced km
    # value (the real contract), not the raw capture.
    @pytest.mark.parametrize(("desc", "expected"), [
        (_ID4_RANGE, 253),
        (_EUP_RANGE, 41),
    ])
    def test_real_dumps_parse(self, desc: str, expected: int) -> None:
        field = _field("electric_range_km")
        match = re.compile(field.content_desc_re).search(desc)
        assert match is not None, "the verified preset still cannot read its own app"
        assert coerce(field.parse, match.group(1)) == expected

    def test_the_symbol_still_works(self) -> None:
        """English builds and the older wording used the symbol; both must read."""
        field = _field("electric_range_km")
        match = re.compile(field.content_desc_re).search("Battery range 320 km")
        assert match is not None and coerce(field.parse, match.group(1)) == 320

    def test_imperial_miles_convert_to_km(self) -> None:
        """#968 — a Mk8 on imperial units narrates miles; it must read as km."""
        field = _field("electric_range_km")
        match = re.compile(field.content_desc_re).search("Battery range 14 miles")
        assert match is not None and coerce(field.parse, match.group(1)) == 23


class TestTheTripTileIsNotTheOdometer:
    def test_last_trip_distance_is_not_read_as_mileage(self) -> None:
        """The guard rail on widening the unit: this tile also says Kilometer,
        and reading 234 as the odometer would send the mileage sensor
        backwards by tens of thousands."""
        assert _selector("odometer_km").search(_EUP_TRIP) is None

    def test_a_real_odometer_still_reads(self) -> None:
        match = _selector("odometer_km").search("Kilometerstand 12 345 km")
        assert match is not None and match.group(1).strip() == "12 345"


# Verbatim from the VW 4.6.4 charge detail while charging (charging/01-range.xml).
_464_CHARGE = (
    "Charging details. One hour and. 40 minutes of charging time left. Charging "
    "capacity: 1 kilowatt. Target charge level: 80 per cent"
)


def _charge_detail_node(desc: str):
    return UiNode(
        resource_id="", content_desc=desc, text="", clazz="android.view.View",
        clickable=False, bounds=(0, 0, 100, 100),
    )


class TestRemainingChargeTimeSpelledOutHour:
    """4.6.4 spells a count of one out, so only the minutes read: 40 not 100."""

    def test_the_464_string_reads_hours_plus_minutes(self) -> None:
        charge = next(nav for nav in PRESETS["volkswagen"].nav_reads if nav.name == "charge_detail")
        fields = read_selectors([_charge_detail_node(_464_CHARGE)], charge.values)
        assert fields["remaining_charge_time_min"] == 100

    @pytest.mark.parametrize(("raw", "expected"), [
        (_464_CHARGE, 100),
        # The 4.3.2 forms the existing captures pin.
        ("Charging details. 2 hours and. 15 minutes of charging time left", 135),
        ("Charging details. Zero hours and. 55 minutes of charging time left. "
         "Charging speed: 11 kilometres per hour", 55),
        ("Ladedetails. 4 Stunden und. 5 Minuten Ladezeit verbleibend", 245),
        # Singular/plural and spelled-out on either side.
        ("One hour and. One minute of charging time left", 61),
        ("3 hours and. Zero minutes of charging time left", 180),
        ("Eine Stunde und. 20 Minuten Ladezeit verbleibend", 80),
        # Hours-only and minutes-only.
        ("2 hours", 120),
        ("One hour", 60),
        ("40 minutes of charging time left", 40),
        ("One minute of charging time left", 1),
        ("noch 90 min", 90),
        ("1:45 h", 105),
    ])
    def test_hours_and_minutes_are_summed(self, raw: str, expected: int) -> None:
        assert coerce("hm_minutes", raw) == expected

    def test_a_speed_per_hour_is_not_an_hour_count(self) -> None:
        assert coerce("hm_minutes", "Charging speed: 11 kilometres per hour") is None
        assert coerce("hm_minutes", "Ladegeschwindigkeit: 62 Kilometer pro Stunde") is None
