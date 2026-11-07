# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The coordinate SENT to Nominatim must be blunted, not just the cache key.

#60 made reverse geocoding opt-in because vehicle GPS is sensitive. The rounding
that opt-in implies reached only the cache key: ``cache_key = (round(lat, 3),
round(lon, 3))`` sat two lines above a URL built from the untouched ``lat``/
``lon``, so the full-precision parking position went to a third party while the
function's docstring and PRIVACY.md both promised ~110m.

Two things are asserted here, because either alone is satisfiable by broken
code. "No long decimal run in the URL" is also true of an empty URL, of
``lat=0``, and of a request that never happens — so the test also pins that the
value actually sent still identifies the same ~110m cell. A blunting that loses
the place is not a fix.

The regex is proved against a full-precision URL before it is trusted: a pattern
that cannot match is indistinguishable from a clean result.
"""
from __future__ import annotations

import asyncio
import re
from unittest.mock import MagicMock, patch

from custom_components.vag_connect.coordinator import VagConnectCoordinator

_SESSION = "homeassistant.helpers.aiohttp_client.async_get_clientsession"

#: Four or more digits after a decimal point — i.e. finer than the ~110m the
#: feature promises. Three decimals is the contract, so 4+ is the violation.
_TOO_PRECISE = re.compile(r"\d+\.\d{4,}")

#: Marienplatz, Munich — a public square, deliberately not anyone's address,
#: carried to seven decimals so any leak of raw precision is unmistakable.
#:
#: Both values sit near the MIDDLE of their ~110m cell, which matters for the
#: cache test below: the first pick was 48.1374987, a hair under the .1375
#: rounding boundary, so nudging it by 1e-5 landed in the NEXT cell and the
#: cache looked broken when it was behaving correctly. A coordinate chosen at a
#: cell edge tests the edge, not the cache.
LAT_IN = 48.1372345
LON_IN = 11.5762345

_PAYLOAD = {
    "address": {"road": "Marienplatz", "suburb": "Altstadt", "city": "Munich"},
    "display_name": "Marienplatz, Altstadt, Munich, Germany",
}


class _Resp:
    status = 200

    async def json(self):
        return _PAYLOAD


class _Ctx:
    async def __aenter__(self):
        return _Resp()

    async def __aexit__(self, *_exc):
        return False


class _Session:
    """Records every URL it is asked for; answers all of them the same way."""

    def __init__(self):
        self.urls: list[str] = []

    def get(self, url, **_kwargs):
        self.urls.append(url)
        return _Ctx()


def _coord():
    coord = VagConnectCoordinator.__new__(VagConnectCoordinator)
    coord.hass = MagicMock()
    return coord


def test_regex_catches_full_precision():
    """Positive control. Without this, a pattern typo reads as a clean URL."""
    old_style = (
        "https://nominatim.openstreetmap.org/reverse"
        f"?lat={LAT_IN}&lon={LON_IN}&format=json&addressdetails=1"
    )
    assert _TOO_PRECISE.search(old_style), "the instrument cannot see a leak"


def test_request_carries_no_more_than_three_decimals():
    coord = _coord()
    session = _Session()
    with patch(_SESSION, return_value=session):
        result = asyncio.run(coord._reverse_geocode(LAT_IN, LON_IN))

    assert len(session.urls) == 1, f"expected one request, got {session.urls}"
    url = session.urls[0]

    # 1. The promise: nothing finer than three decimals leaves the house.
    assert not _TOO_PRECISE.search(url), f"raw precision reached Nominatim: {url}"

    # 2. And it is still the right place — a blunting that sends 0,0 or drops
    #    the coordinate would satisfy (1) while breaking the feature.
    sent = {k: float(v) for k, v in re.findall(r"[?&](lat|lon)=([-\d.]+)", url)}
    assert set(sent) == {"lat", "lon"}, f"coordinate missing from {url}"
    assert abs(sent["lat"] - LAT_IN) <= 0.0005
    assert abs(sent["lon"] - LON_IN) <= 0.0005

    # The geocode itself still works, so this is not a test of a dead path.
    assert result is not None


def test_same_cell_is_requested_once():
    """The cache still keys on the blunted pair: two fixes 1e-5 apart — far
    inside one ~110m cell — must not produce a second outbound request.
    """
    coord = _coord()
    session = _Session()
    with patch(_SESSION, return_value=session):
        asyncio.run(coord._reverse_geocode(LAT_IN, LON_IN))
        asyncio.run(coord._reverse_geocode(LAT_IN + 1e-5, LON_IN + 1e-5))

    assert len(session.urls) == 1, f"cache stopped working: {session.urls}"
