"""Audi EU — interactive myAudi Auth0 login (authorization code + PKCE).

#1712 — since 2026-10 the CARIAD BFF refuses the IDK token exchange with
``invalid assertion headers``: it wants a Play-Integrity attestation that
only the official app on a genuine phone can produce. The QR / device-code
grant was withdrawn for Audi before that (#1364). What the vendor left open
is the login the myAudi app itself uses: the **Auth0 tenant at
``group.identity.vwgroup.io``**, with the myAudi public client, PKCE, and a
``localhost`` callback URL that is registered on that client. The token
endpoint of that tenant does not ask for an assertion header, and the access
token it issues (audience ``https://api.cariad.com``) is accepted by the
CARIAD vehicle API directly — no AZS / MBB exchange in between.

Ported from audiconnect/audi_connect_ha#905 (MIT), where it was validated
against a live EU account on 2026-11.

Flow (config_flow ``audi_auth0`` step):

1. Generate a PKCE verifier/challenge pair and an OAuth ``state``.
2. Show the user the ``/authorize`` URL. They sign in with their myAudi
   account in any browser. Auth0 redirects to
   ``http://localhost:8080/myaudi-callback?code=…&state=…``, which the
   browser cannot load — an expected connection error.
3. The user copies the full URL from the address bar into the HA form.
   ``parse_callback_url`` checks host/path/state and extracts the code.
4. ``AudiAuth0Grant.exchange_code`` trades code + verifier for tokens.
   The token set is stamped ``strategy="audi_auth0"`` so the base client
   knows to refresh it here rather than at the IDK endpoint.

Scope: ``email`` is requested on top of the upstream ``openid profile
offline_access`` so the id_token can carry the account's e-mail. That lets
the flow recognise an existing email+password entry for the same account
and attach the new tokens to it instead of creating a second entry. If the
tenant does not return the claim, the ``sub`` claim is used instead.
"""
from __future__ import annotations

import base64
import hashlib
import json
import logging
import secrets
import time
from typing import Any
from urllib.parse import parse_qs, quote, urlencode, urlparse

from aiohttp import ClientSession, ClientTimeout

from ..exceptions import AuthenticationError, TokenRefreshRetryError
from ..models import TokenSet

_LOGGER = logging.getLogger(__name__)

# ``TokenSet.strategy`` label for sessions minted here. Compared against in
# base.py (refresh routing + passwordless guard), audi.py (image token) and
# config_flow.py (reauth routing); stamped literally below so the
# strategy-label pairing test sees both halves.
STRATEGY_AUDI_AUTH0 = "audi_auth0"

AUTH0_AUTHORIZE_URL = "https://group.identity.vwgroup.io/authorize"
AUTH0_TOKEN_URL = "https://group.identity.vwgroup.io/oauth/token"
AUTH0_AUDIENCE = "https://api.cariad.com"
AUTH0_SCOPE = "openid profile email offline_access"
# Registered on the myAudi public client — live-checked 2026-11-08: a
# different localhost port answers ``unauthorized_client — Callback URL
# mismatch``, this one redirects to the universal login.
AUTH0_REDIRECT_URI = "http://localhost:8080/myaudi-callback"

# The myAudi Android client. The market config can override it via
# ``idkClientIDAndroidLive``; most markets (DK/da checked) do not carry the
# key, so this literal is what runs in practice.
AUDI_AUTH0_CLIENT_ID = "09b6cbec-cd19-4589-82fd-363dfa8c24da@apps_vw-dilab_com"

_USER_AGENT = (
    "Android/5.8.1 (Build 800344777.root project 'myaudi_android'"
    ".ext.buildTime) Android/13"
)
_REQUEST_TIMEOUT_S = 30

# Refresh rejections that mean the refresh token itself is dead and only a
# new interactive sign-in can help. Anything else degrades to a retry.
_HARD_REFRESH_ERRORS = frozenset({"invalid_grant"})

# Error keys the config flow maps to translated messages.
ERR_INVALID_CALLBACK = "invalid_auth0_callback"
ERR_DENIED = "auth0_denied"


def audi_auth0_client_id() -> str:
    """Return the client_id to use: market config first, then the literal."""
    try:
        from ._audi_market_config import cached_audi_market_config  # noqa: PLC0415

        market_cid = cached_audi_market_config().get("idkClientIDAndroidLive")
    except Exception:  # noqa: BLE001 — the cache is best-effort
        market_cid = None
    if isinstance(market_cid, str) and "@apps_vw-dilab_com" in market_cid:
        return market_cid
    return AUDI_AUTH0_CLIENT_ID


def generate_pkce() -> tuple[str, str, str]:
    """Return ``(code_verifier, code_challenge, state)`` for one sign-in."""
    verifier = secrets.token_urlsafe(48)
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
    return verifier, challenge, secrets.token_urlsafe(24)


def build_authorization_url(
    client_id: str, code_challenge: str, state: str, *, ui_locales: str = "",
) -> str:
    """Return the ``/authorize`` URL the user opens in a browser."""
    params: dict[str, str] = {
        "client_id": client_id,
        "audience": AUTH0_AUDIENCE,
        "redirect_uri": AUTH0_REDIRECT_URI,
        "response_type": "code",
        "scope": AUTH0_SCOPE,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "state": state,
    }
    if ui_locales:
        params["ui_locales"] = ui_locales
    return f"{AUTH0_AUTHORIZE_URL}?{urlencode(params, quote_via=quote)}"


def parse_callback_url(callback_url: str, expected_state: str) -> str:
    """Validate the pasted callback URL and return its authorization code.

    Raises ``ValueError(ERR_INVALID_CALLBACK)`` when the URL is not the
    registered callback, carries no code, or its ``state`` is not the one this
    sign-in issued (a stale paste from an earlier attempt would otherwise be
    exchanged against the wrong verifier). Raises ``ValueError(ERR_DENIED)``
    when Auth0 reported an error (the user cancelled, or consent was refused).
    """
    raw = (callback_url or "").strip()
    # Tolerate a paste without scheme ("localhost:8080/myaudi-callback?…").
    if raw.startswith("localhost"):
        raw = "http://" + raw
    parsed = urlparse(raw)
    expected = urlparse(AUTH0_REDIRECT_URI)
    if (parsed.scheme, parsed.hostname, parsed.port, parsed.path.rstrip("/")) != (
        expected.scheme, expected.hostname, expected.port, expected.path,
    ):
        raise ValueError(ERR_INVALID_CALLBACK)
    params = parse_qs(parsed.query)
    if params.get("error"):
        raise ValueError(ERR_DENIED)
    state = (params.get("state") or [""])[0]
    code = (params.get("code") or [""])[0]
    if not code or not state or not secrets.compare_digest(state, expected_state):
        raise ValueError(ERR_INVALID_CALLBACK)
    return code


def id_token_claims(id_token: str) -> dict[str, Any]:
    """Decode the public payload of a JWT (no signature check). Never raises."""
    try:
        parts = id_token.split(".")
        if len(parts) < 2:
            return {}
        payload = parts[1] + "=" * (-len(parts[1]) % 4)
        claims = json.loads(base64.urlsafe_b64decode(payload))
    except (ValueError, TypeError, json.JSONDecodeError):
        return {}
    return claims if isinstance(claims, dict) else {}


def _oauth_error(payload: Any) -> tuple[str, str]:
    if not isinstance(payload, dict):
        return "", ""
    return (
        str(payload.get("error") or ""),
        str(payload.get("error_description") or ""),
    )


class AudiAuth0Grant:
    """Token client for the myAudi Auth0 public client."""

    def __init__(self, session: ClientSession, client_id: str | None = None) -> None:
        self._session = session
        self._client_id = client_id or audi_auth0_client_id()

    @property
    def client_id(self) -> str:
        return self._client_id

    def authorization_url(
        self, code_challenge: str, state: str, *, ui_locales: str = ""
    ) -> str:
        return build_authorization_url(
            self._client_id, code_challenge, state, ui_locales=ui_locales
        )

    async def _post_token(self, data: dict[str, str], context: str) -> tuple[int, Any]:
        # Encode by hand so the scope's spaces travel as %20 (what the app
        # sends) rather than aiohttp's form-encoding "+".
        body = urlencode(data, quote_via=quote)
        headers = {
            "Accept": "application/json",
            "Accept-Charset": "utf-8",
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": _USER_AGENT,
        }
        try:
            async with self._session.post(
                AUTH0_TOKEN_URL,
                data=body,
                headers=headers,
                allow_redirects=False,
                timeout=ClientTimeout(total=_REQUEST_TIMEOUT_S),
            ) as resp:
                status = resp.status
                payload = await resp.json(content_type=None)
        except Exception as exc:  # noqa: BLE001 — network / decode
            raise TokenRefreshRetryError(
                f"{context}: request failed ({type(exc).__name__})"
            ) from exc
        return status, payload

    @staticmethod
    def _to_tokens(
        payload: dict[str, Any], *, fallback_refresh: str = "", fallback_id: str = "",
    ) -> TokenSet:
        access_token = str(payload.get("access_token") or "")
        id_token = str(payload.get("id_token") or "") or fallback_id
        refresh_token = str(payload.get("refresh_token") or "") or fallback_refresh
        expires_in = int(payload.get("expires_in") or 3600)
        return TokenSet(
            access_token=access_token,
            refresh_token=refresh_token,
            id_token=id_token,
            expires_at=time.time() + expires_in - 60,
            strategy="audi_auth0",
        )

    async def exchange_code(self, code: str, code_verifier: str) -> TokenSet:
        """Trade the authorization code for a token set. Raises on refusal."""
        status, payload = await self._post_token(
            {
                "client_id": self._client_id,
                "grant_type": "authorization_code",
                "code": code,
                "code_verifier": code_verifier,
                "redirect_uri": AUTH0_REDIRECT_URI,
            },
            "Auth0 code exchange",
        )
        if status != 200 or not isinstance(payload, dict) or "access_token" not in payload:
            err, desc = _oauth_error(payload)
            _LOGGER.warning(
                "Audi Auth0 code exchange rejected: HTTP %d %s (%d-byte description withheld)",
                status, err or "(no error code)", len(desc),
            )
            raise AuthenticationError(
                f"Auth0 code exchange rejected: HTTP {status} {err}".rstrip()
            )
        tokens = self._to_tokens(payload)
        if not tokens.refresh_token:
            raise AuthenticationError("Auth0 did not issue a refresh token")
        if not tokens.id_token:
            raise AuthenticationError("Auth0 did not issue an id_token")
        _LOGGER.info("Audi Auth0 sign-in succeeded (expires_in=%ss)", payload.get("expires_in"))
        return tokens

    async def refresh(self, refresh_token: str, *, id_token: str = "") -> TokenSet:
        """Refresh at the Auth0 token endpoint.

        ``invalid_grant`` means the refresh token is dead → ``AuthenticationError``
        so the caller starts a reauth. Everything else (5xx, network, odd body)
        → ``TokenRefreshRetryError`` so the next poll simply tries again.
        An unrotated refresh token is kept, and so is the previous ``id_token``
        when the response carries none (``TokenSet.is_valid`` needs one);
        the strategy tag is preserved.
        """
        status, payload = await self._post_token(
            {
                "client_id": self._client_id,
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "audience": AUTH0_AUDIENCE,
                "scope": AUTH0_SCOPE,
            },
            "Auth0 refresh",
        )
        if status != 200 or not isinstance(payload, dict) or "access_token" not in payload:
            err, desc = _oauth_error(payload)
            if err in _HARD_REFRESH_ERRORS:
                _LOGGER.warning(
                    "Audi Auth0 refresh token rejected (%s) — a new browser sign-in is needed",
                    err,
                )
                raise AuthenticationError(
                    f"Auth0 refresh rejected: HTTP {status} {err}"
                )
            raise TokenRefreshRetryError(
                f"Auth0 refresh: transient rejection HTTP {status} {err or '(no error code)'} "
                f"({len(desc)}-byte description withheld)"
            )
        return self._to_tokens(
            payload, fallback_refresh=refresh_token, fallback_id=id_token
        )
