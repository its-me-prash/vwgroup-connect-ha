"""v2.20.0 — APK-audit command route/payload corrections (byte-identical to the
current official apps). Every route + JSON field pinned here was verified against
the fresh Google-Play APK (Audi 5.6.0 / VW-EU 4.1.1 / myVW 2026.5.27 / Skoda
8.14.0 / SEAT+CUPRA 2.19.1). These are read-vs-write field traps and copied-enum
values that were silently rejected before.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

from custom_components.vag_connect.cariad.api.skoda import SkodaClient
from custom_components.vag_connect.cariad.api.seat_cupra import SeatCupraClient
from custom_components.vag_connect.cariad.api.vw_na import VWNAClient


def _url_body(client: object) -> tuple[str, dict]:
    a = client._post.call_args
    return a.args[0], a.kwargs.get("json")


# ── Skoda ───────────────────────────────────────────────────────────────


def test_skoda_flash_is_FLASH_not_FLASH_ONLY() -> None:
    c = SkodaClient(MagicMock(), "u@t.de", "pw")
    c._post = AsyncMock()  # type: ignore[method-assign]
    asyncio.run(c.command_flash("VIN1"))
    url, body = _url_body(c)
    assert url.endswith("/api/v1/vehicle-access/VIN1/honk-and-flash")
    assert body == {"mode": "FLASH"}  # not FLASH_ONLY (EU/Audi value)


def test_skoda_target_soc_field() -> None:
    c = SkodaClient(MagicMock(), "u@t.de", "pw")
    c._put = AsyncMock()  # type: ignore[method-assign]
    asyncio.run(c.command_set_target_soc("VIN1", 80))
    a = c._put.call_args  # v2.20.1 (#866): set-charge-limit is PUT, not POST
    url, body = a.args[0], a.kwargs.get("json")
    assert url.endswith("/charging/VIN1/set-charge-limit")
    assert body == {"targetSOCInPercent": 80}  # not targetStateOfChargeInPercent


# ── SEAT / CUPRA (OLA) ──────────────────────────────────────────────────


def _sc() -> SeatCupraClient:
    c = SeatCupraClient(MagicMock(), "cupra", "u@t.de", "pw")
    c._post = AsyncMock()  # type: ignore[method-assign]
    return c


def test_seatcupra_battery_care_enabled_field() -> None:
    c = _sc()
    asyncio.run(c.command_set_battery_care("VIN1", True))
    url, body = _url_body(c)
    assert url.endswith("/charging/battery-care")
    assert body == {"enabled": True}  # not batteryCareMode


def test_seatcupra_battery_care_target_field() -> None:
    c = _sc()
    asyncio.run(c.command_set_battery_care_target("VIN1", 80))
    _, body = _url_body(c)
    assert body == {"targetSocPercentage": 80}  # not targetSOC_pct


def test_seatcupra_target_soc_update_settings_route() -> None:
    c = _sc()
    asyncio.run(c.command_set_target_soc("VIN1", 70))
    url, body = _url_body(c)
    assert url.endswith("/charging/actions/update-settings")  # not bare /charging/actions
    assert body == {"targetSocPercentage": 70}


def test_seatcupra_climate_temp_settings_route_celsius() -> None:
    c = _sc()
    asyncio.run(c.command_set_climate_temperature("VIN1", 21.5))
    url, body = _url_body(c)
    assert url.endswith("/v2/vehicles/VIN1/climatisation/settings")
    assert body == {"targetTemperatureInCelsius": 21.5}  # not Kelvin targetTemperature_K


# ── VW-NA (con-veh.net) ─────────────────────────────────────────────────


def _vwna() -> VWNAClient:
    c = VWNAClient.__new__(VWNAClient)
    c._base = "https://b-h-s.spr.us00.p.con-veh.net"
    c._vin_to_uuid = {"VIN1": "uuid-1"}
    c._read_session_tokens = {}
    c._post = AsyncMock()  # type: ignore[method-assign]
    return c


def test_vwna_wake_uses_rvs_refresh() -> None:
    # v2.29.x — wake is now carnet-gated (sstur/vwapp): routed via _carnet_command
    # -> _request with the carnetVehicleToken as Bearer, not a plain _post.
    c = _vwna()
    c._get_read_session_token = AsyncMock(return_value="carnet")  # type: ignore[method-assign]
    c._request = AsyncMock(return_value={})  # type: ignore[method-assign]
    asyncio.run(c.command_wake("VIN1"))
    a = c._request.call_args
    assert a.args[0] == "POST"
    assert a.args[1].endswith("/rvs/v1/vehicle/uuid-1/refresh")  # not /ev/.../wakeup
    assert a.kwargs["headers"]["Authorization"] == "Bearer carnet"


def test_vwna_target_soc_percentage_field() -> None:
    # v2.29.x — set-charge-limit is a PUT that replaces the whole settings object;
    # with no readable current settings it PUTs the bare targetSOCPercentage.
    c = _vwna()
    c._get_read_session_token = AsyncMock(return_value="carnet")  # type: ignore[method-assign]
    c._read = AsyncMock(return_value={})  # type: ignore[method-assign]
    c._request = AsyncMock(return_value={})  # type: ignore[method-assign]
    asyncio.run(c.command_set_target_soc("VIN1", 90))
    a = c._request.call_args
    assert a.args[0] == "PUT"
    assert a.args[1].endswith("/ev/v1/vehicle/uuid-1/charging/settings")
    assert a.kwargs["json"] == {"targetSOCPercentage": 90}  # not targetSOC_pct


def test_vwna_flash_uses_honkflash_service() -> None:
    # v2.29.x (#659) — carnet-gated PUT with the APK-grounded body. The old
    # {"action": "FLASH_ONLY"} (an EU enum) drew a 405, then a 500 from
    # HonkAndFlashService once the verb was right. The real model is
    # HonkAndLights(horn=bool, lights=bool), mirroring lockunlock's {lock: bool}.
    c = _vwna()
    c._get_read_session_token = AsyncMock(return_value="carnet")  # type: ignore[method-assign]
    c._request = AsyncMock(return_value={})  # type: ignore[method-assign]
    asyncio.run(c.command_flash("VIN1"))
    a = c._request.call_args
    assert a.args[0] == "PUT"
    assert a.args[1].endswith("/honkflash/v1/vehicle/uuid-1")  # not /ev/.../horn-and-lights
    assert a.kwargs["json"] == {"horn": False, "lights": True}  # flash only
    assert a.kwargs["headers"]["Authorization"] == "Bearer carnet"


def test_vwna_flash_honk_flag_sets_horn() -> None:
    # the honk argument used to be ignored; it now drives the horn boolean
    c = _vwna()
    c._get_read_session_token = AsyncMock(return_value="carnet")  # type: ignore[method-assign]
    c._request = AsyncMock(return_value={})  # type: ignore[method-assign]
    asyncio.run(c.command_flash("VIN1", honk=True))
    assert c._request.call_args.kwargs["json"] == {"horn": True, "lights": True}
