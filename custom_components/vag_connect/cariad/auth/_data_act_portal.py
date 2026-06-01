# Copyright 2026 Prash Balan (@its-me-prash) — Apache License 2.0
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

    Format: ``{country}__{language}__{brand_suffix}`` where the
    brand_suffix matches the portal's internal brand-routing enum.
    Falls back to VOLKSWAGEN_PASSENGER_CARS for unknown brand names
    so the login at least lands somewhere instead of erroring out.
    """
    brand_suffix = _BRAND_STATE_FRAGMENTS.get(
        brand_name.lower(), _BRAND_STATE_FRAGMENTS["volkswagen"],
    )
    return f"{country.lower()}__{language.lower()}__{brand_suffix}"


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

        nonce = secrets.token_urlsafe(16)
        state = _build_state(self._brand_name, self._country, self._language)

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
        authorize_params = {
            "client_id": _PORTAL_OIDC_CLIENT_ID,
            "redirect_uri": _PORTAL_OIDC_REDIRECT_URI,
            "response_type": "code id_token token",
            "scope": _PORTAL_OIDC_SCOPE,
            "state": state,
            "nonce": nonce,
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
            # v2.7.3 — when the password form is missing, the most common
            # real-world cause (as reported by VW EU users on issue #372)
            # is that VW interjected the EU Data Act consent screen
            # between the identifier step and the password step. The
            # user has to grant the "your vehicle data can help shape
            # the future" consent on myvolkswagen.* once before the
            # password page becomes reachable again. Detect this case
            # via a light HTML signature scan and raise with a clearer
            # message so config_flow can route to the data_act_consent
            # error key instead of the generic invalid_credentials.
            html_lower = password_html.lower()
            consent_signals = (
                "data act",
                "datenverarbeitung",
                "consent",
                "einwilligung",
                "zustimmung",
                "shape the future",
            )
            if any(sig in html_lower for sig in consent_signals):
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

        # Step 4 — verify we landed on the portal host and not on an
        # error page. Extract the access_token + id_token from the
        # callback URL fragment (hybrid flow delivery), as Auth0 does
        # for the portal client.
        parsed = urlparse(callback_url)
        host_ok = parsed.netloc.endswith("drivesomethinggreater.com")
        if not host_ok or "signin-service" in callback_url or "/error" in callback_url:
            raise AuthenticationError(
                f"Data Act portal: login did not land on portal host "
                f"(final URL: {callback_url[:120]})"
            )

        all_params = {**parse_qs(parsed.query), **parse_qs(parsed.fragment)}
        access_token = (all_params.get("access_token") or [""])[0]
        id_token = (all_params.get("id_token") or [""])[0]
        if not access_token or not id_token:
            raise AuthenticationError(
                "Data Act portal: callback URL missing access_token or "
                "id_token — IDP may have stripped hybrid response_type "
                "for the portal client"
            )

        _LOGGER.info(
            "Data Act portal: login succeeded for brand %s (read-only "
            "mode). Live BFF strategies are exhausted; integration is "
            "operating in 15-minute portal cadence.",
            self._brand_name,
        )
        return TokenSet(
            access_token=access_token,
            refresh_token="",
            id_token=id_token,
            # Portal access_tokens are typically valid ~1 h; mark
            # explicitly so the coordinator schedules re-login before
            # silent 401s.
            expires_at=time.time() + 3300,
            strategy="data_act_portal",
        )
