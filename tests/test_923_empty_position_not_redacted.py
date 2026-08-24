# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#923 (@naked-head) — an EMPTY redacted field must stay visibly empty.

The diagnostics redactor masks by key name: ``latitude``/``longitude``/
``parking_address`` (and every ``_REDACT_KEYS`` member) were replaced with
``**REDACTED**`` regardless of whether they held a value. That makes an empty
coordinate indistinguishable from a real-but-hidden one, so triage cannot tell
"the car never produced a position" from "the position is present but redacted".
@naked-head caught this on three cohort exports whose position was genuinely
empty (no ``field_sources`` entry, ``position_captured_at = None``) yet showed
``latitude = **REDACTED**``.

Fix: only mask when there is actually a value to hide; empties pass through so
``field_sources`` stays the honest signal.

Everything here is synthetic — never put a real coordinate in a test.
"""
from __future__ import annotations

from custom_components.vag_connect.diagnostics import _is_empty_value, _scrub


class TestEmptyPositionStaysEmpty:
    def test_empty_coordinates_are_not_faked_as_redacted(self):
        # naked-head's exact shape: no position anywhere in the payload.
        veh = {"latitude": None, "longitude": None, "parking_address": None,
               "position_captured_at": None, "parking_city": None}
        out = _scrub(dict(veh), gps_round=False)
        assert out["latitude"] is None
        assert out["longitude"] is None
        assert out["parking_address"] is None
        # unchanged companions confirm the empty picture is coherent
        assert out["position_captured_at"] is None

    def test_empty_string_coordinate_stays_empty(self):
        out = _scrub({"latitude": "", "parking_address": ""}, gps_round=False)
        assert out["latitude"] == ""
        assert out["parking_address"] == ""


class TestRealPositionStillRedacted:
    def test_real_coordinate_redacted_by_default(self):
        # privacy-by-default: a real value is still hidden
        out = _scrub({"latitude": 48.137, "longitude": 11.575}, gps_round=False)
        assert out["latitude"] == "**REDACTED**"
        assert out["longitude"] == "**REDACTED**"

    def test_real_coordinate_rounded_when_opted_in(self):
        out = _scrub({"latitude": 48.137, "longitude": 11.575}, gps_round=True)
        assert out["latitude"] == 48.1
        assert out["longitude"] == 11.6

    def test_real_parking_address_still_redacted(self):
        out = _scrub({"parking_address": "Somestreet 1, City"}, gps_round=False)
        assert out["parking_address"] == "**REDACTED**"


class TestRedactKeysPreserveEmpties:
    def test_empty_secret_is_visibly_empty_but_present_secret_is_masked(self):
        out = _scrub({"password": "", "spin": "SYNTHETIC"}, gps_round=False)
        assert out["password"] == ""          # nothing to hide → truthful
        assert out["spin"] == "**REDACTED**"  # real value → masked

    def test_empty_container_secret_stays_empty(self):
        # e.g. a stored-tokens dict that was never populated
        out = _scrub({"vweu_twoway_tokens": {}}, gps_round=False)
        assert out["vweu_twoway_tokens"] == {}


class TestIsEmptyValueHelper:
    def test_empties(self):
        for v in (None, "", [], {}):
            assert _is_empty_value(v) is True

    def test_real_values_including_zero_and_false(self):
        # 0 / False are real values, not "empty" — they still hit redaction
        for v in (0, False, "x", [1], {"a": 1}, 48.1):
            assert _is_empty_value(v) is False
