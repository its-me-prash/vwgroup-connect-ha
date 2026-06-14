# Copyright 2026 Prash Balan (@its-me-prash) — Apache License 2.0
# SPDX-License-Identifier: Apache-2.0
"""Base async API client — injected aiohttp session, token management."""

from __future__ import annotations

import asyncio
import logging
import time
from contextlib import contextmanager
from typing import Any, Callable, Iterator

from aiohttp import (
    ClientConnectorError,
    ClientPayloadError,
    ClientSession,
    ClientTimeout,
    ServerDisconnectedError,
)

from ..auth.idk import IDKAuth
from .graphql import VehicleImageFetcher, VehicleImageData
from ..exceptions import APIError, AuthenticationError, TokenExpiredError
from ..models import BrandConfig, TokenSet, VehicleData

_LOGGER = logging.getLogger(__name__)

_REQUEST_TIMEOUT = 60

# Token-refresh storm protection (v1.8.7).
# Capped at 3 successful-or-attempted refreshes per rolling hour. If the
# CARIAD identity backend hands out short-lived tokens or returns transient
# 401s, this prevents us from looping login → 401 → login until the IP gets
# rate-limited or the account temporarily locked. Patterns from
# `skodaconnect/myskoda` #976 and `upstream/homeassistant-volkswagencarnet`
# #683 — both repos shipped fixes after users reported account suspensions
# triggered by integrations refreshing tokens every poll cycle.
_REFRESH_MAX_PER_HOUR = 3
_REFRESH_WINDOW_S = 3600

# v2.9.0 - VW account-lock detection. After the 2026-05-31 ecosystem-
# wide VW Auth chaos, oliverrahner (volkswagencarnet#332) and others
# reported their underlying brand account getting locked for ~24h
# after too many failed token-refresh attempts. The lock manifests as
# HTTP 423 (Locked) or HTTP 403 with a throttling body marker on
# ``/auth/v1/idk/oidc/token``. Coordinator surfaces a Repair issue
# once we see ``_LOCK_THRESHOLD`` such responses inside
# ``_LOCK_WINDOW_S`` so the user understands why polling went silent.
_LOCK_THRESHOLD = 3
_LOCK_WINDOW_S = 1800
_LOCK_BODY_MARKERS: tuple[str, ...] = (
    "throttle",
    "rate limit",
    "too many",
    "account locked",
    "temporarily locked",
)

# v2.5.2 — Silent scout-channel expansion guardrails.
#   _PROBE_INTERVAL_S    — minimum seconds between probe passes per VIN
#   _PROBE_TIMEOUT_S     — per-probe HTTP timeout (kept short — probes are best-effort)
#   _PROBE_BUDGET_S      — total time budget for one pass before we bail
#   _PROBE_TOKEN_GUARD   — skip pass when last_rate_limit_remaining is at or below this
#   _PROBE_CB_THRESHOLD  — disable probes after this many consecutive auth-storm hits
_PROBE_INTERVAL_S    = 3600          # 1 hour
_PROBE_TIMEOUT_S     = 5
_PROBE_BUDGET_S      = 30
_PROBE_TOKEN_GUARD   = 50
_PROBE_CB_THRESHOLD  = 3


class _AuthStormSignal(Exception):
    """Internal sentinel — a probe got HTTP 401.

    Distinct from ``AuthenticationError`` so the probe pass can abort
    cleanly without poisoning the production ``_request`` retry path.
    Never escapes the probe runner.
    """

# Transient network exceptions that should be retried with the same
# exponential backoff as 5xx server errors. Verified against:
#   - `mitch-dc/volkswagen_we_connect_id` #166 (`socket.gaierror` /
#     `ClientConnectorError` was being misclassified as auth failure)
#   - `skodaconnect/homeassistant-myskoda` #731 ("server unavailable" UX)
# DNS, connection refused, and mid-stream disconnects from the CARIAD BFF
# happen routinely on weekends and during VAG maintenance windows. They are
# not auth failures and must not trigger reauth.
_TRANSIENT_NET_ERRORS: tuple[type[BaseException], ...] = (
    ClientConnectorError,
    ServerDisconnectedError,
    ClientPayloadError,
    asyncio.TimeoutError,
)


class CariadBaseClient:
    """Base class for all CARIAD brand API clients.

    Subclasses implement get_vehicles() and get_status(vin).
    Token refresh is handled transparently.
    """

    def __init__(
        self,
        session: ClientSession,
        brand: BrandConfig,
        email: str,
        password: str,
        spin: str = "",
    ) -> None:
        self._session = session
        self._brand = brand
        self._email = email
        self._password = password
        self._spin = spin
        self._tokens: TokenSet | None = None
        # v2.12.0 — when the VW EU strategy chain falls through to the EU
        # Data Act portal (cookie-based, read-only), the connector is
        # retained here so the brand client's get_status routes through
        # it instead of the (dead) token-based BFF. None = token mode.
        self._eu_portal: Any = None
        # v2.14.0 — OPT-IN, BETA. When the user explicitly chooses the
        # volkswagen.de website-authproxy mode, the coordinator flips this
        # flag (set_website_authproxy_mode) BEFORE authenticate(). It makes
        # authenticate() use the cookie-based WebsiteAuthProxyConnector
        # (retained on _website_proxy) as the sole strategy and routes
        # get_vehicles/get_status through it — exactly the way _eu_portal is
        # wired. Default False → every existing strategy path is untouched.
        self._use_website_proxy: bool = False
        self._website_proxy: Any = None
        # When the website-authproxy login surfaces an email-OTP challenge,
        # the code the user enters in the config flow is handed to the
        # connector via this field before authenticate() runs.
        self._website_proxy_otp: str | None = None
        self._image_data: dict[str, VehicleImageData] = {}
        self._refresh_lock: asyncio.Lock | None = None
        # Sliding window of token refresh attempt timestamps (monotonic seconds).
        # Pruned to the last `_REFRESH_WINDOW_S` on every refresh attempt.
        # Prevents the spiral documented in myskoda #976 / volkswagencarnet #683.
        self._refresh_history: list[float] = []
        # v2.9.0 - VW account-lock detection sliding window. Tuples of
        # (monotonic_seconds, http_status). Coordinator drains via
        # ``self.account_lock_signal`` to decide whether to raise the
        # Repair issue. Pruned to ``_LOCK_WINDOW_S`` on every append.
        self._lock_history: list[tuple[float, int]] = []
        # Bool the coordinator polls each cycle: True once the lock
        # threshold has been crossed inside the window. Cleared after
        # the first successful auth lands.
        self.account_lock_detected: bool = False
        self._auth = IDKAuth(session, brand)
        # v1.9.0 — Vehicle Data Scout opt-in stash. Brand clients populate
        # this in ``get_status`` so the coordinator can run
        # ``detect_unexpected`` over the raw responses without each brand
        # client having to import the detector. Keys are logical endpoint
        # names matching ``EXPECTED_KEYS[brand][endpoint]`` (e.g.
        # ``"vehicle-status"``); values are the unparsed dict from the
        # backend. Re-populated per poll — never accumulates across polls.
        self.last_raw_responses: dict[str, dict[str, Any]] = {}
        # v1.19.1 — Pycupra-style API quota visibility. Most VAG backends
        # send X-RateLimit-Remaining (and sometimes X-RateLimit-Limit /
        # X-RateLimit-Reset) on successful responses. We capture the
        # latest value so the coordinator can surface it as a
        # ``requests_remaining_today`` sensor — users see how close they
        # are to the daily quota cap (community research: MyCupra/MySeat
        # ~1500/day, OLA + mysmob behave similarly). None means we have
        # never observed the header (older backends don't send it on
        # every endpoint).
        self.last_rate_limit_remaining: int | None = None
        self.last_rate_limit_limit: int | None = None
        self.last_rate_limit_reset_at: str | None = None
        # v1.19.2 (#118 eismarkt) — token persistence callback hook.
        # Coordinator wires this to ``TokenStorage.save`` so every
        # successful authenticate() / _refresh_tokens() result is
        # persisted across HA restarts + HACS updates. Optional —
        # if None (e.g. tests without storage), tokens stay in-memory.
        # Signature: ``async def on_tokens_changed(tokens: TokenSet) -> None``
        self.on_tokens_changed: Any | None = None

        # v2.5.2 — Silent scout-channel expansion (see ``_v3_probes.py``).
        # The probe pass runs at most once per ``_PROBE_INTERVAL_S`` per VIN
        # and feeds GET responses into ``last_raw_responses`` so the
        # coordinator's scout walk picks them up like any other response.
        # All state is fail-safe: probe errors NEVER affect production
        # polling, and the circuit-breaker auto-disables probes for the
        # session if too many consecutive failures (auth-storm risk).
        self._probe_last_pass_at: dict[str, float] = {}  # vin -> monotonic
        self._probe_consecutive_fails: int = 0
        self._probe_disabled: bool = False

        # v2.8.0 quick win D — per-job parser-health counters. Each brand
        # client's get_status() wraps each job-extraction block in a
        # self._parser_job("job_name") context manager that increments
        # successes/failures. Coordinator exposes the snapshot in diagnostics.
        self.parser_stats: dict[str, dict[str, int | str]] = {}

    @property
    def brand(self) -> BrandConfig:
        """Brand configuration."""
        return self._brand

    async def authenticate_via_device_grant(
        self,
        on_user_code: Callable[[Any], None] | None = None,
    ) -> None:
        """v2.6.0 — OAuth Device Authorization Grant (RFC 8628) login.

        Browser-based, password-less, refresh-token-friendly login flow.
        The IDP returns a real refresh_token so no ~2 h re-login penalty
        (unlike hybrid_full). The end user opens a URL in any browser,
        signs in with their VW Brand ID credentials, and approves the
        device — Home Assistant never sees the password.

        Brand support (per ``cariad.auth._device_grant.DAG_ENABLED_BRANDS``):
          ✅ audi, skoda, seat, cupra
          ❌ volkswagen — VW EU's consumer client_id is not whitelisted
            for device grant by the IDP; use the standard
            ``authenticate()`` chain (hybrid_full → classic) instead.

        Args:
            on_user_code: optional callback invoked with the
                ``DeviceCodeResponse`` as soon as the IDP issues a
                device_code. UI layers (config_flow, service calls)
                use it to display ``user_code`` + ``verification_uri_complete``
                to the end user. If ``None``, the flow runs but the user
                will not be told where to authorize, so the polling
                deadline will simply expire.

        Raises:
            AuthenticationError: if the brand is not DAG-eligible, the
                IDP rejects the client_id, the grant expires before
                user approval, or the user declines in the browser.
        """
        from ..auth._device_grant import (  # noqa: PLC0415
            DeviceAuthorizationGrant,
            is_dag_eligible,
        )

        if not is_dag_eligible(self._brand.name):
            raise AuthenticationError(
                f"Device grant not enabled for brand {self._brand.name} "
                f"by the VW IDP. Use authenticate() with email + password."
            )

        # Match scope to what the standard authenticate() flow asks for
        # — the IDP enforces scopes at token level rather than at
        # device-authorization level, so we want parity with the rest
        # of the integration.
        dag = DeviceAuthorizationGrant(
            self._session,
            self._brand.client_id,
            scope=self._brand.scope,
        )
        self._tokens = await dag.run(on_user_code=on_user_code)
        _LOGGER.info(
            "Authenticated for brand %s via device grant (refresh_token: %s)",
            self._brand.name,
            "yes" if self._tokens and self._tokens.refresh_token else "no",
        )
        await self._notify_tokens_changed()

    # v2.9.0 - provenance canary, see ``_canaries.py``. Referenced as
    # a class attribute so any port of the multi-strategy resolver in
    # this class carries the marker along into the destination repo.
    _PROVENANCE_AUTH_RESOLVER = "cariad_resolver_provenance_kw7zq3p1_2026"

    async def authenticate(self, mfa_code: str | None = None) -> None:
        """Perform full login and store tokens.

        v2.6.0 multi-strategy resolver. The 2026-05-27 Cariad WAF migration
        gated the BFF token endpoint behind Google Play Integrity, which
        Python clients cannot satisfy. The OIDC hybrid_full flow
        (response_type=code id_token token) bypasses that wall entirely by
        having Auth0 deliver tokens directly in the callback URL fragment.

        Per-brand strategy (in priority order, fallback on AuthenticationError):
          - volkswagen  : hybrid_full → classic auth-code → data_act_portal
          - audi        : classic auth-code → hybrid_full → data_act_portal
                          (Audi still issues usable refresh_tokens through
                          the qmauth assertion path; prefer that to avoid
                          the ~2h re-login penalty of hybrid_full)
          - skoda/seat  : classic auth-code → data_act_portal
            /cupra
          - others      : classic auth-code only (unchanged)

        The data_act_portal strategy is a last-resort read-only fallback.
        When it succeeds the TokenSet carries strategy="data_act_portal"
        and the coordinator switches into read-only mode (command entities
        disabled, polling throttled to 15 min).

        Trade-off for hybrid_full success: no usable refresh_token is
        returned, so re-login fires every ~2 h. ``_refresh_tokens()``
        detects the empty refresh_token and calls ``authenticate()`` again
        transparently. The 5-strategy storm-guard in _refresh_tokens
        prevents runaway loops.
        """
        # Strategy descriptor: (kind, kwargs) where kind is "idk" for the
        # standard IDKAuth.authenticate path and "data_act_portal" for the
        # last-resort read-only fallback.
        strategies: list[tuple[str, dict[str, bool]]] = []
        # v2.14.0 — when authenticate() is re-driven with an OTP code (e.g. a
        # coordinator reauth for the website-authproxy channel), feed it to the
        # connector so the email-challenge step can complete.
        if self._use_website_proxy and mfa_code:
            self._website_proxy_otp = mfa_code
        # v2.14.0 — OPT-IN website-authproxy mode short-circuits the whole
        # resolver: it is the ONLY strategy when the user selected it, so we
        # never touch the BFF/hybrid/Data-Act chain. Gated on the explicit
        # opt-in flag, so this branch is dead for every other entry.
        if self._use_website_proxy:
            strategies = [("website_authproxy", {})]
        elif self._brand.name == "volkswagen":
            strategies = [
                ("idk", {"hybrid_full": True}),
                ("idk", {"hybrid_full": False}),
                ("data_act_portal", {}),
            ]
        elif self._brand.name == "audi":
            strategies = [
                ("idk", {"hybrid_full": False}),
                ("idk", {"hybrid_full": True}),
                ("data_act_portal", {}),
            ]
        elif self._brand.name in ("skoda", "seat", "cupra", "bentley"):
            strategies = [
                ("idk", {"hybrid_full": False}),
                ("data_act_portal", {}),
            ]
        else:
            strategies = [("idk", {"hybrid_full": False})]

        last_err: Exception | None = None
        for idx, (kind, opts) in enumerate(strategies):
            try:
                if kind == "idk":
                    self._tokens = await self._auth.authenticate(
                        self._email, self._password,
                        mfa_code=mfa_code,
                        **opts,
                    )
                elif kind == "data_act_portal":
                    # v2.12.0 — cookie-based EU Data Act portal connector
                    # (read-only). v2.12.7 — the build+login+sentinel logic
                    # moved to ``_arm_eu_portal`` so the SAME arming can fire
                    # as a runtime fallback when a brand's native data backend
                    # is blocked mid-flight (e.g. CUPRA/SEAT OLA 403) even
                    # though the IDP login still succeeds.
                    await self._arm_eu_portal()
                elif kind == "website_authproxy":
                    # v2.14.0 — OPT-IN, read-only volkswagen.de website
                    # authproxy connector. Only reached when the user opted in
                    # (see the strategy list above), so dormant otherwise.
                    await self._arm_website_proxy()
                else:
                    raise AuthenticationError(f"Unknown strategy kind: {kind}")

                if idx > 0:
                    _LOGGER.info(
                        "Authenticated for brand %s via fallback strategy "
                        "#%d (kind=%s opts=%s) after primary strategy failed: %s",
                        self._brand.name, idx, kind, opts,
                        type(last_err).__name__ if last_err else "?",
                    )
                else:
                    _LOGGER.debug(
                        "Authenticated for brand %s (kind=%s opts=%s)",
                        self._brand.name, kind, opts,
                    )
                # v2.8.0 — capture session cookies into the token set
                # so the next session can hydrate the IDP device-bound
                # cookie and skip the OTP prompt. Only the idk path
                # owns vwgroup.io cookies; the data_act_portal path
                # leaves its session jar alone.
                if (
                    self._tokens is not None
                    and kind == "idk"
                    and hasattr(self._auth, "capture_session_cookies")
                ):
                    captured = self._auth.capture_session_cookies()
                    if captured:
                        self._tokens.auth_cookies = captured
                        _LOGGER.debug(
                            "Captured %d IDP cookies for brand %s on "
                            "successful auth",
                            len(captured), self._brand.name,
                        )
                await self._notify_tokens_changed()
                return
            except AuthenticationError as err:
                last_err = err
                if idx == len(strategies) - 1:
                    raise
                _LOGGER.info(
                    "Auth strategy #%d (kind=%s opts=%s) failed for %s: %s — "
                    "trying next strategy",
                    idx, kind, opts, self._brand.name, err,
                )
            except Exception as err:  # noqa: BLE001
                # v2.7.2 — aiohttp.InvalidURL and similar low-level
                # errors can carry tokens or full OAuth callback URLs
                # in their __str__. Catch any non-AuthenticationError
                # here, log the exception TYPE only (no PII), and
                # convert to an AuthenticationError so downstream
                # handlers see a clean error without the raw URL.
                # Re-raise on the last strategy; otherwise fall through
                # to the next one like AuthenticationError above.
                last_err = err
                _LOGGER.warning(
                    "Auth strategy #%d (kind=%s opts=%s) raised %s for %s "
                    "(message redacted to protect tokens)",
                    idx, kind, opts, type(err).__name__, self._brand.name,
                )
                if idx == len(strategies) - 1:
                    raise AuthenticationError(
                        f"Auth failed with {type(err).__name__} "
                        f"(no usable strategy left)"
                    ) from err

    async def _arm_eu_portal(self) -> None:
        """Build + log in the read-only EU Data Act portal connector and
        retain it on ``self._eu_portal`` with a sentinel TokenSet.

        v2.12.7 — used both by the ``data_act_portal`` login strategy AND as
        a runtime fallback when a brand's native data backend is blocked
        (e.g. the CUPRA/SEAT OLA ``403`` device-attestation wall) while the
        IDP login still succeeds. In that case the login-time fallback never
        fires, so the brand's read methods arm the portal here on a persistent
        native block — reads then degrade to the portal instead of going dark.
        """
        import time as _time  # noqa: PLC0415

        from ..auth._eu_data_act import EUDataActConnector  # noqa: PLC0415

        connector = EUDataActConnector(self._session, brand=self._brand.name)
        await connector.login(self._email, self._password)
        self._eu_portal = connector
        # Sentinel TokenSet: no real token (cookie session), but valid()
        # needs access_token + id_token non-empty so downstream treats us as
        # authenticated. Long expiry so the coordinator doesn't churn
        # re-logins; the connector re-logins on 401/403 via the read methods.
        self._tokens = TokenSet(
            access_token="eu-data-act-portal-cookie-session",
            refresh_token="",
            id_token="eu-data-act-portal-cookie-session",
            expires_at=_time.time() + 3300,
            strategy="data_act_portal",
        )

    def set_website_authproxy_mode(
        self, enabled: bool, *, otp: str | None = None
    ) -> None:
        """v2.14.0 — OPT-IN: route this client through the website authproxy.

        Called by the coordinator (and the config-flow validator) when the
        user explicitly selected the "Volkswagen.de website (beta)" mode.
        Strictly additive: when ``enabled`` is False (the default), nothing
        changes and every existing strategy path runs unmodified. ``otp`` is
        the email-OTP code collected by the config flow, consumed once on the
        next ``authenticate()``.
        """
        self._use_website_proxy = bool(enabled)
        self._website_proxy_otp = otp

    async def _arm_website_proxy(self) -> None:
        """Build + log in the read-only website-authproxy connector.

        v2.14.0 — mirrors ``_arm_eu_portal``: it logs the connector in,
        retains it on ``self._website_proxy`` so the brand client's
        get_vehicles/get_status route through it, and stores a sentinel
        TokenSet (``strategy="website_authproxy"``) so downstream treats the
        client as authenticated and the coordinator forces read-only mode.

        A pending email-OTP challenge raises ``EmailTwoFactorRequiredError``
        unless an OTP code was supplied via ``set_website_authproxy_mode`` —
        the config flow catches that to add the OTP step, and the coordinator
        surfaces the matching Repair issue.
        """
        import time as _time  # noqa: PLC0415

        from ..auth._website_authproxy import (  # noqa: PLC0415
            WebsiteAuthProxyConnector,
        )
        from ..exceptions import EmailTwoFactorRequiredError  # noqa: PLC0415

        connector = WebsiteAuthProxyConnector(
            self._session, self._email, self._password, brand=self._brand.name,
        )
        result = await connector.begin_login()
        if result == "otp_required":
            if not self._website_proxy_otp:
                raise EmailTwoFactorRequiredError()
            ok = await connector.submit_otp(self._website_proxy_otp)
            # OTP is single-use — drop it so a later re-login doesn't reuse it.
            self._website_proxy_otp = None
            if not ok:
                raise AuthenticationError(
                    "Website authproxy: OTP submission did not complete login"
                )
        self._website_proxy = connector
        # Sentinel TokenSet: no usable bearer (cookie session), but valid()
        # needs access_token + id_token non-empty so the client counts as
        # authenticated. Long expiry so the coordinator doesn't churn relogins;
        # the connector re-establishes the session on 401/403 via refresh().
        self._tokens = TokenSet(
            access_token="vw-website-authproxy-cookie-session",
            refresh_token="",
            id_token="vw-website-authproxy-cookie-session",
            expires_at=_time.time() + 3300,
            strategy="website_authproxy",
        )

    def set_persisted_tokens(self, tokens: TokenSet | None) -> None:
        """v1.19.2 (#118) — inject tokens loaded from HA storage at
        coordinator setup, before the first API call. If valid, the
        client will skip the initial authenticate() and rely on the
        existing 401-refresh path for any expired access_token.

        No-op for None / invalid tokens — coordinator falls through to
        a normal authenticate() flow.

        v2.8.0 — also hydrates any persisted IDP cookies (e.g. the
        ~30-day device-bound cookie issued after a successful email
        OTP challenge) into the auth session. Without this, every
        fresh authenticate() ran the OTP challenge from scratch on
        VW EU even though the IDP would have remembered the device.
        """
        if tokens is not None and tokens.is_valid():
            self._tokens = tokens
            _LOGGER.debug(
                "Loaded persisted tokens for brand %s "
                "(expires_at=%.0f, strategy=%s)",
                self._brand.name,
                tokens.expires_at,
                tokens.strategy or "(legacy)",
            )
            # v2.13.0 — device-code/QR portal entries carry a REAL bearer for
            # the EU-Data-Act proxy_api (not the BFF). Build the portal
            # connector in Bearer mode now so the first poll — at setup AND
            # after a restart (this is the single central token-load point for
            # both) — routes to the portal, not the dead BFF. _refresh_tokens
            # re-injects a fresh bearer on expiry.
            if tokens.strategy == "device_grant_portal":
                from ..auth._eu_data_act import (  # noqa: PLC0415
                    EUDataActConnector,
                )

                self._eu_portal = EUDataActConnector(
                    self._session, brand=self._brand.name,
                    access_token=tokens.access_token,
                )
            if tokens.auth_cookies and hasattr(
                self._auth, "hydrate_session_cookies"
            ):
                self._auth.hydrate_session_cookies(tokens.auth_cookies)
                _LOGGER.debug(
                    "Hydrated %d persisted IDP cookies into auth "
                    "session for brand %s",
                    len(tokens.auth_cookies),
                    self._brand.name,
                )

    async def _notify_tokens_changed(self) -> None:
        """v1.19.2 — fire the persistence hook if registered.

        Called from authenticate() and _refresh_tokens() success
        paths. Defensive: callback errors are logged but never
        propagate, so a broken storage path can't break runtime
        polling.
        """
        if self.on_tokens_changed is None or self._tokens is None:
            return
        try:
            await self.on_tokens_changed(self._tokens)
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning(
                "Token persistence callback failed (%s) — runtime "
                "tokens still valid in-memory, will retry on next "
                "refresh",
                err,
            )

    async def get_vehicles(self) -> list[str]:
        """Return list of VINs in the account garage."""
        raise NotImplementedError

    async def get_status(self, vin: str) -> VehicleData:
        """Return current vehicle data for the given VIN."""
        raise NotImplementedError

    # ── v2.8.0 EU Data Act scraper bridge (Action #3) ──────────────────────────

    async def get_status_via_data_act_portal(
        self,
        vin: str,
        *,
        enable_browser_fallback: bool = False,
    ) -> VehicleData | None:
        """Tier 3.5: fetch + parse the customised-data zip from the portal.

        Called by the coordinator (or by a brand client subclass) when
        ``self._tokens.strategy == "data_act_portal"``. In that mode the
        normal BFF read paths are not available because the integration
        only holds a portal session, not a BFF token. The customised-data
        zip the portal exposes is the only data path under the EU Data
        Act fallback.

        Cadence: the coordinator throttles polling to 15 minutes when
        the active strategy is ``data_act_portal``. See ``DataActScraper``
        for the wake-state requirement and the empty-streak Repair hint.

        Returns ``None`` on any failure so the coordinator can keep the
        previous poll's data visible (stale-cache behaviour).
        """
        from ..auth._data_act_scraper import (  # noqa: PLC0415
            DataActScraper,
            DataActScraperError,
        )

        if self._tokens is None or self._tokens.strategy != "data_act_portal":
            return None
        scraper = DataActScraper(
            self._session,
            brand_name=self._brand.name,
            enable_browser_fallback=enable_browser_fallback,
        )
        try:
            zip_bytes = await scraper.fetch_vehicle_zip(vin)
        except DataActScraperError as err:
            # Structural failure (e.g. browser toggle enabled but
            # playwright missing). Surface to the caller so the
            # coordinator can raise a Repair issue with the message.
            _LOGGER.warning(
                "Data Act scraper structural error for brand %s: %s",
                self._brand.name, err,
            )
            return None
        if zip_bytes is None:
            return None
        parsed = scraper.parse_zip(zip_bytes)
        if not parsed:
            return None
        return scraper.to_vehicle_data(vin, parsed)

    async def fetch_images(self) -> None:
        """Fetch render image URLs via GraphQL — Audi only.

        Called once during get_vehicles(). Populates self._image_data.
        SEAT/CUPRA use OLA renders endpoint instead (in SeatCupraClient).
        Škoda, Porsche, VW NA do not have a GraphQL image endpoint.
        """
        if self._brand.name not in ("audi",):
            return
        try:
            fetcher = VehicleImageFetcher(self._session)
            data = await fetcher.fetch_image_data(self._access_token, self._brand.name)
            self._image_data = data
            if data:
                _LOGGER.info(
                    "VAG images (%s): render URLs for %d vehicle(s)",
                    self._brand.name, len(data),
                )
        except Exception:  # noqa: BLE001
            self._image_data = {}

    async def command_lock(self, vin: str) -> None:
        """Remote lock."""
        raise NotImplementedError

    async def command_unlock(self, vin: str, spin: str = "") -> None:
        """Remote unlock — may require S-PIN."""
        raise NotImplementedError

    async def get_capabilities(self, vin: str) -> dict[str, Any]:
        """Return the per-VIN capabilities document.

        Default implementation returns ``{}`` (i.e. "no data") so callers
        can rely on the helper existing without checking ``hasattr``.
        Brand-specific clients that have a real capabilities endpoint
        override this — currently SEAT/CUPRA (OLA) and the CARIAD BFF
        family (VW EU + Audi). Škoda mysmob and Porsche PPA do not expose
        a discrete capabilities endpoint and keep the default.
        """
        return {}

    async def command_start_climate(self, vin: str) -> None:
        """Start pre-conditioning."""
        raise NotImplementedError

    async def command_start_climate_control(
        self,
        vin: str,
        *,
        temp_c: float | None = None,
        glass_heating: bool | None = None,
        seat_fl: bool | None = None,
        seat_fr: bool | None = None,
        seat_rl: bool | None = None,
        seat_rr: bool | None = None,
        climatisation_at_unlock: bool | None = None,
        climatisation_mode: str | None = None,
    ) -> None:
        """v2.10.0 - rich climate-start. Override in CARIAD-BFF brand clients.

        Accepts per-seat heating toggles (seat_fl/fr/rl/rr), glass_heating,
        climatisation_at_unlock, climatisation_mode and temp_c. Each field
        is optional, with omitted fields keeping the brand backend default.

        Default implementation raises NotImplementedError so the coordinator
        can fall back to the basic ``command_start_climate`` flow for brands
        that do not accept the rich payload (SEAT/CUPRA OLA, Skoda mysmob,
        Porsche PPA, VW NA).
        """
        raise NotImplementedError

    async def command_stop_climate(self, vin: str) -> None:
        """Stop pre-conditioning."""
        raise NotImplementedError

    async def command_start_charging(self, vin: str) -> None:
        """Start charging."""
        raise NotImplementedError

    async def command_stop_charging(self, vin: str) -> None:
        """Stop charging."""
        raise NotImplementedError

    async def command_flash(
        self,
        vin: str,
        latitude: float | None = None,
        longitude: float | None = None,
    ) -> None:
        """Honk and flash. SEAT/CUPRA require the user position; others ignore it."""
        raise NotImplementedError

    async def command_wake(self, vin: str) -> None:
        """Wake vehicle from sleep."""
        raise NotImplementedError

    async def command_set_target_soc(self, vin: str, target: int) -> None:
        """Set charge target SoC (20–100%)."""
        raise NotImplementedError

    async def command_set_battery_care(self, vin: str, enabled: bool) -> None:
        """v2.10.0 - toggle battery preservation mode (SEAT/CUPRA primary).

        When enabled, the brand backend caps the high end of the
        charge at the battery-care target SOC (default 80%, configurable
        via command_set_battery_care_target). Reduces calendar-aging
        damage to the HV battery for users that mostly do short trips.
        """
        raise NotImplementedError

    async def command_set_battery_care_target(self, vin: str, target_pct: int) -> None:
        """v2.10.0 - set the battery-care top-charge target (50-100%)."""
        raise NotImplementedError

    async def command_set_climate_temperature(self, vin: str, temp_c: float) -> None:
        """Set pre-conditioning target temperature."""
        raise NotImplementedError

    async def command_set_charge_mode(self, vin: str, mode: str) -> None:
        """Set charging mode (MANUAL | TIMER | PREFERRED_CHARGING_TIMES)."""
        raise NotImplementedError

    async def command_set_min_soc(self, vin: str, min_soc: int) -> None:
        """Set minimum SoC for PHEV departure timer (0–100%)."""
        raise NotImplementedError

    async def command_start_window_heating(self, vin: str) -> None:
        """Start window (windscreen + rear) heating."""
        raise NotImplementedError

    async def command_stop_window_heating(self, vin: str) -> None:
        """Stop window heating."""
        raise NotImplementedError

    # ── v2.5.2 silent scout-channel probe pass ─────────────────────────────────

    async def run_v3_probe_pass(self, vin: str) -> int:
        """Issue probe GETs for the given VIN, feed responses to the scout.

        Probe behaviour (silent + fail-safe):
        - Runs at most once per ``_PROBE_INTERVAL_S`` per VIN (default 1h).
        - Skipped entirely when ``last_rate_limit_remaining`` is at or
          below ``_PROBE_TOKEN_GUARD`` — protects the user's daily quota.
        - Skipped entirely after ``_PROBE_CB_THRESHOLD`` consecutive
          pass-level failures (auth-storm circuit-breaker).
        - Per-probe HTTP timeout ``_PROBE_TIMEOUT_S`` (short, best-effort).
        - Total per-pass time budget ``_PROBE_BUDGET_S`` (bail if exceeded).
        - 401/403/404/5xx/network errors are swallowed silently per-probe;
          a 401 NEVER triggers ``_refresh_tokens`` here (would be a storm
          risk). On 401 the entire pass aborts and increments the
          circuit-breaker.
        - 2xx-with-JSON responses are stored into ``last_raw_responses``
          under a ``v3_probe:<probe_name>`` key. The coordinator runs the
          same ``detect_unexpected`` walk it always does and emits scout
          telemetry for any new field paths.

        Returns:
            The number of probes that completed with a 2xx JSON body
            (zero on skip / failure / circuit-breaker tripped).
        """
        from ._v3_probes import probes_for_brand, base_url_for_brand  # noqa: PLC0415

        if self._probe_disabled:
            return 0
        probes = probes_for_brand(self._brand.name)
        if not probes:
            return 0
        if self._tokens is None:
            return 0

        # Rate-limit per VIN — never re-run within _PROBE_INTERVAL_S.
        now = time.monotonic()
        last = self._probe_last_pass_at.get(vin, 0.0)
        if last and (now - last) < _PROBE_INTERVAL_S:
            return 0

        # Token-budget guard — don't burn the user's daily quota on probes.
        if (
            self.last_rate_limit_remaining is not None
            and self.last_rate_limit_remaining <= _PROBE_TOKEN_GUARD
        ):
            _LOGGER.debug(
                "v3 probe pass skipped (%s vin=%s): rate-limit remaining %d <= guard %d",
                self._brand.name, vin[-6:],
                self.last_rate_limit_remaining, _PROBE_TOKEN_GUARD,
            )
            self._probe_last_pass_at[vin] = now  # honour interval even on skip
            return 0

        base_url = base_url_for_brand(self._brand.name) or getattr(self, "_BASE", None)
        if not base_url:
            # No documented backend host for this brand — silently skip.
            return 0

        self._probe_last_pass_at[vin] = now
        pass_started = time.monotonic()
        success_count = 0
        # Capture user_id once (set by IDKAuth during login, SEAT/CUPRA path).
        user_id = getattr(self._auth, "user_id", "") or ""

        for probe in probes:
            # Pass-level time budget.
            if (time.monotonic() - pass_started) > _PROBE_BUDGET_S:
                _LOGGER.debug(
                    "v3 probe pass aborted (%s vin=%s): time budget %ds exceeded",
                    self._brand.name, vin[-6:], _PROBE_BUDGET_S,
                )
                break

            host = probe.host_override or base_url
            try:
                path = probe.path.format(vin=vin, user_id=user_id)
            except KeyError:
                # Unknown placeholder — skip probe, never crash.
                continue
            url = f"{host}{path}"

            try:
                body = await self._probe_request(url)
            except _AuthStormSignal:
                # 401 from a probe — abort entire pass and trip the breaker.
                self._probe_consecutive_fails += 1
                if self._probe_consecutive_fails >= _PROBE_CB_THRESHOLD:
                    self._probe_disabled = True
                    _LOGGER.info(
                        "v3 probe channel auto-disabled for %s (%d consecutive 401s)",
                        self._brand.name, self._probe_consecutive_fails,
                    )
                return success_count
            except Exception:  # noqa: BLE001 — probes never raise
                continue

            if not isinstance(body, dict):
                continue
            scout_key = f"v3_probe:{probe.name}"
            self.last_raw_responses[scout_key] = body
            success_count += 1

        # Successful pass resets the auth-storm breaker.
        if success_count > 0:
            self._probe_consecutive_fails = 0
        _LOGGER.debug(
            "v3 probe pass complete (%s vin=%s): %d/%d probes returned JSON",
            self._brand.name, vin[-6:], success_count, len(probes),
        )
        return success_count

    async def _probe_request(self, url: str) -> Any:
        """Minimal GET for v2.5.2 probe pass.

        Distinct from ``_request`` in three ways:
        1. Short timeout (``_PROBE_TIMEOUT_S``).
        2. No retry loop — best-effort one-shot.
        3. 401 raises ``_AuthStormSignal`` so the caller aborts the pass
           rather than triggering ``_refresh_tokens`` (storm risk).

        Returns the parsed JSON body for 2xx responses, ``None`` otherwise.
        Caller is expected to treat all non-dict returns as no-op.
        """
        headers = {
            "Authorization": f"Bearer {self._access_token}",
            "Accept": "application/json",
            "User-Agent": self._brand.user_agent,
        }
        try:
            async with self._session.request(
                "GET", url, headers=headers,
                timeout=ClientTimeout(total=_PROBE_TIMEOUT_S),
            ) as resp:
                if resp.status == 401:
                    raise _AuthStormSignal()
                self._capture_rate_limit_headers(resp.headers)
                if resp.status not in (200, 201, 207):
                    return None
                ct = resp.headers.get("Content-Type", "")
                if "json" not in ct:
                    return None
                return await resp.json()
        except _TRANSIENT_NET_ERRORS:
            return None

    # ── HTTP helpers ───────────────────────────────────────────────────────────

    async def _get(self, url: str, **kwargs: Any) -> Any:
        """Authenticated GET — auto-refreshes token on 401."""
        return await self._request("GET", url, **kwargs)

    async def _post(self, url: str, **kwargs: Any) -> Any:
        """Authenticated POST."""
        return await self._request("POST", url, **kwargs)

    async def _request(
        self, method: str, url: str, retry: bool = True, _attempt: int = 0, **kwargs: Any
    ) -> Any:
        """Execute an authenticated request with retry for transient errors.

        Retry behaviour (v1.8.7 hardening):

        - HTTP 401 → token refresh + 1 retry. Refresh itself is throttled
          to ``_REFRESH_MAX_PER_HOUR`` per rolling hour (storm protection).
        - HTTP 429 → exponential backoff up to 3 attempts (5s/10s/20s).
        - HTTP 500/502/503/504 → exponential backoff up to 3 attempts
          (3s/6s/12s). 504 added in v1.8.7 — Gateway Timeouts from the
          CARIAD BFF are routine on weekends and were previously surfaced
          as fatal API errors.
        - Transient network errors (DNS / connection refused / mid-stream
          disconnects / asyncio timeouts) → same backoff as server errors.
          Verified pattern from we_connect_id #166 and myskoda #731.
        """
        headers = kwargs.pop("headers", {})
        headers["Authorization"] = f"Bearer {self._access_token}"
        headers["Accept"] = "application/json"
        headers["Content-Type"] = headers.get("Content-Type", "application/json")
        headers["User-Agent"] = self._brand.user_agent

        try:
            async with self._session.request(
                method, url, headers=headers, timeout=ClientTimeout(total=_REQUEST_TIMEOUT), **kwargs
            ) as resp:
                if resp.status == 401 and retry:
                    await self._refresh_tokens()
                    return await self._request(method, url, retry=False, **kwargs)
                if resp.status == 429 and _attempt < 3:
                    wait = (2 ** _attempt) * 5
                    _LOGGER.debug("Rate limited (429) — retrying in %ds", wait)
                    await asyncio.sleep(wait)
                    return await self._request(method, url, retry=retry, _attempt=_attempt + 1, **kwargs)
                if resp.status in (500, 502, 503, 504) and _attempt < 3:
                    wait = (2 ** _attempt) * 3
                    _LOGGER.debug("Server error %d — retrying in %ds", resp.status, wait)
                    await asyncio.sleep(wait)
                    return await self._request(method, url, retry=retry, _attempt=_attempt + 1, **kwargs)
                if resp.status == 204:
                    self._capture_rate_limit_headers(resp.headers)
                    return None
                if resp.status not in (200, 201, 202, 207):
                    body = await resp.text()
                    raise APIError(resp.status, url, body)
                # v1.19.1 — capture quota headers on successful response
                # only (4xx/5xx may omit them or send stale values).
                self._capture_rate_limit_headers(resp.headers)
                ct = resp.headers.get("Content-Type", "")
                if "json" in ct:
                    return await resp.json()
                return await resp.text()
        except _TRANSIENT_NET_ERRORS as err:
            if _attempt < 3:
                wait = (2 ** _attempt) * 3
                _LOGGER.debug(
                    "Transient network error (%s) — retrying in %ds",
                    type(err).__name__,
                    wait,
                )
                await asyncio.sleep(wait)
                return await self._request(
                    method, url, retry=retry, _attempt=_attempt + 1, **kwargs
                )
            raise APIError(0, url, f"transient: {type(err).__name__}: {err}") from err

    async def _refresh_tokens(self) -> None:
        """Attempt token refresh; fall back to full re-login.

        Uses a lock to prevent concurrent refresh attempts from racing.

        Storm protection (v1.8.7): if more than ``_REFRESH_MAX_PER_HOUR``
        refresh attempts occur within ``_REFRESH_WINDOW_S`` seconds, raise
        ``AuthenticationError`` to surface the problem instead of silently
        looping. The coordinator catches this in its poll loop and triggers
        the HA reauth flow — the user gets a UI prompt instead of a slowly
        rate-limited account. Patterns from myskoda #976 and
        volkswagencarnet #683.
        """
        if self._refresh_lock is None:
            self._refresh_lock = asyncio.Lock()
        async with self._refresh_lock:
            now = time.monotonic()
            cutoff = now - _REFRESH_WINDOW_S
            self._refresh_history = [t for t in self._refresh_history if t > cutoff]
            if len(self._refresh_history) >= _REFRESH_MAX_PER_HOUR:
                _LOGGER.error(
                    "Token refresh storm: %d attempts in last %ds for %s — pausing"
                    " to prevent IP ban; please reauthenticate from the UI",
                    len(self._refresh_history),
                    _REFRESH_WINDOW_S,
                    self._brand.name,
                )
                raise AuthenticationError(
                    "Token refresh storm — please reauthenticate"
                )
            self._refresh_history.append(now)

            # v2.13.0 — device-code/QR portal tokens refresh at the IDP token
            # endpoint as a PUBLIC client, NOT via self._auth.refresh() (which
            # routes VW to the dead CARIAD BFF). Re-inject the fresh bearer into
            # the live portal connector so it never 401s mid-poll. If the IDP
            # rejects the refresh (the one unverified runtime assumption), the
            # error propagates → the coordinator triggers a QR reauth prompt.
            if (
                self._tokens
                and self._tokens.strategy == "device_grant_portal"
                and self._tokens.refresh_token
            ):
                from ..auth._device_grant import (  # noqa: PLC0415
                    DeviceAuthorizationGrant,
                    portal_dag_config,
                )

                pc = portal_dag_config(self._brand.name)
                if pc is not None:
                    client_id, scope = pc
                    grant = DeviceAuthorizationGrant(
                        self._session, client_id, scope=scope,
                        strategy="device_grant_portal",
                    )
                    self._tokens = await grant.refresh(self._tokens.refresh_token)
                    if getattr(self, "_eu_portal", None) is not None:
                        self._eu_portal.set_bearer(self._tokens.access_token)
                    await self._notify_tokens_changed()
                    return

            if self._tokens and self._tokens.refresh_token:
                try:
                    self._tokens = await self._auth.refresh(self._tokens.refresh_token)
                    # v1.19.2 (#118) — persist refreshed tokens so the
                    # next HACS update / HA restart picks up the
                    # already-valid session instead of re-running the
                    # full OAuth login (which counts against quota +
                    # can trigger reauth-storm on transient failures).
                    await self._notify_tokens_changed()
                    # v2.9.0 - successful refresh clears any prior
                    # lock signal so the coordinator's Repair issue
                    # gets dismissed on the next cycle.
                    self.account_lock_detected = False
                    self._lock_history.clear()
                    return
                except TokenExpiredError:
                    pass
                except APIError as err:
                    # v2.9.0 - account-lock detection. Record HTTP 423
                    # or HTTP 403 with throttle-marker bodies; if 3 such
                    # responses arrive inside the 30-min sliding window,
                    # flip ``account_lock_detected`` so the coordinator
                    # surfaces a Repair issue on the next poll.
                    self._record_lock_signal(err.status, err.body)
                    raise
            _LOGGER.info("Token refresh failed — re-authenticating for %s", self._brand.name)
            await self.authenticate()
            # v2.9.0 - a successful full re-auth also clears the lock.
            self.account_lock_detected = False
            self._lock_history.clear()

    def _record_lock_signal(self, status: int, body: str) -> None:
        """v2.9.0 - feed the VW account-lock sliding-window detector.

        Called from ``_refresh_tokens`` whenever an ``APIError`` lands
        with a status that matches the lock signature (423 unambiguously,
        or 403 with one of ``_LOCK_BODY_MARKERS`` in the body). After
        ``_LOCK_THRESHOLD`` such signals inside ``_LOCK_WINDOW_S``,
        flips ``self.account_lock_detected`` so the coordinator can
        raise the Repair issue on its next iteration.
        """
        is_lock = False
        if status == 423:
            is_lock = True
        elif status == 403 and body:
            body_l = body.lower()
            if any(marker in body_l for marker in _LOCK_BODY_MARKERS):
                is_lock = True
        if not is_lock:
            return
        now = time.monotonic()
        cutoff = now - _LOCK_WINDOW_S
        self._lock_history = [(t, s) for (t, s) in self._lock_history if t > cutoff]
        self._lock_history.append((now, status))
        if len(self._lock_history) >= _LOCK_THRESHOLD:
            if not self.account_lock_detected:
                _LOGGER.warning(
                    "Brand account appears to be temporarily locked for %s "
                    "(%d lock-class auth responses in last %ds, last status=%d). "
                    "Surfacing Repair issue.",
                    self._brand.name,
                    len(self._lock_history),
                    _LOCK_WINDOW_S,
                    status,
                )
            self.account_lock_detected = True

    @property
    def _access_token(self) -> str:
        if not self._tokens:
            raise AuthenticationError("Not authenticated — call authenticate() first.")
        return self._tokens.access_token

    def _capture_rate_limit_headers(self, headers: Any) -> None:
        """v1.19.1 — Read X-RateLimit-* headers from a response.

        Most VAG backends send these on successful 2xx responses:

        - ``X-RateLimit-Remaining``: int, requests left in the current
          window. Most useful field — surfaced as
          ``requests_remaining_today`` sensor by the coordinator.
        - ``X-RateLimit-Limit``: int, total budget in the current
          window. Useful for percentage calculations in HA templates.
        - ``X-RateLimit-Reset``: ISO-8601 timestamp or epoch seconds —
          when the budget refreshes. Stored as opaque string; the
          coordinator can parse if needed.

        Older backends omit these headers — we leave the attributes
        at their previous value rather than reset to None, so a
        single header-less endpoint doesn't blank an otherwise valid
        observation. ``None`` means we've never seen the header at all.

        Headers are case-insensitive per RFC 9110; aiohttp's
        ``CIMultiDict`` handles that already.
        """
        remaining = headers.get("X-RateLimit-Remaining")
        if remaining is not None:
            try:
                self.last_rate_limit_remaining = int(remaining)
            except (TypeError, ValueError):
                # Some backends ship a float ("1499.5") or "unlimited"
                # — try float fallback; otherwise leave previous value.
                try:
                    self.last_rate_limit_remaining = int(float(remaining))
                except (TypeError, ValueError):
                    pass
        limit = headers.get("X-RateLimit-Limit")
        if limit is not None:
            try:
                self.last_rate_limit_limit = int(limit)
            except (TypeError, ValueError):
                try:
                    self.last_rate_limit_limit = int(float(limit))
                except (TypeError, ValueError):
                    pass
        reset = headers.get("X-RateLimit-Reset")
        if reset is not None:
            self.last_rate_limit_reset_at = str(reset)

    @contextmanager
    def _parser_job(self, job_name: str) -> Iterator[None]:
        """v2.8.0 quick win D — wrap a parser block; count success/failure.

        Each brand client's ``get_status()`` wraps each named parser job
        (vehicle_status, charging, climatisation, oil_level, etc.) with
        ``with self._parser_job("name"):``. Successful exit increments
        the ``success`` counter; any exception inside the block increments
        ``fail``, stores the truncated error text in ``last_error``, then
        re-raises so the existing except clauses in ``get_status()`` decide
        whether to swallow or propagate (we do not change behavior here).

        Counters are exposed via ``self.parser_stats`` and surfaced in
        diagnostics export for users debugging silent "Unbekannt" sensors.

        Defensive: when the client was instantiated via ``__new__``
        (the existing parser-unit tests do this to skip the HA setup
        chain), ``parser_stats`` is not initialised. Fall back to a
        local stats dict so the counters become no-ops instead of
        raising AttributeError mid-parse.
        """
        stats_store = getattr(self, "parser_stats", None)
        if stats_store is None:
            stats_store = {}
            self.parser_stats = stats_store  # type: ignore[attr-defined]
        stats = stats_store.setdefault(
            job_name, {"success": 0, "fail": 0, "last_error": ""}
        )
        try:
            yield
            stats["success"] = int(stats.get("success", 0)) + 1
        except Exception as err:  # noqa: BLE001
            stats["fail"] = int(stats.get("fail", 0)) + 1
            stats["last_error"] = str(err)[:200]
            raise

    def _note_parser_job(self, job_name: str, *, present: bool) -> None:
        """v2.8.0 quick win D — record sub-job presence in ``parser_stats``.

        Companion to ``_parser_job``. Used for the selectivestatus family
        of jobs where one HTTP call returns many sub-blocks (charging,
        climatisation, oilLevel, tyrePressure, auxiliaryHeating,
        door_lock, service_care). Each brand parser calls this once
        per logical sub-job after probing the expected top-level key:
        ``present=True`` when the backend shipped the block,
        ``present=False`` when the block is missing or the wrong shape.
        Lets the diagnostics export show "which sub-job stopped flowing"
        without forcing huge with-block indentation diffs in the existing
        defensively-parsed ``_parse_status`` methods.

        Same defensive-getattr as ``_parser_job``: tolerate clients
        instantiated via ``__new__`` in unit tests.
        """
        stats_store = getattr(self, "parser_stats", None)
        if stats_store is None:
            stats_store = {}
            self.parser_stats = stats_store  # type: ignore[attr-defined]
        stats = stats_store.setdefault(
            job_name, {"success": 0, "fail": 0, "last_error": ""}
        )
        if present:
            stats["success"] = int(stats.get("success", 0)) + 1
        else:
            stats["fail"] = int(stats.get("fail", 0)) + 1
            if not stats.get("last_error"):
                stats["last_error"] = "sub-job absent in selectivestatus response"

    def _val(self, data: dict[str, Any], *path: str, default: Any = None) -> Any:
        """Safe nested dict access. _val(d, 'a', 'b', 'c') → d['a']['b']['c']."""
        node: Any = data
        for key in path:
            if not isinstance(node, dict):
                return default
            node = node.get(key, default)
            if node is None:
                return default
        return node
