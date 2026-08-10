# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""A reading of zero is an answer, not a missing value.

The brand parsers read the same quantity under several spellings and picked
whichever answered with ``a or b or c``. That chain skips a legitimate zero,
and zero is the value that matters most: a service interval of 0 km means DUE
NOW, an empty tank reports 0 km of range, a flat battery reports 0 %, and 0
degrees is an ordinary winter morning. Each of those fell through to the next
spelling, found nothing, and arrived as "no reading at all", so with
hide-empty-entities on by default the sensor disappeared at the exact moment it
was worth looking at.

The worst of it was not a missing number but a missing car. ``has_combustion``
and ``has_battery`` were derived from the collapsed result, so a tank reading
0 km made the car "not a combustion car" and took every combustion-conditioned
entity with it.

This was diagnosed once before: ``cariad/_normalize.derive_range_headline``
was written to fix exactly this and its docstring says so, but it was never
called from anywhere. Hence the second half of this file, which pins the
absence of the pattern rather than trusting that nobody reintroduces it.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from custom_components.vag_connect.cariad._util import first_not_none

_API = Path(__file__).resolve().parents[1] / "custom_components" / "vag_connect" / "cariad" / "api"


class TestTheCoalescer:
    def test_zero_wins_over_a_later_spelling(self) -> None:
        assert first_not_none(None, 0, 42) == 0

    def test_zero_point_zero_wins_too(self) -> None:
        assert first_not_none(None, 0.0, 9.9) == 0.0

    def test_none_falls_through(self) -> None:
        assert first_not_none(None, None, 7) == 7

    def test_all_absent_is_none(self) -> None:
        assert first_not_none(None, None) is None

    def test_nothing_at_all_is_none(self) -> None:
        assert first_not_none() is None

    def test_false_and_empty_string_are_answers(self) -> None:
        """Not every caller is numeric; an enum of "" or a flag of False is
        still a thing the car said."""
        assert first_not_none(None, False, True) is False
        assert first_not_none(None, "", "x") == ""

    def test_the_first_answer_wins_not_the_truthiest(self) -> None:
        assert first_not_none(0, 5) == 0


@pytest.mark.parametrize(("brand", "assignment"), [
    # The fields their project got bitten on, on our side.
    ("seat_cupra", "service_km"),
    ("seat_cupra", "oil_service_km"),
    ("seat_cupra", "service_due_at"),
    ("seat_cupra", "oil_service_at"),
    # The capability flags: these delete entities, not just values.
    ("seat_cupra", "combustion"),
    ("seat_cupra", "electric"),
    ("seat_cupra", "battery_soc"),
    ("skoda", "electric"),
    ("skoda", "combustion"),
    # Ranges and charge readings, where zero is the everyday case.
    ("seat_cupra", "range_km"),
    ("seat_cupra", "charging_power_kw"),
    ("seat_cupra", "charging_rate_kmh"),
    ("seat_cupra", "adblue_range_km"),
    ("vw_na", "odometer_km"),
    ("vw_na", "charging_power_kw"),
    # VW EU brake service, the same family as their "remaining maintenance
    # fields" follow-up fix.
    ("vw_eu", "brake_fluid_raw"),
    ("vw_eu", "front_pads_raw"),
    ("vw_eu", "rear_pads_raw"),
])
def test_no_truthy_chain_behind_a_zero_valid_field(brand: str, assignment: str) -> None:
    """The assignment must not be built from ``or``, in any of these files.

    A source-level check on purpose: the parse happens inline inside an async
    method that talks HTTP, so there is no seam to drive it through, and the
    fault is a syntactic one that a reviewer reintroduces by habit. Pinning the
    shape catches that where a value-level test could not run at all.
    """
    src = (_API / f"{brand}.py").read_text(encoding="utf-8")
    name = re.escape(assignment)

    # Positive: the assignment exists and is built from the zero-safe helper.
    # Without this half the test would pass on a file where the assignment had
    # simply been deleted, or renamed, and would prove nothing at all.
    # v3.0.2 (#1122): an optional ``drop_odometer_sentinel(`` wrapper is tolerated
    # — it screens the uint32 sentinel AFTER first_not_none has picked the
    # zero-safe value, so the anti-truthy-or guarantee is unchanged (a real 0 km
    # still survives: drop_odometer_sentinel(0) == 0).
    assert re.search(
        rf"^\s*(?:d\.)?{name} = (?:drop_odometer_sentinel\()?first_not_none\(",
        src, re.MULTILINE,
    ), (
        f"{brand}.{assignment} is not assigned via first_not_none"
    )

    # Negative: no remaining parenthesised or-chain under that name, which is
    # the exact shape the fault would return in.
    pattern = re.compile(
        rf"^\s*(?:d\.)?{name} = \(\n(?P<body>(?:.*\n)*?)\s*\)$", re.MULTILINE,
    )
    for match in pattern.finditer(src):
        body = match.group("body")
        assert not re.search(r"^\s*or ", body, re.MULTILINE), (
            f"{brand}.{assignment} still falls through on a legitimate zero:\n{body}"
        )
