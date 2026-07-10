# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Porsche Connect authentication — EXPERIMENTAL / superseded stack.

⚠️ v2.17.1 (#666 fresh APK sweep): this module targets the OLD My-Porsche
**Auth0** stack (identity.porsche.com /authorize + /oauth/token, hardcoded
Auth0 client XhygisuebbrqQ80byOuU5VncxLIm8E6H, my-porsche-app://auth0/callback).
The live app is **Porsche One** (com.porsche.one 12.24.27), whose auth is
**PingFederate**, not Auth0 — so this password flow is expected to fail on
current accounts. Porsche is marked experimental in the brand picker until
this is rebuilt.

REBUILD RECIPE (DEX-grounded, feasible off-device — verified in the sweep:
zero client_secret, NO Play-Integrity/AppCheck/captcha on the auth path,
first-class RFC-8628 device grant):
  1. clientId at runtime: GET /v1/mobile/clientId (no hardcoded Auth0 client).
  2. OIDC discovery: GET https://identity.porsche.com/.well-known/openid-configuration
     → device_authorization_endpoint + token_endpoint (PingFederate).
  3. Device authorization (RFC 8628): POST device_authorization_endpoint with
     client_id + scope="openid profile email ssodb mbb offline_access" →
     device_code/user_code/verification_uri (device.identity.porsche.com/activate).
  4. Poll token_endpoint (grant_type=urn:ietf:params:oauth:grant-type:device_code).
  Commands then run against api.ppa.porsche.com/app/connect/*.
Needs a Porsche One owner to verify end-to-end before it's un-flagged — the
rewrite is otherwise ready to build (self-contained; won't touch the shared
device-grant used by the 4 working VW-Group brands).

Old flow based on CJNE/pyporscheconnectapi (Apache-2.0), aiohttp reimpl.
"""

from __future__ import annotations

import base64
import hashlib
import logging
import os
import re
from urllib.parse import parse_qs

from aiohttp import ClientTimeout, ClientSession

from ..exceptions import AuthenticationError, TokenExpiredError
from ..models import TokenSet

_AUTH_TIMEOUT = ClientTimeout(total=30)  # per-request timeout for auth flows

_LOGGER = logging.getLogger(__name__)

_AUTH_SERVER   = "identity.porsche.com"
_AUTH_URL      = f"https://{_AUTH_SERVER}/authorize"
_TOKEN_URL     = f"https://{_AUTH_SERVER}/oauth/token"
_CLIENT_ID     = "XhygisuebbrqQ80byOuU5VncxLIm8E6H"
_REDIRECT_URI  = "my-porsche-app://auth0/callback"
_AUDIENCE      = "https://api.porsche.com"
_USER_AGENT    = "My Porsche/2.1.0 (iPhone; iOS 17.0; Scale/3.00)"

_SCOPE = (
    "openid profile email offline_access mbb ssodb badge vin dealers cars "
    "charging manageCharging plugAndCharge climatisation manageClimatisation "
    "pid:user_profile.porscheid:read pid:user_profile.vehicles:read"
)


def _pkce() -> tuple[str, str]:
    verifier = base64.urlsafe_b64encode(os.urandom(32)).rstrip(b"=").decode()
    digest   = hashlib.sha256(verifier.encode()).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    return verifier, challenge


class PorscheAuth:
    """Auth0 PKCE login for Porsche Connect."""

    def __init__(self, session: ClientSession) -> None:
        self._session = session

    async def authenticate(self, email: str, password: str) -> TokenSet:
        """Full PKCE flow → access_token + refresh_token."""
        verifier, challenge = _pkce()
        state = base64.urlsafe_b64encode(os.urandom(16)).rstrip(b"=").decode()

        # Step 1: Get auth page
        params = {
            "client_id":             _CLIENT_ID,
            "redirect_uri":          _REDIRECT_URI,
            "response_type":         "code",
            "scope":                 _SCOPE,
            "audience":              _AUDIENCE,
            "code_challenge":        challenge,
            "code_challenge_method": "S256",
            "state":                 state,
        }
        async with self._session.get(
            _AUTH_URL,
            timeout=_AUTH_TIMEOUT,
            params=params,
            headers={"User-Agent": _USER_AGENT},
            allow_redirects=True,
        ) as resp:
            await resp.text()
            final_url = str(resp.url)

        # Extract Auth0 state from redirect URL
        state_match = re.search(r'state=([a-zA-Z0-9_\-]+)', final_url)
        if not state_match:
            raise AuthenticationError("Could not extract Auth0 state from login page")
        auth0_state = state_match.group(1)

        # Step 2: POST credentials
        login_url = f"https://{_AUTH_SERVER}/u/login/identifier?state={auth0_state}"
        async with self._session.post(
            login_url,
            timeout=_AUTH_TIMEOUT,
            data={
                "state":       auth0_state,
                "username":    email,
                "js-available":"true",
                "webauthn-available": "true",
                "is-brave":    "false",
                "webauthn-platform-authenticator-available": "false",
                "action":      "default",
            },
            headers={
                "User-Agent":   _USER_AGENT,
                "Content-Type": "application/x-www-form-urlencoded",
            },
            allow_redirects=True,
        ) as resp:
            pass

        # Step 3: POST password
        password_url = f"https://{_AUTH_SERVER}/u/login/password?state={auth0_state}"
        async with self._session.post(
            password_url,
            timeout=_AUTH_TIMEOUT,
            data={
                "state":    auth0_state,
                "username": email,
                "password": password,
                "action":   "default",
            },
            headers={
                "User-Agent":   _USER_AGENT,
                "Content-Type": "application/x-www-form-urlencoded",
            },
            allow_redirects=False,
        ) as resp:
            location = resp.headers.get("Location", "")

        # Extract auth code from redirect
        code = self._extract_code(location)
        if not code:
            raise AuthenticationError(
                "Porsche auth failed — wrong credentials or captcha required"
            )

        # Step 4: Exchange code for tokens
        return await self._exchange_code(code, verifier)

    async def refresh(self, refresh_token: str) -> TokenSet:
        """Refresh tokens using refresh_token."""
        async with self._session.post(
            _TOKEN_URL,
            timeout=_AUTH_TIMEOUT,
            json={
                "grant_type":    "refresh_token",
                "client_id":     _CLIENT_ID,
                "refresh_token": refresh_token,
            },
            headers={"User-Agent": _USER_AGENT},
        ) as resp:
            if resp.status == 401:
                raise TokenExpiredError("Porsche refresh token expired")
            data = await resp.json()

        return TokenSet(
            access_token=data["access_token"],
            refresh_token=data.get("refresh_token", refresh_token),
            id_token=data.get("id_token", ""),
        )

    async def _exchange_code(self, code: str, verifier: str) -> TokenSet:
        async with self._session.post(
            _TOKEN_URL,
            timeout=_AUTH_TIMEOUT,
            json={
                "grant_type":    "authorization_code",
                "client_id":     _CLIENT_ID,
                "code":          code,
                "redirect_uri":  _REDIRECT_URI,
                "code_verifier": verifier,
            },
            headers={"User-Agent": _USER_AGENT},
        ) as resp:
            if resp.status != 200:
                body = await resp.text()
                raise AuthenticationError(f"Porsche token exchange failed {resp.status}: {body[:200]}")
            data = await resp.json()

        return TokenSet(
            access_token=data["access_token"],
            refresh_token=data.get("refresh_token", ""),
            id_token=data.get("id_token", ""),
        )

    @staticmethod
    def _extract_code(location: str) -> str | None:
        prefix = "my-porsche-app://auth0/callback"
        if not location.startswith(prefix):
            return None
        query = location.split("?", 1)[-1] if "?" in location else ""
        params = parse_qs(query)
        codes = params.get("code")
        return codes[0] if codes else None
