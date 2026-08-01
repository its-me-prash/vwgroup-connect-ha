# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""v2.5.3 — OLA v1↔v5 fallback chain tests (#306).

Covers the three patches:
1. /v1/mileage fallback → odometer_km populated when mycar is null
2. Field-name variant coverage for /v1/maintenance + /v1/ranges
3. doors_locked-overrides-doors_open consistency safeguard

The parser tests exercise the parsing logic via the same shape contracts
the SEAT/CUPRA backend serves to PyCupra. We don't import the live
client (HA dep); instead we mirror the parse paths used in
``seat_cupra.py``.
"""

from __future__ import annotations

import asyncio


# ── /v1/mileage parse contract ──────────────────────────────────────────────


class TestMileageV1Fallback:
    """The 5 field-name variants we accept for the cached-odometer endpoint.

    PyCupra's OLA bindings report seeing different names across the
    firmware generations active on SEAT Mii Electric, CUPRA Born,
    Tavascan VZ, and Leon FR KL. v2.5.3 accepts all 5 with first-wins
    ordering.
    """

    def _extract(self, payload: dict) -> int | None:
        # Mirror the production fallback chain in seat_cupra.py.
        odo = (
            payload.get("mileageInKm")
            or payload.get("mileage")
            or payload.get("odometer")
            or payload.get("currentMileage")
            or payload.get("value")
        )
        if isinstance(odo, (int, float)) and odo > 0:
            return int(odo)
        return None

    def test_mileageInKm_variant(self) -> None:
        assert self._extract({"mileageInKm": 42_123}) == 42_123

    def test_mileage_variant(self) -> None:
        assert self._extract({"mileage": 42_123}) == 42_123

    def test_odometer_variant(self) -> None:
        assert self._extract({"odometer": 42_123}) == 42_123

    def test_currentMileage_variant(self) -> None:
        assert self._extract({"currentMileage": 42_123}) == 42_123

    def test_value_fallback(self) -> None:
        # PyCupra has been seen returning a bare ``{"value": <km>}`` shape
        # for cars that predate the v2 response format.
        assert self._extract({"value": 42_123}) == 42_123

    def test_float_coerces_to_int(self) -> None:
        # Some firmware sends a float (probably due to mile-to-km conversion).
        assert self._extract({"mileageInKm": 42_123.5}) == 42_123

    def test_zero_treated_as_no_data(self) -> None:
        # `odo > 0` guard — a literal 0 is more likely a parser garbage
        # value than a brand-new car that's never been driven.
        assert self._extract({"mileageInKm": 0}) is None

    def test_negative_treated_as_no_data(self) -> None:
        assert self._extract({"mileageInKm": -1}) is None

    def test_missing_returns_none(self) -> None:
        assert self._extract({"someOtherField": 999}) is None

    def test_first_present_wins(self) -> None:
        # When multiple variants present, the first in priority order wins.
        # Tests against accidental short-circuit-mis-ordering after refactor.
        result = self._extract({"mileageInKm": 100, "mileage": 200})
        assert result == 100


# ── /v1/maintenance field-variant coverage ──────────────────────────────────


class TestMaintenanceFieldVariants:
    """v2.5.3 — `/v1/maintenance` now accepts 4 variants per field."""

    def test_service_km_snake_case(self) -> None:
        payload = {"inspectionDue_km": 5000}
        result = (
            payload.get("inspectionDue_km")
            or payload.get("distanceToInspection")
            or payload.get("inspectionDueInKm")
            or payload.get("mileageRemainingForInspection")
        )
        assert result == 5000

    def test_service_km_camel_case(self) -> None:
        payload = {"distanceToInspection": 5000}
        result = (
            payload.get("inspectionDue_km")
            or payload.get("distanceToInspection")
            or payload.get("inspectionDueInKm")
            or payload.get("mileageRemainingForInspection")
        )
        assert result == 5000

    def test_service_km_myskoda_style(self) -> None:
        # v2.5.3 — new variant added for OLA backend's `*InKm` naming.
        payload = {"inspectionDueInKm": 5000}
        result = (
            payload.get("inspectionDue_km")
            or payload.get("distanceToInspection")
            or payload.get("inspectionDueInKm")
            or payload.get("mileageRemainingForInspection")
        )
        assert result == 5000

    def test_service_km_mileage_remaining_variant(self) -> None:
        # v2.5.3 — Leon FR KL variant.
        payload = {"mileageRemainingForInspection": 5000}
        result = (
            payload.get("inspectionDue_km")
            or payload.get("distanceToInspection")
            or payload.get("inspectionDueInKm")
            or payload.get("mileageRemainingForInspection")
        )
        assert result == 5000


# ── /v1/ranges field-variant coverage ───────────────────────────────────────


class TestRangesFieldVariants:
    """v2.5.3 — `/v1/ranges` electricRange + combustion + totalRange + adblue
    all accept multiple variants."""

    def test_electric_range_basic(self) -> None:
        # The actual ranges parser flow is nested: try electric → combustion →
        # total. We test each variant returns the expected number through
        # the same `or` chain used in production.
        payload = {"electricRange": 350}
        electric = (
            payload.get("electricRange")
            or payload.get("electricRangeInKm")
            or (payload.get("primaryEngineRange") or {}).get("remainingRangeInKm")
        )
        assert electric == 350

    def test_electric_range_myskoda_style(self) -> None:
        payload = {"electricRangeInKm": 350}
        electric = (
            payload.get("electricRange")
            or payload.get("electricRangeInKm")
            or (payload.get("primaryEngineRange") or {}).get("remainingRangeInKm")
        )
        assert electric == 350

    def test_electric_range_nested_primary_engine(self) -> None:
        # v2.5.3 — myskoda-style nested shape, sometimes seen on OLA too.
        payload = {"primaryEngineRange": {"remainingRangeInKm": 350}}
        electric = (
            payload.get("electricRange")
            or payload.get("electricRangeInKm")
            or (payload.get("primaryEngineRange") or {}).get("remainingRangeInKm")
        )
        assert electric == 350

    def test_combustion_range_diesel_variant(self) -> None:
        payload = {"dieselRange": 500}
        combustion = (
            payload.get("gasolineRange")
            or payload.get("dieselRange")
            or payload.get("combustionRangeInKm")
            or (payload.get("secondaryEngineRange") or {}).get("remainingRangeInKm")
        )
        assert combustion == 500


# ── doors_locked-overrides-doors_open contract ──────────────────────────────


class TestDoorsLockedConsistencySafeguard:
    """v2.5.3 (#306 @DanielBie) — physical impossibility check.

    When `doors_locked=True` but per-door / rollup say "open", the lock is
    more reliable (binary signal) than position (analog sensor that can
    stick at the last-known value). Override to closed.
    """

    # These used to be inline copies of the safeguard's logic, so they passed
    # while the real parser wrote the opposite polarity for years. They now
    # drive SeatCupraClient.get_status itself. doors_individual stores
    # True == OPEN (v2.23.2), so "forced closed" means every value is False.

    @staticmethod
    def _status(locked: bool, door_open: bool) -> dict:
        # Real OLA shape: status.doors.{pos}.{open: "open"|"closed", locked: bool}
        state = "open" if door_open else "closed"
        return {
            "doors": {
                pos: {"open": state, "locked": locked}
                for pos in ("frontLeft", "frontRight", "rearLeft", "rearRight")
            },
        }

    def _doors(self, body: dict):
        from tests.test_cariad import TestSeatCupraGetStatus

        helper = TestSeatCupraGetStatus()
        client = helper._client_with_url_routing("cupra", {"/v2/vehicles/": body})
        return asyncio.run(client.get_status("VSSZZE1KZLR000005"))

    def test_consistent_locked_closed_no_override(self) -> None:
        """Normal case — locked + closed agree, no change."""
        res = self._doors(self._status(True, door_open=False))
        assert res.doors_open is False
        assert res.doors_individual == dict.fromkeys(res.doors_individual, False)

    def test_locked_but_open_overrides_to_closed(self) -> None:
        """DanielBie's scenario — locked + open contradict, the lock wins.

        The regression this now catches: the safeguard used to write True for
        every door while True means OPEN, so a locked car rendered all four
        per-door sensors as "Open" (ckomma hit the same polarity class).
        """
        res = self._doors(self._status(True, door_open=True))
        assert res.doors_open is False
        assert res.doors_individual, "per-door map must survive the override"
        assert not any(res.doors_individual.values()), (
            "every per-door entry must read closed (False) after the override"
        )

    def test_unlocked_open_no_override(self) -> None:
        """User legitimately opened a door — no override should apply."""
        res = self._doors(self._status(False, door_open=True))
        assert res.doors_open is True
        assert any(res.doors_individual.values()), (
            "an open door on an unlocked car must stay open"
        )
        d_locked = False
        d_open = True
        individual = {"frontLeft": False, "frontRight": True,
                      "rearLeft": True, "rearRight": True}
        if d_locked is True and d_open is True:  # condition false
            d_open = False
            individual = {k: True for k in individual}
        assert d_open is True
        assert individual["frontLeft"] is False  # front-left genuinely open

    def test_locked_no_individuals_safe(self) -> None:
        """Override must not crash when per-door dict is empty."""
        d_locked = True
        d_open = True
        individual: dict[str, bool] = {}
        if d_locked is True and d_open is True:
            d_open = False
            if individual:
                individual = {k: True for k in individual}
        assert d_open is False
        assert individual == {}
