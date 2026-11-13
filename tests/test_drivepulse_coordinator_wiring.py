# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Held push source (a linked DrivePulse device): coordinator wiring.

The merge and the cache each have their own tests for this source class. These
pin what only the coordinator decides:

* the stale-data verdict ignores a held reading in all three places it looks
  (changed values, the per-field stamps, the live-contributor proxy);
* the supplier is offered only while something fresh is held for THAT car, and
  it is handed the drivetrain flags already on record;
* a held reading alone never revives a poll that brought no data;
* the paths that show the last snapshot again drop a held value once nothing
  fresh backs it, and every such path does so (walked from the source, so a
  path added later cannot be forgotten).
"""
from __future__ import annotations

import asyncio
import inspect
import re
import threading
from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.vag_connect import coordinator as coordinator_module
from custom_components.vag_connect.cariad.models import VehicleData
from custom_components.vag_connect.const import (
    CONF_DRIVEPULSE_LINKS,
    DRIVEPULSE_HOLD_S,
)
from custom_components.vag_connect.coordinator import (
    VagConnectCoordinator,
    _capture_age_s,
    _gap_fill_from_export,
    _has_live_contributor,
    _release_held,
    _values_moved,
)

VIN = "WVWZZZTESTFAKE001"
OTHER_VIN = "WVWZZZTESTFAKE002"


def _ago(minutes: float) -> str:
    return (datetime.now(tz=timezone.utc) - timedelta(minutes=minutes)).isoformat()


def _held_vd(vin: str, **values: Any) -> VehicleData:
    """A held reading as the mapper builds it: values plus their capture stamp."""
    vd = VehicleData(vin=vin)
    stamp = _ago(2)
    for name, value in values.items():
        setattr(vd, name, value)
        vd.field_captured_ts[name] = stamp
    return vd


class _Hold:
    """Stand-in for the hold: fresh for the VINs it was given, silent otherwise."""

    def __init__(self, fresh: dict[str, VehicleData]) -> None:
        self._fresh = fresh
        self.calls: list[tuple[str, bool, bool]] = []

    def has_fresh(self, vin: str) -> bool:
        return vin in self._fresh

    def vehicle_data(
        self, vin: str, *, has_battery: bool, has_combustion: bool
    ) -> VehicleData | None:
        self.calls.append((vin, has_battery, has_combustion))
        return self._fresh.get(vin)


def _portal_client(readers: Any = None) -> Any:
    """A client whose primary channel is the EU Data Act portal (a batch)."""
    client = MagicMock()
    client._eu_portal = object()
    client.supplementary_readers = readers
    return client


def _coord_stub(
    client: Any,
    *,
    hold: Any = None,
    vehicles: dict[str, dict[str, Any]] | None = None,
) -> Any:
    """Minimal coordinator stub with the methods under test bound to it."""
    stub = type("S", (), {})()
    stub._cariad_client = client
    stub.entry = MagicMock()
    stub.entry.data = {}
    stub.entry.options = {}
    stub.vehicles = vehicles or {}
    stub._vehicles_lock = threading.Lock()
    stub.hass = MagicMock()
    stub._drivepulse_hold = hold
    for name in (
        "_primary_channel_name",
        "_read_priority_channel",
        "_held_supplier",
        "_without_stale_held",
        "_drop_stale_held_in_place",
        "_merge_supplementary",
        "_revive_from_supplementary",
        "_merge_official_live",
        "_async_setup_drivepulse_hold",
        "_start_drivepulse_hold",
        "_async_stop_drivepulse_hold",
    ):
        setattr(stub, name, getattr(VagConnectCoordinator, name).__get__(stub))
    return stub


class TestStaleVerdictIgnoresAHeldReading:
    def test_a_changed_held_value_is_not_proof_of_a_live_feed(self) -> None:
        batch = {"fuel_level": 40, "field_sources": {"fuel_level": "eu_data_act"}}
        held = {"fuel_level": 35, "field_sources": {"fuel_level": "drivepulse"}}
        # the held source takes the field over, and later hands it back
        assert _values_moved(batch, held) is None
        assert _values_moved(held, batch) is None

    def test_control_a_changed_batch_value_still_counts(self) -> None:
        before = {"fuel_level": 40, "field_sources": {"fuel_level": "eu_data_act"}}
        after = {"fuel_level": 35, "field_sources": {"fuel_level": "eu_data_act"}}
        assert _values_moved(before, after) == "fuel_level"

    def test_a_held_token_is_not_a_live_contributor(self) -> None:
        assert not _has_live_contributor({"source_channel": "drivepulse"})
        assert not _has_live_contributor(
            {"source_channel": "drivepulse+eu_data_act"})

    def test_control_a_real_live_channel_beside_it_still_counts(self) -> None:
        assert _has_live_contributor(
            {"source_channel": "drivepulse+website_authproxy"})

    def test_a_held_stamp_does_not_date_a_frozen_feed(self) -> None:
        four_days = 4 * 24 * 60
        age = _capture_age_s({
            "source_channel": "drivepulse+eu_data_act",
            "last_seen_at": _ago(four_days),
            "field_sources": {
                "fuel_level": "drivepulse", "battery_soc": "eu_data_act",
            },
            "field_captured_ts": {
                "fuel_level": _ago(2), "battery_soc": _ago(four_days),
            },
        })
        assert age is not None and age > 3.9 * 86400, (
            f"the dongle's two-minute-old stamp dated a feed frozen for four "
            f"days; got {age}"
        )

    def test_control_the_same_stamp_owned_by_the_batch_does_date_it(self) -> None:
        four_days = 4 * 24 * 60
        age = _capture_age_s({
            "source_channel": "eu_data_act",
            "last_seen_at": _ago(four_days),
            "field_sources": {
                "fuel_level": "eu_data_act", "battery_soc": "eu_data_act",
            },
            "field_captured_ts": {
                "fuel_level": _ago(2), "battery_soc": _ago(four_days),
            },
        })
        assert age is not None and age < 600


class TestTheSupplierIsOfferedOnlyForAFreshLinkedCar:
    def test_a_fresh_reading_fills_the_gap_and_is_attributed(self) -> None:
        hold = _Hold({VIN: _held_vd(VIN, fuel_level=35)})
        stub = _coord_stub(
            _portal_client(), hold=hold,
            vehicles={VIN: {"has_combustion": True, "has_battery": False}},
        )
        primary = VehicleData(vin=VIN, odometer_km=100)
        out = asyncio.run(stub._merge_supplementary(VIN, primary))
        assert out.fuel_level == 35
        assert out.field_sources["fuel_level"] == "drivepulse"
        assert out.field_sources["odometer_km"] == "eu_data_act"
        assert out.source_channel == "drivepulse+eu_data_act"
        # the flags come from the snapshot on record, not from the reading
        assert hold.calls == [(VIN, False, True)]

    def test_a_client_with_its_own_readers_keeps_them_and_gains_the_held_one(
        self,
    ) -> None:
        async def _web() -> VehicleData:
            return VehicleData(vin=VIN, battery_soc=61)

        readers = MagicMock(return_value=[("website_authproxy", _web())])
        hold = _Hold({VIN: _held_vd(VIN, voltage_12v=12.4)})
        stub = _coord_stub(_portal_client(readers), hold=hold)
        out = asyncio.run(
            stub._merge_supplementary(VIN, VehicleData(vin=VIN, odometer_km=100))
        )
        assert out.battery_soc == 61
        assert out.voltage_12v == 12.4
        assert out.field_sources["voltage_12v"] == "drivepulse"

    def test_nothing_fresh_means_the_merge_it_always_was(self) -> None:
        hold = _Hold({})
        stub = _coord_stub(_portal_client(), hold=hold)
        primary = VehicleData(vin=VIN, odometer_km=100)
        out = asyncio.run(stub._merge_supplementary(VIN, primary))
        assert out.fuel_level is None
        assert out.source_channel == "eu_data_act"
        assert hold.calls == []

    def test_the_other_car_of_the_entry_gets_nothing(self) -> None:
        hold = _Hold({VIN: _held_vd(VIN, fuel_level=35)})
        stub = _coord_stub(
            _portal_client(), hold=hold,
            vehicles={OTHER_VIN: {"has_combustion": True}},
        )
        out = asyncio.run(
            stub._merge_supplementary(
                OTHER_VIN, VehicleData(vin=OTHER_VIN, odometer_km=7)
            )
        )
        assert out.fuel_level is None
        assert out.source_channel == "eu_data_act"
        assert hold.calls == []

    def test_no_hold_at_all_is_the_unlinked_entry(self) -> None:
        stub = _coord_stub(_portal_client(), hold=None)
        out = asyncio.run(
            stub._merge_supplementary(VIN, VehicleData(vin=VIN, odometer_km=100))
        )
        assert out.source_channel == "eu_data_act"

    def test_a_hold_that_raises_never_sinks_the_poll(self) -> None:
        class _Broken:
            def has_fresh(self, vin: str) -> bool:
                raise RuntimeError("store unreadable")

        stub = _coord_stub(_portal_client(), hold=_Broken())
        out = asyncio.run(
            stub._merge_supplementary(VIN, VehicleData(vin=VIN, odometer_km=100))
        )
        assert out.odometer_km == 100
        assert out.source_channel == "eu_data_act"


class TestAHeldReadingAloneNeverRevivesAPoll:
    def test_only_the_held_source_contributed(self) -> None:
        hold = _Hold({VIN: _held_vd(VIN, fuel_level=35)})
        stub = _coord_stub(
            _portal_client(), hold=hold, vehicles={VIN: {"has_combustion": True}},
        )
        empty = VehicleData(vin=VIN, no_data=True)
        assert asyncio.run(stub._revive_from_supplementary(VIN, empty)) is None

    def test_a_real_channel_revives_and_the_held_value_rides_along(self) -> None:
        async def _web() -> VehicleData:
            return VehicleData(vin=VIN, odometer_km=42)

        readers = MagicMock(return_value=[("website_authproxy", _web())])
        hold = _Hold({VIN: _held_vd(VIN, fuel_level=35)})
        stub = _coord_stub(
            _portal_client(readers), hold=hold,
            vehicles={VIN: {"has_combustion": True}},
        )
        empty = VehicleData(vin=VIN, no_data=True)
        out = asyncio.run(stub._revive_from_supplementary(VIN, empty))
        assert out is not None
        assert out.no_data is False
        assert out.odometer_km == 42
        assert out.fuel_level == 35
        assert out.field_sources["fuel_level"] == "drivepulse"


def _snapshot_with_held_fuel() -> dict[str, Any]:
    return {
        "fuel_level": 35,
        "odometer_km": 100,
        "source_channel": "drivepulse+eu_data_act",
        "field_sources": {"fuel_level": "drivepulse", "odometer_km": "eu_data_act"},
        "field_captured_ts": {"fuel_level": _ago(2)},
    }


class TestAShownAgainSnapshotDropsAStaleHeldValue:
    def test_kept_while_the_hold_still_has_a_fresh_reading(self) -> None:
        stub = _coord_stub(
            _portal_client(), hold=_Hold({VIN: _held_vd(VIN, fuel_level=35)})
        )
        snap = _snapshot_with_held_fuel()
        assert stub._without_stale_held(VIN, snap) is snap

    def test_dropped_once_nothing_fresh_backs_it(self) -> None:
        stub = _coord_stub(_portal_client(), hold=_Hold({}))
        snap = _snapshot_with_held_fuel()
        out = stub._without_stale_held(VIN, snap)
        assert out["fuel_level"] is None
        assert "fuel_level" not in out["field_sources"]
        assert "fuel_level" not in out["field_captured_ts"]
        assert out["source_channel"] == "eu_data_act"
        assert out["odometer_km"] == 100
        assert snap["fuel_level"] == 35, "the input must not be modified"

    def test_dropped_when_the_link_is_gone(self) -> None:
        stub = _coord_stub(_portal_client(), hold=None)
        out = stub._without_stale_held(VIN, _snapshot_with_held_fuel())
        assert out["fuel_level"] is None

    def test_a_snapshot_without_a_held_value_is_returned_as_it_is(self) -> None:
        stub = _coord_stub(_portal_client(), hold=None)
        snap = {
            "fuel_level": 40,
            "field_sources": {"fuel_level": "eu_data_act"},
            "source_channel": "eu_data_act",
        }
        assert stub._without_stale_held(VIN, snap) is snap


class TestEveryPathThatShowsTheLastSnapshotAgainIsCovered:
    """Walked from the source rather than listed by hand.

    The paths that publish the last snapshot again skip ``reconcile``, so a
    held value would outlive its hold time there. A path added later would be
    a silent hole; this fails instead.
    """

    def test_each_poll_failed_marker_is_preceded_by_the_drop(self) -> None:
        lines = inspect.getsource(coordinator_module).splitlines()
        marked = [
            i for i, line in enumerate(lines)
            if '["_poll_failed"] = True' in line
        ]
        assert len(marked) >= 4, "control: the marker must be findable"
        for i in marked:
            window = "\n".join(lines[max(0, i - 4): i])
            # The ASSIGNMENT form: a call whose result is thrown away would
            # satisfy a looser check and drop nothing.
            assert "= self._without_stale_held(" in window, (
                f"line {i + 1} shows the last snapshot again without dropping "
                "a stale held value first"
            )

    def test_the_path_without_a_marker_goes_through_the_drop_too(self) -> None:
        """The poll loop's last fallback republishes without setting the marker."""
        source = inspect.getsource(coordinator_module)
        guarded = re.compile(
            r"self\._redecide_stale\(\s*"
            r"self\._without_stale_held\(vin, self\.vehicles\.get\(vin, \{\}\)\)"
        )
        assert guarded.search(source), "control: the guarded form must be there"
        assert "self._redecide_stale(self.vehicles.get(vin" not in source

    def test_the_manual_refresh_drops_before_it_keeps_the_last_snapshot(
        self,
    ) -> None:
        source = inspect.getsource(coordinator_module)
        assert source.count("self._drop_stale_held_in_place(vin)") >= 2

    def test_the_restored_snapshot_is_stripped(self) -> None:
        source = inspect.getsource(VagConnectCoordinator.async_setup)
        assert "restored = dict(strip_held(vdata))" in source
        assert "restored = dict(vdata)" not in source

    def test_dropping_in_place_replaces_the_snapshot_on_record(self) -> None:
        snap = _snapshot_with_held_fuel()
        stub = _coord_stub(_portal_client(), hold=_Hold({}), vehicles={VIN: snap})
        stub._drop_stale_held_in_place(VIN)
        assert stub.vehicles[VIN]["fuel_level"] is None
        assert stub.vehicles[VIN]["odometer_km"] == 100

    def test_dropping_in_place_leaves_a_backed_value_alone(self) -> None:
        snap = _snapshot_with_held_fuel()
        hold = _Hold({VIN: _held_vd(VIN, fuel_level=35)})
        stub = _coord_stub(_portal_client(), hold=hold, vehicles={VIN: snap})
        stub._drop_stale_held_in_place(VIN)
        assert stub.vehicles[VIN] is snap


class TestAHeldReadingNeverReachesAThirdParty:
    """ABRP is the one place a reading leaves Home Assistant."""

    def test_a_held_state_of_charge_does_not_open_the_send_gate(self) -> None:
        from custom_components.vag_connect import abrp

        held = {"battery_soc": 62, "field_sources": {"battery_soc": "drivepulse"}}
        batch = {"battery_soc": 62, "field_sources": {"battery_soc": "eu_data_act"}}
        assert not abrp.has_sendable_soc(held)
        assert abrp.has_sendable_soc(batch)

    def test_the_coordinator_gate_asks_that_question(self) -> None:
        source = inspect.getsource(VagConnectCoordinator)
        assert "_abrp.has_sendable_soc(vehicle)" in source

    def test_a_change_in_a_held_value_is_not_a_change_for_abrp(self) -> None:
        from custom_components.vag_connect import abrp

        def _snap(soc: int, owner: str) -> dict[str, Any]:
            return {"battery_soc": soc, "field_sources": {"battery_soc": owner}}

        assert abrp.telemetry_fingerprint(
            _snap(62, "drivepulse")
        ) == abrp.telemetry_fingerprint(_snap(40, "drivepulse"))
        # control: the same change on a batch value is a change
        assert abrp.telemetry_fingerprint(
            _snap(62, "eu_data_act")
        ) != abrp.telemetry_fingerprint(_snap(40, "eu_data_act"))


class TestTheEventHandlerRunsInTheEventLoop:
    def test_the_bus_listener_is_a_callback(self) -> None:
        """Without ``@callback`` Home Assistant runs a listener in a worker
        thread, where the hold's dict and its delayed save must not be touched."""
        from homeassistant.core import is_callback

        from custom_components.vag_connect.held_push import DrivePulseHold

        assert is_callback(DrivePulseHold._handle)


class TestTheOfficialChannelTakesTheStampWithTheValue:
    def _run(self, owner: str) -> dict[str, Any]:
        async def _official(_vin: str) -> VehicleData:
            return VehicleData(vin=VIN, fuel_level=50)

        client = _portal_client()
        client.official_live_read = _official
        stub = _coord_stub(client)
        enriched: dict[str, Any] = {
            "fuel_level": 35,
            "field_sources": {"fuel_level": owner},
            "field_captured_ts": {"fuel_level": _ago(2)},
        }
        asyncio.run(stub._merge_official_live(VIN, enriched))
        return enriched

    def test_a_held_stamp_goes_when_the_official_value_replaces_it(self) -> None:
        enriched = self._run("drivepulse")
        assert enriched["fuel_level"] == 50
        assert enriched["field_sources"]["fuel_level"] == "skoda_official"
        assert "fuel_level" not in enriched["field_captured_ts"]

    def test_control_a_batch_stamp_is_left_as_it_was(self) -> None:
        enriched = self._run("eu_data_act")
        assert enriched["fuel_level"] == 50
        assert "fuel_level" in enriched["field_captured_ts"]


def test_the_hold_time_is_seven_days() -> None:
    """The documentation says seven days; the constant must say the same."""
    assert DRIVEPULSE_HOLD_S == 7 * 24 * 3600


class TestAHeldReadingNeverStandsInForAReadThatFailed:
    def test_a_car_seen_for_the_first_time_with_an_empty_primary(self) -> None:
        """No last snapshot to fall back to, so the caller would take the
        merged result as a successful poll."""
        hold = _Hold({VIN: _held_vd(VIN, range_km=300)})
        stub = _coord_stub(_portal_client(), hold=hold)
        empty = VehicleData(vin=VIN, no_data=True)
        out = asyncio.run(stub._merge_supplementary(VIN, empty))
        assert out is empty
        assert out.range_km is None
        assert out.no_data is True

    def test_control_the_same_reading_over_a_primary_with_data(self) -> None:
        hold = _Hold({VIN: _held_vd(VIN, range_km=300)})
        stub = _coord_stub(_portal_client(), hold=hold)
        out = asyncio.run(
            stub._merge_supplementary(VIN, VehicleData(vin=VIN, odometer_km=100))
        )
        assert out.range_km == 300


class TestLinkingDoesNotChangeHowACarIsClassified:
    """A car without a supplementary channel keeps the flags its client set.
    The held source going through the merge must not be what re-derives them."""

    def _primary(self) -> VehicleData:
        primary = VehicleData(vin=VIN, odometer_km=100, battery_soc=50)
        assert primary.has_battery is False, "control: the client left it unset"
        return primary

    def test_the_only_held_merge_keeps_the_primary_flags(self) -> None:
        hold = _Hold({VIN: _held_vd(VIN, voltage_12v=12.4)})
        stub = _coord_stub(_portal_client(), hold=hold)
        out = asyncio.run(stub._merge_supplementary(VIN, self._primary()))
        assert out.voltage_12v == 12.4, "control: the merge did run"
        assert out.has_battery is False
        assert out.is_electric is False

    def test_control_without_the_link_the_flags_are_the_same(self) -> None:
        stub = _coord_stub(_portal_client(), hold=None)
        out = asyncio.run(stub._merge_supplementary(VIN, self._primary()))
        assert out.has_battery is False

    def test_control_a_real_second_channel_still_re_derives(self) -> None:
        async def _web() -> VehicleData:
            return VehicleData(vin=VIN, range_km=200)

        readers = MagicMock(return_value=[("website_authproxy", _web())])
        hold = _Hold({VIN: _held_vd(VIN, voltage_12v=12.4)})
        stub = _coord_stub(_portal_client(readers), hold=hold)
        out = asyncio.run(stub._merge_supplementary(VIN, self._primary()))
        assert out.has_battery is True


class TestTheDiagnosticsLabelGoesWhenTheSourceIsNoLongerAsked:
    def test_a_stale_label_is_removed_and_the_others_stay(self) -> None:
        client = _portal_client()
        client.probe_outcomes = {
            "channel:drivepulse": "ok", "channel:website_authproxy": "ok",
        }
        stub = _coord_stub(client, hold=_Hold({}))
        asyncio.run(
            stub._merge_supplementary(VIN, VehicleData(vin=VIN, odometer_km=1))
        )
        assert client.probe_outcomes == {"channel:website_authproxy": "ok"}


class TestAHeldReaderNobodyAwaitedIsClosed:
    def test_closed_when_the_merge_fails(self, monkeypatch: Any) -> None:
        from custom_components.vag_connect.cariad import _channel_merge

        async def _boom(*_a: Any, **_k: Any) -> VehicleData:
            raise RuntimeError("merge broke")

        monkeypatch.setattr(_channel_merge, "gather_and_merge", _boom)
        closed: list[bool] = []

        class _Reader:
            def close(self) -> None:
                closed.append(True)

        stub = _coord_stub(_portal_client(), hold=None)
        stub._held_supplier = lambda _vin: ("drivepulse", _Reader())
        primary = VehicleData(vin=VIN, odometer_km=100)
        out = asyncio.run(stub._merge_supplementary(VIN, primary))
        assert out is primary, "the primary is kept when the merge fails"
        assert closed == [True]


class TestTheExportImportTreatsAHeldValueAsAGap:
    def _current(self) -> dict[str, Any]:
        return {
            "battery_soc": 70,
            "odometer_km": 100,
            "source_channel": "drivepulse+eu_data_act",
            "field_sources": {
                "battery_soc": "drivepulse", "odometer_km": "eu_data_act",
            },
            "field_captured_ts": {"battery_soc": _ago(2)},
        }

    def test_the_export_value_takes_the_field_with_its_own_provenance(self) -> None:
        current = self._current()
        stamp = _ago(600)
        hist = {
            "battery_soc": 31,
            "odometer_km": 90,
            "field_sources": {
                "battery_soc": "eu_data_act", "odometer_km": "eu_data_act",
            },
            "field_captured_ts": {"battery_soc": stamp},
        }
        assert _gap_fill_from_export(current, hist) == ["battery_soc"]
        assert current["battery_soc"] == 31
        assert current["field_sources"]["battery_soc"] == "eu_data_act"
        assert current["field_captured_ts"]["battery_soc"] == stamp
        assert current["source_channel"] == "eu_data_act"
        assert current["odometer_km"] == 100, "a live value is never clobbered"

    def test_a_held_value_the_export_has_nothing_for_is_left_alone(self) -> None:
        current = self._current()
        assert _gap_fill_from_export(current, {"odometer_km": 90}) == []
        assert current["battery_soc"] == 70
        assert current["field_sources"]["battery_soc"] == "drivepulse"

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "owner,promoted", [("drivepulse", False), ("eu_data_act", True)]
    )
    async def test_the_import_takes_no_drivetrain_evidence_from_a_held_value(
        self, owner: str, promoted: bool
    ) -> None:
        """The third caller of the drivetrain rule, in the import path."""
        hist = VehicleData(vin=VIN)
        hist.no_data = False
        hist.odometer_km = 12345

        class _Portal:
            async def get_vehicle_data(
                self, vin: str, request_type: str = "partial"
            ) -> VehicleData:
                return hist

        coord = VagConnectCoordinator.__new__(VagConnectCoordinator)
        coord._cariad_client = MagicMock()
        coord._cariad_client._eu_portal = _Portal()
        coord.vehicles = {
            VIN: {
                "fuel_level": 40,
                "has_combustion": False,
                "field_sources": {"fuel_level": owner},
            }
        }
        coord._vehicles_lock = threading.Lock()
        coord.async_set_updated_data = lambda _data: None  # type: ignore[method-assign]
        coord._save_vehicle_cache = lambda: None  # type: ignore[method-assign]
        assert await coord.async_import_historical_export(VIN) is True
        snap = coord.vehicles[VIN]
        assert snap["odometer_km"] == 12345, "control: the import ran"
        assert bool(snap.get("has_combustion")) is promoted


class TestReleasingAHeldField:
    def test_the_token_stays_while_another_field_is_still_held(self) -> None:
        data: dict[str, Any] = {
            "fuel_level": 50,
            "range_km": 300,
            "source_channel": "drivepulse+plugandplay",
            "field_sources": {"fuel_level": "drivepulse", "range_km": "drivepulse"},
            "field_captured_ts": {"fuel_level": "a", "range_km": "b"},
        }
        _release_held(data, ["fuel_level"])
        assert data["field_sources"] == {"range_km": "drivepulse"}
        assert data["field_captured_ts"] == {"range_km": "b"}
        assert data["source_channel"] == "drivepulse+plugandplay"
        assert data["fuel_level"] == 50, "the value is the caller's business"
        _release_held(data, ["range_km"])
        assert data["source_channel"] == "plugandplay"


class TestTheCarsOwnLitresOutrankAHeldPercentage:
    """The plug and play channel reports litres; with a configured tank size
    the percentage is derived from them on every poll."""

    def _coord(self, tank_cap: int) -> Any:
        coord = VagConnectCoordinator.__new__(VagConnectCoordinator)
        coord.hass = MagicMock()
        coord.hass.async_add_executor_job = AsyncMock(return_value=None)
        coord.entry = MagicMock()
        coord.entry.data = {
            "brand": "audi_acpp", "username": "t@t.com", "password": "x",
            "spin": "", "update_interval": 300, "fuel_tank_capacity": tank_cap,
        }
        coord._vehicles_lock = threading.Lock()
        coord._cariad_client = MagicMock()
        coord._cariad_client._image_data = {}
        coord.vehicle_static_info = {}
        coord._was_available = True
        coord.data = None
        return coord

    def _data(self, owner: str) -> dict[str, Any]:
        return {
            "vin": "V",
            "fuel_level_liters": 32.5,
            "fuel_level": 80,
            "source_channel": f"{owner}+plugandplay",
            "field_sources": {
                "fuel_level": owner, "fuel_level_liters": "plugandplay",
            },
            "field_captured_ts": {"fuel_level": _ago(2)},
        }

    def test_the_derived_value_replaces_the_held_one(self) -> None:
        out = asyncio.run(self._coord(65)._enrich(self._data("drivepulse")))
        assert out["fuel_level"] == 50
        assert "fuel_level" not in out["field_sources"]
        assert "fuel_level" not in out["field_captured_ts"]
        assert out["source_channel"] == "plugandplay"

    def test_control_a_real_percentage_is_still_not_overwritten(self) -> None:
        out = asyncio.run(self._coord(65)._enrich(self._data("website_authproxy")))
        assert out["fuel_level"] == 80

    def test_control_without_a_tank_size_the_held_value_stays(self) -> None:
        out = asyncio.run(self._coord(0)._enrich(self._data("drivepulse")))
        assert out["fuel_level"] == 80
        assert out["field_sources"]["fuel_level"] == "drivepulse"


class _FakeHold:
    """Records what the coordinator asks of the hold."""

    instances: list["_FakeHold"] = []

    def __init__(self, hass: Any, entry_id: str, links: Any, hold_s: float) -> None:
        self.args = (entry_id, dict(links), hold_s)
        self.events: list[str] = []
        _FakeHold.instances.append(self)

    async def async_load(self) -> None:
        self.events.append("load")

    def async_start(self) -> None:
        self.events.append("start")

    async def async_stop(self) -> None:
        self.events.append("stop")

    async def async_discard(self) -> None:
        self.events.append("discard")


class TestTheHoldsLifecycleInTheCoordinator:
    @pytest.fixture(autouse=True)
    def _fake_hold(self, monkeypatch: Any) -> None:
        from custom_components.vag_connect import held_push

        _FakeHold.instances.clear()
        monkeypatch.setattr(held_push, "DrivePulseHold", _FakeHold)

    def _stub(self, links: dict[str, str] | None) -> Any:
        stub = _coord_stub(_portal_client())
        stub.entry.data = {CONF_DRIVEPULSE_LINKS: links} if links else {}
        stub.entry.entry_id = "e1"
        return stub

    def test_setup_loads_and_only_start_listens(self) -> None:
        stub = self._stub({VIN: "dev-1"})
        asyncio.run(stub._async_setup_drivepulse_hold())
        hold = stub._drivepulse_hold
        assert hold.events == ["load"], "a setup that may still fail must not listen"
        assert hold.args == ("e1", {VIN: "dev-1"}, DRIVEPULSE_HOLD_S)
        stub._start_drivepulse_hold()
        assert hold.events == ["load", "start"]

    def test_an_entry_without_a_link_builds_nothing(self) -> None:
        stub = self._stub(None)
        asyncio.run(stub._async_setup_drivepulse_hold())
        assert stub._drivepulse_hold is None
        assert _FakeHold.instances == []
        stub._start_drivepulse_hold()  # nothing to start, and no error

    def test_stop_writes_what_is_waiting_while_the_link_exists(self) -> None:
        stub = self._stub({VIN: "dev-1"})
        asyncio.run(stub._async_setup_drivepulse_hold())
        hold = stub._drivepulse_hold
        asyncio.run(stub._async_stop_drivepulse_hold())
        assert hold.events == ["load", "stop"]
        assert stub._drivepulse_hold is None

    def test_stop_discards_once_the_link_is_gone(self) -> None:
        stub = self._stub({VIN: "dev-1"})
        asyncio.run(stub._async_setup_drivepulse_hold())
        hold = stub._drivepulse_hold
        stub.entry.data = {}  # the options flow removed the link, then reloads
        asyncio.run(stub._async_stop_drivepulse_hold())
        assert hold.events == ["load", "discard"]

    def test_shutdown_stops_the_hold_before_anything_else(self) -> None:
        source = inspect.getsource(VagConnectCoordinator.async_shutdown)
        assert source.index("_async_stop_drivepulse_hold()") < source.index(
            "async_stop_push_managers()"
        )

    def test_only_a_setup_that_succeeded_starts_listening(self) -> None:
        source = inspect.getsource(VagConnectCoordinator.async_setup)
        assert source.count("self._start_drivepulse_hold()") == 1
        assert re.search(
            r"if found > 0:\n(\s*#[^\n]*\n)*\s*self\._start_drivepulse_hold\(\)\n"
            r"\s*return found > 0",
            source,
        )


class TestTheAbrpChangedSensorAsksTheSendGatesQuestion:
    """Otherwise it announces an upload the send gate then refuses, on every
    run of the automation that watches it."""

    def _is_on(self, owner: str, last: Any = None) -> Any:
        from custom_components.vag_connect.binary_sensor import (
            VagAbrpDataChangedSensor,
        )

        entity = MagicMock()
        entity._vehicle = {"battery_soc": 62, "field_sources": {"battery_soc": owner}}
        entity._vin = VIN
        entity.coordinator.abrp_last_sent_fingerprint = (
            {} if last is None else {VIN: last}
        )
        return VagAbrpDataChangedSensor.is_on.fget(entity)

    def test_a_held_state_of_charge_keeps_it_off(self) -> None:
        assert self._is_on("drivepulse") is False
        assert self._is_on("drivepulse", last="an earlier upload") is False

    def test_control_a_batch_state_of_charge_turns_it_on(self) -> None:
        assert self._is_on("eu_data_act") is True
