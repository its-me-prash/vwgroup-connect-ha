# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""VW EU Two-Way — the stored login password/email/token/cookies must NEVER
appear in a diagnostics download (the file users routinely attach to GitHub
issues). This pins the redaction so a future refactor cannot re-leak them.
"""
from __future__ import annotations

import json

from custom_components.vag_connect.const import (
    CONF_VWEU_TWOWAY_COOKIES,
    CONF_VWEU_TWOWAY_EMAIL,
    CONF_VWEU_TWOWAY_PASSWORD,
    CONF_VWEU_TWOWAY_TOKENS,
)
from custom_components.vag_connect.diagnostics import _scrub


def test_vweu_twoway_secrets_are_fully_redacted() -> None:
    data = {
        CONF_VWEU_TWOWAY_PASSWORD: "SuperSecret123",
        CONF_VWEU_TWOWAY_EMAIL: "driver@example.com",
        CONF_VWEU_TWOWAY_TOKENS: {
            "access_token": "eyJhbGciSECRETtoken",
            "refresh_token": "reftok",
            "strategy": "device_grant",
            "expires_at": 123.0,
        },
        CONF_VWEU_TWOWAY_COOKIES: [{"name": "idkit_p", "value": "cookieSECRET"}],
        "brand": "volkswagen",  # non-secret context stays
    }
    out = _scrub(data)

    assert out[CONF_VWEU_TWOWAY_PASSWORD] == "**REDACTED**"
    assert out[CONF_VWEU_TWOWAY_EMAIL] == "**REDACTED**"
    assert out[CONF_VWEU_TWOWAY_TOKENS] == "**REDACTED**"
    assert out[CONF_VWEU_TWOWAY_COOKIES] == "**REDACTED**"
    assert out["brand"] == "volkswagen"

    # No secret value survives ANYWHERE in the serialised diagnostics.
    blob = json.dumps(out)
    for secret in (
        "SuperSecret123", "eyJhbGciSECRETtoken", "reftok", "cookieSECRET",
        "driver@example.com",
    ):
        assert secret not in blob, secret
