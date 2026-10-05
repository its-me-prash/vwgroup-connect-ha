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

import pytest

from custom_components.vag_connect.config_flow import (
    VagConnectConfigFlow,
    _is_grant_retired,
)
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


@pytest.mark.parametrize(
    "msg",
    [
        "Device grant: /device_authorization HTTP 403 (unauthorized_client)",
        "client is not allowed to use the device_code grant",
        # Audi and Porsche send different halves of this message, so both
        # substrings are load-bearing; neither may be dropped.
        'HTTP 403: {"error":"unauthorized_client"}',
        "UNAUTHORIZED_CLIENT",
    ],
)
def test_a_retired_grant_rejection_is_recognised(msg: str) -> None:
    """Calls the PRODUCTION classifier.

    The previous version of this test copied the two substring checks into its
    own body and asserted on the copy, with an ``if`` around the state change —
    so it could not fail no matter what the real rule did. That is why the rule
    now lives in ``_is_grant_retired`` instead of inline in the Phase-1 except.
    """
    assert _is_grant_retired(ValueError(msg)) is True


@pytest.mark.parametrize(
    "msg",
    [
        "Device grant: /device_authorization HTTP 503",
        "Device grant: /device_authorization request failed (TimeoutError)",
        "invalid_grant",
        "",
    ],
)
def test_an_ordinary_failure_is_not_mistaken_for_a_retired_grant(msg: str) -> None:
    """The negative half, which the old test had none of. A 503 or a timeout is
    an outage: flagging it as retired would tell the user their brand's login is
    permanently gone because VW had a bad minute."""
    assert _is_grant_retired(ValueError(msg)) is False


@pytest.mark.parametrize(
    ("message", "expected_flag"),
    [
        ("boom: unauthorized_client", True),
        ("client is not allowed to use the device_code grant", True),
        ("HTTP 503 upstream unavailable", False),
    ],
)
def test_phase_one_sets_the_flag_from_the_real_failure(
    monkeypatch: pytest.MonkeyPatch, message: str, expected_flag: bool
) -> None:
    """Drives the real Phase-1 handler and checks the FLAG, not the source text.

    A source-text assertion cannot carry this: the first version of this test
    asserted that ``_is_grant_retired(err)`` appears in the handler, and
    ``if False and _is_grant_retired(err):`` satisfies that while disabling the
    behaviour entirely — proven by mutating it, where all eleven tests stayed
    green. So the failure is injected at the first statement inside the
    handler's ``try`` and the resulting flag is read.
    """
    import aiohttp

    def _boom(*_a: object, **_k: object) -> None:
        raise ValueError(message)

    monkeypatch.setattr(aiohttp, "TCPConnector", _boom)

    flow = _flow()
    flow._dag_brand = "audi"
    flow._dag_mbb = False
    assert flow._dag_grant_disabled is False, "precondition"

    asyncio.run(flow._do_request_device_code())

    assert flow._dag_grant_disabled is expected_flag
    # The handler must swallow it into _dag_error either way, not propagate.
    assert flow._dag_error is not None and message in flow._dag_error
