# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""VW EU Two-Way — headless device-grant login for client 650d46ca.

Credit: the ``650d46ca`` VW-EU device-authorization client was first surfaced by
community researcher **@magicus**. We independently probed and confirmed it
against a live account and re-implemented the flow here (never copied), with our
own multi-channel + security design. See ATTRIBUTION.md.

650d46ca is a VW-EU app client ("Volkswagen OneApp") that is BOTH
device-code-mintable AND CARIAD-BFF-whitelisted, so its Bearer drives the modern
BFF read/command surface in ``vw_eu.py`` directly (strategy ``device_grant``).
The catch: the token is 1h and NON-refreshable (public client), and the 24h
re-auth cookie lands in whatever session performs the login. So to run it
unattended we do the login OURSELVES with the user's stored password (the cookie
then lands in OUR aiohttp session's jar → we cache it → the next hour's re-mint
is a silent CONFIRM with no password, only ~daily needs the password again).

The flow, GROUNDED end-to-end on a live account 2026-08-18 (mints a token with no
browser, BFF /vehicles + /capabilities 200):

  1. POST /oidc/v1/device_authorization {client_id, scope} -> device_code + user_code.
  2. GET verification_uri_complete -> the signin-service page. Parse window._IDK.
     * stage ``loginIdentifier``     -> a fresh login (need email + password).
     * stage ``codeConfirmation``    -> a valid 24h cookie in the jar (QUICK route:
                                        skip email/password, only confirm).
  3. (full only) POST /signin-service/v1/{client}/login/identifier
                 {_csrf, relayState, hmac, email}    -> ``loginAuthenticate``.
  4. (full only) POST /signin-service/v1/{client}/login/authenticate
                 {_csrf, relayState, hmac, email, password} -> ``codeConfirmation``.
  5. POST the codeConfirmation page's OWN form action (it carries
     relayState/user_id/hmac as query params) with its hidden inputs
     {_csrf, client_identity_name} + ``allow=""``  -> ``verificationSuccess``.
  6. POST /oidc/v1/token {grant_type=device_code, device_code, client_id}
     -> Bearer access_token (1h), stamped strategy ``device_grant``.

Nothing here is exchanged/registered (unlike the MBB Car-Net path): the minted
Bearer IS the BFF credential.
"""
from __future__ import annotations

import asyncio
import html as _html
import logging
import re
import time
from typing import TYPE_CHECKING, Any

from aiohttp import ClientTimeout

from ..models import TokenSet
from ..exceptions import AuthenticationError
from ._device_grant import VWEU_DAG_CLIENT_ID, VWEU_DAG_SCOPE

if TYPE_CHECKING:
    from aiohttp import ClientSession

_LOGGER = logging.getLogger(__name__)

_IDP = "https://identity.vwgroup.io"
_DEVICE_AUTH_URL = f"{_IDP}/oidc/v1/device_authorization"
_TOKEN_URL = f"{_IDP}/oidc/v1/token"
# The We Connect / OneApp app UA — the signin-service pages are served to it.
_UA = "Volkswagen/3.61.0-android/14"
_TIMEOUT = ClientTimeout(total=30)
_DEVICE_GRANT_TYPE = "urn:ietf:params:oauth:grant-type:device_code"


def _extract_idk(page: str) -> dict[str, str]:
    """Pull the flat fields we need out of the ``window._IDK = {...}`` blob.

    The blob is a JS object literal (not strict JSON), so we brace-match it and
    regex the handful of scalar fields the flow uses rather than parse it whole.
    """
    m = re.search(r"window\._IDK\s*=\s*\{", page)
    if not m:
        return {}
    i = m.end() - 1
    depth, end = 0, None
    for j in range(i, min(len(page), i + 200_000)):
        c = page[j]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                end = j + 1
                break
    blob = page[i:end] if end else page[i : i + 4000]
    out: dict[str, str] = {}
    for key in ("csrf_token", "_csrf", "relayState", "hmac", "template",
                "userId", "user_id", "clientIdentityName", "client_identity_name"):
        mm = re.search(
            r'["\']?%s["\']?\s*:\s*["\']([^"\']+)["\']' % re.escape(key), blob
        )
        if mm:
            out[key] = mm.group(1)
    return out


def _form_action(page: str) -> str | None:
    mm = re.search(r'<form[^>]+action=["\']([^"\']+)["\']', page)
    return _html.unescape(mm.group(1)) if mm else None


def _hidden_inputs(page: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for mm in re.finditer(
        r'<input[^>]+name=["\']([^"\']+)["\'][^>]*value=["\']([^"\']*)["\']', page
    ):
        out[mm.group(1)] = _html.unescape(mm.group(2))
    return out


def bff_selectivestatus_has_data(status: object) -> bool:
    """True if a CARIAD-BFF ``selectivestatus`` body carries at least one real
    value block (a ``{"value": ...}`` sub-object), not just error envelopes.

    Used to confirm a car actually SERVES live data on the modern plane before
    activating VW EU Two-Way (a car that only 4103s must not be activated, or the
    entry would swap a working primary for an empty one). Requiring a ``value``
    key — rather than merely 'no error' — rejects BOTH a field-level
    ``{"error": ...}`` block AND a job-level ``{"error": {...}}`` envelope whose
    inner ``{code, message}`` dict would otherwise read as error-free.
    """
    if not isinstance(status, dict):
        return False
    for job in status.values():
        if isinstance(job, dict):
            for sub in job.values():
                if isinstance(sub, dict) and "value" in sub and "error" not in sub:
                    return True
    return False


class VwEuTwoWayLogin:
    """Headless 650d46ca device-grant login. Reuses the passed aiohttp session so
    its cookie jar is the 24h re-auth cache: hydrate the jar with cached cookies
    before calling :meth:`login` and the flow takes the password-free QUICK route."""

    def __init__(
        self,
        session: "ClientSession",
        *,
        client_id: str = VWEU_DAG_CLIENT_ID,
        scope: str = VWEU_DAG_SCOPE,
    ) -> None:
        self._session = session
        self._client_id = client_id
        self._scope = scope

    async def login(self, email: str, password: str) -> TokenSet:
        """Run the full (or cookie-quick) flow and return a ``device_grant``
        TokenSet whose Bearer the CARIAD BFF accepts. Raises AuthenticationError."""
        device_code, user_code, ver_url = await self._device_authorization()
        page, url = await self._get(ver_url)
        f = _extract_idk(page)
        stage = f.get("template", "")

        if stage == "loginIdentifier":
            page, url = await self._submit_identifier(page, url, email)
            page, url = await self._submit_password(page, url, email, password)
            f = _extract_idk(page)
            stage = f.get("template", "")
        if stage != "codeConfirmation":
            low = stage.lower()
            if any(k in low for k in
                   ("mfa", "otp", "authenticator", "verify", "twofactor", "2fa")):
                raise AuthenticationError(
                    "MFA_UNSUPPORTED: this Volkswagen account needs an email or "
                    "authenticator code, which VW EU Two-Way cannot handle yet"
                )
            raise AuthenticationError(
                f"VW EU Two-Way login: expected a confirm page, got stage "
                f"{stage!r} (login failed — most likely the wrong password)"
            )
        await self._confirm_device(page, url)
        return await self._poll_token(device_code)

    # ── legs ─────────────────────────────────────────────────────────────────

    async def _device_authorization(self) -> tuple[str, str, str]:
        status, payload = await self._post_json(
            _DEVICE_AUTH_URL, {"client_id": self._client_id, "scope": self._scope}
        )
        if status != 200 or "device_code" not in payload:
            raise AuthenticationError(
                f"VW EU Two-Way: device_authorization HTTP {status} "
                f"({payload.get('error', '?')})"
            )
        return (
            str(payload["device_code"]),
            str(payload["user_code"]),
            str(payload.get("verification_uri_complete") or payload["verification_uri"]),
        )

    async def _submit_identifier(
        self, page: str, url: str, email: str
    ) -> tuple[str, str]:
        f = _extract_idk(page)
        action = f"{_IDP}/signin-service/v1/{self._client_id}/login/identifier"
        body = {
            "_csrf": f.get("_csrf") or f.get("csrf_token", ""),
            "relayState": f.get("relayState", ""),
            "hmac": f.get("hmac", ""),
            "email": email,
        }
        return await self._post_form(action, body)

    async def _submit_password(
        self, page: str, url: str, email: str, password: str
    ) -> tuple[str, str]:
        f = _extract_idk(page)
        action = f"{_IDP}/signin-service/v1/{self._client_id}/login/authenticate"
        body = {
            "_csrf": f.get("_csrf") or f.get("csrf_token", ""),
            "relayState": f.get("relayState", ""),
            "hmac": f.get("hmac", ""),
            "email": email,
            "password": password,
        }
        return await self._post_form(action, body)

    async def _confirm_device(self, page: str, url: str) -> None:
        """Approve the device. The codeConfirmation page's own form action carries
        relayState/user_id/hmac as query params; POST it with the hidden inputs
        (_csrf + client_identity_name) plus ``allow=""``."""
        action = _form_action(page)
        hidden = _hidden_inputs(page)
        if not action:
            raise AuthenticationError(
                "VW EU Two-Way login: confirm page had no form action"
            )
        from urllib.parse import urljoin, urlparse  # noqa: PLC0415

        if not action.startswith("http"):
            action = urljoin(url, action)
        # Defence-in-depth: the confirm POST carries the authenticated session,
        # so never follow a scraped form action off VW's own identity host.
        if urlparse(action).hostname != urlparse(_IDP).hostname:
            raise AuthenticationError(
                "VW EU Two-Way login: confirm action pointed off identity.vwgroup.io"
            )
        body = dict(hidden)
        body["allow"] = ""
        page4, _landed = await self._post_form(action, body)
        if _extract_idk(page4).get("template") == "generalErrorBranded":
            raise AuthenticationError("VW EU Two-Way login: device confirm rejected")

    async def _poll_token(self, device_code: str) -> TokenSet:
        deadline = time.monotonic() + 60.0
        interval = 2.0
        while time.monotonic() < deadline:
            status, payload = await self._post_json(
                _TOKEN_URL,
                {
                    "grant_type": _DEVICE_GRANT_TYPE,
                    "device_code": device_code,
                    "client_id": self._client_id,
                },
            )
            if status == 200 and payload.get("access_token"):
                now = time.time()
                return TokenSet(
                    access_token=str(payload["access_token"]),
                    refresh_token=str(payload.get("refresh_token", "")),
                    id_token=str(payload.get("id_token", "")),
                    expires_at=now + int(payload.get("expires_in", 3600)),
                    strategy="device_grant",
                )
            err = payload.get("error", "")
            if err == "slow_down":
                interval += 5
            elif err != "authorization_pending":
                raise AuthenticationError(
                    f"VW EU Two-Way: token poll failed ({err or status})"
                )
            await asyncio.sleep(interval)
        raise AuthenticationError("VW EU Two-Way: token poll timed out")

    # ── HTTP ─────────────────────────────────────────────────────────────────

    def _headers(self) -> dict[str, str]:
        return {"User-Agent": _UA, "Accept": "text/html,application/json,*/*"}

    async def _get(self, url: str) -> tuple[str, str]:
        async with self._session.get(
            url, headers=self._headers(), timeout=_TIMEOUT, allow_redirects=True
        ) as resp:
            return await resp.text(errors="replace"), str(resp.url)

    async def _post_form(self, url: str, data: dict[str, str]) -> tuple[str, str]:
        async with self._session.post(
            url, data=data, headers=self._headers(), timeout=_TIMEOUT,
            allow_redirects=True,
        ) as resp:
            return await resp.text(errors="replace"), str(resp.url)

    async def _post_json(
        self, url: str, data: dict[str, str]
    ) -> tuple[int, dict[str, Any]]:
        headers = {**self._headers(), "Accept": "application/json"}
        async with self._session.post(
            url, data=data, headers=headers, timeout=_TIMEOUT
        ) as resp:
            try:
                payload = await resp.json(content_type=None)
            except Exception:  # noqa: BLE001
                payload = {}
            return resp.status, payload if isinstance(payload, dict) else {}
