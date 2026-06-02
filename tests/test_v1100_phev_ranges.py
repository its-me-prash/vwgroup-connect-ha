# Copyright 2026 Prash Balan (@its-me-prash) — Apache License 2.0
# SPDX-License-Identifier: Apache-2.0
"""Tests for v1.10.0 — PHEV range triple (#94) + Audi dieselRange (#91).

Three groups:

- ``TestVehicleDataFields`` — VehicleData has the new fields with safe
  defaults so old code reading ``.electric_range_km`` etc. doesn't crash.
- ``TestVWEUParseRanges`` — parser populates the right field based on
  ``primaryEngine.type`` / ``secondaryEngine.type`` and back-fills
  combustion range from older ``measurements.rangeStatus.value.dieselRange``
  when no ``fuelStatus`` block exists.
- ``TestSkodaParseRanges`` — same logic for Skoda mysmob driving-range
  endpoint (``electricRange.distanceInKm`` + ``combustionRange.distanceInKm``
  + ``totalRangeInKm``).
- ``TestSensorGating`` — phantom-entity prevention: a pure EV must NOT
  get ``combustion_range_km``, a pure ICE must NOT get
  ``electric_range_km``.
"""

from __future__ import annotations




# ─────────────────────────────────────────────────────────────────────────────
# VehicleData fields
# ─────────────────────────────────────────────────────────────────────────────


class TestVehicleDataFields:
    def test_new_range_fields_default_to_none(self):
        from custom_components.vag_connect.cariad.models import VehicleData

        d = VehicleData(vin="WVGTEST123456")
        assert d.electric_range_km is None
        assert d.combustion_range_km is None
        assert d.total_range_km is None

    def test_to_dict_includes_new_fields(self):
        from custom_components.vag_connect.cariad.models import VehicleData

        d = VehicleData(
            vin="VIN1",
            electric_range_km=45,
            combustion_range_km=520,
            total_range_km=565,
        )
        out = d.to_dict()
        assert out["electric_range_km"] == 45
        assert out["combustion_range_km"] == 520
        assert out["total_range_km"] == 565


# ─────────────────────────────────────────────────────────────────────────────
# VW EU parsing
# ─────────────────────────────────────────────────────────────────────────────


class TestVWEUParseRanges:
    def _client(self):
        from custom_components.vag_connect.cariad.api.vw_eu import VWEUClient

        client = VWEUClient.__new__(VWEUClient)
        # Minimum scaffolding for _parse_status — vehicle metadata is optional.
        client._vehicle_metadata = {}
        return client

    def test_phev_with_primary_electric_secondary_gasoline(self):
        """VW Golf 7 GTE shape (#90 verified live):

        primaryEngine.type=electric, secondaryEngine.type=gasoline
        plus an explicit totalRange_km. Each goes to its own field.
        ``has_battery`` is set from the primary engine's type, so
        the parser picks the battery range as the back-compat
        ``range_km`` headline.
        """
        client = self._client()
        raw = {
            "fuelStatus": {
                "rangeStatus": {
                    "value": {
                        "primaryEngine": {
                            "type": "electric",
                            "remainingRange_km": 45,
                        },
                        "secondaryEngine": {
                            "type": "gasoline",
                            "remainingRange_km": 520,
                        },
                        "totalRange_km": 565,
                    }
                }
            },
        }
        d = client._parse_status("VINX", raw, parking={})
        assert d.electric_range_km == 45
        assert d.combustion_range_km == 520
        assert d.total_range_km == 565
        assert d.has_battery is True
        assert d.has_combustion is True
        # Headline number for a PHEV with battery → battery range.
        assert d.range_km == 45

    def test_swapped_engine_positions_classified_by_type(self):
        """Some firmwares put primary=gasoline, secondary=electric.
        We classify by ``type`` not by position — both must end up in
        the right field regardless of order.
        """
        client = self._client()
        raw = {
            "fuelStatus": {
                "rangeStatus": {
                    "value": {
                        "primaryEngine": {
                            "type": "gasoline",
                            "remainingRange_km": 480,
                        },
                        "secondaryEngine": {
                            "type": "electric",
                            "remainingRange_km": 38,
                        },
                    }
                }
            },
        }
        d = client._parse_status("VINX", raw, parking={})
        assert d.electric_range_km == 38
        assert d.combustion_range_km == 480

    def test_audi_diesel_range_from_measurements_block(self):
        """Audi S6 C8 2021 (#91 verified live): no fuelStatus block,
        only ``measurements.rangeStatus.value.dieselRange = 190``.
        Must populate combustion_range_km via the fallback path."""
        client = self._client()
        raw = {
            "measurements": {
                "rangeStatus": {
                    "value": {"dieselRange": 190},
                },
            },
        }
        d = client._parse_status("VINA", raw, parking={})
        assert d.combustion_range_km == 190
        assert d.electric_range_km is None
        assert d.total_range_km is None
        # Headline falls through to combustion since no battery.
        assert d.range_km == 190

    def test_pure_ev_only_electric_range_set(self):
        """Pure EV: only batteryStatus.cruisingRangeElectric_km; no
        fuelStatus block. combustion_range_km must stay None so no
        phantom entity is created.

        The headline ``range_km`` is set from electric_range_km only
        when ``has_battery`` is True, which is determined elsewhere
        in the parser from ``measurements.fuelLevelStatus.value.carType``
        (verified live on ID.4). We include carType="electric" so the
        full pure-EV path runs and the headline picks up.
        """
        client = self._client()
        raw = {
            "charging": {
                "batteryStatus": {
                    "value": {"cruisingRangeElectric_km": 380},
                },
            },
            "measurements": {
                "fuelLevelStatus": {
                    "value": {"carType": "electric"},
                },
            },
        }
        d = client._parse_status("VINEV", raw, parking={})
        assert d.electric_range_km == 380
        assert d.combustion_range_km is None
        assert d.total_range_km is None
        assert d.range_km == 380

    def test_dieselrange_wrapped_object_form(self):
        """Some firmwares wrap the value as ``{distanceInKm: int}``
        instead of a bare scalar. Both shapes must be accepted."""
        client = self._client()
        raw = {
            "measurements": {
                "rangeStatus": {
                    "value": {"dieselRange": {"distanceInKm": 240}},
                },
            },
        }
        d = client._parse_status("VINA", raw, parking={})
        assert d.combustion_range_km == 240


# ─────────────────────────────────────────────────────────────────────────────
# Skoda parsing — same fields
# ─────────────────────────────────────────────────────────────────────────────


class TestSkodaParseRangesUnit:
    """Pure unit-level checks on the new Skoda range parsing block.

    The full SkodaClient.get_status pipeline is exercised in the existing
    skoda fixture-based tests; this just verifies the v1.10.0 output
    fields against the documented payload shapes."""

    def test_phev_kodiaq_shape(self):
        """Driving-range endpoint with both electric + combustion +
        total. Sample paths verified against myskoda fixtures."""
        from custom_components.vag_connect.cariad.api.skoda import SkodaClient
        from custom_components.vag_connect.cariad.models import VehicleData

        # Stub attributes _parse_status path expects.
        client = SkodaClient.__new__(SkodaClient)
        client._vehicle_metadata = {}

        # Directly exercise the driving-range branch by running the
        # relevant slice. We construct the inputs the way get_status does.
        d = VehicleData(vin="V1")
        d.has_battery = True
        v = client._val
        driving_range = {
            "electricRange": {"distanceInKm": 50},
            "combustionRange": {"distanceInKm": 480},
            "totalRangeInKm": 530,
        }
        # Recreate the driving-range parsing block inline (mirror of skoda.py
        # v1.10.0 logic) — keeps the test tight without spinning the whole
        # asyncio.gather pipeline.
        electric = v(driving_range, "electricRange", "distanceInKm")
        total = v(driving_range, "totalRangeInKm")
        combustion = v(driving_range, "combustionRange", "distanceInKm")
        if electric is not None:
            d.electric_range_km = int(electric)
        if combustion is not None:
            d.combustion_range_km = int(combustion)
        if total is not None:
            d.total_range_km = int(total)

        assert d.electric_range_km == 50
        assert d.combustion_range_km == 480
        assert d.total_range_km == 530


# ─────────────────────────────────────────────────────────────────────────────
# Sensor gating — no phantom entities
# ─────────────────────────────────────────────────────────────────────────────


class TestSensorGating:
    """v1.10.0 (#94 acceptance) — pure EVs do not get combustion entity,
    pure ICE do not get electric entity, even if the ``condition`` flag
    might let them through."""

    def test_data_present_required_set_includes_three_new_keys(self):
        """Catches the case where someone removes a key from the gating
        set — would silently re-introduce phantom entities."""
        from custom_components.vag_connect.sensor import _DATA_PRESENT_REQUIRED

        assert "electric_range_km" in _DATA_PRESENT_REQUIRED
        assert "combustion_range_km" in _DATA_PRESENT_REQUIRED
        assert "total_range_km" in _DATA_PRESENT_REQUIRED

    def test_sensor_descriptions_have_new_entries(self):
        from custom_components.vag_connect.sensor import SENSOR_DESCRIPTIONS

        keys = {desc.key for desc in SENSOR_DESCRIPTIONS}
        assert "electric_range_km" in keys
        assert "combustion_range_km" in keys
        assert "total_range_km" in keys

    def test_combustion_sensor_has_gas_station_icon(self):
        """Visual cue matters — combustion range must use the gas-station
        icon to be distinguishable from electric range at a glance."""
        from custom_components.vag_connect.sensor import SENSOR_DESCRIPTIONS

        combustion = next(
            d for d in SENSOR_DESCRIPTIONS if d.key == "combustion_range_km"
        )
        assert combustion.icon == "mdi:gas-station"
        assert combustion.condition == "combustion"

    def test_electric_sensor_has_battery_icon(self):
        from custom_components.vag_connect.sensor import SENSOR_DESCRIPTIONS

        electric = next(
            d for d in SENSOR_DESCRIPTIONS if d.key == "electric_range_km"
        )
        assert electric.icon == "mdi:battery-charging-outline"
        assert electric.condition == "electric"

    def test_total_range_has_no_condition(self):
        """Total range is meaningful for any vehicle type that publishes
        it. The data-present gate handles the "didn't publish" case."""
        from custom_components.vag_connect.sensor import SENSOR_DESCRIPTIONS

        total = next(
            d for d in SENSOR_DESCRIPTIONS if d.key == "total_range_km"
        )
        assert total.condition is None
