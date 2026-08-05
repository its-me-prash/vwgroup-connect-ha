# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""v2.15.5 (#503) — VW NA SPIN read-session auth.

Peer-confirmed (zackcornelius/CarConnectivity-connector-volkswagen-na, pushed
2026-06-24): on locked-down NA accounts the rvs/ev reads 403 on the bare
access_token but succeed when authorised with a per-vehicle
``carnetVehicleToken`` obtained via a SPIN challenge/session handshake.

Flow:
    1. GET  {base}/ss/v1/user/{uid}/challenge -> data.challenge + remainingTries
    2. spinHash = SHA512(challenge + "." + spin).hexdigest()  [LOWERCASE first,
       v2.29.x sstur/vwapp; uppercase is retried on a 401/403 as a legacy fallback]
    3. POST {base}/ss/v1/user/{uid}/vehicle/{uuid}/session
            body {idToken, spinHash, tsp:"WCT"} -> data.carnetVehicleToken
    4. Authorization: Bearer <carnetVehicleToken> on the rvs + ev reads.

These tests prove:
  - happy path: challenge -> hash -> session -> carnetVehicleToken used as the
    Bearer on the data reads (and the peer header block applied there only);
  - no-S-PIN -> falls back to access_token (no SPIN calls);
  - SPIN session failure (401) -> fallback + no retry-loop (disabled flag);
  - carnetVehicleToken cached (second poll doesn't re-challenge);
  - persistence counter surfaces the repair after N consecutive bare-403s.

Pure-Python: constructs VWNAClient via __new__ to skip the HA / aiohttp setup
chain, matching test_v210_vw_na_endpoints.py + test_v2154_vw_na_data_403_triage.
"""

from __future__ import annotations

import base64
import hashlib
import json
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest


pytestmark = pytest.mark.ha_required


_VIN = "WVWZZZ1KZAW000503"
_UUID = "11112222-3333-4444-5555-666677778888"
_USER_ID = "user-abc"
_CARNET = "carnet.token.value"  # placeholder; happy-path overrides with a JWT


def _make_jwt(exp_epoch: float | None) -> str:
    """Build an unsigned JWT-shaped string with an optional exp claim."""
    header = base64.urlsafe_b64encode(b'{"alg":"none"}').decode().rstrip("=")
    payload_obj: dict = {}
    if exp_epoch is not None:
        payload_obj["exp"] = int(exp_epoch)
    payload = (
        base64.urlsafe_b64encode(json.dumps(payload_obj).encode())
        .decode()
        .rstrip("=")
    )
    return f"{header}.{payload}.sig"


class _FakeTokens:
    def __init__(self) -> None:
        self.access_token = "ACCESS-TOKEN"
        self.id_token = "ID-TOKEN"
        self.refresh_token = "REFRESH-TOKEN"


def _client(spin: str = "1234"):
    from custom_components.vag_connect.cariad.api.vw_na import VWNAClient

    client = VWNAClient.__new__(VWNAClient)
    client._base = "https://example.test"
    client._vin_to_uuid = {_VIN: _UUID}
    client._vin_to_model = {}
    client._vin_to_nickname = {}
    client._user_id = _USER_ID
    client._spin = spin
    client._tokens = _FakeTokens()
    client.vw_na_data_forbidden = False
    client.vw_na_data_forbidden_reason = ""
    client._last_privileges_status = None
    client._read_session_tokens = {}
    client._spin_read_session_disabled = False
    client._spin_read_warned = False
    client._bare_403_streak = 0
    return client


def _api_error(status: int, body: str = "forbidden"):
    from custom_components.vag_connect.cariad.exceptions import APIError

    return APIError(status, "https://example.test/x", body)


# ---------------------------------------------------------------------------
# 1) SPIN read-auth happy path
# ---------------------------------------------------------------------------


class TestReadSessionHappyPath:
    @pytest.mark.asyncio
    async def test_carnet_token_used_as_bearer_on_reads(self):
        client = _client(spin="1234")
        future_exp = (datetime.now(tz=timezone.utc) + timedelta(hours=1)).timestamp()
        carnet_jwt = _make_jwt(future_exp)
        challenge = "deadbeefchallenge"
        # v2.29.x — lowercase hex is the primary casing (VW's own app form).
        expected_hash = hashlib.sha512(
            f"{challenge}.1234".encode("utf-8")
        ).hexdigest()

        get_calls: list[tuple[str, dict]] = []
        post_calls: list[tuple[str, dict]] = []

        async def fake_request(method, url, retry=True, _carnet_auth=False, **kwargs):
            if method == "GET" and url.endswith("/challenge"):
                return {"data": {"challenge": challenge, "remainingTries": 5}}
            if method == "POST" and url.endswith(f"/vehicle/{_UUID}/session"):
                post_calls.append((url, kwargs))
                return {"data": {"carnetVehicleToken": carnet_jwt}}
            # data reads
            get_calls.append((url, {"headers": kwargs.get("headers"),
                                    "_carnet_auth": _carnet_auth}))
            if "/rvs/" in url:
                return {"powerStatus": {}}
            return {}

        client._request = fake_request  # type: ignore[method-assign]
        client.get_subscription_privileges = AsyncMock(return_value={})  # type: ignore[method-assign]

        await client.get_status(_VIN)

        # session POST carried the peer body (idToken / spinHash / tsp=WCT)
        assert len(post_calls) == 1
        body = post_calls[0][1]["json"]
        assert body["idToken"] == "ID-TOKEN"
        assert body["spinHash"] == expected_hash
        assert body["tsp"] == "WCT"

        # all 3 data reads authorised with the carnet Bearer + peer headers
        assert len(get_calls) == 3
        for _url, info in get_calls:
            hdr = info["headers"]
            assert hdr["Authorization"] == f"Bearer {carnet_jwt}"
            assert hdr["User-Agent"] == "Car-Net/60 CFNetwork/1121.2.2 Darwin/19.3.0"
            assert hdr["content-version"] == "1"
            assert info["_carnet_auth"] is True

        # token cached for reuse
        assert client._read_session_tokens[_UUID][0] == carnet_jwt
        assert client.vw_na_data_forbidden is False


# ---------------------------------------------------------------------------
# 2) No S-PIN -> falls back to access_token, NO SPIN calls
# ---------------------------------------------------------------------------


class TestNoSpinFallback:
    @pytest.mark.asyncio
    async def test_no_spin_uses_access_token_no_challenge(self):
        client = _client(spin="")  # no S-PIN configured

        spin_urls: list[str] = []
        read_carnet_flags: list[bool] = []

        async def fake_request(method, url, retry=True, _carnet_auth=False, **kwargs):
            if "/ss/v1/user/" in url:
                spin_urls.append(url)
            else:
                read_carnet_flags.append(_carnet_auth)
            if "/rvs/" in url:
                return {"powerStatus": {}}
            return {}

        client._request = fake_request  # type: ignore[method-assign]
        client.get_subscription_privileges = AsyncMock(return_value={})  # type: ignore[method-assign]

        await client.get_status(_VIN)

        # NO challenge / session calls were made
        assert spin_urls == []
        # all reads went the plain access_token path (no carnet auth)
        assert read_carnet_flags and all(f is False for f in read_carnet_flags)


# ---------------------------------------------------------------------------
# 3) SPIN session failure -> fallback + no retry-loop
# ---------------------------------------------------------------------------


class TestSessionFailureNoRetryLoop:
    @pytest.mark.asyncio
    async def test_session_403_disables_and_falls_back(self, caplog):
        client = _client(spin="9999")  # wrong S-PIN

        challenge_calls = {"n": 0}
        session_calls = {"n": 0}
        read_carnet_flags: list[bool] = []

        async def fake_request(method, url, retry=True, _carnet_auth=False, **kwargs):
            if url.endswith("/challenge"):
                challenge_calls["n"] += 1
                return {"data": {"challenge": "chal", "remainingTries": 5}}
            if url.endswith("/session"):
                session_calls["n"] += 1
                raise _api_error(403, "wrong spin")
            read_carnet_flags.append(_carnet_auth)
            if "/rvs/" in url:
                return {"powerStatus": {}}
            return {}

        client._request = fake_request  # type: ignore[method-assign]
        client.get_subscription_privileges = AsyncMock(return_value={})  # type: ignore[method-assign]

        # First poll: lowercase session(403) -> fresh challenge + uppercase
        # session(403) -> BOTH casings rejected -> disable, reads via access_token.
        # v2.29.x: the lowercase→uppercase fallback means 2 challenges + 2 sessions
        # on the failing poll (each on a fresh single-use challenge).
        await client.get_status(_VIN)
        assert challenge_calls["n"] == 2
        assert session_calls["n"] == 2
        assert client._spin_read_session_disabled is True
        assert all(f is False for f in read_carnet_flags)
        assert client._spin_read_warned is True

        # Second poll: MUST NOT re-challenge or re-session (no try-burning loop)
        read_carnet_flags.clear()
        await client.get_status(_VIN)
        assert challenge_calls["n"] == 2  # unchanged
        assert session_calls["n"] == 2  # unchanged
        assert all(f is False for f in read_carnet_flags)

    @pytest.mark.asyncio
    async def test_lowercase_403_then_uppercase_succeeds(self):
        """v2.29.x — lowercase is tried first; if VW rejects it (401/403) the
        legacy uppercase casing is retried on a fresh challenge and, when it
        succeeds, yields the carnet token (no disable)."""
        client = _client(spin="1234")
        future_exp = (datetime.now(tz=timezone.utc) + timedelta(hours=1)).timestamp()
        carnet_jwt = _make_jwt(future_exp)
        challenge = "chal-xyz"
        lower = hashlib.sha512(f"{challenge}.1234".encode("utf-8")).hexdigest()
        upper = lower.upper()
        seen_hashes: list[str] = []

        async def fake_request(method, url, retry=True, _carnet_auth=False, **kwargs):
            if url.endswith("/challenge"):
                return {"data": {"challenge": challenge, "remainingTries": 5}}
            if url.endswith("/session"):
                h = kwargs["json"]["spinHash"]
                seen_hashes.append(h)
                if h == lower:
                    raise _api_error(403, "wrong casing")
                return {"data": {"carnetVehicleToken": carnet_jwt}}
            if "/rvs/" in url:
                return {"powerStatus": {}}
            return {}

        client._request = fake_request  # type: ignore[method-assign]
        client.get_subscription_privileges = AsyncMock(return_value={})  # type: ignore[method-assign]

        await client.get_status(_VIN)
        # lowercase tried first, then uppercase which succeeded
        assert seen_hashes == [lower, upper]
        assert client._spin_read_session_disabled is False
        assert client._read_session_tokens[_UUID][0] == carnet_jwt

    @pytest.mark.asyncio
    async def test_low_remaining_tries_aborts_without_session(self):
        client = _client(spin="1234")
        challenge_calls = {"n": 0}
        session_calls = {"n": 0}

        async def fake_request(method, url, retry=True, _carnet_auth=False, **kwargs):
            if url.endswith("/challenge"):
                challenge_calls["n"] += 1
                # only 1 try left -> must NOT spend it
                return {"data": {"challenge": "chal", "remainingTries": 1}}
            if url.endswith("/session"):
                session_calls["n"] += 1
                return {"data": {"carnetVehicleToken": "x"}}
            if "/rvs/" in url:
                return {"powerStatus": {}}
            return {}

        client._request = fake_request  # type: ignore[method-assign]
        client.get_subscription_privileges = AsyncMock(return_value={})  # type: ignore[method-assign]

        await client.get_status(_VIN)
        assert challenge_calls["n"] == 1
        assert session_calls["n"] == 0  # never POSTed the session
        assert client._spin_read_session_disabled is True


# ---------------------------------------------------------------------------
# 4) carnetVehicleToken cached (second poll doesn't re-challenge)
# ---------------------------------------------------------------------------


class TestTokenCaching:
    @pytest.mark.asyncio
    async def test_second_poll_reuses_cached_token(self):
        client = _client(spin="1234")
        future_exp = (datetime.now(tz=timezone.utc) + timedelta(hours=1)).timestamp()
        carnet_jwt = _make_jwt(future_exp)
        challenge_calls = {"n": 0}
        session_calls = {"n": 0}
        read_tokens: list[str] = []

        async def fake_request(method, url, retry=True, _carnet_auth=False, **kwargs):
            if url.endswith("/challenge"):
                challenge_calls["n"] += 1
                return {"data": {"challenge": "chal", "remainingTries": 5}}
            if url.endswith("/session"):
                session_calls["n"] += 1
                return {"data": {"carnetVehicleToken": carnet_jwt}}
            if _carnet_auth:
                read_tokens.append(kwargs["headers"]["Authorization"])
            if "/rvs/" in url:
                return {"powerStatus": {}}
            return {}

        client._request = fake_request  # type: ignore[method-assign]
        client.get_subscription_privileges = AsyncMock(return_value={})  # type: ignore[method-assign]

        await client.get_status(_VIN)
        await client.get_status(_VIN)

        # Exchange ran ONCE; second poll reused the cached token.
        assert challenge_calls["n"] == 1
        assert session_calls["n"] == 1
        # Both polls' reads (6 total) carried the carnet Bearer.
        assert len(read_tokens) == 6
        assert all(t == f"Bearer {carnet_jwt}" for t in read_tokens)


# ---------------------------------------------------------------------------
# 5) Persistence counter surfaces the repair after N bare-403s
# ---------------------------------------------------------------------------


class TestBare403Persistence:
    @pytest.mark.asyncio
    async def test_persistent_bare_403_surfaces_after_threshold(self):
        from custom_components.vag_connect.cariad.api.vw_na import VWNAClient

        client = _client(spin="")  # no S-PIN: reads go plain, stay bare-403
        # All data reads bare-403; privileges succeed with an ACTIVE sub so the
        # 403 stays classified bare-403 (no entitlement / attestation marker).
        client._request = AsyncMock(side_effect=_api_error(403, "Forbidden"))  # type: ignore[method-assign]
        client.get_subscription_privileges = AsyncMock(
            return_value={"subscription_active": True, "capabilities_count": 5}
        )  # type: ignore[method-assign]

        threshold = VWNAClient._BARE_403_PERSIST_THRESHOLD

        # Polls 1..threshold-1: silent (transient-tolerant).
        for i in range(threshold - 1):
            await client.get_status(_VIN)
            assert client.vw_na_data_forbidden is False, f"surfaced too early at poll {i+1}"
            assert client.vw_na_data_forbidden_reason == "bare-403"

        # Poll `threshold`: now surfaces.
        await client.get_status(_VIN)
        assert client.vw_na_data_forbidden is True
        assert client.vw_na_data_forbidden_reason == "bare-403"

    @pytest.mark.asyncio
    async def test_recovery_resets_streak(self):
        client = _client(spin="")
        # 2 bare-403 polls
        client._request = AsyncMock(side_effect=_api_error(403, "Forbidden"))  # type: ignore[method-assign]
        client.get_subscription_privileges = AsyncMock(
            return_value={"subscription_active": True}
        )  # type: ignore[method-assign]
        await client.get_status(_VIN)
        await client.get_status(_VIN)
        assert client._bare_403_streak == 2

        # A successful read clears the streak.
        client._request = AsyncMock(return_value={"powerStatus": {}})  # type: ignore[method-assign]
        await client.get_status(_VIN)
        assert client._bare_403_streak == 0
        assert client.vw_na_data_forbidden is False
