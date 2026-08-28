# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""VAG Group GraphQL client for vehicle render images.

Fetches render image URLs via the VW Group vgql proxy.
Images are publicly accessible (no auth needed to GET the PNG URL).

Endpoint confirmed working for Audi (April 2026):
  POST https://www.audi.de/userinfo-emea/v2/myaudi/proxy/vgql/v1/graphql
  Auth: Bearer {IDK access_token}

Research source: vag-connect-ha Issue #15
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from aiohttp import ClientSession, ClientTimeout

_LOGGER = logging.getLogger(__name__)

# GraphQL endpoints per brand
_GRAPHQL_ENDPOINTS: dict[str, str] = {
    "audi":       "https://www.audi.de/userinfo-emea/v2/myaudi/proxy/vgql/v1/graphql",
    "volkswagen": "https://www.volkswagen.de/app/proxy/vgql/v1/graphql",
    "skoda":      "https://www.skoda-auto.com/myskoda/proxy/vgql/v1/graphql",
    "seat":       "https://www.seat.com/myway/proxy/vgql/v1/graphql",
    "cupra":      "https://www.cupraofficial.com/mycupra/proxy/vgql/v1/graphql",
}

# Portal base URLs — used to establish session before GraphQL call
_PORTAL_AUTH_URLS: dict[str, str] = {
    "audi":       "https://www.audi.de/userinfo-emea/v2/myaudi/authenticated",
    "volkswagen": "https://www.volkswagen.de/userinfo-emea/v2/myvw/authenticated",
    "skoda":      "https://www.skoda-auto.com/userinfo-emea/v2/myskoda/authenticated",
    "seat":       "https://www.seat.com/userinfo-emea/v2/myseat/authenticated",
    "cupra":      "https://www.cupraofficial.com/userinfo-emea/v2/mycupra/authenticated",
}

# Corrected VW EU GraphQL endpoint (verified via network inspection)
# VW EU GraphQL: portal lives on myvw.volkswagen.de
_GRAPHQL_ENDPOINTS["volkswagen"] = "https://myvw.volkswagen.de/userinfo-emea/v2/myvw/proxy/vgql/v1/graphql"

# Audi PRIMARY vgql source — the myAudi app-API. This is the endpoint the classic
# myAudi clients read the vehicle list + ``media.longName`` from, and it serves
# accounts the ``www.audi.de`` web-proxy above rejects (a rejected proxy is why an
# Audi S6 fell back to a bare "Audi (2021)" with no model). Preferred for Audi;
# the web-proxy is kept as the fallback. (US accounts point at the AoA host.)
_AUDI_APP_API_ENDPOINT = "https://app-api.live-my.audi.com/vgql/v1/graphql"
_AUDI_APP_API_ENDPOINT_US = "https://app-api.my.aoa.audi.com/vgql/v1/graphql"

# Brand-specific client IDs for the vgql proxy (X-App-ID header)
_BRAND_APP_IDS: dict[str, str] = {
    "audi":       "de.audi.myaudi",
    "volkswagen": "de.volkswagen.myvw",
    "skoda":      "cz.skodaauto.myskoda",
    "seat":       "es.seat.myseat",
    "cupra":      "com.cupraofficial.mycupra",
}

# v2.15.3 — brand-aware app version + User-Agent for the vgql proxy. Previously
# every brand sent the hardcoded myAudi build, which can get a foreign-brand
# request flagged by the proxy. Map per brand; fall back to the Audi build.
_BRAND_APP_VERSIONS: dict[str, str] = {
    "audi":       "5.5.1",
    "volkswagen": "4.27.0",
    "skoda":      "7.20.0",
    "seat":       "3.0.0",
    "cupra":      "3.0.0",
}
_BRAND_USER_AGENTS: dict[str, str] = {
    "audi":       "myAudi/5.5.1 Android/34",
    "volkswagen": "We Connect/4.27.0 Android/34",
    "skoda":      "myŠkoda/7.20.0 Android/34",
    "seat":       "SEAT CONNECT/3.0.0 Android/34",
    "cupra":      "MyCUPRA/3.0.0 Android/34",
}

# Complete metadata for all 7 render image types
# Order = preference (best for Lovelace first)
RENDER_IMAGE_TYPES: list[dict[str, str]] = [
    {
        "media_type":       "MYAPN8NB",
        "entity_suffix":    "render_side_lg",
        "tag":              "side_large",
        "view_description": "Seitenprofil groß",
        "recommended_use":  "⭐ Empfohlen für Lovelace-Karten und Dashboards",
        "file_size_approx": "309 KB",
    },
    {
        "media_type":       "MYAAN8NB",
        "entity_suffix":    "render_angle_lg",
        "tag":              "angle_large",
        "view_description": "3/4-Ansicht groß",
        "recommended_use":  "Dashboard-Karten, Picture-Entity Cards",
        "file_size_approx": "879 KB",
    },
    {
        "media_type":       "MS_MYP5",
        "entity_suffix":    "render_medium",
        "tag":              "medium",
        "view_description": "3/4-Ansicht mittel",
        "recommended_use":  "Standard-Karten, Grid-Layouts",
        "file_size_approx": "196 KB",
    },
    {
        "media_type":       "MYAPN3NB",
        "entity_suffix":    "render_side_sm",
        "tag":              "side_small",
        "view_description": "Seitenprofil klein",
        "recommended_use":  "Kompakte Seitenansicht, horizontale Karten",
        "file_size_approx": "158 KB",
    },
    {
        "media_type":       "MS_MYP4",
        "entity_suffix":    "render_small",
        "tag":              "small",
        "view_description": "3/4-Ansicht klein",
        "recommended_use":  "Kleine Karten, Sidebar-Widgets",
        "file_size_approx": "117 KB",
    },
    {
        "media_type":       "MS_MYP3",
        "entity_suffix":    "render_icon",
        "tag":              "icon",
        "view_description": "3/4-Ansicht Icon",
        "recommended_use":  "Mini-Icon in Listen, Badges, Chip-Cards",
        "file_size_approx": "76 KB",
    },
    {
        "media_type":       "MYAAN3NB",
        "entity_suffix":    "render_angle_hd",
        "tag":              "angle_hd",
        "view_description": "3/4-Ansicht HD",
        "recommended_use":  "Hero-Banner, Vollbild-Dashboards, Wallpaper",
        "file_size_approx": "1.7 MB",
    },
]

# Quick lookup: media_type → metadata dict
RENDER_TYPE_BY_MEDIA: dict[str, dict[str, str]] = {
    r["media_type"]: r for r in RENDER_IMAGE_TYPES
}

# Preferred order for "best single image" fallback
_PREFERRED_ORDER = [r["media_type"] for r in RENDER_IMAGE_TYPES]

_GQL_QUERY = """
query GET_USER_VEHICLES {
  userVehicles {
    vin
    nickname
    csid
    vehicle {
      brand { name }
      core { modelYear }
      classification { driveTrain }
      media {
        shortName
        longName
        exteriorColor
        interiorColor
      }
      renderPictures {
        mediaType
        url
      }
    }
  }
}
"""


@dataclass
class VehicleImageData:
    """All render image data for a single vehicle."""

    vin: str
    image_urls: dict[str, str]          # {mediaType: public URL}
    short_name: str | None = None       # e.g. "Q4 e-tron"
    long_name: str | None = None        # e.g. "Audi Q4 50 e-tron quattro"
    exterior_color: str | None = None
    nickname: str | None = None         # User-set nickname in app
    model_year: int | None = None       # e.g. 2021 (vehicle.core.modelYear)
    # vgql authoritative drivetrain classification (vehicle.classification.driveTrain,
    # e.g. "electric" / "hybrid" / "gasoline" / "diesel") + the stable customer-
    # service id. Both are fetched on the same userVehicles query we already run for
    # the model name; the official myAudi client reads them here too.
    drive_train: str | None = None
    csid: str | None = None


# v4.4.0 — the vehicle model designation lives in ``media.shortName`` /
# ``media.longName``, which are *localised* catalog strings. The vgql backend
# only fills them when the request carries a locale: without ``Accept-Language``
# + ``X-User-Country`` it answers with ``modelYear`` but ``media: null``, which
# left cars as a bare "Audi (2021)". Live A/B proof (same token, same query):
# no locale headers → all media null; ``Accept-Language: de-DE`` +
# ``X-User-Country: DE`` → "Audi S6 Avant TDI quattro tiptronic". The classic
# myAudi / We Connect clients always send them (cf. audi_connect
# audi_services.py). We take the country from the account id-token and pair it
# with a sensible language (the two never have to match perfectly — the model
# names are language-neutral; the point is that a valid locale is present).
_COUNTRY_LANG: dict[str, str] = {
    "AT": "de", "CH": "de", "LI": "de", "BE": "nl", "LU": "fr",
    "GB": "en", "UK": "en", "IE": "en",
}


def _locale_headers(country: str | None) -> dict[str, str]:
    """``Accept-Language`` + ``X-User-Country`` so the vgql returns localised
    ``media`` (the model name). Defaults to DE — a safe EU default that always
    populates media — when the account country is unknown."""
    ctry = (country or "DE").strip().upper() or "DE"
    lang = _COUNTRY_LANG.get(ctry, ctry.lower())
    return {"Accept-Language": f"{lang}-{ctry}", "X-User-Country": ctry}


class VehicleImageFetcher:
    """Fetches vehicle render image URLs via VW Group GraphQL API.

    fetch_image_data(access_token, brand) → dict[vin, VehicleImageData]
    URLs are public — no further auth needed to GET the actual PNG.
    """

    def __init__(self, session: ClientSession) -> None:
        self._session = session

    async def fetch_image_data(
        self, access_token: str, brand: str, graphql_url: str | None = None,
        *, app_api: bool = False, country: str | None = None,
    ) -> dict[str, VehicleImageData]:
        """Return {vin: VehicleImageData} for all vehicles in the account.

        graphql_url: override the default endpoint for this brand.
        app_api: send the myAudi app-API header shape (X-App-Name) — set it when
            the override URL is the app-api vgql, so it gets the right headers.
        country: account country (ISO-2) for the locale headers that make the
            backend return the localised ``media`` model name; see
            ``_locale_headers``.
        Returns empty dict on any error — images are optional, never block startup.

        Audi resilience: the primary vgql source is the ``www.audi.de`` web-proxy,
        which rejects some accounts' BFF tokens outright (HTTP 4xx → the car falls
        back to a bare "Audi (2021)"). The myAudi app-API vgql
        (``app-api.live-my.audi.com``) is the more reliable source — it's what the
        classic myAudi clients read the vehicle list + ``media.longName`` from. So
        for Audi we fall back to it when the web-proxy returns nothing, unless the
        caller pinned an explicit ``graphql_url``.
        """
        if graphql_url is not None:  # an explicit override always wins
            return await self._fetch_from(
                graphql_url, access_token, brand, app_api=app_api, country=country,
            )

        if brand.lower() == "audi":
            # myAudi app-API FIRST (the proven source, what the classic myAudi
            # clients use), then the www.audi.de web-proxy as a fallback. Either
            # order alone leaves some accounts without a model; try both.
            result = await self._fetch_from(
                _AUDI_APP_API_ENDPOINT, access_token, brand, app_api=True,
                country=country,
            )
            if not result:
                _LOGGER.info(
                    "Audi app-API vgql returned no vehicles — falling back to the "
                    "www.audi.de web-proxy",
                )
                result = await self._fetch_from(
                    _GRAPHQL_ENDPOINTS["audi"], access_token, brand, country=country,
                )
            return result

        endpoint = _GRAPHQL_ENDPOINTS.get(brand.lower())
        if not endpoint:
            _LOGGER.debug("No GraphQL endpoint configured for brand '%s'", brand)
            return {}
        return await self._fetch_from(endpoint, access_token, brand, country=country)

    async def _fetch_from(
        self, endpoint: str, access_token: str, brand: str, *,
        app_api: bool = False, country: str | None = None,
    ) -> dict[str, VehicleImageData]:
        """POST the userVehicles query to one endpoint and parse it, or {} on error."""
        if app_api:
            # myAudi app-API headers (matches the classic myAudi client shape).
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type":  "application/json; charset=utf-8",
                "Accept":        "application/json",
                "X-App-Name":    "myAudi",
                "X-App-Version": _BRAND_APP_VERSIONS.get(brand.lower(), "5.5.1"),
                "User-Agent":    _BRAND_USER_AGENTS.get(
                    brand.lower(), "myAudi/5.5.1 Android/34"),
            }
        else:
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type":  "application/json",
                "Accept":        "application/json",
                "X-App-ID":      _BRAND_APP_IDS.get(brand.lower(), "de.audi.myaudi"),
                # v2.15.3 — brand-aware version + UA (Audi build as fallback).
                "X-App-Version": _BRAND_APP_VERSIONS.get(brand.lower(), "5.5.1"),
                "User-Agent":    _BRAND_USER_AGENTS.get(
                    brand.lower(), "myAudi/5.5.1 Android/34"),
            }
        # Localised model strings (media.shortName/longName) only come back when
        # the request carries a locale — see _locale_headers.
        headers.update(_locale_headers(country))
        try:
            async with self._session.post(
                endpoint,
                json={"query": _GQL_QUERY},
                headers=headers,
                timeout=ClientTimeout(total=15),
            ) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    _LOGGER.warning(
                        "GraphQL images failed for %s: HTTP %d @ %s — %s",
                        brand, resp.status, endpoint, body[:200],
                    )
                    return {}
                data = await resp.json()
        except Exception as err:  # noqa: BLE001
            err_str = str(err)
            if err_str:
                _LOGGER.warning("GraphQL image fetch failed for %s: %s", brand, err_str)
            else:
                # Empty error = connection reset / server blocked request (common for non-Audi brands)
                _LOGGER.debug(
                    "GraphQL images unavailable for %s (connection reset — server may block non-browser requests)",
                    brand,
                )
            return {}
        return self._parse_response(data)

    @staticmethod
    def _parse_response(data: dict[str, Any]) -> dict[str, VehicleImageData]:
        """Extract VehicleImageData per VIN from GraphQL response.

        v1.25.0 PR-B (Audit Agent C, upstream #709 lesson):
        PPC / PPE platform vehicles (Audi Q5 PPC 2025+, Q6/A6 PPE) can
        return ``"errors": [{"path": ["userVehicles", N, "vehicle",
        "core"], "extensions": {"code": "INTERNAL_SERVER_ERROR"}}]``
        on the bulk ``userVehicles { core mappingVin }`` query — the
        backend bursts on the affected VIN's ``core`` field while
        other VINs in the same response are fine.

        We log the error path → VIN mapping so support can see exactly
        which VIN's ``core`` blew up, then continue parsing the
        remaining vehicles. Skipping bad-vehicle entries is correct
        — the user's other cars still render.
        """
        result: dict[str, VehicleImageData] = {}
        # Surface PPC/PPE GraphQL partial-failure paths if present
        errors = data.get("errors") if isinstance(data, dict) else None
        if isinstance(errors, list) and errors:
            for err in errors:
                if not isinstance(err, dict):
                    continue
                code = (err.get("extensions") or {}).get("code", "?")
                path = err.get("path", [])
                msg = err.get("message", "")
                _LOGGER.info(
                    "GraphQL partial error (PPC/PPE platform pattern): "
                    "code=%s path=%s msg=%s — affected VIN(s) skipped, "
                    "other vehicles render normally",
                    code, path, msg[:120],
                )
        try:
            vehicles = data.get("data", {}).get("userVehicles", []) or []
            for v in vehicles:
                vin = v.get("vin")
                if not vin:
                    continue
                vehicle = v.get("vehicle") or {}
                media   = vehicle.get("media") or {}
                core    = vehicle.get("core") or {}
                pictures = vehicle.get("renderPictures") or []

                # v2.19.0 — model year (vehicle.core.modelYear) for the rich
                # "<model> (<year>)" device name. Coerce str/int defensively.
                _my_raw = core.get("modelYear")
                _model_year: int | None = None
                if isinstance(_my_raw, int):
                    _model_year = _my_raw
                elif isinstance(_my_raw, str) and _my_raw.strip().isdigit():
                    _model_year = int(_my_raw.strip())

                urls: dict[str, str] = {}
                for pic in pictures:
                    mt  = pic.get("mediaType")
                    url = pic.get("url")
                    if mt and url:
                        urls[mt] = url

                _drive_train = (vehicle.get("classification") or {}).get("driveTrain")
                _csid = v.get("csid")
                result[vin] = VehicleImageData(
                    vin=vin,
                    image_urls=urls,
                    short_name=media.get("shortName"),
                    long_name=media.get("longName"),
                    exterior_color=media.get("exteriorColor"),
                    nickname=v.get("nickname"),
                    model_year=_model_year,
                    drive_train=_drive_train if isinstance(_drive_train, str) else None,
                    csid=_csid if isinstance(_csid, str) else None,
                )
                _LOGGER.debug(
                    "GraphQL images for %s (%s): %d mediaTypes",
                    vin, media.get("shortName", "?"), len(urls),
                )
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug("GraphQL response parse error: %s", err)
        return result

    @staticmethod
    def best_url(image_urls: dict[str, str] | None) -> str | None:
        """Return the best available image URL (MYAPN8NB preferred)."""
        if not image_urls:
            return None
        for mt in _PREFERRED_ORDER:
            url = image_urls.get(mt)
            if url:
                return url
        return next(iter(image_urls.values()), None)
