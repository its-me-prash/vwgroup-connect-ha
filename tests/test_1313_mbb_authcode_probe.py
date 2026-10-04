# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The requestAuthCode probe in the MBB DAG harness (Audi watch, 2026-10-04).

myAudi 5.8.1 carries ``mobile/oauth2/v1/requestAuthCode/authorize`` on exactly
the host ``_mbboauth.py`` already talks to, with the same ``sc2:fal`` scope, and
an ``authorizationCode`` call on its MBB connector. Our 2026-06 probe of
``/mobile/oauth2/v1/token`` got a 403, and the hypothesis is that we skip this
code step.

Live behaviour cannot be tested here: it needs a real account and a browser
confirmation. What IS testable, and what these tests pin, is the mechanic — the
endpoint, the variant matrix, fail-soft per variant, and above all that neither
the id_token nor a returned code is ever printed. The harness's own header
promises it never prints tokens, and a tester pastes its output into a public
issue, so that promise is the load-bearing property here.
"""
from __future__ import annotations

import asyncio
import importlib.util
import json
import pathlib
import sys
from typing import Any

import pytest

_HARNESS = pathlib.Path("scripts/mbb_dag_test.py")


def _load() -> Any:
    """Load the harness as a module without running its CLI."""
    spec = importlib.util.spec_from_file_location("_mbb_dag_harness", _HARNESS)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["_mbb_dag_harness"] = mod
    spec.loader.exec_module(mod)
    return mod


H = _load()

TOKEN = "eyJhbGciOiJSUzI1NiJ9.THIS_IS_THE_SECRET_ID_TOKEN_PAYLOAD.sig"
CODE = "AUTHCODE_THAT_MUST_NOT_BE_PRINTED_0123456789"


# ── the pure helpers ────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "key", ["code", "authorizationCode", "authCode", "auth_code"]
)
def test_the_code_field_is_found_under_every_spelling(key: str) -> None:
    """The APK does not say which spelling the server uses, so all four are
    accepted — and only the NAME and LENGTH come back, never the value."""
    name, length = H._code_from(json.dumps({key: CODE}))
    assert name == key
    assert length == len(CODE)


@pytest.mark.parametrize("body", [
    "", "not json", "[]", '"str"', "{}",
    '{"code": ""}', '{"code": 12345}', '{"nested": {"code": "x"}}',
])
def test_no_code_is_reported_when_there_is_none(body: str) -> None:
    assert H._code_from(body) == ("", 0)


def test_the_error_code_is_shape_bounded() -> None:
    """Same discipline as the integration's own error reader: an enum-like token
    passes, free text does not, because this string reaches a pasted report."""
    assert H._err_code_of('{"error": "invalid_grant"}') == "invalid_grant"
    assert H._err_code_of('{"errorCode": "RS.security.9007"}') == "RS.security.9007"
    assert H._err_code_of('{"error": {"errorCode": 4004}}') == "4004"
    assert H._err_code_of('{"error": "the token 123 is not valid"}') == ""
    assert H._err_code_of(json.dumps({"error": "x" * 60})) == ""
    assert H._err_code_of("not json") == ""


# ── the probe mechanic ──────────────────────────────────────────────────────

class _Resp:
    def __init__(self, status: int, payload: Any) -> None:
        self.status = status
        self._payload = payload

    async def text(self) -> str:
        if isinstance(self._payload, str):
            return self._payload
        return json.dumps(self._payload)

    async def __aenter__(self) -> _Resp:
        return self

    async def __aexit__(self, *_a: object) -> None:
        return None


class _Session:
    """Records every call so the matrix and headers can be asserted."""

    def __init__(self, responses: list[Any] | None = None) -> None:
        self.calls: list[dict[str, Any]] = []
        self._responses = list(responses or [])

    def _next(self) -> Any:
        if self._responses:
            r = self._responses.pop(0)
            if isinstance(r, Exception):
                raise r
            return r
        return _Resp(404, {"message": "path not found"})

    def post(self, url: str, **kw: Any) -> Any:
        self.calls.append({"method": "POST", "url": url, **kw})
        return self._next()

    def get(self, url: str, **kw: Any) -> Any:
        self.calls.append({"method": "GET", "url": url, **kw})
        return self._next()


def _run(session: _Session) -> None:
    asyncio.new_event_loop().run_until_complete(
        H._request_auth_code_probe(
            session, TOKEN, client_id="cid-1", brand="audi"
        )
    )


def test_it_probes_the_endpoint_the_apk_names() -> None:
    s = _Session()
    _run(s)
    assert s.calls, "no request was made"
    tail = "/mbbcoauth/mobile/oauth2/v1/requestAuthCode/authorize"
    for c in s.calls:
        assert c["url"].endswith(tail), c["url"]
        assert "mbboauth-1d.prd.ece.vwg-connect.com" in c["url"]


def test_the_matrix_varies_one_dimension_at_a_time() -> None:
    """Four forms: the id_token grant with response_type=code, the same with the
    token under the other field name, an OIDC-style GET, and one without the
    client header — that last one separates "client not allowed" from "wrong
    form"."""
    s = _Session()
    _run(s)
    assert len(s.calls) == 4, f"{len(s.calls)} variants"
    assert sum(1 for c in s.calls if c["method"] == "GET") == 1
    no_hdr = [c for c in s.calls if "X-Client-Id" not in (c.get("headers") or {})]
    assert len(no_hdr) == 1, "the without-client-header variant is missing"
    for c in s.calls:
        assert TOKEN not in c["url"], "the token must not travel in the URL path"


def test_one_variant_failing_does_not_stop_the_others() -> None:
    """The fail-soft rule the harness's other probes follow."""
    s = _Session([
        RuntimeError("connection reset"),
        _Resp(400, {"error": "invalid_request"}),
        _Resp(403, {}),
        _Resp(404, {}),
    ])
    _run(s)
    assert len(s.calls) == 4


# ── the promise the harness makes ───────────────────────────────────────────

def test_neither_the_token_nor_the_code_is_ever_printed(
    capsys: pytest.CaptureFixture[str],
) -> None:
    s = _Session([
        _Resp(200, {"code": CODE}), _Resp(200, {"authCode": CODE}),
        _Resp(200, {"code": CODE}), _Resp(200, {"code": CODE}),
    ])
    _run(s)
    out = capsys.readouterr().out
    assert TOKEN not in out, "the id_token was printed"
    assert "THIS_IS_THE_SECRET_ID_TOKEN_PAYLOAD" not in out
    assert CODE not in out, "the auth code was printed"
    assert "AUTHCODE_THAT_MUST_NOT_BE_PRINTED" not in out
    # the useful facts ARE reported
    assert str(len(CODE)) in out
    assert "code-Feld" in out


def test_the_verdict_explains_each_status(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A tester who is not the maintainer has to read the result unaided."""
    s = _Session([_Resp(404, {}) for _ in range(4)])
    _run(s)
    out = capsys.readouterr().out
    assert "KEIN Code" in out
    for status in ("404", "400", "403", "401"):
        assert status in out, f"the verdict does not explain {status}"


def test_a_hit_is_not_auto_exchanged(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """An auth code is usually single-use. Spending it automatically would burn
    the one piece of evidence before the exchange form is decided."""
    s = _Session([_Resp(200, {"code": CODE})])
    _run(s)
    out = capsys.readouterr().out
    assert "TREFFER" in out
    assert all("requestAuthCode" in c["url"] for c in s.calls), (
        "a second endpoint was called — the code may already be spent"
    )
    assert "NICHT automatisch" in out
