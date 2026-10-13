# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#1767 — the four tyre-pressure-sensor DIDs 0x4E94 to 0x4E97.

Five Audis reported the same four fields on every poll, the largest single
family in the Scout backlog:

    LL_TirePressMonit1UDS_ReadDataByIdentMeasuValue_
        Left front tire pressure sensor remaining operation time_0x4E94

They are not tyre pressure. The name says remaining operation time of the
pressure SENSOR, so the four per-wheel pressure entities are the wrong
destination and this needs its own reading.

Why nothing happened with them: the payload is base64, and ``_uds_envelope``
json-loads it and then requires a dict. ``MTIw`` decodes to ``120``, a bare
number, so the envelope parser correctly refused it, the dispatch loop only
marks a key used after a non-empty decode, and the field came back as
undiscovered on the next poll. Forever.

The measured values decide the design. One car sends 120 on all four wheels;
the other four send 255, which is the CAN "signal not available" byte that
#1403 already screens for the charge level. So:

- 255 is screened, exactly like the sentinels the pressure-delta family drops.
- The leaf is consumed anyway when it decodes, sentinel included, because
  reading a sentinel IS an interpretation. Otherwise the four cars that send
  255, the majority of reporters, would keep filing the same issue.
- The catalogue gives these four no unit and no meaning, so the value is a
  unitless diagnostic, the same treatment the per-wheel pressure and the
  pressure delta already get for being unit-ambiguous.
"""
from __future__ import annotations

import base64

from custom_components.vag_connect.cariad.auth._eu_data_act import (
    map_dataset_to_vehicle_data,
)
from custom_components.vag_connect.cariad.models import VehicleData

# The field names exactly as the five reports carry them.
_PREFIX = "LL_TirePressMonit1UDS_ReadDataByIdentMeasuValue_"
_KEYS = {
    "fl": f"{_PREFIX}Left front tire pressure sensor remaining operation time_0x4E94",
    "fr": f"{_PREFIX}Right front tire pressure sensor remaining operation time_0x4E95",
    "rl": f"{_PREFIX}Left rear tire pressure sensor remaining operation time_0x4E96",
    "rr": f"{_PREFIX}Right rear tire pressure sensor remaining operation time_0x4E97",
}


def _b64(value: str) -> str:
    """The portal's shape: base64 plus the unit-token separator (#1772)."""
    return base64.b64encode(value.encode()).decode() + " "


def _map(fields: dict) -> VehicleData:
    return map_dataset_to_vehicle_data(fields, VehicleData(vin="X"))


def test_the_samples_are_what_we_think_they_are() -> None:
    """Ground the two observed payloads before anything is built on them."""
    assert base64.b64decode("MTIw") == b"120"
    assert base64.b64decode("MjU1") == b"255"


class TestTheReadingLands:
    """The one car that sends a real value gets four readings."""

    def test_front_left_from_the_verbatim_field_name(self):
        d = _map({_KEYS["fl"]: "MTIw "})
        assert d.tyre_sensor_life_fl == 120

    def test_all_four_wheels_land_on_their_own_slot(self):
        d = _map({k: "MTIw " for k in _KEYS.values()})
        assert (
            d.tyre_sensor_life_fl,
            d.tyre_sensor_life_fr,
            d.tyre_sensor_life_rl,
            d.tyre_sensor_life_rr,
        ) == (120, 120, 120, 120)

    def test_the_did_decides_the_wheel_not_the_name(self):
        """Dispatch is on the DID, like every other UDS family here."""
        d = _map({f"{_PREFIX}whatever the ecu calls it_0x4E95": "MTIw "})
        assert d.tyre_sensor_life_fr == 120
        assert d.tyre_sensor_life_fl is None

    def test_an_instance_suffix_still_matches(self):
        """The same DID can arrive from several logical links (``_0x4E94_2``)."""
        d = _map({f"{_PREFIX}Left front ... operation time_0x4E94_2": "MTIw "})
        assert d.tyre_sensor_life_fl == 120

    def test_a_lowercase_did_matches(self):
        d = _map({f"{_PREFIX}Left front ... operation time_0x4e94": "MTIw "})
        assert d.tyre_sensor_life_fl == 120

    def test_no_separator_also_works(self):
        """Do not depend on the trailing space being there."""
        d = _map({_KEYS["fl"]: "MTIw"})
        assert d.tyre_sensor_life_fl == 120

    def test_a_real_unit_token_is_tolerated(self):
        d = _map({_KEYS["fl"]: "MTIw Unit_Month"})
        assert d.tyre_sensor_life_fl == 120

    def test_an_existing_value_is_not_overwritten(self):
        """Fill-if-empty, like every other assignment in this mapper."""
        d = map_dataset_to_vehicle_data(
            {_KEYS["fl"]: "MTIw "},
            VehicleData(vin="X", tyre_sensor_life_fl=7),
        )
        assert d.tyre_sensor_life_fl == 7

    def test_zero_is_published(self):
        """Nothing suggests 0 is a sentinel for this family, so keep it."""
        d = _map({_KEYS["fl"]: _b64("0")})
        assert d.tyre_sensor_life_fl == 0


class TestTheSentinelIsScreened:
    """Four of the five reporting cars send the not-available byte."""

    def test_255_is_not_published(self):
        d = _map({_KEYS["fl"]: "MjU1 "})
        assert d.tyre_sensor_life_fl is None

    def test_255_on_all_four_publishes_nothing(self):
        """The exact payload of #1812, #1769, #1798 and #1802."""
        d = _map({k: "MjU1 " for k in _KEYS.values()})
        assert [
            d.tyre_sensor_life_fl, d.tyre_sensor_life_fr,
            d.tyre_sensor_life_rl, d.tyre_sensor_life_rr,
        ] == [None, None, None, None]

    def test_254_is_still_published(self):
        """Only the sentinel is screened, not the top of the byte range."""
        d = _map({_KEYS["fl"]: _b64("254")})
        assert d.tyre_sensor_life_fl == 254

    def test_a_value_above_the_byte_range_is_screened(self):
        d = _map({_KEYS["fl"]: _b64("300")})
        assert d.tyre_sensor_life_fl is None

    def test_a_negative_value_is_screened(self):
        d = _map({_KEYS["fl"]: _b64("-5")})
        assert d.tyre_sensor_life_fl is None


class TestTheScoutStopsOffering:
    """The whole point: five issues for one family, filed on every poll."""

    def test_a_published_value_consumes_its_leaf(self):
        d = _map({_KEYS["fl"]: "MTIw "})
        assert _KEYS["fl"] not in d.raw_unmapped_fields

    def test_a_screened_sentinel_ALSO_consumes_its_leaf(self):
        """Reading the sentinel is an interpretation, so the field is handled.

        This is the case that matters: the majority of reporting cars send 255,
        and if screening the value left the leaf unconsumed they would keep
        filing the issue the fix was meant to end.
        """
        d = _map({_KEYS["fl"]: "MjU1 "})
        assert _KEYS["fl"] not in d.raw_unmapped_fields

    def test_all_four_sentinels_are_consumed(self):
        d = _map({k: "MjU1 " for k in _KEYS.values()})
        assert not [k for k in d.raw_unmapped_fields if "0x4E9" in k]

    def test_an_undecodable_payload_stays_visible(self):
        """No-suppression policy: what we cannot read, we keep reporting."""
        d = _map({_KEYS["fl"]: "!!!not base64!!!"})
        assert d.tyre_sensor_life_fl is None
        assert _KEYS["fl"] in d.raw_unmapped_fields

    def test_a_non_numeric_payload_stays_visible(self):
        d = _map({_KEYS["fl"]: _b64("not a number")})
        assert d.tyre_sensor_life_fl is None
        assert _KEYS["fl"] in d.raw_unmapped_fields

    def test_an_unrelated_did_is_untouched(self):
        """Only these four DIDs are claimed; the rest stay discoverable."""
        key = f"{_PREFIX}something else entirely_0x4E99"
        d = _map({key: "MTIw "})
        assert key in d.raw_unmapped_fields


class TestItReachesDiagnostics:
    """Unitless and diagnostic, but never hidden."""

    def test_the_value_is_in_to_dict(self):
        d = _map({_KEYS["rr"]: "MTIw "})
        assert d.to_dict()["tyre_sensor_life_rr"] == 120

    def test_the_four_fields_exist_on_a_bare_model(self):
        d = VehicleData(vin="X")
        for slot in ("fl", "fr", "rl", "rr"):
            assert getattr(d, f"tyre_sensor_life_{slot}") is None
