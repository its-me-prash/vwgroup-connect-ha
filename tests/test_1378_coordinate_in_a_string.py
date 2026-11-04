# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#1378 — the Vehicle Data Scout posted a reporter's parked position.

MEB portal cars ship the vehicle position in the continuous EU Data Act feed as
the STRING ``persLocation`` = ``"[<lat>, <lon>]"``, six decimals (~0.1 m). Every
Scout issue carries a footer promising its readers "GPS rounded to 1 decimal",
and ``mask_value`` did round — but only a ``float``. Every string form went out
at full precision, so the coordinates had to be hand-redacted in the issue body
and the original revision deleted.

Measured on the unfixed masker: of nine shapes a coordinate can arrive in, six
survived with full precision, and every one of those six was a string. The VIN
in a hex blob, two fixes earlier in the same module, leaked five times before
anyone fixed the masker. This is that defect in a second data type.

Every coordinate in this file is invented. The reporter's own value is not in
this repository and must not come back into it — not as a fixture, not as an
example, not in a docstring.
"""
from __future__ import annotations

import json
import re

import pytest

from custom_components.vag_connect.cariad._unexpected_keys import (
    detect_unexpected,
    mask_value,
)

# Anything still carrying two or more decimals was not rounded to one.
PRECISE = re.compile(r"\d{1,3}\.\d{2,}")

# The shape the portal actually sends, with invented digits.
OBSERVED = "[50.123456, 4.654321]"


def test_the_observed_persLocation_shape_is_rounded() -> None:
    # The fixture itself has to be precise, or the test proves nothing.
    assert PRECISE.search(OBSERVED), "fixture must carry full precision"
    out = mask_value(OBSERVED)
    assert not PRECISE.search(out), f"coordinate survived in {out!r}"
    assert out == '"[50.1, 4.7]"', out


@pytest.mark.parametrize(
    "value",
    [
        "[50.123456, 4.654321]",          # persLocation, as the car sends it
        "50.123456,4.654321",             # bare pair, no space
        "50.123456; 4.654321",            # semicolon
        "50.123456 4.654321",             # whitespace only
        "50.123456N 4.654321E",           # hemisphere letters
        "parked at 50.123456, 4.654321 since 08:00",   # inside a sentence
        "https://maps.google.com/?q=50.123456,4.654321",  # URL query
        "-33.333300, 151.444400",         # southern / eastern hemisphere
    ],
)
def test_no_string_shape_keeps_full_precision(value: str) -> None:
    assert PRECISE.search(value), "fixture must carry full precision"
    out = mask_value(value)
    assert not PRECISE.search(out), f"coordinate survived in {out!r}"


def test_a_float_still_rounds_as_it_always_did() -> None:
    """Positive control for the path that was never broken."""
    assert mask_value(50.123456) == "50.1"
    assert mask_value(-4.654321) == "-4.7"


def test_the_field_name_catches_a_lone_coordinate() -> None:
    """A car that splits the position into two leaves sends two lone values.

    Nothing in the value itself says "50.123456" is a latitude, so the masker
    needs the path. Both call sites pass it.
    """
    assert mask_value("50.123456", path_hint="eu_data_act.latitude") == '"50.1"'
    assert mask_value("4.654321", path_hint="position.lon") == '"4.7"'
    assert mask_value("50.123456", path_hint="eu_data_act.persLocation") == '"50.1"'


def test_a_lookalike_field_name_does_not_trigger_rounding() -> None:
    """``lat`` sits inside "translation" and "related"; ``location`` inside
    "allocation". A name match on a substring would round unrelated numbers."""
    for path in (
        "vehicle.relatedVehicles.distance",
        "ui.translationVersion",
        "doors.doorLatchStatus",
        "billing.allocationShare",
        "seat.plateThickness",
    ):
        assert mask_value("12.345678", path_hint=path) == '"12.345678"', path


def test_the_documented_limits_are_still_the_limits() -> None:
    """Two shapes the masker deliberately does not touch, pinned so the limit
    is visible instead of silent.

    A comma-decimal pair cannot be told apart from thousands separators, and
    rounding those would corrupt ordinary numbers. A lone decimal with no path
    is indistinguishable from a consumption figure — and does not arise in
    practice, because both call sites pass the path.

    If you close one of these, delete the line here AND the matching sentence
    in ``mask_value``'s docstring. A limit documented in only one of the two
    places is how the last one went unnoticed.
    """
    assert mask_value("50,123456 4,654321") == '"50,123456 4,654321"'
    assert mask_value("50.123456") == '"50.123456"'


@pytest.mark.parametrize(
    "value,expected",
    [
        ("5.1.3", '"5.1.3"'),                           # a version string
        ("15.8 kWh/100km", '"15.8 kWh/100km"'),         # a consumption figure
        ("2026-09-09T20:08:40.237963+00:00", '"2026-09-09T20:08:40.237963+00:00"'),
        ("123456.789, 123457.890", '"123456.789, 123457.890"'),   # odometer pair
        ("1234.5678, 2345.6789", '"1234.5678, 2345.6789"'),       # money pair
        ("999.123456, 888.654321", '"999.123456, 888.654321"'),   # too many digits
        # Matches the pattern and is rejected by the bounds check: no latitude
        # reaches 95. This is the branch that keeps a two-decimal measurement
        # pair from being rounded just because it looks coordinate-shaped.
        ("95.123456, 4.654321", '"95.123456, 4.654321"'),
        ("50.123456, 191.654321", '"50.123456, 191.654321"'),
    ],
)
def test_numbers_that_are_not_positions_are_left_alone(value: str, expected: str) -> None:
    """Rounding the wrong number costs the Scout its diagnostic value, which is
    the whole reason the report exists."""
    assert mask_value(value) == expected


def test_the_rounded_sample_still_says_what_the_field_was() -> None:
    """Brackets and hemisphere letters survive, so a reader can still tell a
    position field from a number field without learning where the car stood."""
    assert mask_value("[50.123456, 4.654321]") == '"[50.1, 4.7]"'
    assert mask_value("50.123456N 4.654321E") == '"50.1N 4.7E"'


def test_the_earlier_fixes_still_hold() -> None:
    """Regression control: the coordinate rule runs beside the VIN and UUID
    rules, not instead of them."""
    assert mask_value("WVWZZZAUZFW000000") == '"***000000"'
    assert mask_value("4f3a2b1c-5d6e-7f80-9a1b-2c3d4e5f6071") == '"[uuid]"'


def test_the_scout_report_itself_cannot_carry_the_pair() -> None:
    """The gate that matters: the whole chain, not just the helper.

    ``persLocation`` is not a registered key, so the Scout flags it and puts
    ``sample_masked`` straight into a public issue body.
    """
    findings = list(
        detect_unexpected("skoda", "vehicle-status", {"persLocation": OBSERVED})
    )
    assert findings, "the Scout must still report the unknown field"
    assert len(findings) == 1
    sample = findings[0].sample_masked
    assert not PRECISE.search(sample), f"the Scout would publish {sample!r}"
    assert findings[0].path == "persLocation"


def test_the_diagnostics_export_cannot_carry_the_pair_either() -> None:
    """The second surface, and the one a reporter attaches to a public issue.

    ``_GPS_KEYS`` in ``diagnostics`` is keyed on the field NAME, and
    ``persLocation`` is in neither set, so it fell through to the string branch
    — which masked e-mails and ``?latitude=`` URLs but not a bracketed pair.
    Both surfaces now share one rule; this test is what keeps the second one
    from being forgotten when the first is changed.
    """
    from custom_components.vag_connect.diagnostics import _scrub

    payload = {
        "raw_unmapped_fields": {
            "eu_data_act.persLocation": OBSERVED,
            "persLocation": OBSERVED,
            "latitude": 50.123456,
        }
    }

    # Default: privacy-by-default is removal, not rounding.
    default = _scrub(payload, gps_round=False)["raw_unmapped_fields"]
    assert not PRECISE.search(json.dumps(default)), default
    assert default["latitude"] == "**REDACTED**"          # positive control
    assert default["persLocation"] == "[REDACTED, REDACTED]"
    assert default["eu_data_act.persLocation"] == "[REDACTED, REDACTED]"

    # Opt-in: one decimal, as the neighbouring query-string rule does.
    opted = _scrub(payload, gps_round=True)["raw_unmapped_fields"]
    assert not PRECISE.search(json.dumps(opted)), opted
    assert opted["latitude"] == 50.1                      # positive control
    assert opted["persLocation"] == "[50.1, 4.7]"
