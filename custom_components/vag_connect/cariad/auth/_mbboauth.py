# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""MBB OAuth token exchange — the legacy stack that PREDATES the App-Check wall.

The MBB ("msg" / Car-Net) OAuth backend at
``mbboauth-1d.prd.ece.vwg-connect.com/mbbcoauth`` is the pre-CARIAD generation.
A hybrid ``id_token`` minted at ``identity.vwgroup.io`` can be exchanged here
for a **durable, refreshable** MBB bearer — which is exactly the piece missing
for (a) two-way on the brands whose modern CARIAD-BFF token path is gated
behind Google Play-Integrity attestation (VW EU), and (b) legacy MBB-backed
combustion/PHEV cars that the modern IDK apps never onboard.

Grounded, not guessed:
- Token path ``/mbbcoauth/mobile/oauth2/v1/token``, revoke
  ``/mbbcoauth/mobile/oauth2/v1/revoke``, header ``X-Client-Id``, scope
  ``sc2:fal`` and the shared client ``9523ee15-…`` were all read from the
  We Connect e-Remote (``de.volkswagen.carnet.eu.eremote``) and SEAT/CUPRA
  ``mod2connectapp`` DEX in the 2026-06 app-atlas.
- A 2026-06 live probe of ``/mbbcoauth/mobile/oauth2/v1/token`` returned
  **HTTP 403** (auth-reject), NOT a 404 — i.e. the endpoint is live, the path
  is correct, and it rejects on missing credentials rather than behind the
  Play-Integrity wall that blocks the CARIAD BFF.

Scope of THIS module: the token exchange + refresh + revoke only (the auth
foundation). The MBB read path (homeRegion → VSR/FAL) already lives in
``cariad/_mbb.py``; command (S-PIN secure-token) wiring is a separate step.
Nothing here is wired into the live auth chain yet — it is exercised by the
local DAG test harness (``scripts/mbb_dag_test.py``) until a tester confirms a
real token exchange against their account.
"""

from __future__ import annotations

import base64
import json
import time
from dataclasses import dataclass
from typing import Any

from aiohttp import ClientError, ClientSession, ClientTimeout

from ..exceptions import AuthenticationError

# ── Endpoints (DEX + live-probe confirmed 2026-06) ──────────────────────────
MBB_OAUTH_BASE = "https://mbboauth-1d.prd.ece.vwg-connect.com/mbbcoauth"
MBB_TOKEN_URL = f"{MBB_OAUTH_BASE}/mobile/oauth2/v1/token"
MBB_REVOKE_URL = f"{MBB_OAUTH_BASE}/mobile/oauth2/v1/revoke"
# Classic Car-Net device-registration step — POST the hybrid id_token + app
# metadata here to obtain the per-device ``X-Client-Id`` that the token
# exchange + refresh + VSR reads must carry. Grounded in the We Connect
# e-Remote DEX (``de.volkswagen.carnet.eu.eremote``) and proven live in
# ``scripts/mbb_dag_test.py`` (2026-06-20 — HTTP 200 + durable refresh_token).
MBB_REGISTER_URL = f"{MBB_OAUTH_BASE}/mobile/register/v1"
# We Connect e-Remote app metadata for the register body (the app whose
# device-grant client mints the ``mbb``-scoped id_token).
_MBB_APP_ID = "de.volkswagen.carnet.eu.eremote"
_MBB_APP_NAME = "WeConnect"
_MBB_APP_VERSION = "5.17.6"
_MBB_REGISTER_UA = f"WeConnect/{_MBB_APP_VERSION} (Android 14; okhttp/3.14.9)"

# Shared legacy MBB client present in BOTH We Connect e-Remote and the
# SEAT/CUPRA mod2 apps (atlas ``_SHARED_UUIDS``). The MBB ``X-Client-Id`` is a
# bare UUID (no ``@apps_vw-dilab_com`` suffix) — a DIFFERENT identifier from
# the IDK/dilab OAuth client.
MBB_SHARED_CLIENT_ID = "9523ee15-f6e0-4eb9-9907-59d058d7e16e"

_MBB_SCOPE = "sc2:fal"
_TIMEOUT = ClientTimeout(total=20)
_UA = "okhttp/3.14.9"


@dataclass
class MbbTokenSet:
    """Token set minted by the MBB OAuth backend.

    Unlike the CARIAD hybrid token, this one carries a usable
    ``refresh_token`` (the whole point — durable, no ~2h re-login).
    """

    access_token: str
    refresh_token: str
    token_type: str = "Bearer"
    expires_at: float = 0.0  # Unix ts; 0 = unknown

    def is_valid(self) -> bool:
        return bool(self.access_token)

    def needs_refresh(self) -> bool:
        if not self.expires_at:
            return False
        return time.time() >= self.expires_at - 60


def _headers(client_id: str) -> dict[str, str]:
    return {
        "X-Client-Id": client_id,
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept": "application/json",
        "User-Agent": _UA,
    }


def _parse_token_payload(payload: dict[str, Any]) -> MbbTokenSet:
    access = payload.get("access_token", "")
    if not access:
        raise AuthenticationError("MBB token response missing access_token")
    expires_in = payload.get("expires_in")
    expires_at = time.time() + float(expires_in) if expires_in else 0.0
    return MbbTokenSet(
        access_token=access,
        refresh_token=payload.get("refresh_token", ""),
        token_type=payload.get("token_type", "Bearer"),
        expires_at=expires_at,
    )


async def _post_token(
    session: ClientSession, data: dict[str, str], client_id: str
) -> MbbTokenSet:
    try:
        async with session.post(
            MBB_TOKEN_URL, data=data, headers=_headers(client_id), timeout=_TIMEOUT
        ) as resp:
            body = await resp.text()
            if resp.status != 200:
                raise AuthenticationError(
                    f"MBB token exchange HTTP {resp.status}: {body[:400]}"
                )
            try:
                payload = json.loads(body)
            except ValueError as exc:
                raise AuthenticationError(
                    f"MBB token response not JSON: {body[:120]}"
                ) from exc
            return _parse_token_payload(payload)
    except ClientError as exc:
        raise AuthenticationError(f"MBB token exchange failed: {exc}") from exc


async def exchange_id_token(
    session: ClientSession,
    id_token: str,
    *,
    client_id: str = MBB_SHARED_CLIENT_ID,
    scope: str = _MBB_SCOPE,
) -> MbbTokenSet:
    """Exchange a hybrid ``identity.vwgroup.io`` id_token for an MBB bearer.

    Classic Car-Net/MBB grant: ``grant_type=id_token`` with the id_token in the
    ``token`` form field + ``scope=sc2:fal`` and the ``X-Client-Id`` header.
    """
    if not id_token:
        raise AuthenticationError("MBB exchange requires a non-empty id_token")
    data = {"grant_type": "id_token", "token": id_token, "scope": scope}
    return await _post_token(session, data, client_id)


async def refresh(
    session: ClientSession,
    refresh_token: str,
    *,
    client_id: str = MBB_SHARED_CLIENT_ID,
) -> MbbTokenSet:
    """Refresh an MBB bearer using its refresh_token (the durable path)."""
    if not refresh_token:
        raise AuthenticationError("MBB refresh requires a non-empty refresh_token")
    data = {"grant_type": "refresh_token", "token": refresh_token}
    return await _post_token(session, data, client_id)


def jwt_aud(id_token: str) -> str | None:
    """Return the (first) ``aud`` claim of a JWT id_token, or None.

    Decodes ONLY the public payload segment — never the signature, and
    never logs the raw token. The MBB token exchange requires
    ``id_token.aud == X-Client-Id``; for the ``mbb``-scoped id_token the
    ``aud`` is multi-valued and includes the MBB backend audience, so we
    pin the registered client to this value.
    """
    try:
        payload_b64 = id_token.split(".")[1]
        payload_b64 += "=" * (-len(payload_b64) % 4)  # pad to 4
        claims = json.loads(base64.urlsafe_b64decode(payload_b64))
    except (ValueError, IndexError, json.JSONDecodeError):
        return None
    aud = claims.get("aud")
    if isinstance(aud, list):
        return aud[0] if aud else None
    return aud if isinstance(aud, str) else None


async def register(
    session: ClientSession,
    id_token: str,
    *,
    desired_client_id: str | None = None,
) -> tuple[str | None, str | None]:
    """Register a per-device MBB client and return ``(client_id, secret)``.

    The classic Car-Net flow POSTs the hybrid id_token + the e-Remote app
    metadata to ``/mobile/register/v1`` and gets back a fresh per-device
    ``client_id`` (the value used as ``X-Client-Id`` for the subsequent
    token exchange). The MBB backend binds the registered client to the
    id_token's ``aud``, so we pin ``client_id`` in the body to the aud
    (passed as ``desired_client_id``) when known.

    A public client — the register response carries NO ``client_secret``.
    Raises ``AuthenticationError`` on a non-2xx response (never prints the
    token or the body verbatim beyond a short truncated diagnostic).
    """
    if not id_token:
        raise AuthenticationError("MBB register requires a non-empty id_token")
    body: dict[str, Any] = {
        "client_name": "vag-connect-mbb",
        "platform": "google",
        "client_brand": "VW",
        "appId": _MBB_APP_ID,
        "appName": _MBB_APP_NAME,
        "appVersion": _MBB_APP_VERSION,
        "id_token": id_token,
    }
    if desired_client_id:
        body["client_id"] = desired_client_id
        body["scope"] = _MBB_SCOPE
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": _MBB_REGISTER_UA,
        "Authorization": f"Bearer {id_token}",
    }
    try:
        async with session.post(
            MBB_REGISTER_URL, json=body, headers=headers, timeout=_TIMEOUT
        ) as resp:
            text = await resp.text()
            if resp.status not in (200, 201):
                raise AuthenticationError(
                    f"MBB register HTTP {resp.status}: {text[:200]}"
                )
            try:
                payload = json.loads(text)
            except ValueError as exc:
                raise AuthenticationError(
                    f"MBB register response not JSON: {text[:120]}"
                ) from exc
            return payload.get("client_id"), payload.get("client_secret")
    except ClientError as exc:
        raise AuthenticationError(f"MBB register failed: {exc}") from exc


async def mint_mbb_bearer(
    session: ClientSession,
    id_token: str,
    *,
    registered_client_id: str | None = None,
) -> tuple[MbbTokenSet, str]:
    """Full recipe: register (if needed) then exchange → durable MBB bearer.

    Returns ``(token_set, client_id)`` where ``client_id`` is the
    ``X-Client-Id`` that minted the bearer — the caller MUST persist it,
    because the refresh + every MBB read/command request has to send the
    same client id (a mismatch 403s).

    The MBB backend requires ``id_token.aud == X-Client-Id``. We pin the
    registered client to the id_token's aud and exchange with that same
    value, so a single browser confirm is enough WHEN the backend accepts
    the aud-pinned registration. If a caller already holds a registered
    client (e.g. from a prior ``register`` whose id_token aud matched),
    pass it via ``registered_client_id`` to skip re-registration.
    """
    aud = jwt_aud(id_token)
    client_id = registered_client_id
    if client_id is None:
        reg_client_id, _secret = await register(
            session, id_token, desired_client_id=aud
        )
        client_id = reg_client_id or aud
    if not client_id:
        raise AuthenticationError(
            "MBB mint: no client_id from register and id_token has no aud"
        )
    token_set = await exchange_id_token(session, id_token, client_id=client_id)
    return token_set, client_id
