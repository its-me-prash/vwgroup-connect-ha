# Copyright 2026 Prash Balan (@its-me-prash) - Apache License 2.0
# SPDX-License-Identifier: AGPL-3.0-or-later
"""v2.19.0 — Tibber supplementary channel wiring (arm + cache + merge + flow).

Covers the coordinator/base-client side of wiring the (already-tested) Tibber
mapper as a lowest-trust supplementary reader, plus the config-flow OAuth2
auth-code+PKCE helpers. Network is faked — no live calls.
"""
from __future__ import annotations

import base64
import hashlib

import pytest

from custom_components.vag_connect import config_flow as cf
from custom_components.vag_connect.cariad._tibber_source import TibberDataSource
from custom_components.vag_connect.cariad.api.base import CariadBaseClient
from custom_components.vag_connect.cariad.models import VehicleData

_VIN = "WVWZZZ1KZAW000000"


def _mk_client() -> CariadBaseClient:
    """A bare base client with just the supplementary-Tibber slots set."""
    c = CariadBaseClient.__new__(CariadBaseClient)
    c._session = object()
    c._supplementary_authproxy = None
    c._supplementary_eu_portal = None
    c._supplementary_session = None
    c._mbb_command = None
    c._supplementary_tibber = None
    c._tibber_cache = {}
    c._tibber_cache_at = 0.0
    c._tibber_lock = None
    return c


class _CountingSource:
    """Fake TibberDataSource: counts sweeps, returns one car."""

    def __init__(self) -> None:
        self.calls = 0

    async def fetch_vehicles(self) -> dict[str, VehicleData]:
        self.calls += 1
        return {_VIN: VehicleData(vin=_VIN, battery_soc=55)}


# ── arm ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_arm_valid_tokens_arms_source() -> None:
    c = _mk_client()
    ok = await c.arm_supplementary_tibber({
        "access_token": "at", "refresh_token": "rt",
        "client_id": "cid", "client_secret": "sec",
    })
    assert ok is True
    assert isinstance(c._supplementary_tibber, TibberDataSource)


@pytest.mark.asyncio
async def test_arm_rejects_empty_and_nondict() -> None:
    c = _mk_client()
    assert await c.arm_supplementary_tibber(None) is False
    assert await c.arm_supplementary_tibber({}) is False
    assert await c.arm_supplementary_tibber(
        {"access_token": "", "refresh_token": ""}
    ) is False
    assert c._supplementary_tibber is None


# ── per-poll cache ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_read_caches_one_sweep_across_vins() -> None:
    c = _mk_client()
    src = _CountingSource()
    c._supplementary_tibber = src
    # two reads within the TTL → exactly ONE sweep
    a = await c._read_tibber(_VIN)
    b = await c._read_tibber(_VIN.lower())  # case-insensitive VIN match
    assert a is not None and a.vin == _VIN
    assert b is not None and b.vin == _VIN
    assert src.calls == 1


@pytest.mark.asyncio
async def test_read_refetches_after_ttl() -> None:
    c = _mk_client()
    src = _CountingSource()
    c._supplementary_tibber = src
    await c._read_tibber(_VIN)
    assert src.calls == 1
    # expire the cache → next read sweeps again
    c._tibber_cache_at = 0.0
    c._tibber_cache = {}
    await c._read_tibber(_VIN)
    assert src.calls == 2


@pytest.mark.asyncio
async def test_read_returns_none_when_unarmed() -> None:
    c = _mk_client()
    assert await c._read_tibber(_VIN) is None


@pytest.mark.asyncio
async def test_read_is_fail_soft() -> None:
    c = _mk_client()

    class _Boom:
        async def fetch_vehicles(self):
            raise RuntimeError("boom")

    c._supplementary_tibber = _Boom()
    assert await c._read_tibber(_VIN) is None  # never raises


# ── reader registration / trust order ───────────────────────────────────────

@pytest.mark.asyncio
async def test_tibber_registered_last_lowest_trust() -> None:
    c = _mk_client()
    c._supplementary_authproxy = object()
    c._supplementary_eu_portal = object()
    c._supplementary_tibber = _CountingSource()
    readers = c.supplementary_readers(_VIN)
    names = [n for n, _ in readers]
    assert names == ["website_authproxy", "eu_data_act", "tibber"]
    for _, coro in readers:
        coro.close()  # we only asserted registration, don't run the reads


@pytest.mark.asyncio
async def test_no_tibber_reader_when_unarmed() -> None:
    c = _mk_client()
    readers = c.supplementary_readers(_VIN)
    assert readers == []


# ── close ───────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_close_supplementary_drops_tibber_and_cache() -> None:
    c = _mk_client()
    c._supplementary_tibber = _CountingSource()
    c._tibber_cache = {_VIN: VehicleData(vin=_VIN)}
    c._tibber_cache_at = 123.0
    await c.close_supplementary()
    assert c._supplementary_tibber is None
    assert c._tibber_cache == {}
    assert c._tibber_cache_at == 0.0


# ── rotating-token persistence hook ─────────────────────────────────────────

class _FakeResp:
    def __init__(self, status: int, body: dict) -> None:
        self.status = status
        self._body = body

    async def __aenter__(self) -> "_FakeResp":
        return self

    async def __aexit__(self, *a: object) -> bool:
        return False

    async def json(self, content_type: object = None) -> dict:
        return self._body


class _FakeSession:
    def __init__(self, body: dict, status: int = 200) -> None:
        self._body = body
        self._status = status

    def post(self, url: str, data=None, headers=None, timeout=None) -> _FakeResp:
        return _FakeResp(self._status, self._body)


@pytest.mark.asyncio
async def test_refresh_fires_on_tokens_changed_with_rotated_bundle() -> None:
    src = TibberDataSource(
        _FakeSession({"access_token": "new_at", "refresh_token": "new_rt"}),
        access_token="old_at", refresh_token="old_rt",
        client_id="cid", client_secret="sec",
    )
    captured: list[dict] = []

    async def _hook(bundle: dict) -> None:
        captured.append(bundle)

    src.on_tokens_changed = _hook
    assert await src._refresh() is True
    assert src.refresh_token == "new_rt"
    assert captured and captured[0] == {
        "access_token": "new_at", "refresh_token": "new_rt",
        "client_id": "cid", "client_secret": "sec",
    }


# ── config-flow OAuth2 (auth-code + PKCE) helpers ───────────────────────────

def test_pkce_challenge_is_s256_base64url_no_pad() -> None:
    verifier = "abc123-_verifier-string-of-sufficient-length-000"
    expected = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode("ascii")).digest()
    ).rstrip(b"=").decode("ascii")
    assert cf._tibber_pkce_challenge(verifier) == expected
    assert "=" not in cf._tibber_pkce_challenge(verifier)


def _mk_flow() -> cf.VagConnectOptionsFlow:
    f = cf.VagConnectOptionsFlow.__new__(cf.VagConnectOptionsFlow)
    f._otib_client_id = "my-client"
    f._otib_client_secret = "my-secret"
    f._otib_verifier = "verifier-000000000000000000000000000000000000"
    f._otib_state = "state-xyz"
    return f


def test_authorize_url_has_pkce_and_state() -> None:
    url = _mk_flow()._otib_authorize_url()
    assert url.startswith("https://thewall.tibber.com/connect/authorize?")
    assert "response_type=code" in url
    assert "client_id=my-client" in url
    assert "code_challenge_method=S256" in url
    assert "code_challenge=" in url
    assert "state=state-xyz" in url
    assert "data-api-vehicles-read" in url


def test_extract_code_from_redirect_url_verifies_state() -> None:
    f = _mk_flow()
    code = f._otib_extract_code(
        "https://my.home-assistant.io/redirect/oauth?code=THECODE&state=state-xyz"
    )
    assert code == "THECODE"


def test_extract_code_accepts_bare_code() -> None:
    assert _mk_flow()._otib_extract_code("BARECODE123") == "BARECODE123"


def test_extract_code_rejects_state_mismatch() -> None:
    with pytest.raises(ValueError):
        _mk_flow()._otib_extract_code(
            "https://x/redirect?code=C&state=WRONG"
        )


def test_extract_code_rejects_empty() -> None:
    with pytest.raises(ValueError):
        _mk_flow()._otib_extract_code("")
    with pytest.raises(ValueError):
        _mk_flow()._otib_extract_code("https://x/redirect?state=state-xyz")
