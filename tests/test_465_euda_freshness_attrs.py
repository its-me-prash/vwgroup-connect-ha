# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""v4.7.11 (#465/#529/#1218 parity ADOPT) — per-VALUE freshness on EU-DA sensors.

Portal readers expose per-value freshness (when THIS datum was actually captured,
and whether the source shipped disagreeing candidates). We adopt the shape: the
EU-DA mapper records the resolved source leaf's genuine capture time under the
TARGET VehicleData attribute (``field_captured_ts``) plus a note for a genuine
tie (``ambiguous_fields``); the channel merge carries both like ``field_sources``;
and an EU-DA-sourced sensor surfaces ``data_captured_at`` / ``freshness_source`` /
``ambiguous_reading`` — but never a per-poll-changing age or dataset filename.
"""
from __future__ import annotations

from unittest.mock import MagicMock

from custom_components.vag_connect.cariad._channel_merge import merge_channels
from custom_components.vag_connect.cariad.auth._eu_data_act import (
    _epoch_or_iso,
    _walk_fields,
    map_dataset_to_vehicle_data,
)
from custom_components.vag_connect.cariad.models import VehicleData


def _map(
    fields: dict[str, str],
    field_ts: dict[str, float] | None = None,
    contested: dict[str, set[str]] | None = None,
) -> VehicleData:
    return map_dataset_to_vehicle_data(
        fields, VehicleData(vin="X"), field_ts=field_ts, contested=contested
    )


class TestPerFieldCaptureTs:
    def test_ts_recorded_for_mapped_field(self) -> None:
        # a mapped field (battery_soc) records the chosen leaf's genuine ts as ISO
        d = _map({"battery_state_report.soc": "81"},
                 {"battery_state_report.soc": 1000.0})
        assert d.battery_soc == 81
        assert d.field_captured_ts["battery_soc"] == _epoch_or_iso("1000.0")

    def test_ts_follows_the_resolved_alias(self) -> None:
        # freshness resolution picks the fresher alias; the recorded ts is ITS ts,
        # not the stale one's — the ts always belongs to the surfaced value.
        d = _map(
            {"battery_state_report.soc": "57", "soc": "81"},
            {"battery_state_report.soc": 100.0, "soc": 200.0},
        )
        assert d.battery_soc == 81
        assert d.field_captured_ts["battery_soc"] == _epoch_or_iso("200.0")

    def test_no_ts_no_entry(self) -> None:
        # only genuine per-point timestamps are recorded; a field with no real ts
        # (dataset floor / unknown) gets no field_captured_ts entry.
        d = _map({"battery_state_report.soc": "81"}, None)
        assert d.battery_soc == 81
        assert "battery_soc" not in d.field_captured_ts

    def test_odometer_records_its_own_ts(self) -> None:
        d = _map({"mileage.value": "12345"}, {"mileage.value": 1700.0})
        assert d.odometer_km == 12345
        assert d.field_captured_ts["odometer_km"] == _epoch_or_iso("1700.0")


class TestAmbiguousFlag:
    def test_tie_sets_ambiguous_note(self) -> None:
        # two disagreeing candidates under one capture time — a genuine tie the
        # mode-resolver can't settle — flags the TARGET attribute with a note.
        d = _map(
            {"battery_state_report.soc": "81"},
            {"battery_state_report.soc": 1000.0},
            contested={"battery_state_report.soc": {"57", "81"}},
        )
        assert d.ambiguous_fields["battery_soc"] == (
            "2 candidates disagree: 57 vs 81"
        )

    def test_no_tie_no_flag(self) -> None:
        d = _map({"battery_state_report.soc": "81"},
                 {"battery_state_report.soc": 1000.0})
        assert "battery_soc" not in d.ambiguous_fields

    def test_end_to_end_tie_via_walk_fields(self) -> None:
        # reuse the real freshness-resolution logic: two soc points, same genuine
        # capture time, disagreeing values -> _walk_fields records the contest,
        # the mapper carries it onto the attribute.
        payload = {
            "data": [
                {"dataFieldName": "battery_state_report.soc", "value": "57",
                 "carCapturedTimestamp": 1000},
                {"dataFieldName": "battery_state_report.soc", "value": "81",
                 "carCapturedTimestamp": 1000},
            ]
        }
        field_ts: dict[str, float] = {}
        field_syn: dict[str, set[str]] = {}
        contested: dict[str, set[str]] = {}
        field_uuids: dict[str, set[str]] = {}
        fields = _walk_fields(payload, field_ts, field_syn, contested, field_uuids)
        d = map_dataset_to_vehicle_data(
            fields, VehicleData(vin="X"), field_ts, field_syn, contested, field_uuids
        )
        assert d.battery_soc == 81
        assert d.field_captured_ts["battery_soc"] == _epoch_or_iso("1000.0")
        assert "battery_soc" in d.ambiguous_fields
        assert "57" in d.ambiguous_fields["battery_soc"]
        assert "81" in d.ambiguous_fields["battery_soc"]


class TestMergeCarriesFreshness:
    def _eu(self) -> VehicleData:
        vd = VehicleData(vin="X")
        vd.battery_soc = 81
        vd.field_captured_ts = {"battery_soc": _epoch_or_iso("1000.0") or ""}
        vd.ambiguous_fields = {"battery_soc": "2 candidates disagree: 57 vs 81"}
        return vd

    def test_single_channel_merge_preserves_dicts(self) -> None:
        merged = merge_channels([("eu_data_act", self._eu())])
        assert merged.field_sources["battery_soc"] == "eu_data_act"
        assert merged.field_captured_ts["battery_soc"] == _epoch_or_iso("1000.0")
        assert merged.ambiguous_fields["battery_soc"] == (
            "2 candidates disagree: 57 vs 81"
        )

    def test_gapfill_from_eu_keeps_ts(self) -> None:
        # EU-DA fills a gap a live channel does not carry (odometer here is unset
        # on both, so battery_soc from EU-DA survives) -> its ts is carried.
        live = VehicleData(vin="X")
        live.fuel_level = 50  # a disjoint field so the live channel contributes
        merged = merge_channels([("mbb", live), ("eu_data_act", self._eu())])
        assert merged.battery_soc == 81
        assert merged.field_sources["battery_soc"] == "eu_data_act"
        assert merged.field_captured_ts["battery_soc"] == _epoch_or_iso("1000.0")

    def test_live_supersede_drops_stale_ts(self) -> None:
        # a live channel supersedes the EU-DA battery_soc (live telemetry rule) ->
        # the value AND its provenance move to the live channel, and the stale
        # EU-DA capture ts is dropped (its owner no longer holds the field).
        live = VehicleData(vin="X")
        live.battery_soc = 80
        merged = merge_channels([("eu_data_act", self._eu()), ("mbb", live)])
        assert merged.battery_soc == 80
        assert merged.field_sources["battery_soc"] == "mbb"
        assert "battery_soc" not in merged.field_captured_ts
        assert "battery_soc" not in merged.ambiguous_fields


class TestSensorFreshnessAttributes:
    def _sensor(self, vehicle: dict[str, object]) -> object:
        from custom_components.vag_connect.sensor import (
            VagConnectSensor,
            VagSensorDescription,
        )
        coord = MagicMock()
        coord.data = {"X": vehicle}
        coord.vehicles = coord.data
        coord.is_read_only = MagicMock(return_value=False)
        coord.last_update_success = True
        desc = VagSensorDescription(key="battery_level", data_key="battery_soc")
        return VagConnectSensor(coord, "X", desc)

    def test_point_freshness_on_eu_da_sensor(self) -> None:
        iso = _epoch_or_iso("1000.0")
        s = self._sensor({
            "vin": "X", "battery_soc": 81,
            "field_sources": {"battery_soc": "eu_data_act"},
            "field_captured_ts": {"battery_soc": iso},
        })
        attrs = s.extra_state_attributes or {}
        assert attrs["data_captured_at"] == iso
        assert attrs["freshness_source"] == "point"
        assert "ambiguous_reading" not in attrs

    def test_dataset_freshness_when_no_point_ts(self) -> None:
        s = self._sensor({
            "vin": "X", "battery_soc": 81,
            "field_sources": {"battery_soc": "eu_data_act"},
        })
        attrs = s.extra_state_attributes or {}
        assert attrs["freshness_source"] == "dataset"
        assert "data_captured_at" not in attrs

    def test_ambiguous_reading_flagged(self) -> None:
        s = self._sensor({
            "vin": "X", "battery_soc": 81,
            "field_sources": {"battery_soc": "eu_data_act"},
            "field_captured_ts": {"battery_soc": _epoch_or_iso("1000.0")},
            "ambiguous_fields": {"battery_soc": "2 candidates disagree: 57 vs 81"},
        })
        attrs = s.extra_state_attributes or {}
        assert attrs["ambiguous_reading"] is True

    def test_absent_for_non_eu_da_sensor(self) -> None:
        # a value from a live channel gets no freshness attributes at all, even
        # with a stamp beside it. vw.de, whose bodies are the car's last upload,
        # is the exception: see test_vwde_data_captured_at.py.
        s = self._sensor({
            "vin": "X", "battery_soc": 81,
            "field_sources": {"battery_soc": "mbb"},
            "field_captured_ts": {"battery_soc": _epoch_or_iso("1000.0")},
        })
        attrs = s.extra_state_attributes or {}
        assert "data_captured_at" not in attrs
        assert "freshness_source" not in attrs
        assert "ambiguous_reading" not in attrs
