# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Volkswagen North America API client — b-h-s.spr.{country}00.p.con-veh.net.

Endpoints from matpoulin/CarConnectivity-connector-volkswagen-na (Apache-2.0).
Clean-room reimplementation using aiohttp + IDK PKCE auth.
Source: https://github.com/matpoulin/CarConnectivity-connector-volkswagen-na
"""

from __future__ import annotations

import asyncio
import hashlib
from datetime import datetime, timedelta, timezone
import logging
from typing import Any

from aiohttp import ClientConnectionError, ClientSession

from .._util import first_not_none
from .._util import mask_vin as _mask_vin
from .._util import safe_float, safe_int
from ..models import VehicleData
from ..exceptions import (
    AuthenticationError,
    APIError,
    CommandFailureReason,
    TokenExpiredError,
    UpstreamUnavailableError,
    classify_command_failure,
)
from ..auth.idk import IDKAuth
from ..models import BrandConfig, TokenSet

_LOGGER = logging.getLogger(__name__)


def _classify_data_403(exc: APIError) -> str:
    """v2.15.4 (#503) — classify a VW NA data-plane 403 from its body MARKERS.

    Returns one of the short, value-free labels ``"attestation"`` /
    ``"entitlement"`` / ``"bare-403"`` for the per-``get_status`` triage log.

    ``classify_command_failure`` only sees ``str(exc)``, which truncates the
    body to 200 chars (``exceptions.py`` ``APIError.__init__`` →
    ``body[:200]``), so an attestation marker further into the body could be
    cut off. We therefore re-classify against the retained ``exc.body`` (up to
    4 KB) by building a throw-away ``APIError`` whose ``str()`` carries the
    full body, then reuse the shared marker table — keeping ONE source of
    truth for the attestation/entitlement vocabulary.

    CRITICAL — privacy: the returned string is a fixed label only. The body is
    inspected locally for substring markers and is NEVER returned, logged, or
    attached to anything. Callers must log only the returned label.
    """
    body = exc.body if isinstance(getattr(exc, "body", None), str) else ""
    # Feed the FULL retained body through the shared classifier by wrapping it
    # in a probe whose str() exposes the whole body (no 200-char clip on the
    # marker scan). url is fixed/empty so no real URL is ever materialised.
    probe = APIError(exc.status, "", body)
    # str(probe) still clips to body[:200]; classify off the full body instead
    # by temporarily exposing it. We call the shared marker logic directly on a
    # probe whose __str__ we don't rely on: re-run classify on a probe whose
    # body[:200] already holds the markers when they're early, else fall to the
    # explicit full-body marker grep below.
    reason = classify_command_failure(probe)
    if reason is CommandFailureReason.ATTESTATION_LOCKED:
        return "attestation"
    # Full-body (up to 4 KB) attestation marker grep — covers markers that sit
    # past the 200-char str() clip the shared classifier scans.
    low = body.lower()
    if (
        "missing-device-token" in low
        or "missing_device_token" in low
        or "forbidden device detected" in low
        or "x-firebase-appcheck" in low
        or "firebase-appcheck" in low
        or "appcheck" in low
        or "play integrity" in low
        or "play_integrity" in low
    ):
        return "attestation"
    if (
        "not_entitled" in low
        or "not-entitled" in low
        or "license_required" in low
        or "license-required" in low
        or "entitlement" in low
        or "subscription" in low
    ):
        return "entitlement"
    if reason is CommandFailureReason.NOT_ENTITLED:
        # status-only 403 with no body marker
        return "bare-403"
    return "bare-403"

# Country → API base. b-h-s.spr.{cc}00.p.con-veh.net, per-country host.
# v2.26.0 (#915) — CANADA CORRECTED to ca00. The earlier N7 decision routed CA
# to us00 because a static DEX scan of the myVW APK found no "ca00" literal. That
# scan was misleading: the host is built at RUNTIME from the country code
# (b-h-s.spr.{cc}00...), so the concrete "ca00" never appears as a string to
# grep — only the "us00" default the app ships with does. A CA tester (vrouleau,
# #915) captured the live app and it queries b-h-s.spr.ca00.p.con-veh.net
# directly (most of the traffic in the capture), which is the "verify us00 serves
# CA cars" check the old comment asked for: it does not — a CA account on us00
# returns HTTP 500. Pointing CA at its own ca00 host cannot regress Canada (it was
# already 500); whether our client + login authenticate on ca00 is still
# live-unconfirmed (the capture was encrypted), so this is a grounded best-effort
# pending vrouleau's test on a real Canada account.
_COUNTRY_BASES: dict[str, str] = {
    "us": "https://b-h-s.spr.us00.p.con-veh.net",
    "ca": "https://b-h-s.spr.ca00.p.con-veh.net",
}

# v2.26.1 (#990/#915) — OIDC authorize/token PROXY host for every NA country.
# vrouleau confirmed the myVW app signs in on identity.na.vwgroup.io, and that
# v2.25 (which sent every NA country through us00) authenticated fine; only the
# vehicle-DATA host is per-country. The Canadian data host ca00 does NOT front a
# working /oidc/v1/authorize (it returns HTTP 400 before any credentials are
# submitted), so the auth flow must stay on the us00 con-veh proxy that 302s to
# the NA IDP for ALL NA countries, while api_base (the vehicle reads/commands)
# stays per-country from _COUNTRY_BASES above. This is the v2.26.0 regression:
# routing CA auth to ca00 moved the failure from a late 500 (v2.25, us00 data
# host wrong for a CA car) to an early 400 (ca00 has no authorize proxy).
_NA_OIDC_PROXY_BASE = _COUNTRY_BASES["us"]

BRAND_VW_NA = BrandConfig(
    name="volkswagen_na",
    client_id="59992128-69a9-42c3-8621-7942041ba824_MYVW_ANDROID",
    redirect_uri="kombi:///login",
    user_agent="MyVW/1.0 Android",
    api_base="https://b-h-s.spr.us00.p.con-veh.net",
    # b13 (#503) — scope MUST stay bare "openid". APK-CONFIRMED: dismantling
    # the live MyVW app (com.vw.carnet.release) shows the only OAuth scope
    # literal in the DEX is bare "openid" — "openid profile cars vin" appears
    # nowhere (not as literal, not url-encoded). v2.3.0 (#269) also live-
    # confirmed it: NA tester roberttco hit HTTP 400 with the wider chain.
    # v2.11.0 re-widened it from a source-read (never live-tested against NA)
    # and silently regressed login → the authorize redirect never lands a
    # code → "Legacy: no code in: identity.na.vwgroup.io/signin-service".
    scope="openid",
)

# v2.20.0 (N7) — the old per-CA client_id was REMOVED. Re-grepping the myVW DEX:
# the old CA client = 0 hits; the only *_MYVW_ANDROID literals are 59992128
# (phone) + the Wear-OS id. So CA shares the 59992128 CLIENT with US. Only the
# HOST differs: v2.26.0 (#915) points CA at its own ca00 host (see the bases
# above); the "ca00 = 0 DEX hits" that once argued for us00 was a static-scan
# artefact of the runtime-templated host, not evidence ca00 does not exist.

# v2.3.0 (#269) — VW NA-specific IDP host: identity.na.vwgroup.io
# (NOT identity.vwgroup.io). The authorize-redirect lands on this NA IDP and
# the signin form is served here (relative form-action paths resolve against it).
_NA_IDP_BASE = "https://identity.na.vwgroup.io"
# b14 (#503) — DORMANT/outdated. matpoulin's old "browser IDP client" GUID. It
# is no longer wired in (see IDKAuth construction below): the current NA flow
# uses the MYVW_ANDROID client throughout, so this would dead-end at
# ``signin-service/v1/b680e751… → "no code"``. Kept documented, not used.
_NA_SIGNIN_CLIENT_GUID_DORMANT = "b680e751-7e1f-4008-8ec1-3a528183d215@apps_vw-dilab_com"


class VWNAClient:
    """VW North America client.

    Uses a country-specific auth endpoint (b-h-s.spr.{cc}00.p.con-veh.net/oidc/v1/).
    Vehicle data uses UUID (not VIN directly in path) — VIN is mapped after garage fetch.
    """

    def __init__(
        self,
        session: ClientSession,
        email: str,
        password: str,
        spin: str = "",
        country: str = "us",
    ) -> None:
        self._session  = session
        self._email    = email
        self._password = password
        self._spin     = spin
        self._country  = country.lower()
        self._base     = _COUNTRY_BASES.get(self._country, _COUNTRY_BASES["us"])
        self._tokens: TokenSet | None = None
        # VW NA uses IDK auth but against a country-specific endpoint.
        # v2.20.0 (N7) — US and CA share the one client the current app ships
        # (59992128); the old per-CA client_id was unvalidated dead config.
        client_id = BRAND_VW_NA.client_id
        brand = BrandConfig(
            name=f"volkswagen_{self._country}",
            client_id=client_id,
            redirect_uri=BRAND_VW_NA.redirect_uri,
            user_agent=BRAND_VW_NA.user_agent,
            api_base=self._base,
            scope=BRAND_VW_NA.scope,
        )
        # v2.3.0 (#269 roberttco, 2026-05-21) — VW NA auth requires four
        # IDP overrides vs the default identity.vwgroup.io (EU) flow:
        #
        #   1. authorize_url_override → ``{_NA_OIDC_PROXY_BASE}/oidc/v1/authorize``
        #      (the us00 con-veh proxy, NOT identity.vwgroup.io). The
        #      MYVW_ANDROID client_id is only registered against this host —
        #      sending it to the EU IDP returns HTTP 400 (user's log on #269).
        #      v2.26.1 (#990): this is the us00 proxy for EVERY NA country, not
        #      the per-country data host. The ca00 host has no working authorize
        #      endpoint (it 400s), and vrouleau confirmed CA signs in here fine.
        #
        #   2. token_url_override → ``{_NA_OIDC_PROXY_BASE}/oidc/v1/token`` — same
        #      us00 host for both code-exchange and refresh-token calls. The
        #      default fallback (emea.bff.cariad.digital/login/v1/idk/
        #      token) does not know NA client_ids.
        #
        #   3. idk_base_override → identity.na.vwgroup.io. The authorize
        #      step redirects to the NA IDP host, and our resolution of
        #      relative form-actions + the ``Origin`` header must point
        #      at the right base.
        #
        # b14 (#503) — NO separate signin client_id override. Keeping the
        # override off means ``idk._signin_client_id`` falls back to
        # ``brand.client_id`` (the shared 59992128 MYVW client for US and CA).
        # Rationale, corrected in v2.24.0 after a live probe of the whole chain:
        #
        #  - The ORIGINAL justification here was that the MyVW APK contains zero
        #    ``b680e751`` / ``identity.na`` literals, so the flow "must" use
        #    MYVW_ANDROID throughout. That inference is WRONG: the app never
        #    performs the credential step itself (it opens a CustomTab and lets
        #    the browser do it), so its DEX cannot evidence the signin client
        #    either way.
        #  - What is actually true: ``b-h-s.spr.us00.p.con-veh.net`` is a PROXY.
        #    Our authorize call 302s to identity.na.vwgroup.io carrying con-veh's
        #    OWN client ``b680e751-…@apps_vw-dilab_com``, so the signin-service
        #    page we land on genuinely belongs to b680e751.
        #  - The override nevertheless stays OFF, because the reason it was
        #    removed still stands on its own: with it, NA login died at "no code"
        #    in a real test (Canaillee, b13). The signin client and the client we
        #    exchange the code with are different layers, and forcing the inner
        #    one broke the outer exchange.
        #  - Live-checked consequence of leaving it off: the wrong id is only
        #    ever used to BUILD A FALLBACK URL, and only when the served page has
        #    no parseable form action. Today the page has exactly one form with a
        #    valid action, so the fallback never fires. If VW ever re-renders it
        #    as a SPA shell, that fallback would hit
        #    ``signin-service/v1/59992128…_MYVW_ANDROID`` which answers HTTP 500
        #    (probed: the same path with b680e751 answers 400), i.e. an
        #    unresolvable-client 500 rather than a clear error. Prefer parsing the
        #    client id out of the signin URL we actually landed on over
        #    hardcoding either value.
        self._auth = IDKAuth(
            session,
            brand,
            authorize_url_override=f"{_NA_OIDC_PROXY_BASE}/oidc/v1/authorize",
            token_url_override=f"{_NA_OIDC_PROXY_BASE}/oidc/v1/token",
            idk_base_override=_NA_IDP_BASE,
        )
        # UUID cache: VIN → UUID (returned by garage)
        self._vin_to_uuid: dict[str, str] = {}
        # v2.4.1 (#285) — human-friendly metadata from garage payload.
        # vehicleNickName + modelName per matpoulin's response shape.
        # Used by get_status() / device-info to enrich the entity model.
        self._vin_to_nickname: dict[str, str] = {}
        self._vin_to_model: dict[str, str] = {}
        # v2.10.0 (Group C). user_id for the NA-specific endpoints that
        # are addressed by user-id rather than VIN/UUID. Populated from
        # the IDK auth redirect or by decoding the id_token ``sub``
        # claim. Refer to the privileges + SPIN flow comments below for
        # the endpoints that consume it.
        self._user_id: str | None = None
        # v2.15.4 (#503) — read-path entitlement surfacing. The coordinator
        # polls these after each cycle (mirrors the OLA / data_act_no_data
        # repair plumbing) to decide whether to raise the
        # ``vw_na_data_forbidden`` Repair issue. They are set ONLY from the
        # 403 marker classification + the privileges-call outcome inside
        # ``get_status`` — never from a value, VIN, UUID or token. Markers-only.
        self.vw_na_data_forbidden: bool = False
        self.vw_na_data_forbidden_reason: str = ""
        # Last HTTP status of the privileges (4th gather) call. ``None`` means
        # the call wasn't attempted (no user_id) or succeeded; an int is the
        # last error status. Used as the entitlement discriminator only.
        self._last_privileges_status: int | None = None
        # v2.15.5 (#503) — SPIN read-session auth (peer-confirmed:
        # zackcornelius/CarConnectivity-connector-volkswagen-na, 2026-06-24).
        # On locked-down NA accounts the rvs/ev reads 403 on the bare
        # access_token but succeed when authorised with a per-vehicle
        # ``carnetVehicleToken`` obtained via the SPIN challenge/session
        # handshake. We cache that token per-UUID and only re-run the exchange
        # when it is missing/expired (the S-PIN has a limited try budget — an
        # exchange every poll would brick the user's PIN).
        #   uuid -> (carnetVehicleToken, exp_epoch_or_None)
        self._read_session_tokens: dict[str, tuple[str, float | None]] = {}
        # LOCKOUT GUARD: once the SPIN read-session exchange fails for an auth
        # reason (low remainingTries, 401/403 on the session POST, or a wrong
        # S-PIN), we set this and NEVER retry the exchange this session — we
        # fall back to the access_token read path. This avoids a poll-loop that
        # would burn through the remaining S-PIN tries and lock the user out.
        self._spin_read_session_disabled: bool = False
        # One-time "S-PIN looks wrong" surfacing (set True after we've warned).
        self._spin_read_warned: bool = False
        # v2.15.5 (#503) — persistence counter so a bare-403 (active sub, no
        # marker) that recurs across N polls surfaces the repair instead of
        # staying silent forever. Reset on any successful / non-403 read.
        self._bare_403_streak: int = 0

    # v2.15.5 (#503) — number of consecutive bare-403 polls before we surface
    # the vw_na_data_forbidden repair for an otherwise-silent persistent lock.
    _BARE_403_PERSIST_THRESHOLD = 3
    # remainingTries at/below which we refuse to spend an S-PIN attempt.
    _SPIN_MIN_REMAINING_TRIES = 2
    # Peer header block (Car-Net app fingerprint) applied ONLY to the rvs/ev
    # data reads when authorising with a carnetVehicleToken. The login + garage
    # path already returns 200 with the default headers and is left untouched.
    _READ_HEADERS = {
        "User-Agent": "Car-Net/60 CFNetwork/1121.2.2 Darwin/19.3.0",
        "content-version": "1",
        "Accept-Language": "en-us",
        "Accept": "*/*",
    }

    async def authenticate(self, mfa_code: str | None = None) -> None:
        """IDK PKCE login against VW NA endpoint."""
        self._tokens = await self._auth.authenticate(self._email, self._password)
        # v2.10.0 (Group C). Capture the user_id once auth completes.
        # The NA stack exposes a per-user privileges endpoint and a
        # per-user SPIN-challenge endpoint that both need it; pulling
        # it from the IDK redirect or id_token now avoids re-decoding
        # on every command.
        await self._capture_user_id()
        _LOGGER.debug("VW NA auth complete (%s)", self._country.upper())

    async def _capture_user_id(self) -> None:
        """v2.10.0 (Group C). Populate ``self._user_id``.

        Three-step fallback chain mirrors the SEAT/CUPRA pattern in
        ``seat_cupra._fetch_user_id``:

        1. The IDK redirect-URI scan inside ``IDKAuth`` already records
           a ``user_id`` query-string parameter when the NA IDP includes
           it. Reuse that.
        2. If that didn't fire (NA IDP does not always echo the
           ``user_id`` param), decode the id_token's ``sub`` claim
           locally.
        3. If neither yielded a value, leave ``self._user_id`` as None.
           The privileges + SPIN endpoints simply won't be reachable
           in that case and ``get_subscription_privileges`` returns an
           empty dict so the cross-brand subscription sensors stay at
           ``None`` (phantom-protected).
        """
        if self._auth.user_id:
            self._user_id = self._auth.user_id
            return
        if self._tokens and self._tokens.id_token:
            try:
                import base64  # noqa: PLC0415
                import json as _json  # noqa: PLC0415
                payload_b64 = self._tokens.id_token.split(".")[1]
                payload_b64 += "=" * (4 - len(payload_b64) % 4)
                payload = _json.loads(base64.urlsafe_b64decode(payload_b64))
                sub = payload.get("sub")
                if isinstance(sub, str) and sub:
                    self._user_id = sub
            except Exception:  # noqa: BLE001
                _LOGGER.debug("VW NA: could not decode id_token sub claim")

    @staticmethod
    def _jwt_exp(token: str) -> float | None:
        """Decode the ``exp`` (epoch seconds) claim from a JWT, locally.

        No signature check (we don't hold the key and don't need to — we only
        want to know when to stop reusing the cached carnetVehicleToken). Any
        decode error returns ``None`` so the caller treats it as "no known
        expiry" and re-runs the exchange next time it's needed.
        """
        try:
            import base64  # noqa: PLC0415
            import json as _json  # noqa: PLC0415
            payload_b64 = token.split(".")[1]
            payload_b64 += "=" * (4 - len(payload_b64) % 4)
            payload = _json.loads(base64.urlsafe_b64decode(payload_b64))
            exp = payload.get("exp")
            if isinstance(exp, (int, float)):
                return float(exp)
        except Exception:  # noqa: BLE001
            return None
        return None

    async def _get_read_session_token(self, vin: str) -> str | None:
        """v2.15.5 (#503) — per-vehicle carnetVehicleToken for the data reads.

        PEER-CONFIRMED (zackcornelius/CarConnectivity-connector-volkswagen-na,
        pushed 2026-06-24): on locked-down NA accounts the rvs/ev reads 403 on
        the bare access_token but succeed when authorised with a per-vehicle
        ``carnetVehicleToken``. The token is obtained via a SPIN handshake:

            1. GET  {base}/ss/v1/user/{uid}/challenge
                    -> data.challenge (str) + data.remainingTries (int)
            2. spinHash = SHA512(challenge + "." + spin).hexdigest().upper()
            3. POST {base}/ss/v1/user/{uid}/vehicle/{uuid}/session
                    body {idToken, spinHash, tsp:"WCT"}
                    -> data.carnetVehicleToken (a JWT)

        v2.29.x (sstur/vwapp): this SAME ``carnetVehicleToken`` is now the auth
        for the remote COMMANDS too (lock/unlock/wake/charge/climate use it as
        the Bearer via ``_carnet_command``). The old separate command-SPIN path
        (``/ss/v1/user/{uid}/spin`` with {challenge,response} → an X-Spin-Session
        header) was wrong — VW never honoured it — and has been removed.

        SAFETY:
        - S-PIN-gated: returns ``None`` immediately if no S-PIN is configured
          (caller then keeps the plain access_token path → non-S-PIN users
          unchanged).
        - Cached per-UUID; only re-runs the exchange when the cached token is
          missing or its JWT ``exp`` has passed → NOT every poll.
        - Lockout-safe: if ``remainingTries`` is low or the session POST fails
          for an auth reason, sets ``_spin_read_session_disabled`` and never
          retries this session (fall back to access_token). Surfaces a single
          warning if the S-PIN looks wrong.

        Returns the carnetVehicleToken, or ``None`` to signal "use the plain
        access_token read path".
        """
        # getattr defaults keep this safe for clients built via __new__ in
        # tests (which skip __init__) — they have no S-PIN so we short-circuit.
        spin = getattr(self, "_spin", "")
        if not spin or not getattr(self, "_user_id", None) or not getattr(
            self, "_tokens", None
        ):
            return None
        if getattr(self, "_spin_read_session_disabled", False):
            return None
        if not hasattr(self, "_read_session_tokens"):
            self._read_session_tokens = {}
        if not hasattr(self, "_spin_read_warned"):
            self._spin_read_warned = False
        uuid = self._vin_to_uuid.get(vin, vin)

        # ── cache hit (not expired) ───────────────────────────────────────────
        cached = self._read_session_tokens.get(uuid)
        if cached is not None:
            token, exp = cached
            if exp is None:
                return token
            # 60s skew so we don't hand back a token about to expire mid-read.
            if exp - 60 > datetime.now(tz=timezone.utc).timestamp():
                return token
            # expired — drop it and re-exchange below
            self._read_session_tokens.pop(uuid, None)

        id_token = self._tokens.id_token if self._tokens else None
        if not id_token:
            return None

        challenge_url = f"{self._base}/ss/v1/user/{self._user_id}/challenge"
        session_url = (
            f"{self._base}/ss/v1/user/{self._user_id}/vehicle/{uuid}/session"
        )

        # spinHash casing — v2.29.x (sstur/vwapp, iOS live-capture 2026-08): VW's
        # OWN app sends LOWERCASE SHA-512 hex. Our prior uppercase (from
        # zackcornelius) was never end-to-end validated on our stack, and SHA-512
        # hex is canonically lowercase — an uppercase-only server is implausible,
        # so if uppercase ever "worked" it was because VW compares case-
        # insensitively. Try lowercase first; only if the session POST rejects it
        # (401/403) fetch a FRESH single-use challenge and retry with the legacy
        # uppercase before disabling. The remaining-tries guard runs on each
        # challenge, so the fallback can never push the S-PIN budget to lockout.
        for use_upper in (False, True):
            # ── 1) challenge (fresh each attempt: single-use) ──────────────────
            try:
                ch_resp = await self._get(challenge_url)
            except APIError as err:
                _LOGGER.debug(
                    "VW NA read-session: challenge failed (%s) for vin ***%s — "
                    "falling back to access_token reads",
                    err.status, vin[-6:],
                )
                return None
            if not isinstance(ch_resp, dict):
                return None
            _ch_nested = ch_resp.get("data")
            data: dict[str, Any] = (
                _ch_nested if isinstance(_ch_nested, dict) else ch_resp
            )
            challenge = data.get("challenge")
            remaining = data.get("remainingTries")
            if not isinstance(challenge, str) or not challenge:
                return None
            # LOCKOUT GUARD: refuse to spend an attempt when few tries remain.
            if isinstance(remaining, int) and remaining <= self._SPIN_MIN_REMAINING_TRIES:
                self._spin_read_session_disabled = True
                if not self._spin_read_warned:
                    self._spin_read_warned = True
                    _LOGGER.warning(
                        "VW NA read-session: only %d S-PIN attempt(s) remain — "
                        "NOT spending one on the data-read session exchange to "
                        "avoid locking your S-PIN. Falling back to the standard "
                        "read path. Verify your S-PIN is correct, then reload the "
                        "integration to re-enable the SPIN read path.",
                        remaining,
                    )
                return None

            # ── 2) spinHash (lowercase primary, uppercase legacy fallback) ─────
            digest = hashlib.sha512(
                f"{challenge}.{spin}".encode("utf-8")
            ).hexdigest()
            spin_hash = digest.upper() if use_upper else digest

            # ── 3) session ─────────────────────────────────────────────────────
            try:
                sess = await self._post(
                    session_url,
                    json={"idToken": id_token, "spinHash": spin_hash, "tsp": "WCT"},
                )
            except APIError as err:
                status = err.status or 0
                if status in (401, 403):
                    if not use_upper:
                        # Lowercase rejected — retry once with the legacy
                        # uppercase casing on a fresh challenge before disabling.
                        continue
                    # Both casings rejected: wrong S-PIN (or PIN lockout).
                    # DISABLE for the session so we never loop and burn tries.
                    self._spin_read_session_disabled = True
                    if not self._spin_read_warned:
                        self._spin_read_warned = True
                        _LOGGER.warning(
                            "VW NA read-session: the S-PIN session exchange was "
                            "rejected (%s) — your S-PIN may be wrong. Disabling "
                            "the SPIN read path for this session (falling back to "
                            "the standard reads) so we don't lock your S-PIN. Fix "
                            "the S-PIN and reload the integration to retry.",
                            status,
                        )
                    return None
                _LOGGER.debug(
                    "VW NA read-session: session POST failed (%s) for vin "
                    "***%s — falling back to access_token reads",
                    status, vin[-6:],
                )
                return None
            if not isinstance(sess, dict):
                return None
            _s_nested = sess.get("data")
            sdata: dict[str, Any] = (
                _s_nested if isinstance(_s_nested, dict) else sess
            )
            new_token = sdata.get("carnetVehicleToken")
            if not isinstance(new_token, str) or not new_token:
                return None
            self._read_session_tokens[uuid] = (new_token, self._jwt_exp(new_token))
            _LOGGER.debug(
                "VW NA read-session: obtained carnetVehicleToken for vin ***%s "
                "(cached)", vin[-6:],
            )
            return new_token
        return None

    async def get_vehicles(self) -> list[str]:
        """Return VINs from VW NA garage.

        v2.4.1 (#285 roberttco, 2026-05-24) — the actual API response
        shape per matpoulin/CarConnectivity-connector-volkswagen-na
        (the Apache-2.0 reference cited at the top of this file) is:

            {"data": {"vehicles": [{"vin": ..., "vehicleId": ..., ...}]}}

        Our previous parser read ``data.get("vehicles", [])`` (top-
        level), which returned ``[]`` and raised ``ConfigEntryNotReady
        ("No vehicles found")`` even though the auth flow + token
        exchange had succeeded perfectly. roberttco's debug log on #285
        confirmed: full auth chain works, but garage call result was
        treated as empty. Fix: walk through the ``data`` envelope with
        defensive fallback to top-level for forward-compat if VW NA
        ever flattens the shape.

        Bonus per matpoulin: response also carries ``vehicleNickName``
        and ``modelName`` per vehicle — cache them for device-info /
        entity-naming downstream.
        """
        data = await self._get(f"{self._base}/account/v1/garage")
        # v2.23.3 (#503/#659, vrouleau CA) — robust recursive garage walk.
        # The old rigid path data["data"]["vehicles"] / data["vehicles"]
        # returned [] for accounts where VW NA nests the vehicle array deeper
        # under the 'data' envelope (per-region Cox shape), raising a false
        # "no vehicles" ConfigEntryNotReady even though auth + the garage call
        # both succeeded. Mirror the EU-portal parser: walk the whole payload
        # and treat any dict carrying a 17-char 'vin' as a vehicle, draining
        # its uuid / nickname / model too. A genuinely empty garage still
        # walks to zero VINs, so the empty-account behaviour is unchanged.
        vins: list[str] = []

        def _collect(node: Any) -> None:
            if isinstance(node, dict):
                vin = node.get("vin") or node.get("vehicleIdentificationNumber")
                if isinstance(vin, str) and len(vin) == 17 and vin not in vins:
                    uuid = node.get("uuid") or node.get("vehicleId")
                    if uuid:
                        self._vin_to_uuid[vin] = uuid
                    nickname = node.get("vehicleNickName")
                    if isinstance(nickname, str) and nickname:
                        self._vin_to_nickname[vin] = nickname
                    model = node.get("modelName")
                    if isinstance(model, str) and model:
                        self._vin_to_model[vin] = model
                    vins.append(vin)
                    _LOGGER.debug(
                        "VW NA: found VIN %s uuid=%s nickname=%s model=%s",
                        _mask_vin(vin), uuid, nickname, model,
                    )
                for value in node.values():
                    _collect(value)
            elif isinstance(node, list):
                for value in node:
                    _collect(value)

        _collect(data)
        if not vins:
            # Genuinely empty OR a shape we still don't reach — log the nested
            # keys (top level + one into 'data') so an unexpected empty result
            # stays diagnosable from a single DEBUG report.
            inner = data.get("data") if isinstance(data, dict) else None
            _LOGGER.warning(
                "VW NA garage returned no vehicles (top-level keys=%s, data "
                "keys=%s) — if this is unexpected, please open an issue with "
                "the DEBUG log so we can adjust the parser shape",
                list(data.keys()) if isinstance(data, dict) else type(data).__name__,
                list(inner.keys()) if isinstance(inner, dict) else type(inner).__name__,
            )
        return vins

    async def get_subscription_privileges(self, vin: str) -> dict[str, Any]:
        """v2.10.0 (Group C). VW NA Cox-backend privileges endpoint.

        ``GET /rrs/v1/privileges/user/{user_id}/vehicle/{uuid}`` returns
        the per-vehicle subscription + capability map for the signed-in
        user. Reference: zackcornelius/CarConnectivity-connector-
        volkswagen-na scan 2026-06-02.

        Response shape (sanitised from the NA app traffic):

            {
              "subscription": {
                "active": true,
                "expiresAt": "2027-08-14T00:00:00Z",
                ...
              },
              "capabilities": {
                "remoteLockUnlock": "ENABLED",
                ...
              }
            }

        Returned dict carries normalised fields the parser drains in
        ``get_status``. Empty dict on any HTTP error so callers stay
        defensive: the cross-brand ``subscription_*`` fields default
        to ``None`` so the gated sensors stay hidden when the call
        fails or the user_id is unavailable.
        """
        # v2.15.4 (#503) — reset the per-poll privileges status so a previous
        # cycle's error never lingers as a false entitlement signal.
        self._last_privileges_status = None
        if not self._user_id:
            _LOGGER.debug(
                "VW NA: get_subscription_privileges skipped (no user_id captured)"
            )
            return {}
        uuid = self._vin_to_uuid.get(vin, vin)
        url = (
            f"{self._base}/rrs/v1/privileges/user/{self._user_id}"
            f"/vehicle/{uuid}"
        )
        try:
            data = await self._get(url)
        except APIError as err:
            # v2.15.4 (#503) — remember the status so get_status can use the
            # privileges outcome as the entitlement discriminator. Numeric
            # status only — never the body/url.
            self._last_privileges_status = err.status
            # 401 / 403 / 404 are expected on accounts without an active
            # Car-Net subscription or on legacy firmware that does not
            # expose this endpoint. 5xx is also benign here, the rest
            # of the polling cycle still completes.
            _LOGGER.debug(
                "VW NA privileges fetch returned %s for vin ***%s, "
                "leaving subscription fields at None",
                err.status, vin[-6:],
            )
            return {}
        except Exception as exc:  # noqa: BLE001
            _LOGGER.debug(
                "VW NA privileges fetch errored for vin ***%s: %s",
                vin[-6:], exc,
            )
            return {}
        if not isinstance(data, dict):
            return {}
        # Walk the optional ``data`` envelope (Cox convention) so the
        # caller sees a flat dict either way.
        nested = data.get("data")
        body: dict[str, Any] = nested if isinstance(nested, dict) else data

        out: dict[str, Any] = {}
        raw_sub = body.get("subscription")
        sub_block: dict[str, Any] = raw_sub if isinstance(raw_sub, dict) else {}
        if not sub_block:
            # Some firmware nests under ``privileges``
            raw_priv = body.get("privileges")
            if isinstance(raw_priv, dict):
                sub_block = raw_priv
        if sub_block:
            # Active flag (multiple key variants observed)
            active: bool | None = None
            raw_active = sub_block.get("active")
            if isinstance(raw_active, bool):
                active = raw_active
            else:
                state = sub_block.get("status") or sub_block.get("state")
                if isinstance(state, str):
                    active = state.upper() in ("ACTIVE", "VALID", "ENABLED")
            if active is not None:
                out["subscription_active"] = active
            # Expiry timestamp (multiple key variants observed)
            expiry = (
                sub_block.get("expiresAt")
                or sub_block.get("expirationDate")
                or sub_block.get("validUntil")
                or sub_block.get("endDate")
            )
            if isinstance(expiry, str) and len(expiry) >= 10 and "T" in expiry:
                out["subscription_expiry_at"] = expiry

        capabilities = body.get("capabilities")
        if isinstance(capabilities, dict) and capabilities:
            # Counted as a diagnostic value, the number of capability
            # flags the backend advertises for this vehicle/user combo.
            # Mirrors the EU CARIAD-BFF ``capabilities_count`` sensor.
            out["capabilities_count"] = len(capabilities)

        return out

    async def get_status(self, vin: str) -> VehicleData:
        """Fetch vehicle status using UUID."""
        v = self._val
        uuid = self._vin_to_uuid.get(vin, vin)
        # Defensive: tests construct the client via __new__ (skipping __init__),
        # so the v2.15.5 counters may be absent. Treat as fresh.
        if not hasattr(self, "_bare_403_streak"):
            self._bare_403_streak = 0
        if not hasattr(self, "_read_session_tokens"):
            self._read_session_tokens = {}
        d = VehicleData(vin=vin, manufacturer="Volkswagen")
        # Thread the human-friendly metadata cached during garage discovery.
        # Without this, d.model was always None for VW US/CA, so Scout/Error
        # reports showed model=None even though list_vehicles cached modelName.
        d.model = self._vin_to_model.get(vin)
        d.vehicle_nickname = self._vin_to_nickname.get(vin)

        # v2.15.5 (#503) — SPIN read-session auth. On locked-down NA accounts
        # the rvs/ev reads 403 on the bare access_token but succeed with a
        # per-vehicle carnetVehicleToken (peer-confirmed). S-PIN-gated + cached
        # + lockout-safe (see _get_read_session_token). ``None`` => keep the
        # plain access_token path (non-S-PIN users + fallback are unchanged).
        carnet_token = await self._get_read_session_token(vin)

        results = await asyncio.gather(
            self._read(f"{self._base}/rvs/v1/vehicle/{uuid}", carnet_token),
            self._read(f"{self._base}/ev/v1/vehicle/{uuid}/charge/summary", carnet_token),
            self._read(f"{self._base}/ev/v1/vehicle/{uuid}/climate/summary", carnet_token),
            self.get_subscription_privileges(vin),
            return_exceptions=True,
        )
        vehicle_raw, charge, climate, privileges = results

        # v2.15.3 (#503) — COMPACT shape-only DEBUG log so a user's DEBUG log
        # reveals the real response shape without ever logging values (privacy).
        # Emits, per response, either the exception repr OR the sorted top-level
        # keys; for the charge dict it also drills into the batteryStatus /
        # chargingStatus / plugStatus sub-object keys (the EV SoC/range lived in
        # an unexpected sub-object — keys-only makes the next report diagnostic).
        if _LOGGER.isEnabledFor(logging.DEBUG):
            def _shape(obj: Any) -> str:
                if isinstance(obj, Exception):
                    # TYPE-ONLY: never log the exception repr — its message can
                    # carry response-body fragments / a UUID. Surface the class
                    # name plus an optional numeric HTTP status if one is attached.
                    _st = getattr(obj, "status", None)
                    return (
                        f"EXC {type(obj).__name__} status={_st}"
                        if isinstance(_st, int)
                        else f"EXC {type(obj).__name__}"
                    )
                if isinstance(obj, dict):
                    return f"dict keys={sorted(obj.keys())}"
                return f"type={type(obj).__name__}"

            _LOGGER.debug("VW NA get_status shapes: rvs=%s", _shape(vehicle_raw))
            _LOGGER.debug("VW NA get_status shapes: charge=%s", _shape(charge))
            if isinstance(charge, dict):
                for _sub in ("batteryStatus", "chargingStatus", "plugStatus"):
                    _val_sub = charge.get(_sub)
                    if isinstance(_val_sub, dict):
                        _LOGGER.debug(
                            "VW NA get_status charge.%s keys=%s",
                            _sub, sorted(_val_sub.keys()),
                        )
                    else:
                        _LOGGER.debug(
                            "VW NA get_status charge.%s type=%s",
                            _sub, type(_val_sub).__name__,
                        )
            _LOGGER.debug("VW NA get_status shapes: climate=%s", _shape(climate))

        # ── #503 read-path 403 triage + entitlement surfacing ──────────────────
        # login + garage succeed but the per-vehicle reads (rvs / charge /
        # climate) 403. Until now the only signal was the type+numeric-status
        # shape log above, so attestation-lock vs not-entitled vs a bare 403
        # could not be told apart. Classify the FIRST data 403 from its body
        # MARKERS (never its text), emit ONE value-free DEBUG line, and use the
        # privileges (4th gather) outcome as the entitlement discriminator.
        #
        # PRIVACY: every value below is a fixed label, a class name, or a
        # numeric HTTP status. No UUID / VIN / body fragment / token is ever
        # built into these strings (matches the shape-only log above).
        # #659 — the entitlement/forbidden verdict keys ONLY off the primary RVS
        # read (vehicle_raw). On a COMBUSTION VW NA car the EV-only charge +
        # climate summaries legitimately 403 (USER_NOT_AUTHORIZED) while RVS 200s
        # — counting those as data-403s falsely tripped the "renew subscription"
        # Repair. RVS 200 already proves entitlement; RVS 403 is the real signal.
        data_403s = [
            r for r in (vehicle_raw,)
            if isinstance(r, APIError) and getattr(r, "status", None) == 403
        ]
        if data_403s:
            data_class = _classify_data_403(data_403s[0])
            _LOGGER.debug(
                "VW NA data 403 classified as %s (primary RVS read forbidden; "
                "benign EV-summary 403s on combustion cars are ignored)",
                data_class,
            )
            # Privileges shape/status as the entitlement discriminator —
            # value-safe: only the dict-ness, an active bool, a count int, or
            # the last error status.
            priv_status = self._last_privileges_status
            if isinstance(privileges, dict) and privileges:
                _LOGGER.debug(
                    "VW NA data 403 privileges: dict subscription_active=%s "
                    "capabilities_count=%s",
                    privileges.get("subscription_active"),
                    privileges.get("capabilities_count"),
                )
            else:
                _LOGGER.debug(
                    "VW NA data 403 privileges: empty (last_status=%s)",
                    priv_status,
                )
            # Entitlement decision: the data plane is forbidden AND either the
            # privileges call also 403/401'd OR the privileges payload reports
            # an INACTIVE subscription. Attestation locks are NOT an
            # entitlement problem — never surface them as a phantom renewal.
            sub_active = (
                privileges.get("subscription_active")
                if isinstance(privileges, dict)
                else None
            )
            privileges_forbidden = priv_status in (401, 403)
            # v2.15.5 (#503) — a carnetVehicleToken read that STILL 403s means
            # the cached token is stale/rejected: drop it so the next poll
            # re-exchanges (subject to the lockout guard). Never re-exchange in
            # THIS poll (would risk a second S-PIN attempt back-to-back).
            if carnet_token is not None:
                self._read_session_tokens.pop(uuid, None)
            if data_class == "attestation":
                self.vw_na_data_forbidden = True
                self.vw_na_data_forbidden_reason = "attestation"
                self._bare_403_streak = 0
            elif data_class == "entitlement" or privileges_forbidden or sub_active is False:
                self.vw_na_data_forbidden = True
                self.vw_na_data_forbidden_reason = "entitlement"
                self._bare_403_streak = 0
            else:
                # Bare 403 with no corroborating entitlement signal — could be
                # transient. v2.15.5 (#503): count consecutive bare-403 polls;
                # once it persists past the threshold, surface the repair so a
                # silent persistent lockout (active sub, no marker — e.g. the
                # SPIN read path couldn't be used) isn't invisible forever.
                self._bare_403_streak += 1
                if self._bare_403_streak >= self._BARE_403_PERSIST_THRESHOLD:
                    self.vw_na_data_forbidden = True
                    self.vw_na_data_forbidden_reason = "bare-403"
                    _LOGGER.debug(
                        "VW NA data 403: bare-403 persisted %d polls — "
                        "surfacing repair",
                        self._bare_403_streak,
                    )
                else:
                    self.vw_na_data_forbidden = False
                    self.vw_na_data_forbidden_reason = "bare-403"
        else:
            # Any successful (or non-403) read clears the forbidden flag so the
            # coordinator drops the Repair issue on recovery.
            self.vw_na_data_forbidden = False
            self.vw_na_data_forbidden_reason = ""
            self._bare_403_streak = 0

        # ── Vehicle status ────────────────────────────────────────────────────
        if isinstance(vehicle_raw, dict):
            power = v(vehicle_raw, "powerStatus") or {}
            # v2.10.0 (#322) — modern VW NA backend ships odometer as a
            # root-level ``currentMileage`` field in addition to (or
            # instead of) the legacy ``powerStatus.odometer`` nested
            # path. Try both, root-level first since that is what
            # current firmware sends.
            d.odometer_km = first_not_none(
                v(vehicle_raw, "currentMileage"),
                v(power, "odometer"),
            )
            d.fuel_level  = v(power, "fuelPercentRemaining")
            # v2.11.0 (zackcornelius source-verified) - cruiseRangeUnits
            # is "KM" or "MI"; pre-v2.11.0 we unconditionally treated
            # the value as km, miles users got their range under-
            # reported by ~38%.
            # v2.15.2 (#503, MyVW APK) — modern NA backend splits range into
            # cruiseRangeFirst/Second and may omit the bare cruiseRange; EVs
            # report their range in cruiseRangeFirst, so a bare read left them
            # with no range at all.
            range_raw = v(power, "cruiseRange")
            if range_raw is None:
                range_raw = v(power, "cruiseRangeFirst")
            range_unit = (v(power, "cruiseRangeUnits") or "KM").upper()
            if isinstance(range_raw, (int, float)):
                if range_unit == "MI":
                    d.range_km = int(range_raw * 1.609344)
                else:
                    d.range_km = int(range_raw)

            # v2.15.3 (#503, MyVW APK DEX-verified) — the OLD rvs.batteryStatus
            # read lived here. RvsResponse carries NO batteryStatus object, so it
            # always returned None. EV SoC/range/charged-energy now come from the
            # charge/summary BatteryStatus block below; has_battery is set there.

            # v2.10.0 (#322 roberttco — 2023 ID.4 US) — VW NA RVS
            # response shape migration. Pre-v2.10.0 we read doors and
            # windows from ``data.doorStatus`` / ``data.windowStatus``
            # at root, which worked on the 2023-era myVW backend. Newer
            # firmware (and the parallel zackcornelius VW NA work)
            # confirms the modern shape is ``data.exteriorStatus.*``.
            # Try both: root for the legacy install base, exteriorStatus
            # for current firmware. First non-empty wins.
            door_status = (
                v(vehicle_raw, "exteriorStatus", "doorStatus")
                or v(vehicle_raw, "doorStatus")
                or {}
            )
            overall_lock = (
                v(vehicle_raw, "exteriorStatus", "doorLockStatus")
                or v(door_status, "overallStatus")
            )
            if isinstance(overall_lock, str):
                d.doors_locked = overall_lock.upper() == "LOCKED"
            # zackcornelius iterates the doorStatus dict items so
            # firmware-specific door-id sets work without an enum list.
            # We keep both: explicit ID list first for the legacy
            # shape, dict-iteration fallback for the modern one.
            door_keys = ("frontLeftDoor", "frontRightDoor", "rearLeftDoor", "rearRightDoor")
            door_states = [v(door_status, k) for k in door_keys]
            if not any(isinstance(s, str) for s in door_states) and isinstance(door_status, dict):
                door_states = [
                    val for key, val in door_status.items()
                    if key != "doorStatusTimestamp" and val != "NOTAVAILABLE"
                ]
            if any(isinstance(s, str) for s in door_states):
                d.doors_open = any(
                    isinstance(s, str) and s.upper() == "OPEN" for s in door_states
                )
            trunk = v(door_status, "trunk")
            if isinstance(trunk, str):
                d.trunk_open = trunk.upper() == "OPEN"
            hood = v(door_status, "hood") or v(vehicle_raw, "exteriorStatus", "hood")
            if isinstance(hood, str):
                d.hood_open = hood.upper() == "OPEN"

            # v2.10.0 (#322) — Windows, same root + exteriorStatus
            # fallback chain.
            win = (
                v(vehicle_raw, "exteriorStatus", "windowStatus")
                or v(vehicle_raw, "windowStatus")
                or {}
            )
            window_keys = (
                "frontLeftWindow", "frontRightWindow",
                "rearLeftWindow", "rearRightWindow",
            )
            window_states = [v(win, k) for k in window_keys]
            if not any(isinstance(s, str) for s in window_states) and isinstance(win, dict):
                window_states = [
                    val for key, val in win.items()
                    if not key.endswith("Timestamp") and val != "NOTAVAILABLE"
                ]
            if any(isinstance(s, str) for s in window_states):
                d.windows_open = any(
                    isinstance(s, str) and s.upper() == "OPEN" for s in window_states
                )

            # v2.10.0 (#322) — Parking light from exteriorStatus.lightStatus.
            light_status = v(vehicle_raw, "exteriorStatus", "lightStatus")
            if isinstance(light_status, dict):
                # Older firmware reports per-light keys (parkingLight,
                # leftFrontTurnSignal, ...); roll up to a single "any
                # external light on" boolean for the parking_light
                # entity. We pick the parkingLight specifically when
                # present, otherwise fall through to any non-OFF state.
                parking_l = light_status.get("parkingLight")
                if isinstance(parking_l, str):
                    d.parking_light = parking_l.upper() == "ON"
            elif isinstance(light_status, str):
                d.parking_light = light_status.upper() == "ON"

            # GPS — v2.10.0 (#322) — lastParkedLocation fallback for
            # offline cars. Modern VW NA backend caches the last known
            # parking GPS under ``data.lastParkedLocation`` even when
            # the car is OFFLINE and ``vehicleLocation`` is null.
            # v2.11.0 (zackcornelius source-verified) - canonical key
            # is ``location`` (without "vehicle" prefix); kept old key
            # as fallback for any firmware that does ship it.
            pos = (
                v(vehicle_raw, "location")
                or v(vehicle_raw, "vehicleLocation")
                or v(vehicle_raw, "lastParkedLocation")
                or {}
            )
            d.latitude  = v(pos, "latitude")
            d.longitude = v(pos, "longitude")

            # Connection — v2.0.1 (#131 follow-up): defensive parsing.
            # v2.11.0 (zackcornelius source-verified) - canonical online
            # signal is `readiness.readinessStatus.value.connectionState.isOnline`
            # (boolean). Pre-v2.11.0 we read `connectionStatus.connectionState`
            # as a string ("CONNECTED" check) which is a scout-derived
            # guess; the legacy path stays as fallback.
            ready_online = v(
                vehicle_raw, "readiness", "readinessStatus", "value",
                "connectionState", "isOnline",
            )
            if isinstance(ready_online, bool):
                d.is_online = ready_online
            else:
                conn_state = v(vehicle_raw, "connectionStatus", "connectionState")
                if isinstance(conn_state, str):
                    d.is_online = conn_state.upper() == "CONNECTED"

            # Drivetrain type
            engine = v(vehicle_raw, "vehicleType", "engine") or ""
            d.is_electric    = engine in ("BEV", "ELECTRIC")
            d.is_hybrid      = engine == "PHEV"
            d.has_battery    = d.is_electric or d.is_hybrid or d.has_battery
            d.has_combustion = engine in ("PHEV", "ICE", "GASOLINE", "DIESEL") or (
                d.fuel_level is not None
            )

            # v2.5.10 (#323 roberttco — 2023 ID.4 US) — populate
            # last_seen_at from the VW NA RVS response. Pre-v2.5.10 we
            # never set this field for VW NA, so the user-visible
            # "Last Update" sensor effectively showed our local poll
            # time instead of when the car actually reported data to
            # the cloud. Defensive parser: VW NA RVS API has shipped at
            # least 4 different timestamp field-name conventions across
            # firmware generations — try them in priority order, first
            # ISO-8601-looking string wins.
            # v2.11.0 (zackcornelius source-verified) - canonical
            # last-seen field on RVS is `data.timestamp` as epoch-ms.
            # Try epoch-ms first then fall back to ISO strings.
            ts_ms = v(vehicle_raw, "timestamp")
            if isinstance(ts_ms, (int, float)) and ts_ms > 1e12:
                from datetime import datetime as _dt2  # noqa: PLC0415
                try:
                    d.last_seen_at = _dt2.fromtimestamp(
                        ts_ms / 1000, tz=timezone.utc
                    ).isoformat()
                except (ValueError, OSError):
                    pass
            ts_clamp = v(vehicle_raw, "clampStateTimestamp")
            if not d.last_seen_at and isinstance(ts_clamp, (int, float)) and ts_clamp > 1e12:
                from datetime import datetime as _dt2  # noqa: PLC0415
                try:
                    d.last_seen_at = _dt2.fromtimestamp(
                        ts_clamp / 1000, tz=timezone.utc
                    ).isoformat()
                except (ValueError, OSError):
                    pass
            if not d.last_seen_at:
                # Note: upstream zackcornelius uses the field name
                # `instrumentCluserTime` (with the typo - missing 't').
                for path in (
                    ("instrumentCluserTime",),
                    ("vehicleStatusTime",),
                    ("connectionStatus", "lastConnectionTime"),
                    ("connectionStatus", "timestamp"),
                    ("carCapturedTimestamp",),
                    ("powerStatus", "carCapturedTimestamp"),
                    ("lastUpdated",),
                    ("dataTimestamp",),
                ):
                    ts = v(vehicle_raw, *path)
                    if isinstance(ts, str) and len(ts) >= 10 and "T" in ts:
                        d.last_seen_at = ts
                        break

        # ── Charging ──────────────────────────────────────────────────────────
        if isinstance(charge, dict):
            # v2.11.0 (zackcornelius source-verified):
            #   currentChargeState (NOT chargingState)
            #   chargePower (NOT chargePower_kW)
            #   chargeSettings.targetSOCPercentage (NOT chargingSettings.targetSOC_pct)
            d.charging_state    = (
                v(charge, "chargingStatus", "currentChargeState")
                or v(charge, "chargingStatus", "chargingState")
            )
            # v2.0.1 (#131 follow-up) — defensive parsing.
            if isinstance(d.charging_state, str):
                d.is_charging = d.charging_state.upper() == "CHARGING"
            d.charging_power_kw = first_not_none(
                v(charge, "chargingStatus", "chargePower"),
                v(charge, "chargingStatus", "chargePower_kW"),
            )
            plug = v(charge, "plugStatus", "plugConnectionState")
            if isinstance(plug, str):
                d.plug_connected = plug.upper() == "CONNECTED"
                d.plug_state = plug
            # v2.29.x (sstur/vwapp) — plug LOCK state → connector_locked, the most
            # safety-relevant plug signal (whether the cable is latched). vw_na
            # read plugConnectionState but never the lock state; four other brands
            # already map it. NA field is plugStatus.plugLockState ("LOCKED"/...).
            plug_lock = v(charge, "plugStatus", "plugLockState")
            if isinstance(plug_lock, str):
                d.connector_locked = plug_lock.upper() == "LOCKED"
            d.target_soc = first_not_none(
                v(charge, "chargeSettings", "targetSOCPercentage"),
                v(charge, "chargingSettings", "targetSOC_pct"),
            )
            # v2.15.3 (#503, MyVW APK DEX-verified) — the EV traction SoC, range
            # and charged energy live on charge/summary's BatteryStatus object
            # (BatteryAndPlugStatusResponse.batteryStatus), a SIBLING of
            # chargingStatus. The earlier chargingStatus.currentSOCPct read always
            # returned None, and the /hvbattery endpoint (briefly tried in v2.15.2)
            # is only the departure-timer "use HV battery" toggle, not a status
            # read. Read SoC + range + charged-energy from batteryStatus instead.
            bs = v(charge, "batteryStatus") or {}
            soc_charge = v(bs, "currentSOCPct")
            if isinstance(soc_charge, (int, float)) and d.battery_soc is None:
                d.battery_soc = int(soc_charge)
                d.has_battery = True
            # BatteryStatus.cruisingRange = {engineType, range} (km on NA EV)
            cr_range = v(bs, "cruisingRange", "range")
            if isinstance(cr_range, (int, float)):
                if d.range_km is None:
                    d.range_km = int(cr_range)
                if d.electric_range_km is None:
                    d.electric_range_km = int(cr_range)
            # v2.15.3 — BatteryStatus.chargeEnergy is the CURRENT-charge (per-
            # session) value, not a lifetime total (matches the EU data-dict
            # battery_state_report.charge_energy: a 0..1000 kWh gauge that reads
            # 0 when idle). Route it to the per-session sensor, not the lifetime
            # total_charged_energy_kwh.
            ce = v(bs, "chargeEnergy")
            if isinstance(ce, (int, float)) and ce >= 0 and d.charge_session_energy_kwh is None:
                d.charge_session_energy_kwh = float(ce)
            # charge-complete ETA — field is bare remainingChargingTimeToComplete;
            # the prior ``_min`` suffix never matched (always None).
            remaining_min = safe_int(v(charge, "chargingStatus", "remainingChargingTimeToComplete"))
            if remaining_min is not None and remaining_min > 0:
                d.charge_complete_eta = datetime.now(tz=timezone.utc) + timedelta(minutes=remaining_min)

        # ── Climate ────────────────────────────────────────────────────────────
        # v2.10.0 (#322 roberttco) — VW NA climate response uses the
        # ``climateStatusReport`` / ``climateSettings`` naming instead of
        # the EU-style ``climatisationStatus`` / ``climatisationSettings``
        # that the pre-v2.10.0 parser looked for. Try the NA naming
        # first (current backend), fall back to the EU naming for any
        # legacy install that still ships the older shape.
        if isinstance(climate, dict):
            d.climatisation_state = (
                # v2.11.0 (zackcornelius source-verified) - canonical
                # key is `climateStatusInd` (NOT climateState).
                v(climate, "climateStatusReport", "climateStatusInd")
                or v(climate, "climateStatusReport", "climateState")
                or v(climate, "climateStatusReport", "state")
                or v(climate, "climatisationStatus", "climatisationState")
            )
            d.climatisation_active = d.climatisation_state not in (None, "OFF", "off")
            # v2.29.x (sstur/vwapp) — minutes left until the cabin reaches target.
            # NA field is climateStatusReport.remainingClimatizationTimeMin; feeds
            # the existing cross-brand climate_remaining_time_min sensor.
            rem = safe_int(
                v(climate, "climateStatusReport", "remainingClimatizationTimeMin")
            )
            if rem is not None and rem >= 0:
                d.climate_remaining_time_min = rem
            # Settings block: target temperature. NA backend reports
            # this in either Celsius (modern firmware on ID.4) or
            # Fahrenheit + Kelvin depending on the user's app preference.
            settings = (
                v(climate, "climateSettings")
                or v(climate, "climatisationSettings")
                or {}
            )
            if isinstance(settings, dict):
                # Try Celsius first (already converted), then Kelvin (EU
                # historical), then Fahrenheit (NA user-pref case).
                temp_c = settings.get("targetTemperatureInCelsius")
                if isinstance(temp_c, (int, float)):
                    d.target_temperature = float(temp_c)
                else:
                    temp_k_val = settings.get("targetTemperature_K") or settings.get(
                        "targetTemperatureInKelvin"
                    )
                    temp_k = safe_float(temp_k_val) if temp_k_val is not None else None
                    if temp_k is not None and temp_k > 200:
                        d.target_temperature = round(temp_k - 273.15, 1)
                    else:
                        temp_f = settings.get("targetTemperatureInFahrenheit")
                        if isinstance(temp_f, (int, float)):
                            d.target_temperature = round((temp_f - 32) * 5 / 9, 1)

        d.is_electric    = d.has_battery and not d.has_combustion
        d.is_hybrid      = d.has_battery and d.has_combustion

        # v2.10.0 (Group C). Privileges + subscription block.
        # Soft-fail by design (see get_subscription_privileges docstring):
        # any HTTP error returned an empty dict so we just skip the
        # parser block here. The cross-brand sensors (subscription_*,
        # capabilities_count) stay None / hidden when this dict is empty
        # because of the existing phantom-protection gate.
        if isinstance(privileges, dict) and privileges:
            if privileges.get("subscription_active") is not None:
                d.subscription_active = privileges["subscription_active"]
            if privileges.get("subscription_expiry_at"):
                d.subscription_expiry_at = privileges["subscription_expiry_at"]
                # Derive days-remaining from the timestamp so HA can render
                # a "Connect renews in N days" sensor. Same calculation as
                # the SEAT/CUPRA + VW EU branches.
                try:
                    exp_dt = datetime.fromisoformat(
                        privileges["subscription_expiry_at"].replace("Z", "+00:00")
                    )
                    if exp_dt.tzinfo is None:
                        exp_dt = exp_dt.replace(tzinfo=timezone.utc)
                    now_utc = datetime.now(tz=timezone.utc)
                    d.subscription_days_remaining = (exp_dt - now_utc).days
                    # If the privileges payload omitted the active flag,
                    # derive it from the expiry: past = False, future = True.
                    if d.subscription_active is None:
                        d.subscription_active = exp_dt > now_utc
                except (ValueError, TypeError) as exc:
                    _LOGGER.debug(
                        "VW NA: could not parse subscription expiry %s (%s)",
                        privileges["subscription_expiry_at"], exc,
                    )
            cap_count = privileges.get("capabilities_count")
            if isinstance(cap_count, int) and cap_count >= 0:
                d.capabilities_count = cap_count

        # v2.2.1 Phase 8 PR #5 — cross-brand car_type derivation.
        # VW NA Kombi doesn't ship a direct `carType` enum — derive
        # from has_battery + has_combustion. Never overwrites.
        from .._util import derive_car_type_if_missing  # noqa: PLC0415

        derive_car_type_if_missing(d)

        return d

    async def get_capabilities(self, vin: str) -> dict[str, Any]:  # noqa: ARG002
        """VW NA does not expose a discrete capabilities endpoint.

        Returning ``{}`` keeps the interface consistent with the other
        clients so the coordinator can call this without feature
        detection. Buttons will not be capability-gated for VW NA until
        an endpoint is documented.
        """
        return {}

    async def _carnet_command(
        self,
        method: str,
        url: str,
        vin: str,
        json: dict[str, Any] | None = None,
    ) -> Any:
        """v2.29.x (sstur/vwapp, APK + live-verified 2026-07-30) — issue an NA
        remote command authorised with the per-vehicle carnetVehicleToken.

        VW moved NA remote commands behind the same S-PIN ``carnetVehicleToken``
        the reads now require: with the plain access_token every command returns
        ``403 USER_NOT_AUTHORIZED`` and lock/unlock is silently ignored (VW drops
        the unknown ``action`` field). Reuse the CACHED read-session carnet token
        (``_get_read_session_token`` — no extra S-PIN spend) as the
        ``Authorization: Bearer``. When no carnet token is available (no S-PIN, or
        the exchange is disabled) fall back to the plain access_token path so a
        non-S-PIN account is no worse off than before.

        NOT YET live-confirmed on our own stack (we have no NA car): the routes,
        HTTP methods and bodies are taken verbatim from sstur/vwapp's live-
        verified client, which fixed why NA commands never actuated. See the
        #1012 / #915 lineage and the open "testers wanted" issue.
        """
        carnet = await self._get_read_session_token(vin)
        if carnet:
            headers = dict(self._READ_HEADERS)
            headers["Authorization"] = f"Bearer {carnet}"
            try:
                return await self._request(
                    method, url, headers=headers, _carnet_auth=True, json=json
                )
            except APIError as err:
                # A 401/403 with the carnet token means it was rejected/expired —
                # drop it so the NEXT command re-mints (subject to the lockout
                # guard). Never re-mint in this call (avoids a 2nd S-PIN attempt
                # back-to-back).
                if (err.status or 0) in (401, 403):
                    self._read_session_tokens.pop(
                        self._vin_to_uuid.get(vin, vin), None
                    )
                raise
        return await self._request(method, url, json=json)

    async def command_lock(self, vin: str) -> None:
        """NA lock — v2.29.x (sstur/vwapp): PUT ``{lock: true}`` with the
        carnetVehicleToken as Bearer.

        The old ``POST {"action":"lock"}`` on the access_token was silently
        ignored by VW (unknown ``action`` field) — the command was accepted but
        never actuated. VW's own app PUTs ``{lock: boolean}`` to
        ``/lockunlock/v1/vehicle/{uuid}`` with the carnet token as the bearer.
        """
        uuid = self._vin_to_uuid.get(vin, vin)
        await self._carnet_command(
            "PUT",
            f"{self._base}/lockunlock/v1/vehicle/{uuid}",
            vin,
            json={"lock": True},
        )

    async def command_unlock(self, vin: str, spin: str = "") -> None:  # noqa: ARG002
        """NA unlock — v2.29.x (sstur/vwapp): PUT ``{lock: false}`` with the
        carnetVehicleToken as Bearer (see :meth:`command_lock`).

        The ``spin`` argument is kept for signature compatibility; the S-PIN is
        consumed by the carnet-token exchange (``_get_read_session_token``), not
        sent in the request. The old two-step ``/challenge`` + ``/spin`` handshake
        with an ``X-Spin-Session`` header and ``{"action":"unlock"}`` body never
        actuated (VW ignores the unknown ``action`` field).
        """
        uuid = self._vin_to_uuid.get(vin, vin)
        await self._carnet_command(
            "PUT",
            f"{self._base}/lockunlock/v1/vehicle/{uuid}",
            vin,
            json={"lock": False},
        )

    async def command_start_climate(self, vin: str) -> None:
        """NA pre-trip climate start.

        v2.29.x (#659, sstur/vwapp) — carnet-gated like every other NA command:
        with the plain access_token it 403s USER_NOT_AUTHORIZED (same signature
        #659 reported for wake/flash). The old EU-style ``/climatisation/start``
        404 fallback is dropped: v2.20.0 confirmed the myVW app only exposes the
        ``/pretripclimate/*`` family, so that alias never resolved.
        """
        uuid = self._vin_to_uuid.get(vin, vin)
        await self._carnet_command(
            "POST", f"{self._base}/ev/v1/vehicle/{uuid}/pretripclimate/start",
            vin, json={},
        )

    async def command_stop_climate(self, vin: str) -> None:
        """NA pre-trip climate stop. See command_start_climate (carnet-gated)."""
        uuid = self._vin_to_uuid.get(vin, vin)
        await self._carnet_command(
            "POST", f"{self._base}/ev/v1/vehicle/{uuid}/pretripclimate/stop",
            vin, json={},
        )

    async def command_start_charging(self, vin: str) -> None:
        uuid = self._vin_to_uuid.get(vin, vin)
        # v2.29.x (sstur/vwapp) — body {actionMode:"immediate"} + carnet Bearer;
        # the old empty-body POST on the access_token was ignored / 403'd.
        await self._carnet_command(
            "POST", f"{self._base}/ev/v1/vehicle/{uuid}/charging/start", vin,
            json={"actionMode": "immediate"},
        )

    async def command_stop_charging(self, vin: str) -> None:
        uuid = self._vin_to_uuid.get(vin, vin)
        await self._carnet_command(
            "POST", f"{self._base}/ev/v1/vehicle/{uuid}/charging/stop", vin,
            json={"actionMode": "immediate"},
        )

    async def command_flash(
        self,
        vin: str,
        latitude: float | None = None,  # noqa: ARG002
        longitude: float | None = None,  # noqa: ARG002
        duration_s: int = 10,  # noqa: ARG002 - value not grounded for this brand
        honk: bool = False,  # noqa: ARG002 - value not grounded for this brand
    ) -> None:
        uuid = self._vin_to_uuid.get(vin, vin)
        # v2.20.0 (APK audit) — myVW 2026.5.27 exposes honk/flash as the dedicated
        # top-level service /honkflash/v1/vehicle/{id} (parallel to /lockunlock/v1);
        # the old /ev/.../horn-and-lights path doesn't exist → 404. NOTE: the exact
        # action/mode body value is not yet confirmed (FLASH_ONLY is the EU value);
        # live-capture on a real myVW before relying on flash-only vs honk+flash.
        # v2.29.x (#659) — carnet-gated: Rizencip's Tiguan 403'd USER_NOT_AUTHORIZED
        # on flash with the plain access_token, the same wall wake hit.
        await self._carnet_command(
            "POST", f"{self._base}/honkflash/v1/vehicle/{uuid}", vin,
            json={"action": "FLASH_ONLY"},
        )

    async def command_wake(self, vin: str) -> None:
        uuid = self._vin_to_uuid.get(vin, vin)
        # v2.20.0 (APK audit) — no /wakeup route exists on con-veh.net; a fresh
        # status is forced via the vehicle-status-request refresh endpoint.
        # v2.29.x (sstur/vwapp) — carnet-gated: with the plain access_token this
        # 403s USER_NOT_AUTHORIZED. This is our freshness lever, so it matters.
        await self._carnet_command(
            "POST", f"{self._base}/rvs/v1/vehicle/{uuid}/refresh", vin, json={}
        )

    async def command_set_target_soc(self, vin: str, target: int) -> None:
        uuid = self._vin_to_uuid.get(vin, vin)
        # v2.20.0 (APK audit) — myVW models use targetSOCPercentage (matches the
        # read side); the invented targetSOC_pct was silently ignored.
        # v2.29.x (sstur/vwapp) — set-charge-limit is a PUT that REPLACES the whole
        # charging-settings object, so read the current settings and merge the new
        # target rather than PUTting a bare {targetSOCPercentage} (which would wipe
        # the other charge settings). carnet Bearer. The old POST never actuated.
        merged: dict[str, Any] = {"targetSOCPercentage": target}
        try:
            carnet = await self._get_read_session_token(vin)
            summary = await self._read(
                f"{self._base}/ev/v1/vehicle/{uuid}/charge/summary", carnet
            )
            if isinstance(summary, dict):
                cur = summary.get("chargeSettings") or summary.get("chargingSettings")
                if isinstance(cur, dict) and cur:
                    merged = {**cur, "targetSOCPercentage": target}
        except APIError:
            pass  # fall back to the bare target below
        await self._carnet_command(
            "PUT", f"{self._base}/ev/v1/vehicle/{uuid}/charging/settings", vin,
            json=merged,
        )

    async def command_set_climate_temperature(self, vin: str, temp_c: float) -> None:
        uuid = self._vin_to_uuid.get(vin, vin)
        # v2.29.x (sstur/vwapp) — PUT the full climate-settings object with a
        # NESTED targetTemperature {temperature, unit}; VW replaces the whole
        # object, so read + merge to preserve the other zones/toggles. carnet
        # Bearer. The old POST of a scalar {targetTemperature_K} was dropped.
        target = {"temperature": round(temp_c, 1), "unit": "celsius"}
        body: dict[str, Any] = {"targetTemperature": target}
        try:
            carnet = await self._get_read_session_token(vin)
            summary = await self._read(
                f"{self._base}/ev/v1/vehicle/{uuid}/climate/summary", carnet
            )
            if isinstance(summary, dict):
                cur = (
                    summary.get("climateSettings")
                    or summary.get("climatisationSettings")
                )
                if isinstance(cur, dict) and cur:
                    body = {**cur, "targetTemperature": target}
        except APIError:
            pass
        await self._carnet_command(
            "PUT", f"{self._base}/ev/v1/vehicle/{uuid}/pretripclimate/settings",
            vin, json=body,
        )

    async def command_start_window_heating(self, vin: str) -> None:
        """NA window heating start — ``/pretripclimate/windowheating/start``.

        v2.29.x (#659, sstur/vwapp) — carnet-gated like the other NA commands;
        the EU-style ``/climatisation/*`` 404 fallback is dropped (v2.20.0: only
        the pretripclimate family is exposed on con-veh.net).
        """
        uuid = self._vin_to_uuid.get(vin, vin)
        await self._carnet_command(
            "POST",
            f"{self._base}/ev/v1/vehicle/{uuid}/pretripclimate/windowheating/start",
            vin, json={},
        )

    async def command_stop_window_heating(self, vin: str) -> None:
        """NA window heating stop. See command_start_window_heating (carnet-gated)."""
        uuid = self._vin_to_uuid.get(vin, vin)
        await self._carnet_command(
            "POST",
            f"{self._base}/ev/v1/vehicle/{uuid}/pretripclimate/windowheating/stop",
            vin, json={},
        )

    async def command_set_departure_timer(
        self,
        vin: str,
        timer_id: int,
        enabled: bool,
        departure_time: str | None,
        recurring_on: list[str] | None = None,
    ) -> None:
        # v2.0.0 (Big-Bang) — VW NA's MyVW Cloud accepts the same
        # ``recurringOn`` field shape as the EU CARIAD-BFF backend
        # (verified against MyVW 2.x app traffic).
        uuid = self._vin_to_uuid.get(vin, vin)
        payload: dict[str, Any] = {"id": timer_id, "enabled": enabled}
        if departure_time:
            payload["departureTime"] = {"time": departure_time}
        if recurring_on:
            valid = {"MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY",
                     "FRIDAY", "SATURDAY", "SUNDAY"}
            cleaned = [d.upper() for d in recurring_on if d.upper() in valid]
            if cleaned:
                payload["recurringOn"] = cleaned
                payload["type"] = "RECURRING"
        # v2.20.0 (APK audit) — myVW's EV climate routes are the pretripclimate/*
        # family; the EU-style climatisation/timers path is not exposed on
        # con-veh.net → 404.
        # v2.29.x (#659) — carnet-gated like every other NA command.
        await self._carnet_command(
            "POST", f"{self._base}/ev/v1/vehicle/{uuid}/pretripclimate/timers",
            vin, json=payload,
        )

    # ── HTTP helpers ──────────────────────────────────────────────────────────

    async def _read(self, url: str, carnet_token: str | None) -> Any:
        """v2.15.5 (#503) — a data read (rvs/ev), optionally SPIN-authorised.

        When ``carnet_token`` is set, authorise with the per-vehicle
        carnetVehicleToken (Bearer) and apply the peer Car-Net header block —
        ONLY here, on the data reads. The login + garage path and every other
        request keep ``_request``'s default headers + access_token, so the
        already-working 200 path is untouched.

        ``carnet_token=None`` (no S-PIN, or the exchange was skipped/failed)
        delegates to the plain ``_get`` so non-S-PIN users behave exactly as
        before.
        """
        if not carnet_token:
            return await self._get(url)
        headers = dict(self._READ_HEADERS)
        headers["Authorization"] = f"Bearer {carnet_token}"
        # _carnet_auth=True: tell _request not to overwrite the carnet Bearer
        # with the access_token, and to skip the 401-refresh retry (a 401 here
        # means the carnet token expired/was rejected, not the access_token).
        return await self._request("GET", url, headers=headers, _carnet_auth=True)

    async def _get(self, url: str, **kwargs: Any) -> Any:
        return await self._request("GET", url, **kwargs)

    async def _post(self, url: str, **kwargs: Any) -> Any:
        return await self._request("POST", url, **kwargs)

    async def _request(
        self,
        method: str,
        url: str,
        retry: bool = True,
        _carnet_auth: bool = False,
        **kwargs: Any,
    ) -> Any:
        from aiohttp import ClientTimeout  # noqa: PLC0415
        if not self._tokens:
            raise AuthenticationError("Not authenticated")
        headers = kwargs.pop("headers", {})
        if _carnet_auth:
            # v2.15.5 (#503) — carnetVehicleToken read: the caller already set
            # Authorization (Bearer <carnetVehicleToken>) + the peer header
            # block. Do NOT clobber it with the access_token, and do NOT widen
            # the header set (peer headers only). A bare Accept default is
            # filled only if the caller omitted one.
            headers.setdefault("Accept", "application/json")
        else:
            headers.update({
                "Authorization": f"Bearer {self._tokens.access_token}",
                "User-Agent":    BRAND_VW_NA.user_agent,
                "Accept":        "application/json",
            })
        # v2.15.9 (#593) — a transport-level timeout/disconnect during the HTTP
        # round-trip is a backend hiccup, NOT our bug. A raw
        # ``ClientConnectorError``/``TimeoutError`` here used to propagate out of
        # ``get_status`` and land in the Error Reporter (per-VIN poll failure) as
        # if the integration had broken. Re-raise it as
        # ``UpstreamUnavailableError`` — the same typed "backend temporarily
        # unavailable" the coordinator already de-escalates to a transient
        # no-data poll and explicitly does NOT error-report (#438/#465), exactly
        # mirroring the v2.15.8 EU-login fix (#576/#578). Only connection/timeout
        # errors are mapped; genuine HTTP responses (4xx/5xx, incl. auth 401 and
        # data-plane 403) still flow through the status checks below → real
        # ``APIError``s are raised and reported as before. ``ClientConnectorError``
        # is a subclass of ``ClientConnectionError``, so it is covered.
        try:
            async with self._session.request(
                method, url, headers=headers, timeout=ClientTimeout(total=30),
                **kwargs,
            ) as resp:
                if resp.status == 401 and retry and not _carnet_auth:
                    await self._refresh()
                    return await self._request(method, url, retry=False, **kwargs)
                if resp.status == 204:
                    return {}
                if resp.status not in (200, 202, 207):
                    body = await resp.text()
                    raise APIError(resp.status, url, body)
                return await resp.json()
        except (TimeoutError, ClientConnectionError) as exc:
            # asyncio.TimeoutError aliases the builtin TimeoutError on py3.11+,
            # so an aiohttp total-timeout is covered here too.
            raise UpstreamUnavailableError(504, brand=BRAND_VW_NA.name) from exc

    async def _refresh(self) -> None:
        if self._tokens and self._tokens.refresh_token:
            try:
                # #1012 — replay the login's PKCE verifier: the con-veh server
                # binds the refresh to it. Empty on a token set from before the
                # fix, in which case the refresh fails and we fall through to a
                # full re-login below (which now carries the verifier again).
                self._tokens = await self._auth.refresh(
                    self._tokens.refresh_token,
                    code_verifier=self._tokens.code_verifier,
                )
                return
            except TokenExpiredError:
                pass
        await self.authenticate()

    @staticmethod
    def _val(data: dict, *path: str, default: Any = None) -> Any:
        node: Any = data
        for key in path:
            if not isinstance(node, dict):
                return default
            node = node.get(key, default)
            if node is None:
                return default
        return node
