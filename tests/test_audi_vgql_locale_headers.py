# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Audi vgql locale headers — the model designation lives in the *localised*
``media.shortName``/``longName``. The backend only fills them when the request
carries ``Accept-Language`` + ``X-User-Country``; without them it answers with
``modelYear`` but ``media: null``, which left an S6 as a bare "Audi (2021)".

Live A/B proof (same token, same query): no locale headers → all media null;
``Accept-Language: de-DE`` + ``X-User-Country: DE`` → "Audi S6 Avant TDI quattro
tiptronic". These tests pin that we always send a valid locale (defaulting to DE)
and honour the account country.
"""
from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from custom_components.vag_connect.cariad.api.graphql import (
    _AUDI_APP_API_ENDPOINT,
    VehicleImageFetcher,
    _locale_headers,
)

_HAS = {
    "data": {
        "userVehicles": [
            {
                "vin": "WAUZZZTESTVHN0001",
                "nickname": None,
                "vehicle": {
                    "brand": {"name": "Audi"},
                    "core": {"modelYear": 2021},
                    "media": {"shortName": "Audi S6 Avant",
                              "longName": "Audi S6 Avant TDI quattro tiptronic"},
                    "renderPictures": [],
                },
            }
        ]
    }
}


class _Resp:
    def __init__(self, status: int, payload: Any) -> None:
        self.status = status
        self._payload = payload

    async def __aenter__(self) -> "_Resp":
        return self

    async def __aexit__(self, *_a: Any) -> bool:
        return False

    async def json(self) -> Any:
        return self._payload

    async def text(self) -> str:
        return ""


def _fetcher_capturing():
    """A fetcher whose session records the headers of every POST."""
    seen: list[dict[str, str]] = []
    sess = MagicMock()

    def _post(url, **kw):
        seen.append(dict(kw.get("headers") or {}))
        return _Resp(200, _HAS)

    sess.post = _post
    return VehicleImageFetcher(sess), seen


# ── the pure helper ──────────────────────────────────────────────────────────

def test_locale_headers_default_is_valid_de():
    # Unknown country must still send a valid locale (never null media again).
    assert _locale_headers(None) == {"Accept-Language": "de-DE", "X-User-Country": "DE"}
    assert _locale_headers("") == {"Accept-Language": "de-DE", "X-User-Country": "DE"}


@pytest.mark.parametrize(
    ("country", "lang_region", "ctry"),
    [
        ("DE", "de-DE", "DE"),
        ("de", "de-DE", "DE"),      # normalised to upper
        ("FR", "fr-FR", "FR"),
        ("IT", "it-IT", "IT"),
        ("CH", "de-CH", "CH"),      # multi-lingual → German (from the map)
        ("AT", "de-AT", "AT"),      # Austria → German, not "at-AT"
        ("BE", "nl-BE", "BE"),
        ("GB", "en-GB", "GB"),
    ],
)
def test_locale_headers_country_pairing(country, lang_region, ctry):
    h = _locale_headers(country)
    assert h["Accept-Language"] == lang_region
    assert h["X-User-Country"] == ctry


# ── the request actually carries the locale ─────────────────────────────────

@pytest.mark.asyncio
async def test_app_api_request_sends_locale_and_myaudi_headers():
    f, seen = _fetcher_capturing()
    result = await f.fetch_image_data(
        "tok", "audi", graphql_url=_AUDI_APP_API_ENDPOINT,
        app_api=True, country="DE",
    )
    assert result["WAUZZZTESTVHN0001"].long_name == "Audi S6 Avant TDI quattro tiptronic"
    assert len(seen) == 1
    h = seen[0]
    # the locale headers that make media populate
    assert h["Accept-Language"] == "de-DE"
    assert h["X-User-Country"] == "DE"
    # app_api=True → myAudi header shape on the app-api endpoint
    assert h["X-App-Name"] == "myAudi"


@pytest.mark.asyncio
async def test_request_without_country_still_sends_a_locale():
    # Regression: the old code sent NO locale header at all → null media.
    f, seen = _fetcher_capturing()
    await f.fetch_image_data("tok", "audi", graphql_url=_AUDI_APP_API_ENDPOINT, app_api=True)
    assert seen[0]["Accept-Language"] == "de-DE"
    assert seen[0]["X-User-Country"] == "DE"


@pytest.mark.asyncio
async def test_account_country_flows_into_the_request():
    f, seen = _fetcher_capturing()
    await f.fetch_image_data(
        "tok", "audi", graphql_url=_AUDI_APP_API_ENDPOINT, app_api=True, country="CH",
    )
    assert seen[0]["Accept-Language"] == "de-CH"
    assert seen[0]["X-User-Country"] == "CH"


@pytest.mark.asyncio
async def test_default_audi_path_also_carries_locale():
    # No explicit graphql_url → app-api-first branch must still send the locale.
    f, seen = _fetcher_capturing()
    await f.fetch_image_data("tok", "audi", country="FR")
    assert seen  # at least the app-api call happened
    assert seen[0]["Accept-Language"] == "fr-FR"
    assert seen[0]["X-User-Country"] == "FR"
