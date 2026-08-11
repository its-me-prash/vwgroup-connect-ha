# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Pure builders + parsers for the volkswagen.de **authproxy** data endpoints.

The myVolkswagen web portal reads vehicle-file data through a server-side
reverse-proxy on its own domain::

    https://www.volkswagen.de/app/authproxy/{realm}/proxy/{backend-path}?resourceHost={host}

Auth is a volkswagen.de **session cookie + X-CSRF-TOKEN** (double-submit); the
real Bearer is attached server-side and never reaches the client. These helpers
cover the static / semi-static **vehicle-file** reads — NOT live remote status,
which the portal does not expose for legacy MBB cars:

* ``relations``  → VIN + ``mbbUserId`` + platform (``modBackend``) discovery
* ``details`` / ``data`` → market model name, engine, colour (text + code)
* ``vehicleimages`` → exterior render URLs

Grounded on real captured responses (Golf GTE, MBB, 2026-06). Everything here is
pure (no I/O) so it unit-tests against fixtures; the session/transport lives in
``auth/_website_authproxy.py``.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

_AUTHPROXY_BASE = "https://www.volkswagen.de/app/authproxy"
_REALM_VWDE = "vw-de"
# The live-status endpoints (warninglights / transactionhistory / charging /
# maintenance) route through the WeConnect vehicle backend, a DIFFERENT
# function-access-group than the vehicle-file reads. Endpoint/param recipe
# cross-checked against rafaelhutter/ha-volkswagen-connect (MIT)
# website_portal.py:390,416; the parser below is our own.
_REALM_WECONNECT = "vwag-weconnect"

# Backend ``resourceHost`` ids the authproxy routes to (observed in captures).
_HOST_VUM = "myvw-vum-prod"
_HOST_VCF = "cwat-group-vehicle-file-service-prod"
_HOST_VILMA = "myvw-vilma-proxy-prod"
# Live-status endpoints pair a ``gdc`` (global-data-centre) id with a DIFFERENT
# VCF host than the static vehicle-file reads use above. Cross-checked against
# rafaelhutter website_portal.py:328,391,417 (MIT); our own builders below.
_HOST_VCF_LIVE = "myvw-vcf-prod"
_GDC_WCAR = "myvw-wcar-prod"  # WeConnect / MEB (ID.x) global-data-centre
_GDC_MBB = "myvw-mbb-prod"  # legacy MBB / Car-Net global-data-centre


def gdc_for_backend(mod_backend: str | None) -> str:
    """Map a vehicle's ``modBackend`` (from relations) to its live-status gdc.

    The myVolkswagen web app sends ``gdc=myvw-mbb-prod`` for legacy MBB/Car-Net
    cars and ``gdc=myvw-wcar-prod`` for WeConnect (MEB/ID.x) cars. Sending the
    WeConnect gdc to an MBB car makes every live-status read return HTTP 412
    Precondition Failed (verified live 2026-07-12 on an MBB Golf GTE — the web
    app itself calls ``…/tripdata/cyclic/last?gdc=myvw-mbb-prod``). Unknown /
    missing backend falls back to the WeConnect gdc (the historical default).
    """
    # #632 parity — the relations sentinel is SUFFIXED on real cars (e.g.
    # "MBB_ODP"), not a bare "MBB". An exact `== "MBB"` mis-routed those Car-Net
    # cars to the WeConnect gdc and 412'd every live-status read (no
    # warning-lights / lock-history / maintenance). Match the MBB prefix instead.
    return (
        _GDC_MBB
        if (mod_backend or "").strip().upper().startswith("MBB")
        else _GDC_WCAR
    )


def build_authproxy_url(
    path: str,
    *,
    realm: str = _REALM_VWDE,
    resource_host: str | None = None,
    gdc: str | None = None,
) -> str:
    """Assemble a ``/app/authproxy/{realm}/proxy/{path}`` URL.

    ``gdc`` + ``resource_host`` become query params (``gdc`` first, matching
    the order the myVolkswagen web app sends). Either may be omitted.
    """
    url = f"{_AUTHPROXY_BASE}/{realm}/proxy/{path.lstrip('/')}"
    params = []
    if gdc:
        params.append(f"gdc={gdc}")
    if resource_host:
        params.append(f"resourceHost={resource_host}")
    if params:
        url += "?" + "&".join(params)
    return url


def build_warninglights_url(vin: str, gdc: str | None = None) -> str:
    """Active dashboard warning-lights list (``warninglights/last``).

    Realm is the WeConnect vehicle backend, NOT ``vw-de``. Carries both
    ``gdc`` + the live VCF host, matching the myVolkswagen web app. ``gdc``
    selects the global-data-centre per car platform (see
    :func:`gdc_for_backend`); None keeps the historical WeConnect default.
    """
    return build_authproxy_url(
        f"vehicles/{vin}/warninglights/last",
        realm=_REALM_WECONNECT,
        resource_host=_HOST_VCF_LIVE,
        gdc=gdc or _GDC_WCAR,
    )


def build_parkingposition_url(vin: str, gdc: str | None = None) -> str:
    """Last-parked GPS position (``parkingposition``) — EXPERIMENTAL / UNCONFIRMED.

    Mirrors the warning-lights recipe exactly (WeConnect realm + live VCF host +
    per-platform ``gdc``), on the theory that the reverse-proxy which already
    passes charging + warning-lights may also pass position. This is NOT confirmed:
    the myVolkswagen website has no "where's my car" map, so the proxy allowlist
    very likely excludes the position service — expect 403/404/412. Wired
    best-effort behind a live probe (#923); if a portal-enrolled car returns
    ``{"data": {"lat", "lon"}}`` here, it becomes real live GPS for every VW EU
    authproxy user. The underlying source of truth is the CARIAD BFF
    ``/vehicle/v1/vehicles/{vin}/parkingposition`` (attestation-walled, 403 for VW
    EU post-lockdown), so this proxy path is the only remaining attestation-free
    lever.
    """
    return build_authproxy_url(
        f"vehicles/{vin}/parkingposition",
        realm=_REALM_WECONNECT,
        resource_host=_HOST_VCF_LIVE,
        gdc=gdc or _GDC_WCAR,
    )


def parse_parking_position(
    body: object,
) -> tuple[float, float, str | None] | None:
    """Extract ``(lat, lon, carCapturedTimestamp)`` from a parkingposition body.

    Same shape contract as the CARIAD-BFF read (vw_eu.py): coordinates live under
    ``data`` (``{"data": {"lat", "lon", "carCapturedTimestamp"}}``), with a
    top-level fallback for legacy/alternate firmwares. Returns ``None`` unless the
    body carries BOTH a numeric lat and lon — a degraded 200 with an empty data
    node must not overwrite a good last-known position with None (#923). The
    timestamp is returned as the raw ISO string (or None), matching how the BFF
    path stores ``position_captured_at``.
    """
    if not isinstance(body, dict):
        return None
    node = body.get("data")
    if not isinstance(node, dict):
        node = body  # top-level fallback
    lat = node.get("lat")
    lon = node.get("lon")
    if not isinstance(lat, (int, float)) or not isinstance(lon, (int, float)):
        return None
    if isinstance(lat, bool) or isinstance(lon, bool):  # bool is an int subclass
        return None
    ts = node.get("carCapturedTimestamp")
    ts_str = ts if isinstance(ts, str) and ts else None
    return float(lat), float(lon), ts_str


def build_transactionhistory_url(vin: str, gdc: str | None = None) -> str:
    """Remote-command history (lock/unlock lives here). Realm ``vw-de``.

    ``gdc`` selects the global-data-centre per car platform (see
    :func:`gdc_for_backend`); None keeps the historical WeConnect default.
    """
    return build_authproxy_url(
        f"vehicles/{vin}/transactionhistory",
        resource_host=_HOST_VCF_LIVE,
        gdc=gdc or _GDC_WCAR,
    )


def build_relation_detail_url(vin: str) -> str:
    """Per-VIN relation detail — ``{"relation": {...}}`` (nickname + plate).

    The singular counterpart to :func:`build_relations_url`. Only needed if
    the LIST endpoint ever omits nickname/plate for an account; the list
    parse already surfaces both field names for the common case.
    """
    return build_authproxy_url(
        f"v2/users/me/relations/{vin}", resource_host=_HOST_VUM
    )


def build_relations_url() -> str:
    """User↔vehicle relations (the VIN list + mbbUserId)."""
    return build_authproxy_url("v2/users/me/relations", resource_host=_HOST_VUM)


def build_vehicle_details_url(vin: str, locale: str = "de-DE") -> str:
    """Master data + the long ``specifications`` equipment list."""
    return build_authproxy_url(
        f"vehicles/{vin}/details/{locale}", resource_host=_HOST_VCF
    )


def build_vehicle_data_url(vin: str, locale: str = "de-DE") -> str:
    """Flat core record: vin, modelName, exteriorColor (code)."""
    return build_authproxy_url(f"vehicles/{vin}/data/{locale}", resource_host=_HOST_VCF)


def build_vehicle_images_url(vin: str) -> str:
    """Exterior render URLs (model-key + hash based, not VIN-specific)."""
    return build_authproxy_url(
        f"vehicleimages/exterior/{vin}", resource_host=_HOST_VILMA
    )


def build_usercapabilities_url(vin: str, gdc: str | None = None) -> str:
    """Per-vehicle capability list (``usercapabilities``). Realm ``vw-de``.

    v2.16.2 (rafaelhutter v0.5.20 parity — GAP 4.1) — the myVolkswagen web app
    reads the enabled-capabilities set for a car at
    ``application/json;version=3`` (see ``build_usercapabilities_accept``);
    the caller must send that Accept. Endpoint/Accept-version cross-checked
    against rafaelhutter/ha-volkswagen-connect (MIT) website_portal.py:22; the
    URL builder + parser here are our own. Additive read-only metadata — nothing
    in the poll path consumes it yet, so activating capability gating on a
    sole-vw.de entry stays a maintainer decision (it can hide entities).
    """
    return build_authproxy_url(
        f"vehicles/{vin}/usercapabilities",
        realm=_REALM_WECONNECT,
        resource_host=_HOST_VCF_LIVE,
        gdc=gdc or _GDC_WCAR,
    )


def build_usercapabilities_accept() -> str:
    """The versioned Accept the usercapabilities endpoint requires.

    Kept as a named helper (not an inline literal) so the one place that
    encodes the ``version=3`` contract is testable and reusable.
    """
    return "application/json;version=3"


# ── relations (VIN + mbbUserId discovery) ─────────────────────────────────────
@dataclass
class AuthproxyRelation:
    """One vehicle the account is related to."""

    vin: str
    nickname: str | None = None
    license_plate: str | None = None
    role: str | None = None
    role_status: str | None = None
    enrollment_status: str | None = None
    primary_car: bool = False
    mod_backend: str | None = None  # "MBB" / "MEB" / …
    relation_id: str | None = None
    euda_scoped: bool = False


@dataclass
class AuthproxyRelations:
    """Parsed ``/v2/users/me/relations`` — user identity + vehicle list."""

    user_id: str | None = None  # idKitUserId
    mbb_user_id: str | None = None  # mbbUserId (== X-MbbUserId)
    legal_entity: str | None = None  # VOLKSWAGEN / AUDI / …
    vehicles: list[AuthproxyRelation] = field(default_factory=list)

    @property
    def vins(self) -> list[str]:
        return [v.vin for v in self.vehicles if v.vin]


def _s(val: Any) -> str | None:
    """Coerce to a non-empty stripped string, else None."""
    if isinstance(val, str) and val.strip():
        return val.strip()
    return None


def parse_relations(raw: Any) -> AuthproxyRelations | None:
    """Parse the relations body into :class:`AuthproxyRelations`.

    Returns None only when the body isn't a dict at all; a dict with no
    relations yields an empty vehicle list (still carries the user identity).
    """
    if not isinstance(raw, dict):
        return None
    raw_user = raw.get("user")
    user: dict[str, Any] = raw_user if isinstance(raw_user, dict) else {}
    out = AuthproxyRelations(
        user_id=_s(user.get("idKitUserId")),
        mbb_user_id=_s(user.get("mbbUserId")),
        legal_entity=_s(user.get("legalEntityCode")),
    )
    relations = raw.get("relations")
    if not isinstance(relations, list):
        return out
    for rel in relations:
        if not isinstance(rel, dict):
            continue
        raw_veh = rel.get("vehicle")
        veh: dict[str, Any] = raw_veh if isinstance(raw_veh, dict) else {}
        vin = _s(veh.get("vin"))
        if not vin:
            continue
        tags = rel.get("tags")
        out.vehicles.append(
            AuthproxyRelation(
                vin=vin,
                nickname=_s(rel.get("vehicleNickname")),
                license_plate=_s(rel.get("licensePlate")),
                role=_s(rel.get("role")),
                role_status=_s(rel.get("roleStatus")),
                enrollment_status=_s(rel.get("enrollmentStatus")),
                primary_car=rel.get("primaryCar") is True,
                mod_backend=_s(veh.get("modBackend")),
                relation_id=_s(rel.get("relationId")),
                euda_scoped=isinstance(tags, list) and "EUDA_SCOPED" in tags,
            )
        )
    return out


def parse_relation_detail(raw: Any) -> AuthproxyRelation | None:
    """Parse the SINGULAR ``/relations/{vin}`` body → one :class:`AuthproxyRelation`.

    Shape is ``{"relation": {...}}`` (competitor website_portal.py:493), the same
    per-vehicle relation object the list endpoint nests under ``relations[*]`` —
    so we reuse the identical ``vehicleNickname`` / ``licensePlate`` field names.
    Returns None when the body isn't a dict with a relation object carrying a VIN.
    """
    if not isinstance(raw, dict):
        return None
    rel = raw.get("relation")
    if not isinstance(rel, dict):
        return None
    raw_veh = rel.get("vehicle")
    veh: dict[str, Any] = raw_veh if isinstance(raw_veh, dict) else {}
    vin = _s(veh.get("vin"))
    if not vin:
        return None
    tags = rel.get("tags")
    return AuthproxyRelation(
        vin=vin,
        nickname=_s(rel.get("vehicleNickname")),
        license_plate=_s(rel.get("licensePlate")),
        role=_s(rel.get("role")),
        role_status=_s(rel.get("roleStatus")),
        enrollment_status=_s(rel.get("enrollmentStatus")),
        primary_car=rel.get("primaryCar") is True,
        mod_backend=_s(veh.get("modBackend")),
        relation_id=_s(rel.get("relationId")),
        euda_scoped=isinstance(tags, list) and "EUDA_SCOPED" in tags,
    )


# ── live-status parsers (warning lights + lock history) ───────────────────────
def parse_warning_lights(raw: Any) -> int | None:
    """Count of currently-active dashboard warning lights.

    ``warninglights/last`` → ``body.data.warningLights`` is a JSON list; an
    EMPTY list is a valid "all OK ⇒ 0" reading, so only a missing/non-list
    node returns None. Logic mirrors competitor website_portal.py:398-403 (MIT);
    parser is our own.
    """
    if not isinstance(raw, dict):
        return None
    data = raw.get("data")
    if not isinstance(data, dict):
        return None
    lights = data.get("warningLights")
    if not isinstance(lights, list):
        return None
    return len(lights)


def parse_lock_history(raw: Any) -> tuple[str, str | None] | None:
    """Last confirmed remote lock/unlock command from the transaction log.

    NOT a live lock sensor — the live door/lock state sits behind the
    attestation-secured tier. This surfaces the newest ``remotelockunlock``
    command instead. Filter/sort/prefer-success logic cross-checked against
    competitor website_portal.py:424-443 (MIT); parser is our own:

    * keep messages with ``category == "remotelockunlock"`` and
      ``action in {"lock", "unlock"}``
    * sort ascending by ISO ``timestamp`` string
    * prefer the newest with ``actionSuccess`` truthy, else the newest overall
    * return ``(action, timestamp_or_None)`` — None when no lock message exists.
    """
    if not isinstance(raw, dict):
        return None
    data = raw.get("data")
    if not isinstance(data, dict):
        return None
    messages = data.get("messages")
    if not isinstance(messages, list):
        return None
    locks = [
        m
        for m in messages
        if isinstance(m, dict)
        and m.get("category") == "remotelockunlock"
        and m.get("action") in ("lock", "unlock")
    ]
    if not locks:
        return None
    locks.sort(key=lambda m: m.get("timestamp") or "")
    confirmed = [m for m in locks if m.get("actionSuccess")]
    chosen = (confirmed or locks)[-1]
    action = _s(chosen.get("action"))
    if not action:
        return None
    ts = _s(chosen.get("timestamp"))
    return action, ts


# ── master data (details + data) ──────────────────────────────────────────────
@dataclass
class AuthproxyVehicleInfo:
    """Merged master-data view from the ``details`` + ``data`` endpoints."""

    vin: str | None = None
    model_name: str | None = None
    model_year: str | None = None
    engine: str | None = None
    exterior_color_text: str | None = None  # "Oryxweiß Perlmutteffekt"
    exterior_color_code: str | None = None  # "0R"
    spec_count: int = 0


def parse_vehicle_details(raw: Any, into: AuthproxyVehicleInfo | None = None) -> AuthproxyVehicleInfo:
    """Fill model/engine/year/colour-text + spec count from ``details/{locale}``."""
    info = into or AuthproxyVehicleInfo()
    if not isinstance(raw, dict):
        return info
    info.model_name = _s(raw.get("modelName")) or info.model_name
    info.model_year = _s(raw.get("modelYear")) or info.model_year
    info.engine = _s(raw.get("engine")) or info.engine
    info.exterior_color_text = _s(raw.get("exteriorColorText")) or info.exterior_color_text
    specs = raw.get("specifications")
    if isinstance(specs, list):
        info.spec_count = len(specs)
    return info


def parse_vehicle_data(raw: Any, into: AuthproxyVehicleInfo | None = None) -> AuthproxyVehicleInfo:
    """Fill vin + colour-code (+ model name) from the flat ``data/{locale}``."""
    info = into or AuthproxyVehicleInfo()
    if not isinstance(raw, dict):
        return info
    info.vin = _s(raw.get("vin")) or info.vin
    info.model_name = _s(raw.get("modelName")) or info.model_name
    info.exterior_color_code = _s(raw.get("exteriorColor")) or info.exterior_color_code
    return info


# ── exterior images ───────────────────────────────────────────────────────────
@dataclass
class AuthproxyImage:
    url: str
    angle: str | None = None  # Left / Right / Center
    view_direction: str | None = None  # Side / Back / Front


def parse_vehicle_images(raw: Any) -> list[AuthproxyImage]:
    """Parse the structured ``images[]`` (preferred) or fall back to ``imageUrls[]``."""
    if not isinstance(raw, dict):
        return []
    images = raw.get("images")
    out: list[AuthproxyImage] = []
    if isinstance(images, list):
        for img in images:
            if not isinstance(img, dict):
                continue
            url = _s(img.get("url"))
            if not url:
                continue
            out.append(
                AuthproxyImage(
                    url=url,
                    angle=_s(img.get("angle")),
                    view_direction=_s(img.get("viewDirection")),
                )
            )
    if out:
        return out
    # Fallback: flat list of plain URL strings.
    urls = raw.get("imageUrls")
    if isinstance(urls, list):
        out = [AuthproxyImage(url=u) for u in urls if _s(u)]
    return out


def primary_image_url(images: list[AuthproxyImage]) -> str | None:
    """Pick a sensible hero render: prefer a Front view, then anything."""
    for img in images:
        if (img.view_direction or "").lower() == "front":
            return img.url
    return images[0].url if images else None


# ── usercapabilities (GAP 4.1, additive read-only metadata) ───────────────────
def parse_usercapabilities(raw: Any) -> set[str]:
    """Parse a ``usercapabilities`` body into the set of enabled capability ids.

    v2.16.2 (rafaelhutter v0.5.20 parity — GAP 4.1). The WeConnect capabilities
    surface is a ``{"capabilities": [{"id": "...", "status": [...]}...]}`` list;
    a capability counts as ENABLED when it carries no blocking ``status`` codes
    (an empty/absent ``status`` = available). Tolerates a bare list body and a
    flat ``["id", ...]`` list. Pure + defensive: a non-dict/parse-miss yields an
    empty set — never raises. Nothing in the poll path consumes this yet (see
    the connector docstring); it exists so the endpoint has read parity and is
    unit-testable without flipping capability gating on any live entry.
    """
    caps: Any
    if isinstance(raw, dict):
        caps = raw.get("capabilities")
    elif isinstance(raw, list):
        caps = raw
    else:
        return set()
    if not isinstance(caps, list):
        return set()
    enabled: set[str] = set()
    for cap in caps:
        if isinstance(cap, str):
            cid = _s(cap)
            if cid:
                enabled.add(cid)
            continue
        if not isinstance(cap, dict):
            continue
        cid = _s(cap.get("id"))
        if not cid:
            continue
        status = cap.get("status")
        # A capability with any status code(s) is disabled/degraded for this
        # user (the web app greys it out); no status = available.
        if isinstance(status, list) and status:
            continue
        enabled.add(cid)
    return enabled
