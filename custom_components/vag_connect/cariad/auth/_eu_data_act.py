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

import io
import json
import logging
import re
import uuid
import zipfile
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urljoin, urlparse

from aiohttp import ClientSession, ClientTimeout

from ..exceptions import AuthenticationError
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


def _login_error(html: str) -> str | None:
    """Return a human-readable login error from the page, if present."""
    model = _extract_template_model(html)
    err = model.get("error") or model.get("errorCode")
    if isinstance(err, dict):
        return err.get("text") or err.get("errorCode") or str(err)
    return str(err) if err else None


# ── Dataset parsing + curated field mapping ────────────────────────────────

def _walk_fields(payload: Any) -> dict[str, str]:
    """Flatten the EU Data Act dataset into ``{field_name: value}``.

    The portal ZIP contains a JSON dataset whose shape varies by firmware
    (flat eGolf vs structured MEB). We walk it defensively, collecting any
    node that carries a recognizable ``dataFieldName``/``name``+``value``
    pair, plus dotted-path fallbacks for nested ``{report: {field: v}}``
    shapes. Robust to wrapper differences.
    """
    out: dict[str, str] = {}

    def add(name: Any, value: Any) -> None:
        if isinstance(name, str) and name and value is not None:
            if isinstance(value, (str, int, float, bool)):
                out.setdefault(name, str(value))

    def walk(node: Any, prefix: str = "") -> None:
        if isinstance(node, dict):
            # data-point shape: {dataFieldName|name: X, value: Y}
            fname = node.get("dataFieldName") or node.get("name")
            if fname is not None and "value" in node:
                add(fname, node.get("value"))
            for k, val in node.items():
                if k in ("dataFieldName", "name", "value"):
                    continue
                key = f"{prefix}.{k}" if prefix else str(k)
                if isinstance(val, (str, int, float, bool)):
                    add(key, val)
                    add(str(k), val)
                else:
                    walk(val, key)
        elif isinstance(node, list):
            for item in node:
                walk(item, prefix)

    walk(payload)
    return out


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


def map_dataset_to_vehicle_data(fields: dict[str, str], d: VehicleData) -> VehicleData:
    """Map a curated subset of EU Data Act fields onto ``VehicleData``.

    v2.12.0 ships the ~15 highest-value fields users care about (odometer,
    SoC, range, charging state, doors). The long tail of the 300+ field
    dictionary follows in later v2.12.x once live payloads confirm shapes.
    ``fields`` may carry both the bare name (``soc``) and dotted variants
    (``battery_state_report.soc``); we try both.
    """
    def first(*names: str) -> str | None:
        for n in names:
            if n in fields:
                return fields[n]
        return None

    soc = _to_int(first("battery_state_report.soc", "soc", "stateOfChargeInPercent",
                        "state_of_charge"))
    if soc is not None:
        d.battery_soc = soc
        d.has_battery = True

    odo = _to_int(first("mileage.value", "mileage", "odometer", "totalMileage"))
    if odo is not None:
        d.odometer_km = odo

    rng = _to_int(first("range", "cruising_range_primary_engine",
                        "totalRange_km", "primaryEngineRange"))
    if rng is not None:
        d.range_km = rng
        if d.electric_range_km is None:
            d.electric_range_km = rng

    cp = _to_float(first("battery_state_report.charge_power", "charge_power",
                        "chargePower_kW"))
    if cp is not None:
        d.charging_power_kw = cp

    tsoc = _to_int(first("settings.target_soc", "target_soc", "targetSOC_pct"))
    if tsoc is not None:
        d.target_soc = tsoc

    cs = first("charging_state_report.current_charge_state", "current_charge_state",
               "chargingState", "charging_state")
    if cs:
        d.charging_state = cs
        d.is_charging = cs.lower() in ("charging", "chargingacactive", "active")

    cmode = first("charging_state_report.charge_mode", "charge_mode")
    if cmode:
        d.charge_mode = cmode

    tmin = _to_float(first("min_temperature", "battery_min_temperature"))
    if tmin is not None:
        d.hv_battery_min_temperature_c = tmin
    tmax = _to_float(first("max_temperature", "battery_max_temperature"))
    if tmax is not None:
        d.hv_battery_max_temperature_c = tmax

    locked = first("locked", "doors_locked", "doorLockStatus")
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

    async def login(self, email: str, password: str) -> None:
        """Run the OIDC code-flow login; portal backend sets cookies."""
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

        if status >= 400:
            err = _login_error(landing_html)
            raise AuthenticationError(
                err or f"EU Data Act portal: login rejected (HTTP {status})"
            )
        # A completed flow lands back on the portal host via
        # /services/callbacklogin. Bad credentials re-render signin-service.
        portal_host = urlparse(_PORTAL_BASE).netloc
        if "signin-service" in landing or "/error" in landing:
            raise AuthenticationError(
                "EU Data Act portal: login failed — check email and password"
            )
        if urlparse(landing).netloc != portal_host:
            raise AuthenticationError(
                f"EU Data Act portal: login did not complete (ended at "
                f"{landing[:80]})"
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
        "not provisioned yet" statuses (404/410/500/502/503). Used for the
        data-request metadata endpoint, which 404s/500s on accounts where
        the continuous data request hasn't been enabled / hasn't propagated
        yet (#393, #424) — that's an expected transient, not a hard error.
        """
        async with self._session.get(
            url, headers=headers, timeout=ClientTimeout(total=_TIMEOUT_S),
        ) as resp:
            if resp.status >= 400:
                if soft and resp.status in (404, 410, 500, 502, 503):
                    return None
                raise AuthenticationError(f"EU Data Act GET {url} → HTTP {resp.status}")
            return await resp.json(content_type=None)

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

    async def get_vehicle_data(self, vin: str) -> VehicleData:
        """Fetch the latest dataset for *vin* and map it to VehicleData."""
        d = VehicleData(vin=vin)
        # 1. metadata → identifier. Soft on 404/500: when the continuous
        # data request isn't set up / hasn't propagated yet, the endpoint
        # 404s or 500s. Treat that as "no data yet" — return the bare
        # VehicleData so the vehicle still appears and the data fills in
        # once the portal request goes active, instead of erroring every
        # poll (#393, #424).
        meta = await self._get_json(
            f"{_PORTAL_BASE}{_METADATA_PATH.format(vin=vin)}", soft=True,
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
        # 2. list datasets → newest non-empty zip
        listing = await self._get_json(
            f"{_PORTAL_BASE}{_LIST_PATH.format(vin=vin, identifier=identifier)}",
            headers={"type": "partial"},
        )
        files = listing if isinstance(listing, list) else listing.get("files", [])
        names: list[str] = []
        for f in files:
            if not isinstance(f, dict):
                continue
            name = f.get("name")
            if isinstance(name, str) and not name.endswith(_NO_CONTENT_SUFFIX):
                names.append(name)
        if not names:
            self.last_no_data_reason = "empty"
            _LOGGER.debug("EU Data Act portal: no dataset files for %s yet", vin[-6:])
            return d
        newest = names[-1]
        # 3. download ZIP → JSON
        async with self._session.get(
            f"{_PORTAL_BASE}{_DOWNLOAD_PATH.format(vin=vin, identifier=identifier)}",
            headers={"filename": newest, "type": "partial"},
            timeout=ClientTimeout(total=_TIMEOUT_S),
        ) as resp:
            if resp.status >= 400:
                raise AuthenticationError(
                    f"EU Data Act portal: download → HTTP {resp.status}"
                )
            raw = await resp.read()
        payload = _unzip_json(raw, newest)
        fields = _walk_fields(payload)
        _LOGGER.debug(
            "EU Data Act portal: %s dataset carried %d fields", vin[-6:], len(fields)
        )
        self.last_no_data_reason = ""
        d.connection_state = "online"
        return map_dataset_to_vehicle_data(fields, d)

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
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as zf:
            members = [n for n in zf.namelist() if n.lower().endswith(".json")]
            if not members:
                raise AuthenticationError(f"EU Data Act portal: no JSON in {name}")
            with zf.open(members[0]) as fh:
                parsed = json.loads(fh.read().decode("utf-8"))
            return parsed if isinstance(parsed, dict) else {}
    except (zipfile.BadZipFile, ValueError) as err:
        raise AuthenticationError(
            f"EU Data Act portal: could not read {name}: {err}"
        ) from err
