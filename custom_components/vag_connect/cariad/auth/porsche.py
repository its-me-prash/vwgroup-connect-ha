# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Porsche Connect authentication — EXPERIMENTAL / superseded stack.

⚠️ v2.17.1 (#666 fresh APK sweep): this module's ACTIVE flow targets the OLD
My-Porsche Auth0 password stack (identity.porsche.com /authorize + /oauth/token,
hardcoded Auth0 client XhygisuebbrqQ80byOuU5VncxLIm8E6H,
my-porsche-app://auth0/callback). The live app is **Porsche One**
(com.porsche.one 12.24.27), and that password flow returns "wrong credentials
or captcha required" on current accounts (see #13). Porsche stays experimental
in the brand picker until the device-grant below is wired in.

v2.26.0 (#13, re-verified against the current com.porsche.one DEX + LIVE probes):
  - identity.porsche.com is an **Auth0** tenant, NOT PingFederate (an earlier
    note here was wrong). Live .well-known/openid-configuration confirms:
    device_authorization_endpoint = https://identity.porsche.com/oauth/device/code,
    token_endpoint = https://identity.porsche.com/oauth/token, and
    "urn:ietf:params:oauth:grant-type:device_code" IS in grant_types_supported.
    So the device grant is viable and our discovery-driven code resolves the
    right endpoints without a code change.
  - scope="openid profile email ssodb mbb offline_access" is confirmed present
    in the current DEX (verbatim).
  - The client_id is genuinely fetched at RUNTIME (DEX has a whole
    clientIdProvider/clientIdService/clientIdCache + ClientIdDto); there is no
    static Porsche One Auth0 client_id literal to hardcode.
  - LIVE BLOCKER: GET https://api.ppa.porsche.com/v1/mobile/clientId returns 502
    for us (Azure Application Gateway). The host is alive (/app/connect gives a
    clean 401), and the DEX shows the app redacts X-API-KEY / X-Client-ID /
    X-Auth-Token headers in its logs, so that endpoint almost certainly needs an
    X-API-KEY we do not send. The key is not a plain DEX literal (likely
    assembled or in a resource/native lib). So the clientId fetch, and therefore
    the whole device grant, cannot be validated off a real account: the next
    step is a Porsche One owner (#13) either running a test build so its real
    error tells us what the endpoint wants, or capturing one login.

REBUILD RECIPE (Auth0 device grant, RFC 8628):
  1. clientId at runtime: GET /v1/mobile/clientId (needs the app's X-API-KEY).
  2. OIDC discovery: GET https://identity.porsche.com/.well-known/openid-configuration
     → device_authorization_endpoint + token_endpoint (Auth0).
  3. Device authorization: POST device_authorization_endpoint with client_id +
     scope → device_code/user_code/verification_uri.
  4. Poll token_endpoint (grant_type=urn:ietf:params:oauth:grant-type:device_code).
  Commands then run against api.ppa.porsche.com/app/connect/*.

v2.17.2 — the recipe is IMPLEMENTED as ``PorscheOneDeviceAuth`` (below):
discovery-driven device grant + token poll + refresh, unit-tested against mocked
endpoints. Two gates remain, both needing a Porsche One owner: (a) the live
clientId endpoint (blocked above), and (b) wiring the interactive user-code/QR
step into the config flow (the current ``PorscheClient`` still drives the legacy
password flow — swapping it in is deferred so no unverified auth path ships).
Self-contained: touches neither the old Auth0 password flow nor the shared
device-grant used by the 4 working VW-Group brands.

Old flow based on CJNE/pyporscheconnectapi (Apache-2.0), aiohttp reimpl.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import re
from urllib.parse import parse_qs, urljoin, urlsplit

from aiohttp import ClientTimeout, ClientSession

from ..exceptions import AuthenticationError, TokenExpiredError
from ..models import TokenSet

_AUTH_TIMEOUT = ClientTimeout(total=30)  # per-request timeout for auth flows
_MAX_AUTH_REDIRECTS = 10  # bound the Auth0 resume-hop chain so it cannot loop

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


def _oauth_error_code(body: str) -> str:
    """Best-effort OAuth ``error`` code from a token-endpoint body.

    Redaction helper (#1355): the raw Auth0 token-endpoint body can echo
    request context / secrets, so it must never reach an exception message a
    tester copy-pastes. Return only the standardized short ``error`` code
    (e.g. ``invalid_grant``) — never the raw body or ``error_description``.
    """
    try:
        parsed = json.loads(body)
    except (ValueError, TypeError):
        return "non-JSON body"
    if isinstance(parsed, dict) and parsed.get("error"):
        return str(parsed["error"])
    return "no error field"


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
        # b11 (#1337 Hollywoodchaos) — the Porsche auth path emitted zero log
        # lines, so a user's debug capture showed nothing but the final warning.
        # Log status + whether a redirect was handed back (hostnames/statuses
        # only — never the URL query, code, state, e-mail or password).
        _LOGGER.debug(
            "Porsche auth: password POST → HTTP %s, %s",
            resp.status,
            "redirect handed back" if location
            else "NO Location header (Auth0 rendered a page — likely a "
                 "captcha/consent step the headless flow can't clear)",
        )

        # Step 4: follow the Auth0 redirect chain to the code.
        #
        # In Auth0's Identifier-First flow the password POST does NOT redirect
        # straight to my-porsche-app://auth0/callback. Its Location is a *resume*
        # path (e.g. /authorize/resume?state=...), and the code only appears
        # after following that hop (and sometimes a second one). The old code
        # required the callback immediately, so it ALWAYS fell through to
        # "wrong credentials or captcha" even with correct credentials — a
        # self-inflicted failure independent of the Porsche One migration.
        code = await self._follow_to_code(location, password_url)
        if not code:
            raise AuthenticationError(
                "Porsche auth failed — no authorization code after login "
                "(wrong credentials, or a captcha/consent step we do not handle)"
            )

        # Step 5: Exchange code for tokens
        return await self._exchange_code(code, verifier)

    async def _follow_to_code(self, location: str, base_url: str) -> str | None:
        """Walk the redirect chain from the password POST to the auth code.

        Each ``Location`` may be relative (``/authorize/resume?...``) or
        absolute (Auth0 sometimes bounces to ``https://my.porsche.com/?iss=``),
        so it is resolved with ``urljoin`` against the URL it came from rather
        than string-formatted. The loop is bounded so a redirect cycle cannot
        hang the login.
        """
        current_base = base_url
        for _ in range(_MAX_AUTH_REDIRECTS):
            if not location:
                return None
            code = self._extract_code(location)
            if code:
                return code
            target = urljoin(current_base, location)
            # The app-scheme callback is terminal; if it carried no code the
            # chain has failed rather than continuing.
            if target.startswith(_REDIRECT_URI):
                return self._extract_code(target)
            async with self._session.get(
                target,
                timeout=_AUTH_TIMEOUT,
                headers={"User-Agent": _USER_AGENT},
                allow_redirects=False,
            ) as resp:
                # b11 (#1337) — trace each hop by host + status only (never the
                # full URL, which carries state/code).
                _LOGGER.debug(
                    "Porsche auth: redirect hop → host=%s HTTP %s",
                    urlsplit(target).hostname or "?", resp.status,
                )
                # A 200 here means Auth0 rendered a page instead of redirecting
                # — typically the captcha/consent screen — so there is no code.
                if resp.status not in (301, 302, 303, 307, 308):
                    _LOGGER.debug(
                        "Porsche auth: hop returned HTTP %s (a rendered page, not "
                        "a redirect) — no authorization code. This is typically "
                        "the captcha/consent screen the Porsche One migration "
                        "requires, which the headless login cannot clear.",
                        resp.status,
                    )
                    return None
                current_base = target
                location = resp.headers.get("Location", "")
        return None

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
                raise AuthenticationError(
                    f"Porsche token exchange failed {resp.status}: "
                    f"{_oauth_error_code(body)}"
                )
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


# ── Porsche One — Auth0 RFC-8628 device grant (v2.17.2) ────────────────
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
    """Porsche One (com.porsche.one) Auth0 RFC-8628 device grant.

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
        """Fetch the runtime client_id + resolve the Auth0 device /
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
                    f"({resp.status}): {_oauth_error_code(body)}"
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
        """Refresh via the Auth0 token endpoint."""
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
                    f"Porsche One refresh failed ({resp.status}): "
                    f"{_oauth_error_code(body)}"
                )
            data = await resp.json()
        return TokenSet(
            access_token=data["access_token"],
            refresh_token=data.get("refresh_token", refresh_token),
            id_token=data.get("id_token", ""),
        )
