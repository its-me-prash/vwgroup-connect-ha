# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#1853 — a Porsche command answers "201 Created", which was treated as an error.

``POST /app/connect/v1/vehicles/{vin}/commands`` returns 201 for an accepted
command. ``PorscheClient._request`` accepted only 200 and 202 (plus an early
return on 204), so every remote command raised ``APIError(201)`` in front of the
user while the car went on and performed it.

The second half matters more than the message. The raise sits *before*
``resp.json()``, so the response body was never parsed — and that body is where
``status.id`` and ``status.result == "ACCEPTED"`` live. ``_command()`` reads them
to decide whether to poll ``/commands/{id}`` for a terminal state. With the
raise in the way, a command that Porsche later *rejected* looked exactly like
one it performed: the verification could not run at all.

Porsche was the only client in the package that left 201 out — ``base.py``
accepts ``(200, 201, 207)`` and ``(200, 201, 202, 207)``, ``skoda_official``
accepts ``(200, 201, 202, 204)``.
"""
from __future__ import annotations

import asyncio
import json
import time
from typing import Any
from unittest.mock import MagicMock

from custom_components.vag_connect.cariad.api.porsche import PorscheClient
from custom_components.vag_connect.cariad.models import TokenSet


class _Resp:
    """Minimal aiohttp-ish response: async context manager, status, json/text."""

    def __init__(self, status: int, payload: Any = None) -> None:
        self.status = status
        self.headers: dict[str, str] = {}
        self._payload = payload if payload is not None else {}

    async def __aenter__(self) -> "_Resp":
        return self

    async def __aexit__(self, *exc: object) -> bool:
        return False

    async def json(self) -> Any:
        return self._payload

    async def text(self) -> str:
        return json.dumps(self._payload)


def _client(responses: list[_Resp]) -> PorscheClient:
    it = iter(responses)
    session = MagicMock()
    session.request = MagicMock(side_effect=lambda *a, **kw: next(it))
    client = PorscheClient(session, "u@t.invalid", "pw")
    # Keep _request on the transport path: _request refuses without a token
    # set, and refreshes proactively when one is close to expiry — so hand it
    # a set that is valid for an hour.
    client._tokens = TokenSet(  # noqa: SLF001
        access_token="t", refresh_token="r", id_token="i",
        expires_at=time.time() + 3600, strategy="classic",
    )
    return client


_ACCEPTED = {"status": {"id": "cmd-1", "result": "ACCEPTED"}}


def test_a_201_is_a_created_command_not_an_error() -> None:
    """The reported symptom: "API error 201" on every command."""
    client = _client([_Resp(201, _ACCEPTED)])
    got = asyncio.run(
        client._request("POST", "https://x.invalid/commands", retry=False)  # noqa: SLF001
    )
    assert got == _ACCEPTED, (
        "a 201 response must come back parsed, not as an APIError"
    )


def test_the_201_body_reaches_the_caller_so_the_command_can_be_verified() -> None:
    """The part that was not just cosmetic. `status.id` + "ACCEPTED" live in the
    body, and _command() needs them to poll for a terminal state — a raise
    before resp.json() made a rejected command indistinguishable from a
    performed one."""
    client = _client([_Resp(201, _ACCEPTED)])
    body = asyncio.run(
        client._request("POST", "https://x.invalid/commands", retry=False)  # noqa: SLF001
    )
    status = body.get("status", {})
    assert status.get("id") == "cmd-1"
    assert status.get("result") == "ACCEPTED"


def test_200_and_202_still_pass_and_204_still_returns_empty() -> None:
    """Widening the set must not change what already worked."""
    for status in (200, 202):
        client = _client([_Resp(status, {"ok": status})])
        assert asyncio.run(
            client._request("GET", "https://x.invalid/thing", retry=False)  # noqa: SLF001
        ) == {"ok": status}
    client = _client([_Resp(204)])
    assert asyncio.run(
        client._request("DELETE", "https://x.invalid/thing", retry=False)  # noqa: SLF001
    ) == {}


def test_a_real_error_status_still_raises() -> None:
    """The widening is three codes, not "anything below 400". A 403 or a 404
    must still surface, or this fix would hide the next real failure."""
    from custom_components.vag_connect.cariad.exceptions import APIError

    for status in (400, 403, 404, 409):
        client = _client([_Resp(status, {"error": "no"})])
        raised = None
        try:
            asyncio.run(
                client._request("POST", "https://x.invalid/commands", retry=False)  # noqa: SLF001
            )
        except APIError as err:
            raised = err
        assert raised is not None, f"{status} must raise APIError"
        assert raised.status == status


def test_porsche_is_no_longer_the_only_client_rejecting_201() -> None:
    """Pinned as a cross-client invariant: 201 means created, and a command
    endpoint is exactly the kind that answers it. This is what made the bug
    findable — every other client already accepted it."""
    from pathlib import Path

    api = Path(__file__).resolve().parent.parent / "custom_components" / "vag_connect" / "cariad" / "api"
    porsche = (api / "porsche.py").read_text(encoding="utf-8")
    assert "if resp.status not in (200, 201, 202):" in porsche
    assert "if resp.status not in (200, 202):" not in porsche
