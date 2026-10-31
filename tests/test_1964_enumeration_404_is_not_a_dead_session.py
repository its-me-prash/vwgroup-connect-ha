"""#1964 (@Hollywoodchaos) — a 404 on vehicle enumeration is the portal's
problem, not the user's session.

He reported it precisely and proved it from outside the integration: logged
into the portal in a browser with the same account, its own "Veículos
associados" section fails with a technical error, so the 404 we received was
the truth about the portal and not about his login. We turned it into the
session-expired repair card, which told him to fix the one thing that was
working.

The cause was that the meaning of a 404 on this portal is
ENDPOINT-DEPENDENT and one rule was applied to all of them:

* metadata endpoint — 404 means "there is no such data request". #1932 decided
  that deliberately and pinned it with a test. **Unchanged here**, and guarded
  below so this change cannot quietly reverse it.
* vehicle enumeration — 404 means the portal cannot list the account's cars.

The rule now lives at the call site that knows which endpoint it is talking to.
"""
from __future__ import annotations

import asyncio
from typing import Any

import pytest

from custom_components.vag_connect.cariad.auth import _eu_data_act as mod
from custom_components.vag_connect.cariad.auth._eu_data_act import (
    EUDataActConnector,
)
from custom_components.vag_connect.cariad.exceptions import (
    AuthenticationError,
    UpstreamUnavailableError,
)

_VIN = "WVWZZZAUZFW000000"


class _Resp:
    def __init__(self, status: int, payload: Any = None) -> None:
        self.status = status
        self._payload = payload if payload is not None else {}
        self.url = "https://portal.invalid/proxy_api/consent/me/vehicles"
        self.headers: dict[str, str] = {}

    async def __aenter__(self) -> "_Resp":
        return self

    async def __aexit__(self, *_exc: object) -> bool:
        return False

    async def json(self, content_type: str | None = None) -> Any:
        return self._payload

    async def text(self, errors: str | None = None) -> str:
        return "{}"

    async def read(self) -> bytes:
        return b""


class _Session:
    """Answers every GET with one status, like a portal having a bad day."""

    def __init__(self, status: int, payload: Any = None) -> None:
        self.status = status
        self.payload = payload
        self.calls = 0

    def get(self, url: str, **_kw: Any) -> _Resp:
        self.calls += 1
        return _Resp(self.status, self.payload)

    def post(self, url: str, **_kw: Any) -> _Resp:
        self.calls += 1
        return _Resp(self.status, self.payload)


def _run(coro: Any) -> Any:
    return asyncio.new_event_loop().run_until_complete(coro)


def _connector(status: int, payload: Any = None) -> Any:
    return EUDataActConnector(_Session(status, payload))  # type: ignore[arg-type]


@pytest.fixture(autouse=True)
def _no_backoff_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    """The 5xx control would otherwise really sleep 3 s then 6 s."""
    monkeypatch.setattr(mod, "_PORTAL_RETRY_DELAYS", (0.0, 0.0))


class TestEnumeration:
    @pytest.mark.parametrize("status", [404, 410])
    def test_a_not_found_is_an_upstream_problem(self, status: int) -> None:
        c = _connector(status)
        with pytest.raises(UpstreamUnavailableError):
            _run(c.list_vehicle_vins())

    @pytest.mark.parametrize("status", [401, 403])
    def test_a_real_session_refusal_still_raises_auth(self, status: int) -> None:
        """Control: the session-expired path must keep working for 401/403."""
        c = _connector(status)
        with pytest.raises(AuthenticationError):
            _run(c.list_vehicle_vins())

    @pytest.mark.parametrize("status", [429, 500, 503])
    def test_the_outage_family_is_unchanged(self, status: int) -> None:
        """Control: what was already upstream stays upstream."""
        c = _connector(status)
        with pytest.raises(UpstreamUnavailableError):
            _run(c.list_vehicle_vins())

    def test_the_happy_path_still_returns_the_vins(self) -> None:
        """Control: a harness that raises on everything proves nothing."""
        c = _connector(200, {"vehicles": [{"vin": _VIN}]})
        assert _run(c.list_vehicle_vins()) == [_VIN]


class TestTheMetadataDecisionIsUntouched:
    """#1932: on the METADATA endpoint a 404 means "no such data request"."""

    def test_a_soft_404_still_returns_no_data(self) -> None:
        c = _connector(404)
        got = _run(c._get_json("https://portal.invalid/metadata", soft=True))
        assert got is None
        assert c._last_soft_status == 404, (
            "the status must still be recorded, or the caller cannot tell a "
            "404 'not provisioned' from a 5xx outage"
        )

    def test_soft_wins_even_when_a_caller_declares_the_status(self) -> None:
        """The two mechanisms must not fight: soft returns None, never raises."""
        c = _connector(404)
        got = _run(
            c._get_json(
                "https://portal.invalid/metadata",
                soft=True,
                outage_statuses=(404, 410),
            )
        )
        assert got is None

    def test_a_hard_call_without_the_declaration_still_raises_auth(self) -> None:
        """The default is unchanged: only a declaring call site gets the new verdict.

        This is the test that fails if someone 'simplifies' the fix by adding
        404 to the global outage set — which would silently reverse #1932.
        """
        c = _connector(404)
        with pytest.raises(AuthenticationError):
            _run(c._get_json("https://portal.invalid/metadata"))


def test_the_enumeration_call_site_declares_the_statuses() -> None:
    """Pins the wiring over the AST, not over the text.

    The first version of this test matched the words in the source and stayed
    green when the keyword argument was deleted — because the method's own
    docstring explains ``outage_statuses`` and names 404 and 410. A prohibition
    or presence check by substring hits its own explanatory comment. So read
    the call expression instead: the keyword has to be an actual argument with
    both numbers in it.
    """
    import ast
    import inspect
    import textwrap

    tree = ast.parse(
        textwrap.dedent(inspect.getsource(mod.EUDataActConnector.list_vehicle_vins))
    )
    declared: list[int] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        for kw in node.keywords:
            if kw.arg == "outage_statuses":
                declared = [
                    e.value
                    for e in getattr(kw.value, "elts", [])
                    if isinstance(e, ast.Constant) and isinstance(e.value, int)
                ]
    assert declared, (
        "no outage_statuses keyword argument in the enumeration call - the "
        "parameter can exist and still not be passed where it is needed"
    )
    assert set(declared) == {404, 410}, declared
