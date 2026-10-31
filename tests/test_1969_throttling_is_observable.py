"""#1969 — whether this portal ever throttles US had never been observed.

Its rate limits are known from someone else measuring their own traffic against
the same portal: per-endpoint ceilings, a refill of roughly one request every
two seconds, and a short explicit ``Retry-After``. We honour such a cooldown
now. Whether the portal sends one to this integration at all was an open
question, and a rate limit taken on faith is how a poll loop gets paced against
a number that does not apply to it.

Three recorded values make one user's diagnostics file settle it:

* count 0 — it has never happened to us;
* count above 0 with no seconds — throttled and told nothing;
* count above 0 with a number — the mechanism applies, and the number says
  whether the 30 s cap is right.

Recorded on EVERY 429, including the second one in a call and the over-cap case,
because those are exactly the observations that say the pacing is wrong — and
they are the ones a "record it only when we act on it" version would lose.
"""
from __future__ import annotations

import asyncio
from typing import Any

import pytest

from custom_components.vag_connect import diagnostics as D
from custom_components.vag_connect.cariad.auth import _eu_data_act as mod
from custom_components.vag_connect.cariad.auth._eu_data_act import (
    EUDataActConnector,
)
from custom_components.vag_connect.cariad.exceptions import (
    UpstreamUnavailableError,
)


class _Resp:
    def __init__(self, status: int, headers: dict[str, str]) -> None:
        self.status = status
        self.headers = headers
        self.url = "https://portal.invalid/x"

    async def __aenter__(self) -> "_Resp":
        return self

    async def __aexit__(self, *_exc: object) -> bool:
        return False

    async def json(self, content_type: str | None = None) -> Any:
        return {}

    async def text(self, errors: str | None = None) -> str:
        return "{}"

    async def read(self) -> bytes:
        return b""


class _Session:
    def __init__(self, script: list[tuple[int, dict[str, str]]]) -> None:
        self.script = list(script)
        self.calls = 0

    def _next(self) -> _Resp:
        self.calls += 1
        s, h = self.script[min(self.calls - 1, len(self.script) - 1)]
        return _Resp(s, h)

    def get(self, url: str, **_kw: Any) -> _Resp:
        return self._next()

    def post(self, url: str, **_kw: Any) -> _Resp:
        return self._next()


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _fake(_s: float) -> None:
        return None

    monkeypatch.setattr(mod.asyncio, "sleep", _fake)


def _run(c: Any) -> Any:
    return asyncio.new_event_loop().run_until_complete(c)


def _conn(script: list[tuple[int, dict[str, str]]]) -> Any:
    return EUDataActConnector(_Session(script))  # type: ignore[arg-type]


class TestTheCounterStartsHonest:
    def test_a_fresh_connector_has_never_been_throttled(self) -> None:
        c = _conn([(200, {})])
        assert c.throttle_count == 0
        assert c.last_retry_after_s is None
        assert c.last_throttle_honoured is None

    def test_a_successful_poll_does_not_invent_a_throttle(self) -> None:
        c = _conn([(200, {})])
        _run(c.list_vehicle_vins())
        assert c.throttle_count == 0


class TestWhatGetsRecorded:
    def test_a_honoured_cooldown_is_recorded_as_honoured(self) -> None:
        c = _conn([(429, {"Retry-After": "4"}), (200, {})])
        _run(c.list_vehicle_vins())
        assert c.throttle_count == 1
        assert c.last_retry_after_s == 4
        assert c.last_throttle_honoured is True

    def test_throttled_and_told_nothing_is_distinguishable(self) -> None:
        """The case that says a cap has to be guessed rather than read."""
        c = _conn([(429, {})])
        with pytest.raises(UpstreamUnavailableError):
            _run(c.list_vehicle_vins())
        assert c.throttle_count == 1
        assert c.last_retry_after_s is None
        assert c.last_throttle_honoured is False

    def test_an_over_cap_cooldown_is_recorded_with_its_number(self) -> None:
        """Recorded, not honoured: the number is what says the cap is wrong."""
        c = _conn([(429, {"Retry-After": "600"})])
        with pytest.raises(UpstreamUnavailableError):
            _run(c.list_vehicle_vins())
        assert c.throttle_count == 1
        assert c.last_retry_after_s == 600
        assert c.last_throttle_honoured is False

    def test_a_second_throttle_in_one_call_still_counts(self) -> None:
        """The observation a 'record only what we act on' version would lose."""
        c = _conn([(429, {"Retry-After": "2"}), (429, {"Retry-After": "2"})])
        with pytest.raises(UpstreamUnavailableError):
            _run(c.list_vehicle_vins())
        assert c.throttle_count == 2, (
            "only the honoured one was counted, so a portal that keeps "
            "throttling looks like a portal that throttled once"
        )


class TestItReachesTheDownload:
    """A field nothing reads is not observability."""

    def _client(self, portal: Any) -> Any:
        class _C:
            pass

        c = _C()
        c._eu_portal = portal  # type: ignore[attr-defined]
        return c

    def test_the_values_are_exported(self) -> None:
        c = _conn([(429, {"Retry-After": "4"}), (200, {})])
        _run(c.list_vehicle_vins())
        got = D._portal_throttle(self._client(c))
        assert got == {"count": 1, "retry_after_s": 4, "honoured": True}

    def test_a_never_throttled_portal_exports_a_zero_not_a_nothing(self) -> None:
        """Zero is the answer "it has never happened", which is a real answer."""
        c = _conn([(200, {})])
        got = D._portal_throttle(self._client(c))
        assert got == {"count": 0, "retry_after_s": None, "honoured": None}

    def test_an_older_client_without_the_field_stays_export_safe(self) -> None:
        class _Old:
            pass

        assert D._portal_throttle(self._client(_Old())) is None

    def test_no_portal_and_no_client_are_both_handled(self) -> None:
        class _C:
            pass

        assert D._portal_throttle(None) is None
        assert D._portal_throttle(_C()) is None

    def test_the_key_is_in_the_emitted_section(self) -> None:
        """Pins the wiring over the AST: the field must be in the dict.

        Checked structurally because the comment beside it names the key too,
        and a substring check would pass with the entry deleted.
        """
        import ast
        import inspect
        import textwrap

        tree = ast.parse(textwrap.dedent(inspect.getsource(D)))
        keys: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Dict):
                for k in node.keys:
                    if isinstance(k, ast.Constant) and isinstance(k.value, str):
                        keys.add(k.value)
        assert "portal_throttle" in keys, (
            "the value is recorded and never emitted, which is a dead field"
        )
