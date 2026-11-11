# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#923 — the registered MBB X-Client-Id and the EU-Data-Act ZIP-envelope
dataset key are opaque UUID identifiers with no triage value in a shared
diagnostics file. They are not credential-NAMED, so the completeness guard in
test_923_diagnostics_redaction_completeness.py does not catch them; this file
pins their by-hand redaction so a refactor of _REDACT_KEYS cannot drop them.
"""
from __future__ import annotations

import pytest

from custom_components.vag_connect.diagnostics import _REDACT_KEYS, _scrub


@pytest.mark.parametrize("key", ["mbb_command_client_id", "dataset_key"])
def test_identifier_is_in_the_redact_list(key: str) -> None:
    assert key in _REDACT_KEYS


@pytest.mark.parametrize("key", ["mbb_command_client_id", "dataset_key"])
def test_identifier_does_not_survive_a_scrub(key: str) -> None:
    secret = "0718582b-1f44-781f-85fb-dac0c600e6a7"
    out = _scrub({key: secret}, gps_round=False)
    assert out[key] == "**REDACTED**"
    assert secret not in __import__("json").dumps(out)
