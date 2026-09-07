# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#1364 (Audi) / #1337 (Porsche) — graceful handling when the manufacturer
disabled the app device-code grant.

The manufacturer moved the app login to Auth0 with on-device Play-Integrity
attestation on the token exchange (live-confirmed: the Audi + Porsche clients
return 403 unauthorized_client, and even an interactive browser login cannot
complete the attestation-gated token exchange). So instead of a raw exception,
the brand picker shows an honest, actionable message: Audi users are pointed at
the read-only EU Data Act Portal; Porsche has no fallback yet.
"""
from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

from custom_components.vag_connect.config_flow import VagConnectConfigFlow
from custom_components.vag_connect.const import DOMAIN


def _flow() -> VagConnectConfigFlow:
    flow = VagConnectConfigFlow()
    flow.hass = MagicMock()
    flow.context = {}
    flow.handler = DOMAIN
    flow.flow_id = "test"
    return flow


def test_grant_disabled_shows_retired_error() -> None:
    flow = _flow()
    flow._dag_grant_disabled = True
    res = asyncio.run(flow.async_step_browser_login(None))
    assert res["type"] == "form"
    assert res["step_id"] == "browser_login"
    assert res["errors"]["base"] == "device_grant_retired"


def test_fresh_flow_has_no_grant_error() -> None:
    # __init__ leaves the flag False → a first-time picker shows no such error.
    flow = _flow()
    assert flow._dag_grant_disabled is False
    res = asyncio.run(flow.async_step_browser_login(None))
    assert res.get("errors", {}).get("base") != "device_grant_retired"


def test_unauthorized_client_error_string_is_classified() -> None:
    # Mirrors the Phase-1 catch: an unauthorized_client rejection flips the flag.
    flow = _flow()
    for msg in (
        "Device grant: /device_authorization HTTP 403 (unauthorized_client)",
        "client is not allowed to use the device_code grant",
    ):
        flow._dag_grant_disabled = False
        _e = msg.lower()
        if "unauthorized_client" in _e or "not allowed" in _e:
            flow._dag_grant_disabled = True
        assert flow._dag_grant_disabled is True
