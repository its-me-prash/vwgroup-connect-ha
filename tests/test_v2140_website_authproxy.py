# Copyright 2026 Prash Balan (@its-me-prash) - Apache License 2.0
# SPDX-License-Identifier: Apache-2.0
"""Tests for the v2.14.0 volkswagen.de website-authproxy connector (BETA).

This OPT-IN, read-only channel logs in through the volkswagen.de authproxy
(which lands on the same identity.vwgroup.io Auth0 the rest of the
integration handles) and reads vehicle data via the ``/app/authproxy/...``
reverse-proxy endpoints. The pieces pinned here are the ones verifiable
without a live VW account:

  1. The Auth0 form-field extraction reuse (``_login_fields`` from the EU
     Data Act connector) — the website authproxy lands on the SAME page.
  2. The charging + maintenance JSON → ``VehicleData`` mapping, against a
     synthetic payload built from the documented response field names.
  3. Cookie export / import round-trip (domain-filtered persistence).
  4. The async login / VIN-list / data-fetch orchestration with a mocked
     aiohttp session — NOT a live login.

The live login + reverse-proxy reads require the maintainer's VW account
and are validated post-release; they cannot be unit-tested here.
"""

from __future__ import annotations

from typing import Any

import pytest

from custom_components.vag_connect.cariad.auth._website_authproxy import (
    WebsiteAuthProxyConnector,
    map_charging_to_vehicle_data,
    map_maintenance_to_vehicle_data,
)
from custom_components.vag_connect.cariad.exceptions import AuthenticationError
from custom_components.vag_connect.cariad.models import VehicleData


# ── charging/status → VehicleData mapping ──────────────────────────────────

def test_charging_mapping_populates_ev_fields() -> None:
    """A synthetic charging/status body maps onto the EV VehicleData fields."""
    payload = {
        "data": {
            "batteryStatus": {
                "currentSOC_pct": 82,
                "cruisingRangeElectric_km": 305,
                "navigationTargetSOC_pct": 80,
                "temperatureHvBattery_K": 295.15,
            },
            "chargingStatus": {
                "chargingState": "charging",
                "chargePower_kW": 11.0,
                "chargeRate_kmph": 48.0,
                "remainingChargingTimeToComplete_min": 95,
                "chargeMode": "manual",
            },
            "plugStatus": {
                "plugConnectionState": "connected",
                "plugLockState": "locked",
                "externalPower": "available",
            },
        }
    }
    d = map_charging_to_vehicle_data(payload, VehicleData(vin="WVWZZZTEST0000001"))
    assert d.battery_soc == 82
    assert d.has_battery is True
    assert d.is_electric is True
    assert d.electric_range_km == 305
    assert d.range_km == 305
    assert d.target_soc == 80
    assert d.battery_temp_c == 22.0
    assert d.charging_state == "charging"
    assert d.is_charging is True
    assert d.charging_power_kw == 11.0
    assert d.charging_rate_kmh == 48.0
    assert d.remaining_charge_time_nav_min == 95
    assert d.charge_mode == "manual"
    assert d.plug_state == "connected"
    assert d.plug_connected is True
    assert d.connector_locked is True
    assert d.external_power is True


def test_charging_mapping_not_charging_when_disconnected() -> None:
    """A 'notConnected' plug + 'readyForCharging' state map to not-charging."""
    payload = {
        "data": {
            "batteryStatus": {"currentSOC_pct": 55},
            "chargingStatus": {"chargingState": "readyForCharging"},
            "plugStatus": {"plugConnectionState": "disconnected"},
        }
    }
    d = map_charging_to_vehicle_data(payload, VehicleData(vin="WVWZZZTEST0000002"))
    assert d.battery_soc == 55
    assert d.is_charging is False
    assert d.plug_connected is False


def test_charging_mapping_tolerates_missing_blocks() -> None:
    """A body with no data / wrong shape leaves the fields at defaults."""
    d = map_charging_to_vehicle_data({}, VehicleData(vin="WVWZZZTEST0000003"))
    assert d.battery_soc is None
    assert d.is_charging is None
    d2 = map_charging_to_vehicle_data(
        {"data": {"batteryStatus": "oops"}},
        VehicleData(vin="WVWZZZTEST0000004"),
    )
    assert d2.battery_soc is None


# ── maintenance/status → VehicleData mapping ───────────────────────────────

def test_maintenance_mapping_wrapped_value_shape() -> None:
    """The WeConnect {maintenanceStatus: {value: {...}}} envelope maps."""
    payload = {
        "data": {
            "maintenanceStatus": {
                "value": {
                    "mileage_km": 42150,
                    "inspectionDue_days": 230,
                    "inspectionDue_km": 18000,
                    "oilServiceDue_days": 110,
                    "oilServiceDue_km": 9000,
                }
            }
        }
    }
    d = map_maintenance_to_vehicle_data(payload, VehicleData(vin="WVWZZZTEST0000005"))
    assert d.odometer_km == 42150
    assert d.service_due_in_days == 230
    assert d.service_km == 18000
    assert d.oil_service_due_in_days == 110
    assert d.oil_service_km == 9000


def test_maintenance_mapping_flat_shape() -> None:
    """A flat {data: {...}} envelope (no maintenanceStatus wrapper) maps too."""
    payload = {"data": {"mileage_km": 12345, "inspectionDue_days": -5}}
    d = map_maintenance_to_vehicle_data(payload, VehicleData(vin="WVWZZZTEST0000006"))
    assert d.odometer_km == 12345
    # Negative "overdue" day counts are kept as-is (sensor renders them).
    assert d.service_due_in_days == -5


def test_maintenance_mapping_tolerates_empty() -> None:
    """An empty / malformed body leaves maintenance fields unset."""
    d = map_maintenance_to_vehicle_data({}, VehicleData(vin="WVWZZZTEST0000007"))
    assert d.odometer_km is None
    assert d.service_due_in_days is None


# ── cookie export / import round-trip ──────────────────────────────────────

class _FakeCookie(dict):
    """Minimal stand-in for an aiohttp Morsel-like cookie."""

    def __init__(self, key: str, value: str, domain: str) -> None:
        super().__init__()
        self.key = key
        self.value = value
        self["domain"] = domain
        self["path"] = "/"


class _FakeJarSession:
    """Session whose cookie_jar yields a fixed set of cookies."""

    def __init__(self, cookies: list[_FakeCookie]) -> None:
        self._cookies = cookies
        self.updated: list[tuple[str, Any]] = []

    @property
    def cookie_jar(self) -> "_FakeJarSession":
        return self

    def __iter__(self) -> Any:
        return iter(self._cookies)

    def update_cookies(self, cookies: dict[str, Any], response_url: Any = None) -> None:
        self.updated.append((next(iter(cookies)), response_url))


def test_export_cookies_filters_to_vw_domains() -> None:
    """export_cookies keeps only volkswagen.de / vwgroup.io cookies."""
    session = _FakeJarSession([
        _FakeCookie("sess", "abc", "www.volkswagen.de"),
        _FakeCookie("idp", "xyz", "identity.vwgroup.io"),
        _FakeCookie("other", "nope", "example.com"),
    ])
    conn = WebsiteAuthProxyConnector(session, "u@x.z", "pw")  # type: ignore[arg-type]
    out = conn.export_cookies()
    names = {c["name"] for c in out}
    assert names == {"sess", "idp"}
    assert "other" not in names


def test_import_cookies_round_trip() -> None:
    """import_cookies hydrates only the two relevant domains into the jar."""
    session = _FakeJarSession([])
    conn = WebsiteAuthProxyConnector(session, "u@x.z", "pw")  # type: ignore[arg-type]
    conn.import_cookies([
        {"name": "sess", "value": "abc", "domain": "www.volkswagen.de"},
        {"name": "junk", "value": "v", "domain": "example.com"},
    ])
    injected = {name for name, _url in session.updated}
    assert "sess" in injected
    assert "junk" not in injected


# ── async login / list / data orchestration (mocked session) ───────────────

_LOGIN_HTML = (
    '<html><body>'
    '<form action="/u/login?state=AUTH0STATE">'
    '<input type="hidden" name="state" value="AUTH0STATE">'
    '<input type="hidden" name="hmac" value="loginhmac">'
    '</form></body></html>'
)


class _FakeResp:
    def __init__(
        self, url: str, *, status: int = 200, text: str = "",
        json_data: Any = None,
    ) -> None:
        self.url = url
        self.status = status
        self._text = text
        self._json = json_data

    async def __aenter__(self) -> "_FakeResp":
        return self

    async def __aexit__(self, *_a: Any) -> bool:
        return False

    async def text(self, errors: str | None = None) -> str:
        return self._text

    async def json(self, content_type: Any = None) -> Any:
        return self._json


_CHARGING_JSON = {
    "data": {
        "batteryStatus": {"currentSOC_pct": 77, "cruisingRangeElectric_km": 250},
        "chargingStatus": {"chargingState": "charging", "chargePower_kW": 7.4},
        "plugStatus": {"plugConnectionState": "connected"},
    }
}
_MAINT_JSON = {"data": {"maintenanceStatus": {"value": {"mileage_km": 33333}}}}
_RELATIONS_TEXT = (
    '{"relations":[{"vin":"WVWZZZTESTVHN0001","role":"PRIMARY_USER"},'
    '{"vehicle":{"vin":"WVWZZZTESTVHN0002"}},{"vin":"TOOSHORT"}]}'
)


class _OkLoginSession:
    """Routes the authproxy login + data endpoints to canned responses."""

    def __init__(self) -> None:
        self.posts: list[dict[str, Any]] = []

    def get(self, url: str, **kw: Any) -> _FakeResp:
        if "/app/authproxy/login" in url:
            # Authproxy redirected us into Auth0 universal login.
            return _FakeResp(
                "https://identity.vwgroup.io/u/login?state=AUTH0STATE",
                text=_LOGIN_HTML,
            )
        if "relations" in url:
            return _FakeResp(url, text=_RELATIONS_TEXT)
        if "charging/status" in url:
            return _FakeResp(url, json_data=_CHARGING_JSON)
        if "maintenance/status" in url:
            return _FakeResp(url, json_data=_MAINT_JSON)
        raise AssertionError(f"unmatched GET {url}")

    def post(self, url: str, **kw: Any) -> _FakeResp:
        self.posts.append({"url": url, "data": kw.get("data")})
        # Credential POST lands back on the volkswagen.de host → logged in.
        return _FakeResp(
            "https://www.volkswagen.de/de/besitzer-und-nutzer/myvolkswagen.html",
            status=200, text="<html>welcome</html>",
        )


@pytest.mark.asyncio
async def test_begin_login_ok_lands_on_site() -> None:
    """begin_login() → 'ok' when the credential POST lands on volkswagen.de."""
    session = _OkLoginSession()
    conn = WebsiteAuthProxyConnector(session, "user@example.com", "secret")  # type: ignore[arg-type]
    result = await conn.begin_login()
    assert result == "ok"
    assert conn.logged_in is True
    # Credentials were carried in the POST body.
    cred = session.posts[-1]
    assert cred["data"]["password"] == "secret"
    assert cred["data"]["username"] == "user@example.com"
    assert cred["data"]["state"] == "AUTH0STATE"


@pytest.mark.asyncio
async def test_begin_login_otp_required() -> None:
    """begin_login() → 'otp_required' when Auth0 issues an email challenge."""
    class _OtpSession:
        def get(self, url: str, **kw: Any) -> _FakeResp:
            return _FakeResp(
                "https://identity.vwgroup.io/u/login?state=ST",
                text=_LOGIN_HTML,
            )

        def post(self, url: str, **kw: Any) -> _FakeResp:
            return _FakeResp(
                "https://identity.vwgroup.io/u/email-challenge?state=ST",
                status=200, text="<html>enter code</html>",
            )

    conn = WebsiteAuthProxyConnector(_OtpSession(), "u@x.z", "pw")  # type: ignore[arg-type]
    result = await conn.begin_login()
    assert result == "otp_required"
    assert conn.logged_in is False


@pytest.mark.asyncio
async def test_submit_otp_finishes_login() -> None:
    """submit_otp() posts the code and completes the login on success."""
    class _OtpThenOkSession:
        def __init__(self) -> None:
            self.otp_posts: list[Any] = []

        def get(self, url: str, **kw: Any) -> _FakeResp:
            return _FakeResp(
                "https://identity.vwgroup.io/u/login?state=ST",
                text=_LOGIN_HTML,
            )

        def post(self, url: str, **kw: Any) -> _FakeResp:
            if "email-challenge" in url:
                self.otp_posts.append(kw.get("data"))
                return _FakeResp(
                    "https://www.volkswagen.de/de/besitzer-und-nutzer/"
                    "myvolkswagen.html",
                    status=200, text="<html>welcome</html>",
                )
            # Initial credential POST → email challenge.
            return _FakeResp(
                "https://identity.vwgroup.io/u/email-challenge?state=ST",
                status=200, text="<html>enter code</html>",
            )

    session = _OtpThenOkSession()
    conn = WebsiteAuthProxyConnector(session, "u@x.z", "pw")  # type: ignore[arg-type]
    assert await conn.begin_login() == "otp_required"
    ok = await conn.submit_otp("123456")
    assert ok is True
    assert conn.logged_in is True
    assert session.otp_posts[-1]["code"] == "123456"


@pytest.mark.asyncio
async def test_list_vehicle_vins_scans_relations() -> None:
    """list_vehicle_vins() extracts 17-char VINs from the relations body."""
    session = _OkLoginSession()
    conn = WebsiteAuthProxyConnector(session, "u@x.z", "pw")  # type: ignore[arg-type]
    vins = await conn.list_vehicle_vins()
    assert vins == ["WVWZZZTESTVHN0001", "WVWZZZTESTVHN0002"]


@pytest.mark.asyncio
async def test_get_vehicle_data_merges_charging_and_maintenance() -> None:
    """get_vehicle_data() fetches both endpoints and maps onto VehicleData."""
    session = _OkLoginSession()
    conn = WebsiteAuthProxyConnector(session, "u@x.z", "pw")  # type: ignore[arg-type]
    d = await conn.get_vehicle_data("WVWZZZTESTVHN0001")
    assert d.battery_soc == 77
    assert d.electric_range_km == 250
    assert d.charging_power_kw == 7.4
    assert d.odometer_km == 33333
    assert d.connection_state == "online"


@pytest.mark.asyncio
async def test_get_vehicle_data_401_raises() -> None:
    """A genuine 401 on a data endpoint propagates (session expired)."""
    class _401Session:
        def get(self, url: str, **kw: Any) -> _FakeResp:
            if "charging/status" in url:
                return _FakeResp(url, status=401)
            raise AssertionError(f"should not reach {url} after 401")

    conn = WebsiteAuthProxyConnector(_401Session(), "u@x.z", "pw")  # type: ignore[arg-type]
    with pytest.raises(AuthenticationError):
        await conn.get_vehicle_data("WVWZZZTESTVHN0001")


@pytest.mark.asyncio
async def test_get_vehicle_data_soft_404_is_graceful() -> None:
    """A non-fatal 4xx on a data endpoint yields a bare VehicleData, no raise.

    Both reads are soft: the maintenance 404 here is swallowed so a missing /
    not-yet-available block just means 'no maintenance this poll' rather than
    a dead session. (404 is non-retriable, so this returns immediately — the
    retriable-5xx backoff path is exercised by the EU Data Act connector
    tests that share the same backoff shape.)
    """
    class _Maint404Session:
        def get(self, url: str, **kw: Any) -> _FakeResp:
            if "charging/status" in url:
                return _FakeResp(url, json_data=_CHARGING_JSON)
            if "maintenance/status" in url:
                return _FakeResp(url, status=404)
            raise AssertionError(f"unmatched GET {url}")

    conn = WebsiteAuthProxyConnector(_Maint404Session(), "u@x.z", "pw")  # type: ignore[arg-type]
    d = await conn.get_vehicle_data("WVWZZZTESTVHN0001")
    # Charging still mapped; maintenance softly skipped.
    assert d.battery_soc == 77
    assert d.odometer_km is None
    assert d.connection_state == "online"
