# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Companion parsing hardening, mined from ckomma/charge-app-connector-vw
(Apache-2.0) issues #7 (implausible/grouped numbers) and #15 (charge power).
"""
from __future__ import annotations

from custom_components.vag_connect.companion.presets import (
    PRESETS,
    _first_int,
    coerce,
)
from custom_components.vag_connect.companion.screen import parse_ui_dump, read_fields


class TestGroupedThousands:
    """ckomma #7 — an odometer like '27 886 km' must not truncate to 27."""

    def test_space_grouped(self) -> None:
        assert _first_int("27 886 km") == 27886

    def test_dot_grouped(self) -> None:
        assert _first_int("27.886") == 27886

    def test_multi_group(self) -> None:
        assert _first_int("1 234 567 km") == 1234567

    def test_plain_number_unchanged(self) -> None:
        assert _first_int("312 km") == 312
        assert _first_int("noch 45 min") == 45

    def test_decimal_is_not_treated_as_grouped(self) -> None:
        # "12,5" (comma) and "12.5" (single non-3-digit tail) must not collapse
        # to 125 — the tail is not a 3-digit group.
        assert _first_int("12,5") == 12
        assert _first_int("12.5") == 12

    def test_coerce_int_km_grouped(self) -> None:
        assert coerce("int_km", "27 886 km") == 27886

    def test_kw_parser_keeps_decimals(self) -> None:
        # the kw path is separate and must still read a decimal power.
        assert coerce("kw", "12,5 kW") == 12.5
        assert coerce("kw", "7.4 kW") == 7.4


def _dump(nodes: str) -> str:
    return f'<?xml version="1.0"?><hierarchy>{nodes}</hierarchy>'


class TestOdometerAndChargePowerWiring:
    def test_vw_reads_odometer_grouped(self) -> None:
        screen = _dump(
            '<node content-desc="Kilometerstand 27 886 km" text="" '
            'class="TextView" clickable="false" bounds="[0,0][10,10]" />'
        )
        fields = read_fields(parse_ui_dump(screen), PRESETS["volkswagen"])
        assert fields["odometer_km"] == 27886

    def test_vw_reads_charge_power(self) -> None:
        screen = _dump(
            '<node content-desc="Ladeleistung 7,4 kW" text="" '
            'class="TextView" clickable="false" bounds="[0,0][10,10]" />'
        )
        fields = read_fields(parse_ui_dump(screen), PRESETS["volkswagen"])
        assert fields["charging_power_kw"] == 7.4

    def test_every_preset_now_reads_odometer(self) -> None:
        for brand, p in PRESETS.items():
            targets = {f.target for f in p.fields}
            assert "odometer_km" in targets, brand
