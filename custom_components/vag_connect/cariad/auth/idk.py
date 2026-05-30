# Copyright 2026 Prash Balan (@its-me-prash) — Apache License 2.0
"""VAG IDK authentication — PKCE/OAuth2 for VW EU, Audi, Škoda, SEAT, CUPRA.

Clean-room implementation of the standard PKCE flow documented in:
  IETF RFC 7636 — Proof Key for Code Exchange
  https://identity.vwgroup.io/.well-known/openid-configuration

No code copied from any GPL project. Auth flow discovered through
publicly available open-source research (see docs/research/VAG_GROUP_ECOSYSTEM.md).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import os
import re
import time
from html.parser import HTMLParser
from typing import Any
from urllib.parse import parse_qs, urlparse, urlunparse


from aiohttp import ClientSession, ClientTimeout, InvalidURL

from ._auth_config_resolver import AuthConfigResolver
from ..exceptions import (
    AuthenticationError,
    EmailTwoFactorRequiredError,
    MarketingConsentError,
    TermsAndConditionsError,
    TwoFactorRequiredError,
    RateLimitError,
    TokenExpiredError,
    UpstreamUnavailableError,
)
from ..models import BrandConfig, TokenSet

_LOGGER = logging.getLogger(__name__)

_AUTH_TIMEOUT = ClientTimeout(total=30)  # per-request timeout for auth flows

_IDK_BASE = "https://identity.vwgroup.io"
_SIGNIN_BASE = f"{_IDK_BASE}/signin-service/v1"
_AUTHORIZE_URL = f"{_IDK_BASE}/oidc/v1/authorize"

# ── CARIAD-BFF token endpoint (Audi + VW EU) ────────────────────────────────
# v2.5.4 (#313) — On 2026-05-28 VW shut down the legacy
# ``/login/v1/idk/token`` endpoint at the Azure Application Gateway WAF
# layer. Requests now return HTTP 403 from
# ``Microsoft-Azure-Application-Gateway/v2`` regardless of headers,
# query shape, or User-Agent. The replacement endpoint adopted by the
# official Volkswagen 3.61.0 + myAudi 4.31.0 APKs (and ported by
# evcc PR #30277 / volkswagencarnet PR #331 / ioBroker.vw-connect):
_CARIAD_TOKEN_URL = "https://emea.bff.cariad.digital/auth/v1/idk/oidc/token"

# ── X-QMAuth signing for Audi + VW EU IDK token exchange ────────────────────
# v2.5.4 (#313) — Audi/VW EU's IDK token endpoint validates an
# ``x-qmauth`` HMAC-SHA256 header on both ``authorization_code`` and
# ``refresh_token`` grants. Values rotated upstream 2026-05-28 and
# captured by evcc PR #30292 (MIT) — cross-verified against
# arjenvrh/audi_connect_ha (MIT) and TA2k/ioBroker.vw-connect.
# Format: ``v1:<qmClientId>:<hmac_sha256(qmSecret, ts_hundred_seconds)>``
#
# v2.5.7 R2 — keep the PRIOR rotation pair as a fallback. ioBroker's
# pattern: try current first, then try prior on 4xx. Reduces blast
# radius when VW re-rotates while we wait for evcc/audi_connect_ha to
# extract the new values via live testing. Phase 0 / Path 2.5 confirmed
# we cannot extract these from APK static analysis.
_QM_CLIENT_ID = "01da27b0"
_QM_SECRET = "1ab69925ac179aaa4e83abe671a9476d176418b85bd706f1436ca15be647989c"
_QM_PRIOR_CLIENT_ID = "c95f4fd2"  # pre-2026-05-28 rotation, evcc PR #30277 baseline
_QM_PRIOR_SECRET = "e47866378ef0658ce75d71007a809f34616b9635e2ec228245784c1f63e88d06"


def _calculate_x_qmauth(
    secret_hex: str | None = None,
    client_id: str | None = None,
    now: float | None = None,
) -> str:
    """Compute the ``x-qmauth`` header value.

    Python port of evcc PR #30292 (Go, MIT). The Audi/VW EU IDK token
    endpoint validates this header on both authorization-code and
    refresh-token grants. Time-bucket is 100-seconds (so the same value
    survives clock-skew up to ~100s between client and server).

    v2.5.6 (#313 follow-on) — secret + client_id are now caller-supplied
    so the ``AuthConfigResolver`` can inject APK-mined values. Defaults
    to the v2.5.4 hardcoded competitor-known constants when the caller
    omits them (e.g. unit tests).

    Args:
        secret_hex: 64-char hex HMAC secret. Defaults to ``_QM_SECRET``.
        client_id:  8-char hex client identifier. Defaults to ``_QM_CLIENT_ID``.
        now: Optional UNIX-epoch timestamp override (for tests). Default
            is ``time.time()`` at call time.

    Returns:
        Header value of the form ``v1:<clientId>:<hexHmac>``.
    """
    secret_hex = secret_hex or _QM_SECRET
    client_id = client_id or _QM_CLIENT_ID
    ts = int((now if now is not None else time.time()) / 100)
    secret_bytes = bytes.fromhex(secret_hex)
    sig = hmac.new(secret_bytes, str(ts).encode("ascii"), hashlib.sha256).hexdigest()
    return f"v1:{client_id}:{sig}"


def _cariad_token_headers(
    user_agent: str,
    *,
    qmauth_secret: str | None = None,
    qmauth_client_id: str | None = None,
    android_package_name: str = "de.myaudi.mobile.assistant",
) -> dict[str, str]:
    """Return the assertion-header set required by the new CARIAD IDK
    token endpoint (Audi + VW EU).

    v2.5.4 (#313) — Sent for BOTH authorization_code exchange AND
    refresh_token. Missing any one of these results in either an HTTP
    403 (Azure WAF) or an ``{"error":"invalid assertion headers"}``
    response body once past the gateway.

    v2.5.6 (#313 follow-on) — qmauth values are now caller-supplied so
    the resolver can swap in APK-mined values. Caller omits = defaults
    apply (v2.5.4 hardcoded constants, cross-verified against
    audi_connect_ha + evcc + volkswagencarnet + ioBroker.vw-connect).

    v2.5.11 — brand-impersonation bugfix. Pre-v2.5.11 the
    ``x-android-package-name`` was hardcoded to
    ``de.myaudi.mobile.assistant`` for ALL brands including VW EU,
    silently impersonating the Audi app on VW token requests. Our own
    atlas profile (vw_group_auth_profile.json) documented this as
    wrong since 2026-05-29 but the code didn't match. Caller now
    passes per-brand value via ``android_package_name`` kwarg
    (resolved from ``BrandConfig.android_package_name``). Default
    remains the Audi value for backward-compat with any unparameterised
    callers, but the production paths in IDKAuth always pass through
    the brand-specific value as of v2.5.11.

    Note: audi_connect_ha v1.19.2 (PR #736 / 2026-05-28) reportedly
    works with only 5 headers (no x-platform / x-android-package-name /
    x-assertion). Our 8-header set is a superset that mimics the
    official app more closely — still functional, more
    anomaly-score-resilient if VW tightens WAF rules. Documented for
    future minimisation if WAF stays permissive.
    """
    return {
        "Content-Type":            "application/x-www-form-urlencoded",
        "Accept":                  "application/json",
        "Accept-Charset":          "utf-8",
        "User-Agent":              user_agent,
        "x-qmauth":                _calculate_x_qmauth(qmauth_secret, qmauth_client_id),
        "x-platform":              "android",
        "x-android-package-name":  android_package_name,
        "x-assertion":             "0",
    }


class _CSRFParser(HTMLParser):
    """Minimal HTML parser — extracts hidden form fields from IDK login pages."""

    def __init__(self) -> None:
        super().__init__()
        self.fields: dict[str, str] = {}
        self.form_action: str = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = dict(attrs)
        if tag == "input" and attr.get("type") == "hidden":
            name = attr.get("name", "")
            value = attr.get("value", "")
            if name:
                self.fields[name] = value or ""
        if tag == "form" and not self.form_action:
            self.form_action = attr.get("action") or ""


def _pkce_pair() -> tuple[str, str]:
    """Generate a PKCE code_verifier + code_challenge (S256)."""
    verifier = base64.urlsafe_b64encode(os.urandom(32)).rstrip(b"=").decode()
    digest = hashlib.sha256(verifier.encode()).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    return verifier, challenge


def _extract_auth_code(location: str, redirect_uri: str) -> str | None:
    """Extract 'code' from a redirect-to-app URL.

    Tries query first (default for response_type=code), then fragment
    (default for response_type=code+id_token / hybrid). v1.26.3 fix.
    """
    return _extract_param_from_url(location, redirect_uri, "code")


def _extract_param_from_url(
    location: str, redirect_uri: str, param: str
) -> str | None:
    """Extract a named param from a redirect URL, checking query and fragment.

    For OIDC code-flow the params land in `?query`. For hybrid flow
    (response_type=code+id_token) they land in `#fragment`. v1.26.3.
    """
    prefix = redirect_uri.split("://")[0] + "://"
    if not location.startswith(prefix):
        return None
    parsed = urlparse(location)
    for source in (parsed.query, parsed.path.lstrip("?"), parsed.fragment):
        if not source:
            continue
        params = parse_qs(source)
        values = params.get(param)
        if values and values[0]:
            return values[0]
    return None


def _absolute_url(base: str, path: str) -> str:
    """Resolve a relative form action against the IDK base URL."""
    if path.startswith("http"):
        return path
    parsed = urlparse(base)
    return urlunparse((parsed.scheme, parsed.netloc, path, "", "", ""))


def _make_absolute(base_url: str, location: str) -> str:
    """Resolve a Location header value to an absolute URL.

    Auth0 and other servers often return relative Location headers
    (e.g. '/v2/login/callback?...'). aiohttp requires absolute URLs.
    """
    if not location:
        return ""
    if location.startswith("http"):
        return location
    # Relative path — join with base
    parsed = urlparse(base_url)
    base = f"{parsed.scheme}://{parsed.netloc}"
    if location.startswith("/"):
        return base + location
    # Relative to current path directory
    from urllib.parse import urljoin
    return urljoin(base_url, location)


class IDKAuth:
    """Handles authentication against the VAG Identity Kit (IDK) server.

    Covers: VW EU, Audi, Škoda, SEAT, CUPRA. Also covers Volkswagen
    North America (US/CA) via per-instance URL overrides (see
    ``authorize_url_override`` / ``token_url_override`` /
    ``idk_base_override`` / ``signin_client_id_override``).

    Uses the caller's injected aiohttp.ClientSession — no requests dependency.
    """

    def __init__(
        self,
        session: ClientSession,
        brand: BrandConfig,
        *,
        authorize_url_override: str | None = None,
        token_url_override: str | None = None,
        idk_base_override: str | None = None,
        signin_client_id_override: str | None = None,
    ) -> None:
        """Construct an IDKAuth client.

        v2.3.0 (#269 roberttco) — VW NA support: the legacy default
        path uses ``identity.vwgroup.io`` for the EU IDP. VW NA users
        hit a different OAuth flow per matpoulin/CarConnectivity-
        connector-volkswagen-na (Apache-2.0):

        - **authorize_url_override**: full URL to GET for the initial
          authorize call. VW NA uses
          ``https://b-h-s.spr.{country}00.p.con-veh.net/oidc/v1/authorize``
          — co-located with the API base, not on identity.vwgroup.io.
          When None, falls back to ``_AUTHORIZE_URL``.

        - **token_url_override**: full URL for the OAuth2 token exchange
          (auth-code → access+refresh tokens) AND refresh-token calls.
          VW NA uses ``https://b-h-s.spr.{country}00.p.con-veh.net/oidc/v1/token``.
          When None, falls back to ``_get_token_endpoint()`` (which
          today handles cupra/seat/cariad-bff resolution).

        - **idk_base_override**: scheme+host for ``Origin`` header on
          Auth0 form POSTs. Mostly redundant for VW NA (which uses the
          legacy signin-service flow, not Auth0) but kept available for
          symmetric configuration. When None, falls back to ``_IDK_BASE``.

        - **signin_client_id_override**: client-GUID used to build the
          fallback signin-service URL when the form-action is missing
          from the HTML response. VW NA's signin-service uses a
          hardcoded NA GUID (``b680e751-...@apps_vw-dilab_com``)
          distinct from the ``MYVW_ANDROID`` API client_id.
        """
        self._session = session
        self._brand = brand
        self.user_id: str | None = None
        # MBB-mode (hybrid flow) support: when authenticate(mbb_mode=True) is
        # called, the final app:// redirect URL is stored here so callers can
        # extract the cross-service-signed id_token from its query/fragment.
        # For Cariad-only callers this stays None and behaviour is unchanged.
        self.last_redirect_url: str | None = None
        # v2.3.0 — per-instance URL overrides for non-EU IDPs.
        self._authorize_url = authorize_url_override or _AUTHORIZE_URL
        self._token_url_override = token_url_override
        self._idk_base = idk_base_override or _IDK_BASE
        self._signin_base = (
            f"{idk_base_override}/signin-service/v1"
            if idk_base_override
            else _SIGNIN_BASE
        )
        self._signin_client_id = signin_client_id_override or self._brand.client_id

    async def authenticate(
        self,
        email: str,
        password: str,
        mfa_code: str | None = None,
        mbb_mode: bool = False,
    ) -> TokenSet:
        """Full login flow → returns access/refresh/id tokens.

        IDK migrated to Auth0 Universal Login (/u/login) in 2025.
        New flow:
          1. GET /oidc/v1/authorize → redirects to /u/login?state=AUTH0_STATE
          2. POST /usernamepassword/login with email+password (Auth0 API)
          3. Parse form_post HTML response, POST to /login/callback
          4. Follow redirects to app:// URI → extract auth code
          5. Exchange code for tokens (PKCE)

        mbb_mode (NEW v1.26.3 research):
          When True, requests OIDC HYBRID flow (response_type=code id_token,
          response_mode=query) instead of plain code flow. The hybrid-issued
          id_token in the authorize-redirect URL is signed for cross-service
          use and is the ONLY id_token format the legacy MBB OAuth endpoint
          (mbboauth-1d.prd.ece.vwg-connect.com) accepts. Mirrors evcc-io/evcc
          vehicle/vag/vwidentity/oauth2.go (Go reference, MIT). After this
          call returns, callers should parse id_token from
          self.last_redirect_url (the original token_set.id_token from the
          token-endpoint exchange is for app-only audience and MBB rejects it
          with HTTP 400 'Id token is invalid').
        """
        verifier, challenge = _pkce_pair()
        pkce_state = base64.urlsafe_b64encode(os.urandom(16)).rstrip(b"=").decode()
        nonce = base64.urlsafe_b64encode(os.urandom(16)).rstrip(b"=").decode()

        # Step 1 — GET authorize, follow to Auth0 /u/login page
        params: dict[str, str] = {
            "client_id": self._brand.client_id,
            "redirect_uri": self._brand.redirect_uri,
            "response_type": "code id_token" if mbb_mode else "code",
            "scope": self._brand.scope,
            "state": pkce_state,
            "nonce": nonce,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        }
        # Cariad-flow: force re-auth (helpful when user has multiple sessions).
        # MBB hybrid-flow: drop prompt=login because some IDK templates reject
        # it in combination with response_type=code+id_token.
        if not mbb_mode:
            params["prompt"] = "login"
        # NOTE: deliberately do NOT set response_mode for MBB hybrid flow.
        # OIDC default for response_type=code+id_token is fragment, and our
        # extract code reads BOTH query and fragment. Some IDK Auth0 setups
        # reject explicit response_mode=query for hybrid as invalid_request.
        async with self._session.get(
            self._authorize_url,
            timeout=_AUTH_TIMEOUT, params=params, headers=self._base_headers(),
            allow_redirects=True,
        ) as resp:
            login_url = str(resp.url)
            html = await resp.text(errors="replace")
            _LOGGER.debug(
                "IDK step1: status=%s url=%s html_len=%d",
                resp.status, login_url[:80], len(html),
            )
            if resp.status != 200:
                raise AuthenticationError(
                    f"Authorization page HTTP {resp.status} at {login_url}"
                )

        # Determine which login variant we landed on
        if "/u/login" in login_url:
            # Auth0 Universal Login (new IDK, 2025+)
            return await self._authenticate_auth0(
                login_url, html, email, password, verifier, mfa_code,
                mbb_mode=mbb_mode,
            )

        # Legacy signin-service flow (kept as fallback)
        return await self._authenticate_legacy(
            html, email, password, verifier, mbb_mode=mbb_mode
        )

    async def _authenticate_auth0(
        self,
        login_url: str,
        html: str,
        email: str,
        password: str,
        verifier: str,
        mfa_code: str | None = None,
        mbb_mode: bool = False,
    ) -> TokenSet:
        """Auth0 Universal Login — combined username+password POST.

        Based on reverse-engineering of volkswagencarnet (MIT) which uses the
        SAME client_id and the SAME Auth0 /u/login page successfully:

          1. Parse <input name="state"> from the login page HTML
          2. POST {username, password, state} to /u/login?state=STATE
             with allow_redirects=False
          3. Follow redirects manually until app:// URI
          4. Exchange auth code (PKCE)
        """
        # Step 1 — extract state from hidden HTML input
        # Auth0 embeds state as <input type="hidden" name="state" value="...">
        # even in SPA pages. Fall back to URL query string if not found.
        state_from_html = self._parse_csrf_robust(html).fields.get("state", "")
        auth0_state: str = (
            state_from_html
            or parse_qs(urlparse(login_url).query).get("state", [""])[0]
        )
        if not auth0_state:
            raise AuthenticationError("Auth0: could not find state token.")

        _LOGGER.debug(
            "IDK Auth0: state=%s... (from_html=%s)",
            auth0_state[:20], bool(state_from_html),
        )

        # Step 2 — POST credentials (combined, NOT identifier-first)
        # state goes BOTH in URL query AND in form body (volkswagencarnet pattern)
        login_form = {
            "username": email,
            "password": password,
            "state":    auth0_state,
        }
        # URL-encode state for URL construction (form body is encoded by aiohttp automatically)
        from urllib.parse import quote as _quote  # noqa: PLC0415
        post_url = f"{self._idk_base}/u/login?state={_quote(auth0_state, safe='')}"
        _LOGGER.debug(
            "IDK Auth0: brand=%s post_url=%s",
            self._brand.name, post_url[:80],
        )

        try:
            async with self._session.post(
                post_url,
                timeout=_AUTH_TIMEOUT,
                data=login_form,
                headers=self._form_headers(),
                allow_redirects=False,  # follow manually to preserve cookies
            ) as resp:
                status   = resp.status
                raw_loc  = resp.headers.get("Location", "")
                # Resolve relative Location → absolute (volkwagencarnet pattern)
                location = _make_absolute(self._idk_base, raw_loc) if raw_loc else ""
                resp_html = await resp.text(errors="replace")
        except InvalidURL as exc:
            _LOGGER.error("IDK Auth0: InvalidURL posting to %s — %s", post_url, exc)
            raise AuthenticationError(f"Invalid login URL: {post_url[:100]}") from exc

        _LOGGER.debug(
            "IDK Auth0 POST: status=%s location=%s",
            status, location[:80] if location else "(none)",
        )

        if status == 400:
            # Parse error from Auth0 HTML response.
            # v1.24.1 (2026-05-08 audit): Auth0 error templates can echo the
            # submitted username/email back into the error string (sometimes
            # verbatim, sometimes inside a "for user X" phrase). Truncate +
            # mask the user's email before logging at WARNING level so we
            # don't leak PII to anyone tailing HA logs.
            err = self._extract_auth0_error(resp_html)
            err_safe = (err or "")[:120]
            if email:
                err_safe = err_safe.replace(email, "***@***")
            _LOGGER.warning("IDK Auth0 400: %s", err_safe)
            raise AuthenticationError(
                f"Auth0 login rejected (400): {err_safe or 'check email/password'}"
            )
        if status == 401:
            raise AuthenticationError("Invalid email or password.")
        if status == 429:
            raise RateLimitError()
        if status not in (302, 303):
            raise AuthenticationError(
                f"Auth0 POST returned HTTP {status}: {resp_html[:200]}"
            )

        # Step 3 — follow redirect chain manually until app:// URI
        prefix = self._brand.redirect_uri.split("://")[0] + "://"
        ref = location
        for _ in range(15):
            if not ref:
                break
            # Capture user_id from redirect URL (SEAT/CUPRA pattern from pycupra)
            if "user_id" in ref:
                uid = parse_qs(urlparse(ref).query).get("user_id", [""])[0]
                if uid:
                    self.user_id = uid
                    _LOGGER.debug("IDK Auth0: captured user_id from redirect: %s", uid[:8])
            if ref.startswith(prefix):
                break
            # Detect MFA — v2.2.0 (#183 follow-on) discriminates Email-OTP
            # from authenticator-app TOTP so the Repair-issue surfaces the
            # right message (check inbox vs. open authenticator).
            is_email_2fa = "/u/email-challenge" in ref
            is_mfa = is_email_2fa or "/u/mfa" in ref
            if is_mfa:
                _LOGGER.debug(
                    "IDK Auth0: %s challenge at %s",
                    "Email-OTP" if is_email_2fa else "TOTP",
                    ref[:80],
                )
                if mfa_code:
                    mfa_state = parse_qs(urlparse(ref).query).get("state", [auth0_state])[0]
                    async with self._session.post(
                        ref,
                        timeout=_AUTH_TIMEOUT,
                        data={"code": mfa_code, "state": mfa_state},
                        headers=self._form_headers(),
                        allow_redirects=False,
                    ) as mfa_resp:
                        raw = mfa_resp.headers.get("Location", "")
                        ref = _make_absolute(self._idk_base, raw) if raw else ""
                    continue
                else:
                    if is_email_2fa:
                        raise EmailTwoFactorRequiredError()
                    raise TwoFactorRequiredError()

            # v2.2.0 — Detect Marketing-Consent / T&C interstitial.
            # v2.5.1 — Try auto-skip BEFORE raising MarketingConsentError.
            # Cross-references for the 2026 consent-wall epidemic across all
            # VAG brands: pycupra #83, audi_connect PR #731 (#535/#735),
            # evcc PR #29980 (#29760), myskoda #976, our #309 (moltke69).
            # The IDP randomly interjects a consent screen into the OAuth
            # redirect chain. evcc's solution (merged 2026-05-17) is to
            # detect the ``/consent/marketing/`` interstitial and follow
            # the OIDC ``callback`` URL embedded in the consent request —
            # equivalent to the "not now / skip" path. Login completes with
            # ``consentedScopes=openid profile mbb`` only (no marketing
            # scopes granted). Reduces user friction: no Repair flow needed.
            # If auto-skip fails (callback missing, fetch errors), we fall
            # back to the v2.2.0 behaviour and raise MarketingConsentError
            # so the Repairs UI surfaces a deep-link to the brand portal.
            #
            # URL patterns we recognise:
            # - consent/marketing: legacy signin-service path (skippable)
            # - /u/consent: Auth0 Universal Login consent template
            # - cupraid.vwgroup.io: CUPRA portal-redirect for SEAT/Cupra
            # - skoda-id.vwgroup.io / skodaid.vwgroup.io: Skoda variants
            # - signin-service/v1/terms-and-conditions: T&C prompt (not skippable)
            # - audi-id.vwgroup.io / myaudi.de/consent: Audi-specific (added v2.5.1)
            consent_markers = (
                "consent/marketing",
                "/u/consent",
                "cupraid.vwgroup.io",
                "skoda-id.vwgroup.io",
                "skodaid.vwgroup.io",
                "audi-id.vwgroup.io",
                "myaudi.de/consent",
                "terms-and-conditions",
            )
            if any(marker in ref for marker in consent_markers):
                # T&C prompts cannot be skipped (legal acceptance required).
                # Marketing-consent / interstitials CAN be skipped via the
                # embedded OIDC callback URL (evcc PR #29980).
                if "terms-and-conditions" in ref:
                    _LOGGER.warning(
                        "IDK Auth0: T&C wall at %s — cannot auto-skip "
                        "(legal acceptance required)", ref[:120],
                    )
                    raise TermsAndConditionsError()
                skipped = await self._skip_marketing_consent(ref)
                if skipped:
                    _LOGGER.info(
                        "IDK Auth0: marketing-consent auto-skipped (#309) → %s",
                        skipped[:80],
                    )
                    ref = skipped
                    continue
                _LOGGER.warning(
                    "IDK Auth0: consent wall at %s — auto-skip failed, "
                    "raising MarketingConsentError for Repair flow",
                    ref[:120],
                )
                raise MarketingConsentError()

            try:
                async with self._session.get(
                    ref,
                    timeout=_AUTH_TIMEOUT,
                    headers=self._base_headers(),
                    allow_redirects=False,
                ) as redir_resp:
                    raw_next = redir_resp.headers.get("Location", "")
                    if redir_resp.status in (301, 302, 303, 307, 308) and raw_next:
                        ref = _make_absolute(ref, raw_next)
                    else:
                        break
            except InvalidURL as exc:
                _LOGGER.error("IDK Auth0 redirect: InvalidURL '%s' — %s", ref[:100], exc)
                break

        _LOGGER.debug("IDK Auth0: final redirect = %s", ref[:80] if ref else "(none)")

        if not ref or not ref.startswith(prefix):
            # Print FULL URL on failure (esp. for /v2/login/ui/error which
            # carries error_description in query params we need to debug).
            raise AuthenticationError(
                f"Auth0: no app:// redirect after login. Last: {ref}"
            )

        # Save final redirect URL so MBB-mode callers can extract the
        # cross-service-signed id_token from the query/fragment (v1.26.3).
        self.last_redirect_url = ref

        # MBB-mode short-circuit: in hybrid flow the id_token is already in
        # the redirect URL (typically fragment). It's the cross-service-signed
        # token MBB validates against. We do NOT call _exchange_code because
        # the token endpoint may reject hybrid-flow codes, and the resulting
        # id_token would be app-audience (which MBB rejects). The MBB exchange
        # itself happens out-of-band via mbboauth-1d.prd.ece.vwg-connect.com.
        if mbb_mode:
            id_tok = _extract_param_from_url(
                ref, self._brand.redirect_uri, "id_token"
            )
            if not id_tok:
                raise AuthenticationError(
                    f"MBB hybrid-flow: no id_token in redirect URL "
                    f"({len(ref)} chars). Auth0 may have stripped "
                    f"response_type=id_token for this client. URL: {ref[:200]}"
                )
            _LOGGER.debug(
                "IDK Auth0 MBB hybrid: id_token captured (%d chars)", len(id_tok)
            )
            return TokenSet(access_token="", refresh_token="", id_token=id_tok)

        auth_code = _extract_auth_code(ref, self._brand.redirect_uri)
        if not auth_code:
            raise AuthenticationError(f"Auth0: no code in: {ref[:80]}")

        _LOGGER.debug("IDK Auth0: got auth code, exchanging tokens")
        return await self._exchange_code(auth_code, verifier)

    @staticmethod
    def _extract_auth0_error(html: str) -> str:
        """Extract human-readable error from Auth0 400 response page."""
        for pattern in [
            r'data-error-code=["\']([^"\']+)["\']',
            r'"errorCode"\s*:\s*"([^"]+)"',
            r'class=["\']error[^"\']*["\'][^>]*>([^<]{5,80})<',
        ]:
            m = re.search(pattern, html)
            if m:
                return m.group(1)
        return ""

    async def _auth0_post_form(
        self,
        url: str,
        extra: dict[str, str],
    ) -> tuple[str, str]:
        """POST a form step in Auth0 Universal Login v2.

        Auth0 UL v2: state is in the URL query string, NOT in the body.
        CSRF is handled automatically via session cookies (set on page GET).
        Returns (final_url, response_html).
        """
        data = {**extra}  # NO state in body — Auth0 reads it from URL
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "text/html,application/xhtml+xml,*/*",
            "User-Agent": self._brand.user_agent,
            "Origin": self._idk_base,
            "Referer": url,
        }
        async with self._session.post(
            url,
            timeout=_AUTH_TIMEOUT,
            data=data,
            headers=headers,
            allow_redirects=True,
        ) as resp:
            final_url = str(resp.url)
            resp_html = await resp.text(errors="replace")
            _LOGGER.debug(
                "IDK Auth0 form POST %s → status=%s url=%s html_len=%d",
                url[-40:], resp.status, final_url[-60:], len(resp_html),
            )
            if resp.status == 401:
                raise AuthenticationError("Invalid email or password (Auth0 401).")
            if resp.status == 429:
                raise RateLimitError()
            if resp.status not in (200, 302, 400):
                raise AuthenticationError(
                    f"Auth0 form POST returned HTTP {resp.status}: {resp_html[:200]}"
                )
            # 400: Auth0 returns login page again — caller decides what to do
            if resp.status == 400:
                _LOGGER.debug(
                    "IDK Auth0 form POST 400 — html_len=%d url=%s",
                    len(resp_html), final_url[-60:],
                )
        return final_url, resp_html

    async def _authenticate_legacy(
        self,
        html: str,
        email: str,
        password: str,
        verifier: str,
        mbb_mode: bool = False,
    ) -> TokenSet:
        """Legacy signin-service flow — ported 1:1 from audiconnect (arjenvrh, MIT).

        audiconnect approach (confirmed working):
          1. Parse hidden form fields + form action from authorize page
          2. POST email with ALL step1 fields + cookies from step1 GET
          3. Extract hmac from JavaScript in response (JS-rendered, not in form)
          4. POST password using step1 fields + new hmac (NOT step2 fields!)
             with allow_redirects=False, cookies from step1
          5. Manually follow exactly 3 redirects (each with step1 cookies)
          6. Extract auth code from final redirect Location
        """
        # Step 1 — parse initial login page
        csrf1 = self._parse_csrf_robust(html)
        _LOGGER.debug(
            "IDK legacy: step1 fields=%s action=%s",
            list(csrf1.fields.keys()),
            csrf1.form_action[:80] if csrf1.form_action else "(none)",
        )
        if not csrf1.fields.get("_csrf") and not csrf1.fields.get("hmac") \
                and not csrf1.fields.get("relayState"):
            raise AuthenticationError(
                "Could not parse IDK login page (legacy flow) — no form fields found."
            )

        email_url = _absolute_url(
            self._idk_base,
            csrf1.form_action or f"{self._signin_base}/{self._signin_client_id}/login/identifier",
        )

        # audiconnect: submit_data starts with ALL step1 hidden fields + email
        submit_data: dict[str, str] = {**csrf1.fields, "email": email}

        # Step 2 — POST email (audiconnect: cookies=step1_cookies, allow_redirects=True)
        _LOGGER.debug("IDK legacy: posting email to %s", email_url[:100])
        async with self._session.post(
            email_url,
            timeout=_AUTH_TIMEOUT, data=submit_data,
            headers=self._form_headers(), allow_redirects=True,
        ) as resp:
            if resp.status != 200:
                raise AuthenticationError(
                    f"Email POST HTTP {resp.status} at {email_url[:80]}"
                )
            html2 = await resp.text()

        # Step 3 — extract hmac from JavaScript (audiconnect pattern)
        # "new HTML response uses JS to build form — extract hmac from embedded JS"
        hmac_matches = re.findall(r'"hmac"\s*:\s*"([0-9a-fA-F]+)"', html2)
        if hmac_matches:
            # audiconnect: UPDATE submit_data with new hmac, keep _csrf+relayState from step1
            submit_data["hmac"] = hmac_matches[0]
            # Password URL: replace "identifier" with "authenticate" in email_url
            pw_url = email_url.replace("identifier", "authenticate")
            _LOGGER.debug(
                "IDK legacy: hmac from JS, step1 fields kept, pw_url=%s", pw_url[:100]
            )
        else:
            # Fallback: try form fields from password page
            csrf2 = self._parse_csrf_robust(html2)
            submit_data = {**csrf2.fields, "email": email, "password": password}
            if csrf2.form_action:
                pw_url = _absolute_url(self._idk_base, csrf2.form_action)
            else:
                pw_url = email_url.replace("identifier", "authenticate") \
                    if "identifier" in email_url \
                    else _absolute_url(
                        self._idk_base,
                        f"{self._signin_base}/{self._signin_client_id}/login/authenticate",
                    )
            _LOGGER.debug(
                "IDK legacy: no hmac in JS, using form fields=%s pw_url=%s",
                list(csrf2.fields.keys()), pw_url[:100],
            )

        submit_data["password"] = password

        # Step 4 — POST password (audiconnect: allow_redirects=False, manual redirects)
        _LOGGER.debug(
            "IDK legacy: posting password to %s fields=%s",
            pw_url[:100], list(submit_data.keys()),
        )
        async with self._session.post(
            pw_url,
            timeout=_AUTH_TIMEOUT, data=submit_data,
            headers=self._form_headers(), allow_redirects=False,
        ) as resp:
            pw_status = resp.status
            pw_loc = _make_absolute(pw_url, resp.headers.get("Location", ""))
            pw_body = await resp.text() if pw_status != 302 else ""

        _LOGGER.debug(
            "IDK legacy: password POST status=%s location=%s",
            pw_status, pw_loc[:80] if pw_loc else "(none)",
        )

        if pw_status == 200:
            if "terms-and-conditions" in pw_body.lower():
                raise TermsAndConditionsError()
            # v2.2.0 (#183 follow-on) — discriminate Email-OTP 2FA from
            # generic / TOTP 2FA. Body markers observed on legacy signin-
            # service: "email-otp", "email-code", "send-email-code" all
            # indicate the IDP wants the user to check inbox for a code.
            pw_body_lc = pw_body.lower()
            if any(m in pw_body_lc for m in ("email-otp", "email-code", "send-email-code")):
                raise EmailTwoFactorRequiredError()
            if "two-factor" in pw_body_lc or "2fa" in pw_body_lc:
                raise TwoFactorRequiredError()
            raise AuthenticationError(
                "Unexpected 200 after password POST — wrong credentials?"
            )
        if pw_status == 401:
            raise AuthenticationError("Invalid credentials (401).")
        if pw_status == 429:
            raise RateLimitError()
        if pw_status not in (302, 303):
            raise AuthenticationError(
                f"Password POST HTTP {pw_status} at {pw_url[:80]}: {pw_body[:200]}"
            )
        if not pw_loc:
            # v2.5.1 — audi_connect PR #731 inspiration: a missing Location
            # header after a 302/303 typically means the IDP is showing a
            # consent/terms page instead of redirecting. Give the user an
            # actionable hint rather than the cryptic raw header error.
            raise AuthenticationError(
                "Login redirect missing after password submission "
                f"(HTTP {pw_status}). The Audi/VW/Skoda IDP may be showing "
                "a consent or terms-of-service prompt that we couldn't "
                "auto-detect. Please log in once via the brand app or "
                "website, accept any pending agreements, then retry."
            )

        # Step 5 — follow redirect chain (audiconnect: 3 explicit GETs)
        prefix = self._brand.redirect_uri.split("://")[0] + "://"
        ref = pw_loc
        for hop in range(10):
            _LOGGER.debug("IDK legacy: redirect hop %d → %s", hop + 1, ref[:100])
            if ref.startswith(prefix):
                break
            if "terms-and-conditions" in ref:
                raise TermsAndConditionsError()
            async with self._session.get(
                ref,
                timeout=_AUTH_TIMEOUT, headers=self._base_headers(), allow_redirects=False,
            ) as redir:
                next_loc = redir.headers.get("Location", "")
                if redir.status in (301, 302, 303, 307, 308) and next_loc:
                    ref = _make_absolute(ref, next_loc)
                else:
                    break

        _LOGGER.debug("IDK legacy: final ref=%s", ref[:100])

        # Save final redirect URL so MBB-mode callers can extract the
        # cross-service-signed id_token from the query/fragment (v1.26.3).
        self.last_redirect_url = ref

        # MBB-mode short-circuit (same logic as auth0 path; legacy flow
        # may also return id_token in the URL when response_type includes it).
        if mbb_mode:
            id_tok = _extract_param_from_url(
                ref, self._brand.redirect_uri, "id_token"
            )
            if id_tok:
                return TokenSet(access_token="", refresh_token="", id_token=id_tok)
            # else fall through to normal code exchange

        auth_code = _extract_auth_code(ref, self._brand.redirect_uri)
        if not auth_code:
            raise AuthenticationError(f"Legacy: no code in: {ref[:100]}")

        return await self._exchange_code(auth_code, verifier)

    async def refresh(self, refresh_token: str) -> TokenSet:
        """Exchange a refresh token for a fresh token set.

        Refresh endpoints differ by brand:
        - Škoda: proprietary endpoint on mysmob
        - SEAT/CUPRA: OLA endpoint (CUPRA includes client_secret)
        - VW EU/Audi: CARIAD BFF
        """
        if self._brand.name == "skoda":
            return await self._refresh_skoda(refresh_token)

        # SEAT and CUPRA both refresh via OLA endpoint
        if self._brand.name in ("seat", "cupra"):
            token_url = "https://ola.prod.code.seat.cloud.vwgroup.com/authorization/api/v1/token"
        else:
            token_url = self._get_token_endpoint()

        data: dict[str, str] = {
            "client_id": self._brand.client_id,
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        }
        if self._brand.client_secret:
            data["client_secret"] = self._brand.client_secret

        # v2.5.4 (#313) — Audi + VW EU require the assertion header set
        # at the CARIAD BFF token endpoint AFTER the 2026-05-28 Azure
        # WAF migration. The header set must be sent on refresh too —
        # otherwise the access_token works for ~1h and then refresh
        # quietly starts returning 403 (the failure mode evcc PR #30292
        # documented). Other brands keep using the legacy form headers.
        # v2.5.11 — pass per-brand android_package_name (was hardcoded
        # to Audi pre-v2.5.11; latent VW-impersonates-Audi bug fixed).
        if self._brand.name in ("audi", "volkswagen"):
            headers = _cariad_token_headers(
                self._brand.user_agent,
                android_package_name=(
                    self._brand.android_package_name
                    or "de.myaudi.mobile.assistant"
                ),
            )
        else:
            headers = self._form_headers()

        async with self._session.post(
            token_url,
            timeout=_AUTH_TIMEOUT, data=data, headers=headers,
        ) as resp:
            if resp.status == 400:
                raise TokenExpiredError("Refresh token rejected — full re-login required.")
            if resp.status != 200:
                raise AuthenticationError(f"Token refresh returned HTTP {resp.status}")
            payload: dict[str, Any] = await resp.json()

        return self._parse_tokens(payload)

    async def _refresh_skoda(self, refresh_token: str) -> TokenSet:
        """Škoda uses a proprietary refresh endpoint."""
        url = (
            "https://mysmob.api.connect.skoda-auto.cz"
            "/api/v1/authentication/refresh-token?tokenType=CONNECT"
        )
        async with self._session.post(
            url, timeout=_AUTH_TIMEOUT,
            json={"token": refresh_token},
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": self._brand.user_agent,
            },
        ) as resp:
            if resp.status == 400:
                raise TokenExpiredError("Škoda refresh token rejected.")
            if resp.status != 200:
                raise AuthenticationError(f"Škoda token refresh HTTP {resp.status}")
            payload: dict[str, Any] = await resp.json()

        return self._parse_tokens(payload)

    # ── Auth0 Universal Login helpers ─────────────────────────────────────────

    @staticmethod
    def _extract_auth0_csrf(html: str) -> str:
        """Extract Auth0 CSRF token from page HTML (fallback if cookie missing)."""
        patterns = [
            r'"csrf"\s*:\s*"([^"]{8,})"',
            r"_csrf[\"']\s*:\s*[\"']([^\"']{8,})[\"']",
            r'name=["\']_csrf["\'][^>]+value=["\']([^"\']+)["\']',
            r'value=["\']([^"\']+)["\'][^>]+name=["\']_csrf["\']',
        ]
        for p in patterns:
            m = re.search(p, html)
            if m:
                return m.group(1)
        return ""

    async def _submit_auth0_callback(self, html: str) -> str | None:
        """Parse Auth0 form_post response and POST to /login/callback.

        After /usernamepassword/login, Auth0 returns an HTML page with:
          <form method="post" action="https://identity.vwgroup.io/login/callback">
            <input name="wctx" value="...">
            <input name="wresult" value="...">
          </form>
        We must POST these fields to continue the flow.
        """
        parser = _CSRFParser()
        parser.feed(html)

        # Also try regex for the hidden fields
        for tag in re.finditer(r"<input[^>]+>", html, re.IGNORECASE):
            t = tag.group(0)
            if 'type="hidden"' not in t.lower() and "type='hidden'" not in t.lower():
                continue
            nm = re.search(r'name=["\']([^"\']+)["\']', t)
            vm = re.search(r'value=["\']([^"\']*)["\']', t)
            if nm:
                parser.fields[nm.group(1)] = vm.group(1) if vm else ""

        if not parser.form_action and not parser.fields:
            # Might be a direct JSON response with location
            m = re.search(r'"location"\s*:\s*"([^"]+)"', html)
            if m:
                return m.group(1)
            _LOGGER.warning("Auth0 callback: no form fields in response (len=%d)", len(html))
            return None

        callback_url = parser.form_action or f"{self._idk_base}/login/callback"
        if not callback_url.startswith("http"):
            callback_url = self._idk_base + callback_url

        _LOGGER.debug("IDK Auth0: posting callback to %s fields=%s",
                      callback_url[:60], list(parser.fields.keys()))

        async with self._session.post(
            callback_url,
            timeout=_AUTH_TIMEOUT,
            data=parser.fields,
            headers=self._form_headers(),
            allow_redirects=False,
        ) as resp:
            location = resp.headers.get("Location", "")
            _LOGGER.debug("IDK Auth0: callback status=%s location=%s",
                          resp.status, location[:60])
            return location if location else None

    async def _follow_to_app_redirect_get(
        self, start_url: str, app_prefix_full: str
    ) -> str | None:
        """Follow GET redirects from a URL until we reach the app:// URI."""
        prefix = app_prefix_full.split("://")[0] + "://"
        location = start_url

        for _ in range(15):
            if location.startswith(prefix):
                return location
            if not location.startswith("http"):
                # Relative or app:// — return as-is
                return location if location.startswith(prefix) else None

            async with self._session.get(
                location,
                timeout=_AUTH_TIMEOUT,
                headers=self._base_headers(),
                allow_redirects=False,
            ) as resp:
                new_loc = resp.headers.get("Location", "")
                if resp.status in (301, 302, 303, 307, 308) and new_loc:
                    location = new_loc
                elif location.startswith(prefix):
                    return location
                else:
                    # Read body in case it's another form_post
                    body = await resp.text(errors="replace")
                    if "<form" in body.lower():
                        next_loc = await self._submit_auth0_callback(body)
                        if next_loc:
                            location = next_loc
                            continue
                    break

        return location if location.startswith(prefix) else None

    # ── Legacy signin-service helpers ─────────────────────────────────────────



    async def _follow_to_app_redirect(
        self, url: str, data: dict[str, str], app_prefix_full: str
    ) -> str | None:
        """POST data, then follow HTTP 302 redirects until we hit the app URI."""
        prefix = app_prefix_full.split("://")[0] + "://"
        async with self._session.post(
            url,
            timeout=_AUTH_TIMEOUT, data=data, headers=self._form_headers(), allow_redirects=False
        ) as resp:
            if resp.status == 200:
                body = await resp.text()
                body_lc = body.lower()
                if "terms-and-conditions" in body_lc:
                    raise TermsAndConditionsError()
                if "marketing" in body_lc and "consent" in body_lc:
                    raise MarketingConsentError()
                # v2.2.0 (#183 follow-on) — Email-OTP discrimination
                # (must come BEFORE the generic 2FA check; Email-OTP
                # bodies also contain "two-factor" boilerplate from the
                # IDP template).
                if any(m in body_lc for m in ("email-otp", "email-code", "send-email-code")):
                    raise EmailTwoFactorRequiredError()
                if "two-factor" in body_lc or "2fa" in body_lc:
                    raise TwoFactorRequiredError()
                raise AuthenticationError("Unexpected non-redirect after password submission.")
            if resp.status == 429:
                raise RateLimitError()
            if resp.status == 401:
                raise AuthenticationError("Password rejected — wrong credentials.")
            if resp.status not in (302, 303, 301, 307, 308):
                body = await resp.text()
                raise AuthenticationError(
                    f"Password POST returned HTTP {resp.status} at {url[:100]}: {body[:200]}"
                )
            raw_loc = resp.headers.get("Location", "")
            location = _make_absolute(url, raw_loc) if raw_loc else ""
            current_base = url
            _LOGGER.debug(
                "IDK legacy: password POST status=%s location=%s",
                resp.status, location[:80] if location else "(none)",
            )
            if not location:
                raise AuthenticationError(
                    f"Password POST returned {resp.status} but no Location header."
                )

        # Follow redirect chain until app:// or max 10 hops
        for _ in range(10):
            if not location:
                _LOGGER.debug("IDK legacy: empty location in redirect chain")
                break
            # Capture user_id from redirect URL (SEAT/CUPRA pattern from pycupra)
            if "user_id" in location:
                uid = parse_qs(urlparse(location).query).get("user_id", [""])[0]
                if uid:
                    self.user_id = uid
                    _LOGGER.debug("IDK: captured user_id from redirect: %s", uid[:8])
            if location.startswith(prefix):
                return location
            # v2.2.0 / v2.5.1 — Consent-wall detection (symmetric with
            # Auth0 flow above). v2.5.1 adds auto-skip via evcc-style
            # OIDC callback follow (PR #29980, our #309).
            if "terms-and-conditions" in location:
                raise TermsAndConditionsError()
            _consent_markers = (
                "consent/marketing",
                "/u/consent",
                "cupraid.vwgroup.io",
                "skoda-id.vwgroup.io",
                "skodaid.vwgroup.io",
                "audi-id.vwgroup.io",
                "myaudi.de/consent",
            )
            if any(marker in location for marker in _consent_markers):
                skipped = await self._skip_marketing_consent(location)
                if skipped:
                    _LOGGER.info(
                        "IDK legacy: marketing-consent auto-skipped (#309) → %s",
                        skipped[:80],
                    )
                    location = skipped
                    continue
                _LOGGER.warning(
                    "IDK legacy: consent wall at %s — auto-skip failed, "
                    "raising MarketingConsentError",
                    location[:120],
                )
                raise MarketingConsentError()
            _LOGGER.debug("IDK legacy: following redirect → %s", location[:80])
            async with self._session.get(
                location,
                timeout=_AUTH_TIMEOUT, headers=self._base_headers(), allow_redirects=False
            ) as resp:
                if resp.status in (301, 302, 303, 307, 308):
                    raw_next = resp.headers.get("Location", "")
                    current_base = location
                    location = _make_absolute(current_base, raw_next) if raw_next else ""
                elif location.startswith(prefix):
                    return location
                else:
                    _LOGGER.debug(
                        "IDK legacy: redirect chain ended — status=%s url=%s",
                        resp.status, location[:80],
                    )
                    break

        return location if location.startswith(prefix) else None

    async def _exchange_code(self, code: str, verifier: str) -> TokenSet:
        """POST authorization code + PKCE verifier → tokens.

        Each brand uses a different token exchange mechanism:
        - VW EU / Audi: CARIAD BFF (standard OAuth)
        - CUPRA: IDK /oidc/v1/token (standard OAuth + client_secret)
        - SEAT: OLA /authorization/api/v1/token (standard OAuth, no secret)
        - Škoda: proprietary JSON API on mysmob (not OAuth)
        """
        if self._brand.name == "skoda":
            return await self._exchange_code_skoda(code, verifier)

        # v2.5.6 — APK-primary auth config with competitor fallback. The
        # resolver loads values from .app-atlas-apk-cache/{brand}.json
        # when available; falls back to v2.5.4 hardcoded constants if not.
        # v2.5.7 R2 — also pass the PRIOR qmauth pair as last-resort
        # fallback in case VW rotates again and we haven't ported the
        # new value yet.
        resolver = AuthConfigResolver(
            self._brand.name,
            hardcoded_client_id=self._brand.client_id,
            hardcoded_qmauth_secret=_QM_SECRET,
            hardcoded_qmauth_client_id=_QM_CLIENT_ID,
            hardcoded_token_url=_CARIAD_TOKEN_URL,
            prior_qmauth_secret=_QM_PRIOR_SECRET,
            prior_qmauth_client_id=_QM_PRIOR_CLIENT_ID,
        )
        # v2.5.7 R3 — try OIDC discovery for the token URL before
        # falling back to APK / hardcoded values. Best-effort: a
        # discovery failure silently uses whatever ``token_url()``
        # already returns. Throttled to once per hour per brand via
        # module-level cache so this adds zero extra latency on
        # repeated polls within the TTL window.
        if self._brand.name in ("audi", "volkswagen"):
            try:
                await resolver.refresh_via_discovery(self._session)
            except Exception:  # noqa: BLE001 — defense-in-depth
                pass
        token_url = (
            resolver.token_url()
            if self._brand.name in ("audi", "volkswagen")
            else self._get_token_endpoint()
        )

        # v2.5.6 — OAuth client_id fallback chain. The retro-mining of
        # the 2026-05-27 APKs surfaced UUID@apps_vw-dilab_com values
        # that aren't our hardcoded canonical client_id but ARE in the
        # official app's DEX (purpose unknown — possibly region-specific
        # or new post-WAF preferred). We try the hardcoded canonical
        # first (worked for years; multi-source verified), then the APK
        # alternates, and only fail if ALL candidates return 4xx.
        # Non-Audi/VW brands stay single-shot (no fallback chain because
        # their IDPs are stable).
        #
        # v2.5.7 R2 — combined client_id × qmauth attempts list. For
        # CARIAD-BFF brands we build the Cartesian product of:
        #   - OAuth client_id chain (canonical + APK alternates)
        #   - qmauth chain (current + prior, in case VW re-rotated)
        # Total attempts capped at ~6 per call (3 client_ids × 2 qmauth
        # tuples). The first 200 short-circuits the rest.
        if self._brand.name in ("audi", "volkswagen"):
            client_id_chain = resolver.oauth_client_id_chain()
            qmauth_chain = resolver.qmauth_chain()
            attempts: list[tuple[str, str, str]] = [
                (cid, qm_s, qm_c)
                for cid in client_id_chain
                for (qm_s, qm_c) in qmauth_chain
            ]
            _LOGGER.debug(
                "Token exchange (v2.5.7 resolver): brand=%s attempts=%d url=%s prov=%s",
                self._brand.name, len(attempts), token_url,
                resolver.provenance(),
            )
        else:
            client_id_chain = [self._brand.client_id]
            attempts = [(self._brand.client_id, "", "")]

        last_error: AuthenticationError | None = None
        for idx, (client_id, qm_secret, qm_client_id) in enumerate(attempts):
            data: dict[str, str] = {
                "client_id": client_id,
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": self._brand.redirect_uri,
                "code_verifier": verifier,
            }
            if self._brand.client_secret:
                data["client_secret"] = self._brand.client_secret

            # v2.5.7 R2 — assertion headers signed with this attempt's qmauth.
            # v2.5.11 — per-brand x-android-package-name (was hardcoded to
            # Audi value pre-v2.5.11; latent VW-impersonation bug fixed).
            if self._brand.name in ("audi", "volkswagen"):
                headers = _cariad_token_headers(
                    self._brand.user_agent,
                    qmauth_secret=qm_secret,
                    qmauth_client_id=qm_client_id,
                    android_package_name=(
                        self._brand.android_package_name
                        or "de.myaudi.mobile.assistant"
                    ),
                )
            else:
                headers = self._form_headers()

            try:
                async with self._session.post(
                    token_url,
                    timeout=_AUTH_TIMEOUT, data=data, headers=headers,
                ) as resp:
                    if resp.status == 200:
                        if idx > 0:
                            _LOGGER.info(
                                "Token exchange (%s): fallback attempt #%d "
                                "succeeded (client_id=%s..%s, qmauth_cid=%s) — "
                                "primary candidates 4xx'd",
                                self._brand.name, idx,
                                client_id[:8] if client_id else "?",
                                client_id[-4:] if client_id else "?",
                                qm_client_id or "n/a",
                            )
                        payload: dict[str, Any] = await resp.json()
                        return self._parse_tokens(payload)
                    body = await resp.text()
                    # v2.5.7 (#313 follow-on / 502 storm 2026-05-29) — 5xx
                    # responses from the CARIAD-BFF mean the VW backend is
                    # flapping (Azure WAF + upstream Azure incidents), NOT
                    # that the credentials are wrong. Raise the dedicated
                    # ``UpstreamUnavailableError`` so the config-flow /
                    # repair UI surfaces a non-credentials message and
                    # users do NOT reconfigure the integration in a panic.
                    # The _request retry layer handles its own 5xx retries
                    # at the API call layer; the auth path here doesn't
                    # retry because PKCE codes are single-use (a retry
                    # would just hit "code already used").
                    if 500 <= resp.status < 600:
                        _LOGGER.warning(
                            "Token exchange (%s): upstream HTTP %d — VW "
                            "backend flapping. Not a credentials issue.",
                            self._brand.name, resp.status,
                        )
                        raise UpstreamUnavailableError(
                            resp.status, brand=self._brand.name,
                        )
                    # 4xx → try next (client_id, qmauth) attempt.
                    if 400 <= resp.status < 500 and idx < len(attempts) - 1:
                        _LOGGER.debug(
                            "Token exchange (%s) attempt #%d (client_id=%s..%s, "
                            "qmauth_cid=%s) rejected HTTP %d — trying next",
                            self._brand.name, idx,
                            client_id[:8] if client_id else "?",
                            client_id[-4:] if client_id else "?",
                            qm_client_id or "n/a",
                            resp.status,
                        )
                        last_error = AuthenticationError(
                            f"Token exchange failed HTTP {resp.status}: {body[:200]}"
                        )
                        continue
                    raise AuthenticationError(
                        f"Token exchange failed HTTP {resp.status}: {body[:200]}"
                    )
            except (AuthenticationError, UpstreamUnavailableError):
                raise

        # Chain exhausted without success.
        raise last_error or AuthenticationError(
            "Token exchange: all client_id × qmauth candidates exhausted"
        )

    async def _exchange_code_skoda(self, code: str, verifier: str) -> TokenSet:
        """Škoda uses a proprietary token exchange — not standard OAuth."""
        url = (
            "https://mysmob.api.connect.skoda-auto.cz"
            "/api/v1/authentication/exchange-authorization-code?tokenType=CONNECT"
        )
        payload = {
            "code": code,
            "redirectUri": self._brand.redirect_uri,
            "verifier": verifier,
        }
        _LOGGER.debug("Škoda token exchange: %s", url)
        async with self._session.post(
            url, timeout=_AUTH_TIMEOUT, json=payload,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": self._brand.user_agent,
            },
        ) as resp:
            if resp.status != 200:
                body = await resp.text()
                raise AuthenticationError(
                    f"Škoda token exchange failed HTTP {resp.status}: {body[:200]}"
                )
            data: dict[str, Any] = await resp.json()

        return self._parse_tokens(data)

    async def _skip_marketing_consent(self, consent_url: str) -> str | None:
        """Auto-skip the optional VW/Audi marketing-consent interstitial (v2.5.1).

        Python port of evcc PR #29980 (`skipMarketingConsent`, merged
        2026-05-17, MIT). VW periodically interjects an optional consent
        page after an otherwise successful login. The page URL carries an
        OIDC ``callback=https://...`` query parameter that — when followed
        — completes the login WITHOUT granting marketing scopes (the
        "not now" path). This recovers transparently instead of forcing
        the user through a Repair flow.

        Args:
            consent_url: The full URL of the consent interstitial that
                we landed on in the redirect chain.

        Returns:
            The next ``Location`` header from following the callback URL,
            or ``None`` if auto-skip is not possible (callback missing,
            network error, unexpected response).
        """
        parsed = urlparse(consent_url)
        callback = parse_qs(parsed.query).get("callback", [""])[0]
        if not callback:
            _LOGGER.debug(
                "IDK consent-skip: no callback param in %s — cannot auto-skip",
                consent_url[:100],
            )
            return None

        cb_url = _make_absolute(consent_url, callback)
        try:
            async with self._session.get(
                cb_url,
                timeout=_AUTH_TIMEOUT,
                headers=self._base_headers(),
                allow_redirects=False,
            ) as cb_resp:
                next_loc = cb_resp.headers.get("Location", "")
                _LOGGER.debug(
                    "IDK consent-skip: callback %s → status=%s next=%s",
                    cb_url[:80], cb_resp.status,
                    next_loc[:80] if next_loc else "(none)",
                )
                if not next_loc:
                    return None
                return _make_absolute(cb_url, next_loc)
        except (InvalidURL, Exception) as exc:  # noqa: BLE001
            _LOGGER.warning(
                "IDK consent-skip: callback GET failed — %s: %s",
                type(exc).__name__, exc,
            )
            return None

    def _get_token_endpoint(self) -> str:
        """Return the correct token endpoint for the current brand.

        v2.3.0 — per-instance override wins over the brand-name lookup.
        VW NA constructs IDKAuth with ``token_url_override=
        f"{api_base}/oidc/v1/token"`` so the token-exchange + refresh
        calls go to the NA-specific con-veh.net host, not to the EU
        emea.bff.cariad.digital fallback.

        v2.5.4 (#313) — VW shut down the legacy ``/login/v1/idk/token``
        BFF endpoint at the Azure WAF layer on 2026-05-28. Audi + VW EU
        now use the OIDC-style ``/auth/v1/idk/oidc/token`` replacement.
        Cross-references: evcc PR #30277 + #30292 (MIT),
        volkswagencarnet PR #331, TA2k/ioBroker.vw-connect.
        """
        if self._token_url_override:
            return self._token_url_override
        if self._brand.name == "cupra":
            return f"{_IDK_BASE}/oidc/v1/token"
        if self._brand.name == "seat":
            return "https://ola.prod.code.seat.cloud.vwgroup.com/authorization/api/v1/token"
        # VW EU, Audi, and others: CARIAD BFF — v2.5.4 migrated URL.
        return _CARIAD_TOKEN_URL

    def _parse_tokens(self, payload: dict[str, Any]) -> TokenSet:
        """Parse token response into a TokenSet.

        Handles both snake_case (OAuth standard) and camelCase (Škoda proprietary).
        """
        access = payload.get("access_token") or payload.get("accessToken")
        refresh = payload.get("refresh_token") or payload.get("refreshToken")
        id_tok = payload.get("id_token") or payload.get("idToken") or ""
        if not access or not refresh:
            raise AuthenticationError(
                f"Token response missing required fields: {list(payload)}"
            )
        return TokenSet(access_token=access, refresh_token=refresh, id_token=id_tok)

    @staticmethod
    def _parse_csrf(html: str) -> _CSRFParser:
        parser = _CSRFParser()
        parser.feed(html)
        return parser

    @staticmethod
    def _parse_csrf_robust(html: str) -> _CSRFParser:
        """Parse CSRF from IDK login page — handles multiple page structures.

        IDK has changed their login page over the years:
        - Classic (2022): <input type="hidden" name="_csrf" value="...">
        - Modern (2024+): CSRF embedded in <script> JSON block
        - Also tries regex fallback for all hidden inputs.
        """
        parser = _CSRFParser()
        parser.feed(html)

        # Fallback 1 — regex over ALL hidden inputs (HTMLParser can miss JS-rendered)
        for tag in re.finditer(r"<input[^>]+>", html, re.IGNORECASE):
            t = tag.group(0)
            if 'type="hidden"' not in t.lower() and "type='hidden'" not in t.lower():
                continue
            nm = re.search(r'name=["\']([^"\']+)["\']', t)
            vm = re.search(r'value=["\']([^"\']*)["\']', t)
            if nm:
                parser.fields[nm.group(1)] = vm.group(1) if vm else ""

        # Fallback 2 — form action via regex
        if not parser.form_action:
            fm = re.search(r'action=["\']([^"\']+/login/[^"\']+)["\']', html)
            if fm:
                parser.form_action = fm.group(1)

        # Fallback 3 — CSRF in JSON/script blocks (modern IDK SPA pages)
        # e.g.: {"_csrf":"token","hmac":"hexval",...}
        # or:   window.__STORE__ = {...,"csrf":"token",...}
        if not parser.fields.get("_csrf"):
            for pattern in [
                r'"_csrf"\s*:\s*"([^"]{8,})"',
                r'"csrf"\s*:\s*"([^"]{8,})"',
                r'"csrfToken"\s*:\s*"([^"]{8,})"',
            ]:
                m = re.search(pattern, html)
                if m:
                    parser.fields["_csrf"] = m.group(1)
                    _LOGGER.debug("IDK: _csrf extracted via JSON pattern")
                    break

        if not parser.fields.get("hmac"):
            m = re.search(r'"hmac"\s*:\s*"([0-9a-fA-F]{20,})"', html)
            if m:
                parser.fields["hmac"] = m.group(1)
                _LOGGER.debug("IDK: hmac extracted via JSON pattern")

        return parser

    def _base_headers(self) -> dict[str, str]:
        return {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "de-de",
            "User-Agent": self._brand.user_agent,
        }

    def _form_headers(self) -> dict[str, str]:
        return {
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json,text/html,*/*",
            "User-Agent": self._brand.user_agent,
        }
