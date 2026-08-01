# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#1020 — HV-battery calibration notifications reach entities.

The car asks its owner to run a battery calibration (a full charge, sometimes
at a named AC rate), escalates twice if it is ignored, and reports whether an
attempt failed and why. Every one of these fields is named AND described in
VW's own data dictionary, so nothing about the meaning is inferred here.

Reported by a Scout run carrying seventeen fields, of which this family was the
genuinely new part.
"""
from __future__ import annotations

from custom_components.vag_connect.cariad.auth._eu_data_act import (
    map_dataset_to_vehicle_data,
)
from custom_components.vag_connect.cariad.models import VehicleData

_REPORTED = {
    "calibration_failure": "CALIBRATION_FAILURE_NONE",
    "calibration_failure_reason": "CALIBRATION_FAILURE_REASON_EVERYTHING_FINE",
    "calibration_need_detected": "CALIBRATION_NEED_DETECTED_NONE",
    "calibration_request_method": "CALIBRATION_REQ_METHOD_NONE",
    "calibration_requests.calibration_request_escalation_1": "CALIBRATION_REQUEST_NONE",
    "calibration_requests.calibration_request_escalation_2": "CALIBRATION_REQUEST_NONE",
    "calibration_requests.calibration_request_initial": "CALIBRATION_REQUEST_NONE",
}

_ATTRS = (
    "calibration_failure",
    "calibration_failure_reason",
    "calibration_need_detected",
    "calibration_request_method",
    "calibration_request_initial",
    "calibration_request_escalation_1",
    "calibration_request_escalation_2",
)


def _map(fields: dict[str, str]) -> VehicleData:
    return map_dataset_to_vehicle_data(dict(fields), VehicleData(vin="X"))


class TestCalibrationMapping:
    def test_every_reported_field_lands_on_the_model(self) -> None:
        d = _map(_REPORTED)
        for attr in _ATTRS:
            assert getattr(d, attr) is not None, f"{attr} was not mapped"

    def test_nothing_is_left_for_the_scout_to_re_report(self) -> None:
        """The whole point: a mapped field must stop coming back as new."""
        d = _map(_REPORTED)
        left = {k for k in (d.raw_unmapped_fields or set()) if "calibration" in k}
        assert left == set(), f"still unmapped: {sorted(left)}"

    def test_an_active_request_is_readable(self) -> None:
        d = _map({
            "calibration_need_detected": "CALIBRATION_NEED_DETECTED_ACTIVE",
            "calibration_requests.calibration_request_initial": "CALIBRATION_REQUEST_ACTIVE",
            "calibration_request_method": "CALIBRATION_REQ_METHOD_FULL_CHARGE_AC95",
        })
        assert "ACTIVE" in d.calibration_need_detected.upper()
        assert "ACTIVE" in d.calibration_request_initial.upper()
        assert "AC95" in d.calibration_request_method.upper()

    def test_bare_spelling_also_works(self) -> None:
        """Dialects that send the request keys without the container prefix."""
        d = _map({"calibration_request_initial": "CALIBRATION_REQUEST_ACK"})
        assert d.calibration_request_initial is not None

    def test_absent_fields_stay_none(self) -> None:
        d = _map({"battery_state_report.soc": "55"})
        for attr in _ATTRS:
            assert getattr(d, attr) is None


class TestEntitiesAndTranslations:
    def test_each_field_has_a_sensor(self) -> None:
        from custom_components.vag_connect.sensor import SENSOR_DESCRIPTIONS

        keys = {d.key for d in SENSOR_DESCRIPTIONS}
        for attr in _ATTRS:
            assert attr in keys, f"no sensor for {attr}"

    def test_every_locale_names_them(self) -> None:
        """A leaked English name in a translated locale is a real defect."""
        import json
        import pathlib

        base = (
            pathlib.Path(__file__).resolve().parents[1]
            / "custom_components/vag_connect/translations"
        )
        for path in sorted(base.glob("*.json")):
            data = json.loads(path.read_text(encoding="utf-8"))
            sensors = data.get("entity", {}).get("sensor", {})
            for attr in _ATTRS:
                assert attr in sensors, f"{path.name} missing {attr}"
                assert sensors[attr].get("name"), f"{path.name}:{attr} has no name"
