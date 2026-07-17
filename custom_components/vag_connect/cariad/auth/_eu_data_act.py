"""VW EU Data Act portal connector — cookie-session login + ZIP data delivery.

v2.12.0 (#388 swebachus / #393 SniperWCW) — the only third-party auth path
left open for VW passenger cars. Live-tested 2026-06-07: every token-based
WeConnect route is closed (hybrid response_type → Auth0 403, code-flow token
exchange needs a client_secret we don't have, device-grant → 403
unauthorized_client). The EU Data Act portal is the one route VW must keep
open under Regulation (EU) 2023/2854 Arts. 4-6.

Architecture (fundamentally different from our token-based BFF clients):
  1. OIDC authorization-code login against identity.vwgroup.io, but the
     portal's OWN backend (``/services/callbacklogin``) consumes the code
     and sets **session cookies**. We never exchange the code ourselves —
     the portal is a confidential Auth0 client; we can't.
  2. Authenticated reads go to ``{portal}/proxy_api/...`` using those
     cookies, returning ZIP archives with a JSON dataset inside.
  3. The dataset is keyed by EU Data Act field names; we map a curated
     subset onto our ``VehicleData`` model.

Trade-offs (documented for users): read-only (no remote commands),
~15-minute data cadence, and the user must enable a one-time "continuous
data request" on the portal first.

Login mechanics + endpoint paths adapted from MIT-licensed community
projects (the CarConnectivity / Home Assistant VW EU Data Act connectors)
that independently reverse-engineered the portal's public web flow.
Attribution in LEGAL.md.
"""
from __future__ import annotations

import asyncio
import io
import json
import logging
import re
import uuid
import zipfile
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urljoin, urlparse

from aiohttp import ClientConnectionError, ClientSession, ClientTimeout

from ..exceptions import (
    AuthenticationError,
    EmailTwoFactorRequiredError,
    MarketingConsentError,
    PortalInteractionRequiredError,
    TermsAndConditionsError,
    TwoFactorRequiredError,
    UpstreamUnavailableError,
)
from ..models import VehicleData

_LOGGER = logging.getLogger(__name__)

_PORTAL_BASE = "https://eu-data-act.drivesomethinggreater.com"
_IDENTITY_BASE = "https://identity.vwgroup.io"
_AUTHORIZE_URL = f"{_IDENTITY_BASE}/oidc/v1/authorize"
_PORTAL_REDIRECT_URI = f"{_PORTAL_BASE}/login"

# v2.12.0 — per-brand EU Data Act portal OAuth config. The portal serves
# the whole VW Group, but the OAuth client + the brand suffix in the
# ``state`` (``{country}__{language}__{BRAND}``) select which brand's
# vehicles the account sees. The portal connector is wired as a fallback
# in every brand's auth chain (see api/base.py), so it must pick the
# right config per brand — otherwise a CUPRA falling through to the
# portal would authenticate with VW's client + state.
#
# client_id sources / verification (2026-06-07):
#   - VW: 9b58543e — community-proven, end-to-end on #388.
#   - CUPRA/SEAT: f85e5b69 — from the community EUDA constants, scope
#     "openid profile cars". Both client+state combos handshake-verified
#     (302 → signin).
# Brands not listed fall back to the VW entry with a brand-derived state
# suffix; account-level verification for those follows in a later release.
_EUDA_VW = {
    "client_id": "9b58543e-1c15-4193-91d5-8a14145bebb0@apps_vw-dilab_com",
    "scope": "openid cars profile",
    "state_brand": "VOLKSWAGEN_PASSENGER_CARS",
}
_EUDA_CUPRA_SEAT = {
    "client_id": "f85e5b69-e3b2-43aa-9c0d-1b7d0e0b576f@apps_vw-dilab_com",
    "scope": "openid profile cars",
}
_EUDA_BRANDS: dict[str, dict[str, str]] = {
    "volkswagen": _EUDA_VW,
    "cupra": {**_EUDA_CUPRA_SEAT, "state_brand": "CUPRA"},
    "seat": {**_EUDA_CUPRA_SEAT, "state_brand": "SEAT"},
    "skoda": {**_EUDA_VW, "state_brand": "SKODA"},
    "audi": {**_EUDA_VW, "state_brand": "AUDI"},
}

_VEHICLES_PATH = "/proxy_api/consent/me/vehicles"
_RELATION_PATH = "/proxy_api/vum/v2/users/me/relations/{vin}"
_METADATA_PATH = "/proxy_api/euda-apim/datarequest/vehicles/{vin}/metadata/partial"
# v2.18.0 (Phase C) — the one-time historical export's metadata endpoint. The
# read path is otherwise identical to the 15-min feed's; only the metadata path
# and the ``type`` header differ (all vs partial). Proven from a real trace.
_ALL_METADATA_PATH = "/proxy_api/euda-apim/datarequest/vehicles/{vin}/metadata/all"
_LIST_PATH = "/proxy_api/euda-apim/datadelivery/vehicles/{vin}/{identifier}/list"
_DOWNLOAD_PATH = (
    "/proxy_api/euda-apim/datadelivery/vehicles/{vin}/{identifier}/download"
)

_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36"
)
_NO_CONTENT_SUFFIX = "_no_content_found.zip"
_TIMEOUT_S = 60
# v2.12.4 (#428/#429/#430/#431) — statuses that mean "the portal is having a
# bad moment", not "your session is dead". During the VW-side all-brands
# outage (since late May 2026) the data endpoints 500 constantly; that's a
# transient server fault, not an auth failure, so we treat it as "no data
# this poll" (the data_act_no_data notice already explains the outage) instead
# of raising AuthenticationError and triggering pointless re-login churn + a
# stream of error reports. 401/403 still mean a genuinely expired session.
# v2.17.4 — 400/429 on the SOFT data-polling GETs (datadelivery list/download,
# metadata) are a provisioning-window / soft-throttle transient, NOT an auth
# failure. Without them a soft 400 fell through to raise AuthenticationError →
# a pointless re-login loop (the churn v2.12.4 fixed for 5xx). They return "no
# data this poll"; kept OUT of _RETRIABLE_STATUSES so we don't hammer the portal
# (one quiet skip, no backoff-retry). Hard (soft=False) calls still raise on 400.
_TRANSIENT_STATUSES = (400, 404, 410, 429, 500, 502, 503, 504)
# v2.13.1 — of those, only the genuinely transient server errors are worth
# retrying with backoff; 404/410 ("data request not provisioned yet") are a
# stable state and return "no data" immediately, so we don't add latency to
# the common not-set-up case.
_RETRIABLE_STATUSES = frozenset({500, 502, 503, 504})
_PORTAL_RETRY_DELAYS = (3.0, 6.0)  # backoff (s) before giving up on a soft call


# ── HTML / templateModel parsing (community-proven mechanics) ──────────────

class _FormParser(HTMLParser):
    """Extract the first <form> action and all hidden/input fields."""

    def __init__(self) -> None:
        super().__init__()
        self.action: str | None = None
        self.fields: dict[str, str] = {}
        self._in_form = False
        self._done = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if self._done:
            return
        a = dict(attrs)
        if tag == "form" and self.action is None:
            self.action = a.get("action")
            self._in_form = True
        elif tag == "input" and self._in_form:
            name = a.get("name")
            if name:
                self.fields[name] = a.get("value") or ""

    def handle_endtag(self, tag: str) -> None:
        if tag == "form" and self._in_form:
            self._in_form = False
            self._done = True


def _extract_template_model(html: str) -> dict[str, Any]:
    """Extract the VW identity ``templateModel`` JSON embedded in the page.

    The SPA-rendered signin/authenticate pages carry their form state
    (hmac, relayState, prefilled email, error) in a JS object rather than
    HTML inputs. Brace-matched extraction handles nested objects.
    """
    idx = html.find("templateModel")
    if idx == -1:
        return {}
    brace = html.find("{", idx)
    if brace == -1:
        return {}
    depth = 0
    for i in range(brace, len(html)):
        c = html[i]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                try:
                    parsed = json.loads(html[brace : i + 1])
                except ValueError:
                    return {}
                return parsed if isinstance(parsed, dict) else {}
    return {}


def _extract_csrf(html: str) -> str | None:
    """Pull the csrf_token out of the identity page's JS."""
    m = re.search(r"csrf_token\s*[:=]\s*['\"]([^'\"]+)['\"]", html)
    return m.group(1) if m else None


def _login_fields(html: str) -> tuple[dict[str, str], str | None]:
    """Collect the fields needed to POST a VW identity login step.

    Merges HTML hidden inputs with the JS templateModel/csrf so it works
    whether the page renders inputs server-side (email step) or via JS
    (password step). Returns (fields, form_action).
    """
    form = _FormParser()
    form.feed(html)
    fields: dict[str, str] = dict(form.fields)
    model = _extract_template_model(html)
    if model:
        for key in ("hmac", "relayState"):
            if model.get(key):
                fields[key] = model[key]
        email = (model.get("emailPasswordForm") or {}).get("email")
        if email:
            fields.setdefault("email", email)
    csrf = _extract_csrf(html)
    if csrf:
        fields.setdefault("_csrf", csrf)
    return fields, form.action


def _resolve_action(base_url: str, action: str | None) -> str:
    """Resolve a form ``action`` against *base_url*, guarding the
    doubled-``/login/login/`` trap.

    The signin-service login pages sometimes ship a RELATIVE action that
    already starts with ``login/`` (e.g. ``login/authenticate``). Joining
    that to a base whose path is ``.../login/identifier`` yields
    ``.../login/login/authenticate`` — the IDP rejects the duplicated
    segment with HTTP 400 (verified via swebachus's v2.11.4 source review
    on #388). When there's no action at all, fall back to the base URL
    with its query stripped (the page we already landed on is the right
    POST target). Finally, collapse any ``/login/login/`` the join may
    still produce — that segment pair is never legitimate in the
    signin-service path structure.
    """
    if action:
        resolved = urljoin(base_url, action)
    else:
        resolved = base_url.split("?", 1)[0]
    return resolved.replace("/login/login/", "/login/")


def _consent_form_fields(html: str) -> tuple[list[tuple[str, str]], str | None]:
    """Parse the consent grant <form> into ORDERED (name, value) pairs.

    Unlike ``_login_fields`` (dict-based — fine for credential steps), the
    consent form emits ``consentedScopes`` ONCE PER granted scope
    (``<input name=consentedScopes value=profile>``,
    ``<input name=consentedScopes value=cars>``). A dict would keep only the
    last and silently drop the mandatory ``profile`` scope → the grant
    endpoint rejects it. So we keep a list and PRESERVE repeats (RaimondB's
    root-cause for #527). Buttons (the Allow button has no name; Cancel is
    ``name='cancel' value='true'``) are excluded so the payload is the hidden
    inputs ONLY. Returns ``(pairs, form_action)`` where ``form_action`` is the
    raw form ``action`` (typically EMPTY on the consent page — meaning POST
    back to the current URL, query intact).
    """

    class _P(HTMLParser):
        def __init__(self) -> None:
            super().__init__()
            self.action: str | None = None
            self.pairs: list[tuple[str, str]] = []
            self._in = False
            self._done = False

        def handle_starttag(
            self, tag: str, attrs: list[tuple[str, str | None]]
        ) -> None:
            if self._done:
                return
            a = dict(attrs)
            if tag == "form" and self.action is None:
                self.action = a.get("action")
                self._in = True
            elif tag == "input" and self._in:
                name = a.get("name")
                if name:
                    self.pairs.append((name, a.get("value") or ""))

        def handle_endtag(self, tag: str) -> None:
            if tag == "form" and self._in:
                self._in = False
                self._done = True

    parser = _P()
    parser.feed(html)
    return parser.pairs, parser.action


def _login_error(html: str) -> str | None:
    """Return a human-readable login error from the page, if present."""
    model = _extract_template_model(html)
    err = model.get("error") or model.get("errorCode")
    if isinstance(err, dict):
        return err.get("text") or err.get("errorCode") or str(err)
    return str(err) if err else None


def _safe_url(url: str) -> str:
    """Return host+path of *url* with the query string STRIPPED.

    Query strings on the signin-service flow carry ``relayState`` / ``code``
    / login tokens — never log them. This yields only the part that is safe
    to log (host + path) so #527 reporters' real failure step can be pinned
    from a debug log without leaking secrets.
    """
    try:
        p = urlparse(url)
        return f"{p.netloc}{p.path}"
    except Exception:  # noqa: BLE001
        return "<unparseable-url>"


# v2.15.4 (#527) — interstitial markers. The portal login lands on the
# signin-service host (or re-renders the credential page) for MANY reasons
# besides bad credentials: T&C, marketing consent, 2FA/OTP, onboarding,
# region selection, soft rate-limit. The historic code classified ALL of
# these as "check email and password" purely from a URL substring. These
# markers (URL fragments + templateModel keys/page identifiers) let us raise
# the SAME typed exceptions the main auth chain (idk.py) already raises, so
# the coordinator/config_flow's existing branches fire and the user gets an
# actionable, non-credential message. Substrings mirror idk.py.
_TC_MARKERS = ("terms-and-conditions", "/u/terms", "termsandconditions")
_CONSENT_MARKERS = (
    "consent/marketing", "/u/consent", "marketing-consent", "marketingconsent",
)
_EMAIL_2FA_MARKERS = (
    "/u/email-challenge", "email-otp", "email-code", "send-email-code",
)
_2FA_MARKERS = ("/u/mfa", "two-factor", "2fa", "totp", "mfa-challenge")
_ONBOARDING_MARKERS = (
    "onboarding", "region-select", "select-region", "country-select",
    "/u/login/identifier-first",
)
_RATELIMIT_MARKERS = ("too-many", "rate-limit", "ratelimit", "throttl")

# v2.15.5 (#527 follow-on) — GENERIC OAuth/IDP consent page. Distinct from the
# MARKETING-consent interstitial (_CONSENT_MARKERS): this is the standard
# signin-service grant page the IDP shows AFTER credentials when the OAuth
# client needs an authorization grant the account has not yet given. Confirmed
# on v2.15.4 diagnostics (sarahlesage): the portal credential POST lands on
# ``identity.vwgroup.io/signin-service/v1/consent/users/{uid}/{client}`` with
# templateModel pageType='consent', status 200 — a generic consent grant, not a
# marketing opt-in. The user already entered creds + wants the integration
# authorized, so the official-app behaviour is to ACCEPT the grant. We mirror
# that (auto-accept in login()); the classifier markers below are the fallback
# for when auto-accept does not complete the login.
_GENERIC_CONSENT_MARKERS = ("/signin-service/v1/consent/", "/consent/users/")
_GENERIC_CONSENT_PAGETYPES = ("consent",)


def _is_generic_consent_page(
    landing_url: str, page_type: str, blob: str
) -> bool:
    """True if the landing is the generic IDP/OAuth consent grant page (#527).

    Matches on the signin-service consent URL family, the consent VIN-less
    ``/consent/users/`` path, OR a templateModel pageType of ``consent``.
    Deliberately does NOT match the MARKETING-consent interstitial (that is
    handled by _CONSENT_MARKERS → MarketingConsentError) — the generic grant
    page is the standard "authorize this client" page, not a marketing opt-in.
    """
    url_l = landing_url.lower()
    if any(m in url_l for m in _GENERIC_CONSENT_MARKERS):
        return True
    if page_type and page_type.lower() in _GENERIC_CONSENT_PAGETYPES:
        return True
    return any(m in blob for m in _GENERIC_CONSENT_MARKERS)


def classify_portal_login_failure(
    landing_url: str, landing_html: str
) -> tuple[AuthenticationError | None, dict[str, str]]:
    """Classify a non-completed portal login landing.

    Returns ``(exc, log_ctx)`` where:
      * ``exc`` is a TYPED ``AuthenticationError`` subclass to raise, or
        ``None`` when the landing is a genuine bad-credential re-render
        (caller raises the credential catch-all).
      * ``log_ctx`` is a secret-free dict (page-type / error / errorCode
        keys only — NEVER email/password/tokens/relayState/code) suitable
        for a DEBUG/WARNING log line.

    Order matters: machine-readable interstitial markers first (so a real
    "accept the T&C" page never surfaces as "wrong password"), then the
    templateModel error/errorCode, then the credential fallback.
    """
    haystack = f"{landing_url}\n{landing_html}".lower()
    model = _extract_template_model(landing_html) or {}
    err = model.get("error")
    err_code = model.get("errorCode")
    if isinstance(err, dict):
        err_code = err_code or err.get("errorCode")
        err = err.get("text") or err.get("errorCode")
    page_type = model.get("template") or model.get("templateName") or ""

    log_ctx: dict[str, str] = {}
    if err:
        log_ctx["error"] = str(err)[:120]
    if err_code:
        log_ctx["errorCode"] = str(err_code)[:120]
    if page_type:
        log_ctx["pageType"] = str(page_type)[:120]

    blob = f"{haystack} {str(err_code).lower()} {str(page_type).lower()}"

    # 1. Interstitials we recognise — reuse the main-chain exceptions.
    if any(m in blob for m in _TC_MARKERS):
        log_ctx.setdefault("classified", "terms_and_conditions")
        return TermsAndConditionsError(), log_ctx
    if any(m in blob for m in _CONSENT_MARKERS):
        log_ctx.setdefault("classified", "marketing_consent")
        return MarketingConsentError(), log_ctx
    # Email-OTP must be checked BEFORE the generic 2FA family (subclass).
    if any(m in blob for m in _EMAIL_2FA_MARKERS):
        log_ctx.setdefault("classified", "email_two_factor_required")
        return EmailTwoFactorRequiredError(), log_ctx
    if any(m in blob for m in _2FA_MARKERS):
        log_ctx.setdefault("classified", "two_factor_required")
        return TwoFactorRequiredError(), log_ctx
    if any(m in blob for m in _ONBOARDING_MARKERS):
        log_ctx.setdefault("classified", "portal_interaction_required")
        return PortalInteractionRequiredError("onboarding / region step"), log_ctx
    if any(m in blob for m in _RATELIMIT_MARKERS):
        log_ctx.setdefault("classified", "portal_interaction_required")
        return PortalInteractionRequiredError("temporary block / rate limit"), log_ctx

    # 1b. Generic OAuth/IDP consent grant page (#527). Checked AFTER the
    #     marketing-consent markers (so a marketing opt-in still maps to
    #     MarketingConsentError) but BEFORE the credential fallback so this
    #     non-credential page never surfaces as "check password". This is the
    #     classifier-side FALLBACK for when login()'s auto-accept could not
    #     complete the grant (e.g. the IDP changed the form shape). The user
    #     then gets the actionable "complete the consent in a browser" message.
    if _is_generic_consent_page(landing_url, str(page_type), blob):
        log_ctx.setdefault("classified", "portal_interaction_required")
        return (
            PortalInteractionRequiredError("consent / terms acceptance"),
            log_ctx,
        )

    # 2. A machine-readable error/errorCode that is NOT one of the known
    #    bad-credential codes → carry the real reason as a non-credential
    #    failure (we couldn't prove it's the password).
    cred_codes = {
        "login.error.password_invalid",
        "login.errors.password_invalid",
        "incorrect_credentials",
        "invalid_credentials",
        "log.in.error.wrong.credentials",
    }
    err_code_l = str(err_code or "").lower()
    if err_code and err_code_l not in cred_codes:
        log_ctx.setdefault("classified", "portal_interaction_required")
        return (
            PortalInteractionRequiredError(f"portal error {err_code}"),
            log_ctx,
        )

    # 3. Genuine bad-credential re-render (or no machine-readable reason at
    #    all): let the caller raise the credential catch-all.
    log_ctx.setdefault("classified", "invalid_credentials")
    return None, log_ctx


# ── Dataset parsing + curated field mapping ────────────────────────────────

# v2.13.0 (P1) — timestamp keys carried alongside a datapoint/report node.
_TS_KEYS = (
    "capturedAt", "carCapturedTimestamp", "timestamp", "recordedAt",
    "lastUpdated", "ts", "time", "datetime",
)


def _parse_ts(value: Any) -> float | None:
    """Best-effort timestamp → comparable float (epoch seconds). Never raises.

    Handles epoch seconds, epoch milliseconds (heuristic: > 1e12 → ms) and
    ISO-8601 strings. Unparseable → None (caller falls back to array order).
    """
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        f = float(value)
        return f / 1000.0 if f > 1e12 else f
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return None
        try:
            f = float(s)
            return f / 1000.0 if f > 1e12 else f
        except ValueError:
            pass
        try:
            from datetime import datetime  # noqa: PLC0415

            return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()
        except (ValueError, TypeError):
            return None
    return None


# v2.15.0a11 — data-quality hardening (EU Data Act read path).
# Sentinel markers the portal ships for "no reading": uint16 / int32 / uint32
# max. A raw 65535 in an SoC/range field is "unknown", not a real value —
# keeping it poisons HA long-term statistics irreversibly.
# v2.17.4 — plus INT32_MIN (-2147483648): a distinct signed "no reading" nonsense
# the maintenance/service COUNTDOWN ships. It MUST drop here, BEFORE the sign
# transform that negates a negative countdown — else -2147483648 negates into a
# spurious +2,147,483,648 km service_km/oil_service_km leak (TommiG1 #39).
_GLOBAL_SENTINELS: frozenset[float] = frozenset(
    {-2147483648.0, 65535.0, 2147483647.0, 4294967295.0}
)

# Field-specific sentinels — TABLE-DRIVEN (case-insensitive substring on the
# flattened field name) so the rule set stays extensible instead of hardcoded.
_FIELD_SENTINELS: tuple[tuple[str, frozenset[float]], ...] = (
    ("remaining_charging_time", frozenset({-1.0})),
    ("remainingchargingtime", frozenset({-1.0})),
    ("tyre_pressure_actual", frozenset({0.0, 1.0})),  # 0=unsupported 1=invalid
    ("tirepressure", frozenset({0.0, 1.0})),
    # v2.15.3 — pressure DELTA-vs-target family: 0=unsupported 1=invalid,
    # >1=valid int (mirrors the tyre_pressure_actual rule).
    ("tyre_pressure_differential", frozenset({0.0, 1.0})),
    # v2.15.4 (#538) — REQUIRED/target per-wheel pressure family: same dict
    # convention (0=unsupported 1=invalid, >1=valid int) as the actual family.
    ("tyre_pressure_required", frozenset({0.0, 1.0})),
)

# Monotonic fields must never regress: an out-of-order OLDER snapshot must not
# lower a higher reading — pick the larger numeric value, not just latest-ts.
_MONOTONIC_HINTS: tuple[str, ...] = (
    "odometer", "mileage", "kilometre", "kilometer", "total_distance",
)

# Field names whose VALUE is itself the dataset capture timestamp.
_CAPTURED_NAME_HINTS: tuple[str, ...] = (
    "car_captured", "carcaptured", "captured_timestamp", "capturedtimestamp",
    "captured_time", "capturedtime", "captured_utc",
)

# v2.17.4 — MEB/ID.x ships some data-points (notably the primary electric range,
# EU dict UUID 0ca40e18 "Value of the primary range") under a GENERIC
# ``dataFieldName`` ("value"/"unit"/…) that only the per-point ``key`` UUID
# disambiguates. Four dict entries share the name "value", so name-keying
# collapses them onto one last-wins field and the range is lost on ID.3/4/5/7.
# The flattener additionally keys such points by their ``key`` UUID so first()
# can resolve them by UUID.
_GENERIC_FIELD_NAMES: frozenset[str] = frozenset(
    {"value", "unit", "state", "timestamp", "is_set", "type"}
)
# v2.17.5 — ONLY alias the UUIDs we actually MAP. The 2.17.4 blanket alias
# emitted an ``eu_data_act.<uuid>`` key for EVERY generic-named point, which
# flooded the Vehicle Data Scout with dozens of unmapped timestamp/state UUID
# names per car ("46 new fields"). We now alias solely these known-mapped UUIDs;
# every other generic point keeps only its bare name + value (still Scout-visible,
# so discovery is unaffected) and no longer spams unmapped UUID rows.
_MAPPED_UUIDS: frozenset[str] = frozenset(
    {"0ca40e18-0564-3eda-bcc0-7aee9ef44f04"}  # primary range (electric on BEV / combustion on PHEV)
)


def _num(value: Any) -> float | None:
    """Coerce a leaf value to float for sentinel/monotonic checks, else None."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip().replace(",", "."))
        except (ValueError, AttributeError):
            return None
    return None


def _is_sentinel(name: str, value: Any) -> bool:
    """True if *value* is a "no reading" sentinel for field *name*."""
    n = _num(value)
    if n is None:
        return False
    if n in _GLOBAL_SENTINELS:
        return True
    low = name.lower()
    return any(needle in low and n in sents for needle, sents in _FIELD_SENTINELS)


def _is_monotonic(name: str) -> bool:
    low = name.lower()
    return any(h in low for h in _MONOTONIC_HINTS)


def _dataset_captured_ts(payload: Any) -> float | None:
    """Max capture timestamp across the dataset.

    A leaf whose NAME marks it a capture time and whose VALUE is the timestamp.
    Used as the default freshness floor for value-fields that carry no sibling
    timestamp, so even bare ``{soc: 80}`` fields rank by dataset freshness rather
    than collapsing to ``-inf`` (last-in-array).
    """
    best: float | None = None

    def consider(raw: Any) -> None:
        nonlocal best
        ts = _parse_ts(raw)
        if ts is not None and (best is None or ts > best):
            best = ts

    def scan(node: Any) -> None:
        if isinstance(node, dict):
            fname = node.get("dataFieldName") or node.get("name")
            if (
                isinstance(fname, str)
                and "value" in node
                and any(h in fname.lower() for h in _CAPTURED_NAME_HINTS)
            ):
                consider(node.get("value"))
            for k, val in node.items():
                if isinstance(k, str) and any(
                    h in k.lower() for h in _CAPTURED_NAME_HINTS
                ):
                    consider(val)
                if isinstance(val, (dict, list)):
                    scan(val)
        elif isinstance(node, list):
            for item in node:
                scan(item)

    scan(payload)
    return best


def _walk_fields(
    payload: Any,
    _ts_out: dict[str, float] | None = None,
    _syn_out: dict[str, set[str]] | None = None,
) -> dict[str, str]:
    """Flatten the EU Data Act dataset into ``{field_name: value}``.

    The portal ZIP contains a JSON dataset whose shape varies by firmware
    (flat eGolf vs structured MEB). We walk it defensively, collecting any
    node that carries a recognizable ``dataFieldName``/``name``+``value``
    pair, plus dotted-path fallbacks for nested ``{report: {field: v}}``
    shapes.

    v2.13.0 (P1) — LATEST-WINS. The portal ships an unordered event-log, so
    the same field can appear at several timestamps; the old first-wins
    ``setdefault`` picked an arbitrary (often oldest) value, which is why SoC /
    odometer jumped around for everyone on the portal. We keep, per field, the
    candidate with the freshest *genuine* per-point timestamp (read from a
    sibling ``_TS_KEYS`` key on the same node).

    b13 (#465 RaAdNe): VW returns several data points with the SAME logical
    name (e.g. four ``target_soc`` candidates, two ``soc`` values). We pick by
    genuine freshness, never by array order: a real per-point timestamp beats the
    inherited dataset floor, and the strictly-newer of two real timestamps wins.
    Fields nested inside an array (e.g. inside ``chargingProfiles[]``) no longer
    collapse onto the bare top-level key. Single-occurrence datasets are
    unaffected, so existing shape tests stay green.

    v2.15.4 (#529): snapshot COHERENCE. The ZIP is a flat, append-ordered
    multi-snapshot log; resolving each field independently let soc, odometer and
    last_seen surface from DIFFERENT snapshots — odometer in particular was
    lifted by a within-ZIP monotonic MAX from an arbitrary older snapshot while
    last_seen tracked the newest one, manufacturing a phantom "moved at night".
    Two changes make every field resolve to its latest available sample, so the
    surfaced values no longer contradict each other (the odometer is never from
    an older block than last_seen):
      1. Drop the odometer/mileage monotonic-MAX. Odometer now resolves to its
         latest-cct sample like every other field, so it tracks the same latest
         samples as soc/last_seen instead of a numeric max from an arbitrary
         older block. The "never goes backwards" guarantee (a11) is NOT lost —
         it is owned across polls by ``vehicle_cache.reconcile``
         (MONOTONIC_INCREASING_FIELDS), which rejects a regression vs the last
         PERSISTED value. That is the right layer: a within-ZIP max conflated
         genuinely-distinct snapshots; the persisted-value guard does not. (Note
         the a11 monotonic tests still pass — in each the newer timestamp legit-
         imately carries the higher reading, which latest-cct selects anyway.)
      2. On a tie with NO real per-point timestamp on either candidate, take the
         LAST write, not the first. The portal log is append-ordered, so a later
         duplicate is the newer sample. This flips the old first-seen tie-break
         that surfaced the stale earlier value (#529 S5/S6); it only affects the
         degenerate no-timestamp tie — real #465 payloads carry car_captured_time
         and resolve by freshness regardless, so #465 stays fixed.

    ``_ts_out`` (optional): if a dict is passed, it is filled with the RESOLVED
    real per-point capture ts of each surfaced field (only fields whose winning
    sample carried a genuine ts). #529 step 2 uses this so ``last_seen_at`` is
    never advanced past the snapshot the surfaced odometer actually came from.

    ``_syn_out`` (optional): if a dict is passed, it is filled with an EXPLICIT,
    bidirectional synonym map ``{spelling -> {the other spelling(s)}}`` recording,
    per PHYSICAL data-point node, the bare-leaf and container-qualified spellings
    we emit for the SAME datum (the v2.15.4 overreport fix below emits BOTH). This
    is the no-suppression-safe replacement for the old leaf+value heuristic in
    ``first()``: two synonyms ALWAYS originate from one node, so two distinct nodes
    that merely share a leaf name (e.g. ``battery_state_report.soc`` vs
    ``front_left_tyre.soc``) are NEVER synonyms and can never cross-collapse — even
    if their values happen to be equal.
    """
    # name -> (value_str, ts, ts_real); ts_real distinguishes a genuine
    # per-point timestamp from the inherited dataset-level floor (-inf=unknown).
    best: dict[str, tuple[str, float, bool]] = {}
    dataset_ts = _dataset_captured_ts(payload)  # a11: dataset-level freshness floor

    def add(name: Any, value: Any, ts: float | None, ts_real: bool) -> None:
        if not (isinstance(name, str) and name and value is not None):
            return
        if not isinstance(value, (str, int, float, bool)):
            return
        # NO-SUPPRESSION (hard rule): sentinels ("no reading" / uint-max) must
        # NOT be dropped from the flattened surface here — that removed the
        # field from raw_unmapped (Scout) entirely, even for fields we never
        # consume but whose name merely contains a sentinel needle. We keep the
        # field Scout-visible; the sentinel VALUE is skipped only at mapping
        # time in first(), so no sentinel ever lands on a mapped target.
        cand = ts if ts is not None else float("-inf")
        cand_real = ts_real and ts is not None
        prev = best.get(name)
        if prev is None:
            best[name] = (str(value), cand, cand_real)
            return
        # #529: ALL fields (incl. monotonic odometer/mileage) resolve by genuine
        # freshness so they come from the same snapshot. Cross-poll monotonic
        # protection lives in vehicle_cache.reconcile, not here.
        prev_real = prev[2]
        if cand_real and prev_real:
            # >= not >: a newer real ts wins, AND on an EQUAL real ts (two samples
            # in the SAME snapshot block, #529 S6) the later-appended one wins —
            # the log is append-ordered, so last-in-block is the newer reading.
            if cand >= prev[1]:
                best[name] = (str(value), cand, True)
        elif cand_real and not prev_real:
            best[name] = (str(value), cand, True)  # real beats floor/unknown
        elif not cand_real and not prev_real:
            # #529 S5/S6: no real ts on either → append-ordered log ⇒ last wins.
            best[name] = (str(value), cand, False)
        # else: incumbent is real and candidate is not → keep the real one.

    def walk(
        node: Any,
        prefix: str = "",
        node_ts: float | None = None,
        node_ts_real: bool = False,
        in_array: bool = False,
    ) -> None:
        if isinstance(node, dict):
            ts, ts_real = node_ts, node_ts_real
            for tk in _TS_KEYS:
                if tk in node:
                    parsed = _parse_ts(node[tk])
                    if parsed is not None:
                        ts, ts_real = parsed, True  # genuine per-point timestamp
                        break
            # data-point shape: {dataFieldName|name: X, value: Y}
            fname = node.get("dataFieldName") or node.get("name")
            if fname is not None and "value" in node:
                add(fname, node.get("value"), ts, ts_real)
                # v2.17.4/v2.17.5 — when the leaf name is a GENERIC token, also key
                # by the per-point ``key`` UUID so points that collide on a bare
                # name (many "value" points on MEB/ID.x) don't collapse and first()
                # can resolve them by UUID (e.g. 0ca40e18 → primary range). Only
                # UUIDs we actually MAP are aliased (_MAPPED_UUIDS) — aliasing every
                # generic point flooded the Scout with unmapped UUID rows (2.17.4
                # regression). Lowercased to match the dictionary + mapping forms.
                pkey = node.get("key")
                if (
                    isinstance(fname, str)
                    and fname.strip().lower() in _GENERIC_FIELD_NAMES
                    and isinstance(pkey, str)
                    and pkey.strip().lower() in _MAPPED_UUIDS
                ):
                    add(pkey.strip().lower(), node.get("value"), ts, ts_real)
                # v2.15.4 overreport fix: a data-point node reached through a
                # container (e.g. slope_consumption_values.ascent_slope_consumption
                # .physical_value) carries its full dotted path in ``prefix``. Emit
                # that CONTAINER-QUALIFIED key IN ADDITION to the bare leaf so (1)
                # the dotted first() forms actually match in the realistic portal
                # shape, and (2) ascent vs descent disambiguate — the bare leaf
                # ``physical_value`` is SHARED by both siblings and latest-wins
                # would otherwise collapse them to one value. The leftover bare
                # synonym is reclaimed by first()'s synonym-collapse so it does not
                # become a new chronic raw_unmapped re-reporter.
                if prefix and not in_array:
                    add(prefix, node.get("value"), ts, ts_real)
                    # Record the bare/qualified pair as EXPLICIT synonyms of each
                    # other (bidirectional). They come from THIS one physical node,
                    # so first()'s synonym-collapse is precise: it never touches a
                    # same-leaf field emitted by a DIFFERENT node.
                    if _syn_out is not None and isinstance(fname, str):
                        _syn_out.setdefault(fname, set()).add(prefix)
                        _syn_out.setdefault(prefix, set()).add(fname)
            for k, val in node.items():
                if k in ("dataFieldName", "name", "value"):
                    continue
                key = f"{prefix}.{k}" if prefix else str(k)
                if isinstance(val, (str, int, float, bool)):
                    add(key, val, ts, ts_real)
                    # b13 (#465): only emit the BARE name outside an array — a
                    # field inside e.g. chargingProfiles[] must not collapse
                    # onto the top-level key and clobber the active value.
                    if not in_array:
                        add(str(k), val, ts, ts_real)
                else:
                    walk(val, key, ts, ts_real, in_array)
        elif isinstance(node, list):
            # v2.15.1 (#465 RaAdNe): the portal ships a flat, ORDERED event-log
            # where each snapshot's capture time arrives as its OWN data-point
            # (``dataFieldName: car_captured_time``) rather than a sibling key, so
            # the per-point ts logic above never fires for it. Carry the running
            # capture time across the list so every following field inherits its
            # snapshot's REAL timestamp. Without it, a field repeated across
            # snapshots (e.g. ``settings.target_soc`` 100 then 80 after battery-care
            # lowered it) ties on the dataset floor and first-seen wins — surfacing
            # the stale 100 instead of the current 80 the car/app actually show.
            run_ts, run_real = node_ts, node_ts_real
            for item in node:
                if isinstance(item, dict):
                    ifn = item.get("dataFieldName") or item.get("name")
                    if (
                        isinstance(ifn, str)
                        and "value" in item
                        and any(h in ifn.lower() for h in _CAPTURED_NAME_HINTS)
                    ):
                        parsed = _parse_ts(item.get("value"))
                        if parsed is not None:
                            run_ts, run_real = parsed, True
                walk(item, prefix, run_ts, run_real, in_array=True)

    walk(payload, node_ts=dataset_ts)  # a11: bare fields inherit dataset freshness
    if _ts_out is not None:
        # Expose only GENUINE (real) per-point capture timestamps; floor/unknown
        # (-inf) carry no snapshot identity and must not constrain last_seen.
        for k, (_v, ts_v, ts_real_v) in best.items():
            if ts_real_v:
                _ts_out[k] = ts_v
    return {k: v[0] for k, v in best.items()}


def _to_float(raw: str | None) -> float | None:
    if raw is None:
        return None
    try:
        return float(str(raw).replace(",", "."))
    except (ValueError, TypeError):
        return None


def _to_int(raw: str | None) -> int | None:
    f = _to_float(raw)
    return int(f) if f is not None else None


def _dur_to_min(raw: str | None) -> int | None:
    """Parse a charging/climate duration to whole minutes (v2.15.2, #511 Ra72xx).

    The EU portal sends seconds with a trailing ``s`` (e.g. ``"2400s"`` = 40 min,
    ``"0s"`` = 0). A bare number is treated as already-minutes (older firmwares),
    preserving the previous behaviour.
    """
    if raw is None:
        return None
    s = str(raw).strip().lower()
    if not s:
        return None
    if s.endswith("s"):
        f = _to_float(s[:-1])
        return int(f // 60) if f is not None else None
    f = _to_float(s)
    return int(f) if f is not None else None


def _epoch_or_iso(raw: str | None) -> str | None:
    """Normalise a capture timestamp to ISO-8601 UTC.

    v2.15.1 — epoch seconds (or milliseconds) → ISO-8601 UTC string; an
    already-ISO string passes through unchanged. Unparseable → None.
    """
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    # Numeric → epoch seconds (ms heuristic: > 1e12).
    try:
        f = float(s)
    except (ValueError, TypeError):
        return s  # non-numeric → assume it's already an ISO/string timestamp
    from datetime import datetime, timezone  # noqa: PLC0415

    if f > 1e12:
        f /= 1000.0
    try:
        return datetime.fromtimestamp(f, tz=timezone.utc).isoformat()
    except (ValueError, OSError, OverflowError):
        return None


def _is_miles(unit_raw: str | None) -> bool:
    """True if a portal distance-unit companion field denotes miles.

    The portal ships either a string (``MILES``/``MILE``/``MI``/``KM``…) or a
    numeric enum (``0`` = km, ``1`` = miles) — the numeric ``1`` case is a known
    miles-vs-km pitfall confirmed against real UK/US portal payloads.
    """
    if unit_raw is None:
        return False
    return str(unit_raw).strip().lower() in ("miles", "mile", "mi", "1")


_ENUM_PREFIXES = (
    "CHARGE_STATE_", "CHARGE_MODE_", "CHARGING_MODE_",
    "IMMEDIATE_ACTION_STATE_",
    # v2.15.1 — charge-type / scenario / charge-reason enum families.
    "CHARGE_TYPE_", "CHARGING_SCENARIO_", "PROFILE_CHARGE_REASON_",
    # v2.15.3 — charge-settings enum families (#465/#514 settings.* block).
    # NOTE: the dict enum tokens are MAX_CHARGE_CURRENT_{INVALID,REDUCED,MAXIMUM,
    # MAX} — the prefix is MAX_CHARGE_CURRENT_ (NOT *_AC_, which is the field
    # name suffix, not the value prefix).
    "CHARGE_MODE_SELECTION_", "MAX_CHARGE_CURRENT_", "AUTO_UNLOCK_AC_",
    "BCAM_ACTIVATION_",
    # v2.15.4 — next-charging-timer reachability enum family (#521/#522 Scout).
    # Tokens: TARGET_REACHABILITY_{INVALID,CALCULATING,REACHABLE,NOT_REACHABLE}.
    # (report_type has no dict-listed values yet — no prefix; _shorten_enum keeps
    # its raw value until a real sample confirms one.)
    "TARGET_REACHABILITY_",
    # v2.15.5 — report-trigger reason enum family (update_reason, many VW-EU
    # Scouts). Tokens: UPDATE_REASON_{INVALID,CHARGING,CLAMP15_OFF,CLAMP15_ON,
    # CLIMATISATION,OTHER} — dict-confirmed, so _shorten_enum strips the prefix.
    "UPDATE_REASON_",
)

# v2.15.1 — labels appended to ``available_charge_modes`` per truthy
# charge_mode_selection_options flag. ONE list attribute, no per-flag entity.
_CHARGE_MODE_SUPPORT_LABELS: tuple[tuple[str, str], ...] = (
    ("immediate_charging", "IMMEDIATE"),
    ("timer_charging", "TIMER"),
    ("timer_charging_climatization", "TIMER_WITH_CLIMATISATION"),
    ("preferred_charging_times", "PREFERRED_CHARGING_TIMES"),
    ("only_own_current", "ONLY_OWN_CURRENT"),
    ("home_storage_charging", "HOME_STORAGE"),
    ("immediate_discharging", "IMMEDIATE_DISCHARGING"),
)


def _shorten_enum(value: str | None) -> str | None:
    """Strip a verbose VW protocol prefix from an enum label for display
    (e.g. ``CHARGE_STATE_CHARGING_HV_BATTERY`` → ``CHARGING_HV_BATTERY``).
    Already-short / non-prefixed values pass through unchanged."""
    if not isinstance(value, str):
        return value
    up = value.upper()
    # v2.15.3 — match the LONGEST applicable prefix, not the first listed: the
    # families overlap (``CHARGE_MODE_`` is a prefix of ``CHARGE_MODE_SELECTION_``)
    # so first-match would strip too little. Longest-first is order-independent.
    best = ""
    for pref in _ENUM_PREFIXES:
        if up.startswith(pref) and len(value) > len(pref) and len(pref) > len(best):
            best = pref
    return value[len(best):] if best else value


# b1/A6 — cap raw-discovery fields kept on the diagnostic sensor's attributes,
# so a pathological payload can't bloat the recorder / state machine.
_RAW_FIELD_CAP = 250

# b14 — NO field suppression. Policy (Prash): never hide Scout/raw fields; every
# portal field is surfaced so it can be mapped. (The b10 ``_SCOUT_SKIP_FIELDS`` /
# ``_is_noise`` filter was removed — we map everything, we don't suppress.)


def map_dataset_to_vehicle_data(
    fields: dict[str, str],
    d: VehicleData,
    field_ts: dict[str, float] | None = None,
    field_syn: dict[str, set[str]] | None = None,
) -> VehicleData:
    """Map a curated subset of EU Data Act fields onto ``VehicleData``.

    v2.12.0 ships the ~15 highest-value fields users care about (odometer,
    SoC, range, charging state, doors). The long tail of the 300+ field
    dictionary follows in later v2.12.x once live payloads confirm shapes.
    ``fields`` may carry both the bare name (``soc``) and dotted variants
    (``battery_state_report.soc``); we try both.
    """
    used: set[str] = set()
    syn = field_syn or {}

    def first(*names: str) -> str | None:
        for n in names:
            if n in fields:
                val = fields[n]
                # NO-SUPPRESSION: a sentinel ("no reading") value must never be
                # assigned to a mapped target, but the field stays Scout-visible.
                # We skip it WITHOUT marking it used, so it still appears in
                # raw_unmapped_fields for discovery/mapping later.
                if _is_sentinel(n, val):
                    continue
                used.add(n)
                # v2.15.4 synonym-collapse (no-suppression-safe): bare / dotted /
                # container-qualified spellings of the SAME field coexist in
                # ``fields`` because the walker emits BOTH the bare leaf AND the
                # full dotted path for a data-point node nested under a container.
                # Once we consume one spelling, mark every OTHER spelling of the
                # same datum used so it stops re-surfacing in raw_unmapped_fields.
                # "Other spellings" = (a) the remaining explicit ``*names`` of this
                # call, and (b) the matched name's EXPLICIT synonyms — the bare/
                # qualified twins recorded by _walk_fields for the one physical node
                # that emitted them. Because a synonym pair always originates from a
                # SINGLE node, two distinct nodes that merely share a leaf name
                # (e.g. battery_state_report.soc vs front_left_tyre.soc) are NEVER
                # synonyms and can never cross-collapse — even with equal values.
                # ascent/descent slope each carry their OWN container-qualified
                # synonym, so the shared bare ``physical_value`` is reclaimed by
                # whichever was matched first without conflating the two values.
                for other in names:
                    if other != n and other in fields:
                        used.add(other)
                for other in syn.get(n, frozenset()):
                    if other in fields:
                        used.add(other)
                return val
        return None

    soc = _to_int(first("battery_state_report.soc", "soc", "stateOfChargeInPercent",
                        "state_of_charge",
                        # b13 (#504) — legacy Car-Net charger dialect: the HV
                        # battery level IS the traction SoC. Kept LAST so the
                        # canonical sources win when a car reports both, and
                        # only the charger-dialect cars (which carry nothing
                        # else) fall back to it.
                        "battery_level_HV.value",
                        "battery_level_HV.battery_level_HV.value",
                        # v2.15.3 (#517) — charger-dialect alias: dict defines
                        # hv_soc as "state of charge for the high voltage
                        # battery" (identical semantic to battery_level_HV).
                        # LAST fallback only — never out-competes the canonical
                        # soc/battery_state_report.soc keys; just widens
                        # coverage for cars that report nothing else.
                        "hv_soc",
                        # v2.18.0 (#702) — Touareg-era legacy Car-Net export.
                        # These cars ship a flat {dataFieldName, value} dataset
                        # whose names are fully qualified (RBC.*/RTS.*/RDT.*),
                        # with no bare-leaf twin, so none of the keys above ever
                        # match and the car reads as "no data at all". LAST, for
                        # the same reason as the charger-dialect aliases.
                        "RBC.vehicleStates.[0].soc"))
    if soc is not None:
        d.battery_soc = soc
        d.has_battery = True

    odo = _to_int(first("mileage.value", "mileage", "odometer", "totalMileage"))
    if odo is not None:
        d.odometer_km = odo

    # ── b14 (#555 Passat GTE 1.4 eHybrid / #565 Tiguan eHybrid) ─────────────
    # PHEV electric/combustion range disambiguation.
    #
    # The portal ships TWO standalone range fields, primary + secondary, with no
    # companion engine_type on those flat fields themselves. The old code blindly
    # mapped cruising_range_primary_engine -> electric_range_km. That assumption
    # ("primary == electric") holds for BEVs (ID.x: a single electric engine) but
    # is INVERTED on MQB PHEVs (Passat/Tiguan GTE), where the PRIMARY engine is
    # the COMBUSTION engine and the SECONDARY engine is electric — so the VW app
    # shows electric 20 km / combustion 380 km while we showed them swapped.
    #
    # Grounded signal (eu_data_dictionary): the engine_type enum tokens are
    # ENGINE_TYPE_TYPE_IS_ELECTRIC vs ENGINE_TYPE_PETROL_GASOLINE /
    # _PETROL_DIESEL / _GAS_CNG / _GAS_LPG / _TYPE_IS_GAS / _TYPE_IS_PETROL. A
    # top-level engine_type, when present, names the PRIMARY engine's fuel type;
    # an explicit combustion token there proves a combustion-primary PHEV.
    #
    # We pick the orientation from the SAFEST grounded rule, in order:
    #   1. explicit top-level engine_type names the primary engine's fuel:
    #        electric token  -> primary is electric  (BEV / electric-primary)
    #        combustion token -> primary is combustion (PHEV)
    #   2. no usable engine_type, but BOTH a secondary range AND a fuel reading
    #      exist -> it's a PHEV with a combustion primary (a pure BEV has no fuel
    #      and no secondary range), so primary == combustion.
    #   3. otherwise default to the historical primary == electric (BEV-safe:
    #      pure electrics with only one range keep electric_range_km exactly as
    #      before).
    et_raw = first("engine_type", "battery_state_report.cruising_ranges.0.engine_type")
    et = (et_raw or "").upper()
    primary_raw = _to_int(first(
        "cruising_range_primary_engine", "primaryEngineRange",
        # v2.17.4 — MEB/ID.x ships the primary range as a UUID-only "value" point.
        # The engine-type logic below still routes it correctly (electric on a
        # BEV, combustion on a PHEV), so wiring it here needs no orientation care.
        "0ca40e18-0564-3eda-bcc0-7aee9ef44f04",
    ))
    secondary_raw = _to_int(first("cruising_range_secondary_engine"))
    has_fuel = (
        first("fuel_level_current_level", "tank_current_level",
              "fuelLevel_pct", "fuel_level") is not None
    )
    _ELECTRIC_TOKENS = ("ELECTRIC",)
    _COMBUSTION_TOKENS = ("PETROL", "GASOLINE", "DIESEL", "_GAS", "CNG", "LPG")
    if any(t in et for t in _ELECTRIC_TOKENS):
        primary_is_combustion = False
    elif any(t in et for t in _COMBUSTION_TOKENS):
        primary_is_combustion = True
    else:
        # No usable engine_type: a secondary range + a fuel reading => PHEV with
        # a combustion primary engine. (A pure BEV reports neither.)
        primary_is_combustion = secondary_raw is not None and has_fuel

    if primary_is_combustion:
        # PHEV, combustion-primary: primary range is combustion, secondary is
        # electric (this is the #555/#565 swap fix).
        if primary_raw is not None and d.combustion_range_km is None:
            d.combustion_range_km = primary_raw
        if secondary_raw is not None and d.electric_range_km is None:
            d.electric_range_km = secondary_raw
    else:
        # BEV / electric-primary (UNCHANGED behaviour): primary range is the
        # electric range, secondary (if any) stays on its own sensor below.
        if primary_raw is not None and d.electric_range_km is None:
            d.electric_range_km = primary_raw

    # range_km — the headline "range" sensor. Keep the legacy ordering (the bare
    # ``range``/total spellings first, then the primary engine range) untouched
    # so the existing range_km behaviour is preserved for every car.
    rng = _to_int(first("range", "cruising_range_primary_engine",
                        "totalRange_km", "primaryEngineRange",
                        "0ca40e18-0564-3eda-bcc0-7aee9ef44f04"))
    if rng is not None:
        d.range_km = rng
        if d.electric_range_km is None:
            d.electric_range_km = rng

    # #717 — battery_state_report.charge_power / charge_power are RAW
    # 0.1-kW-resolution portal values (EU data dict UUID 44ed0d61: "actual charge
    # power … range 0..500 with a resolution of 0,1 kW"; the reporter saw 65 →
    # 6.5 kW), so they scale /10 — the same deci-unit handling the temps + kWh
    # fields below already get. The chargePower_kW / charging_power aliases carry
    # kW already (chargePower_kW by name; charging_power UUID 978be4ed treated as
    # kW by convention — #518), so they stay UNSCALED.
    cp_deci = _to_float(first("battery_state_report.charge_power", "charge_power"))
    if cp_deci is not None:
        d.charging_power_kw = round(cp_deci / 10.0, 1)
    else:
        cp_kw = _to_float(first("chargePower_kW", "charging_power"))
        if cp_kw is not None:
            d.charging_power_kw = cp_kw

    # 2.15.1 — the charger dialect reports charged energy
    # (battery_state_report.charge_energy). The EU data dictionary defines this
    # as PER-SESSION ("charged energy in kWh, 0..1000, EV must be connected to
    # charger" — a gauge that reads 0.0 when idle), NOT a lifetime total. So it
    # belongs on the per-session sensor (charge_session_energy_kwh), not the
    # lifetime total_charged_energy_kwh. (The CUPRA/SEAT chargeEnergyInKwh field
    # IS genuinely lifetime and is mapped separately — left untouched.)
    ce = _to_float(first("battery_state_report.charge_energy", "charge_energy",
                        "chargedEnergy_kWh"))
    if ce is not None and ce >= 0:
        d.charge_session_energy_kwh = ce

    tsoc = _to_int(first("settings.target_soc", "target_soc", "targetSOC_pct"))
    if tsoc is not None:
        d.target_soc = tsoc

    cs = first("charging_state_report.current_charge_state", "current_charge_state",
               "chargingState", "charging_state")
    if cs:
        # is_charging from the RAW value (logic unchanged); store a shortened
        # label for display (a13/A4 — strips verbose VW enum prefixes).
        d.is_charging = cs.lower() in ("charging", "chargingacactive", "active")
        d.charging_state = _shorten_enum(cs)

    else:
        # v2.18.0 (#702) — the Touareg-era legacy export reports charging as a
        # BOOLEAN, not the VW state enum. It deliberately does NOT ride the
        # ``cs`` lookup above: "true" is not in that enum tuple, so a charging
        # car would come out as NOT charging. Only consulted when the canonical
        # state is absent, so nothing changes for cars that ship both.
        _legacy_chg = first("RBC.vehicleStates.[0].charging")
        if _legacy_chg is not None:
            d.is_charging = str(_legacy_chg).strip().lower() in ("true", "1")

    cmode = first("charging_state_report.charge_mode", "charge_mode",
                  # v2.18.0 (#702) — Touareg-era legacy export (e.g.
                  # TIMER_BASED_CHARGING). Enum-shaped like the canonical
                  # sources, so it can share this lookup; LAST as always.
                  "RBC.chargerSettings.[0].chargeModeSelection.value")
    if cmode:
        d.charge_mode = _shorten_enum(cmode)

    tmin = _to_float(first("min_temperature", "battery_min_temperature"))
    if tmin is not None:
        d.hv_battery_min_temperature_c = tmin
    tmax = _to_float(first("max_temperature", "battery_max_temperature"))
    if tmax is not None:
        d.hv_battery_max_temperature_c = tmax

    # v2.17.5 — qualified door-lock fields win over the bare ``locked`` leaf: a
    # ``trunk.locked`` container ALSO emits a bare ``locked`` (cross-container
    # collision) that would otherwise mis-set doors_locked from the trunk state.
    locked = first("doors_locked", "doorLockStatus", "locked")
    if locked is not None:
        d.doors_locked = str(locked).lower() in ("true", "locked", "1")

    whs = first("window_heating_state", "windowHeatingState")
    if whs is not None:
        on = str(whs).lower() == "on"
        d.window_heating_front = on
        d.window_heating_back = on

    lifetime = _to_int(first(
        "cso_v1_vehicle_tripstatistics_total_mileage_subscribe",
        "total_mileage", "overallMileage",
    ))
    if lifetime is not None:
        d.lifetime_distance_km = lifetime

    # a12 — additional high-confidence portal fields (purely additive; every
    # existing mapping above is untouched). Names tried defensively via first().
    # v2.15.4 (#523) — actual_charge_rate (dict UUID 370c2092) has its OWN
    # unit=null, so the dict does NOT mark it km/h. It is folded into
    # charging_rate_kmh as the "actual" variant of the same charge-rate family
    # the canonical `Charge Rate` entry (dict UUID 732b602c, unit=kmPerHour)
    # already represents — i.e. the km/h rate charging_rate_kmh maps. Added as
    # the LAST alias so canonical/report-shaped keys still win when both appear.
    # #717 — battery_state_report.charge_rate / charge_rate are RAW
    # 0.1-resolution portal values (dict UUID 0c60a14f: "actual rate … range
    # 0..3000 with a resolution of 0,1"; reporter saw 149 → 14.9), so /10. The
    # chargeRate_kmph / charging_rate_kmh / actual_charge_rate aliases already
    # carry the real km/h value and stay UNSCALED.
    crate_deci = _to_float(first("battery_state_report.charge_rate", "charge_rate"))
    if crate_deci is not None:
        d.charging_rate_kmh = round(crate_deci / 10.0, 1)
    else:
        crate = _to_int(first("chargeRate_kmph", "charging_rate_kmh",
                              "actual_charge_rate"))
        if crate is not None:
            d.charging_rate_kmh = crate

    plug = first("charging_plug1_connectionstate", "plug_connection_state",
                 "plugConnectionState", "plug_state")
    if plug is not None:
        d.plug_state = plug
        d.plug_connected = str(plug).lower() in ("connected", "plugged", "true", "1")

    # b1/A1 — flat MQB / PHEV schema fields (Golf GTE, Passat GTE, e-Golf, Taigo,
    # Polo…). `_walk_fields` already emits both flat + dotted; these add the flat
    # names to the curated map so legacy/PHEV cars get real telemetry over the EU
    # Data Act portal instead of empty entities. Only unambiguous explicit-field
    # mappings here — primary/electric range stays for the EV-type detection
    # (B3) to avoid mislabelling a PHEV's ICE range as electric.
    # v2.15.3 — tank_current_level is the EU-portal dialect name for the fuel
    # percent (distinct from fuel_level_current_level already tried first).
    fuel = _to_int(first("fuel_level_current_level", "tank_current_level",
                         "fuelLevel_pct", "fuel_level"))
    if fuel is not None:
        d.fuel_level = fuel

    v12 = _to_float(first("boardnetBatteryVoltageIndication", "boardnet_battery_voltage"))
    if v12 is not None:
        d.voltage_12v = v12

    oil = _to_int(first("oil_level_actual_level", "oilLevel_pct", "oil_level_pct"))
    if oil is not None:
        d.oil_level_pct = oil

    # v2.15.4 (#521/#522) — outdoor_temperature is the EU-portal dialect alias
    # for the same ambient reading (dict: "Current outdoor temperature in °C").
    # Added LAST so the dK-carrying outside_temperature wins when both appear;
    # the > 200 guard below already handles dK-vs-°C either way, so the plain-°C
    # outdoor_temperature sample (e.g. 31.5) passes through untouched.
    otemp = _to_float(first("outsideTemperatureIndication", "outside_temperature",
                            "outside_temp", "outdoor_temperature"))
    if otemp is not None:
        # flat MQB ships outside temp in deci-Kelvin (e.g. 2981 = 24.95 °C); an
        # already-°C value (e.g. 17.1) stays as-is — no ambient temp is > 200 °C.
        d.outside_temp = round(otemp / 10 - 273.15, 1) if otemp > 200 else otemp

    # v2.17.1 (Scout #701, VW ID.7) — EU-portal HV-battery + cabin temps.
    # `hvbatterytemperature.{min,max}_temperature` feed the same
    # battery_temp (min) / battery_temp_max (max) sensors the CARIAD-BFF
    # fills from temperatureHvBattery{Min,Max}_K, so portal-only cars get
    # them too. Same >200 deci-Kelvin guard as the ambient reading; only
    # fill when the BFF channel hasn't already provided a value.
    hv_min = _to_float(first("hvbatterytemperature.min_temperature"))
    if hv_min is not None and d.battery_temp is None:
        d.battery_temp = round(hv_min / 10 - 273.15, 1) if hv_min > 200 else hv_min
    hv_max = _to_float(first("hvbatterytemperature.max_temperature"))
    if hv_max is not None and d.battery_temp_max is None:
        d.battery_temp_max = round(hv_max / 10 - 273.15, 1) if hv_max > 200 else hv_max

    # v2.18.0 (#702) — Touareg-era legacy Car-Net export: climate target temp,
    # also deci-Kelvin (2930 = 19.85 °C), with the same measurement-state
    # companion as the in-cabin reading below. Same >200 dK guard, so a plain-°C
    # dialect would pass through untouched.
    _legacy_tt_state = first("RPC.climaterSettings.[0].targetTemperatureMeasurementState")
    _legacy_tt = _to_float(first("RPC.climaterSettings.[0].targetTemperature"))
    if (
        _legacy_tt is not None
        and d.target_temperature is None
        and (
            _legacy_tt_state is None
            or str(_legacy_tt_state).lower()
            not in ("invalid", "error", "measurement_invalid", "not_available")
        )
    ):
        d.target_temperature = (
            round(_legacy_tt / 10 - 273.15, 1) if _legacy_tt > 200 else _legacy_tt
        )

    # v2.18.0 (#702) — Touareg-era legacy export: the charger's picked AC
    # current limit in amperes. It sits under ``chargerSettings``, so it is the
    # *setting* twin (what the user chose), not the live deliverable amperage.
    _legacy_mca = _to_int(first("RBC.chargerSettings.[0].maxChargeCurrentAmpere"))
    if _legacy_mca is not None and d.charge_max_ac_setting is None:
        d.charge_max_ac_setting = _legacy_mca

    # v2.18.0 (Phase C groundwork) — the legacy one-time export carries the
    # departure-timer minimum charge limit under ``RDT.timerBasicSettings
    # .[0].chargeMinLimit`` (a %). It is the same value the modern feed calls
    # ``charging.chargingSettings.value.minChargeLimit_pct`` (parsed into
    # ``min_soc`` in vw_eu.py), so this lights up the EXISTING min_soc sensor
    # for a car we only have a one-time export for — no new surface. Canonical
    # (modern feed) wins; this is the fallback.
    _legacy_min = _to_int(first("RDT.timerBasicSettings.[0].chargeMinLimit"))
    if _legacy_min is not None and d.min_soc is None:
        d.min_soc = _legacy_min

    # v2.18.0 (Phase C) — climatise-without-HV-power config flag. Official
    # dictionary: "regulating the temperature is allowed without a power
    # source." The RPC and RDT copies carry the same value; take whichever is
    # present.
    _legacy_cwhv = first(
        "RPC.climaterSettings.[0].climatisationWithoutHVPower",
        "RDT.timerBasicSettings.[0].climatisationWithoutHVPower",
    )
    if _legacy_cwhv is not None and d.climatisation_without_hv_power is None:
        d.climatisation_without_hv_power = (
            str(_legacy_cwhv).strip().lower() in ("true", "1")
        )

    # `in_cabin_temperature.temperature` — current interior °C. The
    # companion `measurement_state` flags validity; skip an explicitly
    # invalid reading but accept when the flag is absent (not all reports
    # carry it). Same dK guard.
    cabin_state = first("in_cabin_temperature.measurement_state")
    cabin_t = _to_float(first("in_cabin_temperature.temperature"))
    if cabin_t is not None and (
        cabin_state is None
        or str(cabin_state).lower()
        not in ("invalid", "error", "measurement_invalid", "not_available")
    ):
        d.cabin_temp = round(cabin_t / 10 - 273.15, 1) if cabin_t > 200 else cabin_t

    # `battery_state_report.charge_target_time` — ISO-8601 ts the pack
    # reaches its charge target (charging analog of climatisation_ready_at).
    ctt = first("battery_state_report.charge_target_time", "charge_target_time")
    if isinstance(ctt, str) and ctt.strip():
        d.charge_target_time = ctt.strip()

    # `max_number_users` — vehicle-profile seat/account capacity (diagnostic).
    mnu = _to_int(first("max_number_users"))
    if mnu is not None:
        d.max_number_users = mnu

    sec_rng = _to_int(first("cruising_range_secondary_engine"))
    if sec_rng is not None:
        d.secondary_engine_range_km = sec_rng

    comb_rng = _to_int(first("cruising_range_combined", "totalRange_km"))
    if comb_rng is not None:
        d.total_range_km = comb_rng

    insp = _to_int(first("inspectionDistance", "inspection_distance"))
    if insp is not None and d.service_km is None:
        d.service_km = insp

    # b5 — flat MQB maintenance intervals + lock + window-heating that the raw
    # field discovery surfaced in real Golf-class portal payloads. Mapping them
    # gives the portal channel real service/lock telemetry without the (OTP-bound)
    # vw.de channel. Values are portal-reported; a negative interval = overdue.
    # The portal reports these as NEGATIVE remaining-until-due (e.g. -155 =
    # "due in 155 days", -14900 = "due in 14900 km"); negate so the sensors read
    # as a positive countdown (a value that goes negative = genuinely overdue).
    svc_km = _to_int(first("maintenance_interval_distance_until_inspection"))
    if svc_km is not None and d.service_km is None:
        d.service_km = -svc_km
    svc_days = _to_int(first("maintenance_interval__time_until_inspection"))
    if svc_days is not None:
        if d.service_due_in_days is None:
            d.service_due_in_days = -svc_days
        # v2.15.13 — also feed the existing DATE sensor (``service_due_at``)
        # on the EU-Data-Act path. Until now the portal reader set only the
        # int day-counter, so portal users saw "in N days" but the absolute
        # "due on <date>" sensor stayed empty (brand-native paths populate it,
        # the portal path didn't). Store the raw int day-offset; sensor.py
        # native_value converts int→``date.today()+N`` (local midnight).
        if d.service_due_at is None:
            d.service_due_at = -svc_days
    oil_km = _to_int(first("maintenance_interval_distance_until_oil_change"))
    if oil_km is not None and d.oil_service_km is None:
        d.oil_service_km = -oil_km
    oil_days = _to_int(first("maintenance_interval__time_until_oil_change"))
    if oil_days is not None:
        if d.oil_service_due_in_days is None:
            d.oil_service_due_in_days = -oil_days
        if d.oil_service_at is None:
            d.oil_service_at = -oil_days

    lock = first("lock_state", "central_lock_state")
    if lock is not None and d.doors_locked is None:
        d.doors_locked = str(lock).lower() in ("locked", "safe")

    whf = first("window_heating_state_front")
    if whf is not None and d.window_heating_front is None:
        d.window_heating_front = str(whf).lower() in ("on", "active", "true", "1")
    whr = first("window_heating_state_rear")
    if whr is not None and d.window_heating_back is None:
        d.window_heating_back = str(whr).lower() in ("on", "active", "true", "1")

    # ── b10 — portal long-tail (doors/windows/trip/maintenance) ─────────────
    # Enum families resolved from the official data dictionary:
    #   lock-state    2=locked / 3=unlocked
    #   open-state    2=open   / 3=closed   (doors, hood, tailgate)
    #   window-lifter 2=open   / 3=closed
    #   0=unsupported, 1=invalid → ignore. position fields are % open (0=closed).

    # doors_locked from the PER-DOOR lock states. This is the authoritative
    # signal on the portal's payload (the bare `locked` field is absent/stale —
    # it was wrongly reporting an unlocked car), so it OVERRIDES the block above.
    _locks = [
        _to_int(first("locked_state_front_left_door")),
        _to_int(first("locked_state_front_right_door")),
        _to_int(first("locked_state__rear_left_door")),   # double underscore in spec
        _to_int(first("locked_state_rear_right_door")),
    ]
    _tail_lock = _to_int(first("locked_state_tailgate"))
    _lock_vals = [v for v in (*_locks, _tail_lock) if v in (2, 3)]
    if _lock_vals:
        d.doors_locked = all(v == 2 for v in _lock_vals)  # any unlocked → False
    if _tail_lock in (2, 3) and d.trunk_locked is None:
        d.trunk_locked = _tail_lock == 2
    # v2.17.5 — the boolean ``trunk.locked`` dialect (dotted spelling so it never
    # collides with the door's bare ``locked``). "true" = trunk locked.
    _trunk_l = first("trunk.locked", "trunk_locked")
    if _trunk_l is not None and d.trunk_locked is None:
        d.trunk_locked = str(_trunk_l).strip().lower() in ("true", "locked", "1")

    # open-state → doors_individual (True == OPEN, matching the vw_eu polarity)
    for _slot, _name in (
        ("frontLeft", "open_state_front_left_door"),
        ("frontRight", "open_state_front_right_door"),
        ("rearLeft", "open_state_rear_left_door"),
        ("rearRight", "open_state_rear_right_door"),
    ):
        _ov = _to_int(first(_name))
        if _ov in (2, 3):
            d.doors_individual[_slot] = _ov == 2
    if d.doors_individual and d.doors_open is None:
        d.doors_open = any(d.doors_individual.values())
    _tail_open = _to_int(first("open_state_tailgate"))
    if _tail_open in (2, 3) and d.trunk_open is None:
        d.trunk_open = _tail_open == 2
    _bonnet_open = _to_int(first("open_state_front_engine_bonnet"))
    if _bonnet_open in (2, 3) and d.hood_open is None:
        d.hood_open = _bonnet_open == 2
    # state_of_hood — separate source field, same enum family (dict: unsupported
    # 0 / invalid 1 / open 2 / closed 3). Fold into hood_open as a fallback when
    # the open_state_front_engine_bonnet channel is absent.
    _hood_state = _to_int(first("state_of_hood"))
    if _hood_state in (2, 3) and d.hood_open is None:
        d.hood_open = _hood_state == 2

    # window-lifter state → windows_individual (True == CLOSED, per the model
    # convention) + windows_open aggregate; position is % open.
    for _slot, _name in (
        ("frontLeft", "state_front_left_door_window_lifter"),
        ("frontRight", "state_front_right_door_window_lifter"),
        ("rearLeft", "state_rear_left_door_window_lifter"),
        ("rearRight", "state_rear_right_door_window_lifter"),
    ):
        _wv = _to_int(first(_name))
        if _wv in (2, 3):
            d.windows_individual[_slot] = _wv == 3
    if d.windows_individual and d.windows_open is None:
        d.windows_open = any(v is False for v in d.windows_individual.values())
    for _slot, _name in (
        ("frontLeft", "position_front_left_door_window_lifter"),
        ("frontRight", "position_front_right_door_window_lifter"),
        ("rearLeft", "position_rear_left_door_window_lifter"),
        ("rearRight", "position_rear_right_door_window_lifter"),
    ):
        _pv = _to_int(first(_name))
        if _pv is not None:
            d.windows_position[_slot] = _pv

    # trip statistics (short-term → last trip, long-term → lifetime). Units from
    # the dictionary: mileage km, travel_time min, speed km/h. Consumption fields
    # (l/1000km, kWh/1000km) are deferred — current values look like sentinels;
    # they stay Scout-visible for a live A/B before we trust the scale.
    _st_dist = _to_float(first("short_term_data_mileage"))
    if _st_dist is not None and d.last_trip_distance_km is None:
        d.last_trip_distance_km = _st_dist
    _st_time = _to_int(first("short_term_data_travel_time"))
    if _st_time is not None and d.last_trip_duration_min is None:
        d.last_trip_duration_min = _st_time
    _lt_speed = _to_float(first("long_term_data_average_speed"))
    if _lt_speed is not None:
        d.lifetime_avg_speed_kmh = _lt_speed
    _lt_time = _to_int(first("long_term_data_travel_time"))
    if _lt_time is not None:
        d.lifetime_travel_time_min = _lt_time

    # maintenance — warning flags (1 == active) + average monthly mileage
    _oilw = _to_int(first("maintenance_interval_oil_change_warning"))
    if _oilw is not None and d.warning_oil is None:
        d.warning_oil = _oilw == 1
    _insw = _to_int(first("maintenance_interval_inspection_warning"))
    if _insw is not None:
        d.warning_inspection = _insw == 1
    _mm = _to_int(first("maintenance_interval_monthly_mileage"))
    if _mm is not None:
        d.monthly_mileage_km = _mm

    # remaining times (minutes)
    _rcl = _dur_to_min(first("remaining_climatisation_time", "remaining_climate_time"))
    if _rcl is not None and d.climate_remaining_time_min is None:
        d.climate_remaining_time_min = _rcl
    # v2.15.1 — battery_state_report.remaining_charging_time_complete is the
    # preferred source; it joins this EXISTING chain ahead of the bare
    # remaining_charging_time. Single assignment — do not add a second line.
    _rch = _dur_to_min(first(
        "battery_state_report.remaining_charging_time_complete",
        "remaining_charging_time_complete",
        "remaining_charging_time",
    ))
    if _rch is not None and d.remaining_charge_time_min is None:
        d.remaining_charge_time_min = _rch

    # b1/A2 — distance-unit conversion. UK/US cars report distances in miles
    # plus a companion unit field; our sensors are km-typed, so convert once
    # here (km cars hit the no-op branch). Post-process so the individual field
    # mappings above stay untouched.
    if _is_miles(first("mileage.unit", "range.unit", "distance_unit", "distanceUnit")):
        for _attr in ("odometer_km", "range_km", "electric_range_km",
                      "combustion_range_km", "secondary_engine_range_km",
                      "total_range_km", "service_km", "oil_service_km",
                      "monthly_mileage_km", "last_trip_distance_km"):
            _val = getattr(d, _attr)
            if _val is not None:
                setattr(d, _attr, round(_val * 1.60934))

    # ── v2.15.1 — 2.15.0 plan: EU Data Act MAP-INTO-EXISTING + NEW fields ────
    # All additive and guarded; every existing mapping above is untouched.

    # charge_mode_selection_options (7 bools) → available_charge_modes labels.
    # Collapses to ONE list attribute (no per-flag entity). De-duplicated.
    for _opt, _label in _CHARGE_MODE_SUPPORT_LABELS:
        _mode_flag = first(
            f"charge_mode_selection_options.{_opt}",
            f"charge_mode_selection_options_{_opt}",
            _opt,
        )
        if (
            _mode_flag is not None
            and str(_mode_flag).lower() in ("true", "1", "set", "on", "yes")
            and _label not in d.available_charge_modes
        ):
            d.available_charge_modes.append(_label)

    # charge_type → charging_type (_shorten_enum, CHARGE_TYPE_ prefix added).
    _ctype = first("charging_state_report.charge_type", "charge_type", "chargeType")
    if _ctype is not None:
        d.charging_type = _shorten_enum(_ctype)

    # charging_mode → charging_preferred_mode (guard is None so a BFF value
    # is never clobbered).
    _cmode = first("charging_mode", "chargingMode")
    if _cmode is not None and d.charging_preferred_mode is None:
        d.charging_preferred_mode = _shorten_enum(_cmode)

    # battery_care_mode.charge_bcam_threshold → battery_care_target_soc_pct.
    _bcam = _to_int(first("battery_care_mode.charge_bcam_threshold",
                          "charge_bcam_threshold"))
    if _bcam is not None:
        d.battery_care_target_soc_pct = _bcam

    # energy_contents.{current,maximal}_energy_content.physical_value gated on
    # the companion value_type being valid.
    def _value_type_ok(*names: str) -> bool:
        vt = first(*names)
        # Companion is consumed (so it leaves raw_unmapped_fields) but only
        # gates: an explicit "invalid"/"error"/"0" token blocks the value.
        if vt is None:
            return True  # no gate present → don't block a real reading
        return str(vt).strip().lower() not in ("invalid", "error", "0", "false")

    # physical_value is reported in 0.1-kWh units (100 Wh), so divide by 10 to
    # get kWh — e.g. raw 756 → 75.6 kWh, 461 → 46.1 kWh (#534, ID.4 2024).
    _cur_kwh = _to_float(first(
        "energy_contents.current_energy_content.physical_value",
        "current_energy_content.physical_value",
    ))
    if _cur_kwh is not None and _value_type_ok(
        "energy_contents.current_energy_content.value_type",
        "current_energy_content.value_type",
    ):
        d.battery_available_kwh = _cur_kwh / 10.0
    _max_kwh = _to_float(first(
        "energy_contents.maximal_energy_content.physical_value",
        "maximal_energy_content.physical_value",
    ))
    if _max_kwh is not None and _value_type_ok(
        "energy_contents.maximal_energy_content.value_type",
        "maximal_energy_content.value_type",
    ):
        d.battery_cap_kwh = _max_kwh / 10.0

    # Trip consumption averages (l/1000km → l/100km, kWh/1000km → kWh/100km).
    # Guard is None so we don't overwrite a value the structured path set.
    _stf = _to_float(first("short_term_data_average_fuel_consumption"))
    if _stf is not None and d.last_trip_avg_fuel_consumption_l_100km is None:
        d.last_trip_avg_fuel_consumption_l_100km = _stf / 10
    _ste = _to_float(first("short_term_data_average_electr_engine_consumption"))
    if _ste is not None and d.last_trip_avg_electric_consumption_kwh_100km is None:
        d.last_trip_avg_electric_consumption_kwh_100km = _ste / 10
    _ltf = _to_float(first("long_term_data_average_fuel_consumption"))
    if _ltf is not None and d.lifetime_avg_fuel_consumption_l_100km is None:
        d.lifetime_avg_fuel_consumption_l_100km = _ltf / 10
    _lte = _to_float(first("long_term_data_average_electr_engine_consumption"))
    if _lte is not None and d.lifetime_avg_electric_consumption_kwh_100km is None:
        d.lifetime_avg_electric_consumption_kwh_100km = _lte / 10

    # v2.15.3 (#517) — auxiliary-consumer + gas consumption averages.
    # Dict units: aux = "kwH/1000km", gas = "kg/1000km" → /10 for per-100km.
    _ltaux = _to_float(first("long_term_data_average_aux_consumer_consumption"))
    if _ltaux is not None and d.lifetime_avg_aux_consumption_kwh_100km is None:
        d.lifetime_avg_aux_consumption_kwh_100km = _ltaux / 10
    _staux = _to_float(first("short_term_data_average_aux_consumer_consumption"))
    if _staux is not None and d.last_trip_avg_aux_consumption_kwh_100km is None:
        d.last_trip_avg_aux_consumption_kwh_100km = _staux / 10
    _ltgas = _to_float(first("long_term_data_average_gas_consumption"))
    if _ltgas is not None and d.lifetime_avg_gas_consumption_kg_100km is None:
        d.lifetime_avg_gas_consumption_kg_100km = _ltgas / 10
    _stgas = _to_float(first("short_term_data_average_gas_consumption"))
    if _stgas is not None and d.last_trip_avg_gas_consumption_kg_100km is None:
        d.last_trip_avg_gas_consumption_kg_100km = _stgas / 10

    # v2.15.3 (#517) — long-term range-gain + zero-emission distance. Dict unit
    # for both is "100m" (i.e. 0.1 km steps) → multiply by 0.1 for km.
    _ltrg = _to_float(first("long_term_data_range_gain_distance"))
    if _ltrg is not None and d.lifetime_range_gain_km is None:
        d.lifetime_range_gain_km = _ltrg * 0.1
    _strg = _to_float(first("short_term_data_range_gain_distance"))
    if _strg is not None and d.last_trip_range_gain_km is None:
        d.last_trip_range_gain_km = _strg * 0.1
    _ltze = _to_float(first("long_term_data_zero_emission_distance"))
    if _ltze is not None and d.lifetime_zero_emission_km is None:
        d.lifetime_zero_emission_km = _ltze * 0.1
    _stze = _to_float(first("short_term_data_zero_emission_distance"))
    if _stze is not None and d.last_trip_zero_emission_km is None:
        d.last_trip_zero_emission_km = _stze * 0.1

    # v2.15.3 (#517) — trigger info about the last battery-charger update
    # (string enum, e.g. "other"). Shorten any verbose prefix. LOW value but
    # dict-confirmed; disabled-by-default at the entity layer.
    _bcut = first("last_battery_charger_update_trigger")
    if _bcut is not None and d.charger_update_trigger is None:
        d.charger_update_trigger = _shorten_enum(_bcut)
    # v2.16.2 (#636) — report-delivery trigger enum (ROA/ICL/USM/ICL_REMOTE/
    # ROA_REMOTE, "Trigger of the call service"). dict-confirmed, LOW; fail-soft
    # (only mapped when first() finds it), disabled-by-default at the entity.
    _trig = first("trigger_type")
    if _trig is not None and d.report_trigger is None:
        d.report_trigger = _shorten_enum(_trig)
    # NOTE: scope_potential_total (PPE-only, opaque) and echo (constant
    # heartbeat token) are intentionally NOT mapped — they stay Scout-visible
    # in raw_unmapped_fields (no first() call → no false signal).

    # v2.15.5 (#541) — V2G / bidirectional-charging charge-level limits. Dict
    # type=number, unit=null; description "Additional SOC range for
    # bidirectional charging" → percent. Upper / lower bidi charge-level limit.
    # first() drops the uint16 65535 sentinel; container + bare spellings tried.
    # ONLY these two bidi_* fields were reported (#541) — the rest of the
    # bidirectional_charging_mode.* family stays Scout-visible.
    _bidi_max = _to_int(first(
        "bidirectional_charging_mode.bidi_max_Soc", "bidi_max_Soc"))
    if _bidi_max is not None and d.bidi_max_charge_level_pct is None:
        d.bidi_max_charge_level_pct = _bidi_max
    _bidi_min = _to_int(first(
        "bidirectional_charging_mode.bidi_min_Soc", "bidi_min_Soc"))
    if _bidi_min is not None and d.bidi_min_charge_level_pct is None:
        d.bidi_min_charge_level_pct = _bidi_min

    # v2.15.3 (#518) — EU-Data-Act charging-detail string family. All
    # dict-confirmed type=string with no enum list in the dictionary (the enum
    # tokens are only observed from samples: connected/disconnected, locked/
    # unlocked, initializing/notAvailable, …). We map each via first() with
    # _shorten_enum() for display consistency and store the lowercased junk
    # sentinels as None so single-port cars don't get a dead "invalid" entity.
    # NEVER suppressed at the field layer — two-port cars (plug2) exist and the
    # field is always defined; only this car's junk samples are skipped.
    def _charge_str(*names: str) -> str | None:
        raw = first(*names)
        if raw is None:
            return None
        # junk sentinels for these state strings: no active session / single-
        # port car / infra not yet up. Skip → field stays None (no phantom
        # entity) but the raw key is still consumed for discovery hygiene.
        if str(raw).strip().lower() in (
            "invalid", "unavailable", "notavailable", "error", "unknown",
        ):
            return None
        return _shorten_enum(raw)

    _atsoc = _charge_str("active_target_soc")
    if _atsoc is not None and d.active_target_soc is None:
        d.active_target_soc = _atsoc
    _ctd = _charge_str("charge_time_display")
    if _ctd is not None and d.charge_time_display is None:
        d.charge_time_display = _ctd

    _p1fl = _charge_str("charging_plug1_flap_lock_state")
    if _p1fl is not None and d.charging_plug1_flap_lock_state is None:
        d.charging_plug1_flap_lock_state = _p1fl
    _p1f = _charge_str("charging_plug1_flap_state")
    if _p1f is not None and d.charging_plug1_flap_state is None:
        d.charging_plug1_flap_state = _p1f
    _p1i = _charge_str("charging_plug1_infrastructure_state")
    if _p1i is not None and d.charging_plug1_infrastructure_state is None:
        d.charging_plug1_infrastructure_state = _p1i
    _p1l = _charge_str("charging_plug1_lock_state")
    if _p1l is not None and d.charging_plug1_lock_state is None:
        d.charging_plug1_lock_state = _p1l

    _p2c = _charge_str("charging_plug2_connectionstate")
    if _p2c is not None and d.charging_plug2_connectionstate is None:
        d.charging_plug2_connectionstate = _p2c
    _p2fl = _charge_str("charging_plug2_flap_lock_state")
    if _p2fl is not None and d.charging_plug2_flap_lock_state is None:
        d.charging_plug2_flap_lock_state = _p2fl
    _p2f = _charge_str("charging_plug2_flap_state")
    if _p2f is not None and d.charging_plug2_flap_state is None:
        d.charging_plug2_flap_state = _p2f
    _p2i = _charge_str("charging_plug2_infrastructure_state")
    if _p2i is not None and d.charging_plug2_infrastructure_state is None:
        d.charging_plug2_infrastructure_state = _p2i
    _p2l = _charge_str("charging_plug2_lock_state")
    if _p2l is not None and d.charging_plug2_lock_state is None:
        d.charging_plug2_lock_state = _p2l

    # parking_light_left / _right → aggregate parking_light + per-side fields.
    _pll = first("parking_light_left")
    _plr = first("parking_light_right")

    def _truthy_light(raw: str | None) -> bool | None:
        if raw is None:
            return None
        return str(raw).lower() in ("true", "1", "on")

    _pll_b = _truthy_light(_pll)
    _plr_b = _truthy_light(_plr)
    if _pll_b is not None:
        d.parking_light_left = _pll_b
    if _plr_b is not None:
        d.parking_light_right = _plr_b
    # v2.17.5 — parkinglightstate.is_set: some dialects send only this flag and
    # not the per-side lights above (mirrors the parking_brake.is_set precedent).
    # "true"/"set" = a parking light is on.
    _pls = first("parkinglightstate.is_set", "parkinglightstate_is_set")
    if _pls is not None and d.parking_light is None:
        d.parking_light = str(_pls).strip().lower() in ("true", "1", "set")
    if (_pll_b is not None or _plr_b is not None) and d.parking_light is None:
        d.parking_light = bool(_pll_b) or bool(_plr_b)

    # Capture timestamp → last_seen_at. epoch-seconds→ISO-8601 UTC; ISO
    # passthrough. (_dataset_captured_ts already reads these for freshness —
    # surfacing is additive.)
    # v2.18.0 — the dotted spellings are listed alongside the bare ones. The
    # walker emits BOTH for a nested field, and first() only reclaims the
    # spellings it was told about: with bare-only names the dotted twin was
    # never marked used, so it resurfaced as a "new field" on every single
    # poll. That is what put profile_state_report.car_captured_time in front
    # of a reporter (#790) for a field we have read since v2.15.1.
    _cap = first(
        "car_captured_utc_timestamp", "car_captured_time", "instrument_cluster_time",
        "profile_state_report.car_captured_utc_timestamp",
        "profile_state_report.car_captured_time",
        "profile_state_report.instrument_cluster_time",
    )
    if _cap is not None and d.last_seen_at is None:
        cap_iso = _epoch_or_iso(_cap)
        # #529 step 2: never advance last_seen_at PAST the snapshot the surfaced
        # odometer actually came from. If the newest snapshot re-reported a
        # capture time but NOT the odometer, the odometer is genuinely older;
        # letting last_seen run ahead of it lets HA infer movement ("odometer
        # changed AND last_seen advanced") that never happened. Cap last_seen to
        # the odometer's resolved capture ts whenever the latter is older. We
        # only know the odometer's ts from field_ts (the _walk_fields out-param);
        # without it we fall back to the raw capture (pre-#529 behaviour).
        if field_ts and d.odometer_km is not None:
            odo_ts = next(
                (field_ts[k] for k in ("mileage.value", "mileage", "odometer",
                                       "totalMileage") if k in field_ts),
                None,
            )
            cap_ts = _parse_ts(_cap)
            if odo_ts is not None and cap_ts is not None and odo_ts < cap_ts:
                capped = _epoch_or_iso(str(odo_ts))
                if capped is not None:
                    cap_iso = capped
        d.last_seen_at = cap_iso

    # parking_brake.is_set → parking_brake_engaged (shared field).
    _pb = first("parking_brake.is_set", "parking_brake_is_set", "parking_brake")
    if _pb is not None:
        d.parking_brake_engaged = str(_pb).lower() in ("true", "1", "set")

    # bare `open` → sunroof: LOW confidence (3 dict definitions). Per the plan,
    # leave to raw_unmapped_fields until live-test; intentionally NOT mapped.

    # ── EU NEW fields ───────────────────────────────────────────────────────
    # #609 (CUPRA Tavascan) — the dict's CANONICAL name for these two enums is
    # the report-qualified form (dict UUIDs 0ba7abe4 / 1581d30c:
    # charging_state_report.charging_scenario / .immediate_action_state), so a
    # car that ships the flat dict-name key surfaced it unmapped. Add the dotted
    # alias FIRST (mirrors the charge_mode pattern above) so both the report-
    # shaped and bare-leaf spellings resolve onto the same existing entity.
    _cscn = first("charging_state_report.charging_scenario",
                  "charging_scenario", "chargingScenario")
    if _cscn is not None:
        d.charging_scenario = _shorten_enum(_cscn)

    _icas = first("charging_state_report.immediate_action_state",
                  "immediate_charge_action_state", "immediate_action_state")
    if _icas is not None:
        d.immediate_charge_action_state = _shorten_enum(_icas)

    _pcr = first("profile_charge_reason", "charge_reason")
    if _pcr is not None:
        d.profile_charge_reason = _shorten_enum(_pcr)

    # NOTE: charge_session_energy_kwh is already populated earlier from the real
    # dict key battery_state_report.charge_energy (with a >=0 guard). The block
    # that previously sat here used GUESSED names (charge_session_energy /
    # charge_session_energy_kwh) that never appear in the EU data dictionary, so
    # it never fired and only risked clobbering the real value — removed.

    _rcb = _dur_to_min(first(
        "battery_state_report.remaining_charging_time_bulk",
        "remaining_charging_time_bulk",
    ))
    if _rcb is not None:
        d.remaining_charge_time_bulk_min = _rcb

    _ostate = first("mileage.state")
    if _ostate is not None:
        d.odometer_state = _shorten_enum(_ostate)

    _ict = first(
        "instrument_cluster_time", "profile_state_report.instrument_cluster_time",
    )
    if _ict is not None:
        d.instrument_cluster_time = _ict

    # #604 Scout — battery_level_HV.state: dict-confirmed enum ("The enum value
    # of battery level HV state"); dict lists NO value tokens, so it's LOW
    # confidence (ships disabled-by-default) and _shorten_enum passes any
    # unknown-prefix value through unchanged. Distinct from battery_level_HV.value
    # (the charger-dialect SoC fallback above) — this is the report's own status
    # flag. Doubled-key form (battery_level_HV.battery_level_HV.state) mirrors the
    # dict's nested variant, same as the .value block.
    _hvbs = first("battery_level_HV.state",
                  "battery_level_HV.battery_level_HV.state")
    if _hvbs is not None:
        d.hv_battery_state = _shorten_enum(_hvbs)

    # data_error_detail — join non-empty of error_code/number/description,
    # filtering "#0"/"0" "no error" sentinels.
    _err_parts: list[str] = []
    for _en in ("error_code", "error_number", "error_description"):
        _ev = first(_en)
        if _ev is None:
            continue
        _evs = str(_ev).strip()
        if _evs and _evs not in ("#0", "0"):
            _err_parts.append(_evs)
    if _err_parts:
        d.data_error_detail = " ".join(_err_parts)

    # last_report_id — change-detector metadata. Surfaced as a diagnostic but
    # NOT consumed: per the b14 no-suppress policy (and the plan's "kept
    # Scout-visible" note for message_id/dataset_key) it must still appear in
    # raw_unmapped_fields, so we peek without marking it used.
    _rid = fields.get("message_id")
    if _rid is not None:
        d.last_report_id = _rid

    # Real EU data-dictionary keys (the previous first() names were guessed and
    # never matched, so these never populated). Dictionary unit is null for both,
    # so we store the raw numeric value as-is (no scale applied) until a live
    # payload confirms the unit; comment kept as a flag for that follow-up.
    _clim_e = _to_float(first(
        "additional_consumptions.interior_climatization_consumption"))
    if _clim_e is not None:
        d.climate_energy_consumption_kwh = _clim_e  # unit unconfirmed (dict: null)
    _res_e = _to_float(first("additional_consumptions.residual_consumption"))
    if _res_e is not None:
        d.residual_energy_consumption_kwh = _res_e  # unit unconfirmed (dict: null)
    # v2.15.7 (#547-#581 Scout) — battery-climatization energy. Dict UUID
    # 482e54c4 (type=number, unit=null, cluster "Climatisation and Heating"):
    # "Energy consumption for battery climtization for a given driving mode
    # (non-comfort-related)". Sibling of the interior/residual consumption keys
    # above; stored raw (no scale) until a live payload confirms the unit.
    _bat_clim_e = _to_float(first(
        "additional_consumptions.battery_climatization_consumption",
        "battery_climatization_consumption"))
    if _bat_clim_e is not None:
        d.battery_climatization_energy_kwh = _bat_clim_e  # unit unconfirmed (dict: null)

    _st_rec = _to_float(first("short_term_data_average_recuperation"))
    if _st_rec is not None:
        d.last_trip_avg_recuperation_kwh_100km = _st_rec / 10
    _lt_rec = _to_float(first("long_term_data_average_recuperation"))
    if _lt_rec is not None:
        d.lifetime_avg_recuperation_kwh_100km = _lt_rec / 10

    # dataset_key — LOW confidence, disabled-by-default. ZIP-envelope
    # metadata that the plan flags as possibly redundant with the message_id
    # change-detector; like last_report_id it is surfaced but NOT consumed, so
    # the bare key stays Scout-visible (b14 no-suppress policy).
    _dkey = fields.get("Data.key") or fields.get("dataset_key") or fields.get("key")
    if _dkey is not None:
        d.dataset_key = str(_dkey)

    # ── v2.15.2 — EU Data Act portal "charger detail" fields (#513 Scout) ────
    # All additive, guarded, EU-Data-Act-dialect only.
    _eps = first("external_power_supply_state")
    if _eps is not None:
        d.external_power_supply_state = _shorten_enum(_eps)

    _eflow = first("energy_flow")
    if _eflow is not None:
        d.energy_flow_active = str(_eflow).lower() in ("on", "true", "1", "active")

    _creason = first("charging_reason_trigger")
    if _creason is not None:
        d.charging_reason = _shorten_enum(_creason)

    # charging_state_error_code — "0"/"0.0"/"#0" are the "no error" sentinels → None.
    # v2.15.3: normalise numerically so a float-typed "0.0" is also dropped.
    # v2.15.4 (#521): charging_state_report.error_code is the nested EU-portal
    # alias for the same code (dict-confirmed type=number) — added so the report-
    # shaped payload populates the same sensor; sentinel-drop still applies.
    _cerr = first("charging_state_error_code", "charging_state_report.error_code")
    if _cerr is not None:
        _cerrs = str(_cerr).strip()
        _cerrn = _to_float(_cerrs)
        if _cerrs and _cerrs != "#0" and _cerrn != 0:
            d.charging_error_code = _cerrs

    _rtts = first("remaining_charging_time_target_soc")
    if _rtts is not None:
        d.remaining_time_target_soc = _rtts

    _led_c = first("led_color")
    if _led_c is not None:
        d.charge_led_color = _led_c

    _led_s = first("led_state")
    if _led_s is not None:
        d.charge_led_pattern = _led_s

    # ── v2.15.3 — EU Data Act portal new fields (#465/#514/#515/#516) ────────
    # All additive, guarded, EU-Data-Act-dialect only; mirrors the v2.15.1/2
    # style (first(), _shorten_enum, _ENUM_PREFIXES, sentinel drops).

    # A. Charging settings (settings.*  +  the singular setting.bcam_activation).
    _csel = first("settings.charge_mode_selection", "charge_mode_selection")
    if _csel is not None:
        d.charge_mode_selection = _shorten_enum(_csel)
    _mca = first("settings.max_charge_current_ac", "max_charge_current_ac")
    if _mca is not None:
        d.max_charge_current_ac = _shorten_enum(_mca)
    _aua = first("settings.auto_unlock_ac", "auto_unlock_ac")
    if _aua is not None:
        d.auto_unlock_charge_port = _shorten_enum(_aua)
    # setting.bcam_activation (singular) → battery_care_mode_active bool.
    _bcam_act = first("setting.bcam_activation", "bcam_activation")
    if _bcam_act is not None:
        d.battery_care_mode_active = (
            str(_bcam_act).upper().endswith("ACTIVATED")
            and "DEACTIVATED" not in str(_bcam_act).upper()
        )
    # charge_bulk_threshold (% SoC at which charging slows bulk→trickle).
    _cbt = _to_int(first("battery_state_report.charge_bulk_threshold",
                         "charge_bulk_threshold"))
    if _cbt is not None:
        d.charge_bulk_threshold_pct = _cbt
    # charge_rate_unit — LOW, disabled-by-default companion enum for the rate.
    _cru = first("battery_state_report.charge_rate_unit", "charge_rate_unit")
    if _cru is not None:
        d.charge_rate_unit = _shorten_enum(_cru)

    # B. Door / closure SAFE-state (2=safe 3=unsafe — INVERSE polarity of the
    # locked_state 2=locked/3=unlocked block above; do NOT reuse those helpers).
    # NOTE (polarity): the 2=safe/3=unsafe mapping is documented in the dict only
    # for the three door safe_state_* fields (front_right / rear_left /
    # rear_right). The bonnet + tailgate safe-state polarity is INFERRED from the
    # same enum family (and from the locked_state block's bonnet entry); if a live
    # payload shows otherwise these two should be re-verified.
    _bonnet_lock = _to_int(first("locked_state_front_engine_bonnet"))
    if _bonnet_lock in (2, 3):
        d.bonnet_locked = _bonnet_lock == 2
    # Rolled-up "all present closures safe" aggregate (2=safe). Only dict-confirmed
    # safe_state_* fields (NO safe_state_front_left_door — it is absent from the
    # spec; the documented set is front_right/rear_left/rear_right + bonnet/tailgate).
    _safe_vals = [
        _to_int(first(_n)) for _n in (
            "safe_state_front_engine_bonnet",
            "safe_state_front_right_door",
            "safe_state_rear_left_door", "safe_state_rear_right_door",
            "safe_state_tailgate",
        )
    ]
    _safe_present = [v for v in _safe_vals if v in (2, 3)]
    if _safe_present:
        d.closures_secured = all(v == 2 for v in _safe_present)

    # state_* closures (2=open 3=closed; 0=unsupported/1=invalid → ignore).
    _sunroof_vals = [
        _to_int(first("state_sunroof_motor_hood_1")),
        _to_int(first("state_sunroof_motor_hood_3")),
    ]
    _sunroof_present = [v for v in _sunroof_vals if v in (2, 3)]
    if _sunroof_present and d.sunroof_open is None:
        d.sunroof_open = any(v == 2 for v in _sunroof_present)
    # v2.15.5 (#544) — sunroof motor hood 1 POSITION (%; 0=closed). Distinct
    # from the open/closed STATE above. Dict type=number, unit "%". first()
    # drops the uint16 65535 "no reading" sentinel; valid 0-100 survives.
    # v2.17.5 — hood_3 is the same sunroof-position % on cars that report only
    # that slot (we already merge hood_3 STATE into sunroof_open above), so fold
    # it in as a fallback rather than leaving the position sensor empty.
    _sunroof_pos = _to_int(first(
        "position_sunroof_motor_hood_1", "position_sunroof_motor_hood_3",
    ))
    if _sunroof_pos is not None and d.sunroof_position_pct is None:
        d.sunroof_position_pct = _sunroof_pos
    _svc_hatch = _to_int(first("state_service_hatch"))
    if _svc_hatch in (2, 3):
        d.service_hatch_open = _svc_hatch == 2
    _spoiler = _to_int(first("state_spoiler"))
    if _spoiler in (2, 3):
        d.spoiler_open = _spoiler == 2
    # v2.15.11 (#614) — spoiler POSITION (%; 0=closed). Distinct from the
    # open/closed STATE above. Dict type=number, unit "%". first() drops the
    # uint16 65535 "no reading" sentinel; a valid 0-100 survives. Mirrors the
    # sunroof_position_pct parse.
    _spoiler_pos = _to_int(first("position_spoiler"))
    if _spoiler_pos is not None and d.spoiler_position_pct is None:
        d.spoiler_position_pct = _spoiler_pos

    # C. Trip odometer endpoints (km).
    _lt_dist = _to_int(first("long_term_data_mileage"))
    if _lt_dist is not None:
        d.lifetime_trip_distance_km = _lt_dist
    _lt_start = _to_int(first("long_term_data_start_mileage"))
    if _lt_start is not None:
        d.lifetime_trip_start_odometer_km = _lt_start
    _st_start = _to_int(first("short_term_data_start_mileage"))
    if _st_start is not None:
        d.last_trip_start_odometer_km = _st_start

    # D. Fuel / fluids / SCR.
    _oil_l = _to_float(first("oil_level_total_max"))
    if _oil_l is not None:
        d.oil_level_liters = _oil_l
    _oil_add = _to_float(first("oil_level_additional_oil_level"))
    if _oil_add is not None:
        d.oil_level_additional_pct = _oil_add
    _oil_dip = _to_int(first("oil_level_dipstick_indicator_function"))
    if _oil_dip is not None:
        d.oil_dipstick_active = _oil_dip == 1
    # v2.17.5 — oil_level_min_warning (dict 6933): a boolean LOW-oil-level lamp
    # (0=OK, 1=low). Distinct from the oil-CHANGE service lamp (warning_oil).
    # Feeds the existing oil_level_warning binary_sensor, until now only BFF-fed,
    # so VW combustion cars on the portal get oil-level-warning coverage too.
    _oil_w = first("oil_level_min_warning")
    if _oil_w is not None and d.oil_level_warning is None:
        d.oil_level_warning = str(_oil_w).strip().lower() in ("1", "true")
    # v2.18.1 — Scout #794 (@loungelizard2018): the raw oil-level STATUS string
    # the 15-min feed ships (e.g. "ok"/"minWarning"). pct/warning/liters are read
    # above; map the raw enum into the existing diagnostic ``oil_level_status``
    # field so it is CONSUMED, not surfaced as an unmapped Scout row. Raw string
    # only — no guessing the enum→warning semantics (warning is fed separately).
    _oil_s = first("oil_level_status")
    if _oil_s is not None and d.oil_level_status is None:
        d.oil_level_status = str(_oil_s).strip()
    # scr_range — AdBlue/SCR range (km). Empty string guarded by _to_int.
    _scr = _to_int(first("scr_range"))
    if _scr is not None and d.adblue_range_km is None:
        d.adblue_range_km = _scr
    # fuel_level__accuracy (double underscore): 0=measured 1=calculated.
    _fla = _to_int(first("fuel_level__accuracy"))
    if _fla is not None:
        d.fuel_level_estimated = _fla == 1

    # E. Tyres — pressure DELTA vs target. The _FIELD_SENTINELS rule drops the
    # 0/1 (unsupported/invalid) sentinels in first()/_is_sentinel at map time, so
    # only a genuine >1 reading survives. Map the full corner+spare set defensively.
    for _attr, _name in (
        ("tyre_pressure_diff_fl", "tyre_pressure_differential_front_left"),
        ("tyre_pressure_diff_fr", "tyre_pressure_differential_front_right"),
        ("tyre_pressure_diff_rl", "tyre_pressure_differential_rear_left"),
        ("tyre_pressure_diff_rr", "tyre_pressure_differential_rear_right"),
        ("tyre_pressure_diff_spare", "tyre_pressure_differential_spare_tyre"),
    ):
        _tpd = _to_int(first(_name))
        if _tpd is not None:
            setattr(d, _attr, _tpd)

    # E'. Tyres — ACTUAL per-wheel pressure (#528 front pair, #538 rear+spare).
    # Same 0/1 sentinel rule as the diff family (dict: unsupported 0 / invalid 1
    # / valid int), dropped in first()/_is_sentinel via the
    # "tyre_pressure_actual" _FIELD_SENTINELS entry, so a surviving value is a
    # genuine reading. #538 (RichardL6) reported the rear pair + spare.
    for _attr, _name in (
        ("tyre_pressure_actual_fl", "tyre_pressure_actual_front_left"),
        ("tyre_pressure_actual_fr", "tyre_pressure_actual_front_right"),
        ("tyre_pressure_actual_rl", "tyre_pressure_actual_rear_left"),
        ("tyre_pressure_actual_rr", "tyre_pressure_actual_rear_right"),
        ("tyre_pressure_actual_spare", "tyre_pressure_actual_spare_tyre"),
    ):
        _tpa = _to_int(first(_name))
        if _tpa is not None:
            setattr(d, _attr, _tpa)

    # E''. Tyres — REQUIRED/target per-wheel pressure (#538). Same 0/1 sentinel
    # rule via the "tyre_pressure_required" _FIELD_SENTINELS entry. Unit
    # ("10kPA / Bar / PSI/ kPA") is ambiguous → unitless diagnostic, no
    # device_class, disabled-by-default (mirrors the actual family).
    for _attr, _name in (
        ("tyre_pressure_required_fl", "tyre_pressure_required_front_left"),
        ("tyre_pressure_required_fr", "tyre_pressure_required_front_right"),
        ("tyre_pressure_required_rl", "tyre_pressure_required_rear_left"),
        ("tyre_pressure_required_rr", "tyre_pressure_required_rear_right"),
        ("tyre_pressure_required_spare", "tyre_pressure_required_spare_tyre"),
    ):
        _tpr = _to_int(first(_name))
        if _tpr is not None:
            setattr(d, _attr, _tpr)

    # F. Lights / energy / misc.
    # parking_lights (plural enum): 0=unsup 1=invalid 2=off 3=left 4=right 5=both.
    _plights = _to_int(first("parking_lights"))
    if _plights is not None and _plights >= 2:
        d.parking_lights_state = {
            2: "off", 3: "left", 4: "right", 5: "both",
        }.get(_plights)
    # bem_level — auxiliary/12V battery energy management level (%).
    _bem = _to_int(first("bem_level"))
    if _bem is not None:
        d.aux_battery_energy_pct = _bem
    # active_warnings_in_instrument_cluster_feff_filtered — RAW hex/interpreted
    # bitmask only. Do NOT attempt an enum decode we can't verify; surface the
    # raw value as a disabled-by-default diagnostic.
    _warn = first("active_warnings_in_instrument_cluster_feff_filtered")
    if _warn is not None:
        d.dashboard_warnings_raw = str(_warn)
    # climate_error_code / window_heating_error_code — drop "0"/"#0" like the
    # existing charging_state_error_code pattern.
    _clim_err = first("climate_error_code")
    if _clim_err is not None:
        _ces = str(_clim_err).strip()
        if _ces and _ces != "#0" and _to_float(_ces) != 0:
            d.climate_error_code = _ces
    _wh_err = first("window_heating_error_code")
    if _wh_err is not None:
        _whs = str(_wh_err).strip()
        if _whs and _whs != "#0" and _to_float(_whs) != 0:
            d.window_heating_error_code = _whs

    # ── v2.15.4 — EU Data Act portal new fields (#521/#522 Scout) ────────────
    # All additive, guarded, EU-Data-Act-dialect only; same style as 2.15.1-3.

    # Next-charging-timer info: estimated start/finish are dict-confirmed
    # type=string ISO timestamps (the service sends UTC) → ISO passthrough via
    # _epoch_or_iso. target_reachability is a dict-confirmed enum (shortened).
    _ncs = first(
        "profile_state_report.next_charging_timer_information.estimated_start_time",
        "next_charging_timer_information.estimated_start_time",
        # v2.15.4 overreport fix: bare leaf — the realistic data-point shape emits
        # the bare key; the leaf name is UNIQUE so this alias is safe. Listed here
        # so synonym-collapse also reclaims it from raw_unmapped.
        "estimated_start_time",
    )
    if _ncs is not None and d.next_charge_timer_start_at is None:
        d.next_charge_timer_start_at = _epoch_or_iso(_ncs)
    _ncf = first(
        "profile_state_report.next_charging_timer_information.estimated_finish_time",
        "next_charging_timer_information.estimated_finish_time",
        "estimated_finish_time",  # v2.15.4: unique bare leaf — safe alias.
    )
    if _ncf is not None and d.next_charge_timer_finish_at is None:
        d.next_charge_timer_finish_at = _epoch_or_iso(_ncf)
    _ncr = first(
        "profile_state_report.next_charging_timer_information.target_reachability",
        "next_charging_timer_information.target_reachability",
        "target_reachability",  # v2.15.4: unique bare leaf — safe alias.
    )
    if _ncr is not None and d.next_charge_target_reachability is None:
        # Dict tokens (target_reachability desc): TARGET_REACHABILITY_{INVALID,
        # CALCULATING,REACHABLE,NOT_REACHABLE}. INVALID/CALCULATING mean the
        # timer is uninitialized/uncomputed — surface them as unknown (None)
        # instead of a stale literal state. Keep REACHABLE / NOT_REACHABLE.
        _ncr_short = _shorten_enum(_ncr)
        if isinstance(_ncr_short, str) and _ncr_short.upper() in (
            "INVALID", "CALCULATING"
        ):
            _ncr_short = None
        if _ncr_short is not None:
            d.next_charge_target_reachability = _ncr_short
    # nextChargingTimer = which timer slot (1-15) is queued next. Dict-confirmed
    # type=number, unit=null ("Profile1: 1,2,3 ... Profile5: 13,14,15"). A bare
    # slot index → diagnostic NUMBER. _walk_fields keys data-point nodes by the
    # BARE dataFieldName (nextChargingTimer) plus a container-qualified twin;
    # list both the dotted forms and the bare leaf so synonym-collapse reclaims
    # the qualified twin and the realistic data-point shape resolves.
    _nctn = first(
        "profile_state_report.next_charging_timer_information.nextChargingTimer",
        "next_charging_timer_information.nextChargingTimer",
        "nextChargingTimer",
    )
    if _nctn is not None and d.next_charge_timer_number is None:
        d.next_charge_timer_number = _to_int(_nctn)

    # Slope consumption (ascent/descent) — dict-confirmed type=number,
    # unit=null (no scale applied; raw physical_value). Gated on the sibling
    # value_type being valid, exactly like the energy_contents pattern above.
    _asc_slope = _to_float(first(
        "slope_consumption_values.ascent_slope_consumption.physical_value",
        "ascent_slope_consumption.physical_value",
    ))
    if _asc_slope is not None and _value_type_ok(
        "slope_consumption_values.ascent_slope_consumption.value_type",
        "ascent_slope_consumption.value_type",
    ):
        d.ascent_slope_consumption = _asc_slope
    _desc_slope = _to_float(first(
        "slope_consumption_values.descent_slope_consumption.physical_value",
        "descent_slope_consumption.physical_value",
    ))
    if _desc_slope is not None and _value_type_ok(
        "slope_consumption_values.descent_slope_consumption.value_type",
        "descent_slope_consumption.value_type",
    ):
        d.descent_slope_consumption = _desc_slope

    # report_type — dict-confirmed enum metadata describing which report this
    # poll's payload is. (The dict lists NO values for report_type, so a token
    # like "REPORT_TYPE_CONSUMPTION_VALUES" is illustrative/unconfirmed; code
    # deliberately adds no prefix and passes the raw value through.)
    # LOW value (metadata, not telemetry) → disabled-by-default diagnostic, but
    # mapped (never Scout-suppressed). Shortened for display.
    _rtype = first("report_type")
    if _rtype is not None and d.report_type is None:
        d.report_type = _shorten_enum(_rtype)

    # result_app / result_master — generic delivery/sync "result" status enums
    # for the app-data and master-data channels. The dict lists NO values for
    # either (type=enum, unit=null), so — like report_type — code adds no
    # speculative prefix and passes the raw token through _shorten_enum for
    # display. LOW value (metadata, not telemetry) → disabled-by-default
    # diagnostic, but mapped (never Scout-suppressed).
    _rapp = first("result_app")
    if _rapp is not None and d.result_app is None:
        d.result_app = _shorten_enum(_rapp)
    _rmaster = first("result_master")
    if _rmaster is not None and d.result_master is None:
        d.result_master = _shorten_enum(_rmaster)

    # v2.15.5 — update_reason: why the report was sent to the backend
    # (UPDATE_REASON_* enum). dict-confirmed values, so the UPDATE_REASON_
    # prefix is in _ENUM_PREFIXES and _shorten_enum strips it for display
    # (UPDATE_REASON_CHARGING → CHARGING). LOW value (metadata, not telemetry)
    # → disabled-by-default diagnostic, but mapped (never Scout-suppressed).
    _ureason = first("update_reason")
    if _ureason is not None and d.update_reason is None:
        d.update_reason = _shorten_enum(_ureason)

    # ── v2.15.4 (#523) — EU Data Act portal new fields ───────────────────────
    # All additive, guarded, EU-Data-Act-dialect only.
    # Climatisation settings — dict type=string, Climatisation cluster. The
    # values are on/off/enabled-style strings ("Is short conditioning enabled",
    # "Is glass surface heating active", "Is extended conditioning in front
    # left/right zone enabled") → coerce to bool. No enum list in the dict, so
    # accept the common truthy tokens.
    def _setting_bool(raw: str | None) -> bool | None:
        # v2.15.4 — dict lists these as string with no enum; map known truthy/
        # falsy tokens, leave anything unrecognized (e.g. invalid/unsupported) as
        # None rather than a hard False, until a live payload pins the vocab.
        if raw is None:
            return None
        v = str(raw).strip().lower()
        if v in ("true", "1", "on", "enabled", "active", "activated", "yes"):
            return True
        if v in ("false", "0", "off", "disabled", "inactive", "deactivated", "no"):
            return False
        return None

    _cau = _setting_bool(first("setting_climatisation_at_unlock"))
    if _cau is not None and d.climatisation_at_unlock is None:
        d.climatisation_at_unlock = _cau
    _mhe = _setting_bool(first("setting_mirror_heating_enabled"))
    if _mhe is not None and d.mirror_heating_enabled is None:
        d.mirror_heating_enabled = _mhe
    _zfl = _setting_bool(first("setting_zone_enabled_front_left"))
    if _zfl is not None and d.climate_zone_front_left_enabled is None:
        d.climate_zone_front_left_enabled = _zfl
    _zfr = _setting_bool(first("setting_zone_enabled_front_right"))
    if _zfr is not None and d.climate_zone_front_right_enabled is None:
        d.climate_zone_front_right_enabled = _zfr
    # v2.17.5 — the portal ships rear zones too (setting_zone_enabled_rear_*) but
    # only the front pair was aliased. Rear targets the BFF-shared
    # climate_zone_rear_left/right attrs (there is no _enabled twin for rear).
    _zrl = _setting_bool(first("setting_zone_enabled_rear_left"))
    if _zrl is not None and d.climate_zone_rear_left is None:
        d.climate_zone_rear_left = _zrl
    _zrr = _setting_bool(first("setting_zone_enabled_rear_right"))
    if _zrr is not None and d.climate_zone_rear_right is None:
        d.climate_zone_rear_right = _zrr
    # v2.17.5 — LIVE 'active' status twins of the *_enabled settings above
    # (state_mirror_heating_active / state_zone_active_*). active != enabled.
    _mha = _setting_bool(first("state_mirror_heating_active"))
    if _mha is not None and d.mirror_heating_active is None:
        d.mirror_heating_active = _mha
    _zafl = _setting_bool(first("state_zone_active_front_left"))
    if _zafl is not None and d.climate_zone_active_front_left is None:
        d.climate_zone_active_front_left = _zafl
    _zafr = _setting_bool(first("state_zone_active_front_right"))
    if _zafr is not None and d.climate_zone_active_front_right is None:
        d.climate_zone_active_front_right = _zafr
    _zarl = _setting_bool(first("state_zone_active_rear_left"))
    if _zarl is not None and d.climate_zone_active_rear_left is None:
        d.climate_zone_active_rear_left = _zarl
    _zarr = _setting_bool(first("state_zone_active_rear_right"))
    if _zarr is not None and d.climate_zone_active_rear_right is None:
        d.climate_zone_active_rear_right = _zarr

    # start_stop_action — dict type=string, "Indicates the action related to
    # charging". No dict-listed enum values → no confirmed prefix; _shorten_enum
    # passes unprefixed values through unchanged (so it is safe to apply).
    _ssa = first("start_stop_action")
    if _ssa is not None and d.start_stop_action is None:
        d.start_stop_action = _shorten_enum(_ssa)

    # start_stop_modification — dict type=string, "Contains the detail related
    # to start stop modification". Distinct field from start_stop_action; no
    # dict-listed enum → _shorten_enum passes unprefixed values through.
    _ssm = first("start_stop_modification")
    if _ssm is not None and d.start_stop_modification is None:
        d.start_stop_modification = _shorten_enum(_ssm)

    # b1/B3 — derive drivetrain from the data actually present (fixes the
    # #37 class: an EV like the e-up! showing only combustion entities, or a
    # PHEV like the Golf GTE flagged as neither). Additive: only set flags True
    # on a clear signal; never force False, so other channels can still inform it.
    has_e = (d.battery_soc is not None or d.electric_range_km is not None
             or d.charging_state is not None)
    has_c = d.fuel_level is not None or d.combustion_range_km is not None
    if has_e:
        d.has_battery = True
    if has_c:
        d.has_combustion = True
    if has_e and has_c:
        d.is_hybrid = True
    elif has_e:
        d.is_electric = True

    # a12 — surface the long tail: portal fields we did NOT consume this poll.
    # Debug-only, zero behaviour change. Feeds the Vehicle Data Scout and tells
    # us exactly which dictionary entries to add next, from REAL payloads —
    # beats a hand-maintained static dict that silently drops unknown fields.
    unmapped = sorted(k for k in fields if k not in used)
    if unmapped:
        _LOGGER.debug(
            "EU Data Act: %d unmapped portal field(s): %s",
            len(unmapped), ", ".join(unmapped[:40]),
        )
        # b1/A6 — raw field discovery (same detection, both worlds): expose the
        # unmapped fields + their REAL values so the user can see everything the
        # backend sent, on one disabled diagnostic sensor. Capped to keep the
        # attribute payload sane; the debug log above already records the count.
        # PRIVACY (#718 et al.): the portal dataset carries the account UUID
        # (user_id) and the VIN as data fields. They are NOT suppressed from
        # discovery — the field NAMES stay so the Scout still surfaces them — but
        # their VALUES are redacted here, because this diagnostic attribute
        # otherwise exposes the REAL account UUID + full VIN (the Scout issue
        # itself already masks both). Match on the leaf name so both the bare
        # (`vin`) and container-qualified (`eu_data_act.vin`) spellings redact.
        d.raw_unmapped_fields = {
            k: ("<redacted>" if k.rsplit(".", 1)[-1] in ("user_id", "vin")
                else str(fields[k]))
            for k in unmapped[:_RAW_FIELD_CAP]
        }
        if len(unmapped) > _RAW_FIELD_CAP:
            _LOGGER.debug(
                "EU Data Act: raw-discovery capped at %d of %d fields",
                _RAW_FIELD_CAP, len(unmapped),
            )

    return d


# ── The connector ──────────────────────────────────────────────────────────

class EUDataActConnector:
    """Cookie-authenticated VW EU Data Act portal client.

    Lifecycle: ``await login(email, password)`` once (populates the shared
    aiohttp session's cookie jar), then ``await get_vehicle_data(vin)`` per
    poll. ``login`` is re-invoked automatically by the caller on 401/403.
    """

    def __init__(
        self,
        session: ClientSession,
        *,
        brand: str = "volkswagen",
        country: str = "de",
        language: str = "de",
        access_token: str | None = None,
    ) -> None:
        self._session = session
        cfg = _EUDA_BRANDS.get(brand.lower())
        if cfg is None:
            # Unknown brand → VW client with a brand-derived state suffix.
            # Handshake-valid; account-level coverage lands in a later release.
            cfg = {**_EUDA_VW, "state_brand": brand.upper()}
            _LOGGER.debug(
                "EU Data Act: no verified portal config for brand %r — "
                "falling back to the VW client with state suffix %s",
                brand, cfg["state_brand"],
            )
        self._client_id = cfg["client_id"]
        self._scope = cfg["scope"]
        self._state = f"{country}__{language}__{cfg['state_brand']}"
        self.logged_in = False
        # v2.12.2 — last per-poll data outcome, read by the coordinator to
        # raise/clear the "no vehicle data" repair issue:
        #   ""          → data mapped successfully
        #   "no_request" → metadata 404/500 / no data-request set up (or a
        #                  VW-side portal outage at the metadata layer)
        #   "empty"      → request exists but the portal delivered no dataset
        self.last_no_data_reason: str = ""
        # v2.13.0 — device-code/QR Bearer mode. When set, every proxy_api call
        # authenticates via ``Authorization: Bearer <token>`` (the device-grant
        # access_token, aud=portal client) instead of the cookie-scrape session,
        # and login() becomes a no-op. None → legacy cookie mode (unchanged).
        self._bearer: str | None = access_token

    def set_bearer(self, token: str) -> None:
        """Inject / refresh the device-grant access_token for Bearer mode.

        Switches the connector to header auth and marks it logged-in without a
        cookie-scrape login(). Called on auth and after every token refresh so
        the long-lived connector never carries a stale bearer (which would 401
        mid-poll)."""
        self._bearer = token
        self.logged_in = True

    @staticmethod
    def _is_consent_landing(landing_url: str, landing_html: str) -> bool:
        """True if the post-credential landing is the generic consent grant page.

        Mirrors the classifier's detection (URL family + templateModel
        pageType=='consent'), but excludes the MARKETING-consent interstitial:
        a marketing opt-in is a deliberate user choice we must NOT silently
        accept, so it stays on the MarketingConsentError path. The generic OAuth
        grant page (#527) is the only one we auto-accept here.
        """
        url_l = landing_url.lower()
        if any(m in url_l for m in _CONSENT_MARKERS):
            return False  # marketing opt-in → never auto-accept
        model = _extract_template_model(landing_html) or {}
        page_type = str(
            model.get("template") or model.get("templateName") or ""
        )
        blob = f"{url_l}\n{landing_html.lower()}"
        return _is_generic_consent_page(landing_url, page_type, blob)

    async def _accept_consent_page(
        self, consent_url: str, consent_html: str
    ) -> tuple[str, str, int] | None:
        """Scrape + POST the consent grant form to ACCEPT it (#527).

        v2.15.7 — REWRITTEN per RaimondB's verified end-to-end diagnosis:

        1. The consent <form> action is EMPTY → the browser POSTs back to the
           CURRENT consent URL **including its query string** (hmac /
           relayState / callback / scopes), which the grant endpoint validates.
           ``_resolve_action`` would ``split('?', 1)[0]`` and discard the query
           (correct for the credential step, FATAL here → HTTP 400
           generalErrorBranded). So we ``urljoin`` against the FULL consent URL
           and, when the action is empty, POST straight back to ``consent_url``
           with the query intact.
        2. The form emits ``consentedScopes`` ONCE PER granted scope. A
           dict-based parse keeps only the last → drops mandatory ``profile``.
           ``_consent_form_fields`` returns an ordered list of pairs so the
           repeats survive (aiohttp form-encodes a list of tuples preserving
           every entry). It also means we do NOT inject the templateModel hmac
           that ``_login_fields`` would — the consent form has no hmac BODY
           field (hmac is the query param).
        3. The Allow button has NO name; Cancel is ``name='cancel'
           value='true'``. Buttons are excluded by the parser, so the accept
           payload is the hidden inputs ONLY.

        Returns the new ``(landing_url, landing_html, status)`` after the
        accept POST + redirect-follow, or ``None`` when the form could not be
        parsed (no usable fields) so the caller falls through to the typed
        non-credential classification (no silent loop — we accept once).
        """
        pairs, action = _consent_form_fields(consent_html)
        # Gate on the consent form's own anti-CSRF / scope fields. RaimondB's
        # form carried ``_csrf``; some variants carry ``consentedScopes``.
        names = {n for n, _ in pairs}
        if not ({"_csrf", "consentedScopes"} & names):
            _LOGGER.debug(
                "EU Data Act portal: consent page at %s carried no form "
                "fields — cannot auto-accept, leaving to classifier",
                _safe_url(consent_url),
            )
            return None
        # Empty action ⇒ POST to the FULL consent URL incl. query. Do NOT use
        # _resolve_action (it strips the query → 400 generalErrorBranded).
        accept_action = urljoin(consent_url, action) if action else consent_url
        try:
            async with self._session.post(
                accept_action, data=pairs,
                headers={"User-Agent": _USER_AGENT, "Referer": consent_url},
                allow_redirects=True, timeout=ClientTimeout(total=_TIMEOUT_S),
            ) as resp:
                new_landing = str(resp.url)
                new_html = await resp.text(errors="replace")
                new_status = resp.status
        except Exception as exc:  # noqa: BLE001 — best-effort accept
            _LOGGER.debug(
                "EU Data Act portal: consent accept POST failed (%s) — "
                "leaving to classifier", type(exc).__name__,
            )
            return None
        _LOGGER.debug(
            "EU Data Act portal: consent accepted → landing=%s status=%s",
            _safe_url(new_landing), new_status,
        )
        return new_landing, new_html, new_status

    async def login(self, email: str, password: str) -> None:
        """Run the OIDC code-flow login; portal backend sets cookies.

        v2.15.8 (#576/#578) — a transport-level timeout/disconnect during the
        login HTTP round-trips (the priming GET, the authorize GET, the
        identifier/credential POSTs) is a portal hiccup, NOT a credential
        failure. A raw ``TimeoutError``/``ClientConnectionError`` here used to
        propagate out of ``get_status`` and land in the Error Reporter as if it
        were our bug. We now re-raise it as ``UpstreamUnavailableError`` — the
        same typed "backend temporarily unavailable" the coordinator already
        treats as a transient no-data poll (and explicitly does NOT escalate to
        the Reporter; #438/#465). Genuine auth failures (bad password,
        consent-required, attestation, 4xx) are raised INSIDE ``_login_impl`` as
        ``AuthenticationError`` / ``PortalInteractionRequiredError`` subclasses,
        which are NOT caught here, so they surface unchanged.
        """
        try:
            await self._login_impl(email, password)
        except (TimeoutError, ClientConnectionError) as exc:
            # ONLY connection/timeouts map to transient. asyncio.TimeoutError is
            # an alias of the builtin TimeoutError on py3.11+, so it is covered.
            raise UpstreamUnavailableError(504, brand=self._state) from exc

    async def _login_impl(self, email: str, password: str) -> None:
        """OIDC code-flow login worker (see ``login`` for the transient wrap).

        v2.13.0 — in device-code Bearer mode (``self._bearer`` set) this is a
        no-op: the device-grant already minted the token, so there is no SPA
        scrape to run (this is what retires the #388/#393 fragility)."""
        if self._bearer:
            self.logged_in = True
            return
        headers = {"User-Agent": _USER_AGENT}

        # 0. Prime portal session cookies (AEM load-balancer state).
        try:
            async with self._session.get(
                f"{_PORTAL_BASE}/", headers=headers,
                timeout=ClientTimeout(total=_TIMEOUT_S),
            ):
                pass
        except Exception as exc:  # noqa: BLE001
            _LOGGER.debug("EU Data Act: priming GET failed (ignored): %s", exc)

        # 1. Start OIDC directly at the IDP (portal's own servlet 500s for
        #    non-browser clients). response_type=code; portal does the
        #    confidential exchange itself.
        authorize_params = {
            "client_id": self._client_id,
            "response_type": "code",
            "scope": self._scope,
            "state": self._state,
            "redirect_uri": _PORTAL_REDIRECT_URI,
            "prompt": "login",
        }
        async with self._session.get(
            _AUTHORIZE_URL, params=authorize_params, headers=headers,
            allow_redirects=True, timeout=ClientTimeout(total=_TIMEOUT_S),
        ) as resp:
            signin_url = str(resp.url)
            signin_html = await resp.text(errors="replace")

        # 2. POST email (identifier step).
        fields, action = _login_fields(signin_html)
        if "hmac" not in fields:
            raise AuthenticationError(
                "EU Data Act portal: could not parse the sign-in form "
                f"(fields: {sorted(fields)})"
            )
        fields["email"] = email
        identifier_action = _resolve_action(signin_url, action)
        async with self._session.post(
            identifier_action, data=fields, headers={**headers, "Referer": signin_url},
            allow_redirects=True, timeout=ClientTimeout(total=_TIMEOUT_S),
        ) as resp:
            authenticate_url = str(resp.url)
            authenticate_html = await resp.text(errors="replace")

        # 3. POST credentials (password step). The hmac on this page is a
        #    FRESH one bound to the password session.
        fields2, action2 = _login_fields(authenticate_html)
        if "hmac" not in fields2:
            err = _login_error(authenticate_html)
            raise AuthenticationError(
                err or "EU Data Act portal: no password form returned "
                "(check email address or the login flow changed)"
            )
        fields2["email"] = email
        fields2["password"] = password
        # CRITICAL: post to the clean /login/authenticate URL. Posting to
        # authenticate_url (which carries ?relayState=) duplicates the
        # param and the IDP rejects it with HTTP 400. _resolve_action
        # strips the query AND guards the doubled-/login/login/ trap.
        authenticate_action = _resolve_action(authenticate_url, action2)
        async with self._session.post(
            authenticate_action, data=fields2,
            headers={**headers, "Referer": authenticate_url},
            allow_redirects=True, timeout=ClientTimeout(total=_TIMEOUT_S),
        ) as resp:
            landing = str(resp.url)
            landing_html = await resp.text(errors="replace")
            status = resp.status

        # 3b. (#527, v2.15.5) — generic OAuth/IDP consent grant page. After
        # correct credentials the IDP can interject a server-rendered consent
        # page (``/signin-service/v1/consent/users/{uid}/{client}``,
        # templateModel pageType='consent') asking the account to AUTHORIZE
        # this OAuth client. This is NOT a marketing opt-in and NOT a bad
        # password — the user already entered their creds and wants the
        # integration authorized, so accepting the grant is exactly what the
        # official app does. We scrape the consent form (hmac/_csrf/relayState
        # via the same _login_fields helper) and POST to accept it, then let
        # the portal complete the redirect back to the portal host. Bounded:
        # accept at most ONCE — if the result is still not a completed landing
        # we fall through to classify_portal_login_failure (which now also
        # recognises the consent page as a non-credential PortalInteraction).
        if self._is_consent_landing(landing, landing_html):
            _LOGGER.info(
                "EU Data Act portal: consent grant page at %s — auto-accepting "
                "(user already authenticated; mirrors official-app behaviour)",
                _safe_url(landing),
            )
            accepted = await self._accept_consent_page(landing, landing_html)
            if accepted is not None:
                landing, landing_html, status = accepted

        # A completed flow lands back on the portal host via
        # /services/callbacklogin. Anything else (HTTP >= 400, a
        # signin-service/'/error' re-render, or an off-host landing) is a
        # FAILURE — but the failure can be many things besides bad
        # credentials (#527). v2.15.4: consult the templateModel + known
        # interstitial markers FIRST and raise the matching TYPED exception
        # so the callers' existing branches fire; only fall back to the
        # credential catch-all when there is genuinely no machine-readable
        # non-credential reason.
        portal_host = urlparse(_PORTAL_BASE).netloc
        landed_failed = (
            status >= 400
            or "signin-service" in landing
            or "/error" in landing
            or urlparse(landing).netloc != portal_host
        )
        if landed_failed:
            typed_exc, log_ctx = classify_portal_login_failure(
                landing, landing_html
            )
            # Secret-free diagnostics: host+path (query STRIPPED), HTTP
            # status, and templateModel error/errorCode/page-type keys.
            # NEVER email/password/tokens/relayState/code/query strings.
            _LOGGER.warning(
                "EU Data Act portal: login did not complete — "
                "landing=%s status=%s ctx=%s",
                _safe_url(landing), status, log_ctx,
            )
            if typed_exc is not None:
                raise typed_exc
            # classify_portal_login_failure returned None → it could NOT
            # find a non-credential reason (a known bad-credential errorCode,
            # or no machine-readable reason on a signin-service re-render). In
            # both cases this is the genuine credential failure: raise the
            # credential catch-all so the user is told to check the password
            # ONLY here, where we actually believe it.
            if "signin-service" in landing or "/error" in landing:
                raise AuthenticationError(
                    "EU Data Act portal: login failed — check email and password"
                )
            # Off-host / HTTP-error landing with no recognisable reason: we
            # can't prove it's the password, so surface a NON-credential
            # failure (server-side / unexpected page) rather than blaming
            # the user's credentials.
            if status >= 400:
                raise PortalInteractionRequiredError(
                    f"login rejected (HTTP {status})"
                )
            raise PortalInteractionRequiredError(
                "login did not complete (unexpected landing page)"
            )
        self.logged_in = True
        _LOGGER.info(
            "EU Data Act portal: login succeeded (read-only, ~15min cadence)"
        )

    async def _get_json(
        self,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        soft: bool = False,
    ) -> Any:
        """GET + parse JSON. Raises AuthenticationError on HTTP >= 400.

        v2.12.1 — ``soft=True`` returns None instead of raising for the
        transient "not provisioned yet" / portal-outage statuses
        (``_TRANSIENT_STATUSES``). Used for the data-request metadata
        endpoint, which 404s/500s on accounts where the continuous data
        request hasn't been enabled / hasn't propagated yet (#393, #424) —
        that's an expected transient, not a hard error.
        """
        # v2.13.0 — Bearer mode: attach the device-grant token. Covers every
        # JSON proxy_api call (vehicles list, metadata, datadelivery list,
        # relation) since they all funnel through here. No-op in cookie mode.
        eff_headers = dict(headers or {})
        if self._bearer:
            eff_headers["Authorization"] = f"Bearer {self._bearer}"
        # v2.13.1 — the portal is flaky: transient 5xx come and go within
        # seconds (the whole portal ecosystem hit this). On a soft call we
        # back off and retry the genuinely-transient server errors a couple of
        # times before giving up as "no data this poll", recovering polls the
        # portal would otherwise drop. A 404/410 (request not provisioned)
        # returns immediately; a real 401/403 still raises.
        for attempt in range(len(_PORTAL_RETRY_DELAYS) + 1):
            try:
                async with self._session.get(
                    url, headers=eff_headers, timeout=ClientTimeout(total=_TIMEOUT_S),
                ) as resp:
                    if resp.status >= 400:
                        if soft and resp.status in _TRANSIENT_STATUSES:
                            if (
                                resp.status in _RETRIABLE_STATUSES
                                and attempt < len(_PORTAL_RETRY_DELAYS)
                            ):
                                await asyncio.sleep(_PORTAL_RETRY_DELAYS[attempt])
                                continue
                            return None
                        raise AuthenticationError(
                            f"EU Data Act GET {url} → HTTP {resp.status}"
                        )
                    return await resp.json(content_type=None)
            except (TimeoutError, ClientConnectionError):
                # v2.14.8 — a transport-level timeout/disconnect (portal slow or
                # briefly unreachable) is NOT an auth failure. Retry with the
                # same backoff as a transient 5xx; a soft call then gives up as
                # "no data this poll", a hard call re-raises. NEVER convert it to
                # AuthenticationError — that forces a pointless re-login (the
                # churn v2.12.4 fixed). Fixes #481-#483, where a TimeoutError from
                # _session.get bypassed the status-only retry entirely.
                if attempt < len(_PORTAL_RETRY_DELAYS):
                    await asyncio.sleep(_PORTAL_RETRY_DELAYS[attempt])
                    continue
                if soft:
                    return None
                raise
        return None

    async def list_vehicle_vins(self) -> list[str]:
        """Return the VINs consented on the portal."""
        payload = await self._get_json(
            f"{_PORTAL_BASE}{_VEHICLES_PATH}?viewPosition=FRONT_LEFT"
        )
        vins: list[str] = []

        def walk(node: Any) -> None:
            if isinstance(node, dict):
                vin = node.get("vin") or node.get("vehicleIdentificationNumber")
                if isinstance(vin, str) and len(vin) == 17 and vin not in vins:
                    vins.append(vin)
                for v in node.values():
                    walk(v)
            elif isinstance(node, list):
                for v in node:
                    walk(v)

        walk(payload)
        return vins

    async def get_vehicle_data(
        self, vin: str, request_type: str = "partial"
    ) -> VehicleData:
        """Fetch the latest dataset for *vin* and map it to VehicleData.

        v2.18.0 (Phase C) — ``request_type`` selects the portal request family:
        ``"partial"`` is the 15-min live feed (the default, the coordinator's
        poll); ``"all"`` is the one-time historical export (config snapshot in
        the legacy Car-Net dialect). The two differ only in the metadata path
        and the ``type`` header sent to the datadelivery list/download — the
        parse is shared, since ``map_dataset_to_vehicle_data`` handles both
        dialects. Contract verified against real portal traces (2026-07-17).
        """
        meta_path = _ALL_METADATA_PATH if request_type == "all" else _METADATA_PATH
        d = VehicleData(vin=vin)
        # v2.15.0a10 (#481-residue) — assume "no data this poll" until the
        # dataset actually parses (cleared at the success return below). Every
        # early no-data return keeps this True, so the coordinator carries the
        # previous good values forward instead of blanking entities on a portal
        # timeout/outage. A brand-new car (no prior data) still appears.
        d.no_data = True
        # 1. metadata → identifier. Soft on 404/500: when the continuous
        # data request isn't set up / hasn't propagated yet, the endpoint
        # 404s or 500s. Treat that as "no data yet" — return the bare
        # VehicleData so the vehicle still appears and the data fills in
        # once the portal request goes active, instead of erroring every
        # poll (#393, #424).
        meta = await self._get_json(
            f"{_PORTAL_BASE}{meta_path.format(vin=vin)}", soft=True,
        )
        identifier = ""
        if isinstance(meta, dict):
            identifier = (
                meta.get("identifier")
                or meta.get("Identifier")
                or meta.get("dataRequestId")
                or ""
            )
        if not identifier:
            self.last_no_data_reason = "no_request"
            _LOGGER.info(
                "EU Data Act portal: no data-request yet for %s — enable the "
                "continuous data request for this car on the VW data portal "
                "(it can take a while to propagate). Vehicle will show with no "
                "data until then.",
                vin[-6:],
            )
            return d
        # 2. list datasets → newest non-empty zip. Soft on transient 5xx:
        # during the VW outage this endpoint 500s constantly (#428-#431).
        # A 500 here is the portal misbehaving, not a dead session, so we
        # surface it as "no data this poll" (data_act_no_data notice) rather
        # than raising AuthenticationError and re-logging in pointlessly.
        # A genuine 401/403 still raises (→ session-expired path).
        listing = await self._get_json(
            f"{_PORTAL_BASE}{_LIST_PATH.format(vin=vin, identifier=identifier)}",
            headers={"type": request_type},
            soft=True,
        )
        if listing is None:
            self.last_no_data_reason = "empty"
            _LOGGER.info(
                "EU Data Act portal: data endpoint returned a transient error "
                "for %s (most likely the ongoing VW-side portal outage). "
                "Treating as no data this poll; will retry next cycle.",
                vin[-6:],
            )
            return d
        files = listing if isinstance(listing, list) else listing.get("files", [])
        # (name, delivery_ts) per content file; keep array index as the tie/
        # fallback order so a listing with no timestamp behaves as before.
        cands: list[tuple[str, float | None, int]] = []
        for idx, f in enumerate(files):
            if not isinstance(f, dict):
                continue
            name = f.get("name")
            if isinstance(name, str) and not name.endswith(_NO_CONTENT_SUFFIX):
                # #529 step 4: prefer an explicit delivery timestamp over array
                # order (the array is NOT guaranteed newest-last). createdOn is
                # the portal's field (confirmed in the reference reader); accept
                # a few aliases defensively.
                dts = None
                for tk in ("createdOn", "created_on", "createdAt", "creationDate"):
                    if tk in f:
                        dts = _parse_ts(f.get(tk))
                        if dts is not None:
                            break
                cands.append((name, dts, idx))
        if not cands:
            self.last_no_data_reason = "empty"
            _LOGGER.debug("EU Data Act portal: no dataset files for %s yet", vin[-6:])
            return d
        # Newest by delivery ts when present; files without a ts sort below those
        # with one (-inf), and ties / a fully-tsless listing fall back to array
        # order (the original names[-1] behaviour).
        newest = max(
            cands, key=lambda c: (c[1] if c[1] is not None else float("-inf"), c[2])
        )[0]
        # 3. download ZIP → JSON. This GET bypasses _get_json, so the Bearer
        # header (v2.13.0) must be merged in separately without clobbering the
        # filename/type headers the download endpoint requires.
        dl_headers = {"filename": newest, "type": request_type}
        if self._bearer:
            dl_headers["Authorization"] = f"Bearer {self._bearer}"
        try:
            async with self._session.get(
                f"{_PORTAL_BASE}{_DOWNLOAD_PATH.format(vin=vin, identifier=identifier)}",
                headers=dl_headers,
                timeout=ClientTimeout(total=_TIMEOUT_S),
            ) as resp:
                if resp.status in _TRANSIENT_STATUSES:
                    # Same outage story as the listing call — the ZIP download
                    # 500s mid-outage. Don't burn the session; just skip this poll.
                    self.last_no_data_reason = "empty"
                    _LOGGER.info(
                        "EU Data Act portal: dataset download returned a transient "
                        "error (HTTP %s) for %s; treating as no data this poll.",
                        resp.status, vin[-6:],
                    )
                    return d
                if resp.status >= 400:
                    raise AuthenticationError(
                        f"EU Data Act portal: download → HTTP {resp.status}"
                    )
                raw = await resp.read()
        except (TimeoutError, ClientConnectionError):
            # v2.14.8 — same as the soft GETs: a transport timeout/disconnect on
            # the ZIP download is a portal hiccup, not a dead session. Skip the
            # poll instead of letting a raw TimeoutError bubble to the coordinator.
            self.last_no_data_reason = "empty"
            _LOGGER.info(
                "EU Data Act portal: dataset download timed out / disconnected "
                "for %s; treating as no data this poll.",
                vin[-6:],
            )
            return d
        payload = _unzip_json(raw, newest)
        field_ts: dict[str, float] = {}  # #529: resolved per-field capture ts
        field_syn: dict[str, set[str]] = {}  # v2.15.4: bare/qualified synonym map
        fields = _walk_fields(payload, field_ts, field_syn)
        _LOGGER.debug(
            "EU Data Act portal: %s dataset carried %d fields", vin[-6:], len(fields)
        )
        # v2.13.0 (P1) — an empty/no-content ZIP (now returned as {} instead of
        # raising) means no data this poll: flag it so the no-data notice fires,
        # and do NOT mark the vehicle online with a blank dataset.
        if not fields:
            self.last_no_data_reason = "empty"
            return d
        self.last_no_data_reason = ""
        d.no_data = False  # real dataset parsed → this is a genuine good poll
        d.connection_state = "online"
        return map_dataset_to_vehicle_data(fields, d, field_ts, field_syn)

    async def get_relation_nickname(self, vin: str) -> str | None:
        """Best-effort vehicle nickname from the relation endpoint."""
        try:
            rel = await self._get_json(
                f"{_PORTAL_BASE}{_RELATION_PATH.format(vin=vin)}",
                headers={"traceid": f"vehicle-relation-{uuid.uuid4()}"},
            )
        except Exception:  # noqa: BLE001
            return None
        if isinstance(rel, dict):
            nick = (rel.get("relation") or {}).get("vehicleNickname")
            return nick if isinstance(nick, str) else None
        return None


def _unzip_json(raw: bytes, name: str) -> dict[str, Any]:
    """Extract the JSON dataset from a portal ZIP, or ``{}`` if there is none.

    v2.13.0 (P1) — a 200 that returns an empty / no-content / corrupt ZIP is
    "no data this poll", NOT an authentication failure. Returning ``{}`` lets
    ``get_vehicle_data`` record ``last_no_data_reason="empty"`` instead of
    raising ``AuthenticationError``, which used to burn the session on a
    pointless re-login. The genuine auth decision is made by HTTP status at the
    call sites (401/403 → raise), never by ZIP-parse outcome.
    """
    if name.endswith(_NO_CONTENT_SUFFIX):
        return {}
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as zf:
            members = [n for n in zf.namelist() if n.lower().endswith(".json")]
            if not members:
                return {}
            with zf.open(members[0]) as fh:
                parsed = json.loads(fh.read().decode("utf-8"))
            return parsed if isinstance(parsed, dict) else {}
    except (zipfile.BadZipFile, ValueError, KeyError, OSError):
        return {}
