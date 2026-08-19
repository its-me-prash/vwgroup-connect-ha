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
