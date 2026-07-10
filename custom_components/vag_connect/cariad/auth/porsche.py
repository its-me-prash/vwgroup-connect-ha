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

v2.17.2 — the recipe above is now IMPLEMENTED as ``PorscheOneDeviceAuth``
(below): OIDC-discovery-driven device grant + token poll + refresh, unit-tested
against mocked endpoints. Two gates remain before Porsche can be un-flagged, and
both need a Porsche One owner: (a) end-to-end verification against the live
PingFederate tenant (the clientId host + exact discovery shape can't be probed
off a real account), and (b) wiring the interactive user-code/QR step into the
config flow (the current ``PorscheClient`` still drives the legacy Auth0
``PorscheAuth`` password flow — swapping it in is deliberately deferred so this
release ships no unverified auth path). Self-contained: touches neither the old
Auth0 flow nor the shared device-grant used by the 4 working VW-Group brands.

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


# ── Porsche One — PingFederate RFC-8628 device grant (v2.17.2) ────────────────
# DEX-grounded from the com.porsche.one 12.24.27 sweep. Public client, no
# secret / captcha / Play-Integrity on the auth path. See the module docstring
# for the two remaining live-gates (end-to-end verify + config-flow QR wiring).

_PF_DISCOVERY_URL = "https://identity.porsche.com/.well-known/openid-configuration"
# clientId is fetched at runtime (no hardcoded Auth0 client). Host is the
# Porsche mobile API; kept as a constant so it's correctable once verified
# against a real Porsche One account.
_PF_CLIENT_ID_URL = "https://api.ppa.porsche.com/v1/mobile/clientId"
_PF_DEVICE_SCOPE = "openid profile email ssodb mbb offline_access"
_PF_DEVICE_GRANT = "urn:ietf:params:oauth:grant-type:device_code"
_PORSCHE_ONE_UA = "PorscheOne/12.24.27 (Android)"


class PorscheOneDeviceAuth:
    """Porsche One (com.porsche.one) PingFederate RFC-8628 device grant.

    Interactive: :meth:`request_device_code` returns a ``user_code`` +
    ``verification_uri`` the owner approves in a browser, then
    :meth:`poll_once` is called until it returns a :class:`TokenSet`.

    EXPERIMENTAL / not yet wired — implemented per the DEX-grounded recipe and
    unit-tested against mocked endpoints, but not verified end-to-end (needs a
    Porsche One owner). Self-contained: does not touch the legacy Auth0
    :class:`PorscheAuth` nor the shared VW-Group device grant.
    """

    def __init__(
        self,
        session: ClientSession,
        *,
        client_id_url: str = _PF_CLIENT_ID_URL,
        discovery_url: str = _PF_DISCOVERY_URL,
    ) -> None:
        self._session = session
        self._client_id_url = client_id_url
        self._discovery_url = discovery_url
        self._client_id: str = ""
        self._device_endpoint: str = ""
        self._token_endpoint: str = ""

    async def prepare(self) -> None:
        """Fetch the runtime client_id + resolve the PingFederate device /
        token endpoints via OIDC discovery. Idempotent."""
        if not self._client_id:
            self._client_id = await self._fetch_client_id()
        if not (self._device_endpoint and self._token_endpoint):
            await self._discover()

    async def _fetch_client_id(self) -> str:
        async with self._session.get(
            self._client_id_url,
            timeout=_AUTH_TIMEOUT,
            headers={"User-Agent": _PORSCHE_ONE_UA, "Accept": "application/json"},
        ) as resp:
            if resp.status != 200:
                raise AuthenticationError(
                    f"Porsche One clientId fetch failed ({resp.status})"
                )
            data = await resp.json()
        # Accept a bare string or a {"clientId": "..."} envelope.
        client_id = data if isinstance(data, str) else (
            data.get("clientId") or data.get("client_id") or ""
        )
        if not client_id:
            raise AuthenticationError("Porsche One clientId missing in response")
        return client_id

    async def _discover(self) -> None:
        async with self._session.get(
            self._discovery_url,
            timeout=_AUTH_TIMEOUT,
            headers={"User-Agent": _PORSCHE_ONE_UA, "Accept": "application/json"},
        ) as resp:
            if resp.status != 200:
                raise AuthenticationError(
                    f"Porsche One OIDC discovery failed ({resp.status})"
                )
            doc = await resp.json()
        device = doc.get("device_authorization_endpoint")
        token = doc.get("token_endpoint")
        if not device or not token:
            raise AuthenticationError(
                "Porsche One discovery missing device/token endpoint"
            )
        self._device_endpoint = device
        self._token_endpoint = token

    async def request_device_code(self) -> dict[str, object]:
        """RFC 8628 §3.1 — start device authorization. Returns the device_code,
        user_code, verification_uri(_complete), poll interval and expiry."""
        await self.prepare()
        async with self._session.post(
            self._device_endpoint,
            timeout=_AUTH_TIMEOUT,
            data={"client_id": self._client_id, "scope": _PF_DEVICE_SCOPE},
            headers={
                "User-Agent": _PORSCHE_ONE_UA,
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": "application/json",
            },
        ) as resp:
            if resp.status != 200:
                body = await resp.text()
                raise AuthenticationError(
                    f"Porsche One device authorization failed "
                    f"({resp.status}): {body[:200]}"
                )
            data = await resp.json()
        if "device_code" not in data or "user_code" not in data:
            raise AuthenticationError(
                "Porsche One device authorization response incomplete"
            )
        return {
            "device_code": data["device_code"],
            "user_code": data["user_code"],
            "verification_uri": data.get("verification_uri", ""),
            "verification_uri_complete": data.get("verification_uri_complete", ""),
            "interval": int(data.get("interval", 5)),
            "expires_in": int(data.get("expires_in", 600)),
        }

    async def poll_once(self, device_code: str) -> TokenSet | None:
        """RFC 8628 §3.4 — one token poll. Returns a TokenSet once the user has
        approved; ``None`` while still pending (``authorization_pending`` /
        ``slow_down``); raises AuthenticationError on a terminal error
        (``access_denied`` / ``expired_token``)."""
        await self.prepare()
        async with self._session.post(
            self._token_endpoint,
            timeout=_AUTH_TIMEOUT,
            data={
                "grant_type": _PF_DEVICE_GRANT,
                "client_id": self._client_id,
                "device_code": device_code,
            },
            headers={
                "User-Agent": _PORSCHE_ONE_UA,
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": "application/json",
            },
        ) as resp:
            data = await resp.json()
            if resp.status == 200:
                return TokenSet(
                    access_token=data["access_token"],
                    refresh_token=data.get("refresh_token", ""),
                    id_token=data.get("id_token", ""),
                )
            error = str(data.get("error", ""))
        if error in ("authorization_pending", "slow_down"):
            return None
        raise AuthenticationError(f"Porsche One device grant rejected: {error}")

    async def refresh(self, refresh_token: str) -> TokenSet:
        """Refresh via the PingFederate token endpoint."""
        await self.prepare()
        async with self._session.post(
            self._token_endpoint,
            timeout=_AUTH_TIMEOUT,
            data={
                "grant_type": "refresh_token",
                "client_id": self._client_id,
                "refresh_token": refresh_token,
            },
            headers={
                "User-Agent": _PORSCHE_ONE_UA,
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": "application/json",
            },
        ) as resp:
            if resp.status == 401:
                raise TokenExpiredError("Porsche One refresh token expired")
            if resp.status != 200:
                body = await resp.text()
                raise AuthenticationError(
                    f"Porsche One refresh failed ({resp.status}): {body[:200]}"
                )
            data = await resp.json()
        return TokenSet(
            access_token=data["access_token"],
            refresh_token=data.get("refresh_token", refresh_token),
            id_token=data.get("id_token", ""),
        )
