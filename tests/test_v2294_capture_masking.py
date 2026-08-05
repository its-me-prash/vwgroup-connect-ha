# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""v2.29.x — scripts/vwna_capture.py masking guarantees.

The capture script asks a real owner to paste its output into a public issue, so
the masking is a privacy promise, not a nicety. The original value-shape rules
decided on what a value LOOKED like, which was fine while the script only read
ev/rvs telemetry but not once the hidden-surface pass added message-center,
charging-session, trip and address payloads: a plate (ZH123456), a city
(ZURICH) or a first name (PRASH) looks exactly like an enum and printed
verbatim. Error bodies were printed raw and a con-veh error body can carry the
VIN, the vehicle UUID or the userId.

These tests pin the hardened behaviour so a future probe cannot quietly
reintroduce a leak.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "vwna_capture.py"


def _load():
    spec = importlib.util.spec_from_file_location("vwna_capture", _SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


cap = _load()


class TestKeyDrivenMasking:
    """A key name alone can make its value unsafe, whatever the value looks like."""

    def test_ids_masked(self):
        out = cap._shape({"userId": "PRASH123", "vehicleId": "abc", "sessionId": "S1"})
        assert out == {"userId": "<id>", "vehicleId": "<id>", "sessionId": "<id>"}

    def test_gps_masked_even_as_string(self):
        out = cap._shape({"latitude": "47.37", "longitude": 8.54, "heading": "N"})
        assert out == {"latitude": "<gps>", "longitude": "<gps>", "heading": "<gps>"}

    def test_secrets_redacted(self):
        out = cap._shape({"idToken": "x", "spinHash": "y", "encryptedSignature": "z"})
        assert out == {
            "idToken": "<redacted>",
            "spinHash": "<redacted>",
            "encryptedSignature": "<redacted>",
        }

    def test_personal_masked(self):
        out = cap._shape({
            "city": "ZURICH", "licensePlate": "ZH123456", "firstName": "PRASH",
            "subject": "Your alarm triggered", "operatorName": "IONITY",
        })
        assert set(out.values()) == {"<personal>"}

    def test_country_and_unit_kept(self):
        # a 2-char country code is a useful enum and carries no PII
        out = cap._shape({"country": "US", "unit": "KM", "locale": "en-US"})
        assert out["country"] == "US"
        assert out["unit"] == "KM"


class TestValueMasking:
    def test_vin_masked(self):
        assert cap._shape("WVWZZZ1KZAW000503") == "<VIN>"

    def test_jwt_redacted(self):
        jwt = "eyJhbGciOiJub25l.eyJleHAiOjE3MDAwMDAwMDB9.sig"
        assert cap._shape(jwt) == "<redacted>"

    def test_timestamp_classified_not_revealed(self):
        assert cap._shape("2026-08-05T14:30:00Z") == "<iso8601>"

    def test_numbers_masked(self):
        assert cap._shape({"odometer": 123456}) == {"odometer": "<num>"}

    def test_enum_kept_in_normal_mode(self):
        assert cap._shape("USER_NOT_AUTHORIZED") == "USER_NOT_AUTHORIZED"


class TestStrictMode:
    """Payloads that can carry arbitrary personal prose get no passthroughs."""

    def test_strict_drops_enum_passthrough(self):
        assert cap._shape("ZURICH", strict=True) == "<str:6>"
        assert cap._shape("PRASH", strict=True) == "<str:5>"

    def test_strict_drops_short_string_passthrough(self):
        assert cap._shape("ZH", strict=True) == "<str:2>"

    def test_strict_keeps_structure_and_types(self):
        out = cap._shape({"a": {"b": ["TEXT", "TEXT2"]}, "n": 1, "ok": True},
                         strict=True)
        assert out == {"a": {"b": ["<str:4>", "…(+1)"]}, "n": "<num>", "ok": True}


class TestErrorBodyNeverRaw:
    """The single worst leak: error bodies were printed verbatim."""

    class _Err(Exception):
        def __init__(self, status, body):
            super().__init__("x")
            self.status = status
            self.body = body

    def test_json_body_is_shaped_not_raw(self):
        body = json.dumps({"error": {"errorCode": "USER_NOT_AUTHORIZED",
                                     "vin": "WVWZZZ1KZAW000503",
                                     "userId": "1234-5678"}})
        line = cap._safe_error_line(self._Err(403, body))
        assert "WVWZZZ1KZAW000503" not in line
        assert "1234-5678" not in line
        assert "USER_NOT_AUTHORIZED" in line   # the diagnostic value survives
        assert "status=403" in line

    def test_non_json_body_yields_codes_and_length_only(self):
        body = "Forbidden for VIN WVWZZZ1KZAW000503 user prash@example.com"
        line = cap._safe_error_line(self._Err(403, body))
        assert "WVWZZZ1KZAW000503" not in line
        assert "prash@example.com" not in line
        assert "len=" in line

    def test_empty_body(self):
        assert cap._safe_error_line(self._Err(404, "")) == "status=404"


class TestProbeSafety:
    """The script must stay read-only, and the mutating trigger opt-in."""

    def test_no_denied_endpoint_is_probed(self):
        src = _SCRIPT.read_text(encoding="utf-8")
        # everything after the safety block: never probe these
        denied = (
            "/estore/", "/pair/v1/", "pairing/password", "pairing/reset",
            "wifiConnection/vehicle/{uuid}/reset", "/device/v1/event/analytic",
            "/devicestatistics/", "session/start", "/stop",
            "garage/adjust", "valetMode", "/notification/{", "provideFeedback",
            "documents/ingest",
        )
        # only look at actual probe call sites, not the safety comment block
        probe_lines = [ln for ln in src.splitlines()
                       if "_probe(client," in ln or ('f"{B}/' in ln and "await" not in ln)]
        joined = "\n".join(probe_lines)
        for bad in denied:
            assert bad not in joined, f"probe hits denied endpoint {bad!r}"

    def test_health_trigger_is_opt_in(self):
        src = _SCRIPT.read_text(encoding="utf-8")
        assert "--probe-health" in src
        assert "if probe_health:" in src
        # and it defaults to off
        assert "probe_health: bool = False" in src

    def test_tos_is_get_status_only_never_post(self):
        src = _SCRIPT.read_text(encoding="utf-8")
        assert "enrollment/toses" in src
        # the script has no POST helper at all
        assert "_post(" not in src


@pytest.mark.parametrize("probe_label", [
    "messagecenter inbox", "charging sessions (history)",
    "charging session (active)", "trip v1", "trip v2",
    "destination (send-to-car resource)", "mdk summary",
    "location (dedicated)", "activity feed",
])
def test_pii_bearing_probes_use_strict(probe_label: str):
    """Probes whose payload can carry prose/addresses must run strict."""
    src = _SCRIPT.read_text(encoding="utf-8")
    idx = src.index(f'"{probe_label}"')
    # the strict flag must appear within the same call (next ~200 chars)
    assert "strict=True" in src[idx:idx + 220], (
        f"{probe_label} must be captured with strict=True"
    )
