# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#465 (Arno-MA-73) — the EU Data Act portal shipped SoC under two DISAGREEING
aliases (a stale 57 and a fresh 81). ``first()`` picked by fixed alias order, not
by capture time, so the reported Battery Level oscillated 57<->81 while the real
SoC (available/capacity = 80.2%) was steady. ``first_freshest()`` now resolves
the SoC aliases by capture time; ties keep the canonical list order, so the
common case (bare/dotted spellings of one node, same timestamp) is unchanged.
"""
from __future__ import annotations

from custom_components.vag_connect.cariad.auth._eu_data_act import (
    map_dataset_to_vehicle_data,
)
from custom_components.vag_connect.cariad.models import VehicleData


def _soc(fields: dict[str, str], field_ts: dict[str, float] | None = None) -> int | None:
    return map_dataset_to_vehicle_data(
        fields, VehicleData(vin="X"), field_ts=field_ts
    ).battery_soc


class TestSocFreshness:
    def test_fresher_alias_wins_over_canonical_order(self) -> None:
        # canonical-first alias is STALE (57); a later alias is FRESH (81)
        fields = {"battery_state_report.soc": "57", "soc": "81"}
        ts = {"battery_state_report.soc": 100.0, "soc": 200.0}
        assert _soc(fields, ts) == 81

    def test_fresher_wins_even_when_later_in_the_list(self) -> None:
        fields = {"soc": "57", "stateOfChargeInPercent": "81"}
        ts = {"soc": 100.0, "stateOfChargeInPercent": 200.0}
        assert _soc(fields, ts) == 81

    def test_stale_later_alias_does_not_beat_fresh_canonical(self) -> None:
        fields = {"battery_state_report.soc": "81", "soc": "57"}
        ts = {"battery_state_report.soc": 200.0, "soc": 100.0}
        assert _soc(fields, ts) == 81

    def test_equal_timestamps_keep_canonical_order(self) -> None:
        # the common case: same capture time -> first-listed (canonical) wins,
        # identical to the old behaviour.
        fields = {"battery_state_report.soc": "81", "soc": "57"}
        ts = {"battery_state_report.soc": 100.0, "soc": 100.0}
        assert _soc(fields, ts) == 81

    def test_no_timestamps_falls_back_to_list_order(self) -> None:
        # field_ts unavailable -> old first() behaviour (first present wins).
        fields = {"battery_state_report.soc": "57", "soc": "81"}
        assert _soc(fields, None) == 57

    def test_candidate_with_a_timestamp_beats_one_without(self) -> None:
        fields = {"battery_state_report.soc": "57", "soc": "81"}
        ts = {"soc": 200.0}  # only the non-canonical alias carries a ts
        assert _soc(fields, ts) == 81

    def test_single_alias_unaffected(self) -> None:
        assert _soc({"soc": "80"}, {"soc": 100.0}) == 80
