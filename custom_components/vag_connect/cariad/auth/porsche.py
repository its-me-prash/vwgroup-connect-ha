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
    clean 401). CORRECTION (2026-09-07 androguard xref sweep, both com.porsche.one
    and de.porsche.one): the "needs an X-API-KEY" theory below is UNCONFIRMED —
    the two concrete X-API-KEY/apikey wiring sites actually traced in the DEX
    belong to the Payment and Terms-and-Conditions API clients, not the
    vehicle-connect (api.ppa.porsche.com) client the clientId call uses. No
    call site was found tying a required header to this specific endpoint. The
    502's real cause is still unexplained — do not keep chasing the API-key
    hypothesis without new evidence. (Original theory, kept for context: the
    DEX shows the app redacts X-API-KEY / X-Client-ID / X-Auth-Token headers in
    its logs, so it was assumed this endpoint needs one we do not send; the key
    would not have been a plain DEX literal either way — likely assembled or in
    a resource/native lib.) So the clientId fetch, and therefore the whole
    device grant, still cannot be validated off a real account: the next step
    is a Porsche One owner (#13) either running a test build so its real error
    tells us what the endpoint wants, or capturing one login.

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

b18 (#1337, LIVE-VERIFIED on a real account, 2026-09-07): the legacy password
flow above is NOT structurally blocked. A full ``PorscheAuth.authenticate()``
run — real credentials, real Auth0 tenant, real ``/oauth/token`` call — returned
a genuine access_token + refresh_token with HTTP 200, no captcha, no attestation
error. So the "device-code grant disabled + attestation wall" framing that
applies to Audi does NOT apply here by default; it was an analogy, not a
confirmed fact for Porsche.

What IS confirmed live is that Auth0's rendered-200-instead-of-redirect step
(the one this module already detected but gave up on) is, at least sometimes,
the ACUL **passkey-enrollment** screen (``/u/passkey-enrollment``), not a
captcha — declining it ("continue without passkeys") yields a real code. A
different real account (#1337, @Hollywoodchaos) hit this exact 200-instead-of-
redirect step and got no code, consistent with landing on either that screen or
a genuine captcha; which one it was was never captured (debug logging for this
path didn't exist yet at the time). ``_follow_to_code`` now declines the
passkey-enrollment screen automatically and keeps going; an actual captcha
(any other rendered page) still ends the flow with the same honest error as
before — that piece remains genuinely unsolvable headless.

Two more things the same sweep settled: (1) com.porsche.one (NA/-pcna) and
de.porsche.one (ROW/-row) are code-identical on every auth-relevant endpoint,
host, scope and clientId call — no basis for ever splitting "Porsche NA" /
"Porsche EU" as separate brands here, it is one global Auth0 tenant regardless
of app-store variant. (2) both apps ship a real `appIntegrityIsAvailable`
(Google Play Integrity) feature toggle, compiled default DISABLED, but no
traced call site ties it to the device-grant/token-exchange path — so it is
suggestive that Porsche *could* turn on the same kind of attestation Audi has,
but it is not proof that the #1337 `403 unauthorized_client` was actually
caused by it. Full writeup: vag-connect-porsche-full-grounding-2026-09-07.md
(repo root's parent — not shipped in this repo, research-only).

b19 (CJNE-comparison, same day) also added the captcha-solving config-flow
step (`PorscheAuth.authenticate`'s `captcha_code`/`resume_state`/
`resume_verifier` kwargs, `PorscheCaptchaRequiredError`, and
`config_flow.py::async_step_porsche_captcha`). A follow-up sweep of CJNE's
and ha-porscheconnect's FULL issue/PR history (not just current code) —
vag-connect-porsche-cjne-issue-history-2026-09-07.md (repo root's parent) —
surfaced two things folded in directly: (1) a real captcha-image dark-mode
bug (transparent SVG background + black strokes is invisible in HA dark
mode) that ha-porscheconnect's own maintainer shipped and only caught from
user reports — this repo's captcha image already forces a white background
for the same reason CJNE eventually did; (2) repeated failed captcha/login
attempts have gotten real Porsche accounts locked for "suspicious activity"
(ha-porscheconnect#199) — this repo's captcha step never auto-resubmits (a
human must explicitly submit each attempt) and its UI text now warns
against repeated guessing rather than encouraging it.

Old flow based on CJNE/pyporscheconnectapi (Apache-2.0), aiohttp reimpl.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import re
import time
from urllib.parse import parse_qs, urljoin, urlsplit

from aiohttp import ClientTimeout, ClientSession

from ..exceptions import AuthenticationError, PorscheCaptchaRequiredError, TokenExpiredError
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
# b19 (CJNE-comparison #4) — CJNE attaches this X-Client-ID to every Auth0-flow
# request (identifier/password POSTs, resume hops, token exchange, refresh),
# not just post-auth API calls. It is already used post-auth in api/porsche.py
# under the same name; our own #1337 live test succeeded without it on the
# auth path, so this is a defensive match-a-working-implementation addition,
# not a fix for a known failure.
_X_CLIENT      = "41843fb4-691d-4970-85c7-2673e8ecef40"

# b19 (CJNE-comparison #9) — full scope list from CJNE's const.py (Apache-2.0).
# Our previous 15-scope subset dropped 8 read-only pid:user_profile.* scopes;
# Auth0 client registrations sometimes expect the exact registered scope
# string, so match it verbatim even though nothing here currently reads the
# extra profile fields.
_SCOPE = (
    "openid profile email offline_access mbb ssodb badge vin dealers cars "
    "charging manageCharging plugAndCharge climatisation manageClimatisation "
    "pid:user_profile.porscheid:read pid:user_profile.name:read "
    "pid:user_profile.vehicles:read pid:user_profile.dealers:read "
    "pid:user_profile.emails:read pid:user_profile.phones:read "
    "pid:user_profile.addresses:read pid:user_profile.birthdate:read "
    "pid:user_profile.locale:read pid:user_profile.legal:read"
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

    async def authenticate(
        self,
        email: str,
        password: str,
        *,
        captcha_code: str | None = None,
        resume_state: str | None = None,
        resume_verifier: str | None = None,
    ) -> TokenSet:
        """Full PKCE flow → access_token + refresh_token.

        ``captcha_code``/``resume_state``/``resume_verifier`` resume an
        in-progress Auth0 transaction after :class:`PorscheCaptchaRequiredError`
        was raised and a caller (the config flow) got the user to solve it
        (b19, CJNE-comparison #12). The PKCE ``code_verifier`` and Auth0
        ``state`` are bound to the ORIGINAL ``/authorize`` call and cannot be
        regenerated — CJNE's own commit history calls this out explicitly
        (the challenge is bound to that first transaction). So a
        captcha-interrupted login skips straight to re-POSTing the identifier
        step (this time carrying the solved ``captcha`` field) using the
        state/verifier captured when the captcha was first raised, rather
        than starting a brand new transaction that would produce a
        ``code_verifier`` mismatch at the final token exchange.
        """
        if captcha_code and resume_state and resume_verifier:
            verifier = resume_verifier
            auth0_state = resume_state
        else:
            verifier, challenge = _pkce()
            state = base64.urlsafe_b64encode(os.urandom(16)).rstrip(b"=").decode()

            # Step 1: /authorize. allow_redirects=False and read the Location
            # header directly (b19, CJNE-comparison #10): with allow_redirects=True
            # an already-authenticated Auth0 session would redirect straight to
            # ``my-porsche-app://auth0/callback?code=...`` — a non-http(s) scheme
            # aiohttp's redirect follower cannot land on safely. Reading Location
            # ourselves both avoids that crash risk AND lets us short-circuit the
            # whole identifier/password dance when a session is already valid.
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
                headers={"User-Agent": _USER_AGENT, "X-Client-ID": _X_CLIENT},
                allow_redirects=False,
            ) as resp:
                location = resp.headers.get("Location", "")
            if resp.status not in (301, 302, 303, 307, 308) or not location:
                raise AuthenticationError(
                    f"Porsche authorize request did not redirect (HTTP {resp.status})"
                )
            target = urljoin(_AUTH_URL, location)
            existing_code = self._extract_code(target)
            if existing_code:
                _LOGGER.debug(
                    "Porsche auth: existing Auth0 session, skipping login form"
                )
                return await self._exchange_code(existing_code, verifier)

            state_vals = parse_qs(urlsplit(target).query).get("state")
            if not state_vals:
                raise AuthenticationError("Could not extract Auth0 state from login page")
            auth0_state = state_vals[0]

        # Step 2: POST the identifier (e-mail [+ solved captcha, if resuming]).
        # A 401 here is Auth0 rejecting the identifier outright; a 400 means a
        # (possibly new/chained) captcha challenge (b19, CJNE-comparison §1.5)
        # — neither is the generic "wall" case.
        login_url = f"https://{_AUTH_SERVER}/u/login/identifier?state={auth0_state}"
        identifier_data = {
            "state":       auth0_state,
            "username":    email,
            "js-available":"true",
            "webauthn-available": "true",
            "is-brave":    "false",
            "webauthn-platform-authenticator-available": "false",
            "action":      "default",
        }
        if captcha_code:
            identifier_data["captcha"] = captcha_code
        async with self._session.post(
            login_url,
            timeout=_AUTH_TIMEOUT,
            data=identifier_data,
            headers={
                "User-Agent":   _USER_AGENT,
                "X-Client-ID":  _X_CLIENT,
                "Content-Type": "application/x-www-form-urlencoded",
            },
            allow_redirects=False,
        ) as resp:
            if resp.status == 401:
                raise AuthenticationError("Porsche auth failed — wrong credentials")
            if resp.status == 400:
                html = await resp.text()
                image = self._extract_captcha_image(html)
                if image:
                    raise PorscheCaptchaRequiredError(image, auth0_state, verifier)
            # Any other status here: fall through and let step 3 / step 4
            # produce the more general diagnostic — Auth0's identifier step
            # doesn't usually reject on other codes.

        # Step 3: POST the password.
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
                "X-Client-ID":  _X_CLIENT,
                "Content-Type": "application/x-www-form-urlencoded",
            },
            allow_redirects=False,
        ) as resp:
            if resp.status in (400, 401):
                raise AuthenticationError("Porsche auth failed — wrong credentials")
            location = resp.headers.get("Location", "")
            status = resp.status
        # b11 (#1337 Hollywoodchaos) — the Porsche auth path emitted zero log
        # lines, so a user's debug capture showed nothing but the final warning.
        # Log status + whether a redirect was handed back (hostnames/statuses
        # only — never the URL query, code, state, e-mail or password).
        _LOGGER.debug(
            "Porsche auth: password POST → HTTP %s, %s",
            status,
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
                "(a captcha/consent step we do not handle)"
            )

        # Step 5: Exchange code for tokens
        return await self._exchange_code(code, verifier)

    @staticmethod
    def _extract_captcha_image(html: str) -> str | None:
        """Extract a captcha image (data-URI) from an Auth0 ACUL or legacy
        login page. b19 (CJNE-comparison #12a) — extraction only, ported from
        CJNE/pyporscheconnectapi's ``_extract_captcha_image`` (Apache-2.0).
        There is deliberately no solving path yet: this only lets a captcha
        wall be reported distinctly from wrong-credentials (see ``authenticate``
        step 2) instead of collapsed into one vague error. A config-flow step
        that lets a user actually solve it inline is tracked as a follow-up,
        modeled on ``CJNE/ha-porscheconnect``'s ``async_step_captcha``.
        """
        match = re.search(r'atob\("([A-Za-z0-9+/=]+)"', html)
        if match:
            try:
                context = json.loads(base64.b64decode(match.group(1)).decode("utf-8"))
            except (ValueError, json.JSONDecodeError):
                context = None
            if context:
                image = context.get("screen", {}).get("captcha", {}).get("image")
                if isinstance(image, str) and image:
                    return image
        svg_match = re.search(r"(data:image/svg[^\"' ]+)", html)
        if svg_match:
            return svg_match.group(1)
        return None

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
                headers={"User-Agent": _USER_AGENT, "X-Client-ID": _X_CLIENT},
                allow_redirects=False,
            ) as resp:
                # b11 (#1337) — trace each hop by host + status only (never the
                # full URL, which carries state/code).
                _LOGGER.debug(
                    "Porsche auth: redirect hop → host=%s HTTP %s",
                    urlsplit(target).hostname or "?", resp.status,
                )
                if resp.status in (301, 302, 303, 307, 308):
                    current_base = target
                    location = resp.headers.get("Location", "")
                    continue
                # A 200 here means Auth0 rendered a page instead of redirecting.
                # b18 (#1337, live-verified on a real account) — this is not
                # always a captcha/consent wall: it is often the Auth0 ACUL
                # passkey-enrollment nudge (``/u/passkey-enrollment``), which is
                # just an extra screen, not a dead end. Decline it the same way
                # CJNE/pyporscheconnectapi does and keep following the chain.
                # A genuine captcha (or anything else rendered) still ends here.
                if "/u/passkey-enrollment" in urlsplit(target).path:
                    html = await resp.text()
                    resumed = await self._skip_passkey_enrollment(target, html)
                    if resumed:
                        _LOGGER.debug(
                            "Porsche auth: declined passkey-enrollment, resuming"
                        )
                        current_base = target
                        location = resumed
                        continue
                _LOGGER.debug(
                    "Porsche auth: hop returned HTTP %s (a rendered page, not "
                    "a redirect, and not a passkey-enrollment screen we could "
                    "clear) — no authorization code. This is the real captcha/"
                    "consent wall the headless login cannot clear.",
                    resp.status,
                )
                return None
        return None

    async def _skip_passkey_enrollment(self, url: str, html: str) -> str | None:
        """Decline the Auth0 ACUL passkey-enrollment screen and return the
        redirect Location to resume the chain, or ``None`` if the page could
        not be parsed (treated by the caller as the unhandled-wall case).

        The page embeds its transaction context as base64 JSON behind an
        ``atob("...")`` call; we need ``transaction.state`` out of it, plus
        (b19, CJNE-comparison #8) any ``untrustedData.submittedFormData`` the
        ACUL context carried — CJNE seeds the decline POST body with that
        before overwriting ``state``/``action``/``acul-sdk`` on top, in case
        some ACUL versions validate that expected form fields are present.
        Mirrors CJNE/pyporscheconnectapi's ``_skip_passkey_enrollment``
        (Apache-2.0).
        """
        match = re.search(r'atob\("([A-Za-z0-9+/=]+)"', html)
        if not match:
            return None
        try:
            context = json.loads(base64.b64decode(match.group(1)).decode("utf-8"))
        except (ValueError, json.JSONDecodeError):
            _LOGGER.debug("Porsche auth: could not parse passkey-enrollment context")
            return None
        state = context.get("transaction", {}).get("state")
        if not state:
            return None
        data = dict(context.get("untrustedData", {}).get("submittedFormData") or {})
        data.update({
            "state": state,
            "action": "abort-passkey-enrollment",
            "acul-sdk": "@auth0/auth0-acul-js@1.2.0",
        })
        async with self._session.post(
            url,
            timeout=_AUTH_TIMEOUT,
            data=data,
            headers={
                "User-Agent": _USER_AGENT,
                "X-Client-ID": _X_CLIENT,
                "Content-Type": "application/x-www-form-urlencoded",
            },
            allow_redirects=False,
        ) as resp:
            if resp.status not in (301, 302, 303, 307, 308):
                return None
            return resp.headers.get("Location", "")

    async def refresh(self, refresh_token: str) -> TokenSet:
        """Refresh tokens using refresh_token.

        b19 (CJNE-comparison #6) — CJNE treats HTTP 403 (not 401) as "refresh
        token invalid" based on production observation of Porsche's tenant;
        neither side's assumption is spec-verified against a live capture, so
        both codes are treated as expired here — cheap, defensive, and closes
        an unhandled-exception path where a 403 body without ``access_token``
        would otherwise raise a bare ``KeyError``.
        """
        async with self._session.post(
            _TOKEN_URL,
            timeout=_AUTH_TIMEOUT,
            json={
                "grant_type":    "refresh_token",
                "client_id":     _CLIENT_ID,
                "refresh_token": refresh_token,
            },
            headers={"User-Agent": _USER_AGENT, "X-Client-ID": _X_CLIENT},
        ) as resp:
            if resp.status in (401, 403):
                raise TokenExpiredError("Porsche refresh token expired")
            if resp.status != 200:
                body = await resp.text()
                raise AuthenticationError(
                    f"Porsche token refresh failed {resp.status}: "
                    f"{_oauth_error_code(body)}"
                )
            data = await resp.json()

        return TokenSet(
            access_token=data["access_token"],
            refresh_token=data.get("refresh_token", refresh_token),
            id_token=data.get("id_token", ""),
            expires_at=time.time() + float(data.get("expires_in", 3600)),
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
            headers={"User-Agent": _USER_AGENT, "X-Client-ID": _X_CLIENT},
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
            expires_at=time.time() + float(data.get("expires_in", 3600)),
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
                    expires_at=time.time() + float(data.get("expires_in", 3600)),
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
            if resp.status in (401, 403):
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
            expires_at=time.time() + float(data.get("expires_in", 3600)),
        )
