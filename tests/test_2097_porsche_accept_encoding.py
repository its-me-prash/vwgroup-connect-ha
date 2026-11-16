# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#2097 / #2099 — Porsche reads fail once the HTTP client offers ``br``/``zstd``.

Two Porsche reports arrived on the same day, both on Home Assistant 2026.11
(Python 3.14) and both after a login that had worked:

* #2097 — the garage read failed, which setup renders as "No vehicles found
  for this account". @Gaut666 added one request header,
  ``Accept-Encoding: gzip, deflate``, and reported that the integration then
  "works perfectly".
* #2099 — the garage was known, but every status read failed with an
  ``APIError`` that carried no HTTP status: the transient path, three retries
  deep. The diagnostics said only ``"porsche_status": "APIError"``, which is
  why this file also pins the second half below.

What changed underneath is measurable: ``PorscheClient._request`` never set
``Accept-Encoding``, so aiohttp filled in its own default, and that default
grows with the interpreter — ``gzip, deflate``, plus ``br`` when brotli is
importable, plus ``zstd`` on Python 3.14, where the decoder is in the standard
library. The Porsche code itself is byte-identical between the release that
worked and the one that did not. What the Porsche backend does with a request
that offers the newer codings is NOT established here (an unauthenticated probe
answers gzip either way); what is established is the reporter's result on a
real account, and that gzip and deflate are the two codings every aiohttp build
decodes on its own.

So the pin is deliberate and narrow: this client says which codings it wants
instead of inheriting whatever the interpreter happens to support.

The second half is observability. When a read dies on the transient path the
class name of the failure only ever reached a DEBUG line; diagnostics recorded
a bare ``APIError``, which cannot tell a payload-decode failure from a timeout.
The outcome now carries that class name, so the next diagnostics file answers
the question instead of prompting it.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any
from unittest.mock import MagicMock

import aiohttp
import pytest

from custom_components.vag_connect.cariad.api import porsche as porsche_mod
from custom_components.vag_connect.cariad.api.porsche import PorscheClient
from custom_components.vag_connect.cariad.models import TokenSet, VehicleData

_VIN = "WP0ZZZY1ZNS000001"  # synthetic: padded-counter serial


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


def _client(steps: list[Any]) -> tuple[PorscheClient, list[dict[str, Any]]]:
    """A client whose transport plays ``steps`` in order and records each call.

    A step is either a ``_Resp`` or an exception instance to raise — the latter
    is how aiohttp reports a payload it could not decode.
    """
    calls: list[dict[str, Any]] = []
    it = iter(steps)

    def _request(method: str, url: str, **kw: Any) -> Any:
        calls.append({"method": method, "url": url, **kw})
        step = next(it)
        if isinstance(step, BaseException):
            raise step
        return step

    session = MagicMock()
    session.request = MagicMock(side_effect=_request)
    client = PorscheClient(session, "u@t.invalid", "pw")
    # Keep _request on the transport path: it refuses without a token set and
    # refreshes proactively when one is close to expiry.
    client._tokens = TokenSet(  # noqa: SLF001
        access_token="t", refresh_token="r", id_token="i",
        expires_at=time.time() + 3600, strategy="classic",
    )
    return client, calls


def _codings(call: dict[str, Any]) -> list[str]:
    header = call["headers"].get("Accept-Encoding")
    assert header is not None, "the request carries no Accept-Encoding at all"
    return [c.strip() for c in header.split(",")]


@pytest.fixture
def no_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    """The retry ladder waits 3 s / 6 s / 12 s; a test must not."""

    async def _instant(_seconds: float) -> None:
        return None

    monkeypatch.setattr(porsche_mod.asyncio, "sleep", _instant)


# ── the pin ─────────────────────────────────────────────────────────────────


def test_a_read_offers_gzip_and_deflate_and_nothing_else() -> None:
    """The reported fix, as a property of every request this client sends."""
    client, calls = _client([_Resp(200, [])])
    asyncio.run(client._request("GET", "https://x.invalid/vehicles", retry=False))  # noqa: SLF001

    assert len(calls) == 1
    assert _codings(calls[0]) == ["gzip", "deflate"], (
        "the client must name its codings itself — left unset, aiohttp adds br "
        "and (on Python 3.14) zstd, the request shape #2097 failed with"
    )


def test_the_garage_read_goes_out_pinned_and_still_parses() -> None:
    """#2097's own path: ``get_vehicles`` is the read that came back empty."""
    client, calls = _client([_Resp(200, [{"vin": _VIN, "modelName": "Taycan"}])])
    vins = asyncio.run(client.get_vehicles())

    assert vins == [_VIN]
    assert _codings(calls[0]) == ["gzip", "deflate"]


def test_a_401_retry_keeps_the_pin(monkeypatch: pytest.MonkeyPatch) -> None:
    """The retry rebuilds its headers; the pin must survive that rebuild."""
    client, calls = _client([_Resp(401), _Resp(200, [])])

    async def _refresh(**_kw: Any) -> None:
        return None

    monkeypatch.setattr(client, "_refresh", _refresh)
    asyncio.run(client._request("GET", "https://x.invalid/vehicles"))  # noqa: SLF001

    assert len(calls) == 2, "expected the original call and one retry"
    for call in calls:
        assert _codings(call) == ["gzip", "deflate"]


def test_a_transient_retry_keeps_the_pin(no_sleep: None) -> None:
    """A payload error is retried — with the same narrowed offer, not a wider one."""
    client, calls = _client([
        aiohttp.ClientPayloadError("Can not decode content-encoding"),
        _Resp(200, []),
    ])
    asyncio.run(client._request("GET", "https://x.invalid/vehicles", retry=False))  # noqa: SLF001

    assert len(calls) == 2
    for call in calls:
        assert _codings(call) == ["gzip", "deflate"]


def test_a_caller_cannot_widen_the_offer() -> None:
    """Caller headers are merged in, but the coding offer stays this client's."""
    client, calls = _client([_Resp(200, {})])
    asyncio.run(client._request(  # noqa: SLF001
        "GET", "https://x.invalid/vehicles", retry=False,
        headers={"Accept-Encoding": "zstd", "X-Extra": "1"},
    ))

    assert _codings(calls[0]) == ["gzip", "deflate"]
    assert calls[0]["headers"]["X-Extra"] == "1", "other caller headers must pass through"


# ── the diagnostics half (#2099) ────────────────────────────────────────────


def test_a_transient_failure_names_its_class_in_the_probe_outcome(
    no_sleep: None, caplog: pytest.LogCaptureFixture,
) -> None:
    """#2099's diagnostics said ``APIError`` and nothing else.

    Four attempts (the first plus three retries) all die decoding the payload.
    The status read must still not raise — one bad read never crashes a poll —
    but the recorded outcome has to say WHICH transient failure it was.
    """
    boom = [aiohttp.ClientPayloadError("Can not decode content-encoding") for _ in range(4)]
    client, calls = _client(boom)

    with caplog.at_level(logging.WARNING, logger=porsche_mod.__name__):
        data = asyncio.run(client.get_status(_VIN))

    assert isinstance(data, VehicleData), "a failed read returns an empty snapshot, it does not raise"
    assert len(calls) == 4, "expected the first attempt and three retries"
    assert client.probe_outcomes["porsche_status"] == "APIError:transient:ClientPayloadError"

    warnings = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1, "the warning is raised once per car"
    assert "ClientPayloadError" in warnings[0], (
        "the one line a reporter can paste must carry the failure class"
    )
    assert _VIN not in warnings[0], "the full VIN must never reach the log"


def test_an_http_error_keeps_its_old_outcome_shape(no_sleep: None) -> None:
    """Regression guard: a status-bearing failure is recorded exactly as before."""
    client, _calls = _client([_Resp(403, {"error": "forbidden"})])
    asyncio.run(client.get_status(_VIN))

    assert client.probe_outcomes["porsche_status"] == "APIError:403"
