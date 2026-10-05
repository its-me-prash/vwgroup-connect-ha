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


def test_the_verdict_states_the_conclusion_for_what_happened(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A tester who is not the maintainer has to read the result unaided — so
    the verdict names the conclusion for the case that occurred, instead of
    printing a legend of four cases and leaving the reader to apply it."""
    s = _Session([_Resp(404, {}) for _ in range(4)])
    _run(s)
    out = capsys.readouterr().out
    assert "KEIN Code" in out
    assert "widerlegt" in out, "the 404-everywhere conclusion is missing"
    # The other cases must NOT be asserted at the reader; this is the
    # regression the rewrite fixes.
    assert "400=Form falsch" not in out, "the legend is being printed again"


def test_a_uniform_non_json_403_is_not_called_a_client_decision(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The 2026-10-04 Audi run: four identical non-JSON 403s, including the
    variant without X-Client-Id. The old verdict declared "endpoint lives, our
    client may not" — an overclaim. An OAuth endpoint refusing a client answers
    with a JSON error object; a non-JSON body means nothing reached the OAuth
    layer, so the honest reading is a gateway refusal with the reason unknown."""
    s = _Session([_Resp(403, "<html>Forbidden</html>") for _ in range(4)])
    _run(s)
    out = capsys.readouterr().out
    assert "Gateway" in out
    assert "NICHT bestaetigt" in out
    assert "kein JSON" in out, "the body shape is not reported"
    assert "Client-Entscheidung" in out, "the distinction is not drawn"


def test_a_json_403_is_read_as_a_real_refusal(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """With a JSON error object the endpoint DID answer, and then the old
    reading is the right one."""
    s = _Session([_Resp(403, {"error": "unauthorized_client"}) for _ in range(4)])
    _run(s)
    out = capsys.readouterr().out
    assert "lehnt ab" in out
    assert "Gateway" not in out, "a real refusal must not be called a gateway block"


def test_a_400_is_read_as_a_form_problem(
    capsys: pytest.CaptureFixture[str],
) -> None:
    s = _Session([_Resp(400, {"error": "invalid_request"}) for _ in range(4)])
    _run(s)
    out = capsys.readouterr().out
    assert "Form" in out
    assert "lebt" in out, "a 400 proves the endpoint is alive — say so"


def test_a_401_everywhere_is_read_as_an_audience_problem(
    capsys: pytest.CaptureFixture[str],
) -> None:
    s = _Session([_Resp(401, {"error": "invalid_token"}) for _ in range(4)])
    _run(s)
    out = capsys.readouterr().out
    assert "Audience" in out
    assert "KEINE Aussage" in out, "must say it says nothing about requestAuthCode"


def test_mixed_statuses_fall_back_to_the_legend(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Only when the answers disagree is the reader handed the legend."""
    s = _Session([_Resp(404, {}), _Resp(403, {}), _Resp(401, {}), _Resp(404, {})])
    _run(s)
    out = capsys.readouterr().out
    assert "Gemischte Antworten" in out
    assert "404=Pfad fehlt" in out


def test_all_variants_failing_to_connect_is_not_a_finding(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """This machine has flaky DNS to the vwg-connect hosts. Four connect errors
    must not be dressed up as evidence about the endpoint — that is how a
    TimeoutError gets mistaken for a refuted hypothesis."""
    s = _Session([RuntimeError("getaddrinfo failed") for _ in range(4)])
    _run(s)
    out = capsys.readouterr().out
    assert "KEIN Befund" in out
    assert "wiederholen" in out
    assert "widerlegt" not in out, "a connection failure was called a refutation"


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


# ── the precondition that decides whether a run is even readable ────────────

def _tok(aud: object) -> str:
    """A JWT whose public payload carries the given aud (unsigned, test-only)."""
    import base64
    payload = json.dumps({"iss": "https://identity.vwgroup.io", "aud": aud})
    b64 = base64.urlsafe_b64encode(payload.encode()).decode().rstrip("=")
    return f"header.{b64}.signature"


def _run_with(session: _Session, token: str) -> None:
    asyncio.new_event_loop().run_until_complete(
        H._request_auth_code_probe(
            session, token, client_id="cid-1", brand="audi"
        )
    )


def test_a_token_without_the_mbb_audience_is_called_out(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Without the ``mbb`` scope the id_token has no VWGMBB audience, so a 401
    is an audience problem and says nothing about requestAuthCode. A run like
    that must not be mistaken for the hypothesis being refuted."""
    s = _Session([_Resp(401, {"error": "invalid_token"})])
    _run_with(s, _tok(["09b6cbec-cd19-4589-82fd-363dfa8c24da@apps_vw-dilab_com"]))
    out = capsys.readouterr().out
    assert "WARNUNG" in out
    assert "VWGMBB" in out
    # The fix has to be spelled out, and spelled out CORRECTLY: naming the
    # "mbb" route, not "pass a client_id". Pasting the Audi app client is what
    # this warning used to advise, and that client's device grant is retired
    # (#1364) — the advice sent the reader into a 403 instead of a result.
    assert "mbb" in out, "the fix is not spelled out"
    assert "client_id" not in out, "still advises pasting a client_id"


def test_a_token_with_the_mbb_audience_is_confirmed(
    capsys: pytest.CaptureFixture[str],
) -> None:
    s = _Session([_Resp(400, {"error": "invalid_request"})])
    _run_with(s, _tok(["VWGMBBOIDCAPP1", "VWGMBB01DELIV1"]))
    out = capsys.readouterr().out
    assert "[ok] id_token.aud" in out
    assert "WARNUNG" not in out


def test_a_single_string_audience_is_handled() -> None:
    """``aud`` is a string on some issuers and a list on others; neither may
    crash the guard."""
    for aud in ("VWGMBB01DELIV1", ["VWGMBB01DELIV1"], None, 123):
        _run_with(_Session([_Resp(404, {})]), _tok(aud))


def test_the_guard_never_prints_the_token(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The guard decodes the token to read aud — it must print the claim, not
    the token."""
    token = _tok(["VWGMBB01DELIV1"])
    _run_with(_Session([_Resp(404, {})]), token)
    out = capsys.readouterr().out
    assert token not in out
    assert token.split(".")[1] not in out, "the payload segment was printed"
