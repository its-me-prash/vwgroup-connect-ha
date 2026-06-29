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

# Backend ``resourceHost`` ids the authproxy routes to (observed in captures).
_HOST_VUM = "myvw-vum-prod"
_HOST_VCF = "cwat-group-vehicle-file-service-prod"
_HOST_VILMA = "myvw-vilma-proxy-prod"


def build_authproxy_url(
    path: str, *, realm: str = _REALM_VWDE, resource_host: str | None = None
) -> str:
    """Assemble a ``/app/authproxy/{realm}/proxy/{path}`` URL."""
    url = f"{_AUTHPROXY_BASE}/{realm}/proxy/{path.lstrip('/')}"
    if resource_host:
        url += f"?resourceHost={resource_host}"
    return url


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
