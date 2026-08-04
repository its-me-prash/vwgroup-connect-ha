# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""A charge level reported twice under one capture time no longer flips.

The portal export sometimes carries the same field more than once inside a
single snapshot, with different values. When that happens the flattener has
nothing left to separate them but their position in the array, which is not
evidence, and the sensor visibly flips between the two numbers on a parked car.

The parser now records every candidate instead of quietly picking one, and the
merge step, which is the only place that knows the previous poll, keeps the
candidate closest to the last known reading. A real change moves a reading
gradually from poll to poll, so it stays selected; the spurious twin sits far
away and loses. Where nothing was contested, nothing changes at all.

Grounded in a real ID.3 export published by an affected owner: three soc slots
(50, 71, 50), the last two sharing one capture time, with the car neither driven
nor charged and the app showing 71.
"""
from __future__ import annotations

from custom_components.vag_connect.cariad.auth._eu_data_act import _walk_fields
from custom_components.vag_connect.cariad.vehicle_cache import reconcile


def _log(entries: list[tuple[str, str]]) -> dict:
    return {"data": [{"dataFieldName": n, "value": v} for n, v in entries]}


class TestParserRecordsCandidates:
    def test_tie_under_one_capture_time_is_recorded(self) -> None:
        contested: dict[str, set[str]] = {}
        fields = _walk_fields(_log([
            ("car_captured_time", "2026-07-29T05:22:20Z"),
            ("battery_state_report.soc", "71"),
            ("battery_state_report.soc", "50"),
        ]), {}, {}, contested)
        assert contested["battery_state_report.soc"] == {"50", "71"}
        # The parser's own pick is deliberately unchanged.
        assert fields["battery_state_report.soc"] == "50"

    def test_distinct_capture_times_are_not_contested(self) -> None:
        """Genuinely newer wins outright, so there is nothing to resolve."""
        contested: dict[str, set[str]] = {}
        fields = _walk_fields(_log([
            ("car_captured_time", "2026-07-29T05:00:00Z"),
            ("battery_state_report.soc", "40"),
            ("car_captured_time", "2026-07-29T06:00:00Z"),
            ("battery_state_report.soc", "55"),
        ]), {}, {}, contested)
        assert "battery_state_report.soc" not in contested
        assert fields["battery_state_report.soc"] == "55"

    def test_envelope_keys_are_not_reported_as_contested(self) -> None:
        """Per-point UUIDs and message ids legitimately differ; they are not
        a contested vehicle reading."""
        contested: dict[str, set[str]] = {}
        _walk_fields(_log([
            ("car_captured_time", "2026-07-29T05:22:20Z"),
            ("message_id", "RPT_0"),
            ("message_id", "RbcErrorReport_0"),
        ]), {}, {}, contested)
        assert "message_id" not in contested


class TestResolverPrefersThePlausibleCandidate:
    def test_the_reported_case(self) -> None:
        """Last known 71, export offers 71 and 50, car untouched."""
        merged, notes = reconcile(
            {"battery_soc": 71},
            {"battery_soc": 50,
             "contested_fields": {"battery_state_report.soc": ["50", "71"]}},
        )
        assert merged["battery_soc"] == 71
        assert any("battery_soc" in n for n in notes)

    def test_it_follows_a_car_that_is_actually_charging(self) -> None:
        """Closest-to-last tracks a real change; it does not pin the old value."""
        merged, _ = reconcile(
            {"battery_soc": 60},
            {"battery_soc": 50,
             "contested_fields": {"battery_state_report.soc": ["50", "65"]}},
        )
        assert merged["battery_soc"] == 65

    def test_an_uncontested_reading_is_never_touched(self) -> None:
        """The guard rail: a big genuine drop while driving must pass through."""
        merged, notes = reconcile({"battery_soc": 80}, {"battery_soc": 35})
        assert merged["battery_soc"] == 35
        assert notes == []

    def test_no_previous_value_means_no_opinion(self) -> None:
        """First poll after setup has nothing to compare against."""
        merged, _ = reconcile(
            {"vin": "X"},
            {"battery_soc": 50,
             "contested_fields": {"battery_state_report.soc": ["50", "71"]}},
        )
        assert merged["battery_soc"] == 50

    def test_enum_conflicts_are_left_alone(self) -> None:
        """Closest-to-last is meaningless for a mode, and preferring the
        previous one would freeze the state."""
        merged, _ = reconcile(
            {"charging_state": "CHARGING"},
            {"charging_state": "OFF",
             "contested_fields": {
                 "charging_state_report.charge_mode": ["A", "B"]}},
        )
        assert merged["charging_state"] == "OFF"

    def test_target_soc_is_covered_too(self) -> None:
        """Same mechanism was reported for the charge target flipping."""
        merged, _ = reconcile(
            {"target_soc": 70},
            {"target_soc": 90,
             "contested_fields": {"settings.target_soc": ["90", "70"]}},
        )
        assert merged["target_soc"] == 70


# ── Scout #1030: the climate-timer queue under the automation container ──────

class TestClimatisationTimerAlias:
    """Audi firmware ships the queued climate-timer changes under
    ``automation.climatisationTimer.requests`` (singular Timer) instead of
    ``climatisationTimers.climatisationTimersStatus.requests``. Same queue,
    same meaning, so it fills the same sensor rather than being a new field.
    The duality already exists for charging profiles.
    """

    @staticmethod
    def _parse(raw: dict):
        from custom_components.vag_connect.cariad.api.vw_eu import VWEUClient

        c = VWEUClient.__new__(VWEUClient)
        return c._parse_status("VIN123", raw, {})

    def test_known_spelling_still_counts(self) -> None:
        d = self._parse({"climatisationTimers": {
            "climatisationTimersStatus": {"requests": [{"id": 1}, {"id": 2}]}}})
        assert d.climatisation_timers_pending == 2

    def test_automation_spelling_counts_too(self) -> None:
        d = self._parse({"automation": {
            "climatisationTimer": {"requests": [{"id": 1}]}}})
        assert d.climatisation_timers_pending == 1

    def test_neither_present_leaves_it_unset(self) -> None:
        d = self._parse({"charging": {}})
        assert d.climatisation_timers_pending is None
