# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#1850 (@indigomejor) — the account lockout warning now names the endpoint.

The 430 hold pauses every request on the account, so the single WARNING a
reporter can paste after it was the only evidence of the lockout — and it named
the brand but not the call that tripped it. The open question on the thread is
exactly which endpoint returns the 430, so the rate-limited call can be found.

The line now carries the host+path, with the query, the VIN and any UUID
stripped by ``_redact_url`` first, because that path routinely carries the VIN.
"""
from __future__ import annotations

import asyncio
import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.vag_connect.cariad.api.vw_eu import VWEUClient
from custom_components.vag_connect.cariad.exceptions import APIError
from custom_components.vag_connect.cariad.models import TokenSet

_VIN = "WVWZZZAUZFW000000"
_URL = f"https://api.example.com/vehicles/{_VIN}/status?access_token=secret-xyz"


def _resp(status: int, text: str = "") -> AsyncMock:
    resp = AsyncMock()
    resp.status = status
    resp.headers = {"Content-Type": "application/json"}
    resp.json = AsyncMock(return_value={})
    resp.text = AsyncMock(return_value=text)
    resp.__aenter__ = AsyncMock(return_value=resp)
    resp.__aexit__ = AsyncMock(return_value=False)
    return resp


def _client_with(responses: list[AsyncMock]) -> VWEUClient:
    idx = {"i": 0}

    def side_effect(*_a: object, **_k: object) -> AsyncMock:
        r = responses[min(idx["i"], len(responses) - 1)]
        idx["i"] += 1
        return r

    session = MagicMock()
    session.request = MagicMock(side_effect=side_effect)
    client = VWEUClient(session, "u@t.de", "pw")
    client._tokens = TokenSet("acc", "ref", "id")
    return client


def _warning_from_430(caplog: pytest.LogCaptureFixture) -> str:
    """Drive a real request that gets a 430 and return the WARNING text."""
    client = _client_with([_resp(430, text="locked")])
    with patch(
        "custom_components.vag_connect.cariad.api.base.asyncio.sleep",
        new=AsyncMock(return_value=None),
    ), caplog.at_level(
        logging.WARNING, logger="custom_components.vag_connect.cariad.api.base"
    ), pytest.raises(APIError):
        asyncio.run(client._request("GET", _URL))
    return " ".join(r.getMessage() for r in caplog.records)


def test_the_430_lockout_warning_names_the_endpoint(
    caplog: pytest.LogCaptureFixture,
) -> None:
    logged = _warning_from_430(caplog)
    assert "Account rate-limit lockout (HTTP 430)" in logged, logged
    assert "api.example.com/vehicles/<vin>/status" in logged, logged


def test_the_named_endpoint_leaks_neither_the_vin_nor_the_query_token(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The path carries the VIN and the query can carry a token; the masked
    form that reaches the log must show neither."""
    logged = _warning_from_430(caplog)
    assert _VIN not in logged, logged
    assert "secret-xyz" not in logged, logged
    assert "access_token" not in logged, logged
    assert "<vin>" in logged, logged
