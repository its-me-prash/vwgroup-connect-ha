# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#1286 — the Škoda official public-API key is a credential and MUST be redacted.

It leaked in PLAINTEXT in the diagnostics download users attach to public issues
(a real ``msk_…`` key was exposed): neither the single manual key
(``skoda_official_api_key``) nor the auto-enrolled per-VIN map
(``skoda_official_keys``, ``{VIN: {key, id, validUntil}}``) was in the redaction set.
"""
from __future__ import annotations

from custom_components.vag_connect.diagnostics import _scrub

_SECRET = "msk_409c1f3c3928_zzSECRETzz"
_VIN = "TMBJJ7NE9L0123456"


def test_single_manual_official_key_is_redacted():
    out = _scrub({"skoda_official_api_key": _SECRET})
    assert out["skoda_official_api_key"] == "**REDACTED**"
    assert "SECRET" not in repr(out)


def test_per_vin_official_key_map_masks_records_keeps_count():
    data = {
        "skoda_official_keys": {
            _VIN: {"key": _SECRET, "id": "id1", "validUntil": "2027-03-01"},
        }
    }
    out = _scrub(data)
    m = out["skoda_official_keys"]
    # one enrolled VIN still visible as a count, but the record (incl. the key) gone
    assert len(m) == 1
    assert list(m.values()) == ["**REDACTED**"]
    assert "SECRET" not in repr(out)
    assert "id1" not in repr(out)


def test_no_official_secret_survives_a_full_entry_scrub():
    entry_data = {
        "brand": "skoda",
        "skoda_official_api_key": _SECRET,
        "skoda_official_keys": {_VIN: {"key": _SECRET + "2", "id": "i", "validUntil": "x"}},
        "scan_interval": 10,
    }
    out = _scrub(dict(entry_data))
    assert "SECRET" not in repr(out)
    assert out["scan_interval"] == 10          # non-secret fields untouched
    assert out["brand"] == "skoda"


def test_empty_official_key_stays_visibly_empty():
    # an unset key must not read as a fake redaction (triage needs the truth)
    out = _scrub({"skoda_official_api_key": ""})
    assert out["skoda_official_api_key"] == ""
