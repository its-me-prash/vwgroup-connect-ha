# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#1798 / #1802 — trailer detection (``AAG_Anhaenger_erkannt``).

Two Audis report the trailer-hitch module's own verdict on whether something is
hooked up. Unlike the other Scout families, this one had no destination at all:
the data model carried no trailer field, so it is a genuinely new capability
rather than a spelling the mapper failed to ask for.

Both cars sample ``"kein_Anhaenger_erkannt "``, with the trailing space the
portal appends as a unit token even when the unit is empty. So the observed
value is the negative one, and the positive spelling has never been seen.

That decides the parsing. Only the two spellings of this one enum are believed
and anything else reads as unknown, which is the rule ``_hist_state`` already
applies to the door and boot states for a stated reason: folding an
unrecognised value into False would tell an owner that nothing is hooked up
when the car never said so. For a trailer that matters more than for a boot,
because people automate on it.
"""
from __future__ import annotations

from custom_components.vag_connect.cariad.auth._eu_data_act import (
    map_dataset_to_vehicle_data,
)
from custom_components.vag_connect.cariad.models import VehicleData

_KEY = "AAG_Anhaenger_erkannt"


def _map(fields: dict) -> VehicleData:
    return map_dataset_to_vehicle_data(fields, VehicleData(vin="X"))


class TestTheObservedValue:
    """Both reporting cars send the negative spelling."""

    def test_no_trailer_reads_false(self):
        d = _map({_KEY: "kein_Anhaenger_erkannt "})
        assert d.trailer_connected is False

    def test_no_trailer_without_the_unit_separator(self):
        d = _map({_KEY: "kein_Anhaenger_erkannt"})
        assert d.trailer_connected is False

    def test_the_leaf_is_consumed(self):
        """The whole point: two issues filed for a field nothing read."""
        d = _map({_KEY: "kein_Anhaenger_erkannt "})
        assert _KEY not in d.raw_unmapped_fields


class TestThePositiveValue:
    """Never observed, so it is inferred from the negative spelling only."""

    def test_trailer_detected_reads_true(self):
        d = _map({_KEY: "Anhaenger_erkannt "})
        assert d.trailer_connected is True

    def test_case_does_not_matter(self):
        d = _map({_KEY: "ANHAENGER_ERKANNT"})
        assert d.trailer_connected is True


class TestAnythingElseIsUnknown:
    """An unrecognised value must not become a confident False."""

    def test_an_unexpected_token_reads_unknown(self):
        d = _map({_KEY: "nicht_verfuegbar "})
        assert d.trailer_connected is None

    def test_an_empty_value_reads_unknown(self):
        d = _map({_KEY: " "})
        assert d.trailer_connected is None

    def test_a_car_without_the_field_reads_unknown(self):
        d = _map({"mileage": "1000"})
        assert d.trailer_connected is None

    def test_an_unexpected_token_does_not_fall_back_to_false(self):
        """Stated as the failure it prevents, not as an implementation detail."""
        d = _map({_KEY: "Anhaengererkennung_gestoert"})
        assert d.trailer_connected is not False


class TestItReachesTheRestOfTheIntegration:
    def test_the_value_is_in_to_dict(self):
        d = _map({_KEY: "Anhaenger_erkannt "})
        assert d.to_dict()["trailer_connected"] is True

    def test_the_field_exists_on_a_bare_model(self):
        assert VehicleData(vin="X").trailer_connected is None

    def test_a_binary_sensor_is_declared_for_it(self):
        from custom_components.vag_connect.binary_sensor import (
            BINARY_DESCRIPTIONS,
            _DATA_PRESENT_REQUIRED,
        )

        keys = {d.key for d in BINARY_DESCRIPTIONS}
        assert "trailer_connected" in keys
        # gated, so a car that never reports it spawns no phantom entity
        assert "trailer_connected" in _DATA_PRESENT_REQUIRED

    def test_the_name_is_translated_everywhere(self):
        """HA does not fall back to English for a custom integration."""
        import json
        from pathlib import Path

        root = Path(__file__).resolve().parents[1] / "custom_components" / "vag_connect"
        paths = [root / "strings.json"] + sorted(
            (root / "translations").glob("*.json")
        )
        assert len(paths) >= 12
        missing = []
        for p in paths:
            data = json.loads(p.read_text(encoding="utf-8"))
            name = (
                data.get("entity", {})
                .get("binary_sensor", {})
                .get("trailer_connected", {})
                .get("name")
            )
            if not name:
                missing.append(p.name)
        assert not missing, missing
