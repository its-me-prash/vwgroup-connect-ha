# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""A2 — per-field provenance: every reading knows which channel produced it.

``source_channel`` answers "which channels fed this car" and is only set when
a merge happened. It cannot answer "where did THIS reading come from", which
is what an entity needs to show its own source — on a Golf GTE the fuel level
and the SoC legitimately come from different channels.

``field_sources`` records {field_name: channel} for every field that carries a
value, on every merge including single-channel ones.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from custom_components.vag_connect.cariad._channel_merge import (
    annotate_provenance,
    merge_channels,
)
from custom_components.vag_connect.cariad.models import VehicleData


def test_single_channel_still_gets_provenance() -> None:
    # The whole point: a one-source car must still know where its data is from.
    a = VehicleData(vin="V", battery_soc=55, odometer_km=1000)
    m = merge_channels([("eu_data_act", a)])
    assert m.field_sources["battery_soc"] == "eu_data_act"
    assert m.field_sources["odometer_km"] == "eu_data_act"


def test_gap_filled_field_is_attributed_to_the_filler() -> None:
    # The Golf GTE case: SoC from the portal, fuel from MBB.
    portal = VehicleData(vin="V", battery_soc=55)
    mbb = VehicleData(vin="V", fuel_level=80)
    m = merge_channels([("eu_data_act", portal), ("mbb", mbb)])
    assert m.field_sources["battery_soc"] == "eu_data_act"
    assert m.field_sources["fuel_level"] == "mbb"


def test_primary_keeps_ownership_when_both_carry_the_field() -> None:
    # A supplementary never overwrites the primary, so it never owns the field.
    primary = VehicleData(vin="V", battery_soc=55)
    supp = VehicleData(vin="V", battery_soc=99)
    m = merge_channels([("eu_data_act", primary), ("vw_de", supp)])
    assert m.battery_soc == 55
    assert m.field_sources["battery_soc"] == "eu_data_act"


def test_unset_fields_are_absent_not_guessed() -> None:
    a = VehicleData(vin="V", battery_soc=55)
    m = merge_channels([("eu_data_act", a)])
    assert "fuel_level" not in m.field_sources
    assert "odometer_km" not in m.field_sources


def test_field_sources_is_never_itself_merged() -> None:
    # It is bookkeeping, not vehicle data: a stale map on a source snapshot
    # must not leak into the merged result.
    a = VehicleData(vin="V", battery_soc=55)
    b = VehicleData(vin="V", fuel_level=80)
    b.field_sources = {"battery_soc": "LIES", "nonsense": "LIES"}
    m = merge_channels([("eu_data_act", a), ("mbb", b)])
    assert m.field_sources["battery_soc"] == "eu_data_act"
    assert "nonsense" not in m.field_sources


def test_provenance_matches_source_channel() -> None:
    # The two views must not contradict each other.
    portal = VehicleData(vin="V", battery_soc=55)
    mbb = VehicleData(vin="V", fuel_level=80)
    m = merge_channels([("eu_data_act", portal), ("mbb", mbb)])
    assert m.source_channel == "eu_data_act+mbb"
    assert set(m.field_sources.values()) == {"eu_data_act", "mbb"}


def test_vin_mismatch_contributes_nothing() -> None:
    a = VehicleData(vin="V", battery_soc=55)
    other = VehicleData(vin="OTHER", fuel_level=80)
    m = merge_channels([("eu_data_act", a), ("mbb", other)])
    assert "fuel_level" not in m.field_sources
    assert m.fuel_level is None


# ── B2 — provenance for cars with no supplementary channel ──────────────────
#
# These never reach merge_channels (the coordinator returns the primary early),
# so before B2 they had no provenance at all — which is the common case, i.e.
# the per-entity source attribute was useless for most users.


def test_annotate_gives_single_channel_car_its_provenance() -> None:
    d = annotate_provenance("eu_data_act", VehicleData(vin="V", battery_soc=55))
    assert d.field_sources == {"battery_soc": "eu_data_act"}
    assert d.source_channel == "eu_data_act"


def test_annotate_skips_fields_without_a_value() -> None:
    d = annotate_provenance("eu_data_act", VehicleData(vin="V", battery_soc=55))
    assert "fuel_level" not in d.field_sources


def test_annotate_leaves_drivetrain_flags_alone() -> None:
    # THE guard: annotate must not become a merge in disguise. merge_channels
    # re-derives the drivetrain from the data (_merge_drivetrain); doing that
    # here would silently re-classify every single-channel car as a side effect
    # of adding a provenance label.
    d = VehicleData(vin="V", battery_soc=55)
    before = (d.has_battery, d.has_combustion, d.is_electric, d.is_hybrid)
    annotate_provenance("eu_data_act", d)
    assert (d.has_battery, d.has_combustion, d.is_electric, d.is_hybrid) == before


def test_annotate_touches_no_reading() -> None:
    d = VehicleData(vin="V", battery_soc=55, fuel_level=80, odometer_km=1234)
    annotate_provenance("eu_data_act", d)
    assert (d.battery_soc, d.fuel_level, d.odometer_km) == (55, 80, 1234)


def test_annotate_empty_snapshot_claims_nothing() -> None:
    # A car that produced no data must not be labelled as if it had.
    d = annotate_provenance("eu_data_act", VehicleData(vin="V"))
    assert d.field_sources == {}
    assert d.source_channel is None


def test_annotate_does_not_attribute_its_own_bookkeeping() -> None:
    d = annotate_provenance("eu_data_act", VehicleData(vin="V", battery_soc=55))
    for bookkeeping in ("vin", "source_channel", "field_sources"):
        assert bookkeeping not in d.field_sources


# ── the wiring, not just the helper ─────────────────────────────────────────
#
# The helper above is new, so its own tests can't fail on the old code. What
# actually changed for users is the coordinator path: a car with no
# supplementary channel used to return the primary untouched and therefore
# carried no provenance at all. These fail before the fix.


def _coord(suppliers):
    from custom_components.vag_connect.coordinator import VagConnectCoordinator

    c = VagConnectCoordinator.__new__(VagConnectCoordinator)
    client = MagicMock()
    client.supplementary_readers = MagicMock(return_value=suppliers)
    c._cariad_client = client
    c._primary_channel_name = MagicMock(return_value="eu_data_act")
    return c


@pytest.mark.asyncio
async def test_poll_without_supplementary_still_records_provenance() -> None:
    out = await _coord([])._merge_supplementary("V", VehicleData(vin="V", battery_soc=55))
    assert out.field_sources == {"battery_soc": "eu_data_act"}
    assert out.source_channel == "eu_data_act"


@pytest.mark.asyncio
async def test_client_without_supplementary_support_still_records_provenance() -> None:
    # Brands whose client has no supplementary_readers at all.
    from custom_components.vag_connect.coordinator import VagConnectCoordinator

    c = VagConnectCoordinator.__new__(VagConnectCoordinator)
    client = MagicMock(spec=[])  # no supplementary_readers attribute
    c._cariad_client = client
    c._primary_channel_name = MagicMock(return_value="mbb")
    out = await c._merge_supplementary("V", VehicleData(vin="V", fuel_level=80))
    assert out.field_sources == {"fuel_level": "mbb"}
