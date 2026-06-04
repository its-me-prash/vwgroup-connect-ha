# Copyright 2026 Prash Balan (@its-me-prash) — Apache License 2.0
# SPDX-License-Identifier: Apache-2.0
"""v2.6.0 — EU Data Act portal third-tier auth strategy.

This module is the in-house implementation of the EU Data Act consumer
portal authentication flow. It is the third-tier fallback strategy in
the multi-strategy auth resolver: it activates only when both the
hybrid OIDC flow and the classic auth-code flow have failed.

The portal lives at ``eu-data-act.drivesomethinggreater.com`` and is
the Volkswagen Group's EU-Data-Act-compliance interface for end users
who want to access their own vehicle data. Authentication is regular
OAuth-style with the user's Brand ID account; no Play Integrity
attestation is required because the portal is a web flow targeted at
browsers rather than the official mobile app.

## Data semantics

- Read-only: the portal does not expose write/command endpoints. When
  this strategy is the active one, the integration MUST disable
  command entities (lock/unlock, climate, charge start, etc.) and
  fall back to read-only sensors only.
- 15-minute cadence: the portal publishes new dataset drops every
  15 minutes per VIN (server-side limit, not a polite-poll choice).
- Prerequisite: the vehicle owner must have already enabled
  continuous-data-delivery on the portal at least once for the
  integration to find datasets to fetch. Surface this in the HA
  Repair-issue flow when no datasets are returned.

## Why in-house

We do not depend on, fork or reference any external community
project for this implementation. The OIDC client identifier and the
portal endpoint URLs used below are derived from the VW Group public
OIDC discovery document at
``https://identity.vwgroup.io/.well-known/openid-configuration`` and
from observation of the portal's own web traffic — both public
resources that any vehicle owner can inspect themselves.

## When this strategy activates

The base API client iterates strategies in priority order. The Data
Act portal is intentionally last because it is read-only and slower
than the live BFF paths. It activates when:

1. Hybrid OIDC flow raises ``AuthenticationError``
2. Classic auth-code + BFF token exchange also raises
   ``AuthenticationError``

When this strategy returns a TokenSet, the strategy field is set to
``"data_act_portal"`` so the coordinator can:

- Skip refresh-token use (the portal session uses cookies, not OAuth
  refresh)
- Throttle the polling cycle to 15 minutes minimum
- Disable command entities (lock, climate, charge actions)
- Surface a persistent_notification informing the user that the
  integration is operating in read-only fallback mode
"""

from __future__ import annotations

import base64
import hashlib
import logging
import secrets
import time
from typing import TYPE_CHECKING
from urllib.parse import parse_qs, urlparse

if TYPE_CHECKING:
    from aiohttp import ClientSession

from ..exceptions import AuthenticationError
from ..models import TokenSet

_LOGGER = logging.getLogger(__name__)


# Portal endpoints — public web URLs. The OIDC client identifier is
# the public Brand ID OAuth client registered for the consumer portal
# at identity.vwgroup.io; it is visible in any browser's network
# inspector when a user visits the portal's login page.
_PORTAL_BASE = "https://eu-data-act.drivesomethinggreater.com"
_PORTAL_OIDC_CLIENT_ID = "9b58543e-1c15-4193-91d5-8a14145bebb0@apps_vw-dilab_com"
_PORTAL_OIDC_SCOPE = "openid cars profile"
_PORTAL_OIDC_REDIRECT_URI = f"{_PORTAL_BASE}/login"
_IDP_AUTHORIZE_URL = "https://identity.vwgroup.io/oidc/v1/authorize"
_IDP_TOKEN_URL = "https://identity.vwgroup.io/oidc/v1/token"
_PORTAL_LOGIN_CALLBACK_PATH = "/services/callbacklogin"

# Per-brand state-string suffix expected by the portal so it routes
# users to the brand-specific landing area after login. Matches the
# portal-side router shipped at eu-data-act.drivesomethinggreater.com.
# Country/language are passed in via the runtime call.
_BRAND_STATE_FRAGMENTS = {
    "volkswagen": "VOLKSWAGEN_PASSENGER_CARS",
    "audi": "AUDI",
    "skoda": "SKODA",
    "seat": "SEAT",
    "cupra": "CUPRA",
    "bentley": "BENTLEY",
}

_DEFAULT_COUNTRY = "DE"
_DEFAULT_LANGUAGE = "de"
_PORTAL_REQUEST_TIMEOUT_S = 30


def _build_state(brand_name: str, country: str, language: str) -> str:
    """Return the state-string expected by the portal router.

    Format: ``{language}__{country}__{brand_suffix}`` (e.g.
    ``de__de__VOLKSWAGEN_PASSENGER_CARS``). The portal's state-string
    routing decodes the language first, then the country, then the
    brand-suffix that matches its internal brand-routing enum.

    Pre-v2.10.2 we shipped the wrong order ``{country}__{language}``
    which works for de_DE users (both halves identical) but routes the
    wrong locale for any non-matching country/language pair. Verified
    against a live portal trace 2026-06-03.

    Falls back to VOLKSWAGEN_PASSENGER_CARS for unknown brand names so
    the login at least lands somewhere instead of erroring out.
    """
    brand_suffix = _BRAND_STATE_FRAGMENTS.get(
        brand_name.lower(), _BRAND_STATE_FRAGMENTS["volkswagen"],
    )
    return f"{language.lower()}__{country.lower()}__{brand_suffix}"


def _make_pkce() -> tuple[str, str]:
    """Return a (verifier, challenge) pair for PKCE-S256.

    verifier: 43-128 byte URL-safe random string
    challenge: BASE64URL(SHA256(verifier)) with padding stripped
    """
    verifier = secrets.token_urlsafe(64)[:96]
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
    return verifier, challenge


class DataActPortalAuth:
    """In-house auth client for the EU Data Act consumer portal.

    Returns a ``TokenSet`` with ``strategy="data_act_portal"`` on
    success. The access_token returned is the OIDC access_token from
    identity.vwgroup.io — usable for portal API calls but not for the
    BFF or any direct vehicle endpoints. The portal session cookies
    set during the redirect chain are persisted on the supplied
    ``ClientSession`` and the caller should reuse that session for
    subsequent portal data fetches.

    This class does NOT cache credentials — the brand client provides
    them on every call. That makes it safe to drop in/out of the
    strategy chain without state leaks.
    """

    def __init__(
        self,
        session: "ClientSession",
        brand_name: str,
        *,
        country: str = _DEFAULT_COUNTRY,
        language: str = _DEFAULT_LANGUAGE,
    ) -> None:
        self._session = session
        self._brand_name = brand_name
        self._country = country
        self._language = language

    async def login(self, email: str, password: str) -> TokenSet:
        """Run the portal OAuth login and return a portal-strategy TokenSet.

        Raises:
            AuthenticationError: on any step failure. The base.py
                strategy resolver catches this and surfaces a repair
                issue when the entire chain is exhausted.
        """
        from aiohttp import ClientTimeout  # noqa: PLC0415

        state = _build_state(self._brand_name, self._country, self._language)
        # v2.10.2 — Portal uses plain authorization-code flow (not
        # hybrid). Add PKCE-S256 defensively even though we don't yet
        # know the IDP enforces it; modern OIDC public-clients usually
        # require it and the verifier is cheap to carry.
        pkce_verifier, pkce_challenge = _make_pkce()

        # Step 1 — prime the AEM load-balancer cookies. The portal
        # router rejects /services/callbacklogin requests that lack a
        # valid AEM session cookie set during the landing-page hit.
        try:
            async with self._session.get(
                f"{_PORTAL_BASE}/",
                timeout=ClientTimeout(total=_PORTAL_REQUEST_TIMEOUT_S),
                allow_redirects=True,
            ) as resp:
                if resp.status >= 500:
                    raise AuthenticationError(
                        f"Data Act portal landing returned HTTP {resp.status}"
                    )
        except Exception as exc:  # noqa: BLE001
            raise AuthenticationError(
                f"Data Act portal: could not reach landing page ({exc})"
            ) from exc

        # Step 2 — OIDC authorize against identity.vwgroup.io with the
        # portal's OAuth client. Auth0 returns a 302 to the brand-id
        # signin form; we follow the redirect chain and parse the
        # login HTML.
        # v2.10.2 — verified against live portal trace 2026-06-03.
        # The portal client uses plain authorization-code flow with
        # prompt=login. Hybrid (code id_token token) was rejected by
        # the IDP for this specific client_id and caused the
        # "unexpected landing URL" symptom users reported on #388/#393.
        authorize_params = {
            "client_id": _PORTAL_OIDC_CLIENT_ID,
            "redirect_uri": _PORTAL_OIDC_REDIRECT_URI,
            "response_type": "code",
            "scope": _PORTAL_OIDC_SCOPE,
            "state": state,
            "prompt": "login",
            "code_challenge": pkce_challenge,
            "code_challenge_method": "S256",
        }
        try:
            async with self._session.get(
                _IDP_AUTHORIZE_URL,
                params=authorize_params,
                timeout=ClientTimeout(total=_PORTAL_REQUEST_TIMEOUT_S),
                allow_redirects=True,
            ) as resp:
                landing_url = str(resp.url)
                landing_html = await resp.text(errors="replace")
                if resp.status != 200:
                    raise AuthenticationError(
                        f"Data Act portal: IDP authorize HTTP {resp.status}"
                    )
        except AuthenticationError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise AuthenticationError(
                f"Data Act portal: IDP authorize failed ({exc})"
            ) from exc

        if "signin-service" not in landing_url and "u/login" not in landing_url:
            raise AuthenticationError(
                f"Data Act portal: unexpected landing URL "
                f"{landing_url[:120]} — IDP may have rejected client_id"
            )

        # Step 3 — POST credentials. The portal-bound flow happens to
        # land on the Brand ID classic signin-service path; the
        # existing IDK reverse-engineering applies to extracting the
        # form fields. We do a minimal parse here rather than reusing
        # IDKAuth so this module stays standalone and easy to disable.
        #
        # v2.8.0rc2 (#378 jwaeles) — the legacy HTMLParser-only path
        # missed hmac/_csrf when the IDP migrated those fields out of
        # plain ``<input type="hidden">`` markup into a JSON block
        # rendered by the SPA. Mirrors the multi-fallback strategy
        # already in idk.py:_parse_csrf_robust so a future markup
        # migration on either side does not need two patches.
        import re  # noqa: PLC0415
        from html.parser import HTMLParser  # noqa: PLC0415

        class _IdentifierFormParser(HTMLParser):
            def __init__(self) -> None:
                super().__init__()
                self.fields: dict[str, str] = {}
                self.form_action: str = ""

            def handle_starttag(
                self,
                tag: str,
                attrs: list[tuple[str, str | None]],
            ) -> None:
                attr = dict(attrs)
                if tag == "input" and attr.get("type") == "hidden":
                    name = attr.get("name") or ""
                    if name:
                        self.fields[name] = attr.get("value") or ""
                elif tag == "form" and not self.form_action:
                    self.form_action = attr.get("action") or ""

        parser = _IdentifierFormParser()
        parser.feed(landing_html)

        # Fallback 1 — regex over all hidden inputs (HTMLParser misses
        # inputs that are JS-rendered after page load but still ship
        # in the initial HTML inside <noscript> or template blocks).
        for tag_match in re.finditer(r"<input[^>]+>", landing_html, re.IGNORECASE):
            tag_text = tag_match.group(0)
            if 'type="hidden"' not in tag_text.lower() and "type='hidden'" not in tag_text.lower():
                continue
            name_match = re.search(r'name=["\']([^"\']+)["\']', tag_text)
            value_match = re.search(r'value=["\']([^"\']*)["\']', tag_text)
            if name_match:
                parser.fields.setdefault(
                    name_match.group(1),
                    value_match.group(1) if value_match else "",
                )

        # Fallback 2 — form action via regex (handles forms whose
        # ``action`` lives on a <form> attribute that HTMLParser walked
        # past without capturing).
        if not parser.form_action:
            form_match = re.search(
                r'action=["\']([^"\']+/login/[^"\']+)["\']', landing_html,
            )
            if form_match:
                parser.form_action = form_match.group(1)

        # Fallback 3 — CSRF + hmac in JSON / script blocks (the modern
        # IDK SPA shape that broke the original parser). Patterns
        # observed on the live IDP: ``{"_csrf":"...","hmac":"hex..."}``
        # and ``window.__STORE__ = {...,"csrf":"...",...}``.
        if not parser.fields.get("_csrf"):
            for pattern in (
                r'"_csrf"\s*:\s*"([^"]{8,})"',
                r'"csrf"\s*:\s*"([^"]{8,})"',
                r'"csrfToken"\s*:\s*"([^"]{8,})"',
            ):
                csrf_match = re.search(pattern, landing_html)
                if csrf_match:
                    parser.fields["_csrf"] = csrf_match.group(1)
                    break
        if not parser.fields.get("hmac"):
            hmac_match = re.search(
                r'"hmac"\s*:\s*"([0-9a-fA-F]{20,})"', landing_html,
            )
            if hmac_match:
                parser.fields["hmac"] = hmac_match.group(1)

        if not parser.form_action or "hmac" not in parser.fields:
            raise AuthenticationError(
                "Data Act portal: signin form missing expected fields "
                "(hmac/_csrf) — IDP markup may have changed"
            )

        identifier_url = (
            parser.form_action
            if parser.form_action.startswith("http")
            else f"https://identity.vwgroup.io{parser.form_action}"
        )

        try:
            async with self._session.post(
                identifier_url,
                data={
                    **parser.fields,
                    "email": email,
                },
                timeout=ClientTimeout(total=_PORTAL_REQUEST_TIMEOUT_S),
                allow_redirects=True,
            ) as resp:
                password_html = await resp.text(errors="replace")
                if resp.status != 200:
                    raise AuthenticationError(
                        f"Data Act portal: identifier POST HTTP {resp.status}"
                    )
        except AuthenticationError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise AuthenticationError(
                f"Data Act portal: identifier POST failed ({exc})"
            ) from exc

        pw_parser = _IdentifierFormParser()
        pw_parser.feed(password_html)
        if not pw_parser.form_action:
            html_lower = password_html.lower()

            # v2.10.0 (#388 BalooDK + swebachus) — distinguish SPA-rendered
            # password page from a real consent wall. The pre-v2.10.0 logic
            # treated the plain string "consent" as proof of a consent wall,
            # but VW migrated the password page to SPA-rendered (~2026-05-31)
            # where the bundle includes `consent.js` as a generic JS asset
            # that loads on every IDP page. The result was every SPA login
            # falsely reporting "EU Data Act consent required" even when the
            # user had already granted it. Check for the SPA marker first.
            is_spa_password_page = (
                "log in" in html_lower
                and (
                    "enter password" in html_lower
                    or "enter your password" in html_lower
                    or "loginauthenticate" in html_lower
                )
                and "<form" not in html_lower
            )
            if is_spa_password_page:
                # v2.10.6 (#388 xeonixo + Arno-MA-73) — v2.10.3 SPA POST
                # to the parsed email form's action URL returned HTTP 405
                # for VW EU users. Auth0 Universal Login routes the SPA
                # password submission through the SAME /u/login?state=<x>
                # URL as the identifier step; differentiation happens via
                # the body's `action` field. Mirror idk.py's SPA fallback
                # exactly: form-encoded first, JSON content-type fallback
                # on 4xx, follow the resulting redirect chain.
                from urllib.parse import urlparse as _urlparse  # noqa: PLC0415

                # v2.10.7 (Arno-MA-73 trace) - state extraction order
                # mirrors idk.py: HTML hidden input first (most reliable
                # on SPA pages where aiohttp's redirect-following strips
                # the state from the final response URL), then the URL
                # query string of the password-page / landing-page as
                # fallback. Auth0 SPA always embeds the state as
                # ``<input type="hidden" name="state" value="...">`` in
                # the page HTML even when the SPA itself owns rendering.
                # v2.10.9 (#388 Arno) - forensic logging + attribute-order-
                # agnostic state extraction. Walks every hidden input via
                # the two-step name+value capture from idk.py's
                # _parse_csrf_robust so attribute order in the markup
                # never matters.
                _LOGGER.debug(
                    "Data Act portal SPA: entered SPA branch - "
                    "landing_url=%s identifier_url=%s "
                    "password_html_len=%d landing_html_len=%d",
                    landing_url[:120], identifier_url[:120],
                    len(password_html or ""), len(landing_html or ""),
                )
                state_from_url = ""
                state_source = ""

                def _extract_state_from_html(src_html: str) -> str:
                    """Walk every <input ...> tag, extract name+value as
                    two independent regex matches so attribute order in
                    the HTML does not matter. Mirrors idk.py:
                    _parse_csrf_robust line 1860 pattern.
                    """
                    for tag in re.finditer(r"<input[^>]+>", src_html, re.IGNORECASE):
                        t = tag.group(0)
                        tlow = t.lower()
                        if 'type="hidden"' not in tlow and "type='hidden'" not in tlow:
                            continue
                        nm = re.search(r'name=["\']([^"\']+)["\']', t)
                        vm = re.search(r'value=["\']([^"\']*)["\']', t)
                        if nm and nm.group(1) == "state" and vm and vm.group(1):
                            return vm.group(1)
                    return ""

                for label, src_html in (
                    ("password_html", password_html),
                    ("landing_html", landing_html),
                ):
                    if not src_html:
                        continue
                    # 1. Two-step hidden-input walk (attribute-order-agnostic).
                    cand = _extract_state_from_html(src_html)
                    if cand:
                        state_from_url = cand
                        state_source = f"{label}/hidden-input"
                        break
                    # 2. JS embed: "state":"..." (modern Auth0 SPA bundles
                    #    serialize the OAuth state into a window.__STORE__
                    #    object before the React tree hydrates).
                    m = re.search(
                        r'"state"\s*:\s*"([A-Za-z0-9_\-\.]{8,})"', src_html
                    )
                    if m:
                        state_from_url = m.group(1)
                        state_source = f"{label}/json-embed"
                        break
                    # 3. data-state attribute on any element (some Auth0
                    #    builds put it on <body data-state="..."> for
                    #    the bootstrap script to read).
                    m = re.search(
                        r'data-state=["\']([A-Za-z0-9_\-\.]{8,})["\']',
                        src_html,
                    )
                    if m:
                        state_from_url = m.group(1)
                        state_source = f"{label}/data-attr"
                        break
                    # v2.10.11 (#388 swebachus pure-SPA-shell trace) -
                    # 4. Auth0 native state signature. Tokens always
                    # start with the msgpack 2-key map marker ``hKFo``
                    # (base64 of 0x84a1 - 4-element map, first key 1
                    # byte string). Length is typically 80+ chars.
                    # Catches the token even when it is embedded in
                    # minified JS as a bare string literal without any
                    # surrounding "state:" marker.
                    m = re.search(
                        r'\b(hKFo[A-Za-z0-9_\-\.]{40,})\b', src_html
                    )
                    if m:
                        state_from_url = m.group(1)
                        state_source = f"{label}/auth0-native"
                        break
                    # 5. Escaped JSON inside HTML attribute / script
                    # content: the SPA shell often inlines its initial
                    # state as ``\"state\":\"...\"`` when the JSON is
                    # double-encoded.
                    m = re.search(
                        r'\\"state\\"\s*:\s*\\"([A-Za-z0-9_\-\.]{16,})\\"',
                        src_html,
                    )
                    if m:
                        state_from_url = m.group(1)
                        state_source = f"{label}/escaped-json"
                        break
                    # 6. URL-encoded state inside the HTML body (login
                    # bundles sometimes inline the entire callback URL
                    # as ``window.location = "...state=X..."``).
                    m = re.search(
                        r'[?&]state=([A-Za-z0-9_\-\.%]{16,})', src_html
                    )
                    if m:
                        state_from_url = m.group(1)
                        # URL-decode if needed.
                        from urllib.parse import unquote as _unq  # noqa: PLC0415
                        state_from_url = _unq(state_from_url)
                        state_source = f"{label}/url-embedded"
                        break
                    _LOGGER.debug(
                        "Data Act portal SPA: no state in %s "
                        "(first 300 chars: %s)",
                        label, src_html[:300].replace("\n", " "),
                    )
                if not state_from_url:
                    # 4. URL query strings as last resort.
                    for label, src in (
                        ("identifier_url", identifier_url),
                        ("landing_url", landing_url),
                    ):
                        qs = parse_qs(_urlparse(src).query)
                        if qs.get("state"):
                            state_from_url = qs["state"][0]
                            state_source = f"{label}/url-query"
                            break
                if not state_from_url:
                    # v2.10.11 (#388 swebachus) - expanded forensic dump
                    # covering BOTH HTMLs and the raw URL strings, plus
                    # the location around any "state" substring so the
                    # next trace surfaces the exact context the token
                    # lives in (or proves it is purely JS-rendered post
                    # bundle init, in which case we need a different
                    # entry point altogether).
                    def _state_context(src: str) -> str:
                        idx = src.lower().find("state")
                        if idx < 0:
                            return "(no 'state' substring)"
                        start = max(0, idx - 30)
                        end = min(len(src), idx + 80)
                        return src[start:end].replace("\n", " ")

                    _LOGGER.warning(
                        "Data Act portal SPA: no state token. "
                        "landing_url=%s identifier_url=%s",
                        landing_url[:200], identifier_url[:200],
                    )
                    title_m = re.search(
                        r"<title>([^<]+)</title>",
                        password_html or "", re.IGNORECASE,
                    )
                    _LOGGER.warning(
                        "Data Act portal SPA: password_html title=%s "
                        "len=%d, contains '<input'=%s, contains 'state'=%s, "
                        "contains '__STORE__'=%s, state-context=%r",
                        (title_m.group(1) if title_m else "(none)"),
                        len(password_html or ""),
                        "<input" in (password_html or "").lower(),
                        "state" in (password_html or "").lower(),
                        "__STORE__" in (password_html or ""),
                        _state_context(password_html or ""),
                    )
                    title_l = re.search(
                        r"<title>([^<]+)</title>",
                        landing_html or "", re.IGNORECASE,
                    )
                    _LOGGER.warning(
                        "Data Act portal SPA: landing_html title=%s "
                        "len=%d, contains '<input'=%s, contains 'state'=%s, "
                        "contains '__STORE__'=%s, state-context=%r",
                        (title_l.group(1) if title_l else "(none)"),
                        len(landing_html or ""),
                        "<input" in (landing_html or "").lower(),
                        "state" in (landing_html or "").lower(),
                        "__STORE__" in (landing_html or ""),
                        _state_context(landing_html or ""),
                    )
                    raise AuthenticationError(
                        "Data Act portal: SPA password page reached but "
                        "no Auth0 state token found (checked hidden "
                        "input via two-step walk, JS JSON embed, data-"
                        "state attribute, password-page URL and "
                        "landing URL). IDP markup may have changed. "
                        "Enable DEBUG logging for "
                        "'custom_components.vag_connect.cariad.auth."
                        "_data_act_portal' and re-share the log."
                    )
                _LOGGER.debug(
                    "Data Act portal SPA: state token found via %s "
                    "(first 12 chars: %s...)",
                    state_source, state_from_url[:12],
                )
                from urllib.parse import quote as _quote  # noqa: PLC0415
                spa_post_url = (
                    f"https://identity.vwgroup.io/u/login?state="
                    f"{_quote(state_from_url, safe='')}"
                )
                spa_form = {
                    "username": email,
                    "password": password,
                    "action": "default",
                    "state": state_from_url,
                }
                spa_headers_form = {
                    "Accept": (
                        "text/html,application/xhtml+xml,"
                        "application/xml;q=0.9,*/*;q=0.8"
                    ),
                    "Content-Type": "application/x-www-form-urlencoded",
                }
                spa_headers_json = {
                    "Accept": "application/json, text/html",
                    "Content-Type": "application/json",
                }
                callback_url = ""
                spa_attempt_status = 0
                # Try form-encoded first (legacy variant that idk.py
                # found still works for some VW Auth0 deployments).
                try:
                    async with self._session.post(
                        spa_post_url,
                        data=spa_form,
                        timeout=ClientTimeout(
                            total=_PORTAL_REQUEST_TIMEOUT_S
                        ),
                        allow_redirects=True,
                        headers=spa_headers_form,
                    ) as resp:
                        spa_attempt_status = resp.status
                        if resp.status in (200, 302, 303):
                            callback_url = str(resp.url)
                except Exception as exc:  # noqa: BLE001
                    _LOGGER.debug(
                        "Data Act portal SPA POST (form) failed: %s", exc
                    )
                # JSON fallback for SPA-only Auth0 deployments
                # (matches the idk.py order). Triggered when the form
                # attempt produced 4xx OR landed back on the identity
                # host instead of the portal callback.
                needs_json = (
                    not callback_url
                    or "drivesomethinggreater.com" not in callback_url
                )
                if needs_json:
                    try:
                        async with self._session.post(
                            spa_post_url,
                            json=spa_form,
                            timeout=ClientTimeout(
                                total=_PORTAL_REQUEST_TIMEOUT_S
                            ),
                            allow_redirects=True,
                            headers=spa_headers_json,
                        ) as resp:
                            spa_attempt_status = resp.status
                            if resp.status in (200, 302, 303):
                                callback_url = str(resp.url)
                    except Exception as exc:  # noqa: BLE001
                        _LOGGER.debug(
                            "Data Act portal SPA POST (json) failed: %s",
                            exc,
                        )
                if not callback_url or (
                    "drivesomethinggreater.com" not in callback_url
                ):
                    raise AuthenticationError(
                        "Data Act portal: SPA password POST did not "
                        "complete (last status="
                        f"{spa_attempt_status}). Both form-encoded and "
                        "JSON variants were tried; the portal IDP may "
                        "need an SPA-computed parameter (CAPTCHA, "
                        "bot-detection token) we cannot replicate."
                    )
                return await self._complete_after_callback(
                    callback_url=callback_url,
                    pkce_verifier=pkce_verifier,
                )

            # v2.7.3 — when the password form is missing, the most common
            # real-world cause (as reported by VW EU users on issue #372)
            # is that VW interjected the EU Data Act consent screen
            # between the identifier step and the password step. Now scanned
            # for SPECIFIC consent signals rather than the bare word
            # "consent" which matched the SPA bundle's consent.js asset.
            real_consent_signals = (
                "data act",
                "datenverarbeitung",
                "einwilligung",
                "zustimmung",
                "shape the future",
                "/u/consent",
                "/consent/marketing",
            )
            if any(sig in html_lower for sig in real_consent_signals):
                raise AuthenticationError(
                    "Data Act portal: EU Data Act consent required. "
                    "Sign in once on myvolkswagen.<your-country-tld> "
                    "in a browser, accept the data-processing consent "
                    "banner, then retry the integration setup."
                )
            raise AuthenticationError(
                "Data Act portal: password form missing. Most common "
                "cause: VW asked you to grant EU Data Act consent on "
                "the brand website and the integration cannot bypass "
                "that step. Sign in on myvolkswagen.* and accept the "
                "consent banner, then retry. Other possible cause: "
                "the email address was rejected at the identifier step."
            )
        password_action_url = (
            pw_parser.form_action
            if pw_parser.form_action.startswith("http")
            else f"https://identity.vwgroup.io{pw_parser.form_action}"
        )

        try:
            async with self._session.post(
                password_action_url,
                data={
                    **pw_parser.fields,
                    "email": email,
                    "password": password,
                },
                timeout=ClientTimeout(total=_PORTAL_REQUEST_TIMEOUT_S),
                allow_redirects=True,
            ) as resp:
                callback_url = str(resp.url)
                if resp.status != 200:
                    raise AuthenticationError(
                        f"Data Act portal: password POST HTTP {resp.status}"
                    )
        except AuthenticationError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise AuthenticationError(
                f"Data Act portal: password POST failed ({exc})"
            ) from exc

        # Step 4 + 5 — callback parsing + token exchange. Factored into
        # a helper so the v2.10.3 SPA-password path can short-circuit
        # to the same completion logic without duplicating code.
        return await self._complete_after_callback(
            callback_url=callback_url,
            pkce_verifier=pkce_verifier,
        )

    async def _complete_after_callback(
        self,
        *,
        callback_url: str,
        pkce_verifier: str,
    ) -> TokenSet:
        """Validate callback URL, extract code, exchange for tokens.

        Shared between the static-form password-POST path and the
        v2.10.3 SPA-password-POST path. Both land on the same
        ``{portal}/login?code=...&state=...`` callback shape so the
        downstream work is identical.

        Raises:
            AuthenticationError on any validation or HTTP failure.
        """
        from aiohttp import ClientTimeout  # noqa: PLC0415

        parsed = urlparse(callback_url)
        host_ok = parsed.netloc.endswith("drivesomethinggreater.com")
        if (
            not host_ok
            or "signin-service" in callback_url
            or "/error" in callback_url
        ):
            raise AuthenticationError(
                f"Data Act portal: login did not land on portal host "
                f"(final URL: {callback_url[:120]})"
            )

        all_params = {
            **parse_qs(parsed.query),
            **parse_qs(parsed.fragment),
        }
        auth_code = (all_params.get("code") or [""])[0]
        if not auth_code:
            # Belt-and-braces: some IDP variants still deliver in the
            # fragment with hybrid; keep the legacy path as a fallback
            # so we don't regress accounts that happened to work before.
            legacy_access = (all_params.get("access_token") or [""])[0]
            legacy_id = (all_params.get("id_token") or [""])[0]
            if legacy_access and legacy_id:
                _LOGGER.warning(
                    "Data Act portal: callback delivered tokens in the "
                    "fragment (legacy hybrid path) instead of a code. "
                    "Using them directly. IDP behaviour may have changed."
                )
                return TokenSet(
                    access_token=legacy_access,
                    refresh_token="",
                    id_token=legacy_id,
                    expires_at=time.time() + 3300,
                    strategy="data_act_portal",
                )
            raise AuthenticationError(
                "Data Act portal: callback URL missing the authorization "
                "code — IDP may have changed the redirect parameters"
            )

        token_body = {
            "grant_type": "authorization_code",
            "code": auth_code,
            "redirect_uri": _PORTAL_OIDC_REDIRECT_URI,
            "client_id": _PORTAL_OIDC_CLIENT_ID,
            "code_verifier": pkce_verifier,
        }
        try:
            async with self._session.post(
                _IDP_TOKEN_URL,
                data=token_body,
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Accept": "application/json",
                },
                timeout=ClientTimeout(total=_PORTAL_REQUEST_TIMEOUT_S),
                allow_redirects=False,
            ) as resp:
                token_status = resp.status
                token_json: dict[str, str] = {}
                try:
                    token_json = await resp.json(content_type=None)
                except Exception:  # noqa: BLE001
                    token_json = {}
                if token_status != 200:
                    err = token_json.get("error", "")
                    err_desc = token_json.get("error_description", "")
                    raise AuthenticationError(
                        f"Data Act portal: token exchange HTTP "
                        f"{token_status} (error={err!r} "
                        f"desc={err_desc[:120]!r})"
                    )
        except AuthenticationError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise AuthenticationError(
                f"Data Act portal: token exchange failed ({exc})"
            ) from exc

        access_token = token_json.get("access_token", "")
        id_token = token_json.get("id_token", "")
        refresh_token = token_json.get("refresh_token", "")
        expires_in = int(token_json.get("expires_in", 3600))
        if not access_token or not id_token:
            raise AuthenticationError(
                "Data Act portal: token endpoint returned an empty "
                "access_token or id_token"
            )

        _LOGGER.info(
            "Data Act portal: login succeeded for brand %s (read-only "
            "mode). Live BFF strategies are exhausted; integration is "
            "operating in 15-minute portal cadence.",
            self._brand_name,
        )
        return TokenSet(
            access_token=access_token,
            refresh_token=refresh_token,
            id_token=id_token,
            # Subtract 5min safety margin so we re-auth before silent 401s.
            expires_at=time.time() + max(expires_in - 300, 60),
            strategy="data_act_portal",
        )
