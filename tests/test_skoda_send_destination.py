# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""MyŠkoda send-to-car (APK-grounded, 8.15.0, LIVE-GATED).

POST api/v3/maps/navigation/destination, @Body SendDestinationRequestDto (Moshi,
bff_maps/v3): required id/type/vin; optional name/coordinates/address. type is a
closed place-kind vocabulary (wt0/l.smali) — a raw coordinate is "LOCATION".
coordinates is GpsCoordinatesDto{latitude,longitude} (NOT the SEAT/CUPRA shape).
"""
from __future__ import annotations

import asyncio
import uuid
from unittest.mock import AsyncMock, MagicMock

from custom_components.vag_connect.cariad.api.skoda import SkodaClient


def _client() -> SkodaClient:
    c = SkodaClient(MagicMock(), "u@t.de", "pw")
    c._post = AsyncMock()  # type: ignore[method-assign]
    return c


def _call(c: SkodaClient) -> tuple[str, dict]:
    a = c._post.call_args
    return a.args[0], a.kwargs.get("json")


def test_coordinate_only_body() -> None:
    c = _client()
    asyncio.run(c.command_send_destination("VIN1", 48.137, 11.576, "Marienplatz"))
    url, body = _call(c)
    assert url.endswith("/api/v3/maps/navigation/destination")
    assert body["type"] == "LOCATION"
    assert body["vin"] == "VIN1"
    assert body["name"] == "Marienplatz"
    assert body["coordinates"] == {"latitude": 48.137, "longitude": 11.576}
    # id is a required non-null String → a client UUID
    uuid.UUID(body["id"])  # raises if not a valid UUID
    assert "address" not in body  # no address fields given → omitted


def test_address_subset_is_mapped_to_skoda_keys() -> None:
    c = _client()
    asyncio.run(c.command_send_destination(
        "VIN1", 48.1, 11.5, "Home",
        city="München", country="DE", street="Bahnhofstr", house_number="1",
        zip_code="80331",
    ))
    _, body = _call(c)
    assert body["address"] == {
        "city": "München", "country": "DE",
        "houseNumber": "1", "street": "Bahnhofstr", "zipCode": "80331",
    }


def test_state_is_ignored_skoda_has_no_state_field() -> None:
    # The shared service forwards `state` (SEAT/CUPRA), but Škoda's
    # MapPositionAddressDto has no state — it must not leak into the body.
    c = _client()
    asyncio.run(c.command_send_destination(
        "VIN1", 48.1, 11.5, "X", state="Bayern", city="M",
    ))
    _, body = _call(c)
    assert "state" not in body.get("address", {})
    assert body["address"] == {"city": "M"}
