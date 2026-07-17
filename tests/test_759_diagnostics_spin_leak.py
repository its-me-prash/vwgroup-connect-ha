# Copyright 2026 Prash Balan (@its-me-prash) - Apache License 2.0
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Per-VIN S-PIN + ABRP credentials must never reach a diagnostics download.

The per-VIN S-PIN map (#759, shipped 2.17.5) is a `{VIN: S-PIN}` dict. It was
not in `_REDACT_KEYS`, so it fell through to the generic dict branch and got
walked: the diagnostics export carried a real VIN as the key and the S-PIN as
a plaintext value. The shared `spin` was redacted the whole time, which is what
made this easy to miss. The two ABRP credentials leaked the same way, despite
the options help text promising "Never logged".

Diagnostics downloads get attached to public issues, so these assertions guard
a live disclosure path, not a cosmetic one.

Everything here is synthetic — never put a real VIN or S-PIN in a test.
"""
from __future__ import annotations

from custom_components.vag_connect.diagnostics import _scrub

# The exact shape the options update-listener guarantees in `entry.data`
# (__init__.py folds options into data and blanks entry.options).
_ENTRY_DATA = {
    "brand": "volkswagen",
    "username": "someone@example.com",
    "password": "SYNTHETIC_PW",
    "spin": "SYNTHETIC_SHARED_SPIN",
    "spin_by_vin": {
        "WVWZZZSYNTHETIC001": "9999",
        "WVWZZZSYNTHETIC002": "1234",
    },
    "abrp_api_key": "SYNTHETIC_ABRP_KEY",
    "abrp_user_token": "SYNTHETIC_ABRP_TOKEN",
}


def _dump() -> str:
    return repr(_scrub(dict(_ENTRY_DATA), gps_round=False))


def test_759_per_vin_spin_value_not_leaked() -> None:
    assert "9999" not in _dump()
    assert "1234" not in _dump()


def test_759_vin_not_leaked_as_dict_key() -> None:
    # The VIN is the *key* of the map, so a value-only redaction isn't enough.
    assert "WVWZZZSYNTHETIC001" not in _dump()


def test_759_abrp_credentials_not_leaked() -> None:
    dump = _dump()
    assert "SYNTHETIC_ABRP_KEY" not in dump
    assert "SYNTHETIC_ABRP_TOKEN" not in dump


def test_759_shared_spin_still_redacted() -> None:
    # No regression on what already worked.
    assert "SYNTHETIC_SHARED_SPIN" not in _dump()


def test_759_nothing_sensitive_survives_scrub() -> None:
    dump = _dump()
    for secret in (
        "SYNTHETIC_PW",
        "SYNTHETIC_SHARED_SPIN",
        "SYNTHETIC_ABRP_KEY",
        "SYNTHETIC_ABRP_TOKEN",
        "9999",
        "1234",
        "WVWZZZSYNTHETIC001",
        "WVWZZZSYNTHETIC002",
    ):
        assert secret not in dump, f"{secret} leaked into diagnostics"


def test_759_brand_still_reported() -> None:
    # Redaction must not gut the useful half of the dump.
    assert "volkswagen" in _dump()
