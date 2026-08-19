# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#923 / #1222 — the EU-Data-Act identifier map must not leak in diagnostics.

`data_act_identifiers` is keyed by VIN: `{VIN: {identifier: ...}}`. v3.0.1 masked
the VIN used as the *key*, but the identifier VALUE next to it stayed clear-text,
because the recursive string scrubber only runs the email/GPS regexes over string
values, not the VIN/JWT ones. So a per-VIN portal identifier still went out in
plaintext in the download users attach to public GitHub issues. It is now redacted
whole, exactly like the {VIN: S-PIN} map. Reported by @ggfbrkt6mc-max.

Everything here is synthetic — never put a real VIN or identifier in a test.
"""
from __future__ import annotations

from custom_components.vag_connect.diagnostics import _scrub, _scrub_raw

# Real shape: {VIN: "<portal Custom-Data-Request identifier string>"}.
_ENTRY_DATA = {
    "brand": "volkswagen",
    "data_act_identifiers": {
        "WVWZZZSYNTHET0003": "SYNTHETIC_DATAACT_IDENTIFIER",
        "WVWZZZSYNTHET0004": "SYNTHETIC_DATAACT_IDENTIFIER_2",
    },
}


def _dump() -> str:
    return repr(_scrub(dict(_ENTRY_DATA), gps_round=False))


def test_1222_identifier_value_not_leaked() -> None:
    dump = _dump()
    assert "SYNTHETIC_DATAACT_IDENTIFIER" not in dump
    assert "SYNTHETIC_DATAACT_IDENTIFIER_2" not in dump


def test_1222_vin_key_not_leaked() -> None:
    # The VIN is the map key — a value-only redaction would not be enough.
    dump = _dump()
    assert "WVWZZZSYNTHET0003" not in dump
    assert "WVWZZZSYNTHET0004" not in dump


def test_1222_container_survives_with_entry_count() -> None:
    # Redaction keeps the map shape so the enrolment count stays useful.
    out = _scrub(dict(_ENTRY_DATA), gps_round=False)
    assert "data_act_identifiers" in out
    assert len(out["data_act_identifiers"]) == 2
    assert all(v == "**REDACTED**" for v in out["data_act_identifiers"].values())


def test_1222_same_leak_closed_on_raw_path() -> None:
    raw = {"data_act_identifiers": {"WVWZZZSYNTHET0003": "SYNTHETIC_DATAACT_IDENTIFIER"}}
    dump = repr(_scrub_raw(raw))
    assert "SYNTHETIC_DATAACT_IDENTIFIER" not in dump
    assert "WVWZZZSYNTHET0003" not in dump


def test_1222_brand_still_reported() -> None:
    # Redaction must not gut the useful half of the dump.
    assert "volkswagen" in _dump()
