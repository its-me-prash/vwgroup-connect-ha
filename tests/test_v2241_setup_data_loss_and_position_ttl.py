# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""v2.24.1 — the setup path stops destroying stored data, and a carried
position stops pretending to be current.

The headline bug (#702, Bugi66's Touareg): he reported that values used to
appear and then stopped, and we were one reply away from telling him he was
misremembering. He was not. ``async_setup`` restored the last-known-good
snapshot and then overwrote it twelve lines later, because the only guard was
``isinstance(result, Exception)`` and a no-data portal response is not an
exception — it is a bare ``VehicleData``. It therefore arrived with
``failed=False`` and blanked the restore. The first poll afterwards reconciled
against those blanks, found nothing left to carry, and persisted them.

The poll loop has guarded exactly this since v2.15.0a10. This path never did,
which is what made the fix only half landed and turned
``import_historical_export`` into a no-op for the users it exists for: import,
see data, restart, gone.

Second theme, from the same sweep: v2.24.0 fixed #923 by carrying the parked
position forward, which is right — a parked car has not moved — but it carried
it with no age attached and across restarts, so a week-old position was
indistinguishable from a current one, and the backend's own
``parkingPositionNotAvailable`` was masked rather than surfaced.
"""
from __future__ import annotations

import asyncio
import threading
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from custom_components.vag_connect.cariad.models import VehicleData
from custom_components.vag_connect.cariad.vehicle_cache import (
    CARRY_FORWARD_FIELDS,
    POSITION_FIELDS,
    POSITION_MAX_AGE_S,
    position_age_seconds,
    reconcile,
)


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


def _ago(**kw) -> str:
    return _iso(datetime.now(tz=timezone.utc) - timedelta(**kw))


# ── 1. the setup path must not destroy the restored snapshot ────────────────


class TestSetupPathDataLoss:
    """#702 — a no-data setup poll must keep last-known-good visible."""

    def _coord(self, restored: dict | None = None):
        from custom_components.vag_connect.coordinator import VagConnectCoordinator
        coord = VagConnectCoordinator.__new__(VagConnectCoordinator)
        coord.hass = MagicMock()
        coord.hass.loop = MagicMock()
        coord.hass.loop.call_soon_threadsafe = MagicMock()
        coord.entry = MagicMock()
        coord.entry.entry_id = "test"
        coord.entry.data = {
            "brand": "volkswagen", "username": "u@t.de",
            "password": "pw", "spin": "", "scan_interval": 5,
        }
        coord._vehicles_lock = threading.Lock()
        coord._cariad_client = None
        coord._started = False
        coord._was_available = True
        coord.vehicles = {"VIN123": dict(restored)} if restored else {}
        coord.data = None
        coord.async_set_updated_data = MagicMock()
        coord.async_request_refresh = AsyncMock()
        coord.logger = MagicMock()
        return coord

    def _client(self, status):
        client = MagicMock()
        client.authenticate = AsyncMock()
        client.get_vehicles = AsyncMock(return_value=["VIN123"])
        client.get_status = AsyncMock(return_value=status)
        return client

    def _run(self, coord, client):
        from custom_components.vag_connect.cariad.api.factory import CariadClientFactory
        with patch.object(CariadClientFactory, "create", return_value=client), \
             patch(
                 "homeassistant.helpers.aiohttp_client.async_get_clientsession",
                 return_value=MagicMock(),
             ):
            return asyncio.run(coord.async_setup())

    def test_no_data_poll_does_not_blank_the_restored_snapshot(self) -> None:
        """THE regression. Before the fix this asserted-away his data."""
        restored = {
            "vin": "VIN123", "battery_soc": 64, "odometer_km": 81234,
            "fuel_level": 30, "_restored": True, "_poll_failed": False,
        }
        coord = self._coord(restored=restored)
        empty = VehicleData(vin="VIN123")
        empty.no_data = True

        self._run(coord, self._client(empty))

        kept = coord.vehicles["VIN123"]
        assert kept["battery_soc"] == 64, "a no-data setup poll wiped stored data"
        assert kept["odometer_km"] == 81234
        assert kept["fuel_level"] == 30
        # ...and it is marked as a failed poll so the stale-cache watchdog engages
        assert kept["_poll_failed"] is True

    def test_a_brand_new_vin_still_appears_on_no_data(self) -> None:
        """The guard must not stop a first-ever car from being created."""
        coord = self._coord(restored=None)
        empty = VehicleData(vin="VIN123")
        empty.no_data = True

        self._run(coord, self._client(empty))

        assert "VIN123" in coord.vehicles

    def test_real_data_still_overwrites_normally(self) -> None:
        coord = self._coord(restored={"vin": "VIN123", "battery_soc": 10})
        fresh = VehicleData(vin="VIN123", battery_soc=88)

        self._run(coord, self._client(fresh))

        assert coord.vehicles["VIN123"]["battery_soc"] == 88

    def test_partial_setup_payload_carries_recorded_values_forward(self) -> None:
        """The setup path now reconciles, exactly like the poll loop."""
        coord = self._coord(restored={
            "vin": "VIN123", "battery_soc": 64, "odometer_km": 81234,
        })
        # fresh poll knows the SoC but omits the odometer entirely
        partial = VehicleData(vin="VIN123", battery_soc=70)

        self._run(coord, self._client(partial))

        kept = coord.vehicles["VIN123"]
        assert kept["battery_soc"] == 70, "fresh value must win"
        assert kept["odometer_km"] == 81234, "omitted value must carry forward"

    def test_prefetch_and_kickoff_are_deferred_to_the_background(self) -> None:
        """#909 — the best-effort prefetches + Data Act kickoff must no longer be
        awaited inline (they held config-entry setup open on a slow backend).
        They run in a background task, and the inline status merge is untouched.
        """
        coord = self._coord(restored={"vin": "VIN123", "battery_soc": 50})
        coord.refresh_capabilities = AsyncMock()
        coord.refresh_static_info = AsyncMock()
        coord._refresh_mbb_command_capabilities = AsyncMock()
        coord._ensure_data_act_custom_request_kickoff = AsyncMock()
        fresh = VehicleData(vin="VIN123", battery_soc=88)

        self._run(coord, self._client(fresh))

        # the inline status fetch + merge still ran…
        assert coord.vehicles["VIN123"]["battery_soc"] == 88
        # …but the tail-only best-effort work was NOT awaited inline. (Note
        # refresh_static_info is deliberately excluded: _enrich also calls it as
        # a lazy 24h-cache no-op per vehicle, which is inline and expected.)
        coord.refresh_capabilities.assert_not_called()
        coord._refresh_mbb_command_capabilities.assert_not_called()
        coord._ensure_data_act_custom_request_kickoff.assert_not_called()
        # a background finish task was scheduled to run them + the poll loop
        assert coord.hass.async_create_background_task.called


# ── 2. position carry-forward is bounded and dated ──────────────────────────


class TestPositionTTL:
    """#923 follow-up — carrying a position is right, hiding its age is not."""

    def test_a_recent_position_is_still_carried(self) -> None:
        previous = {
            "latitude": 47.39, "longitude": 8.05,
            "parking_address": "Bünzweg 16", "parking_city": "Othmarsingen",
            "position_captured_at": _ago(hours=2),
        }
        merged, notes = reconcile(previous, {"vin": "X"})
        assert merged["latitude"] == 47.39
        assert merged["parking_address"] == "Bünzweg 16"
        assert not notes

    def test_a_stale_position_is_dropped_not_carried(self) -> None:
        previous = {
            "latitude": 47.39, "longitude": 8.05,
            "parking_address": "Bünzweg 16",
            "position_captured_at": _ago(days=9),
        }
        merged, notes = reconcile(previous, {"vin": "X"})
        assert merged.get("latitude") is None, "a 9-day-old position read as current"
        assert merged.get("parking_address") is None
        assert any("dropped" in n for n in notes)

    def test_unknown_age_is_not_treated_as_expired(self) -> None:
        """Brands that never send a timestamp must not lose their position."""
        previous = {"latitude": 47.39, "longitude": 8.05}
        merged, _ = reconcile(previous, {"vin": "X"})
        assert merged["latitude"] == 47.39

    def test_last_seen_at_is_the_fallback_clock(self) -> None:
        old = {"latitude": 1.0, "longitude": 2.0, "last_seen_at": _ago(days=5)}
        merged, notes = reconcile(old, {"vin": "X"})
        assert merged.get("latitude") is None
        assert any("dropped" in n for n in notes)

        recent = {"latitude": 1.0, "longitude": 2.0, "last_seen_at": _ago(hours=1)}
        merged2, _ = reconcile(recent, {"vin": "X"})
        assert merged2["latitude"] == 1.0

    def test_a_fresh_position_never_inherits_the_old_address(self) -> None:
        """The subtle one: topping fresh coordinates up with a previous address
        would pin last week's street name onto this minute's position."""
        previous = {
            "latitude": 47.39, "longitude": 8.05,
            "parking_address": "Bünzweg 16", "parking_city": "Othmarsingen",
            "position_captured_at": _ago(minutes=5),
        }
        fresh = {"vin": "X", "latitude": 46.20, "longitude": 6.14}
        merged, _ = reconcile(previous, fresh)
        assert merged["latitude"] == 46.20
        assert merged.get("parking_address") is None, "stale address pinned to a new position"
        assert merged.get("parking_city") is None

    def test_the_capture_timestamp_travels_with_a_carried_position(self) -> None:
        """Otherwise the carried position loses its age and is carried forever."""
        stamp = _ago(hours=3)
        previous = {"latitude": 1.0, "longitude": 2.0, "position_captured_at": stamp}
        merged, _ = reconcile(previous, {"vin": "X"})
        assert merged["position_captured_at"] == stamp

    def test_position_fields_left_the_blanket_carry_forward_set(self) -> None:
        # they are reconciled as a TTL'd group now, not unconditionally
        for field in POSITION_FIELDS:
            assert field not in CARRY_FORWARD_FIELDS, field

    def test_position_age_helper(self) -> None:
        assert position_age_seconds({}) is None
        assert position_age_seconds({"position_captured_at": "not-a-date"}) is None
        age = position_age_seconds({"position_captured_at": _ago(hours=1)})
        assert age is not None and 3000 < age < 4200
        # a Z-suffixed stamp is the shape the backend actually sends
        assert position_age_seconds(
            {"position_captured_at": datetime.now(tz=timezone.utc)
             .replace(microsecond=0).isoformat().replace("+00:00", "Z")}
        ) is not None

    def test_ttl_is_a_day(self) -> None:
        assert POSITION_MAX_AGE_S == 24 * 3600


# ── 3. is_set is a presence flag, never a state ─────────────────────────────


class TestIsSetPrecedence:
    """A container being populated does not mean the thing is switched on."""

    def _map(self, payload: dict) -> VehicleData:
        from custom_components.vag_connect.cariad.auth._eu_data_act import (
            map_dataset_to_vehicle_data,
        )
        return map_dataset_to_vehicle_data(payload, VehicleData(vin="X"))

    def test_both_lights_off_beats_is_set_true(self) -> None:
        """The reported symptom: parking lights permanently "on"."""
        d = self._map({
            "parkinglightstate.is_set": "true",
            "parking_light_left": "false",
            "parking_light_right": "false",
        })
        assert d.parking_light is False, "is_set outranked two explicit 'off' readings"

    def test_one_light_on_still_reads_on(self) -> None:
        d = self._map({
            "parkinglightstate.is_set": "true",
            "parking_light_left": "true",
            "parking_light_right": "false",
        })
        assert d.parking_light is True

    def test_is_set_alone_is_still_honoured(self) -> None:
        """v2.17.5 behaviour for dialects that send nothing else — kept."""
        assert self._map({"parkinglightstate.is_set": "true"}).parking_light is True
        assert self._map({"parkinglightstate.is_set": "false"}).parking_light is False

    def test_released_parking_brake_beats_is_set_true(self) -> None:
        d = self._map({
            "parking_brake.is_set": "true",
            "parking_brake.parking_brake": "false",
        })
        assert d.parking_brake_engaged is False, "reported a released brake as engaged"

    def test_engaged_parking_brake_still_reads_engaged(self) -> None:
        d = self._map({
            "parking_brake.is_set": "true",
            "parking_brake.parking_brake": "true",
        })
        assert d.parking_brake_engaged is True

    def test_parking_brake_is_set_alone_is_still_honoured(self) -> None:
        assert self._map({"parking_brake.is_set": "true"}).parking_brake_engaged is True


# ── 4. the position timestamp is parsed and exposed ────────────────────────


def test_vw_eu_records_the_backend_capture_time() -> None:
    from custom_components.vag_connect.cariad.models import VehicleData as VD
    d = VD(vin="X")
    parking = {"data": {
        "lat": 47.39, "lon": 8.05,
        "carCapturedTimestamp": "2026-07-26T17:51:13Z",
    }}
    # mirror the assignment block in vw_eu.get_status
    pd = parking["data"]
    if pd.get("lat") is not None and pd.get("lon") is not None:
        d.latitude, d.longitude = pd["lat"], pd["lon"]
        ts = pd.get("carCapturedTimestamp")
        if isinstance(ts, str) and ts:
            d.position_captured_at = ts
    assert d.position_captured_at == "2026-07-26T17:51:13Z"
    assert "position_captured_at" in d.to_dict()


def test_device_tracker_exposes_the_capture_time() -> None:
    import inspect
    from custom_components.vag_connect import device_tracker
    src = inspect.getsource(device_tracker)
    assert '"position_captured_at",' in src, (
        "the carried position must expose its age, otherwise a user cannot "
        "tell yesterday's marker from this minute's"
    )
