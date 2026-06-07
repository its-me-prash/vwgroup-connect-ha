# Copyright 2026 Prash Balan (@its-me-prash) - Apache License 2.0
# SPDX-License-Identifier: Apache-2.0
"""Tests for the v2.12.0 EU Data Act portal connector.

The connector is the only working third-party auth path for VW passenger
cars after VW closed every token-based WeConnect route (verified live
2026-06-07: hybrid 403, code-exchange needs client_secret, device-grant
403). These tests pin the two parts we CAN verify without live portal
credentials:

  1. The login form-field extraction (``_login_fields``) — merges HTML
     hidden inputs with the JS ``templateModel`` (hmac / relayState /
     email) and the ``csrf_token`` regex. This is where v2.11.4's flow
     broke (it only looked for ``"_csrf":`` and missed ``csrf_token:``).
  2. The dataset → ``VehicleData`` curated mapping — given a synthetic
     EU Data Act dataset, the high-value fields (SoC, odometer, range,
     charging state, doors) must populate correctly.

The live login + ZIP download path is validated post-release against a
real VW EU account (issue #388/#393) — it cannot be unit-tested here.
"""

from __future__ import annotations

import io
import zipfile
from typing import Any

import pytest

from custom_components.vag_connect.cariad.auth._eu_data_act import (
    EUDataActConnector,
    _extract_template_model,
    _login_fields,
    _resolve_action,
    _walk_fields,
    map_dataset_to_vehicle_data,
)
from custom_components.vag_connect.cariad.models import VehicleData


# ── login form-field extraction ────────────────────────────────────────────

def test_template_model_extraction_brace_matched() -> None:
    """templateModel JSON is extracted via brace-matching, nested ok."""
    html = (
        '<script>window._IDK = {templateModel: '
        '{"hmac":"abc123","relayState":"rs789",'
        '"emailPasswordForm":{"email":"x@y.z"},'
        '"error":null}, csrf_token: "csrf456"};</script>'
    )
    model = _extract_template_model(html)
    assert model["hmac"] == "abc123"
    assert model["relayState"] == "rs789"
    assert model["emailPasswordForm"]["email"] == "x@y.z"


def test_login_fields_merges_template_model_and_csrf() -> None:
    """The v2.11.4-breaking case: SPA page with NO hidden inputs, all
    state in templateModel + csrf_token JS. Must still yield hmac+_csrf."""
    html = (
        '<html><body><div id="app"></div>'
        '<script>window._IDK = {templateModel: '
        '{"hmac":"deadbeef","relayState":"rs001",'
        '"postAction":"/signin-service/v1/CLIENT/login/authenticate"}, '
        'csrf_token: "csrftok99"};</script></body></html>'
    )
    fields, _action = _login_fields(html)
    assert fields["hmac"] == "deadbeef"
    assert fields["relayState"] == "rs001"
    assert fields["_csrf"] == "csrftok99"


def test_login_fields_reads_html_hidden_inputs() -> None:
    """Classic server-rendered form: fields come from hidden inputs."""
    html = (
        '<form action="/signin-service/v1/CLIENT/login/identifier">'
        '<input type="hidden" name="hmac" value="hexhmac">'
        '<input type="hidden" name="_csrf" value="csrfval">'
        '<input type="hidden" name="relayState" value="rs">'
        '<input type="email" name="email">'
        '</form>'
    )
    fields, action = _login_fields(html)
    assert fields["hmac"] == "hexhmac"
    assert fields["_csrf"] == "csrfval"
    assert action == "/signin-service/v1/CLIENT/login/identifier"


# ── action-URL resolution (the /login/login/ doubling guard) ───────────────

def test_resolve_action_collapses_doubled_login() -> None:
    """Relative 'login/authenticate' must not produce /login/login/.

    swebachus's v2.11.4 source review (#388): a relative postAction that
    already starts with 'login/' joined to a '.../login/identifier' base
    yielded '.../login/login/authenticate' → HTTP 400. The resolver must
    collapse it.
    """
    base = (
        "https://identity.vwgroup.io/signin-service/v1/"
        "CLIENT@apps_vw-dilab_com/login/identifier"
    )
    assert _resolve_action(base, "login/authenticate") == (
        "https://identity.vwgroup.io/signin-service/v1/"
        "CLIENT@apps_vw-dilab_com/login/authenticate"
    )


def test_resolve_action_strips_query_when_no_action() -> None:
    """No action → post to the landed URL with its query stripped."""
    url = (
        "https://identity.vwgroup.io/signin-service/v1/CLIENT/login/"
        "authenticate?relayState=abc123"
    )
    assert _resolve_action(url, None) == (
        "https://identity.vwgroup.io/signin-service/v1/CLIENT/login/authenticate"
    )


def test_resolve_action_absolute_and_plain_relative() -> None:
    """Absolute action replaces the path; plain relative joins cleanly."""
    base = "https://identity.vwgroup.io/signin-service/v1/CLIENT/login/identifier"
    # absolute (leading slash) — used as-is
    assert _resolve_action(base, "/signin-service/v1/CLIENT/login/authenticate") == (
        "https://identity.vwgroup.io/signin-service/v1/CLIENT/login/authenticate"
    )
    # plain relative without the login/ prefix — joins to .../login/authenticate
    assert _resolve_action(base, "authenticate") == (
        "https://identity.vwgroup.io/signin-service/v1/CLIENT/login/authenticate"
    )


# ── dataset → VehicleData mapping ───────────────────────────────────────────

def test_walk_fields_flattens_datapoint_shape() -> None:
    """Data-point shape {dataFieldName, value} is flattened to {name: value}."""
    payload = {
        "data": [
            {"dataFieldName": "battery_state_report.soc", "value": "82"},
            {"dataFieldName": "mileage.value", "value": "18842"},
        ]
    }
    fields = _walk_fields(payload)
    assert fields["battery_state_report.soc"] == "82"
    assert fields["mileage.value"] == "18842"


def test_curated_mapping_populates_high_value_fields() -> None:
    """A synthetic dataset maps onto the curated VehicleData fields."""
    fields = {
        "battery_state_report.soc": "82",
        "mileage.value": "18842",
        "range": "54",
        "battery_state_report.charge_power": "7.4",
        "settings.target_soc": "80",
        "charging_state_report.current_charge_state": "charging",
        "charging_state_report.charge_mode": "manual",
        "min_temperature": "18.5",
        "max_temperature": "21.0",
        "locked": "true",
        "window_heating_state": "on",
    }
    d = map_dataset_to_vehicle_data(fields, VehicleData(vin="TESTVIN0000000001"))
    assert d.battery_soc == 82
    assert d.has_battery is True
    assert d.odometer_km == 18842
    assert d.range_km == 54
    assert d.electric_range_km == 54
    assert d.charging_power_kw == 7.4
    assert d.target_soc == 80
    assert d.charging_state == "charging"
    assert d.is_charging is True
    assert d.charge_mode == "manual"
    assert d.hv_battery_min_temperature_c == 18.5
    assert d.hv_battery_max_temperature_c == 21.0
    assert d.doors_locked is True
    assert d.window_heating_front is True
    assert d.window_heating_back is True


def test_curated_mapping_flat_egolf_variant() -> None:
    """Flat eGolf payload (bare field names, no report prefix) also maps."""
    fields = {
        "state_of_charge": "60",
        "mileage": "99000",
        "cruising_range_primary_engine": "120",
    }
    d = map_dataset_to_vehicle_data(fields, VehicleData(vin="TESTVIN0000000002"))
    assert d.battery_soc == 60
    assert d.odometer_km == 99000
    assert d.range_km == 120


def test_curated_mapping_tolerates_missing_fields() -> None:
    """An empty / partial dataset leaves fields at their defaults."""
    d = map_dataset_to_vehicle_data({}, VehicleData(vin="TESTVIN0000000003"))
    assert d.battery_soc is None
    assert d.odometer_km is None
    assert d.doors_locked is None


# ── async orchestration (mocked aiohttp session) ───────────────────────────

_SIGNIN_HTML = (
    '<form action="/signin-service/v1/CLIENT/login/identifier">'
    '<input type="hidden" name="hmac" value="email_hmac">'
    '<input type="hidden" name="_csrf" value="csrf1">'
    '<input type="hidden" name="relayState" value="rs1">'
    '</form>'
)
# Password page: SPA-rendered, fields in templateModel + a FRESH hmac.
_PASSWORD_HTML = (
    '<script>window._IDK = {templateModel: '
    '{"hmac":"fresh_pw_hmac","relayState":"rs1",'
    '"postAction":"/signin-service/v1/CLIENT/login/authenticate"}, '
    'csrf_token: "csrf2"};</script>'
)


def _build_dataset_zip() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(
            "export.json",
            '{"data":['
            '{"dataFieldName":"battery_state_report.soc","value":"77"},'
            '{"dataFieldName":"mileage.value","value":"12345"},'
            '{"dataFieldName":"range","value":"48"}]}',
        )
    return buf.getvalue()


class _FakeResp:
    def __init__(
        self, url: str, *, status: int = 200, text: str = "",
        json_data: Any = None, body: bytes = b"",
    ) -> None:
        self.url = url
        self.status = status
        self._text = text
        self._json = json_data
        self._body = body

    async def __aenter__(self) -> "_FakeResp":
        return self

    async def __aexit__(self, *_a: Any) -> bool:
        return False

    async def text(self, errors: str | None = None) -> str:
        return self._text

    async def json(self, content_type: Any = None) -> Any:
        return self._json

    async def read(self) -> bytes:
        return self._body


class _FakeSession:
    """Routes login + data-fetch URLs to canned responses."""

    def __init__(self) -> None:
        self.posts: list[dict[str, Any]] = []

    def get(self, url: str, **kw: Any) -> _FakeResp:
        if url.endswith("/") and "drivesomethinggreater" in url:
            return _FakeResp(url, text="<html>portal</html>")
        if "authorize" in url:
            return _FakeResp(
                "https://identity.vwgroup.io/signin-service/v1/CLIENT/login/identifier",
                text=_SIGNIN_HTML,
            )
        if "metadata" in url:
            return _FakeResp(url, json_data={"identifier": "ID123"})
        if url.endswith("/list"):
            return _FakeResp(url, json_data=[{"name": "data_2026.zip"}])
        if url.endswith("/download"):
            return _FakeResp(url, body=_build_dataset_zip())
        raise AssertionError(f"unmatched GET {url}")

    def post(self, url: str, **kw: Any) -> _FakeResp:
        self.posts.append({"url": url, "data": kw.get("data")})
        if url.endswith("/login/identifier"):
            # Lands on the password page; URL carries ?relayState=.
            return _FakeResp(
                "https://identity.vwgroup.io/signin-service/v1/CLIENT/login/"
                "authenticate?relayState=rs1",
                text=_PASSWORD_HTML,
            )
        if "/login/authenticate" in url:
            # Successful credential POST lands back on the portal host.
            return _FakeResp(
                "https://eu-data-act.drivesomethinggreater.com/dashboard",
                status=200, text="<html>welcome</html>",
            )
        raise AssertionError(f"unmatched POST {url}")


# ── per-brand portal config ────────────────────────────────────────────────

def test_brand_config_resolution() -> None:
    """Connector picks the right client_id + state per brand.

    The portal connector is a fallback in every brand's auth chain, so a
    non-VW brand falling through must use its own client/state — not VW's.
    """
    vw = EUDataActConnector(object())  # type: ignore[arg-type]
    assert vw._client_id.startswith("9b58543e")
    assert vw._state == "de__de__VOLKSWAGEN_PASSENGER_CARS"

    cupra = EUDataActConnector(object(), brand="cupra")  # type: ignore[arg-type]
    assert cupra._client_id.startswith("f85e5b69")
    assert cupra._scope == "openid profile cars"
    assert cupra._state == "de__de__CUPRA"

    seat = EUDataActConnector(object(), brand="seat")  # type: ignore[arg-type]
    assert seat._client_id.startswith("f85e5b69")
    assert seat._state == "de__de__SEAT"

    # Unknown brand → VW client with a derived state suffix (graceful).
    porsche = EUDataActConnector(object(), brand="porsche")  # type: ignore[arg-type]
    assert porsche._client_id.startswith("9b58543e")
    assert porsche._state == "de__de__PORSCHE"

    # Locale override flows into the state.
    se = EUDataActConnector(object(), country="se", language="sv")  # type: ignore[arg-type]
    assert se._state == "se__sv__VOLKSWAGEN_PASSENGER_CARS"


@pytest.mark.asyncio
async def test_login_full_flow_mocked() -> None:
    """login() drives prime → authorize → identifier → credential POST."""
    session = _FakeSession()
    conn = EUDataActConnector(session)  # type: ignore[arg-type]
    await conn.login("user@example.com", "secret")
    assert conn.logged_in is True
    # The credential POST must use the FRESH password-page hmac, carry the
    # password, and target the clean /authenticate URL (no ?relayState=).
    cred_post = session.posts[-1]
    assert cred_post["url"].endswith("/login/authenticate")
    assert "?" not in cred_post["url"]
    assert cred_post["data"]["hmac"] == "fresh_pw_hmac"
    assert cred_post["data"]["password"] == "secret"


@pytest.mark.asyncio
async def test_list_vehicle_vins_mocked() -> None:
    """list_vehicle_vins() walks the consent payload for 17-char VINs.

    Covers the get_vehicles wiring gap surfaced on #388: VW EU portal
    mode must enumerate VINs through the portal, not the dead BFF.
    """
    class _VehSession:
        def get(self, url: str, **kw: Any) -> _FakeResp:
            assert "consent/me/vehicles" in url
            return _FakeResp(url, json_data={
                "vehicles": [
                    {"vin": "WVWZZZTESTVIN0001", "vehicleNickname": "ID.7"},
                    {"vehicleIdentificationNumber": "WVWZZZTESTVIN0002"},
                    {"vin": "TOOSHORT"},  # ignored — not 17 chars
                ]
            })

    conn = EUDataActConnector(_VehSession())  # type: ignore[arg-type]
    vins = await conn.list_vehicle_vins()
    assert vins == ["WVWZZZTESTVIN0001", "WVWZZZTESTVIN0002"]


@pytest.mark.asyncio
async def test_get_vehicle_data_mocked() -> None:
    """get_vehicle_data() walks metadata → list → ZIP → curated mapping."""
    session = _FakeSession()
    conn = EUDataActConnector(session)  # type: ignore[arg-type]
    d = await conn.get_vehicle_data("WVWZZZTESTVIN0001")
    assert d.battery_soc == 77
    assert d.odometer_km == 12345
    assert d.range_km == 48
    assert d.connection_state == "online"
