# Copyright 2026 Prash Balan (@its-me-prash) — Apache License 2.0
# SPDX-License-Identifier: Apache-2.0
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
community VW website-portal connector (rafaelhutter/ha-volkswagen-connect);
the parser below is our own.
"""
from __future__ import annotations

import asyncio
import logging
import re
from typing import Any
from urllib.parse import parse_qs, urlparse

from aiohttp import ClientSession, ClientTimeout

from ..._canaries import CANARY_WEBSITE_AUTHPROXY
from ..exceptions import AuthenticationError, EmailTwoFactorRequiredError
from ..models import VehicleData
from ._eu_data_act import _login_fields, _login_error, _resolve_action

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
        d.odometer_km = odo

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

    # ── login ──────────────────────────────────────────────────────────────

    def _headers(self, extra: dict[str, str] | None = None) -> dict[str, str]:
        headers = {
            "User-Agent": _USER_AGENT,
            "Accept-Language": "de-DE,de;q=0.9,en;q=0.8",
        }
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
        async with self._session.get(
            f"{_SITE_BASE}{_LOGIN_PATH}",
            params=_LOGIN_PARAMS,
            headers=self._headers(),
            allow_redirects=True,
            timeout=ClientTimeout(total=_TIMEOUT_S),
        ) as resp:
            login_url = str(resp.url)
            login_html = await resp.text(errors="replace")
            login_status = resp.status

        if login_status >= 400:
            raise AuthenticationError(
                f"Website authproxy: login page HTTP {login_status}"
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

        async with self._session.post(
            post_url,
            data=fields,
            headers=self._headers({"Referer": login_url}),
            allow_redirects=True,
            timeout=ClientTimeout(total=_TIMEOUT_S),
        ) as resp:
            landed = str(resp.url)
            landed_html = await resp.text(errors="replace")
            landed_status = resp.status

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
        # The Auth0 email-challenge page is a form carrying hidden fields
        # (_csrf / relayState / hmac); a hardcoded {code, state} POST omits
        # them, which is what made the OTP "not transmit cleanly". Parse the
        # challenge form exactly like the password step (begin_login) and merge
        # the code into the real fields before POSTing to the form's action.
        fields, action = _login_fields(self._otp_html or "")
        fields["code"] = str(code).strip()
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
        async with self._session.get(
            f"{_SITE_BASE}{_LOGIN_PATH}",
            params=_LOGIN_PARAMS,
            headers=self._headers(),
            allow_redirects=True,
            timeout=ClientTimeout(total=_TIMEOUT_S),
        ) as resp:
            landed = str(resp.url)
            status = resp.status

        if status < 400 and urlparse(landed).netloc == urlparse(_SITE_BASE).netloc:
            # SSO cookie carried us straight back to the site — done.
            self._finalise_login(landed)
            if self.logged_in:
                return
        # SSO did not short-circuit — fall back to a full login.
        result = await self.begin_login()
        if result == "otp_required":
            raise EmailTwoFactorRequiredError()

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
        """Serialise volkswagen.de + vwgroup.io cookies for persistence.

        Domain-filtered so we never persist cookies that belong to other
        integrations sharing Home Assistant's aiohttp session.
        """
        out: list[dict[str, Any]] = []
        try:
            jar_iter = iter(self._session.cookie_jar)
        except Exception:  # noqa: BLE001
            return out
        for cookie in jar_iter:
            try:
                domain = str(cookie.get("domain") or cookie["domain"] or "")
            except (KeyError, AttributeError):
                continue
            if "volkswagen.de" not in domain and "vwgroup.io" not in domain:
                continue
            try:
                out.append({
                    "name": cookie.key,
                    "value": cookie.value,
                    "domain": domain,
                    "path": str(cookie.get("path") or "/"),
                    "expires": str(cookie.get("expires") or ""),
                    "secure": bool(cookie.get("secure") or False),
                    "httponly": bool(cookie.get("httponly") or False),
                })
            except Exception:  # noqa: BLE001
                continue
        return out

    def import_cookies(self, cookies: list[dict[str, Any]]) -> None:
        """Hydrate persisted volkswagen.de / vwgroup.io cookies into the jar.

        Lets a restarted Home Assistant resume the authproxy session (and skip
        the OTP prompt) without re-running the full login. Filtered to the two
        relevant domains so we never inject cookies for anything else.
        """
        if not cookies:
            return
        try:
            from http.cookies import Morsel  # noqa: PLC0415
            from yarl import URL  # noqa: PLC0415
        except ImportError:
            return
        for ck in cookies:
            if not isinstance(ck, dict):
                continue
            name = ck.get("name")
            value = ck.get("value")
            if not name or value is None:
                continue
            domain = str(ck.get("domain") or "")
            if "volkswagen.de" not in domain and "vwgroup.io" not in domain:
                continue
            morsel: Morsel[str] = Morsel()
            morsel.set(str(name), str(value), str(value))
            for attr in ("domain", "path", "expires", "secure", "httponly"):
                if attr in ck and ck[attr] not in (None, ""):
                    try:
                        morsel[attr] = ck[attr]
                    except (KeyError, ValueError):
                        pass
            url = URL(f"https://{domain.lstrip('.')}/")
            try:
                self._session.cookie_jar.update_cookies(
                    {str(name): morsel}, response_url=url,
                )
            except Exception:  # noqa: BLE001
                continue

    # ── reads ──────────────────────────────────────────────────────────────

    async def _get_json(
        self,
        url: str,
        *,
        accept: str = "application/json",
        soft: bool = False,
    ) -> Any:
        """GET a reverse-proxy endpoint and parse JSON.

        Sends the per-endpoint ``Accept`` plus the literal
        ``user-id: __userId__`` placeholder the authproxy substitutes for the
        signed-in user's real id. On ``soft=True`` a transient 5xx returns
        ``None`` (after a short backoff) instead of raising — so a flaky
        backend just means "no data this poll" rather than a dead session. A
        401/403 always raises ``AuthenticationError`` so the caller can
        re-login. (Backoff pattern mirrors the EU Data Act connector.)
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
                if resp.status in (401, 403):
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
                        return None
                    raise AuthenticationError(
                        f"Website authproxy GET {url} → HTTP {resp.status}"
                    )
                return await resp.json(content_type=None)
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

    async def get_vehicle_data(self, vin: str) -> VehicleData:
        """Fetch charging + maintenance for *vin* and map to ``VehicleData``.

        Both reads are ``soft`` — a transient backend hiccup on either one
        leaves the corresponding fields unset instead of failing the whole
        poll. A real 401/403 propagates so the caller re-logs in. The vehicle
        is marked online once any data block parsed successfully.
        """
        d = VehicleData(vin=vin)
        got_data = False

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

        if got_data:
            d.connection_state = "online"
        return d
