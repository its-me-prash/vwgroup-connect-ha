# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""D#1231 / #1195-family — a live channel's live-telemetry reading must always
beat the EU Data Act batch feed's, regardless of which channel is primary.

The EU-DA continuous feed ships frozen stop-charging blocks (a snapshot from the
last charge, re-sent, sometimes re-stamped fresh). Under the plain gap-fill merge
that stale value could win — making SoC/charge readings jump backwards mid-charge
while a competing single-live-source integration stayed steady. The cross-channel
merge now hands every live-telemetry field the batch feed owns to the highest-
priority LIVE channel that actually has a reading. Brand-agnostic: keyed on the
channel name (``eu_data_act`` = batch, everything else = live) and the field,
never on brand. EU-DA-only cars, and fields no live channel reports, are
untouched.
"""
from __future__ import annotations

from custom_components.vag_connect.cariad._channel_merge import (
    _LIVE_TELEMETRY,
    merge_channels,
)
from custom_components.vag_connect.cariad.models import VehicleData


def _v(**kw) -> VehicleData:
    return VehicleData(vin="V1", **kw)


class TestLiveBeatsBatch:
    def test_eu_da_primary_live_supplementary_overrides(self):
        # EU-DA (primary) carries a stale frozen block; vw.de (live) is fresh.
        eu = _v(battery_soc=94, charging_state="charging", charging_power_kw=11.0,
                plug_state="connected", electric_range_km=300)
        live = _v(battery_soc=73, charging_state="off", charging_power_kw=0.0,
                  plug_state="disconnected", electric_range_km=210)
        m = merge_channels([("eu_data_act", eu), ("website_authproxy", live)])
        assert m.battery_soc == 73                 # live wins, not the stale 94
        assert m.charging_state == "off"
        assert m.charging_power_kw == 0.0
        assert m.plug_state == "disconnected"
        assert m.electric_range_km == 210
        assert m.field_sources["battery_soc"] == "website_authproxy"

    def test_live_primary_eu_da_supplementary_keeps_live(self):
        live = _v(battery_soc=73, charging_state="off")
        eu = _v(battery_soc=94, charging_state="charging")
        m = merge_channels([("website_authproxy", live), ("eu_data_act", eu)])
        assert m.battery_soc == 73
        assert m.charging_state == "off"
        assert m.field_sources["battery_soc"] == "website_authproxy"

    def test_cross_brand_bff_channel_also_supersedes(self):
        # any non-eu_data_act channel counts as live (Audi/VW BFF, mbb, OLA…)
        eu = _v(battery_soc=94)
        bff = _v(battery_soc=55)
        m = merge_channels([("eu_data_act", eu), ("audi", bff)])
        assert m.battery_soc == 55
        assert m.field_sources["battery_soc"] == "audi"


class TestScopedAndSafe:
    def test_eu_da_only_car_is_untouched(self):
        # no live channel present → EU-DA value survives (the #1195-only case)
        eu = _v(battery_soc=94, charging_state="charging")
        m = merge_channels([("eu_data_act", eu)])
        assert m.battery_soc == 94
        assert m.charging_state == "charging"

    def test_live_channel_without_the_field_leaves_eu_da_value(self):
        # a command-only live channel (mbb) that doesn't report SoC must NOT
        # blank EU-DA's SoC — EU-DA is the only source for it here.
        eu = _v(battery_soc=94)
        mbb = _v(odometer_km=12000)  # no SoC
        m = merge_channels([("eu_data_act", eu), ("mbb", mbb)])
        assert m.battery_soc == 94
        assert m.field_sources["battery_soc"] == "eu_data_act"

    def test_non_live_telemetry_field_is_not_superseded(self):
        # odometer is monotonic-protected elsewhere and is NOT in the live set:
        # the plain gap-fill (primary wins) must still stand.
        assert "odometer_km" not in _LIVE_TELEMETRY
        eu = _v(odometer_km=1000)
        live = _v(odometer_km=1005)
        m = merge_channels([("eu_data_act", eu), ("website_authproxy", live)])
        assert m.odometer_km == 1000  # EU-DA primary keeps it (not superseded)

    def test_batch_fills_gap_when_live_lacks_the_field(self):
        # live channel present but silent on a live-telemetry field → EU-DA may
        # still fill the gap (better a batch value than nothing on that field).
        live = _v(charging_state="off")          # no SoC
        eu = _v(battery_soc=80)                    # only SoC
        m = merge_channels([("website_authproxy", live), ("eu_data_act", eu)])
        assert m.battery_soc == 80
        assert m.charging_state == "off"
