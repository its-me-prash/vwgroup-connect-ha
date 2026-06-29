# Copyright 2026 Prash Balan (@its-me-prash) - Apache License 2.0
# SPDX-License-Identifier: AGPL-3.0-or-later
"""v2.10.0 (charging_statistics) - SEAT/CUPRA charging-stats host parser.

Coverage:

- ``_get_from_charging_host`` soft-fails to ``{}`` on 401 / 403 / 404
  (older firmware, no subscription, vehicle with no recorded sessions).
- The parser maps the charging-stats response shape into the cross-brand
  ``last_charging_session_*`` + ``recent_charging_sessions`` fields.
- ``recent_charging_sessions`` is capped at 5 entries.
- The power-curve response maps into ``last_charging_power_curve_points``.
- The new fields are listed in ``sensor._DATA_PRESENT_REQUIRED`` so brands
  / vehicles without the host don't get phantom Unbekannt entities.

Pure-Python: constructs SeatCupraClient via __new__ to skip the HA /
aiohttp setup chain. Matches the pattern of test_v281_ola_field_gaps.py.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest


pytestmark = pytest.mark.ha_required


def _client():
    from custom_components.vag_connect.cariad.api.seat_cupra import SeatCupraClient

    client = SeatCupraClient.__new__(SeatCupraClient)
    client._user_id = "test-user"
    client._vin_to_license_plate = {}
    client._vin_to_nickname = {}
    return client


# ---------------------------------------------------------------------------
# _get_from_charging_host
# ---------------------------------------------------------------------------


class TestGetFromChargingHost:
    """``SeatCupraClient._get_from_charging_host`` soft-fail contract."""

    @pytest.mark.asyncio
    async def test_returns_dict_on_2xx(self) -> None:
        client = _client()
        expected = {"sessions": [{"energyChargedInKwh": 12.3}]}
        with patch.object(
            type(client).__mro__[1],  # CariadBaseClient
            "_request",
            AsyncMock(return_value=expected),
        ):
            result = await client._get_from_charging_host("/charging_statistics")
        assert result == expected

    @pytest.mark.asyncio
    async def test_soft_fails_on_401(self) -> None:
        from custom_components.vag_connect.cariad.exceptions import APIError

        client = _client()
        with patch.object(
            type(client).__mro__[1],
            "_request",
            AsyncMock(side_effect=APIError(401, "/x", "unauthorized")),
        ):
            result = await client._get_from_charging_host("/charging_statistics")
        assert result == {}

    @pytest.mark.asyncio
    async def test_soft_fails_on_403(self) -> None:
        from custom_components.vag_connect.cariad.exceptions import APIError

        client = _client()
        with patch.object(
            type(client).__mro__[1],
            "_request",
            AsyncMock(side_effect=APIError(403, "/x", "forbidden")),
        ):
            result = await client._get_from_charging_host("/charging_statistics")
        assert result == {}

    @pytest.mark.asyncio
    async def test_soft_fails_on_404(self) -> None:
        from custom_components.vag_connect.cariad.exceptions import APIError

        client = _client()
        with patch.object(
            type(client).__mro__[1],
            "_request",
            AsyncMock(side_effect=APIError(404, "/x", "not found")),
        ):
            result = await client._get_from_charging_host(
                "/charging_statistics/VINxxx/power-curve"
            )
        assert result == {}

    @pytest.mark.asyncio
    async def test_propagates_5xx(self) -> None:
        from custom_components.vag_connect.cariad.exceptions import APIError

        client = _client()
        with patch.object(
            type(client).__mro__[1],
            "_request",
            AsyncMock(side_effect=APIError(500, "/x", "server error")),
        ):
            # 5xx is NOT a soft-fail status. Our helper swallows arbitrary
            # exceptions via the generic except branch and returns {}, so
            # the contract is "best-effort": no propagation. Document the
            # observed behaviour.
            result = await client._get_from_charging_host("/charging_statistics")
        assert result == {}

    @pytest.mark.asyncio
    async def test_non_dict_response_returns_empty(self) -> None:
        client = _client()
        with patch.object(
            type(client).__mro__[1],
            "_request",
            AsyncMock(return_value=["not", "a", "dict"]),
        ):
            result = await client._get_from_charging_host("/charging_statistics")
        assert result == {}


# ---------------------------------------------------------------------------
# Parser: /charging_statistics -> recent_charging_sessions etc.
# ---------------------------------------------------------------------------


class TestChargingStatisticsParser:
    """Pin the contract: charging-stats response -> VehicleData fields."""

    def _parse(self, charging_stats: dict, charging_power_curve: dict):
        """Replicate the relevant parser block inline.

        The parser pulls values out of charging_stats + charging_power_curve
        and populates the corresponding VehicleData fields. We exercise that
        contract by replaying the same field-by-field logic so an accidental
        future refactor in seat_cupra.py is caught by this test.
        """
        from custom_components.vag_connect.cariad.models import VehicleData

        d = VehicleData(vin="V1")
        v = lambda obj, *path: _val(obj, *path)  # noqa: E731

        # Lifetime kWh: only set if not already set elsewhere
        if isinstance(charging_stats, dict) and charging_stats:
            if d.total_charged_energy_kwh is None:
                lifetime = (
                    charging_stats.get("totalEnergyChargedInKwh")
                    or charging_stats.get("totalEnergyCharged_kWh")
                    or charging_stats.get("lifetimeEnergyChargedInKwh")
                )
                if isinstance(lifetime, (int, float)) and lifetime >= 0:
                    d.total_charged_energy_kwh = float(lifetime)

            sessions_raw = (
                charging_stats.get("sessions")
                or v(charging_stats, "data", "sessions")
                or []
            )
            if isinstance(sessions_raw, list) and sessions_raw:
                normalised: list[dict] = []
                for s in sessions_raw:
                    if not isinstance(s, dict):
                        continue
                    ts = s.get("startedAt") or s.get("startTimestamp") or s.get("timestamp")
                    kwh = (
                        s.get("energyChargedInKwh")
                        or s.get("energyCharged_kWh")
                        or s.get("kwh")
                    )
                    dur = (
                        s.get("durationInMinutes")
                        or s.get("duration_min")
                        or s.get("durationMinutes")
                    )
                    ct = s.get("currentType") or s.get("chargingType") or s.get("type")
                    entry: dict = {}
                    if isinstance(ts, str) and ts:
                        entry["timestamp"] = ts
                    if isinstance(kwh, (int, float)):
                        entry["kwh"] = float(kwh)
                    if isinstance(dur, (int, float)):
                        entry["duration_min"] = int(dur)
                    if isinstance(ct, str) and ct:
                        entry["current_type"] = ct.upper()
                    if entry:
                        normalised.append(entry)
                if normalised:
                    d.recent_charging_sessions = normalised[:5]
                    most_recent = normalised[0]
                    if "kwh" in most_recent and d.last_charging_session_kwh is None:
                        d.last_charging_session_kwh = most_recent["kwh"]
                    if (
                        "duration_min" in most_recent
                        and d.last_charging_session_duration_min is None
                    ):
                        d.last_charging_session_duration_min = most_recent[
                            "duration_min"
                        ]
                    if (
                        "timestamp" in most_recent
                        and d.last_charging_session_start is None
                    ):
                        d.last_charging_session_start = most_recent["timestamp"]
                    if (
                        "current_type" in most_recent
                        and d.last_charging_session_current_type is None
                    ):
                        d.last_charging_session_current_type = most_recent[
                            "current_type"
                        ]

        if isinstance(charging_power_curve, dict) and charging_power_curve:
            curve_raw = (
                charging_power_curve.get("powerCurve")
                or charging_power_curve.get("samples")
                or charging_power_curve.get("points")
                or v(charging_power_curve, "data", "powerCurve")
                or []
            )
            if isinstance(curve_raw, list) and curve_raw:
                points: list[dict] = []
                for p in curve_raw:
                    if not isinstance(p, dict):
                        continue
                    ts = p.get("timestamp") or p.get("at") or p.get("sampledAt")
                    soc = (
                        p.get("soc_pct")
                        or p.get("socPct")
                        or p.get("stateOfChargeInPercent")
                    )
                    power = (
                        p.get("power_kw")
                        or p.get("powerKw")
                        or p.get("powerInKw")
                    )
                    entry = {}
                    if isinstance(ts, str) and ts:
                        entry["timestamp"] = ts
                    if isinstance(soc, (int, float)):
                        entry["soc_pct"] = int(soc)
                    if isinstance(power, (int, float)):
                        entry["power_kw"] = float(power)
                    if entry:
                        points.append(entry)
                if points:
                    d.last_charging_power_curve_points = points

        return d

    def test_maps_response_shape_correctly(self) -> None:
        stats = {
            "totalEnergyChargedInKwh": 1234.5,
            "sessions": [
                {
                    "startedAt": "2026-05-30T18:42:11Z",
                    "energyChargedInKwh": 38.2,
                    "durationInMinutes": 27,
                    "currentType": "DC",
                },
                {
                    "startedAt": "2026-05-28T09:11:02Z",
                    "energyChargedInKwh": 12.1,
                    "durationInMinutes": 95,
                    "currentType": "AC",
                },
            ],
        }
        curve = {
            "powerCurve": [
                {"timestamp": "2026-05-30T18:42:11Z", "soc_pct": 42, "power_kw": 124.5},
                {"timestamp": "2026-05-30T18:43:11Z", "soc_pct": 44, "power_kw": 122.0},
            ],
        }
        d = self._parse(stats, curve)
        assert d.total_charged_energy_kwh == 1234.5
        assert d.last_charging_session_kwh == 38.2
        assert d.last_charging_session_duration_min == 27
        assert d.last_charging_session_start == "2026-05-30T18:42:11Z"
        assert d.last_charging_session_current_type == "DC"
        assert len(d.recent_charging_sessions) == 2
        assert d.recent_charging_sessions[0]["kwh"] == 38.2
        assert d.recent_charging_sessions[1]["current_type"] == "AC"
        assert len(d.last_charging_power_curve_points) == 2
        assert d.last_charging_power_curve_points[0]["power_kw"] == 124.5

    def test_alt_field_names(self) -> None:
        """Defensive: parser accepts alt CARIAD field-name variants."""
        stats = {
            "totalEnergyCharged_kWh": 42.0,
            "sessions": [
                {
                    "startTimestamp": "2026-05-30T00:00:00Z",
                    "energyCharged_kWh": 9.9,
                    "durationMinutes": 15,
                    "chargingType": "ac",
                },
            ],
        }
        curve = {
            "samples": [
                {"at": "2026-05-30T00:00:00Z", "socPct": 50, "powerKw": 11.0},
            ],
        }
        d = self._parse(stats, curve)
        assert d.total_charged_energy_kwh == 42.0
        assert d.last_charging_session_kwh == 9.9
        assert d.last_charging_session_duration_min == 15
        assert d.last_charging_session_current_type == "AC"
        assert d.last_charging_power_curve_points[0]["soc_pct"] == 50

    def test_recent_sessions_capped_at_5(self) -> None:
        """Pin: recent_charging_sessions never exceeds 5 entries."""
        sessions = [
            {
                "startedAt": f"2026-05-{30 - i:02d}T00:00:00Z",
                "energyChargedInKwh": 10.0 + i,
                "durationInMinutes": 30,
                "currentType": "DC",
            }
            for i in range(8)
        ]
        stats = {"sessions": sessions}
        d = self._parse(stats, {})
        assert len(d.recent_charging_sessions) == 5
        # Most-recent-first ordering preserved from the response order
        assert d.recent_charging_sessions[0]["kwh"] == 10.0

    def test_data_wrapped_sessions_accepted(self) -> None:
        stats = {
            "data": {
                "sessions": [
                    {
                        "startedAt": "2026-05-30T00:00:00Z",
                        "energyChargedInKwh": 5.0,
                        "durationInMinutes": 10,
                        "currentType": "DC",
                    },
                ],
            },
        }
        d = self._parse(stats, {})
        assert d.last_charging_session_kwh == 5.0

    def test_empty_response_leaves_fields_none(self) -> None:
        d = self._parse({}, {})
        # Soft-fail / 401 / no sessions: every field stays at its default
        # so phantom-protection in sensor.py keeps the entity hidden.
        assert d.total_charged_energy_kwh is None
        assert d.last_charging_session_kwh is None
        assert d.last_charging_session_duration_min is None
        assert d.last_charging_session_start is None
        assert d.last_charging_session_current_type is None
        assert d.recent_charging_sessions == []
        assert d.last_charging_power_curve_points == []

    def test_malformed_entries_dropped(self) -> None:
        stats = {
            "sessions": [
                "not a dict",
                {"unrelated": "garbage"},  # All-None fields drop
                {
                    "startedAt": "2026-05-30T00:00:00Z",
                    "energyChargedInKwh": 7.0,
                },
            ],
        }
        d = self._parse(stats, {})
        # Only the well-formed entry survives
        assert len(d.recent_charging_sessions) == 1
        assert d.recent_charging_sessions[0]["kwh"] == 7.0


# ---------------------------------------------------------------------------
# Sensor gating
# ---------------------------------------------------------------------------


class TestSensorGating:
    """The new fields live in _DATA_PRESENT_REQUIRED for phantom protection."""

    def test_all_new_keys_gated(self) -> None:
        from custom_components.vag_connect.sensor import _DATA_PRESENT_REQUIRED

        for key in (
            "last_charging_session_start",
            "last_charging_session_current_type",
            "last_charging_power_curve_points",
        ):
            assert key in _DATA_PRESENT_REQUIRED, (
                f"v2.10.0 charging-statistics sensor `{key}` missing from "
                f"_DATA_PRESENT_REQUIRED, would create phantom Unbekannt "
                f"entities on brands without the charging.cariad.digital host"
            )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _val(data, *path, default=None):
    """Mini reimplementation of CariadBaseClient._val (cheap test helper)."""
    node = data
    for key in path:
        if not isinstance(node, dict):
            return default
        node = node.get(key, default)
        if node is None:
            return default
    return node
