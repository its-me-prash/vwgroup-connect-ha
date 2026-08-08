# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""v3.0.0 — the raw brand API responses go into the diagnostics download so a
reporter's one-click "Download diagnostics" carries exactly what grounds a new
feature. That download gets attached to PUBLIC issues, so the raw redactor
(_scrub_raw) must let NOTHING sensitive through. These tests are the safety net.

Everything here is synthetic — never put a real VIN / token / GPS in a test.
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock

from custom_components.vag_connect.diagnostics import _scrub_raw

# A deliberately nasty raw payload: every kind of PII a brand backend can ship,
# under the unpredictable camelCase keys a raw response actually uses.
_RAW = {
    "vin": "WVWZZZSYNTHET0001",
    "vehicleId": "WVWZZZSYNTHET0002",
    "userId": "user-abc-999",
    "gpsCoordinates": {"latitude": 48.137, "longitude": 11.575},
    "parkingPosition": {"latitude": 52.531, "longitude": 13.384, "address": "Beispielstr 7"},
    "licencePlate": "M-AB 1234",
    "city": "Munich",
    "owner": {
        "firstName": "SynthFirst", "lastName": "SynthLast",
        "email": "synth@example.com", "phone": "+41 79 000 0000",
        "nickname": "MyCarNick",
    },
    "authToken": "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U",
    "profileUuid": "0a18a053-1234-4abc-8def-0123456789ab",
    "note": "car WVWZZZSYNTHET0001 last seen at https://x/pos?latitude=48.1&longitude=11.5",
    # non-PII that MUST survive — this is what grounds a new feature
    "batteryStatus": {"currentSOCPercent": 72, "cruisingRangeKm": 310},
    "chargingState": "readyForCharging",
    "profileId": 1,
    "modes": ["MANUAL", "AUTOMATIC"],
}

_SECRETS = [
    "WVWZZZSYNTHET0001", "WVWZZZSYNTHET0002", "user-abc-999",
    "48.137", "11.575", "52.531", "13.384", "Beispielstr", "M-AB 1234",
    "Munich", "SynthFirst", "SynthLast", "synth@example.com", "+41 79",
    "MyCarNick", "eyJhbGci", "0a18a053", "48.1", "11.5",
]


def _dump() -> str:
    return json.dumps(_scrub_raw(_RAW), ensure_ascii=False)


def test_no_pii_survives_the_raw_scrub() -> None:
    dump = _dump()
    for secret in _SECRETS:
        assert secret not in dump, f"{secret!r} leaked into the raw diagnostics"


def test_grounding_structure_and_samples_are_kept() -> None:
    out = _scrub_raw(_RAW)
    # field NAMES kept (the primary grounding signal)
    assert "batteryStatus" in out and "chargingState" in out and "modes" in out
    # non-PII sample VALUES kept
    assert out["batteryStatus"]["currentSOCPercent"] == 72
    assert out["batteryStatus"]["cruisingRangeKm"] == 310
    assert out["chargingState"] == "readyForCharging"
    assert out["profileId"] == 1  # harmless id kept (bare "id" not redacted)
    assert out["modes"] == ["MANUAL", "AUTOMATIC"]


def test_ids_masked_inside_nested_lists_and_free_text() -> None:
    out = _scrub_raw({"events": [{"msg": "vin WVWZZZSYNTHET0001 woke"}]})
    assert "WVWZZZSYNTHET0001" not in json.dumps(out)


def test_scrub_raw_is_none_safe() -> None:
    assert _scrub_raw(None) is None
    assert _scrub_raw({}) == {}
    assert _scrub_raw([]) == []


def test_vwna_client_has_raw_responses_bucket() -> None:
    from custom_components.vag_connect.cariad.api.vw_na import VWNAClient

    c = VWNAClient(MagicMock(), "synth@example.com", "pw")
    assert c.last_raw_responses == {}


def test_diagnostics_source_wires_raw_responses() -> None:
    from pathlib import Path

    src = (
        Path(__file__).resolve().parents[1]
        / "custom_components/vag_connect/diagnostics.py"
    ).read_text(encoding="utf-8")
    assert '"raw_responses": raw_responses' in src
    assert "_scrub_raw(payload)" in src


def test_vwde_authproxy_captures_raw_with_vin_stripped_from_key() -> None:
    # #923 / #966 — the vw.de channel returns early from get_status, so it must
    # capture its own raw responses; the KEY must not leak the VIN.
    from custom_components.vag_connect.cariad.auth._website_authproxy import (
        WebsiteAuthProxyConnector,
    )

    c = WebsiteAuthProxyConnector.__new__(WebsiteAuthProxyConnector)
    c.last_raw_responses = {}
    c._capture_raw(
        "https://x/api/vehicles/WVWZZZSYNTHET0001/warninglights/last?foo=1",
        {"warningLights": []},
    )
    assert list(c.last_raw_responses) == ["vwde:warninglights/last"]
    assert "WVWZZZSYNTHET0001" not in " ".join(c.last_raw_responses)
    # and the body itself is redacted at export time
    out = _scrub_raw({"vin": "WVWZZZSYNTHET0001", "position": {"latitude": 48.1}})
    assert "WVWZZZSYNTHET0001" not in json.dumps(out) and "48.1" not in json.dumps(out)


def test_vw_eu_surfaces_website_raw_responses() -> None:
    from pathlib import Path

    src = (
        Path(__file__).resolve().parents[1]
        / "custom_components/vag_connect/cariad/api/vw_eu.py"
    ).read_text(encoding="utf-8")
    # the early-return vw.de path must copy the connector's raw responses out
    assert "self.last_raw_responses = dict(getattr(web," in src


def test_porsche_client_has_raw_responses_bucket() -> None:
    from custom_components.vag_connect.cariad.api.porsche import PorscheClient

    c = PorscheClient(MagicMock(), "synth@example.com", "pw")
    assert c.last_raw_responses == {}


def test_scout_raw_capture_wired_across_all_brands() -> None:
    # Coverage guard: every active brand/market must surface raw API responses
    # so the Scout can ground new fields. Standalone clients populate
    # last_raw_responses directly; the others inherit a capturing get_status.
    from pathlib import Path

    api = (
        Path(__file__).resolve().parents[1] / "custom_components/vag_connect/cariad/api"
    )
    for brand in ("skoda", "seat_cupra", "vw_eu", "vw_na", "porsche"):
        src = (api / f"{brand}.py").read_text(encoding="utf-8")
        assert "last_raw_responses" in src, f"{brand} lacks raw-response capture"
    # audi / bentley / lambo inherit VWEUClient's capturing get_status; audi_na
    # (US/CA) delegates to it explicitly; cupra_standalone inherits SeatCupra.
    assert "super().get_status" in (api / "audi_na.py").read_text(encoding="utf-8")
    for inheritor, parent in (
        ("audi", "VWEUClient"), ("bentley", "VWEUClient"), ("lambo", "VWEUClient"),
        ("cupra_standalone", "SeatCupraClient"),
    ):
        src = (api / f"{inheritor}.py").read_text(encoding="utf-8")
        assert parent in src, f"{inheritor} no longer inherits {parent}"
