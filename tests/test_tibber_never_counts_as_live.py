# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tibber fills gaps and never counts as a live channel.

The Tibber read channel (v2.19.0) promised to be the lowest-trust source: it
only fills fields the car's own channels left empty and never overwrites them.
A month later the live-supersede rule arrived, and it decides "live" by
exclusion: every channel that is neither the portal batch nor a held push
source counts as live. Tibber was in neither set, so it started to replace
portal values for charge, plug, climate and closures, to escape the SoC hold,
to count as a live contributor in the stale verdict, and to prove a live feed
whenever one of its values changed.

Tibber carries no per-field capture stamp, so there is no evidence that would
let it win on age. It stays a pure gap filler. It is deliberately NOT a held
source either: its car is identified by VIN, so the held rules that stand in
for a hand-set link (field whitelist, stripping after the hold time) must not
apply to it.
"""
from __future__ import annotations

from custom_components.vag_connect.cariad._channel_merge import (
    is_held_source,
    merge_channels,
)
from custom_components.vag_connect.cariad.models import VehicleData
from custom_components.vag_connect.cariad.vehicle_cache import reconcile
from custom_components.vag_connect.coordinator import (
    _has_live_contributor,
    _values_moved,
)

_VIN = "WVWTEST0000FAKE02"


def _v(**kw) -> VehicleData:
    return VehicleData(vin=_VIN, **kw)


class TestMergeKeepsThePortalValue:
    def test_portal_soc_and_plug_are_not_overwritten(self) -> None:
        m = merge_channels([
            ("eu_data_act", _v(battery_soc=80, plug_connected=True)),
            ("tibber", _v(battery_soc=50, plug_connected=False)),
        ])
        assert m.battery_soc == 80
        assert m.plug_connected is True
        assert m.field_sources["battery_soc"] == "eu_data_act"
        assert m.field_sources["plug_connected"] == "eu_data_act"

    def test_same_with_a_live_primary_that_lacks_the_field(self) -> None:
        # The live channel arms the supersede block but has no SoC itself;
        # Tibber must not step in as the "live" owner of the portal's field.
        m = merge_channels([
            ("website_authproxy", _v(odometer_km=12000)),
            ("eu_data_act", _v(battery_soc=80)),
            ("tibber", _v(battery_soc=50)),
        ])
        assert m.battery_soc == 80
        assert m.field_sources["battery_soc"] == "eu_data_act"

    def test_control_tibber_still_fills_an_empty_field(self) -> None:
        m = merge_channels([
            ("eu_data_act", _v(odometer_km=12000)),
            ("tibber", _v(battery_soc=50, target_soc=80)),
        ])
        assert m.battery_soc == 50
        assert m.target_soc == 80  # not limited to the held whitelist
        assert m.field_sources["battery_soc"] == "tibber"

    def test_control_a_real_live_channel_still_beats_the_portal(self) -> None:
        m = merge_channels([
            ("eu_data_act", _v(battery_soc=80)),
            ("website_authproxy", _v(battery_soc=54)),
            ("tibber", _v(battery_soc=50)),
        ])
        assert m.battery_soc == 54
        assert m.field_sources["battery_soc"] == "website_authproxy"

    def test_tibber_is_not_a_held_source(self) -> None:
        assert is_held_source("tibber") is False


class TestSocHoldTreatsTibberAsNotLive:
    def test_tibber_soc_does_not_escape_the_hv_hold(self) -> None:
        prev = {"battery_soc": 55, "battery_soc_from_hv": True}
        fresh = {
            "battery_soc": 67,
            "battery_soc_from_hv": False,
            "field_sources": {
                "battery_soc": "tibber",
                "battery_soc_from_hv": "eu_data_act",
            },
        }
        merged, notes = reconcile(prev, fresh)
        assert merged["battery_soc"] == 55
        assert any("held recorded 55" in n for n in notes)

    def test_control_a_live_soc_still_escapes_it(self) -> None:
        prev = {"battery_soc": 55, "battery_soc_from_hv": True}
        fresh = {
            "battery_soc": 54,
            "battery_soc_from_hv": False,
            "field_sources": {
                "battery_soc": "website_authproxy",
                "battery_soc_from_hv": "eu_data_act",
            },
        }
        merged, _ = reconcile(prev, fresh)
        assert merged["battery_soc"] == 54


class TestStaleVerdictIgnoresTibber:
    def test_tibber_is_not_a_live_contributor(self) -> None:
        assert not _has_live_contributor({"source_channel": "tibber"})
        assert not _has_live_contributor({"source_channel": "eu_data_act+tibber"})

    def test_control_a_live_channel_beside_it_still_counts(self) -> None:
        assert _has_live_contributor({"source_channel": "tibber+website_authproxy"})

    def test_a_changed_tibber_value_is_not_proof_of_a_live_feed(self) -> None:
        batch = {"battery_soc": 80, "field_sources": {"battery_soc": "eu_data_act"}}
        tib = {"battery_soc": 50, "field_sources": {"battery_soc": "tibber"}}
        assert _values_moved(batch, tib) is None
        assert _values_moved(tib, batch) is None
        tib2 = {"battery_soc": 52, "field_sources": {"battery_soc": "tibber"}}
        assert _values_moved(tib, tib2) is None

    def test_control_a_changed_batch_value_still_counts(self) -> None:
        before = {"battery_soc": 80, "field_sources": {"battery_soc": "eu_data_act"}}
        after = {"battery_soc": 78, "field_sources": {"battery_soc": "eu_data_act"}}
        assert _values_moved(before, after) == "battery_soc"
