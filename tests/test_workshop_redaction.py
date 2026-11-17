"""Preferred-workshop data (name, address, phone) must not reach diagnostics.

The flat sensor fields and the composite dict are our own names, handled by
``_REDACT_KEYS``. The wire containers (``preferredServicePartner`` and its two
siblings) are handled by ``_RAW_REDACT_KEYS``. All values here are invented.
"""
from __future__ import annotations

import json

import pytest

from custom_components.vag_connect.diagnostics import (
    _RAW_REDACT_KEYS,
    _scrub,
    _scrub_raw,
)

_NAME = "Testhaus Muster GmbH"
_ADDR = "Musterweg 1, 00000 Testdorf"
_PHONE = "+49 000 0000000"
_FLAT = {
    "preferred_workshop_name": _NAME,
    "preferred_workshop_address": _ADDR,
    "preferred_workshop_phone": _PHONE,
}


@pytest.mark.parametrize("gps_round", [False, True])
def test_flat_workshop_fields_are_redacted(gps_round):
    out = _scrub(dict(_FLAT), gps_round=gps_round)
    blob = json.dumps(out)
    for secret in (_NAME, _ADDR, _PHONE):
        assert secret not in blob
    assert all(v == "**REDACTED**" for v in out.values())


def test_composite_workshop_dict_is_redacted():
    out = _scrub({"preferred_workshop": {"name": _NAME, "id": "XX0"}}, gps_round=False)
    assert out["preferred_workshop"] == "**REDACTED**"
    assert _NAME not in json.dumps(out)


def test_empty_workshop_stays_visibly_empty():
    out = _scrub({"preferred_workshop_name": None, "preferred_workshop": None},
                 gps_round=False)
    assert out["preferred_workshop_name"] is None
    assert out["preferred_workshop"] is None


@pytest.mark.parametrize("key", [
    "preferredServicePartner", "servicePartner", "preferredWorkshop",
])
def test_raw_workshop_containers_are_redacted(key):
    assert key.lower() in _RAW_REDACT_KEYS
    out = _scrub_raw({"maintenance": {key: {"name": _NAME, "id": "XX0"}}})
    assert out["maintenance"][key] == "**REDACTED**"
    assert _NAME not in json.dumps(out)


def test_raw_flat_fields_are_redacted():
    out = _scrub_raw(dict(_FLAT))
    assert _NAME not in json.dumps(out) and _PHONE not in json.dumps(out)


def test_sensors_still_read_the_flat_fields():
    """Redaction is diagnostics-only: the sensor descriptions keep their data keys."""
    from custom_components.vag_connect import sensor

    keys = {getattr(d, "data_key", None) for d in sensor.SENSOR_DESCRIPTIONS}
    assert set(_FLAT) <= keys
