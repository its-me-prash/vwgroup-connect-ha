# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Volkswagen.de website authproxy connector — OPT-IN, BETA, read-only.

v2.14.0 — a SECOND, attestation-free read channel for VW passenger cars,
parallel to (and independent of) the EU Data Act portal path. It rides the
confidential server-side OAuth client that ``www.volkswagen.de`` already
runs for its "myVolkswagen" web area, so it never touches the Play-Integrity
/ App-Check wall that killed the native WeConnect token path.

Architecture (mirrors the EU Data Act cookie connector, different host):
  1. GET ``/app/authproxy/login`` on ``www.volkswagen.de``. The authproxy
     starts an OIDC login and redirects us into the SAME Auth0 universal
     login at ``identity.vwgroup.io`` the rest of the integration already
     handles (email + password, optional email-OTP MFA).
  2. The authproxy's OWN backend consumes the OAuth code and sets first-
     party session cookies on ``www.volkswagen.de`` — we never exchange a
     code ourselves (we are not the confidential client; we cannot).
  3. Authenticated reads go to ``/app/authproxy/{fag}/proxy/...`` which the
     site reverse-proxies to the real VW backends. Some calls carry the
     literal header ``user-id: __userId__`` which the authproxy substitutes
     for the signed-in user's real id server-side.

This channel is **read-only** and dormant unless the user explicitly opts
into the "Volkswagen.de website (beta)" mode in the config flow. It is wired
additively into ``VWEUClient`` (see ``_website_proxy``) exactly the way the
EU Data Act portal connector is wired through ``_eu_portal`` — it never
changes behaviour for any other mode/brand.

We reuse the Auth0 form/cookie/MFA mechanics from ``idk.py`` and the
form-field/parse helpers from ``_eu_data_act.py`` rather than re-deriving
them. Endpoint paths and response field names were cross-checked against the
community VW website-portal connector (rafaelhutter/ha-volkswagen-connect,
MIT); the parser below is our own. v2.16.0 extends that cross-check to the
live-status read recipe: the shared ``traceId`` + ``Accept-Language: de-DE``
headers, the ``gdc=myvw-wcar-prod`` + ``resourceHost=myvw-vcf-prod`` query
pair, the ``len(warningLights)`` warning-count, and the ``transactionhistory``
``remotelockunlock`` + ``actionSuccess`` newest-first lock/unlock logic.
"""
from __future__ import annotations

import asyncio
import logging
import re
import time
import uuid
from typing import TYPE_CHECKING, Any
from urllib.parse import parse_qs, urlparse

from aiohttp import ClientError, ClientSession, ClientTimeout, TooManyRedirects

from ..._canaries import CANARY_WEBSITE_AUTHPROXY
from .._util import drop_odometer_sentinel
from ..exceptions import AuthenticationError
from ..models import VehicleData
from ._eu_data_act import _login_fields, _login_error, _resolve_action, _TC_MARKERS

if TYPE_CHECKING:
    from .._authproxy import (
        AuthproxyImage,
        AuthproxyRelation,
        AuthproxyRelations,
        AuthproxyVehicleInfo,
    )

_LOGGER = logging.getLogger(__name__)

_SITE_BASE = "https://www.volkswagen.de"
_IDENTITY_BASE = "https://identity.vwgroup.io"
_REDIRECT_URL = (
    "https://www.volkswagen.de/de/besitzer-und-nutzer/myvolkswagen.html"
)

# The login trigger fans out across two upstream "function access groups"
# (``fag``): ``vw-de`` (the myVolkswagen web backend) and ``vwag-weconnect``
# (the WeConnect vehicle backend). Each gets its own scope set. The authproxy
# does the confidential OIDC exchange and lands the browser back on
# ``_REDIRECT_URL`` with first-party cookies set.
_LOGIN_PATH = "/app/authproxy/login"
_LOGIN_PARAMS: dict[str, str] = {
    "fag": "vw-de,vwag-weconnect",
    "scope-vw-de": (
        "profile,address,phone,carConfigurations,dealers,cars,vin,"
        "profession"
    ),
    "scope-vwag-weconnect": "openid,mbb",
    "prompt-vwag-weconnect": "none",
    "redirectUrl": _REDIRECT_URL,
    "sessionTimeout": "1800",
}

# Reverse-proxy data endpoints. ``{vin}`` is substituted per call.
_RELATIONS_PATH = (
    "/app/authproxy/vw-de/proxy/v2/users/me/relations?resourceHost=myvw-vum-prod"
)
_CHARGING_PATH = (
    "/app/authproxy/vwag-weconnect/proxy/vehicles/{vin}/charging/status"
)
_MAINTENANCE_PATH = (
    "/app/authproxy/vw-de/proxy/vehicles/{vin}/maintenance/status"
)

# Realistic desktop browser identity — the authproxy fronts a public website
# and is content-negotiation sensitive on the login pages.
_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36"
)
_TIMEOUT_S = 60

# Transient server statuses worth a short backoff before we give up on a
# single poll, mirroring the EU Data Act connector's softening. A genuine
# 401/403 (session dead) is never swallowed here — it propagates so the
# caller can re-login.
_RETRIABLE_STATUSES = frozenset({500, 502, 503, 504})
_RETRY_DELAYS = (3.0, 6.0)

# A stale authproxy session answers data calls with 401/403 (and 428
# Precondition Required) — treat those as "re-login". NOT 412 Precondition
# Failed: verified live 2026-07-12 that 412 is a per-VEHICLE precondition — an
# MBB/Car-Net car queried with the WeConnect ``gdc`` 412s while the session is
# still fully valid (relations returns 200). Treating 412 as an auth failure
# re-logged in on every poll → email-OTP thrash + silent no-data for MBB cars.
# 412 now degrades to "no data this poll" (see ``_get_json``), and the optional
# live-status reads pass ``optional=True`` so a car that simply doesn't serve a
# given read (401/403) can't force a re-login loop either.
_AUTH_FAIL_STATUSES = frozenset({401, 403, 428})

# #632 — VW's silent SSO (prompt=none) now chains TWO OAuth dances through Auth0
# federation, so the resume redirect chain runs long — past aiohttp's default cap
# of 10 and, for some regional accounts, past our old 20. A too-low cap aborts a
# perfectly good resume with TooManyRedirects. 30 gives the federation chain room
# while still bounding a genuine redirect loop.
_MAX_SSO_REDIRECTS = 30

# v2.15.13 — PROACTIVE session-roll debounce. The vw.de authproxy session's
# downstream tokens expire ~30 min after the last login (our own
# ``sessionTimeout=1800``) and are NOT renewed by data reads, and the identity
# SSO behind the silent refresh lapses if it isn't exercised. The poll cadence
# is ~15 min, so on a slow/aliased cycle the SSO can die between polls; the NEXT
# read then eats a guaranteed auth-fail, and if the identity twin also lapsed it
# forces a full re-OTP (re-add). Rolling the session PROACTIVELY each cycle —
# well inside the 30-min window — keeps it alive; the debounce stops a multi-VIN
# poll from re-rolling within the same cycle. (This is a silent-degradation bug:
# the user just sees stale data on our #1 read-path hedge and files no issue.)
_PROACTIVE_ROLL_INTERVAL_S = 600.0

# v2.14.9 — cookie persistence spans BOTH hosts: the portal session cookies on
# www.volkswagen.de AND the ``auth0`` SSO cookie on identity.vwgroup.io. The
# SSO cookie is host-only (aiohttp exposes an empty domain for it), so it must
# be captured and broadcast across both hosts explicitly — otherwise the silent
# session-resume can't re-establish and every restart loops / re-prompts OTP.
_COOKIE_HOSTS = (f"{_SITE_BASE}/", f"{_IDENTITY_BASE}/")


def _redacted_cookie_summary(cookies: list[dict[str, Any]]) -> str:
    """A value-free, one-line summary of a cookie set for debug logging (#966).

    Lists each cookie's name, host and path plus expiry — but NEVER its value —
    so a resume that dies ~20-30s after a restart (@Jradon001) can be diagnosed
    from the cookie diff between the successful reload and the failing one,
    without ever writing a session secret to the log.
    """
    return ", ".join(
        f"{c.get('name', '?')}@{c.get('domain', '?')}{c.get('path', '')}"
        f" exp={c.get('expires') or '-'}"
        for c in cookies
    ) or "(none)"

_VIN_RE = re.compile(r'"vin"\s*:\s*"([A-HJ-NPR-Z0-9]{17})"')


def _to_float(raw: Any) -> float | None:
    """Best-effort float; tolerates comma decimals; never raises."""
    if raw is None or isinstance(raw, bool):
        return None
    try:
        return float(str(raw).replace(",", "."))
    except (ValueError, TypeError):
        return None


def _to_int(raw: Any) -> int | None:
    """Best-effort int via float (so ``"82.0"`` → 82); never raises."""
    f = _to_float(raw)
    return int(f) if f is not None else None


def _kelvin_to_celsius(raw: Any) -> float | None:
    """Convert a Kelvin scalar to Celsius, rounded to 1 dp. None-safe."""
    k = _to_float(raw)
    return round(k - 273.15, 1) if k is not None else None


def map_charging_to_vehicle_data(payload: Any, d: VehicleData) -> VehicleData:
    """Map a ``charging/status`` response onto ``VehicleData``.

    The authproxy reverse-proxies the WeConnect charging surface, so the body
    is the familiar ``{"data": {"batteryStatus", "chargingStatus",
    "plugStatus"}}`` shape. Every read is defensive — a missing block or
    field leaves the corresponding ``VehicleData`` attribute at its default.
    """
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, dict):
        return d
    battery = data.get("batteryStatus")
    charging = data.get("chargingStatus")
    plug = data.get("plugStatus")
    battery = battery if isinstance(battery, dict) else {}
    charging = charging if isinstance(charging, dict) else {}
    plug = plug if isinstance(plug, dict) else {}

    soc = _to_int(battery.get("currentSOC_pct"))
    if soc is not None:
        d.battery_soc = soc
        d.has_battery = True
        d.is_electric = True

    erange = _to_int(battery.get("cruisingRangeElectric_km"))
    if erange is not None:
        d.electric_range_km = erange
        if d.range_km is None:
            d.range_km = erange

    tsoc = _to_int(battery.get("navigationTargetSOC_pct"))
    if tsoc is not None:
        d.target_soc = tsoc

    btemp = _kelvin_to_celsius(battery.get("temperatureHvBattery_K"))
    if btemp is not None:
        d.battery_temp_c = btemp

    state = charging.get("chargingState")
    if isinstance(state, str) and state:
        d.charging_state = state
        d.is_charging = state.lower() in ("charging", "chargepurposereachedandconservation")

    power = _to_float(charging.get("chargePower_kW"))
    if power is not None:
        d.charging_power_kw = power

    rate = _to_float(charging.get("chargeRate_kmph"))
    if rate is not None:
        d.charging_rate_kmh = rate

    eta = _to_int(charging.get("remainingChargingTimeToComplete_min"))
    if eta is not None:
        d.remaining_charge_time_nav_min = eta

    mode = charging.get("chargeMode")
    if isinstance(mode, str) and mode:
        d.charge_mode = mode

    plug_state = plug.get("plugConnectionState")
    if isinstance(plug_state, str) and plug_state:
        d.plug_state = plug_state
        d.plug_connected = plug_state.lower() == "connected"

    lock_state = plug.get("plugLockState")
    if isinstance(lock_state, str) and lock_state:
        d.connector_locked = lock_state.lower() == "locked"

    ext = plug.get("externalPower")
    if isinstance(ext, str) and ext:
        d.external_power = ext.lower() not in ("unavailable", "off", "")

    return d


def map_maintenance_to_vehicle_data(payload: Any, d: VehicleData) -> VehicleData:
    """Map a ``maintenance/status`` response onto ``VehicleData``.

    The authproxy passes the maintenance surface through verbatim, so the
    body is the WeConnect ``{"data": {"maintenanceStatus": {"value": {...}}}}``
    shape. We accept either the wrapped ``value`` node or a flat ``data``
    object so a backend reshuffle of the envelope still maps. Field names
    follow the CARIAD maintenance vocabulary the rest of the integration
    already parses. Negative "overdue" day counts are kept as-is — the
    sensor layer renders them.
    """
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, dict):
        return d
    status = data.get("maintenanceStatus")
    if isinstance(status, dict):
        node = status.get("value")
        if not isinstance(node, dict):
            node = status
    else:
        node = data

    odo = _to_int(node.get("mileage_km"))
    if odo is not None:
        d.odometer_km = drop_odometer_sentinel(odo)

    insp_km = _to_int(node.get("inspectionDue_km"))
    if insp_km is not None:
        d.service_km = insp_km
    insp_days = _to_int(node.get("inspectionDue_days"))
    if insp_days is not None:
        d.service_due_in_days = insp_days

    oil_km = _to_int(node.get("oilServiceDue_km"))
    if oil_km is not None:
        d.oil_service_km = oil_km
    oil_days = _to_int(node.get("oilServiceDue_days"))
    if oil_days is not None:
        d.oil_service_due_in_days = oil_days

    # b1 — capture the freshness anchor the real authproxy maintenance body
    # carries (verified live on a Golf GTE: data.carCapturedTimestamp). Feeds
    # the per-poll channel-merge freshness + a future data-age sensor.
    ts = node.get("carCapturedTimestamp") or data.get("carCapturedTimestamp")
    if isinstance(ts, str) and ts:
        d.maintenance_report_captured_at = ts

    return d


class WebsiteAuthProxyConnector:
    """OPT-IN, read-only volkswagen.de website-authproxy client.

    Lifecycle:
      ``begin_login()`` once → ``"ok"`` (logged in) or ``"otp_required"``
      (email-OTP challenge pending — call ``submit_otp(code)``). Thereafter
      ``list_vehicle_vins()`` + ``get_vehicle_data(vin)`` per poll, and
      ``refresh()`` to silently re-establish the session via the persisted
      SSO cookie on a 401.

    This connector NEVER sends a command — it is a read channel only.
    """

    #: Marks this channel as command-free for any caller that introspects it.
    read_only: bool = True

    def __init__(
        self,
        session: ClientSession,
        email: str,
        password: str,
        brand: str = "volkswagen",
    ) -> None:
        # Provenance canary — referenced so a port of this module carries the
        # marker. Semantically inert (see _canaries.py). Literal embedded for
        # the canary-watch grep: website_authproxy_provenance_b6tkd2x9_2026
        self._canary = CANARY_WEBSITE_AUTHPROXY
        self._session = session
        self._email = email
        self._password = password
        self._brand = brand
        self.logged_in = False
        # Stashed between begin_login() and submit_otp(): the email-challenge
        # URL plus the Auth0 state needed to POST the OTP code.
        self._otp_url: str | None = None
        self._otp_state: str | None = None
        # The email-challenge page HTML — parsed in submit_otp for its hidden
        # form fields (_csrf / relayState / hmac), same as the password step.
        self._otp_html: str | None = None
        # v2.15.13 — monotonic clock of the last PROACTIVE session roll (see
        # maybe_roll). -inf = never → the first poll ALWAYS rolls, regardless of
        # the process's absolute time.monotonic() value. (0.0 was wrong: on a
        # freshly-booted host time.monotonic() can be < the debounce interval,
        # so 0.0 would wrongly debounce the very first roll — CI caught this on a
        # fresh runner where the tests passed on a long-uptime dev box.)
        self._last_roll: float = float("-inf")
        # Per-VIN platform backend ("MBB"/"MEB"/…) learned from the relations
        # parse, so the live-status reads pick the right ``gdc`` — an MBB car
        # uses a different global-data-centre than a WeConnect car, and the
        # wrong gdc makes every read 412. Empty string = "known, no backend
        # field" (→ WeConnect default) so it isn't re-probed every read.
        self._vin_backend: dict[str, str] = {}
        # v3.0.0 — raw vw.de responses for the diagnostics export, so a vw.de
        # reporter's one-click "Download diagnostics" grounds the location / auth
        # issues (#923 / #966). Keyed by endpoint (VIN stripped from the key);
        # the bodies are redacted at export time. Bounded — one per endpoint.
        self.last_raw_responses: dict[str, Any] = {}
        # #923 — EXPERIMENTAL parkingposition probe, gated on the opt-in test
        # cohort (set by the coordinator from entry.data at arm time). Self-
        # limiting: it stops after a few no-coordinate polls so we never hammer
        # VW's proxy with a doomed request forever. If coordinates DO come back,
        # ``_position_available`` latches True and the read continues every poll
        # (it's a real feature at that point).
        self.probe_position: bool = False
        self._position_probe_tries: int = 0
        self._position_available: bool = False

        # SoH probe (4.3.2 batteryHealthState) — same opt-in test-cohort gate as
        # the GPS probe, own independent budget. ``_soh_subpath`` pins the first
        # candidate that returns a real %, so later polls issue a single request.
        self.probe_soh: bool = False
        self._soh_probe_tries: int = 0
        self._soh_available: bool = False
        self._soh_subpath: str | None = None

        # #923/#1157 — last outcome of each experimental probe, surfaced in
        # diagnostics so the test cohort can see WHY a probe yielded nothing (a
        # 403/404/412 refusal vs a never-fired probe vs an empty 200). Values are
        # bare status labels only ("404", "412", "200 no-value") — no PII. Without
        # this a fail-soft probe left zero trace and the whole cohort was blind.
        self.probe_outcomes: dict[str, str] = {}

    _POSITION_PROBE_MAX_TRIES = 4
    _SOH_PROBE_MAX_TRIES = 4

    def _should_probe_soh(self) -> bool:
        """Whether to attempt the experimental vw.de battery-SoH read this poll.

        Latches on once a candidate subpath returns a real % (it becomes a real
        read), else runs while the user is opted into the test cohort and still
        within the self-limiting budget — so an opted-out user never issues the
        request, and an opted-in car whose proxy keeps refusing stops after
        ``_SOH_PROBE_MAX_TRIES`` polls.
        """
        if self._soh_available:
            return True
        return self.probe_soh and self._soh_probe_tries < self._SOH_PROBE_MAX_TRIES

    def _should_probe_position(self) -> bool:
        """Whether to attempt the experimental parkingposition read this poll.

        True once coordinates have been seen at least once (it latches on as a
        real feature), or while the user is opted into the test cohort and still
        within the self-limiting probe budget. False otherwise — so an opted-out
        user never issues the request, and an opted-in car whose proxy keeps
        refusing stops after ``_POSITION_PROBE_MAX_TRIES`` polls.
        """
        if self._position_available:
            return True
        return (
            self.probe_position
            and self._position_probe_tries < self._POSITION_PROBE_MAX_TRIES
        )

    def _capture_raw(self, url: str, body: Any) -> None:
        """Stash a raw vw.de response for diagnostics, keyed by endpoint with the
        VIN stripped from the KEY (the body is redacted separately at export)."""
        try:
            import re  # noqa: PLC0415
            from urllib.parse import urlsplit  # noqa: PLC0415

            path = urlsplit(url).path
            key = re.sub(r"[A-HJ-NPR-Z0-9]{17}", "{vin}", path)
            key = key.split("/vehicles/")[-1]
            if "{vin}/" in key:
                key = key.split("{vin}/", 1)[-1]
            self.last_raw_responses["vwde:" + key.strip("/")] = body
        except Exception:  # noqa: BLE001 — capture must never break a read
            pass

    # ── login ──────────────────────────────────────────────────────────────

    def _csrf(self) -> str:
        """Current ``csrf_token`` cookie value, for the double-submit header.

        The authproxy enforces a double-submit CSRF check: the value of the
        ``csrf_token`` cookie must be echoed back in the ``x-csrf-token`` header
        on every read (and it rotates on each silent refresh). Returns "" if
        absent (never raises)."""
        from yarl import URL  # noqa: PLC0415
        try:
            jar = self._session.cookie_jar
            for host in _COOKIE_HOSTS:
                ck = jar.filter_cookies(URL(host)).get("csrf_token")
                if ck and ck.value:
                    return str(ck.value)
        except Exception:  # noqa: BLE001
            pass
        return ""

    def _headers(self, extra: dict[str, str] | None = None) -> dict[str, str]:
        headers = {
            "User-Agent": _USER_AGENT,
            "Accept-Language": "de-DE,de;q=0.9,en;q=0.8",
            # Per-request trace id. The myVolkswagen web app sends one on every
            # authproxy read, and some live-status endpoints (warninglights/last)
            # 400 without it. Harmless on the endpoints that ignore it, so it goes
            # on unconditionally. (Header recipe cross-checked against
            # rafaelhutter/ha-volkswagen-connect (MIT) website_portal.py:283.)
            "traceId": uuid.uuid4().hex,
        }
        # Double-submit CSRF: echo the csrf_token cookie into the header on every
        # request, or the authproxy rejects reads (the reads silently returned
        # {} / 412 without it).
        csrf = self._csrf()
        if csrf:
            headers["x-csrf-token"] = csrf
        if extra:
            headers.update(extra)
        return headers

    async def begin_login(self) -> str:
        """Drive authproxy → Auth0 email + password. Returns the next step.

        Returns ``"ok"`` when the session landed back on volkswagen.de
        (cookies set, logged in), or ``"otp_required"`` when the IDP wants an
        email-OTP code (the challenge URL + state are stashed for
        ``submit_otp``). Raises ``AuthenticationError`` on bad credentials or
        an unexpected flow.
        """
        self.logged_in = False
        self._otp_url = None
        self._otp_state = None

        # 1. Hit the authproxy login trigger; follow into Auth0 universal login.
        #    A hydrated (cookie-resumed) session changes the shape: it can land
        #    straight back on volkswagen.de already-logged-in, OR — if the
        #    persisted cookies are only partially valid — bounce the authproxy
        #    against the IDP (prompt=none) in a redirect loop. Cap the hops so a
        #    loop raises a clean, handled error instead of an unguarded crash,
        #    and treat an already-authenticated landing as success (no OTP).
        try:
            async with self._session.get(
                f"{_SITE_BASE}{_LOGIN_PATH}",
                params=_LOGIN_PARAMS,
                headers=self._headers(),
                allow_redirects=True,
                max_redirects=_MAX_SSO_REDIRECTS,
                timeout=ClientTimeout(total=_TIMEOUT_S),
            ) as resp:
                login_url = str(resp.url)
                login_html = await resp.text(errors="replace")
                login_status = resp.status
                _LOGGER.debug(
                    "Website authproxy begin_login GET → status %s, chain: %s",
                    login_status,
                    self._redirect_hosts(getattr(resp, "history", ()), login_url),
                )
        except TooManyRedirects as exc:
            # A resumed session looping between the authproxy and the IDP means
            # the persisted cookies are stale. Surface a normal auth failure so
            # the coordinator re-authenticates rather than crashing the poll.
            _LOGGER.debug(
                "Website authproxy begin_login GET redirect LOOP — chain: %s",
                self._redirect_hosts(getattr(exc, "history", ())),
            )
            raise AuthenticationError(
                "Website authproxy: redirect loop resuming the session "
                "(persisted cookies stale) — re-authentication needed"
            ) from exc

        if login_status >= 400:
            raise AuthenticationError(
                f"Website authproxy: login page HTTP {login_status}"
            )

        # Already authenticated? A valid resumed session lands back on
        # volkswagen.de WITHOUT passing through the identity login page — that
        # means the persisted cookies are still good, so we're in (no OTP).
        host = urlparse(login_url).hostname or ""
        if host.endswith("volkswagen.de") and "/u/login" not in login_url:
            self._finalise_login(login_url)
            return "ok"

        # #632 parity — a mandatory terms-and-conditions wall in the resume path
        # is NOT a dead session: the account has to accept an updated VW T&C once,
        # in a browser. Surface that actionable message instead of a generic
        # "session expired", which would otherwise loop the user forever.
        if any(m in (login_url + " " + login_html).lower() for m in _TC_MARKERS):
            raise AuthenticationError(
                "Website authproxy: Volkswagen is showing a terms-and-conditions "
                "wall that must be accepted before data flows again. Open "
                "volkswagen.de in a browser, sign in, accept the updated terms, "
                "then re-add the Volkswagen.de read channel from the integration "
                "options."
            )

        if "/u/login" not in login_url and "signin-service" not in login_url:
            raise AuthenticationError(
                "Website authproxy: did not reach the VW identity login "
                f"(landed at {login_url[:80]})"
            )

        auth0_state = self._auth0_state(login_url, login_html)

        # 2. POST credentials to the Auth0 universal-login endpoint. The state
        #    travels in BOTH the URL query and the form body (the same pattern
        #    idk.py uses against this exact /u/login page).
        fields, action = _login_fields(login_html)
        fields["username"] = self._email
        fields["email"] = self._email
        fields["password"] = self._password
        if auth0_state:
            fields["state"] = auth0_state
        fields.setdefault("action", "default")
        post_url = _resolve_action(login_url, action)

        try:
            async with self._session.post(
                post_url,
                data=fields,
                headers=self._headers({"Referer": login_url}),
                allow_redirects=True,
                max_redirects=_MAX_SSO_REDIRECTS,
                timeout=ClientTimeout(total=_TIMEOUT_S),
            ) as resp:
                landed = str(resp.url)
                landed_html = await resp.text(errors="replace")
                landed_status = resp.status
                _LOGGER.debug(
                    "Website authproxy credential POST → status %s, chain: %s",
                    landed_status,
                    self._redirect_hosts(getattr(resp, "history", ()), landed),
                )
        except TooManyRedirects as exc:
            # The credential POST bouncing the authproxy against the IDP means
            # the flow can't settle — surface a clean auth failure rather than
            # an unguarded crash (mirrors the begin_login GET guard above).
            _LOGGER.debug(
                "Website authproxy credential POST redirect LOOP — chain: %s",
                self._redirect_hosts(getattr(exc, "history", ())),
            )
            raise AuthenticationError(
                "Website authproxy: redirect loop posting credentials "
                "— login could not complete"
            ) from exc

        if landed_status == 401:
            raise AuthenticationError(
                "Website authproxy: invalid email or password"
            )
        if landed_status >= 400 and "email-challenge" not in landed:
            err = _login_error(landed_html)
            raise AuthenticationError(
                err or f"Website authproxy: login rejected (HTTP {landed_status})"
            )

        # 3. Email-OTP challenge? Stash the challenge URL + state and bail out
        #    so the UI can collect the code.
        if "/u/email-challenge" in landed or "/u/mfa" in landed:
            self._otp_url = landed
            self._otp_html = landed_html
            self._otp_state = (
                parse_qs(urlparse(landed).query).get("state", [auth0_state or ""])[0]
                or auth0_state
            )
            _LOGGER.debug("Website authproxy: email-OTP challenge pending")
            return "otp_required"

        self._finalise_login(landed)
        return "ok"

    async def submit_otp(self, code: str) -> bool:
        """POST the email-OTP code and finish the login. Returns success.

        Must be called after ``begin_login()`` returned ``"otp_required"``.
        Follows the post-challenge redirect chain back to volkswagen.de.
        """
        if not self._otp_url:
            raise AuthenticationError(
                "Website authproxy: no pending OTP challenge — call "
                "begin_login() first"
            )
        # The Auth0 email-challenge form carries hidden fields (_csrf /
        # relayState / hmac) AND a code input whose name is NOT always "code" —
        # it can be otp / mfa-code / token / passcode. Our form parser surfaces
        # value-less inputs, so the real field is present in ``fields``; set the
        # code into whichever the form actually carries. A hardcoded "code" left
        # the real field empty, so the IDP treated it as "no code entered",
        # re-issued a FRESH challenge (= a new email) and we bounced on
        # "email-challenge" forever — the "credential issue + new code every
        # attempt" loop. Also opt into any "remember" field so the SSO cookie
        # lives longer (helps the silent resume). Fall back to "code" only if the
        # form exposes no recognisable code field. (Mirrors the working
        # rafaelhutter authproxy flow.)
        fields, action = _login_fields(self._otp_html or "")
        code_clean = str(code).strip()
        matched = False
        for key in list(fields):
            kl = key.lower()
            if kl in (
                "code", "otp", "mfa-code", "mfa_code",
                "email-code", "passcode", "token",
            ):
                fields[key] = code_clean
                matched = True
            elif "remember" in kl:
                fields[key] = "true"
        if not matched:
            fields["code"] = code_clean
        if self._otp_state:
            fields.setdefault("state", self._otp_state)
        post_url = _resolve_action(self._otp_url, action)
        async with self._session.post(
            post_url,
            data=fields,
            headers=self._headers({"Referer": self._otp_url}),
            allow_redirects=True,
            timeout=ClientTimeout(total=_TIMEOUT_S),
        ) as resp:
            landed = str(resp.url)
            landed_html = await resp.text(errors="replace")
            landed_status = resp.status

        if landed_status >= 400 or "email-challenge" in landed:
            err = _login_error(landed_html)
            raise AuthenticationError(
                err or "Website authproxy: OTP rejected — check the code"
            )
        self._otp_url = None
        self._otp_state = None
        self._otp_html = None
        self._finalise_login(landed)
        return self.logged_in

    async def refresh(self) -> None:
        """Silently re-establish the session via the persisted SSO cookie.

        The IDP keeps an SSO session cookie on ``identity.vwgroup.io`` after a
        successful login, so re-running the authproxy login trigger usually
        completes without a fresh password POST (the universal-login page
        recognises the session and redirects straight through). If the IDP
        instead re-prompts for credentials we fall back to the full
        ``begin_login`` flow; a surfaced OTP requirement raises so the caller
        can route the user back through the OTP UI.
        """
        # The silent resume issues the IDENTICAL request begin_login does, so it
        # needs the identical redirect budget. It used to run at aiohttp's
        # default of 10 hops while begin_login was deliberately given 20, and
        # _LOGIN_PARAMS fans out over two function-access groups (a two-leg
        # OAuth chain in one run), so a lengthened VW SSO chain aborted here
        # while the interactive login sailed through. A raw TooManyRedirects
        # also escaped as a redacted generic error, hiding the reason.
        try:
            async with self._session.get(
                f"{_SITE_BASE}{_LOGIN_PATH}",
                params=_LOGIN_PARAMS,
                headers=self._headers(),
                allow_redirects=True,
                max_redirects=_MAX_SSO_REDIRECTS,
                timeout=ClientTimeout(total=_TIMEOUT_S),
            ) as resp:
                landed = str(resp.url)
                status = resp.status
        except TooManyRedirects as exc:
            # Same contract as begin_login: surface a normal auth failure so the
            # caller re-authenticates instead of a raw aiohttp error reaching
            # the poll. Hostnames only, so the OAuth state never lands in a log.
            _LOGGER.debug(
                "Website authproxy refresh GET redirect LOOP — chain: %s",
                self._redirect_hosts(getattr(exc, "history", ())),
            )
            raise AuthenticationError(
                "Website authproxy: redirect loop or over-long SSO chain "
                "resuming the session — re-authentication needed"
            ) from exc

        # prompt=none silent re-authorize: a LIVE Auth0 SSO cookie mints a fresh
        # portal session and lands us back on volkswagen.de. A DEAD SSO bounces
        # to the login page / returns ?error=… — in which case we must NOT fall
        # back to begin_login() (that would start the interactive flow and make
        # the IDP email a fresh OTP every refresh). Raise → the caller surfaces
        # a graceful re-add instead. OTP only ever lives on the interactive path.
        # #923/#875/#966 — classify on the landed HOST + PATH, never on the raw
        # URL. The old test was a bare substring match over the whole URL,
        # query string included, so a resume that landed correctly back on
        # volkswagen.de was still declared "SSO expired" whenever the callback
        # carried an IDP path inside a query parameter (redirect_uri=…/
        # signin-service/…). Three reporters described exactly that shape: the
        # OTP login succeeds and the session is reported expired seconds later,
        # so re-adding the channel produces new cookies and the very same
        # verdict — an endless Repair loop. ``begin_login`` has always done the
        # host-aware check (see its landing test); this brings ``refresh`` in
        # line with it.
        landed_parts = urlparse(landed)
        landed_host = landed_parts.hostname or ""
        landed_path = landed_parts.path or ""
        on_portal = landed_parts.netloc == urlparse(_SITE_BASE).netloc
        # Log the chain unconditionally — hostnames only, so no OAuth state or
        # token ever reaches the log. Previously only the redirect-loop branch
        # logged it, which left a reporter's debug log unable to show where the
        # chain actually went: the single fact needed to tell a dead SSO from a
        # misclassified good one.
        _LOGGER.debug(
            "Website authproxy refresh GET landed host=%s path=%s status=%s",
            landed_host, landed_path, status,
        )
        if not on_portal and (
            "/u/login" in landed_path or "/signin-service" in landed_path
        ):
            raise AuthenticationError(
                "Website authproxy: SSO session expired — full re-login required"
            )
        sso_error = parse_qs(landed_parts.query).get("error", [None])[0]
        if sso_error:
            raise AuthenticationError(
                f"Website authproxy: silent refresh failed (error={sso_error})"
            )
        if status < 400 and on_portal and "/u/login" not in landed_path:
            self.logged_in = True
            _LOGGER.info(
                "Website authproxy: silent refresh resumed the session"
                " (prompt=none, no OTP)"
            )
            return
        raise AuthenticationError(
            f"Website authproxy: refresh did not land on the portal ({landed[:80]})"
        )

    async def maybe_roll(self, *, force: bool = False) -> None:
        """v2.15.13 — PROACTIVELY roll the SSO session before it silently lapses.

        Called at the top of each poll cycle's authproxy reads. Debounced to
        ``_PROACTIVE_ROLL_INTERVAL_S`` so a multi-VIN poll rolls at most once per
        window. Best-effort: a failed roll NEVER breaks the poll — the reactive
        ``refresh()`` inside ``get_status``/``get_vehicles`` remains the safety
        net. See ``_PROACTIVE_ROLL_INTERVAL_S`` for why this exists (silent SSO
        death on our #1 read-path hedge). No-op until the first successful login
        (``logged_in``) so we never roll a session that was never established.
        """
        if not self.logged_in:
            return
        now = time.monotonic()
        if not force and (now - self._last_roll) < _PROACTIVE_ROLL_INTERVAL_S:
            return
        self._last_roll = now
        try:
            await self.refresh()
        except Exception:  # noqa: BLE001
            # A proactive roll is opportunistic: if it fails (transient network,
            # or a genuinely-dead SSO), swallow it and let the subsequent read's
            # reactive refresh()/re-login handle it. Never propagate from here.
            _LOGGER.debug(
                "Website authproxy: proactive session roll skipped (will rely on"
                " the reactive path this cycle)",
                exc_info=True,
            )

    def _finalise_login(self, landed_url: str) -> None:
        """Mark logged-in iff we ended back on the volkswagen.de host."""
        host = urlparse(_SITE_BASE).netloc
        if urlparse(landed_url).netloc == host:
            self.logged_in = True
            _LOGGER.info(
                "Website authproxy: login succeeded (read-only, beta)"
            )
        else:
            raise AuthenticationError(
                "Website authproxy: login did not complete "
                f"(ended at {landed_url[:80]})"
            )

    @staticmethod
    def _redirect_hosts(history: Any, final_url: str | None = None) -> str:
        """Hostname-only redirect chain, safe for DEBUG logging.

        Maps each hop in an aiohttp ``resp.history`` (or a ``TooManyRedirects``
        exception's ``.history``) to just its hostname and joins them with an
        arrow. It deliberately drops paths and query strings — the OAuth
        ``state`` and any tokens live in the query — so only hostnames are
        emitted. A repeating ``A → B → A → B`` pattern is exactly the loop
        signature we need to diagnose a stuck session-resume. Never raises.
        """
        hosts: list[str] = []
        try:
            for hop in history or ():
                hosts.append(urlparse(str(getattr(hop, "url", ""))).hostname or "?")
        except (TypeError, AttributeError):
            pass
        if final_url:
            hosts.append(urlparse(final_url).hostname or "?")
        return " → ".join(hosts) if hosts else "(no redirects)"

    @staticmethod
    def _auth0_state(login_url: str, html: str) -> str | None:
        """Pull the Auth0 ``state`` from the page (hidden input or URL query)."""
        m = re.search(
            r'name=["\']state["\']\s+value=["\']([^"\']+)["\']', html
        )
        if m:
            return m.group(1)
        return parse_qs(urlparse(login_url).query).get("state", [""])[0] or None

    # ── cookie persistence ─────────────────────────────────────────────────

    def export_cookies(self) -> list[dict[str, Any]]:
        """Serialise the authproxy session cookies for persistence.

        v2.14.9 — collect via ``cookie_jar.filter_cookies()`` for BOTH the
        volkswagen.de and identity.vwgroup.io hosts, rather than scanning the
        raw jar and filtering by a domain string. That string filter silently
        dropped the host-only ``auth0`` SSO cookie (aiohttp exposes an empty
        domain for host-only cookies), and WITHOUT that SSO cookie the silent
        resume can never re-establish the session — the restart redirect-loop /
        re-OTP bug. ``filter_cookies`` returns exactly the cookies each host
        would receive (host-only ones included) and nothing from other hosts,
        so it stays scoped to our two domains.
        """
        from yarl import URL  # noqa: PLC0415

        out: list[dict[str, Any]] = []
        seen: set[tuple[str, str, str]] = set()
        # #966 — a host-only cookie that import_cookies() broadcast to BOTH hosts
        # comes back from filter_cookies() for EACH host, and line "domain or
        # host_name" then stamps it with the filter-host, so the (domain,name,path)
        # key below sees two DIFFERENT domains and keeps both. That doubles the
        # host-only set every persist cycle (Arno-MA-73's watertight repro: an
        # 11-cookie login round-tripped to a 22-cookie restore, and the superseded
        # twin clobbered the still-good identity.vwgroup.io SSO cookie -> 401 on
        # the second restart). Collapse on (name, path, VALUE) too: a broadcast
        # twin is byte-identical so it folds to one, while #632's genuinely
        # different-per-host values (auth0 www vs idp) differ in value and are
        # still both kept. import re-broadcasts the survivor to both hosts anyway.
        seen_nv: set[tuple[str, str, str]] = set()
        try:
            jar = self._session.cookie_jar
        except Exception:  # noqa: BLE001
            return out
        for host in _COOKIE_HOSTS:
            try:
                filtered = jar.filter_cookies(URL(host))
            except Exception:  # noqa: BLE001
                continue
            host_name = URL(host).host or ""
            for name, morsel in filtered.items():
                _ck_domain = str(morsel["domain"] or host_name)
                _ck_path = str(morsel["path"] or "/")
                _ck_value = str(morsel.value)
                # #966 — fold the broadcast twin (same name+path+value, different
                # fabricated domain) before the #632 (domain,name,path) key.
                nv_key = (str(name), _ck_path, _ck_value)
                if nv_key in seen_nv:
                    continue
                # #632 — key the de-dup by (domain, name, path), NOT (name, value).
                # VW reuses cookie names (auth0 / auth0_compat / did / idkit_p / …)
                # across identity.vwgroup.io AND www.volkswagen.de with DIFFERENT
                # values; collapsing on name(+value) drops one host's copy, and on
                # the restore round-trip the identity-host SSO cookie is lost — the
                # silent resume then lands on /u/login. Per-account because which
                # value wins the collapse is iteration/value-dependent. (Grounded:
                # the reference vw.de website-portal project hit this exact failure
                # and converged on a (domain, name)-keyed export.)
                key = (_ck_domain, str(name), _ck_path)
                if key in seen:
                    continue
                seen.add(key)
                seen_nv.add(nv_key)
                try:
                    out.append({
                        "name": str(name),
                        "value": str(morsel.value),
                        "domain": _ck_domain,
                        "path": _ck_path,
                        "expires": str(morsel["expires"] or ""),
                        "secure": bool(morsel["secure"]),
                        "httponly": bool(morsel["httponly"]),
                    })
                except Exception:  # noqa: BLE001
                    continue
        if _LOGGER.isEnabledFor(logging.DEBUG):
            _LOGGER.debug(
                "authproxy cookie export: %d cookie(s) — %s",
                len(out), _redacted_cookie_summary(out),
            )
        return out

    def import_cookies(self, cookies: list[dict[str, Any]]) -> None:
        """Hydrate persisted session cookies, broadcast to BOTH authproxy hosts.

        v2.14.9 — each persisted cookie is injected host-only against BOTH
        www.volkswagen.de AND identity.vwgroup.io. aiohttp loses the host for
        host-only cookies, so binding the ``auth0`` SSO cookie to a single host
        left it unreachable from the other; broadcasting to both guarantees the
        SSO cookie reaches identity.vwgroup.io (the linchpin of silent resume).
        An extra cookie a host doesn't expect is harmless. This (with the
        matching ``export_cookies`` fix) is what makes a restart resume the
        session instead of redirect-looping / re-prompting OTP.
        """
        if not cookies:
            return
        if _LOGGER.isEnabledFor(logging.DEBUG):
            _LOGGER.debug(
                "authproxy cookie import: %d cookie(s) — %s",
                len(cookies), _redacted_cookie_summary(cookies),
            )
        try:
            from http.cookies import Morsel  # noqa: PLC0415
            from yarl import URL  # noqa: PLC0415
        except ImportError:
            return
        # VW reuses some cookie NAMES across the two hosts with DIFFERENT
        # values. Broadcasting those would make whichever entry is written last
        # win on BOTH hosts, so one host is guaranteed the wrong value (a
        # neighbouring project hit exactly this). Export already stamps each
        # cookie with its real host, so for a colliding name we bind per host
        # instead of broadcasting. Every non-colliding cookie — including the
        # host-only SSO cookie the broadcast exists for — is untouched.
        _values_per_name: dict[str, set[str]] = {}
        for ck in cookies:
            if isinstance(ck, dict) and ck.get("name") and ck.get("value") is not None:
                _values_per_name.setdefault(str(ck["name"]), set()).add(str(ck["value"]))
        colliding = {n for n, vals in _values_per_name.items() if len(vals) > 1}
        for ck in cookies:
            if not isinstance(ck, dict):
                continue
            name = ck.get("name")
            value = ck.get("value")
            if not name or value is None:
                continue
            # Scope guard: only ever inject cookies that belong to our two
            # hosts (export stamps every persisted cookie with its real host),
            # so a malformed/foreign entry is never broadcast. The host-only
            # SSO cookie now carries domain="identity.vwgroup.io" from export,
            # so it passes this guard (it was the empty-domain drop that broke).
            domain = str(ck.get("domain") or "")
            # #632 — exact host / registrable-suffix check, NOT a substring test.
            # The old `"vwgroup.io" not in domain` would wrongly ADMIT a foreign
            # `vwgroup.io.attacker.com`; a boundary check only accepts our two
            # cookie domains and their true subdomains.
            _d = domain.lstrip(".").lower()
            if not (
                _d == "volkswagen.de" or _d.endswith(".volkswagen.de")
                or _d == "vwgroup.io" or _d.endswith(".vwgroup.io")
            ):
                continue
            morsel: Morsel[str] = Morsel()
            morsel.set(str(name), str(value), str(value))
            # #923/#875/#966 — a DOMAIN cookie must be restored as a domain
            # cookie. Dropping the domain and re-binding host-only to our two
            # hosts means a cookie the IDP issued for ``.vwgroup.io`` is no
            # longer sent to any OTHER *.vwgroup.io hop in the authorize chain,
            # so the silent resume can fail even though the session is alive —
            # the "signed in fine, reported expired seconds later" loop.
            #
            # The comment that used to sit here claimed this matched a working
            # reference implementation. It matched that project's OLD code: they
            # hit this same bug and now restore the domain, their own note
            # saying the previous behaviour "silently broke the silent refresh
            # and forced a re-login" — our exact symptom. Host-only entries
            # (empty or non-dotted domain) keep the broadcast path below, which
            # is what makes the host-only SSO cookie reachable.
            _dotted = domain.startswith(".")
            if _dotted:
                try:
                    morsel["domain"] = domain
                except (KeyError, ValueError):
                    _dotted = False
            for attr in ("path", "expires", "secure", "httponly"):
                if attr in ck and ck[attr] not in (None, ""):
                    try:
                        morsel[attr] = ck[attr]
                    except (KeyError, ValueError):
                        pass
            targets: tuple[str, ...]
            if _dotted:
                # A true domain cookie is filed ONCE against its apex; aiohttp
                # then serves it to every host under that domain, which is the
                # whole point. Broadcasting it host-only would re-narrow it.
                targets = (f"https://{domain.lstrip('.')}/",)
            elif str(name) in colliding:
                # Ambiguous name: send this value only to the host it came from.
                targets = tuple(
                    h for h in _COOKIE_HOSTS if (URL(h).host or "") in domain
                ) or (_COOKIE_HOSTS[0],)
            else:
                targets = _COOKIE_HOSTS
            for host in targets:
                try:
                    # #923/#875/#966 — build a FRESH morsel per target. aiohttp
                    # stamps the response host onto the morsel it is handed, so
                    # re-using one object across the broadcast meant the second
                    # host re-filed the cookie under the FIRST host's domain and
                    # the jar kept only one copy. The host-only SSO cookie
                    # therefore never reached identity.vwgroup.io — the exact
                    # thing this broadcast exists to guarantee, silently not
                    # happening since it was written.
                    per_host: Morsel[str] = Morsel()
                    per_host.set(str(name), str(value), str(value))
                    for _a in ("domain", "path", "expires", "secure", "httponly"):
                        if morsel[_a] not in (None, ""):
                            try:
                                per_host[_a] = morsel[_a]
                            except (KeyError, ValueError):
                                pass
                    self._session.cookie_jar.update_cookies(
                        {str(name): per_host}, response_url=URL(host),
                    )
                except Exception:  # noqa: BLE001
                    continue

    async def session_alive(self) -> bool:
        """Probe the relations endpoint with the currently-loaded cookies.

        The resume partner to ``import_cookies``: a cheap authenticated read
        that tells us whether a persisted session is still good WITHOUT
        re-running the redirect-loop-prone ``/app/authproxy/login`` OAuth
        dance. Returns ``True`` only on a clean authenticated ``200``. A stale
        session — ``401``/``403``, or a ``3xx`` redirect to the login page —
        returns ``False`` WITHOUT following the hop (``allow_redirects=False``),
        so a dead session degrades to a fresh login instead of bouncing the
        authproxy against the IDP in a ``TooManyRedirects`` loop.

        On success it marks the connector logged-in so the caller can adopt the
        resumed session directly and skip ``begin_login()`` altogether.
        """
        url = f"{_SITE_BASE}{_RELATIONS_PATH}"
        headers = self._headers({
            "Accept": "application/json",
            "user-id": "__userId__",
            "Referer": _REDIRECT_URL,
        })
        try:
            async with self._session.get(
                url,
                headers=headers,
                allow_redirects=False,
                timeout=ClientTimeout(total=_TIMEOUT_S),
            ) as resp:
                alive = resp.status == 200
                _LOGGER.debug(
                    "Website authproxy resume probe → status %s (host %s)",
                    resp.status,
                    urlparse(str(resp.url)).hostname or "?",
                )
        except (ClientError, TimeoutError) as exc:
            _LOGGER.debug(
                "Website authproxy resume probe failed: %s", type(exc).__name__
            )
            return False
        if alive:
            self.logged_in = True
            _LOGGER.info(
                "Website authproxy: resumed session still valid "
                "(read-only, beta) — skipped re-login"
            )
        return alive

    # ── reads ──────────────────────────────────────────────────────────────

    async def _get_json(
        self,
        url: str,
        *,
        accept: str = "application/json",
        soft: bool = False,
        optional: bool = False,
        record_as: str | None = None,
    ) -> Any:
        """GET a reverse-proxy endpoint and parse JSON.

        Sends the per-endpoint ``Accept`` plus the literal
        ``user-id: __userId__`` placeholder the authproxy substitutes for the
        signed-in user's real id. On ``soft=True`` a transient 5xx returns
        ``None`` (after a short backoff) instead of raising — so a flaky
        backend just means "no data this poll" rather than a dead session.

        A 401/403 normally raises ``AuthenticationError`` so the caller can
        re-login — EXCEPT on an ``optional=True`` read, where a 4xx means "this
        car doesn't serve this endpoint" (not a dead session) and returns
        ``None``. 412 Precondition Failed always degrades to ``None`` (it is a
        per-vehicle precondition, e.g. the wrong-platform gdc, never a dead
        session). Session validity is decided by the core reads (relations /
        charging / maintenance), which keep raising on a genuine 401/403.
        (Backoff pattern mirrors the EU Data Act connector.)
        """
        headers = self._headers({
            "Accept": accept,
            "user-id": "__userId__",
            "Referer": _REDIRECT_URL,
        })
        for attempt in range(len(_RETRY_DELAYS) + 1):
            async with self._session.get(
                url,
                headers=headers,
                timeout=ClientTimeout(total=_TIMEOUT_S),
            ) as resp:
                if resp.status == 412:
                    # Per-vehicle precondition (e.g. an MBB car queried with the
                    # WeConnect gdc) — never a dead session → no data this poll.
                    _LOGGER.debug(
                        "Website authproxy GET %s → 412 precondition "
                        "(no data this poll)", url,
                    )
                    if record_as:
                        self.probe_outcomes[record_as] = "412 precondition (wrong-platform gdc?)"
                    return None
                if resp.status in _AUTH_FAIL_STATUSES:
                    if optional:
                        _LOGGER.debug(
                            "Website authproxy GET %s → HTTP %s (optional read "
                            "unavailable for this car — not a session failure)",
                            url, resp.status,
                        )
                        if record_as:
                            self.probe_outcomes[record_as] = str(resp.status)
                        return None
                    raise AuthenticationError(
                        f"Website authproxy GET {url} → HTTP {resp.status}"
                    )
                if resp.status >= 400:
                    if (
                        soft
                        and resp.status in _RETRIABLE_STATUSES
                        and attempt < len(_RETRY_DELAYS)
                    ):
                        await asyncio.sleep(_RETRY_DELAYS[attempt])
                        continue
                    if soft:
                        _LOGGER.debug(
                            "Website authproxy GET %s → HTTP %s "
                            "(soft; no data this poll)", url, resp.status,
                        )
                        if record_as:
                            self.probe_outcomes[record_as] = str(resp.status)
                        return None
                    raise AuthenticationError(
                        f"Website authproxy GET {url} → HTTP {resp.status}"
                    )
                body = await resp.json(content_type=None)
                self._capture_raw(url, body)
                if record_as:
                    # provisional; the caller refines to "200 no-value" when the
                    # body carries no usable reading (a degraded 200).
                    self.probe_outcomes[record_as] = "200"
                return body
        return None

    async def list_vehicle_vins(self) -> list[str]:
        """Return the 17-char VINs the signed-in account is related to.

        The relations payload nests the VIN under a per-vehicle relation
        object whose exact shape varies, so we scan the raw body for VIN
        tokens (the same robust approach used elsewhere for relation
        endpoints) and de-duplicate while preserving order.
        """
        url = f"{_SITE_BASE}{_RELATIONS_PATH}"
        headers = self._headers({
            "Accept": "application/json",
            "user-id": "__userId__",
            "Referer": _REDIRECT_URL,
        })
        async with self._session.get(
            url, headers=headers, timeout=ClientTimeout(total=_TIMEOUT_S),
        ) as resp:
            if resp.status in (401, 403):
                raise AuthenticationError(
                    f"Website authproxy: relations → HTTP {resp.status}"
                )
            if resp.status >= 400:
                raise AuthenticationError(
                    f"Website authproxy: relations → HTTP {resp.status}"
                )
            body = await resp.text(errors="replace")
        seen: list[str] = []
        for vin in _VIN_RE.findall(body):
            if vin not in seen:
                seen.append(vin)
        return seen

    async def get_relations(self) -> AuthproxyRelations | None:
        """Structured relations: VINs + ``mbbUserId`` + platform per vehicle.

        a13 — the clean counterpart to the regex ``list_vehicle_vins`` scan.
        Exposes ``mbbUserId`` (== the ``X-MbbUserId`` the MBB strategy needs) and
        ``modBackend`` (MBB vs MEB) so a future combined entry can self-discover
        VINs + user-id from the portal session instead of hard-coding them.
        Returns ``None`` on a transient backend hiccup (401/403 still raises).
        Also caches each VIN's platform backend for the live-status gdc pick.
        """
        from .._authproxy import parse_relations  # noqa: PLC0415

        body = await self._get_json(f"{_SITE_BASE}{_RELATIONS_PATH}", soft=True)
        rels = parse_relations(body) if body is not None else None
        if rels is not None:
            for v in rels.vehicles:
                # Empty string = "seen, no backend field" → WeConnect default,
                # and marks the VIN cached so _ensure_backend won't re-probe.
                self._vin_backend[v.vin] = v.mod_backend or ""
        return rels

    def _gdc(self, vin: str) -> str:
        """The live-status ``gdc`` for *vin* from its cached platform backend."""
        from .._authproxy import gdc_for_backend  # noqa: PLC0415

        return gdc_for_backend(self._vin_backend.get(vin))

    async def _ensure_backend(self, vin: str) -> None:
        """Resolve *vin*'s platform (MBB/MEB) once so ``_gdc`` picks right.

        The live-status reads need the correct global-data-centre id (an MBB car
        uses a different gdc than a WeConnect car — the wrong one 412s). We learn
        the platform from the relations parse; fetch it once and cache it. A
        genuine 401/403 still propagates (dead session → re-login); any other
        hiccup is swallowed and leaves the WeConnect default in place.
        """
        if vin in self._vin_backend:
            return
        try:
            await self.get_relations()
        except AuthenticationError:
            raise
        except Exception:  # noqa: BLE001
            _LOGGER.debug(
                "Website authproxy: platform probe skipped for %s", vin[-6:],
                exc_info=True,
            )

    async def get_master_data(self, vin: str) -> AuthproxyVehicleInfo:
        """Market model name / engine / year / colour (text + code) for *vin*."""
        from .._authproxy import (  # noqa: PLC0415
            AuthproxyVehicleInfo,
            build_vehicle_data_url,
            build_vehicle_details_url,
            parse_vehicle_data,
            parse_vehicle_details,
        )

        info = AuthproxyVehicleInfo()
        details = await self._get_json(build_vehicle_details_url(vin), soft=True)
        if details is not None:
            info = parse_vehicle_details(details, info)
        data = await self._get_json(build_vehicle_data_url(vin), soft=True)
        if data is not None:
            info = parse_vehicle_data(data, info)
        return info

    async def get_warning_lights(self, vin: str) -> int | None:
        """Count of currently-active dashboard warning lights for *vin*.

        BETA, fail-soft + OPTIONAL: any 4xx (incl. 401/403/412 — e.g. a car that
        doesn't serve this read) / parse-miss / empty body returns None; a
        transient 5xx is retried inside ``_get_json``. An empty ``warningLights``
        list is a valid "all OK ⇒ 0" reading (not None). This read never forces a
        re-login (see ``optional`` in ``_get_json``) — session validity is gated
        by the core reads. Uses the car's platform ``gdc`` (MBB vs WeConnect).
        ``Accept-Language: de-DE`` is load-bearing here (the endpoint 400s
        without a language) — sent by ``_headers()`` on every read.
        """
        from .._authproxy import (  # noqa: PLC0415
            build_warninglights_url,
            parse_warning_lights,
        )

        await self._ensure_backend(vin)
        body = await self._get_json(
            build_warninglights_url(vin, self._gdc(vin)),
            accept="*/*", soft=True, optional=True,
        )
        if body is None:
            return None
        count = parse_warning_lights(body)
        _LOGGER.debug(
            "Website authproxy warninglights %s → %s active", vin[-6:], count
        )
        return count

    async def get_parking_position(
        self, vin: str,
    ) -> tuple[float, float, str | None] | None:
        """Last-parked ``(lat, lon, carCapturedTimestamp)`` for *vin* — EXPERIMENTAL.

        Attempts the parkingposition read through the same WeConnect reverse-proxy
        realm that already carries charging + warning-lights. This is the one
        remaining attestation-free lever for VW EU GPS (#923): the CARIAD app
        backend's position endpoint is attestation-walled and 403 for EU passenger
        cars, and the EU Data Act live feed has no coordinate field. UNCONFIRMED —
        the proxy allowlist very likely excludes the position service, so this is
        fail-soft + optional exactly like ``get_warning_lights``: any 4xx / empty /
        parse-miss returns None and never forces a re-login. Returns coordinates
        only when the body actually carries a numeric lat+lon.
        """
        from .._authproxy import (  # noqa: PLC0415
            build_parkingposition_url,
            parse_parking_position,
        )

        await self._ensure_backend(vin)
        body = await self._get_json(
            build_parkingposition_url(vin, self._gdc(vin)),
            accept="*/*", soft=True, optional=True, record_as="parkingposition",
        )
        if body is None:
            return None
        parsed = parse_parking_position(body)
        if parsed is None:  # a degraded 200 that carried no coordinates
            self.probe_outcomes["parkingposition"] = "200 no-coords"
        _LOGGER.debug(
            "Website authproxy parkingposition %s → %s", vin[-6:],
            "coords" if parsed else "no coordinates in body",
        )
        return parsed

    async def get_battery_health(self, vin: str) -> float | None:
        """Battery State-of-Health % for *vin* via the vw.de proxy — EXPERIMENTAL.

        We Connect 4.3.2 added a native ``batteryHealthState`` capability, but the
        app reads it through the CARIAD BFF selectivestatus job
        (``stateOfHealth.ubeIndicator_pct``) which is Play-Integrity-walled (403 for
        VW EU passenger cars). Whether the attestation-free vw.de reverse-proxy
        exposes the same value — and at which subpath — is UNCONFIRMED, so this tries
        the ranked candidates in ``_SOH_PROBE_SUBPATHS`` and stops at the first that
        parses to a plausible %. Fail-soft + optional exactly like
        ``get_parking_position``: any 4xx / empty / parse-miss returns None and never
        forces a re-login. The raw body of every attempt is captured (VIN-stripped)
        into diagnostics by ``_get_json`` regardless, so a maintainer can inspect the
        real shape even when the parser declines. Once a candidate hits, its subpath
        is pinned so later polls issue a single request.
        """
        from .._authproxy import (  # noqa: PLC0415
            _SOH_PROBE_SUBPATHS,
            build_batteryhealth_url,
            parse_battery_health,
        )

        await self._ensure_backend(vin)
        candidates = (
            (self._soh_subpath,) if self._soh_subpath else _SOH_PROBE_SUBPATHS
        )
        for subpath in candidates:
            base = subpath.split("?")[0]
            body = await self._get_json(
                build_batteryhealth_url(vin, subpath, self._gdc(vin)),
                accept="*/*", soft=True, optional=True, record_as=f"soh:{base}",
            )
            if body is None:
                continue
            soh = parse_battery_health(body)
            if soh is not None:
                self._soh_subpath = subpath
                _LOGGER.debug(
                    "Website authproxy SoH %s via %s → %.1f%%",
                    vin[-6:], base, soh,
                )
                return soh
            self.probe_outcomes[f"soh:{base}"] = "200 no-value"
        _LOGGER.debug("Website authproxy SoH probe %s → no usable value", vin[-6:])
        return None

    async def get_last_lock_action(self, vin: str) -> tuple[str, str | None] | None:
        """Last confirmed remote lock/unlock command for *vin*.

        Returns ``(action, iso_timestamp_or_None)`` where action is
        ``"lock"``/``"unlock"`` — the newest ``actionSuccess`` command, else
        the newest overall. BETA, fail-soft + OPTIONAL: any 4xx / parse-miss / no
        lock message returns None and never forces a re-login (an MBB car
        401/403s here). This is the command HISTORY, not a live lock state
        (that's attestation-gated). Uses the car's platform ``gdc``.
        """
        from .._authproxy import (  # noqa: PLC0415
            build_transactionhistory_url,
            parse_lock_history,
        )

        await self._ensure_backend(vin)
        body = await self._get_json(
            build_transactionhistory_url(vin, self._gdc(vin)),
            accept="*/*", soft=True, optional=True,
        )
        if body is None:
            return None
        result = parse_lock_history(body)
        if result is not None:
            _LOGGER.debug(
                "Website authproxy lock history %s → last %s @ %s",
                vin[-6:], result[0], result[1],
            )
        return result

    async def get_relation_detail(self, vin: str) -> AuthproxyRelation | None:
        """Per-VIN relation detail (nickname + plate) via the SINGULAR endpoint.

        Fallback for accounts whose LIST relations omit nickname/plate — the
        common path threads both from ``get_relations()`` already. Fail-soft.
        """
        from .._authproxy import (  # noqa: PLC0415
            build_relation_detail_url,
            parse_relation_detail,
        )

        body = await self._get_json(build_relation_detail_url(vin), soft=True)
        return parse_relation_detail(body) if body is not None else None

    async def get_capabilities(self, vin: str) -> set[str]:
        """Enabled WeConnect capability ids for *vin* (``usercapabilities``).

        v2.16.2 (rafaelhutter v0.5.20 parity — GAP 4.1). Additive, read-only,
        fail-soft: any 4xx / parse-miss returns an empty set (a transient 5xx is
        retried inside ``_get_json``); OPTIONAL — never forces a re-login (an MBB
        car 401/403s here), session validity is gated by the core reads. Sends
        the car's platform ``gdc`` and the versioned
        ``application/json;version=3`` Accept the endpoint requires. Deliberately
        NOT called from ``get_vehicle_data``/the poll path: our capability filter
        is best-effort metadata, and auto-gating a sole-vw.de entry on it could
        hide entities — so wiring it into the entity filter stays a maintainer
        decision. Exposed here for read parity + explicit opt-in use.
        """
        from .._authproxy import (  # noqa: PLC0415
            build_usercapabilities_accept,
            build_usercapabilities_url,
            parse_usercapabilities,
        )

        await self._ensure_backend(vin)
        body = await self._get_json(
            build_usercapabilities_url(vin, self._gdc(vin)),
            accept=build_usercapabilities_accept(),
            soft=True, optional=True,
        )
        if body is None:
            return set()
        return parse_usercapabilities(body)

    async def get_exterior_images(self, vin: str) -> list[AuthproxyImage]:
        """Exterior render URLs ({url, angle, viewDirection}) for *vin*."""
        from .._authproxy import (  # noqa: PLC0415
            build_vehicle_images_url,
            parse_vehicle_images,
        )

        body = await self._get_json(build_vehicle_images_url(vin), soft=True)
        return parse_vehicle_images(body) if body is not None else []

    async def get_vehicle_data(self, vin: str) -> VehicleData:
        """Fetch charging + maintenance + live-status for *vin* → ``VehicleData``.

        Every read is ``soft`` / fail-soft — a transient backend hiccup or a
        parse-miss on any one leaves the corresponding fields unset instead of
        failing the whole poll. A real 401/403 on the CORE reads (the relations
        preflight / charging / maintenance) propagates so the caller re-logs in;
        the optional live-status reads and any 412 precondition degrade to
        no-data instead. The vehicle is marked online once any data block parsed
        successfully.

        v2.16.0 (BETA, opt-in) — three additive read-path fields, all
        disabled-by-default at the sensor layer (unvalidated live endpoints):
          * ``active_warning_lights_count`` ← warninglights/last count
          * ``last_lock_action`` / ``last_lock_action_at`` ← transactionhistory
          * ``vehicle_nickname`` / ``license_plate`` ← relations parse
        Each is wrapped so its own failure can never break the poll.
        """
        d = VehicleData(vin=vin)
        got_data = False

        # Resolve the car's platform (MBB/MEB) up front so the live-status reads
        # below pick the correct gdc, and reuse the parsed relations for the
        # nickname/plate enrich at the end (one relations fetch, not two). A
        # genuine 401/403 here propagates (dead session → re-login).
        rels: AuthproxyRelations | None = None
        try:
            rels = await self.get_relations()  # also populates self._vin_backend
        except AuthenticationError:
            raise
        except Exception:  # noqa: BLE001
            _LOGGER.debug(
                "Website authproxy relations preflight skipped for %s", vin[-6:],
                exc_info=True,
            )

        charging = await self._get_json(
            f"{_SITE_BASE}{_CHARGING_PATH.format(vin=vin)}",
            accept="*/*",
            soft=True,
        )
        if isinstance(charging, dict):
            map_charging_to_vehicle_data(charging, d)
            got_data = True

        maintenance = await self._get_json(
            f"{_SITE_BASE}{_MAINTENANCE_PATH.format(vin=vin)}",
            accept="*/*",
            soft=True,
        )
        if isinstance(maintenance, dict):
            map_maintenance_to_vehicle_data(maintenance, d)
            got_data = True

        # v2.16.0 — active dashboard warning-lights count (BETA, fail-soft).
        try:
            count = await self.get_warning_lights(vin)
            if count is not None:
                d.active_warning_lights_count = count
                got_data = True
        except AuthenticationError:
            raise
        except Exception:  # noqa: BLE001
            _LOGGER.debug(
                "Website authproxy warninglights read skipped for %s", vin[-6:],
                exc_info=True,
            )

        # v2.16.0 — last confirmed remote lock/unlock command (BETA, fail-soft).
        try:
            lock = await self.get_last_lock_action(vin)
            if lock is not None:
                d.last_lock_action, d.last_lock_action_at = lock
                got_data = True
        except AuthenticationError:
            raise
        except Exception:  # noqa: BLE001
            _LOGGER.debug(
                "Website authproxy lock-history read skipped for %s", vin[-6:],
                exc_info=True,
            )

        # v2.16.0 — nickname + licence plate from the relations LIST parse
        # (fetched up front above — reused here, no second round-trip). A miss
        # leaves both fields None; falls back to the singular per-VIN relation
        # detail only if the list omits this VIN.
        try:
            match = None
            if rels is not None:
                match = next(
                    (v for v in rels.vehicles if v.vin == vin), None
                )
            if match is None:
                match = await self.get_relation_detail(vin)
            if match is not None:
                if match.nickname:
                    d.vehicle_nickname = match.nickname
                if match.license_plate:
                    d.license_plate = match.license_plate
        except AuthenticationError:
            raise
        except Exception:  # noqa: BLE001
            _LOGGER.debug(
                "Website authproxy relation enrich skipped for %s", vin[-6:],
                exc_info=True,
            )

        # #923 — EXPERIMENTAL parkingposition read, gated on the opt-in test
        # cohort (``probe_position``, set by the coordinator from entry.data).
        # Attempts the same WeConnect proxy realm that already carries charging +
        # warning-lights — the only remaining attestation-free lever for VW EU GPS
        # (the CARIAD app position endpoint is attestation-walled + 403 for EU
        # passenger cars, and the EU Data Act live feed has no coordinate field).
        # Fail-soft, never forces a re-login. Self-limiting: it stops after a few
        # no-coordinate polls so a doomed request isn't sent forever; the moment
        # coordinates come back it latches on and keeps reading as a real feature.
        if self._should_probe_position():
            if not self._position_available:
                self._position_probe_tries += 1
            try:
                pos = await self.get_parking_position(vin)
                if pos is not None:
                    d.latitude, d.longitude, _pos_ts = pos
                    if _pos_ts:
                        d.position_captured_at = _pos_ts
                    got_data = True
                    self._position_available = True
            except AuthenticationError:
                raise
            except Exception:  # noqa: BLE001
                _LOGGER.debug(
                    "Website authproxy parkingposition read skipped for %s",
                    vin[-6:], exc_info=True,
                )

        # SoH probe (4.3.2 batteryHealthState) — same opt-in test-cohort gate as
        # the GPS probe. The app reads SoH via the attestation-walled BFF
        # selectivestatus job; this checks whether the attestation-free vw.de proxy
        # serves the same ``stateOfHealth.ubeIndicator_pct``. DIAGNOSTICS-ONLY: the
        # raw body is captured (redacted) for the shared cohort diagnostics; we do
        # NOT feed it to the SoH entity (which stays the user-nominal estimate) until
        # a real value is confirmed across cars. Fail-soft, self-limiting like GPS.
        if self._should_probe_soh():
            if not self._soh_available:
                self._soh_probe_tries += 1
            try:
                _soh = await self.get_battery_health(vin)
                if _soh is not None:
                    self._soh_available = True
            except AuthenticationError:
                raise
            except Exception:  # noqa: BLE001
                _LOGGER.debug(
                    "Website authproxy SoH probe skipped for %s",
                    vin[-6:], exc_info=True,
                )

        if got_data:
            d.connection_state = "online"

        # #1229 (Ra72xx) — surface the vw.de exterior renders as image entities.
        # This is the render source for VW-EU cars read over vw.de/portal, whose
        # CARIAD-BFF image endpoint is walled. get_exterior_images() already existed
        # but was never called; wire its {url, angle, viewDirection} list into
        # image_urls (one Image entity per view). Best-effort — never blocks the read.
        try:
            _imgs = await self.get_exterior_images(vin)
            _urls: dict[str, str] = {}
            for _i, _img in enumerate(_imgs):
                if not isinstance(_img.url, str) or not _img.url:
                    continue
                _parts = [p for p in (_img.view_direction, _img.angle) if p]
                _key = "_".join(_parts).strip().lower().replace(" ", "_") or f"view_{_i}"
                # keep every distinct URL even if two share a label
                if _key in _urls and _urls[_key] != _img.url:
                    _key = f"{_key}_{_i}"
                _urls[_key] = _img.url
            if _urls:
                d.image_urls = _urls
        except Exception:  # noqa: BLE001
            _LOGGER.debug("vw.de exterior images skipped for %s", vin[-6:])

        return d
