# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""b1/C1 — cross-channel data merge: union the per-channel snapshots for one
VIN (the Golf GTE case: fuel from one channel, SoC from another, odometer from
a third) into a single VehicleData with provenance."""
from __future__ import annotations

import asyncio

import pytest

from custom_components.vag_connect.cariad._channel_merge import (
    gather_and_merge,
    merge_channels,
)
from custom_components.vag_connect.cariad.models import VehicleData


async def _ok(data: VehicleData) -> VehicleData:
    return data


async def _fail() -> VehicleData:
    raise RuntimeError("supplementary channel down")


async def _none() -> VehicleData | None:
    return None


class TestSourceChannelSensor:
    """C1 provenance sensor reads VehicleData.source_channel."""

    def _sensor(self, source_channel: str | None) -> object:
        from unittest.mock import MagicMock

        from custom_components.vag_connect.sensor import (
            VagConnectSensor,
            VagSensorDescription,
        )
        coord = MagicMock()
        coord.data = {"X": {"vin": "X", "source_channel": source_channel}}
        coord.vehicles = coord.data
        coord.is_read_only = MagicMock(return_value=False)
        coord.last_update_success = True
        desc = VagSensorDescription(
            key="data_source_channel", data_key="source_channel"
        )
        return VagConnectSensor(coord, "X", desc)

    def test_value_passthrough(self) -> None:
        assert self._sensor("eu_data_act+mbb").native_value == "eu_data_act+mbb"

    def test_none_value(self) -> None:
        assert self._sensor(None).native_value is None


class TestChannelMerge:
    def test_complementary_fields_union(self) -> None:
        a = VehicleData(vin="X", fuel_level=40)
        b = VehicleData(vin="X", battery_soc=80)
        merged = merge_channels([("mbb", a), ("eu_data_act", b)])
        assert merged.fuel_level == 40
        assert merged.battery_soc == 80
        assert merged.source_channel == "eu_data_act+mbb"  # sorted join

    def test_overlap_higher_priority_wins(self) -> None:
        a = VehicleData(vin="X", odometer_km=100, fuel_level=40)
        b = VehicleData(vin="X", odometer_km=200, battery_soc=80)
        merged = merge_channels([("brand_native", a), ("eu_data_act", b)])
        assert merged.odometer_km == 100   # first source wins on overlap
        assert merged.fuel_level == 40
        assert merged.battery_soc == 80
        assert merged.source_channel == "brand_native+eu_data_act"

    def test_drivetrain_reclassified_after_merge(self) -> None:
        a = VehicleData(vin="X", fuel_level=40)       # looks ICE alone
        b = VehicleData(vin="X", battery_soc=80)      # looks EV alone
        merged = merge_channels([("mbb", a), ("eu_data_act", b)])
        assert merged.has_battery is True
        assert merged.has_combustion is True
        assert merged.is_hybrid is True
        assert merged.is_electric is False

    def test_single_contributor_named(self) -> None:
        a = VehicleData(vin="X", fuel_level=40)
        b = VehicleData(vin="X")  # all None
        merged = merge_channels([("mbb", a), ("eu_data_act", b)])
        assert merged.fuel_level == 40
        assert merged.source_channel == "mbb"

    def test_all_empty_no_provenance(self) -> None:
        a = VehicleData(vin="X")
        b = VehicleData(vin="X")
        merged = merge_channels([("mbb", a), ("eu_data_act", b)])
        assert merged.source_channel is None

    def test_inputs_not_mutated(self) -> None:
        a = VehicleData(vin="X", fuel_level=40)
        b = VehicleData(vin="X", battery_soc=80)
        merge_channels([("mbb", a), ("eu_data_act", b)])
        assert a.battery_soc is None   # a untouched
        assert b.fuel_level is None    # b untouched
        assert a.source_channel is None

    def test_cross_vin_is_not_merged(self) -> None:
        a = VehicleData(vin="X", fuel_level=40)
        b = VehicleData(vin="Y", battery_soc=80)  # different VIN — must be ignored
        merged = merge_channels([("mbb", a), ("eu_data_act", b)])
        assert merged.battery_soc is None
        assert merged.fuel_level == 40

    def test_empty_sources_raises(self) -> None:
        with pytest.raises(ValueError):
            merge_channels([])

    def test_supplementary_mutable_not_aliased(self) -> None:
        # adversarial-review fix: a gap-filled dict/list must be a copy, not a
        # shared reference to the source snapshot.
        a = VehicleData(vin="X")
        b = VehicleData(vin="X", raw_unmapped_fields={"k": "v"})
        merged = merge_channels([("mbb", a), ("eu_data_act", b)])
        assert merged.raw_unmapped_fields == {"k": "v"}
        b.raw_unmapped_fields["k"] = "CORRUPTED"        # mutate source after merge
        assert merged.raw_unmapped_fields == {"k": "v"}  # merged unaffected
        merged.raw_unmapped_fields["new"] = "1"          # mutate merged
        assert "new" not in b.raw_unmapped_fields        # source unaffected

    def test_base_mutable_not_aliased(self) -> None:
        a = VehicleData(vin="X", raw_unmapped_fields={"a": "1"})
        b = VehicleData(vin="X", battery_soc=80)
        merged = merge_channels([("mbb", a), ("eu_data_act", b)])
        a.raw_unmapped_fields["a"] = "CORRUPTED"          # mutate base after merge
        assert merged.raw_unmapped_fields == {"a": "1"}   # base was deep-copied


class TestGatherAndMerge:
    """C1 async orchestrator: read suppliers concurrently, merge, tolerate
    per-channel failure, never sink the poll on a read-only fallback."""

    def test_no_suppliers_returns_primary_identity(self) -> None:
        primary = VehicleData(vin="X", fuel_level=40)
        out = asyncio.run(gather_and_merge("mbb", primary, []))
        assert out is primary  # byte-for-byte single-channel passthrough

    def test_supplier_success_merges(self) -> None:
        primary = VehicleData(vin="X", fuel_level=40)
        supp = VehicleData(vin="X", battery_soc=80)
        out = asyncio.run(gather_and_merge("mbb", primary, [("eu_data_act", _ok(supp))]))
        assert out.fuel_level == 40 and out.battery_soc == 80
        assert out.source_channel == "eu_data_act+mbb"

    def test_failing_supplier_is_tolerated(self) -> None:
        primary = VehicleData(vin="X", fuel_level=40)
        out = asyncio.run(gather_and_merge("mbb", primary, [("eu_data_act", _fail())]))
        assert out.fuel_level == 40            # primary survives
        assert out.battery_soc is None

    def test_none_supplier_skipped(self) -> None:
        primary = VehicleData(vin="X", fuel_level=40)
        out = asyncio.run(gather_and_merge("mbb", primary, [("vwde", _none())]))
        assert out is primary

    def test_mixed_success_and_failure(self) -> None:
        primary = VehicleData(vin="X", fuel_level=40)
        good = VehicleData(vin="X", battery_soc=80)
        out = asyncio.run(gather_and_merge(
            "mbb", primary,
            [("dead", _fail()), ("eu_data_act", _ok(good))],
        ))
        assert out.fuel_level == 40 and out.battery_soc == 80
        assert out.source_channel == "eu_data_act+mbb"
