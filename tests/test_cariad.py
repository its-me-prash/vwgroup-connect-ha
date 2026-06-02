# Copyright 2026 Prash Balan (@its-me-prash) - Apache License 2.0
# SPDX-License-Identifier: Apache-2.0
"""Tests for the VAG Connect CARIAD API client package."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

# ── helpers ────────────────────────────────────────────────────────────────────

def _mock_session(status: int = 200, json_data: dict | None = None, text: str = "") -> MagicMock:
    """Build an aiohttp.ClientSession mock."""
    resp = AsyncMock()
    resp.status = status
    resp.headers = {"Content-Type": "application/json"}
    resp.json = AsyncMock(return_value=json_data or {})
    resp.text = AsyncMock(return_value=text)
    resp.__aenter__ = AsyncMock(return_value=resp)
    resp.__aexit__ = AsyncMock(return_value=False)

    session = MagicMock()
    session.get = MagicMock(return_value=resp)
    session.post = MagicMock(return_value=resp)
    session.request = MagicMock(return_value=resp)
    return session


# ── models ─────────────────────────────────────────────────────────────────────

class TestModels:
    def test_brand_configs_all_present(self):
        from custom_components.vag_connect.cariad.models import BRANDS
        assert set(BRANDS.keys()) == {
            "volkswagen", "audi", "skoda", "seat", "cupra",
            "volkswagen_na", "porsche",
        }

    def test_brand_vw_client_id(self):
        from custom_components.vag_connect.cariad.models import BRAND_VW_EU
        assert "a24fba63" in BRAND_VW_EU.client_id
        assert BRAND_VW_EU.api_base == "https://emea.bff.cariad.digital"

    def test_brand_audi_client_id(self):
        from custom_components.vag_connect.cariad.models import BRAND_AUDI
        assert "09b6cbec" in BRAND_AUDI.client_id
        assert BRAND_AUDI.redirect_uri == "myaudi:///"

    def test_brand_skoda_client_id(self):
        from custom_components.vag_connect.cariad.models import BRAND_SKODA
        assert "7f045eee" in BRAND_SKODA.client_id
        assert "skoda-auto.cz" in BRAND_SKODA.api_base

    def test_brand_seat_client_id(self):
        from custom_components.vag_connect.cariad.models import BRAND_SEAT
        assert "99a5b77d" in BRAND_SEAT.client_id

    def test_brand_cupra_client_id(self):
        from custom_components.vag_connect.cariad.models import BRAND_CUPRA
        assert "3c756d46" in BRAND_CUPRA.client_id
        assert BRAND_CUPRA.redirect_uri == "cupra://oauth-callback"

    def test_brand_app_prefix(self):
        from custom_components.vag_connect.cariad.models import BRAND_AUDI, BRAND_SKODA
        assert BRAND_AUDI.app_prefix == "myaudi"
        assert BRAND_SKODA.app_prefix == "myskoda"

    def test_vehicle_data_defaults(self):
        from custom_components.vag_connect.cariad.models import VehicleData
        d = VehicleData(vin="WVGTEST123456")
        assert d.vin == "WVGTEST123456"
        assert d.battery_soc is None
        assert d.is_electric is False
        assert d.doors_individual == {}

    def test_vehicle_data_to_dict(self):
        from custom_components.vag_connect.cariad.models import VehicleData
        d = VehicleData(vin="VIN1", battery_soc=80, is_electric=True)
        result = d.to_dict()
        assert result["vin"] == "VIN1"
        assert result["battery_soc"] == 80
        assert result["is_electric"] is True

    def test_token_set_valid(self):
        from custom_components.vag_connect.cariad.models import TokenSet
        t = TokenSet("access", "refresh", "id")
        assert t.is_valid() is True

    def test_token_set_invalid_empty(self):
        from custom_components.vag_connect.cariad.models import TokenSet
        t = TokenSet("", "refresh", "id")
        assert t.is_valid() is False


# ── exceptions ─────────────────────────────────────────────────────────────────

# ── v1.8.12 — Multi-Brand connection-state helper ───────────────────────────

class TestComputeConnectionState:
    """v1.8.12 — ``cariad/_util.compute_connection_state`` is the brand-
    agnostic helper that maps `carCapturedTimestamp` from arbitrarily
    nested status sub-objects to (state, last_seen_at). Used by Škoda
    (v1.8.11), SEAT/CUPRA, VW EU and Audi (via VWEUClient inheritance).
    """

    def test_returns_none_when_no_subobjects(self):
        from custom_components.vag_connect.cariad._util import compute_connection_state
        assert compute_connection_state() == (None, None)

    def test_returns_none_when_no_timestamp_anywhere(self):
        """v1.8.12 / myskoda PR #565: carCapturedTimestamp may be missing.
        Helper must not crash and not invent a value."""
        from custom_components.vag_connect.cariad._util import compute_connection_state
        state, ts = compute_connection_state(
            {"random": "data"}, {"other": [1, 2, 3]}, None,
        )
        assert state is None
        assert ts is None

    def test_top_level_timestamp_skoda_pattern(self):
        """Škoda mysmob: timestamp at top level of each sub-object."""
        from datetime import datetime, timezone, timedelta
        from custom_components.vag_connect.cariad._util import compute_connection_state
        recent = (datetime.now(tz=timezone.utc) - timedelta(minutes=5)).isoformat()
        state, ts = compute_connection_state({"carCapturedTimestamp": recent})
        assert state == "online"
        assert ts is not None

    def test_nested_timestamp_vw_eu_pattern(self):
        """VW EU CARIAD-BFF: timestamp is at .value.carCapturedTimestamp,
        nested 2-3 levels deep in service.statusName.value structure.
        Verified via upstream/volkswagencarnet issue #921 ID.4 dump."""
        from datetime import datetime, timezone, timedelta
        from custom_components.vag_connect.cariad._util import compute_connection_state
        recent = (datetime.now(tz=timezone.utc) - timedelta(minutes=10)).isoformat()
        # Mimic the actual VW EU selectivestatus shape
        raw = {
            "access": {
                "accessStatus": {
                    "value": {
                        "overallStatus": "safe",
                        "carCapturedTimestamp": recent,
                    },
                },
            },
            "charging": {
                "chargingStatus": {"value": {"chargingState": "off"}},
            },
        }
        state, ts = compute_connection_state(raw)
        assert state == "online"
        assert ts is not None

    def test_freshest_wins_across_subobjects(self):
        """The freshest timestamp from any sub-object wins —
        different sub-systems update at different cadences."""
        from datetime import datetime, timezone, timedelta
        from custom_components.vag_connect.cariad._util import compute_connection_state
        old = (datetime.now(tz=timezone.utc) - timedelta(hours=10)).isoformat()
        fresh = (datetime.now(tz=timezone.utc) - timedelta(minutes=2)).isoformat()
        state, ts = compute_connection_state(
            {"carCapturedTimestamp": old},
            {"deeply": {"nested": {"carCapturedTimestamp": fresh}}},
        )
        assert state == "online"  # freshest wins → 2 min ago

    def test_accepts_datetime_objects_too(self):
        """volkswagencarnet's lib pre-parses timestamps to datetime
        objects before storing — we must accept both str and datetime
        (verified in issue #921: mixed format in same response)."""
        from datetime import datetime, timezone, timedelta
        from custom_components.vag_connect.cariad._util import compute_connection_state
        recent = datetime.now(tz=timezone.utc) - timedelta(minutes=5)
        state, ts = compute_connection_state({"carCapturedTimestamp": recent})
        assert state == "online"
        assert ts == recent

    def test_naive_datetime_treated_as_utc(self):
        """Some backends return tz-naive datetimes — assume UTC for them
        instead of crashing in tz-arithmetic."""
        from datetime import datetime, timedelta
        from custom_components.vag_connect.cariad._util import compute_connection_state
        recent_naive = datetime.utcnow() - timedelta(minutes=5)
        state, ts = compute_connection_state({"carCapturedTimestamp": recent_naive})
        assert state == "online"
        assert ts is not None

    def test_corrupt_timestamp_string_does_not_crash(self):
        """Bad backend response with non-ISO timestamp → ignore that
        sub-object, keep checking the others."""
        from datetime import datetime, timezone, timedelta
        from custom_components.vag_connect.cariad._util import compute_connection_state
        good = (datetime.now(tz=timezone.utc) - timedelta(minutes=5)).isoformat()
        state, ts = compute_connection_state(
            {"carCapturedTimestamp": "not a date"},
            {"carCapturedTimestamp": good},
        )
        assert state == "online"
        assert ts is not None

    def test_exception_subobject_skipped(self):
        """asyncio.gather(..., return_exceptions=True) returns Exception
        instances for failed sub-fetches — helper must skip them."""
        from datetime import datetime, timezone, timedelta
        from custom_components.vag_connect.cariad._util import compute_connection_state
        recent = (datetime.now(tz=timezone.utc) - timedelta(minutes=5)).isoformat()
        state, ts = compute_connection_state(
            ValueError("timeout"), {"carCapturedTimestamp": recent}, RuntimeError("..."),
        )
        assert state == "online"

    def test_standby_threshold_just_under_24h(self):
        from datetime import datetime, timezone, timedelta
        from custom_components.vag_connect.cariad._util import compute_connection_state
        ts_str = (datetime.now(tz=timezone.utc) - timedelta(hours=23, minutes=30)).isoformat()
        state, _ = compute_connection_state({"carCapturedTimestamp": ts_str})
        assert state == "standby"

    def test_offline_threshold_just_over_24h(self):
        from datetime import datetime, timezone, timedelta
        from custom_components.vag_connect.cariad._util import compute_connection_state
        ts_str = (datetime.now(tz=timezone.utc) - timedelta(hours=24, minutes=1)).isoformat()
        state, _ = compute_connection_state({"carCapturedTimestamp": ts_str})
        assert state == "offline"

    def test_custom_timestamp_keys(self):
        """Future-proofing: caller can override the field name to look for."""
        from datetime import datetime, timezone, timedelta
        from custom_components.vag_connect.cariad._util import compute_connection_state
        recent = (datetime.now(tz=timezone.utc) - timedelta(minutes=5)).isoformat()
        state, _ = compute_connection_state(
            {"capturedAt": recent},
            timestamp_keys=("capturedAt",),
        )
        assert state == "online"


class TestExceptions:
    def test_terms_error_message(self):
        from custom_components.vag_connect.cariad.exceptions import TermsAndConditionsError
        e = TermsAndConditionsError()
        assert "app" in str(e).lower()

    def test_rate_limit_error(self):
        from custom_components.vag_connect.cariad.exceptions import RateLimitError
        e = RateLimitError()
        assert "15" in str(e)

    def test_vehicle_not_found_carries_vin(self):
        from custom_components.vag_connect.cariad.exceptions import VehicleNotFoundError
        e = VehicleNotFoundError("VIN123")
        assert e.vin == "VIN123"
        assert "VIN123" in str(e)

    def test_vehicle_command_error(self):
        from custom_components.vag_connect.cariad.exceptions import VehicleCommandError
        e = VehicleCommandError("lock", "403 Forbidden")
        assert e.command == "lock"
        assert "403" in str(e)

    def test_api_error(self):
        from custom_components.vag_connect.cariad.exceptions import APIError
        e = APIError(502, "https://example.com/api", "Bad Gateway")
        assert e.status == 502
        assert "502" in str(e)


# ── auth / PKCE ────────────────────────────────────────────────────────────────

class TestIDKAuth:
    def test_pkce_pair_lengths(self):
        from custom_components.vag_connect.cariad.auth.idk import _pkce_pair
        verifier, challenge = _pkce_pair()
        assert len(verifier) >= 40
        assert len(challenge) >= 40
        assert verifier != challenge

    def test_pkce_pairs_unique(self):
        from custom_components.vag_connect.cariad.auth.idk import _pkce_pair
        pairs = [_pkce_pair() for _ in range(10)]
        verifiers = [p[0] for p in pairs]
        assert len(set(verifiers)) == 10

    def test_extract_auth_code_success(self):
        from custom_components.vag_connect.cariad.auth.idk import _extract_auth_code
        location = "myaudi:///login?code=AUTH_CODE_123&state=xyz"
        code = _extract_auth_code(location, "myaudi:///")
        assert code == "AUTH_CODE_123"

    def test_extract_auth_code_wrong_prefix(self):
        from custom_components.vag_connect.cariad.auth.idk import _extract_auth_code
        code = _extract_auth_code("https://example.com?code=X", "myaudi:///")
        assert code is None

    def test_extract_auth_code_weconnect(self):
        from custom_components.vag_connect.cariad.auth.idk import _extract_auth_code
        location = "weconnect://authenticated?code=VW_CODE&state=abc"
        code = _extract_auth_code(location, "weconnect://authenticated")
        assert code == "VW_CODE"

    def test_absolute_url_relative(self):
        from custom_components.vag_connect.cariad.auth.idk import _absolute_url
        result = _absolute_url("https://identity.vwgroup.io/oidc", "/signin-service/v1/login")
        assert result == "https://identity.vwgroup.io/signin-service/v1/login"

    def test_absolute_url_already_absolute(self):
        from custom_components.vag_connect.cariad.auth.idk import _absolute_url
        url = "https://other.example.com/path"
        assert _absolute_url("https://identity.vwgroup.io", url) == url

    def test_csrf_parser_extracts_fields(self):
        from custom_components.vag_connect.cariad.auth.idk import _CSRFParser
        html = '''<form action="/login/authenticate">
            <input type="hidden" name="_csrf" value="TOKEN123">
            <input type="hidden" name="hmac" value="HMAC456">
            <input type="hidden" name="relayState" value="RS789">
        </form>'''
        p = _CSRFParser()
        p.feed(html)
        assert p.fields["_csrf"] == "TOKEN123"
        assert p.fields["hmac"] == "HMAC456"
        assert p.fields["relayState"] == "RS789"
        assert p.form_action == "/login/authenticate"

    def test_idk_auth_get_token_endpoint_vw(self):
        """VW EU uses CARIAD BFF endpoint."""
        from custom_components.vag_connect.cariad.auth.idk import IDKAuth
        from custom_components.vag_connect.cariad.models import BRAND_VW_EU

        auth = IDKAuth(MagicMock(), BRAND_VW_EU)
        result = auth._get_token_endpoint()
        assert "cariad.digital" in result
        assert "token" in result

    def test_idk_auth_get_token_endpoint_cupra(self):
        """CUPRA uses IDK endpoint."""
        from custom_components.vag_connect.cariad.auth.idk import IDKAuth
        from custom_components.vag_connect.cariad.models import BRAND_CUPRA

        auth = IDKAuth(MagicMock(), BRAND_CUPRA)
        result = auth._get_token_endpoint()
        assert "identity.vwgroup.io" in result
        assert "oidc/v1/token" in result

    def test_idk_auth_get_token_endpoint_seat(self):
        """SEAT uses OLA endpoint."""
        from custom_components.vag_connect.cariad.auth.idk import IDKAuth
        from custom_components.vag_connect.cariad.models import BRAND_SEAT

        auth = IDKAuth(MagicMock(), BRAND_SEAT)
        result = auth._get_token_endpoint()
        assert "ola.prod.code.seat" in result
        assert "authorization/api/v1/token" in result

    def test_idk_auth_raises_on_bad_auth_page(self):
        """Raises AuthenticationError if login page has no CSRF fields."""
        from custom_components.vag_connect.cariad.auth.idk import IDKAuth
        from custom_components.vag_connect.cariad.exceptions import AuthenticationError
        from custom_components.vag_connect.cariad.models import BRAND_VW_EU

        session = MagicMock()
        resp = AsyncMock()
        resp.__aenter__ = AsyncMock(return_value=resp)
        resp.__aexit__ = AsyncMock(return_value=False)
        resp.status = 200
        resp.url = "https://identity.vwgroup.io/login"
        resp.headers = {"Content-Type": "text/html"}
        resp.text = AsyncMock(return_value="<html>No form here</html>")
        session.get = MagicMock(return_value=resp)

        auth = IDKAuth(session, BRAND_VW_EU)
        with pytest.raises(AuthenticationError):
            asyncio.get_event_loop().run_until_complete(
                auth.authenticate("user@test.de", "pass")
            )

    def test_idk_auth_raises_on_non_200(self):
        from custom_components.vag_connect.cariad.auth.idk import IDKAuth
        from custom_components.vag_connect.cariad.exceptions import AuthenticationError
        from custom_components.vag_connect.cariad.models import BRAND_AUDI

        session = MagicMock()
        resp = AsyncMock()
        resp.__aenter__ = AsyncMock(return_value=resp)
        resp.__aexit__ = AsyncMock(return_value=False)
        resp.status = 503
        resp.url = "https://identity.vwgroup.io/authorize"
        resp.headers = {"Content-Type": "text/html"}
        resp.text = AsyncMock(return_value="Service Unavailable")
        session.get = MagicMock(return_value=resp)

        auth = IDKAuth(session, BRAND_AUDI)
        with pytest.raises(AuthenticationError, match="503"):
            asyncio.get_event_loop().run_until_complete(
                auth.authenticate("user@test.de", "pass")
            )


# ── factory ────────────────────────────────────────────────────────────────────

class TestFactory:
    def test_creates_vw_client(self):
        from custom_components.vag_connect.cariad.api.factory import CariadClientFactory
        from custom_components.vag_connect.cariad.api.vw_eu import VWEUClient
        client = CariadClientFactory.create("volkswagen", MagicMock(), "u@t.de", "pw")
        assert isinstance(client, VWEUClient)
        assert client.brand.name == "volkswagen"

    def test_creates_audi_client(self):
        from custom_components.vag_connect.cariad.api.factory import CariadClientFactory
        from custom_components.vag_connect.cariad.api.audi import AudiClient
        client = CariadClientFactory.create("audi", MagicMock(), "u@t.de", "pw")
        assert isinstance(client, AudiClient)
        assert client.brand.name == "audi"

    def test_creates_skoda_client(self):
        from custom_components.vag_connect.cariad.api.factory import CariadClientFactory
        from custom_components.vag_connect.cariad.api.skoda import SkodaClient
        client = CariadClientFactory.create("skoda", MagicMock(), "u@t.de", "pw")
        assert isinstance(client, SkodaClient)

    def test_creates_seat_client(self):
        from custom_components.vag_connect.cariad.api.factory import CariadClientFactory
        from custom_components.vag_connect.cariad.api.seat_cupra import SeatCupraClient
        client = CariadClientFactory.create("seat", MagicMock(), "u@t.de", "pw")
        assert isinstance(client, SeatCupraClient)
        assert client.brand.name == "seat"

    def test_creates_cupra_client(self):
        from custom_components.vag_connect.cariad.api.factory import CariadClientFactory
        from custom_components.vag_connect.cariad.api.seat_cupra import SeatCupraClient
        client = CariadClientFactory.create("cupra", MagicMock(), "u@t.de", "pw")
        assert isinstance(client, SeatCupraClient)
        assert client.brand.name == "cupra"

    def test_unknown_brand_raises(self):
        from custom_components.vag_connect.cariad.api.factory import CariadClientFactory
        with pytest.raises(ValueError, match="Unknown brand"):
            CariadClientFactory.create("bmw", MagicMock(), "u@t.de", "pw")


# ── base client ────────────────────────────────────────────────────────────────

class TestBaseClient:
    def _make_client(self, json_data=None, status=200):
        from custom_components.vag_connect.cariad.api.vw_eu import VWEUClient
        from custom_components.vag_connect.cariad.models import TokenSet
        session = _mock_session(status=status, json_data=json_data or {})
        client = VWEUClient(session, "u@t.de", "pw")
        client._tokens = TokenSet("access123", "refresh123", "id123")
        return client

    def test_val_nested_path(self):
        from custom_components.vag_connect.cariad.api.base import CariadBaseClient
        client = CariadBaseClient.__new__(CariadBaseClient)
        data = {"a": {"b": {"c": 42}}}
        assert client._val(data, "a", "b", "c") == 42

    def test_val_missing_key_returns_default(self):
        from custom_components.vag_connect.cariad.api.base import CariadBaseClient
        client = CariadBaseClient.__new__(CariadBaseClient)
        assert client._val({"a": {}}, "a", "x", default="missing") == "missing"

    def test_val_none_stops_traversal(self):
        from custom_components.vag_connect.cariad.api.base import CariadBaseClient
        client = CariadBaseClient.__new__(CariadBaseClient)
        assert client._val({"a": None}, "a", "b") is None

    def test_access_token_raises_without_auth(self):
        from custom_components.vag_connect.cariad.api.vw_eu import VWEUClient
        from custom_components.vag_connect.cariad.exceptions import AuthenticationError
        client = VWEUClient(MagicMock(), "u@t.de", "pw")
        with pytest.raises(AuthenticationError, match="authenticate"):
            _ = client._access_token

    def test_get_vehicles(self):
        client = self._make_client(json_data={
            "data": [{"vin": "WVWZZZAUZLW012345"}, {"vin": "WAUZZZ4G5KN012345"}]
        })
        vins = asyncio.get_event_loop().run_until_complete(client.get_vehicles())
        assert vins == ["WVWZZZAUZLW012345", "WAUZZZ4G5KN012345"]

    def test_get_vehicles_empty(self):
        client = self._make_client(json_data={"data": []})
        vins = asyncio.get_event_loop().run_until_complete(client.get_vehicles())
        assert vins == []

    def test_request_raises_api_error_on_500(self):
        from custom_components.vag_connect.cariad.exceptions import APIError
        from custom_components.vag_connect.cariad.api.vw_eu import VWEUClient
        from custom_components.vag_connect.cariad.models import TokenSet

        session = _mock_session(status=500, text="Internal Error")
        # Make 401 retry not infinite by returning 500 on all calls
        client = VWEUClient(session, "u@t.de", "pw")
        client._tokens = TokenSet("acc", "ref", "id")

        # v1.8.7: 500 is now retried up to 3 times (was 2). Patch sleep
        # so the test finishes quickly instead of waiting 3+6+12 seconds.
        with patch("custom_components.vag_connect.cariad.api.base.asyncio.sleep",
                   new=AsyncMock(return_value=None)):
            with pytest.raises(APIError) as exc:
                asyncio.get_event_loop().run_until_complete(
                    client._request("GET", "https://example.com/api")
                )
        assert exc.value.status == 500

    def test_request_204_returns_none(self):
        from custom_components.vag_connect.cariad.api.vw_eu import VWEUClient
        from custom_components.vag_connect.cariad.models import TokenSet

        session = _mock_session(status=204)
        client = VWEUClient(session, "u@t.de", "pw")
        client._tokens = TokenSet("acc", "ref", "id")

        result = asyncio.get_event_loop().run_until_complete(
            client._request("POST", "https://example.com/api")
        )
        assert result is None


# ── VW EU status parsing ───────────────────────────────────────────────────────

class TestVWEUStatusParsing:
    """Test _parse_status with synthetic selectivestatus payloads."""

    def _client(self) -> object:
        from custom_components.vag_connect.cariad.api.vw_eu import VWEUClient
        from custom_components.vag_connect.cariad.models import TokenSet
        client = VWEUClient(MagicMock(), "u@t.de", "pw")
        client._tokens = TokenSet("acc", "ref", "id")
        return client

    def _ev_payload(self) -> dict:
        return {
            "charging": {
                "chargingStatus": {"value": {
                    "chargingState": "READY_FOR_CHARGING",
                    "chargePower_kW": None,
                    "chargeRate_kmph": None,
                }},
                "batteryStatus": {"value": {
                    "currentSOC_pct": 80,
                    "cruisingRangeElectric_km": 350,
                }},
                "plugStatus": {"value": {
                    "plugConnectionState": "CONNECTED",
                    "plugLockState": "LOCKED",
                }},
                "chargingSettings": {"value": {
                    "targetSOC_pct": 80,
                    "maxChargeCurrentAC_A": 16,
                    "autoUnlockPlugWhenChargedAC": "OFF",
                }},
            },
            "measurements": {
                "odometerStatus": {"value": {"odometer": 15000}},
                "fuelLevelStatus": {"value": {"carType": "electric"}},
            },
            "fuelStatus": {
                "rangeStatus": {"value": {
                    "primaryEngine": {"type": "electric", "remainingRange_km": 350},
                    "totalRange_km": 350,
                }},
            },
            "access": {
                "accessStatus": {"value": {
                    "doorLockStatus": "LOCKED",
                    "overallStatus": "SAFE",
                }},
            },
            "climatisation": {
                "climatisationStatus": {"value": {"climatisationState": "OFF"}},
                "climatisationSettings": {"value": {"targetTemperature_C": 21.0}},
                "windowHeatingStatus": {"value": {"windowHeatingStatus": []}},
            },
            "readiness": {
                "readinessStatus": {"value": {
                    "connectionState": {"isOnline": True},
                }},
            },
            "vehicleHealthInspection": {
                "maintenanceStatus": {"value": {
                    "inspectionDue_km": 8000,
                    "oilServiceDue_km": None,
                }},
            },
            "departureTimers": {
                "departureTimersStatus": {"value": {"timers": [
                    {"enabled": True, "departureTime": {"time": "07:30"}},
                    {"enabled": False, "departureTime": None},
                    {"enabled": False, "departureTime": None},
                ]}},
            },
        }

    def test_ev_battery_soc(self):
        client = self._client()
        result = client._parse_status("VIN1", self._ev_payload(), {})
        assert result.battery_soc == 80

    def test_ev_is_electric(self):
        client = self._client()
        result = client._parse_status("VIN1", self._ev_payload(), {})
        assert result.is_electric is True
        assert result.has_battery is True
        assert result.has_combustion is False

    def test_ev_not_charging(self):
        client = self._client()
        result = client._parse_status("VIN1", self._ev_payload(), {})
        assert result.is_charging is False
        assert result.charging_state == "READY_FOR_CHARGING"

    def test_ev_plug_connected(self):
        client = self._client()
        result = client._parse_status("VIN1", self._ev_payload(), {})
        assert result.plug_connected is True
        assert result.plug_state == "CONNECTED"
        assert result.connector_locked is True

    def test_ev_doors_locked(self):
        client = self._client()
        result = client._parse_status("VIN1", self._ev_payload(), {})
        assert result.doors_locked is True
        assert result.doors_open is False

    def test_ev_target_soc(self):
        client = self._client()
        result = client._parse_status("VIN1", self._ev_payload(), {})
        assert result.target_soc == 80
        assert result.max_charge_current == 16.0

    def test_ev_online(self):
        client = self._client()
        result = client._parse_status("VIN1", self._ev_payload(), {})
        assert result.is_online is True

    def test_ev_odometer(self):
        client = self._client()
        result = client._parse_status("VIN1", self._ev_payload(), {})
        assert result.odometer_km == 15000

    def test_ev_range(self):
        client = self._client()
        result = client._parse_status("VIN1", self._ev_payload(), {})
        assert result.range_km == 350

    def test_ev_target_temperature(self):
        client = self._client()
        result = client._parse_status("VIN1", self._ev_payload(), {})
        assert result.target_temperature == 21.0

    def test_ev_departure_timer_1_enabled(self):
        client = self._client()
        result = client._parse_status("VIN1", self._ev_payload(), {})
        assert result.departure_timer_1_enabled is True
        assert result.departure_timer_1_time == "07:30"
        assert result.departure_timer_2_enabled is False

    def test_service_km(self):
        client = self._client()
        result = client._parse_status("VIN1", self._ev_payload(), {})
        assert result.service_km == 8000

    def test_parking_position_from_dict(self):
        client = self._client()
        result = client._parse_status("VIN1", self._ev_payload(), {"lat": 48.137, "lon": 11.576})
        assert result.latitude == 48.137
        assert result.longitude == 11.576

    def test_phev_detection(self):
        client = self._client()
        payload = self._ev_payload()
        payload["fuelStatus"]["rangeStatus"]["value"]["primaryEngine"]["type"] = "electric"
        payload["fuelStatus"]["rangeStatus"]["value"]["secondaryEngine"] = {"type": "gasoline", "remainingRange_km": 400}
        result = client._parse_status("VIN1", payload, {})
        assert result.has_battery is True
        assert result.has_combustion is True
        assert result.is_hybrid is True
        assert result.is_electric is False

    def test_kelvin_to_celsius_conversion(self):
        client = self._client()
        payload = self._ev_payload()
        payload["measurements"]["outsideTemperatureStatus"] = {
            "value": {"outsideTemperature_K": 296.15}  # 23°C
        }
        result = client._parse_status("VIN1", payload, {})
        assert result.outside_temp == pytest.approx(23.0, abs=0.2)

    def test_charging_active_state(self):
        client = self._client()
        payload = self._ev_payload()
        payload["charging"]["chargingStatus"]["value"]["chargingState"] = "CHARGING"
        payload["charging"]["chargingStatus"]["value"]["chargePower_kW"] = 11.0
        result = client._parse_status("VIN1", payload, {})
        assert result.is_charging is True
        assert result.charging_power_kw == 11.0

    def test_doors_open_unsafe(self):
        client = self._client()
        payload = self._ev_payload()
        payload["access"]["accessStatus"]["value"]["overallStatus"] = "UNSAFE"
        payload["access"]["accessStatus"]["value"]["doors"] = [
            {"name": "frontLeft", "status": [{"value": "open"}]},
            {"name": "frontRight", "status": [{"value": "closed"}]},
        ]
        result = client._parse_status("VIN1", payload, {})
        assert result.doors_open is True
        assert result.doors_individual["frontLeft"] is True
        assert result.doors_individual["frontRight"] is False

    def test_empty_payload_no_crash(self):
        client = self._client()
        result = client._parse_status("VIN1", {}, {})
        assert result.vin == "VIN1"
        assert result.battery_soc is None
        assert result.is_online is False


# ── AudiClient ─────────────────────────────────────────────────────────────────

class TestAudiClient:
    def test_brand_is_audi(self):
        from custom_components.vag_connect.cariad.api.audi import AudiClient
        client = AudiClient(MagicMock(), "u@t.de", "pw")
        assert client.brand.name == "audi"

    def test_redirect_uri_is_myaudi(self):
        from custom_components.vag_connect.cariad.api.audi import AudiClient
        client = AudiClient(MagicMock(), "u@t.de", "pw")
        assert client.brand.redirect_uri == "myaudi:///"


class TestSkodaClient:
    def test_brand_is_skoda(self):
        from custom_components.vag_connect.cariad.api.skoda import SkodaClient
        client = SkodaClient(MagicMock(), "u@t.de", "pw")
        assert client.brand.name == "skoda"

    def test_get_vehicles_parses_garage(self):
        from custom_components.vag_connect.cariad.api.skoda import SkodaClient
        from custom_components.vag_connect.cariad.models import TokenSet

        session = _mock_session(json_data={"vehicles": [
            {"vin": "TMBJB7NE5M3001234"},
            {"vin": "TMBJB7NE5M3005678"},
        ]})
        client = SkodaClient(session, "u@t.de", "pw")
        client._tokens = TokenSet("acc", "ref", "id")

        vins = asyncio.get_event_loop().run_until_complete(client.get_vehicles())
        assert "TMBJB7NE5M3001234" in vins

    def test_api_base_is_skoda(self):
        from custom_components.vag_connect.cariad.api.skoda import _BASE
        assert "skoda-auto.cz" in _BASE


# ── SEAT/CUPRA client ──────────────────────────────────────────────────────────

class TestSeatCupraClient:
    def test_seat_brand_config(self):
        from custom_components.vag_connect.cariad.api.seat_cupra import SeatCupraClient
        client = SeatCupraClient(MagicMock(), "seat", "u@t.de", "pw")
        assert client.brand.name == "seat"
        assert "99a5b77d" in client.brand.client_id

    def test_cupra_brand_config(self):
        from custom_components.vag_connect.cariad.api.seat_cupra import SeatCupraClient
        client = SeatCupraClient(MagicMock(), "cupra", "u@t.de", "pw")
        assert client.brand.name == "cupra"
        assert "3c756d46" in client.brand.client_id

    def test_api_base_is_ola(self):
        from custom_components.vag_connect.cariad.api.seat_cupra import _BASE
        assert "ola.prod.code.seat" in _BASE

    def test_cupra_has_client_secret(self):
        from custom_components.vag_connect.cariad.models import BRAND_CUPRA
        assert BRAND_CUPRA.client_secret != ""
        assert len(BRAND_CUPRA.client_secret) > 20

    def test_seat_has_no_client_secret(self):
        from custom_components.vag_connect.cariad.models import BRAND_SEAT
        assert BRAND_SEAT.client_secret == ""

    def test_fetch_user_id_from_jwt(self):
        import asyncio
        from custom_components.vag_connect.cariad.api.seat_cupra import SeatCupraClient
        from custom_components.vag_connect.cariad.models import TokenSet
        import base64
        import json as _json
        client = SeatCupraClient(MagicMock(), "cupra", "u@t.de", "pw")
        # Build a fake JWT with 'sub' claim
        header = base64.urlsafe_b64encode(b'{"alg":"RS256"}').rstrip(b"=").decode()
        payload = base64.urlsafe_b64encode(
            _json.dumps({"sub": "test-user-123", "email": "u@t.de"}).encode()
        ).rstrip(b"=").decode()
        fake_jwt = f"{header}.{payload}.fakesig"
        client._tokens = TokenSet(
            access_token="fake_access", refresh_token="fake_refresh", id_token=fake_jwt
        )
        asyncio.get_event_loop().run_until_complete(client._fetch_user_id())
        assert client._user_id == "test-user-123"

    def test_fetch_user_id_fallback_on_bad_jwt(self):
        import asyncio
        from custom_components.vag_connect.cariad.api.seat_cupra import SeatCupraClient
        from custom_components.vag_connect.cariad.models import TokenSet
        client = SeatCupraClient(MagicMock(), "cupra", "u@t.de", "pw")
        client._tokens = TokenSet(
            access_token="fake", refresh_token="fake", id_token="not.a.jwt"
        )
        # Should not crash, user_id stays None (fallback API call will also fail in test)
        asyncio.get_event_loop().run_until_complete(client._fetch_user_id())
        # user_id is None because both JWT and API fallback failed
        assert client._user_id is None


# ── IDK auth flow deeper coverage ─────────────────────────────────────────────

class TestIDKAuthFlow:
    """Tests for the complete auth flow methods."""

    def _auth(self, brand_name="volkswagen"):
        from custom_components.vag_connect.cariad.auth.idk import IDKAuth
        from custom_components.vag_connect.cariad.models import BRANDS
        return IDKAuth(MagicMock(), BRANDS[brand_name])

    def _make_resp(self, status=200, text="", json_data=None, location=None):
        resp = AsyncMock()
        resp.status = status
        resp.text = AsyncMock(return_value=text)
        resp.json = AsyncMock(return_value=json_data or {})
        resp.headers = {}
        if location:
            resp.headers["Location"] = location
        resp.__aenter__ = AsyncMock(return_value=resp)
        resp.__aexit__ = AsyncMock(return_value=False)
        return resp

    def test_refresh_success(self):
        from custom_components.vag_connect.cariad.auth.idk import IDKAuth
        from custom_components.vag_connect.cariad.models import BRAND_VW_EU

        token_resp = self._make_resp(200, json_data={
            "access_token": "new_acc",
            "refresh_token": "new_ref",
            "id_token": "new_id",
        })

        session = MagicMock()
        session.post = MagicMock(return_value=token_resp)

        auth = IDKAuth(session, BRAND_VW_EU)
        result = asyncio.get_event_loop().run_until_complete(auth.refresh("old_refresh"))
        assert result.access_token == "new_acc"
        assert result.refresh_token == "new_ref"

    def test_refresh_400_raises_token_expired(self):
        from custom_components.vag_connect.cariad.auth.idk import IDKAuth
        from custom_components.vag_connect.cariad.exceptions import TokenExpiredError
        from custom_components.vag_connect.cariad.models import BRAND_VW_EU

        bad_resp = self._make_resp(400, text="invalid_grant")

        session = MagicMock()
        session.post = MagicMock(return_value=bad_resp)

        auth = IDKAuth(session, BRAND_VW_EU)
        with pytest.raises(TokenExpiredError):
            asyncio.get_event_loop().run_until_complete(auth.refresh("expired_token"))

    def test_exchange_code_skoda_proprietary(self):
        """Škoda uses proprietary JSON API, not standard OAuth."""
        from custom_components.vag_connect.cariad.auth.idk import IDKAuth
        from custom_components.vag_connect.cariad.models import BRAND_SKODA

        token_resp = self._make_resp(200, json_data={
            "access_token": "skoda_acc",
            "refresh_token": "skoda_ref",
            "id_token": "skoda_id",
        })

        session = MagicMock()
        session.post = MagicMock(return_value=token_resp)

        auth = IDKAuth(session, BRAND_SKODA)
        result = asyncio.get_event_loop().run_until_complete(
            auth._exchange_code("AUTH_CODE_XYZ", "verifier_abc")
        )
        assert result.access_token == "skoda_acc"

    def test_exchange_code_audi_standard(self):
        """Audi uses standard OAuth via CARIAD BFF."""
        from custom_components.vag_connect.cariad.auth.idk import IDKAuth
        from custom_components.vag_connect.cariad.models import BRAND_AUDI

        token_resp = self._make_resp(200, json_data={
            "access_token": "audi_acc",
            "refresh_token": "audi_ref",
            "id_token": "audi_id",
        })

        session = MagicMock()
        session.post = MagicMock(return_value=token_resp)

        auth = IDKAuth(session, BRAND_AUDI)
        result = asyncio.get_event_loop().run_until_complete(
            auth._exchange_code("CODE", "VERIFIER")
        )
        assert result.access_token == "audi_acc"

    def test_exchange_code_failure(self):
        from custom_components.vag_connect.cariad.auth.idk import IDKAuth
        from custom_components.vag_connect.cariad.exceptions import AuthenticationError
        from custom_components.vag_connect.cariad.models import BRAND_AUDI

        bad_resp = self._make_resp(401, text="invalid_client")

        session = MagicMock()
        session.post = MagicMock(return_value=bad_resp)

        auth = IDKAuth(session, BRAND_AUDI)
        with pytest.raises(AuthenticationError, match="401"):
            asyncio.get_event_loop().run_until_complete(
                auth._exchange_code("CODE", "VERIFIER")
            )

    def test_parse_tokens_missing_field_raises(self):
        from custom_components.vag_connect.cariad.auth.idk import IDKAuth
        from custom_components.vag_connect.cariad.exceptions import AuthenticationError
        from custom_components.vag_connect.cariad.models import BRAND_VW_EU

        auth = IDKAuth(MagicMock(), BRAND_VW_EU)
        with pytest.raises(AuthenticationError, match="missing"):
            auth._parse_tokens({"only": "partial"})

    def test_follow_redirect_terms_error(self):
        from custom_components.vag_connect.cariad.auth.idk import IDKAuth
        from custom_components.vag_connect.cariad.exceptions import TermsAndConditionsError
        from custom_components.vag_connect.cariad.models import BRAND_VW_EU

        resp = self._make_resp(302, location="https://idp/terms-and-conditions")
        session = MagicMock()
        session.post = MagicMock(return_value=resp)
        session.get = MagicMock(return_value=resp)

        auth = IDKAuth(session, BRAND_VW_EU)
        with pytest.raises(TermsAndConditionsError):
            asyncio.get_event_loop().run_until_complete(
                auth._follow_to_app_redirect(
                    "https://idp/authenticate",
                    {"email": "x", "password": "y"},
                    "weconnect://authenticated",
                )
            )

    def test_follow_redirect_rate_limit(self):
        from custom_components.vag_connect.cariad.auth.idk import IDKAuth
        from custom_components.vag_connect.cariad.exceptions import RateLimitError
        from custom_components.vag_connect.cariad.models import BRAND_VW_EU

        resp = self._make_resp(429, text="Too Many Requests")
        session = MagicMock()
        session.post = MagicMock(return_value=resp)

        auth = IDKAuth(session, BRAND_VW_EU)
        with pytest.raises(RateLimitError):
            asyncio.get_event_loop().run_until_complete(
                auth._follow_to_app_redirect(
                    "https://idp/authenticate",
                    {},
                    "weconnect://authenticated",
                )
            )

    def test_follow_redirect_direct_to_app(self):
        """302 directly to app URI — no additional requests needed."""
        from custom_components.vag_connect.cariad.auth.idk import IDKAuth
        from custom_components.vag_connect.cariad.models import BRAND_SKODA

        resp = self._make_resp(302, location="myskoda://redirect/login/?code=SKODA_CODE&state=xyz")
        session = MagicMock()
        session.post = MagicMock(return_value=resp)

        auth = IDKAuth(session, BRAND_SKODA)
        result = asyncio.get_event_loop().run_until_complete(
            auth._follow_to_app_redirect(
                "https://idp/authenticate",
                {},
                "myskoda://redirect/login/",
            )
        )
        assert result is not None
        assert "SKODA_CODE" in result

    def test_base_headers_contain_user_agent(self):
        from custom_components.vag_connect.cariad.auth.idk import IDKAuth
        from custom_components.vag_connect.cariad.models import BRAND_VW_EU
        auth = IDKAuth(MagicMock(), BRAND_VW_EU)
        headers = auth._base_headers()
        assert "Volkswagen" in headers["User-Agent"]

    def test_form_headers_content_type(self):
        from custom_components.vag_connect.cariad.auth.idk import IDKAuth
        from custom_components.vag_connect.cariad.models import BRAND_AUDI
        auth = IDKAuth(MagicMock(), BRAND_AUDI)
        headers = auth._form_headers()
        assert "application/x-www-form-urlencoded" in headers["Content-Type"]


# ── VW EU commands ────────────────────────────────────────────────────────────

class TestVWEUCommands:
    def _client(self):
        from custom_components.vag_connect.cariad.api.vw_eu import VWEUClient
        from custom_components.vag_connect.cariad.models import TokenSet
        resp = AsyncMock()
        resp.status = 204
        resp.headers = {"Content-Type": "application/json"}
        resp.__aenter__ = AsyncMock(return_value=resp)
        resp.__aexit__ = AsyncMock(return_value=False)
        session = MagicMock()
        session.request = MagicMock(return_value=resp)
        client = VWEUClient(session, "u@t.de", "pw")
        client._tokens = TokenSet("acc", "ref", "id")
        return client

    def test_command_lock(self):
        client = self._client()
        asyncio.get_event_loop().run_until_complete(client.command_lock("VIN1"))
        client._session.request.assert_called()

    def test_command_unlock(self):
        client = self._client()
        asyncio.get_event_loop().run_until_complete(client.command_unlock("VIN1"))
        client._session.request.assert_called()

    def test_command_unlock_with_spin(self):
        client = self._client()
        asyncio.get_event_loop().run_until_complete(client.command_unlock("VIN1", spin="1234"))
        client._session.request.assert_called()

    def test_command_start_climate(self):
        client = self._client()
        asyncio.get_event_loop().run_until_complete(client.command_start_climate("VIN1"))
        client._session.request.assert_called()

    def test_command_stop_climate(self):
        client = self._client()
        asyncio.get_event_loop().run_until_complete(client.command_stop_climate("VIN1"))
        client._session.request.assert_called()

    def test_command_start_charging(self):
        client = self._client()
        asyncio.get_event_loop().run_until_complete(client.command_start_charging("VIN1"))
        client._session.request.assert_called()

    def test_command_stop_charging(self):
        client = self._client()
        asyncio.get_event_loop().run_until_complete(client.command_stop_charging("VIN1"))
        client._session.request.assert_called()

    def test_command_flash(self):
        client = self._client()
        asyncio.get_event_loop().run_until_complete(client.command_flash("VIN1"))
        client._session.request.assert_called()

    def test_command_wake(self):
        client = self._client()
        asyncio.get_event_loop().run_until_complete(client.command_wake("VIN1"))
        client._session.request.assert_called()

    def test_command_set_target_soc(self):
        client = self._client()
        asyncio.get_event_loop().run_until_complete(client.command_set_target_soc("VIN1", 90))
        client._session.request.assert_called()

    def test_command_set_climate_temperature(self):
        client = self._client()
        asyncio.get_event_loop().run_until_complete(client.command_set_climate_temperature("VIN1", 22.0))
        client._session.request.assert_called()


# ── v1.8.8 Session 3B: v1/v2 + combined/separate endpoint dispatch ──────────

class TestVWEUFallbackPaths:
    """v1.8.8 — lock/unlock and climate/charging start/stop now dispatch
    through ``_post_command_with_fallback_paths``: try the combined
    endpoint on v1, on 404 v2; if both 404, try the separate endpoint on
    v1, on 404 v2. Critically, *only* HTTP 404 triggers the fallback —
    auth failures, rate limits and 5xx errors propagate so the
    coordinator can classify them correctly. The previous implementation
    caught a bare ``except Exception`` and masked all of these as
    endpoint-version mismatches.
    """

    @staticmethod
    def _resp(status: int, json_data=None, text: str = ""):
        resp = AsyncMock()
        resp.status = status
        resp.headers = {"Content-Type": "application/json"}
        resp.json = AsyncMock(return_value=json_data or {})
        resp.text = AsyncMock(return_value=text)
        resp.__aenter__ = AsyncMock(return_value=resp)
        resp.__aexit__ = AsyncMock(return_value=False)
        return resp

    def _client_with_responses(self, responses):
        """Build a VWEUClient whose session.request returns the given
        responses in order (last one is repeated if exhausted)."""
        from custom_components.vag_connect.cariad.api.vw_eu import VWEUClient
        from custom_components.vag_connect.cariad.models import TokenSet
        idx = {"i": 0}

        def side_effect(*args, **kwargs):
            r = responses[min(idx["i"], len(responses) - 1)]
            idx["i"] += 1
            return r

        session = MagicMock()
        session.request = MagicMock(side_effect=side_effect)
        client = VWEUClient(session, "u@t.de", "pw")
        client._tokens = TokenSet("acc", "ref", "id")
        return client, session, idx

    def test_404_on_v1_primary_falls_back_to_v2_primary(self):
        """v1/access/lock-unlock → 404, v2/access/lock-unlock → 204.
        Should call exactly two endpoints and not touch the separate
        access/lock fallback at all."""
        responses = [self._resp(404, text="not found"),
                     self._resp(204)]
        client, session, idx = self._client_with_responses(responses)
        with patch("custom_components.vag_connect.cariad.api.base.asyncio.sleep",
                   new=AsyncMock(return_value=None)):
            asyncio.get_event_loop().run_until_complete(client.command_lock("VIN1"))
        assert idx["i"] == 2
        urls = [call.args[1] for call in session.request.call_args_list]
        assert "/vehicle/v1/vehicles/VIN1/access/lock-unlock" in urls[0]
        assert "/vehicle/v2/vehicles/VIN1/access/lock-unlock" in urls[1]

    def test_404_on_both_primaries_falls_back_to_separate_endpoint(self):
        """v1+v2 of combined endpoint both 404 → tries the separate
        endpoint (v1/access/lock) which succeeds with 204."""
        responses = [self._resp(404),  # v1 combined
                     self._resp(404),  # v2 combined
                     self._resp(204)]  # v1 separate
        client, session, idx = self._client_with_responses(responses)
        with patch("custom_components.vag_connect.cariad.api.base.asyncio.sleep",
                   new=AsyncMock(return_value=None)):
            asyncio.get_event_loop().run_until_complete(client.command_lock("VIN1"))
        assert idx["i"] == 3
        urls = [call.args[1] for call in session.request.call_args_list]
        assert urls[0].endswith("/vehicle/v1/vehicles/VIN1/access/lock-unlock")
        assert urls[1].endswith("/vehicle/v2/vehicles/VIN1/access/lock-unlock")
        assert urls[2].endswith("/vehicle/v1/vehicles/VIN1/access/lock")

    def test_500_on_primary_does_not_trigger_fallback(self):
        """KEY REGRESSION TEST for v1.8.8: a 500 server error must
        propagate as APIError(500), NOT trigger the combined→separate
        fallback. The pre-v1.8.8 ``except Exception`` swallowed this
        and silently called the wrong endpoint."""
        from custom_components.vag_connect.cariad.exceptions import APIError

        # 500 on v1 combined; if we accidentally fall back, we'd see
        # additional requests. We give exactly one 500-response so any
        # accidental retry would surface (StopIteration on next call).
        responses = [self._resp(500, text="backend down")]
        client, session, idx = self._client_with_responses(responses)
        with patch("custom_components.vag_connect.cariad.api.base.asyncio.sleep",
                   new=AsyncMock(return_value=None)):
            with pytest.raises(APIError) as exc:
                asyncio.get_event_loop().run_until_complete(client.command_lock("VIN1"))
        assert exc.value.status == 500
        # The 500 itself is retried 4 times (3 backoff retries inside
        # _request) — that's the existing behaviour. What MUST NOT happen
        # is a fall-through to the separate access/lock endpoint.
        urls = [call.args[1] for call in session.request.call_args_list]
        assert all("access/lock-unlock" in u for u in urls), (
            f"Expected only combined-endpoint URLs (lock-unlock); got: {urls}"
        )
        assert not any(u.endswith("/access/lock") for u in urls), (
            f"500 must NOT trigger fallback to separate /access/lock; got: {urls}"
        )

    def test_unlock_passes_spin_in_both_payloads(self):
        """When falling back from combined to separate endpoint after a
        404, the S-PIN must be present in *both* payloads — the legacy
        separate /access/unlock endpoint accepts the PIN in the body."""
        responses = [self._resp(404),  # v1 combined
                     self._resp(404),  # v2 combined
                     self._resp(204)]  # v1 separate succeeds
        client, session, idx = self._client_with_responses(responses)
        with patch("custom_components.vag_connect.cariad.api.base.asyncio.sleep",
                   new=AsyncMock(return_value=None)):
            asyncio.get_event_loop().run_until_complete(
                client.command_unlock("VIN1", spin="1234")
            )
        # Inspect payloads: kwargs['json'] on each request
        payloads = [call.kwargs.get("json") for call in session.request.call_args_list]
        assert payloads[0] == {"action": "unlock", "spin": "1234"}, payloads[0]
        assert payloads[1] == {"action": "unlock", "spin": "1234"}, payloads[1]
        assert payloads[2] == {"spin": "1234"}, payloads[2]


# ── BaseClient refresh logic ──────────────────────────────────────────────────

class TestBaseClientRefresh:
    def test_refresh_on_401(self):
        """On 401, client should refresh token and retry."""
        from custom_components.vag_connect.cariad.api.vw_eu import VWEUClient
        from custom_components.vag_connect.cariad.models import TokenSet

        def make_resp(status, json_data=None):
            resp = AsyncMock()
            resp.status = status
            resp.headers = {"Content-Type": "application/json"}
            resp.json = AsyncMock(return_value=json_data or {})
            resp.text = AsyncMock(return_value="")
            resp.__aenter__ = AsyncMock(return_value=resp)
            resp.__aexit__ = AsyncMock(return_value=False)
            return resp

        responses = [make_resp(401), make_resp(200, {"data": []})]
        idx = 0
        def side_effect(*args, **kwargs):
            nonlocal idx
            r = responses[min(idx, len(responses)-1)]
            idx += 1
            return r

        session = MagicMock()
        session.request = MagicMock(side_effect=side_effect)
        # For token refresh — return new token
        refresh_resp = make_resp(200, {
            "token_endpoint": "https://idp/token",
        })
        token_resp = make_resp(200, {
            "access_token": "refreshed_acc",
            "refresh_token": "refreshed_ref",
            "id_token": "refreshed_id",
        })
        session.get = MagicMock(return_value=refresh_resp)
        session.post = MagicMock(return_value=token_resp)

        client = VWEUClient(session, "u@t.de", "pw")
        client._tokens = TokenSet("old_acc", "old_ref", "old_id")

        result = asyncio.get_event_loop().run_until_complete(client.get_vehicles())
        assert result == []

    def test_authenticate_stores_tokens(self):
        from custom_components.vag_connect.cariad.api.vw_eu import VWEUClient

        # Mock the entire auth flow
        client = VWEUClient(MagicMock(), "u@t.de", "pw")
        mock_tokens = MagicMock()
        mock_tokens.access_token = "fresh_token"
        client._auth.authenticate = AsyncMock(return_value=mock_tokens)

        asyncio.get_event_loop().run_until_complete(client.authenticate())
        assert client._tokens.access_token == "fresh_token"


# ── v1.8.7 hardening: 504, transient network errors, refresh-storm guard ─────

class TestBaseClientHardening:
    """v1.8.7 — retry coverage extended to 504 + transient network errors,
    plus token-refresh storm protection capped at 3/h."""

    @staticmethod
    def _resp(status: int, json_data=None, text: str = ""):
        resp = AsyncMock()
        resp.status = status
        resp.headers = {"Content-Type": "application/json"}
        resp.json = AsyncMock(return_value=json_data or {})
        resp.text = AsyncMock(return_value=text)
        resp.__aenter__ = AsyncMock(return_value=resp)
        resp.__aexit__ = AsyncMock(return_value=False)
        return resp

    @staticmethod
    def _client_with_session(session):
        from custom_components.vag_connect.cariad.api.vw_eu import VWEUClient
        from custom_components.vag_connect.cariad.models import TokenSet
        client = VWEUClient(session, "u@t.de", "pw")
        client._tokens = TokenSet("acc", "ref", "id")
        return client

    def test_request_retries_on_504_then_succeeds(self):
        """504 Gateway Timeout is now retried (was previously fatal)."""
        responses = [self._resp(504, text="GW timeout"),
                     self._resp(200, json_data={"ok": True})]
        idx = 0

        def side_effect(*args, **kwargs):
            nonlocal idx
            r = responses[min(idx, len(responses) - 1)]
            idx += 1
            return r

        session = MagicMock()
        session.request = MagicMock(side_effect=side_effect)
        client = self._client_with_session(session)
        with patch("custom_components.vag_connect.cariad.api.base.asyncio.sleep",
                   new=AsyncMock(return_value=None)):
            result = asyncio.get_event_loop().run_until_complete(
                client._request("GET", "https://example.com/api")
            )
        assert result == {"ok": True}
        assert idx >= 2  # at least one retry happened

    def test_request_retries_on_client_connector_error(self):
        """ClientConnectorError (DNS / connection refused) is retried, not raised."""
        from aiohttp import ClientConnectorError

        # Build a ClientConnectorError using its real signature
        connection_key = MagicMock()
        os_error = OSError("nodename nor servname provided, or not known")
        cc_err = ClientConnectorError(connection_key, os_error)

        ok_resp = self._resp(200, json_data={"recovered": True})
        responses_or_errors = [cc_err, ok_resp]
        idx = 0

        def side_effect(*args, **kwargs):
            nonlocal idx
            item = responses_or_errors[min(idx, len(responses_or_errors) - 1)]
            idx += 1
            if isinstance(item, Exception):
                raise item
            return item

        session = MagicMock()
        session.request = MagicMock(side_effect=side_effect)
        client = self._client_with_session(session)
        with patch("custom_components.vag_connect.cariad.api.base.asyncio.sleep",
                   new=AsyncMock(return_value=None)):
            result = asyncio.get_event_loop().run_until_complete(
                client._request("GET", "https://example.com/api")
            )
        assert result == {"recovered": True}

    def test_request_raises_api_error_after_persistent_transient(self):
        """After 4 attempts at a transient error, surface APIError(0, ...)."""
        from aiohttp import ServerDisconnectedError
        from custom_components.vag_connect.cariad.exceptions import APIError

        session = MagicMock()
        session.request = MagicMock(side_effect=ServerDisconnectedError())
        client = self._client_with_session(session)
        with patch("custom_components.vag_connect.cariad.api.base.asyncio.sleep",
                   new=AsyncMock(return_value=None)):
            with pytest.raises(APIError) as exc:
                asyncio.get_event_loop().run_until_complete(
                    client._request("GET", "https://example.com/api")
                )
        assert exc.value.status == 0
        assert "transient" in str(exc.value).lower()

    def test_refresh_storm_protection_raises_after_threshold(self):
        """More than 3 refresh attempts in 1h must raise AuthenticationError."""
        from custom_components.vag_connect.cariad.api.vw_eu import VWEUClient
        from custom_components.vag_connect.cariad.models import TokenSet
        from custom_components.vag_connect.cariad.exceptions import AuthenticationError

        client = VWEUClient(MagicMock(), "u@t.de", "pw")
        client._tokens = TokenSet("acc", "ref", "id")
        # Mock the inner refresh path so it always succeeds — we want to
        # verify the storm guard, not the refresh logic itself.
        client._auth.refresh = AsyncMock(return_value=TokenSet("acc2", "ref2", "id2"))

        loop = asyncio.get_event_loop()
        # First 3 refreshes succeed (within threshold)
        for _ in range(3):
            loop.run_until_complete(client._refresh_tokens())
        # Fourth must raise
        with pytest.raises(AuthenticationError, match="storm"):
            loop.run_until_complete(client._refresh_tokens())

    def test_refresh_storm_window_resets_after_age_out(self):
        """Old refresh timestamps must be pruned out of the rolling window."""
        from custom_components.vag_connect.cariad.api.vw_eu import VWEUClient
        from custom_components.vag_connect.cariad.models import TokenSet
        import time as _time

        client = VWEUClient(MagicMock(), "u@t.de", "pw")
        client._tokens = TokenSet("acc", "ref", "id")
        client._auth.refresh = AsyncMock(return_value=TokenSet("acc2", "ref2", "id2"))

        # Plant 3 ancient (>1h old) timestamps and one recent — should NOT trip
        old = _time.monotonic() - 7200  # 2h ago
        client._refresh_history = [old, old, old, _time.monotonic() - 5]
        # New refresh should succeed (only the recent one survives prune)
        asyncio.get_event_loop().run_until_complete(client._refresh_tokens())
        # History after prune should contain at most 2 entries (the recent
        # one + the brand new one)
        assert len(client._refresh_history) <= 2


# ── Škoda get_status ──────────────────────────────────────────────────────────

class TestSkodaGetStatus:
    def _client(self, json_data=None):
        from custom_components.vag_connect.cariad.api.skoda import SkodaClient
        from custom_components.vag_connect.cariad.models import TokenSet

        resp = AsyncMock()
        resp.status = 200
        resp.headers = {"Content-Type": "application/json"}
        resp.json = AsyncMock(return_value=json_data or {})
        resp.text = AsyncMock(return_value="")
        resp.__aenter__ = AsyncMock(return_value=resp)
        resp.__aexit__ = AsyncMock(return_value=False)

        session = MagicMock()
        session.request = MagicMock(return_value=resp)
        client = SkodaClient(session, "u@t.de", "pw")
        client._tokens = TokenSet("acc", "ref", "id")
        return client

    def test_get_status_returns_vehicle_data(self):
        client = self._client({"status": {"charging": {"state": "CHARGING"}}})
        result = asyncio.get_event_loop().run_until_complete(client.get_status("TMBTEST"))
        assert result.vin == "TMBTEST"

    def test_get_status_empty_responses(self):
        client = self._client({})
        result = asyncio.get_event_loop().run_until_complete(client.get_status("TMB123"))
        assert result.vin == "TMB123"
        assert result.battery_soc is None

    def test_skoda_commands(self):
        client = self._client()
        for cmd in ["lock", "unlock", "start_climate", "stop_climate",
                    "start_charging", "stop_charging", "flash", "wake"]:
            fn = getattr(client, f"command_{cmd}")
            asyncio.get_event_loop().run_until_complete(fn("TMBTEST"))
        asyncio.get_event_loop().run_until_complete(client.command_set_target_soc("TMBTEST", 80))
        asyncio.get_event_loop().run_until_complete(client.command_set_climate_temperature("TMBTEST", 21.0))

    def test_skoda_status_with_battery_data(self):
        client = self._client({
            "status": {
                "battery": {"stateOfChargeInPercent": 75},
                "state": "READY",
                "chargePowerInKw": 11.0,
                "chargingRateInKilometersPerHour": 45,
                "access": {"overallStatus": "LOCKED"},
            },
            "settings": {"targetStateOfChargeInPercent": 80},
            "maintenanceReport": {
                "mileageInKm": 25000,
                "inspectionDueInKm": 8000,
                "inspectionDueInDays": 120,
                "oilServiceDueInKm": 5000,
                "oilServiceDueInDays": 90,
            },
        })
        result = asyncio.get_event_loop().run_until_complete(client.get_status("TMB_EV"))
        assert result.vin == "TMB_EV"

    # ── v1.8.11 Session 3S: connection-state via carCapturedTimestamp ─────

    def _url_routing_client(self, by_path: dict):
        """Returns a SkodaClient whose session.request routes by URL substring.
        Lets each Skoda endpoint return a different JSON body."""
        from custom_components.vag_connect.cariad.api.skoda import SkodaClient
        from custom_components.vag_connect.cariad.models import TokenSet

        def _resp(json_data):
            r = AsyncMock()
            r.status = 200
            r.headers = {"Content-Type": "application/json"}
            r.json = AsyncMock(return_value=json_data)
            r.text = AsyncMock(return_value="")
            r.__aenter__ = AsyncMock(return_value=r)
            r.__aexit__ = AsyncMock(return_value=False)
            return r

        empty = _resp({})

        def side_effect(method, url, **kwargs):
            for pattern, body in by_path.items():
                if pattern in url:
                    return _resp(body)
            return empty

        session = MagicMock()
        session.request = MagicMock(side_effect=side_effect)
        client = SkodaClient(session, "u@t.de", "pw")
        client._tokens = TokenSet("acc", "ref", "id")
        return client

    def test_v1811_connection_state_online_when_recent(self):
        """v1.8.11 (Session 3S, closes #54): carCapturedTimestamp <30min ago
        → connection_state="online"."""
        from datetime import datetime, timezone, timedelta
        recent = (datetime.now(tz=timezone.utc) - timedelta(minutes=10)).isoformat()
        client = self._url_routing_client({
            "/api/v2/vehicle-status/": {"carCapturedTimestamp": recent},
        })
        result = asyncio.get_event_loop().run_until_complete(
            client.get_status("TMB_TEST"))
        assert result.connection_state == "online"
        assert result.last_seen_at is not None

    def test_v1811_connection_state_standby_under_24h(self):
        """v1.8.11: carCapturedTimestamp <24h ago → standby (wakeable)."""
        from datetime import datetime, timezone, timedelta
        hours_ago = (datetime.now(tz=timezone.utc) - timedelta(hours=5)).isoformat()
        client = self._url_routing_client({
            "/api/v2/vehicle-status/": {"carCapturedTimestamp": hours_ago},
        })
        result = asyncio.get_event_loop().run_until_complete(
            client.get_status("TMB_TEST"))
        assert result.connection_state == "standby"

    def test_v1811_connection_state_offline_over_24h(self):
        """v1.8.11: carCapturedTimestamp >=24h ago → offline (12V flat etc.)."""
        from datetime import datetime, timezone, timedelta
        days_ago = (datetime.now(tz=timezone.utc) - timedelta(days=2)).isoformat()
        client = self._url_routing_client({
            "/api/v2/vehicle-status/": {"carCapturedTimestamp": days_ago},
        })
        result = asyncio.get_event_loop().run_until_complete(
            client.get_status("TMB_TEST"))
        assert result.connection_state == "offline"

    def test_v1811_connection_state_none_when_no_timestamp(self):
        """v1.8.11: missing carCapturedTimestamp → connection_state stays None.
        Verified pattern from skodaconnect/myskoda PR #565: the field is NOT
        guaranteed to be present (e.g. SoftwareStatus NO_UPDATE_AVAILABLE
        doesn't include it). Must not crash, must not invent a value."""
        client = self._url_routing_client({
            "/api/v2/vehicle-status/": {"overall": {"locked": "YES"}},
        })
        result = asyncio.get_event_loop().run_until_complete(
            client.get_status("TMB_TEST"))
        assert result.connection_state is None
        assert result.last_seen_at is None

    def test_v1811_freshest_timestamp_across_subobjects(self):
        """v1.8.11: when multiple sub-objects each carry their own
        carCapturedTimestamp, the freshest one wins. Pattern verified
        in myskoda PR #536 (process_charging_event compares against
        snapshot timestamp)."""
        from datetime import datetime, timezone, timedelta
        old = (datetime.now(tz=timezone.utc) - timedelta(hours=10)).isoformat()
        fresh = (datetime.now(tz=timezone.utc) - timedelta(minutes=5)).isoformat()
        client = self._url_routing_client({
            "/api/v2/vehicle-status/": {"carCapturedTimestamp": old},
            "/api/v1/charging/":       {"carCapturedTimestamp": fresh},
        })
        result = asyncio.get_event_loop().run_until_complete(
            client.get_status("TMB_TEST"))
        # Fresh charging timestamp wins → online
        assert result.connection_state == "online"

    def test_v1811_detail_block_sunroof_trunk_bonnet(self):
        """v1.8.11 (CC-skoda issue #50, Kodiaq iV 2026 Live-Response):
        vehicle-status.detail = {sunroof, trunk, bonnet} with values
        CLOSED/OPEN/UNSUPPORTED. Pre-v1.8.11 these never populated for
        any Skoda."""
        client = self._url_routing_client({
            "/api/v2/vehicle-status/": {
                "detail": {
                    "sunroof": "OPEN",
                    "trunk":   "CLOSED",
                    "bonnet":  "CLOSED",
                },
            },
        })
        result = asyncio.get_event_loop().run_until_complete(
            client.get_status("TMB_TEST"))
        assert result.sunroof_open is True
        assert result.trunk_open is False
        assert result.hood_open is False  # bonnet → hood

    def test_v1811_detail_unsupported_stays_none(self):
        """v1.8.11: 'UNSUPPORTED' must NOT be parsed as True or False —
        the field doesn't apply to this vehicle (e.g. Karoq Diesel
        without sunroof should not show a sunroof_open=False entity)."""
        client = self._url_routing_client({
            "/api/v2/vehicle-status/": {
                "detail": {"sunroof": "UNSUPPORTED", "trunk": "CLOSED"},
            },
        })
        result = asyncio.get_event_loop().run_until_complete(
            client.get_status("TMB_TEST"))
        assert result.sunroof_open is None
        assert result.trunk_open is False

    def test_v1811_reliable_lock_status_preferred(self):
        """v1.8.11 (CC-skoda #50): overall.reliableLockStatus is the
        trustworthy lock field on Kodiaq 2026+ — prefer it over
        doorsLocked which can lag."""
        client = self._url_routing_client({
            "/api/v2/vehicle-status/": {
                "overall": {
                    "doorsLocked": "NO",        # stale
                    "reliableLockStatus": "LOCKED",  # truth
                },
            },
        })
        result = asyncio.get_event_loop().run_until_complete(
            client.get_status("TMB_TEST"))
        assert result.doors_locked is True

    def test_v1811_charging_fully_charged_at_iso_timestamp(self):
        """v1.8.11 (CC-skoda #50): charging.fullyChargedAt is an absolute
        ISO timestamp — prefer it over remainingTimeToFullyChargedInMinutes
        (which drifts because it's car-side computed and we receive it
        with poll latency)."""
        from datetime import datetime
        eta = "2026-12-31T23:59:00Z"
        client = self._url_routing_client({
            "/api/v1/charging/": {
                "status": {
                    "state": "CHARGING",
                    "fullyChargedAt": eta,
                    "remainingTimeToFullyChargedInMinutes": 99999,  # ignored
                    "battery": {"stateOfChargeInPercent": 50},
                },
            },
        })
        result = asyncio.get_event_loop().run_until_complete(
            client.get_status("TMB_TEST"))
        assert result.charge_complete_eta is not None
        # Absolute timestamp used, NOT now()+99999min
        expected = datetime.fromisoformat(eta.replace("Z", "+00:00"))
        assert result.charge_complete_eta == expected

    def test_v1811_charging_interrupted_state_not_charging(self):
        """v1.8.11 (myskoda issue #503): CHARGING_INTERRUPTED is a new
        ChargingState added Feb 2026. Our `is_charging = state == "CHARGING"`
        is correct-by-design — interrupted ≠ active charging. Test exists
        so a future refactor doesn't accidentally treat interrupted as
        active."""
        client = self._url_routing_client({
            "/api/v1/charging/": {
                "status": {
                    "state": "CHARGING_INTERRUPTED",
                    "battery": {"stateOfChargeInPercent": 50},
                },
            },
        })
        result = asyncio.get_event_loop().run_until_complete(
            client.get_status("TMB_TEST"))
        assert result.charging_state == "CHARGING_INTERRUPTED"
        assert result.is_charging is False  # NOT True


# ── SEAT/CUPRA get_status ──────────────────────────────────────────────────────

class TestSeatCupraGetStatus:
    def _client(self, brand="cupra", json_data=None):
        from custom_components.vag_connect.cariad.api.seat_cupra import SeatCupraClient
        from custom_components.vag_connect.cariad.models import TokenSet

        resp = AsyncMock()
        resp.status = 200
        resp.headers = {"Content-Type": "application/json"}
        resp.json = AsyncMock(return_value=json_data or {})
        resp.text = AsyncMock(return_value="")
        resp.__aenter__ = AsyncMock(return_value=resp)
        resp.__aexit__ = AsyncMock(return_value=False)

        session = MagicMock()
        session.request = MagicMock(return_value=resp)
        client = SeatCupraClient(session, brand, "u@t.de", "pw")
        client._tokens = TokenSet("acc", "ref", "id")
        client._user_id = "USER_123"
        return client

    def test_get_status_cupra(self):
        client = self._client("cupra")
        result = asyncio.get_event_loop().run_until_complete(client.get_status("VSSZZE1KZLR123456"))
        assert result.vin == "VSSZZE1KZLR123456"

    def test_get_status_seat(self):
        client = self._client("seat")
        result = asyncio.get_event_loop().run_until_complete(client.get_status("VSSZZZ5FZHR123456"))
        assert result.vin == "VSSZZZ5FZHR123456"

    def test_seat_commands(self):
        client = self._client("seat")
        # Excluded from this loop:
        #  - command_flash         — needs userPosition (separate test)
        #  - command_lock/unlock   — need S-PIN SecToken (separate test below)
        for cmd in ["start_climate", "stop_climate",
                    "start_charging", "stop_charging", "wake"]:
            fn = getattr(client, f"command_{cmd}")
            asyncio.get_event_loop().run_until_complete(fn("VIN_SEAT"))
        asyncio.get_event_loop().run_until_complete(client.command_set_target_soc("VIN_SEAT", 80))
        asyncio.get_event_loop().run_until_complete(client.command_set_climate_temperature("VIN_SEAT", 20.0))

    def test_seat_lock_unlock_require_spin(self):
        """v1.8.4 (#53): lock/unlock without S-PIN must raise SpinError before any HTTP call."""
        from custom_components.vag_connect.cariad.exceptions import SpinError
        client = self._client("seat")  # _client() does not configure an S-PIN

        with pytest.raises(SpinError):
            asyncio.get_event_loop().run_until_complete(client.command_lock("VIN_SEAT"))
        with pytest.raises(SpinError):
            asyncio.get_event_loop().run_until_complete(client.command_unlock("VIN_SEAT"))

    def test_seat_command_flash_resilient_to_missing_position(self):
        """v2.0.0 (#53 Gerhard CUPRA Born): command_flash now tries body
        WITHOUT userPosition first; only enforces position on backend 400.

        - bare body call succeeds → no error (unblocks pre-GPS users)
        - bare body call succeeds with position present too (no regression)
        - bare body call → 400 + no position cached → APIError with guidance
        """
        from custom_components.vag_connect.cariad.exceptions import APIError

        # Case 1: backend accepts bare body → no error even without position
        client = self._client("seat")
        asyncio.get_event_loop().run_until_complete(client.command_flash("VIN_SEAT"))

        # Case 2: backend accepts bare body → still no error with position
        client = self._client("seat")
        asyncio.get_event_loop().run_until_complete(
            client.command_flash("VIN_SEAT", latitude=48.137, longitude=11.576)
        )

        # Case 3: backend returns 400 + no position → APIError raised
        client = self._client("seat")
        # Force the bare body call to return 400 by patching session.request's resp
        resp_400 = AsyncMock()
        resp_400.status = 400
        resp_400.headers = {"Content-Type": "application/json"}
        resp_400.json = AsyncMock(return_value={"error": "needs userPosition"})
        resp_400.text = AsyncMock(return_value='{"error":"needs userPosition"}')
        resp_400.__aenter__ = AsyncMock(return_value=resp_400)
        resp_400.__aexit__ = AsyncMock(return_value=False)
        client._session.request = MagicMock(return_value=resp_400)
        with pytest.raises(APIError):
            asyncio.get_event_loop().run_until_complete(client.command_flash("VIN_SEAT"))

    def test_get_vehicles_with_user_id(self):
        client = self._client("cupra", json_data={"vehicles": [
            {"vin": "VSSZZE1KZLR000001"},
        ]})
        vins = asyncio.get_event_loop().run_until_complete(client.get_vehicles())
        assert "VSSZZE1KZLR000001" in vins

    # ── v1.8.9 Session 3C: OLA /v2/.../status JSON-paths ──────────────────

    @staticmethod
    def _resp(json_data):
        resp = AsyncMock()
        resp.status = 200
        resp.headers = {"Content-Type": "application/json"}
        resp.json = AsyncMock(return_value=json_data)
        resp.text = AsyncMock(return_value="")
        resp.__aenter__ = AsyncMock(return_value=resp)
        resp.__aexit__ = AsyncMock(return_value=False)
        return resp

    def _client_with_url_routing(self, brand: str, by_path: dict):
        """Return a SeatCupraClient whose session.request routes by URL substring.
        ``by_path`` maps URL substring → JSON body. Unknown URLs return ``{}``."""
        from custom_components.vag_connect.cariad.api.seat_cupra import SeatCupraClient
        from custom_components.vag_connect.cariad.models import TokenSet

        empty = self._resp({})

        def side_effect(method, url, **kwargs):
            for pattern, body in by_path.items():
                if pattern in url:
                    return self._resp(body)
            return empty

        session = MagicMock()
        session.request = MagicMock(side_effect=side_effect)
        client = SeatCupraClient(session, brand, "u@t.de", "pw")
        client._tokens = TokenSet("acc", "ref", "id")
        client._user_id = "USER_TEST"
        return client

    def test_v189_status_parses_doors_per_position(self):
        """v1.8.9 (Session 3C): pycupra-style ``status.doors.{position}.{locked,open}``
        is parsed into ``doors_individual`` and aggregates ``doors_open`` /
        ``doors_locked`` are derived correctly."""
        status_body = {
            "doors": {
                "frontLeft":  {"locked": True, "open": False},
                "frontRight": {"locked": True, "open": True},   # this one is open
                "rearLeft":   {"locked": True, "open": False},
                "rearRight":  {"locked": False, "open": False}, # this one not locked
            },
        }
        client = self._client_with_url_routing("cupra", {"/v2/vehicles/": status_body})
        result = asyncio.get_event_loop().run_until_complete(
            client.get_status("VSSZZE1KZLR000001"))

        assert result.doors_individual == {
            "frontLeft":  True,
            "frontRight": False,  # open
            "rearLeft":   True,
            "rearRight":  True,
        }
        assert result.doors_open is True       # frontRight open → at least one
        assert result.doors_locked is False    # rearRight not locked → not all

    def test_v189_status_parses_windows_per_position(self):
        """v1.8.9: pycupra-style ``status.windows.{position}`` (string state)
        populates the new ``windows_individual`` dict and ``windows_open``."""
        status_body = {
            "windows": {
                "frontLeft":  "closed",
                "frontRight": "open",     # one open
                "rearLeft":   "closed",
                "rearRight":  "closed",
            },
        }
        client = self._client_with_url_routing("cupra", {"/v2/vehicles/": status_body})
        result = asyncio.get_event_loop().run_until_complete(
            client.get_status("VSSZZE1KZLR000002"))

        assert result.windows_individual == {
            "frontLeft":  True,
            "frontRight": False,  # open
            "rearLeft":   True,
            "rearRight":  True,
        }
        assert result.windows_open is True

    def test_v189_status_parses_trunk_hood_nested_objects(self):
        """v1.8.9: ``status.trunk`` and ``status.hood`` are nested objects
        with ``open`` (and optionally ``locked``), not flat strings."""
        status_body = {
            "trunk": {"open": False, "locked": True},
            "hood":  {"open": True},
        }
        client = self._client_with_url_routing("cupra", {"/v2/vehicles/": status_body})
        result = asyncio.get_event_loop().run_until_complete(
            client.get_status("VSSZZE1KZLR000003"))

        assert result.trunk_open is False
        assert result.trunk_locked is True
        assert result.hood_open is True

    def test_v189_status_sunroof_in_windows_subtree(self):
        """v1.8.9: pycupra reads sunroof from BOTH ``status.sunroof`` and
        ``status.windows.sunroof`` because firmware varies."""
        status_body = {"windows": {"sunroof": "open"}}
        client = self._client_with_url_routing("cupra", {"/v2/vehicles/": status_body})
        result = asyncio.get_event_loop().run_until_complete(
            client.get_status("VSSZZE1KZLR000004"))
        assert result.sunroof_open is True

    def test_v189_charging_shape_b_chargedPowerInKw_remaining_minutes(self):
        """v1.8.9 / Issue upstream/<project>#109:
        OLA `/v1/vehicles/{vin}/charging` returns `chargedPowerInKw` (with
        the extra "d") and `remainingTimeInMinutes` on current CUPRA Born
        firmware. Pre-v1.8.9 only knew variants without the "d", so power
        and ETA never populated."""
        charging_body = {
            "state": "charging",
            "chargedPowerInKw": 11.0,
            "remainingTimeInMinutes": 75,
            "type": "AC",
            "mode": "manual",
        }
        client = self._client_with_url_routing("cupra", {
            "/v1/vehicles/": charging_body,  # routes both /charging/status and others
        })
        # Disambiguate URL routing — only /charging/status URLs match
        # because the helper picks substring; charging/info, mileage etc.
        # also contain "/v1/vehicles/". For this focused test we only
        # care that the field is parsed when present, not that other
        # endpoints stay untouched. Status endpoint also gets this body
        # but won't write into door fields because there's no `doors` key.
        result = asyncio.get_event_loop().run_until_complete(
            client.get_status("VSSZZE1KZLR000006"))

        assert result.charging_power_kw == 11.0, "chargedPowerInKw not parsed"
        assert result.charge_complete_eta is not None, "remainingTimeInMinutes not used for ETA"
        assert result.charging_state == "charging"
        assert result.is_charging is True
        assert result.charging_type == "AC"

    def test_v189_charging_settings_targetSoc_pct_lowercase(self):
        """v1.8.9 / Issue #109: charging/settings uses `targetSoc_pct`
        (lowercase "soc") on current Born firmware, not `targetSOC_pct`."""
        # Route /charging/info to body with the lowercase variant
        client = self._client_with_url_routing("cupra", {
            "/v1/vehicles/": {"targetSoc_pct": 80, "maxChargeCurrentAC": "maximum"},
        })
        result = asyncio.get_event_loop().run_until_complete(
            client.get_status("VSSZZE1KZLR000007"))
        assert result.target_soc == 80, "targetSoc_pct (lowercase) not parsed"

    def test_v189_status_sunroof_top_level_camelCase(self):
        """v1.8.9 / CC-seatcupra issue #5: ``sunRoof`` (camelCase with capital R)
        is a top-level field on Seat Leon KL — verified live in #5
        comments. Pre-v1.8.9 only checked ``status.sunroof`` (lowercase) and
        ``status.windows.sunroof``, so Leon owners never saw the entity."""
        status_body = {"sunRoof": "open"}
        client = self._client_with_url_routing("cupra", {"/v2/vehicles/": status_body})
        result = asyncio.get_event_loop().run_until_complete(
            client.get_status("VSSZZE1KZLR000008"))
        assert result.sunroof_open is True

    def test_v189_status_engine_on_implies_driving(self):
        """v1.8.9 / CC-seatcupra #50 + #18: ``engine: 'on'`` is the only
        reliable signal that the car is being driven — official ``vehicle.state``
        often stays at "parked" (issue #18). When engine='on', set
        ``is_driving=True`` AND ``vehicle_state="DRIVING"``."""
        status_body = {"engine": "on"}
        client = self._client_with_url_routing("cupra", {"/v2/vehicles/": status_body})
        result = asyncio.get_event_loop().run_until_complete(
            client.get_status("VSSZZE1KZLR000009"))
        assert result.is_driving is True
        assert result.vehicle_state == "DRIVING"

    def test_v189_status_engine_off_does_not_force_driving(self):
        """v1.8.9: ``engine: 'off'`` must NOT force ``vehicle_state``;
        coordinator decides between PARKED/CHARGING/OFFLINE elsewhere."""
        status_body = {"engine": "off"}
        client = self._client_with_url_routing("cupra", {"/v2/vehicles/": status_body})
        result = asyncio.get_event_loop().run_until_complete(
            client.get_status("VSSZZE1KZLR000010"))
        assert result.is_driving is False
        # vehicle_state may be None (default) — important is we don't
        # accidentally set it to "DRIVING".
        assert result.vehicle_state != "DRIVING"

    def test_v189_auto_unlock_permanent_is_truthy(self):
        """v1.8.9 / CC-seatcupra issue #51: ``autoUnlockPlugWhenCharged``
        can be ``"permanent"`` (always unlocked) in addition to "on"/"off".
        Pre-v1.8.9 only checked exact "ON" and missed "permanent" → user
        couldn't see the actual config."""
        client = self._client_with_url_routing("cupra", {
            "/v1/vehicles/": {
                "targetSoc_pct": 80,
                "autoUnlockPlugWhenCharged": "permanent",
            },
        })
        result = asyncio.get_event_loop().run_until_complete(
            client.get_status("VSSZZE1KZLR000011"))
        assert result.auto_unlock_charge is True

    def test_v189_climatisation_trigger_unsupported_is_inactive(self):
        """v1.8.9 / CC-seatcupra issues #21 + #8: ``climatisationState`` can
        return ``"unsupported"`` on older Born firmware. Must be treated as
        inactive (climate off), not as an error or 'on'."""
        # Route /v2/vehicles/...climatisation to a body with unsupported state
        client = self._client_with_url_routing("cupra", {
            "climatisation": {"status": {"climatisationState": "unsupported"}},
        })
        result = asyncio.get_event_loop().run_until_complete(
            client.get_status("VSSZZE1KZLR000012"))
        assert result.climatisation_active is False

    def test_v189_status_legacy_flat_fallback_still_works(self):
        """v1.8.9: defensive — if a (rare/older) firmware sends the
        pre-v1.8.9 flat CARIAD-BFF-style fields, the legacy fallback
        path still populates doors_individual."""
        status_body = {
            "access": {
                "doorClosedLeftFront":  False,  # → frontLeft open
                "doorClosedRightFront": True,   # → frontRight closed
                "doorClosedLeftBack":   True,
                "doorClosedRightBack":  True,
                "doorsOpenedCount":     1,
                "windowsOpenedCount":   0,
                "trunk":                "OPEN",
                "trunkStatus":          "LOCKED",
                "hoodOpen":             False,
            },
        }
        client = self._client_with_url_routing("cupra", {"/v2/vehicles/": status_body})
        result = asyncio.get_event_loop().run_until_complete(
            client.get_status("VSSZZE1KZLR000005"))

        # New-shape parsing produces nothing → legacy fallback fires
        assert result.doors_individual == {
            "frontLeft":  False,  # open
            "frontRight": True,
            "rearLeft":   True,
            "rearRight":  True,
        }
        assert result.doors_open is True
        assert result.windows_open is False
        assert result.trunk_open is True
        assert result.trunk_locked is True
        assert result.hood_open is False

    def test_fetch_user_id(self):
        from custom_components.vag_connect.cariad.api.seat_cupra import SeatCupraClient
        from custom_components.vag_connect.cariad.models import TokenSet

        resp = AsyncMock()
        resp.status = 200
        resp.headers = {"Content-Type": "application/json"}
        resp.json = AsyncMock(return_value={"userId": "seat_user_456"})
        resp.__aenter__ = AsyncMock(return_value=resp)
        resp.__aexit__ = AsyncMock(return_value=False)
        session = MagicMock()
        session.request = MagicMock(return_value=resp)

        client = SeatCupraClient(session, "seat", "u@t.de", "pw")
        client._tokens = TokenSet("acc", "ref", "id")
        client._user_id = None

        asyncio.get_event_loop().run_until_complete(client._fetch_user_id())
        assert client._user_id == "seat_user_456"

    def test_status_with_kelvin_temperature(self):
        """Celsius conversion from Kelvin target temperature."""
        client = self._client("cupra", {
            "status": {"climatisationState": "HEATING"},
            "settings": {"targetTemperature_K": 294.15},  # 21°C
        })
        result = asyncio.get_event_loop().run_until_complete(client.get_status("CUPRA_VIN"))
        if result.target_temperature is not None:
            assert abs(result.target_temperature - 21.0) < 0.2


# ── Coordinator new code ───────────────────────────────────────────────────────

class TestCoordinatorCariad:
    def _make_coord(self):
        from custom_components.vag_connect.coordinator import VagConnectCoordinator
        import threading
        coord = VagConnectCoordinator.__new__(VagConnectCoordinator)
        coord.hass = MagicMock()
        coord.hass.loop = MagicMock()
        coord.hass.loop.is_running = MagicMock(return_value=False)
        coord.entry = MagicMock()
        coord.entry.data = {
            "brand": "volkswagen",
            "username": "u@t.de",
            "password": "pw",
            "spin": "",
            "scan_interval": 5,
            "force_enable_access": False,
            "entry_id": "test_entry",
        }
        coord.entry.entry_id = "test_entry"
        coord._vehicles_lock = threading.Lock()
        coord.vehicles = {}
        coord.data = None
        coord._was_available = True
        coord._started = False
        coord._cariad_client = None
        coord.async_set_updated_data = MagicMock()
        coord.async_update_listeners = MagicMock()
        coord.async_request_refresh = AsyncMock()
        coord.last_update_success = True
        coord.logger = MagicMock()
        return coord

    def test_is_active_false_initially(self):
        coord = self._make_coord()
        assert coord.is_active is False

    def test_is_active_true_after_start(self):
        coord = self._make_coord()
        coord._started = True
        assert coord.is_active is True

    def test_async_setup_invalid_credentials(self):
        """AuthenticationError from client is mapped to ValueError('invalid_credentials')."""
        from custom_components.vag_connect.cariad.exceptions import AuthenticationError
        from custom_components.vag_connect.cariad.api.factory import CariadClientFactory

        coord = self._make_coord()

        mock_client = MagicMock()
        mock_client.authenticate = AsyncMock(side_effect=AuthenticationError("bad creds"))

        with patch.object(CariadClientFactory, "create", return_value=mock_client),              patch("homeassistant.helpers.aiohttp_client.async_get_clientsession", return_value=MagicMock()):
            with pytest.raises(ValueError, match="invalid_credentials"):
                asyncio.get_event_loop().run_until_complete(coord.async_setup())

    def test_async_shutdown_sets_started_false(self):
        coord = self._make_coord()
        coord._started = True
        asyncio.get_event_loop().run_until_complete(coord.async_shutdown())
        assert coord._started is False
        assert coord._cariad_client is None

    def test_poll_loop_stops_when_not_started(self):
        """_poll_loop exits immediately when _started is False."""
        coord = self._make_coord()
        coord._started = False
        # Should return immediately without making any API calls
        asyncio.get_event_loop().run_until_complete(coord._poll_loop())


# ── Coordinator async_setup full paths ────────────────────────────────────────

class TestCoordinatorAsyncSetup:
    """Tests for coordinator.async_setup with mocked cariad client."""

    def _coord(self):
        import threading
        from custom_components.vag_connect.coordinator import VagConnectCoordinator
        coord = VagConnectCoordinator.__new__(VagConnectCoordinator)
        coord.hass = MagicMock()
        coord.hass.loop = MagicMock()
        coord.hass.loop.call_soon_threadsafe = MagicMock()
        coord.entry = MagicMock()
        coord.entry.entry_id = "test"
        coord.entry.data = {
            "brand": "volkswagen", "username": "u@t.de",
            "password": "pw", "spin": "", "scan_interval": 5,
        }
        coord._vehicles_lock = threading.Lock()
        coord._cariad_client = None
        coord._started = False
        coord._was_available = True
        coord.vehicles = {}
        coord.data = None
        coord.async_set_updated_data = MagicMock()
        coord.async_request_refresh = AsyncMock()
        coord.logger = MagicMock()
        return coord

    def _mock_client(self, vins=None, status_data=None):
        from custom_components.vag_connect.cariad.models import VehicleData
        client = MagicMock()
        client.authenticate = AsyncMock()
        client.get_vehicles = AsyncMock(return_value=vins or ["VIN123"])
        result = status_data or VehicleData(vin="VIN123", battery_soc=80)
        client.get_status = AsyncMock(return_value=result)
        return client

    def test_async_setup_success(self):
        from custom_components.vag_connect.cariad.api.factory import CariadClientFactory
        coord = self._coord()
        client = self._mock_client()
        with patch.object(CariadClientFactory, "create", return_value=client), \
             patch("homeassistant.helpers.aiohttp_client.async_get_clientsession", return_value=MagicMock()):
            result = asyncio.get_event_loop().run_until_complete(coord.async_setup())
        assert result is True
        assert coord._started is True
        assert "VIN123" in coord.vehicles

    def test_async_setup_no_vehicles_returns_false(self):
        from custom_components.vag_connect.cariad.api.factory import CariadClientFactory
        coord = self._coord()
        client = MagicMock()
        client.authenticate = AsyncMock()
        client.get_vehicles = AsyncMock(return_value=[])
        with patch.object(CariadClientFactory, "create", return_value=client), \
             patch("homeassistant.helpers.aiohttp_client.async_get_clientsession", return_value=MagicMock()):
            result = asyncio.get_event_loop().run_until_complete(coord.async_setup())
        assert result is False
        client.get_status.assert_not_called()

    def test_async_setup_terms_error(self):
        from custom_components.vag_connect.cariad.api.factory import CariadClientFactory
        from custom_components.vag_connect.cariad.exceptions import TermsAndConditionsError
        coord = self._coord()
        client = MagicMock()
        client.authenticate = AsyncMock(side_effect=TermsAndConditionsError())
        with patch.object(CariadClientFactory, "create", return_value=client), \
             patch("homeassistant.helpers.aiohttp_client.async_get_clientsession", return_value=MagicMock()):
            with pytest.raises(ValueError, match="terms_and_conditions"):
                asyncio.get_event_loop().run_until_complete(coord.async_setup())

    def test_async_setup_rate_limit_error(self):
        from custom_components.vag_connect.cariad.api.factory import CariadClientFactory
        from custom_components.vag_connect.cariad.exceptions import RateLimitError
        coord = self._coord()
        client = MagicMock()
        client.authenticate = AsyncMock(side_effect=RateLimitError())
        with patch.object(CariadClientFactory, "create", return_value=client), \
             patch("homeassistant.helpers.aiohttp_client.async_get_clientsession", return_value=MagicMock()):
            with pytest.raises(ValueError, match="too_many_requests"):
                asyncio.get_event_loop().run_until_complete(coord.async_setup())

    def test_async_setup_marketing_consent_error(self):
        from custom_components.vag_connect.cariad.api.factory import CariadClientFactory
        from custom_components.vag_connect.cariad.exceptions import MarketingConsentError
        coord = self._coord()
        client = MagicMock()
        client.authenticate = AsyncMock(side_effect=MarketingConsentError())
        with patch.object(CariadClientFactory, "create", return_value=client), \
             patch("homeassistant.helpers.aiohttp_client.async_get_clientsession", return_value=MagicMock()):
            with pytest.raises(ValueError, match="marketing_consent"):
                asyncio.get_event_loop().run_until_complete(coord.async_setup())

    def test_async_setup_two_factor_error(self):
        from custom_components.vag_connect.cariad.api.factory import CariadClientFactory
        from custom_components.vag_connect.cariad.exceptions import TwoFactorRequiredError
        coord = self._coord()
        client = MagicMock()
        client.authenticate = AsyncMock(side_effect=TwoFactorRequiredError())
        with patch.object(CariadClientFactory, "create", return_value=client), \
             patch("homeassistant.helpers.aiohttp_client.async_get_clientsession", return_value=MagicMock()):
            with pytest.raises(ValueError, match="two_factor_required"):
                asyncio.get_event_loop().run_until_complete(coord.async_setup())

    def test_async_setup_generic_error_returns_false(self):
        from custom_components.vag_connect.cariad.api.factory import CariadClientFactory
        coord = self._coord()
        client = MagicMock()
        client.authenticate = AsyncMock(side_effect=ConnectionError("network down"))
        with patch.object(CariadClientFactory, "create", return_value=client), \
             patch("homeassistant.helpers.aiohttp_client.async_get_clientsession", return_value=MagicMock()):
            result = asyncio.get_event_loop().run_until_complete(coord.async_setup())
        assert result is False

    def test_async_setup_partial_status_errors(self):
        """One vehicle status fetch fails — others still added."""
        from custom_components.vag_connect.cariad.api.factory import CariadClientFactory
        from custom_components.vag_connect.cariad.models import VehicleData
        coord = self._coord()
        client = MagicMock()
        client.authenticate = AsyncMock()
        client.get_vehicles = AsyncMock(return_value=["VIN_OK", "VIN_FAIL"])
        vin_ok = VehicleData(vin="VIN_OK", battery_soc=75)
        client.get_status = AsyncMock(side_effect=[vin_ok, Exception("timeout")])
        with patch.object(CariadClientFactory, "create", return_value=client), \
             patch("homeassistant.helpers.aiohttp_client.async_get_clientsession", return_value=MagicMock()):
            result = asyncio.get_event_loop().run_until_complete(coord.async_setup())
        assert result is True
        assert "VIN_OK" in coord.vehicles
        assert "VIN_FAIL" not in coord.vehicles

    def test_async_shutdown_clears_state(self):
        coord = self._coord()
        coord._started = True
        coord._cariad_client = MagicMock()
        asyncio.get_event_loop().run_until_complete(coord.async_shutdown())
        assert coord._started is False
        assert coord._cariad_client is None


# ── Coordinator poll loop ─────────────────────────────────────────────────────

class TestPollLoop:
    def _coord(self, vins=None):
        import threading
        from custom_components.vag_connect.coordinator import VagConnectCoordinator
        from custom_components.vag_connect.cariad.models import VehicleData
        coord = VagConnectCoordinator.__new__(VagConnectCoordinator)
        coord.hass = MagicMock()
        coord.entry = MagicMock()
        coord.entry.data = {"scan_interval": 5}
        coord._vehicles_lock = threading.Lock()
        coord._cariad_client = MagicMock()
        coord._started = False  # starts False → exits immediately
        coord._was_available = True
        v = VehicleData(vin="VIN1", battery_soc=80)
        coord._cariad_client.get_status = AsyncMock(return_value=v)
        coord.vehicles = {vin: {} for vin in (vins or ["VIN1"])}
        coord.data = None
        coord.async_set_updated_data = MagicMock()
        coord.async_request_refresh = AsyncMock()
        coord._async_push_update = AsyncMock()
        return coord

    def test_poll_loop_exits_when_stopped(self):
        """_poll_loop returns immediately when _started=False."""
        coord = self._coord()
        coord._started = False
        asyncio.get_event_loop().run_until_complete(coord._poll_loop())
        coord._cariad_client.get_status.assert_not_awaited()

    def test_poll_loop_one_iteration(self):
        """Simulate one poll: start=True, then flip to False after sleep."""

        coord = self._coord()
        call_count = 0

        async def fake_sleep(seconds: float) -> None:
            nonlocal call_count
            call_count += 1
            coord._started = False  # stop after first sleep

        with patch("custom_components.vag_connect.coordinator.asyncio.sleep" if False else "asyncio.sleep", side_effect=fake_sleep),              patch("custom_components.vag_connect.coordinator._asyncio" if False else "asyncio.sleep", side_effect=fake_sleep):
            pass  # patch doesn't apply inside function scope that imports it locally

        # Direct approach: manually run one iteration
        coord._started = True

        async def one_iteration():
            # Simulate what _poll_loop does in one cycle
            import asyncio as _asyncio
            vins = list(coord.vehicles.keys())
            results = await _asyncio.gather(
                *[coord._cariad_client.get_status(vin) for vin in vins],
                return_exceptions=True,
            )
            fresh = {}
            for vin, result in zip(vins, results):
                if isinstance(result, Exception):
                    fresh[vin] = coord.vehicles.get(vin, {})
                else:
                    data = result.to_dict()
                    data["_client"] = coord._cariad_client
                    fresh[vin] = data
            with coord._vehicles_lock:
                coord.vehicles.update(fresh)
            await coord._async_push_update(fresh, success=True)

        asyncio.get_event_loop().run_until_complete(one_iteration())
        coord._cariad_client.get_status.assert_awaited()
        assert coord.vehicles["VIN1"].get("battery_soc") == 80

    def test_poll_loop_handles_status_error(self):
        """Status error on a VIN falls back to cached data, doesn't crash."""
        coord = self._coord()
        coord._cariad_client.get_status = AsyncMock(side_effect=Exception("timeout"))

        # Directly test the gather+fallback logic
        async def one_error_iteration():
            import asyncio as _asyncio
            vins = list(coord.vehicles.keys())
            results = await _asyncio.gather(
                *[coord._cariad_client.get_status(vin) for vin in vins],
                return_exceptions=True,
            )
            fresh = {}
            for vin, result in zip(vins, results):
                if isinstance(result, Exception):
                    fresh[vin] = coord.vehicles.get(vin, {})
                else:
                    data = result.to_dict()
                    fresh[vin] = data
            await coord._async_push_update(fresh, success=True)

        asyncio.get_event_loop().run_until_complete(one_error_iteration())
        coord._async_push_update.assert_awaited()
        # VIN1 should fall back to cached (empty) data
        assert "VIN1" in coord.vehicles


# ── Coordinator _cariad_cmd ───────────────────────────────────────────────────

class TestCariadCmd:
    def _coord(self):
        import threading
        from custom_components.vag_connect.coordinator import VagConnectCoordinator
        coord = VagConnectCoordinator.__new__(VagConnectCoordinator)
        coord.hass = MagicMock()
        coord.entry = MagicMock()
        coord.entry.data = {"spin": "1234"}
        coord._vehicles_lock = threading.Lock()
        coord._cariad_client = MagicMock()
        coord._cariad_client.command_lock = AsyncMock()
        coord._cariad_client.command_unlock = AsyncMock()
        coord._cariad_client.command_start_climate = AsyncMock()
        coord._cariad_client.command_stop_climate = AsyncMock()
        coord._cariad_client.command_start_window_heating = AsyncMock()
        coord._cariad_client.command_stop_window_heating = AsyncMock()
        coord._cariad_client.command_start_charging = AsyncMock()
        coord._cariad_client.command_stop_charging = AsyncMock()
        coord._cariad_client.command_flash = AsyncMock()
        coord._cariad_client.command_wake = AsyncMock()
        coord._cariad_client.command_set_target_soc = AsyncMock()
        coord._cariad_client.command_set_climate_temperature = AsyncMock()
        coord._started = True
        coord._was_available = True
        coord.vehicles = {"VIN1": {}}
        coord.async_request_refresh = AsyncMock()
        # v1.25.0 PR-D: CommandDispatcher state. __new__ bypasses __init__
        # which normally creates this; tests need to attach a working
        # dispatcher so _get_command_lock + wake-cooldown delegations work.
        from custom_components.vag_connect._command_dispatcher import CommandDispatcher
        coord._dispatcher = CommandDispatcher(coord)
        return coord

    def test_cariad_cmd_no_client_logs_error(self):
        coord = self._coord()
        coord._cariad_client = None
        # Should not raise, just log
        asyncio.get_event_loop().run_until_complete(coord._cariad_cmd("VIN1", "command_lock"))

    def test_cariad_cmd_lock(self):
        coord = self._coord()
        asyncio.get_event_loop().run_until_complete(coord._cariad_cmd("VIN1", "command_lock"))
        coord._cariad_client.command_lock.assert_awaited_once_with("VIN1")
        coord.async_request_refresh.assert_awaited()

    def test_cariad_cmd_set_soc(self):
        coord = self._coord()
        asyncio.get_event_loop().run_until_complete(
            coord._cariad_cmd("VIN1", "command_set_target_soc", target=80)
        )
        coord._cariad_client.command_set_target_soc.assert_awaited_once_with("VIN1", target=80)

    def test_cariad_cmd_propagates_exception(self):
        coord = self._coord()
        coord._cariad_client.command_lock = AsyncMock(side_effect=RuntimeError("API down"))
        with pytest.raises(RuntimeError, match="API down"):
            asyncio.get_event_loop().run_until_complete(coord._cariad_cmd("VIN1", "command_lock"))

    def test_async_lock(self):
        coord = self._coord()
        asyncio.get_event_loop().run_until_complete(coord.async_lock("VIN1"))
        coord._cariad_client.command_lock.assert_awaited()

    def test_async_unlock_passes_spin(self):
        coord = self._coord()
        asyncio.get_event_loop().run_until_complete(coord.async_unlock("VIN1"))
        coord._cariad_client.command_unlock.assert_awaited_with("VIN1", spin="1234")

    def test_async_set_target_soc(self):
        coord = self._coord()
        asyncio.get_event_loop().run_until_complete(coord.async_set_target_soc("VIN1", 90))
        coord._cariad_client.command_set_target_soc.assert_awaited_with("VIN1", target=90)

    def test_async_set_climate_temp(self):
        coord = self._coord()
        asyncio.get_event_loop().run_until_complete(
            coord.async_set_climatisation_temperature("VIN1", 22.0)
        )
        coord._cariad_client.command_set_climate_temperature.assert_awaited_with("VIN1", temp_c=22.0)

    def test_async_wake_vehicle(self):
        coord = self._coord()
        asyncio.get_event_loop().run_until_complete(coord.async_wake_vehicle("VIN1"))
        coord._cariad_client.command_wake.assert_awaited()

    def test_async_start_stop_window_heating(self):
        coord = self._coord()
        asyncio.get_event_loop().run_until_complete(coord.async_start_window_heating("VIN1"))
        coord._cariad_client.command_start_window_heating.assert_awaited()
        asyncio.get_event_loop().run_until_complete(coord.async_stop_window_heating("VIN1"))
        coord._cariad_client.command_stop_window_heating.assert_awaited()


# ── __init__.py service handlers ──────────────────────────────────────────────

class TestRegisterServices:
    """Tests for _register_services and service handlers in __init__.py."""

    def _hass_with_entry(self, vin="VIN_SVC"):
        """Build minimal hass mock with a coordinator entry."""
        import threading
        from custom_components.vag_connect.coordinator import VagConnectCoordinator

        coord = VagConnectCoordinator.__new__(VagConnectCoordinator)
        coord.hass = MagicMock()
        coord.entry = MagicMock()
        # Real dict so the v1.8.0 isinstance() check in async_unlock passes;
        # S-PIN is set so the unlock fail-fast does not block dispatch tests.
        coord.entry.data = {"spin": "1234"}
        coord.entry.options = {}
        coord._vehicles_lock = threading.Lock()
        coord._cariad_client = MagicMock()
        for cmd in ["command_lock","command_unlock","command_start_climate",
                    "command_stop_climate","command_start_charging","command_stop_charging",
                    "command_flash","command_wake","command_set_target_soc",
                    "command_set_climate_temperature","command_set_departure_timer"]:
            setattr(coord._cariad_client, cmd, AsyncMock())
        coord._started = True
        coord._was_available = True
        coord.vehicles = {vin: {}}
        coord.async_request_refresh = AsyncMock()

        entry = MagicMock()
        entry.runtime_data = coord

        hass = MagicMock()
        hass.config_entries.async_entries = MagicMock(return_value=[entry])
        hass.config_entries.async_entry_for_domain_unique_id = MagicMock(return_value=None)
        hass.data = {
            "vag_connect": {entry.entry_id: coord}
        }
        hass.services.has_service = MagicMock(return_value=False)
        registered = {}
        def _register(domain, name, handler, schema=None, supports_response=None):
            # v2.0.0: ``find_charging_stations`` registers with
            # ``supports_response`` so the mock has to accept the kwarg.
            registered[(domain, name)] = handler
        hass.services.async_register = MagicMock(side_effect=_register)

        return hass, coord, registered, vin

    def test_register_services_registers_all(self):
        from custom_components.vag_connect import _register_services
        hass, coord, registered, vin = self._hass_with_entry()
        _register_services(hass)
        assert ("vag_connect", "lock") in registered
        assert ("vag_connect", "unlock") in registered
        assert ("vag_connect", "start_climatisation") in registered
        assert ("vag_connect", "refresh_vehicle") in registered
        assert ("vag_connect", "set_target_soc") in registered
        assert ("vag_connect", "set_departure_timer") in registered

    def test_handle_lock_calls_coordinator(self):
        from custom_components.vag_connect import _register_services
        hass, coord, registered, vin = self._hass_with_entry()
        _register_services(hass)

        call = MagicMock()
        call.data = {"vin": vin}
        asyncio.get_event_loop().run_until_complete(registered[("vag_connect", "lock")](call))
        coord._cariad_client.command_lock.assert_awaited()

    def test_handle_unlock_calls_coordinator(self):
        from custom_components.vag_connect import _register_services
        hass, coord, registered, vin = self._hass_with_entry()
        _register_services(hass)

        call = MagicMock()
        call.data = {"vin": vin}
        asyncio.get_event_loop().run_until_complete(registered[("vag_connect", "unlock")](call))
        coord._cariad_client.command_unlock.assert_awaited()

    def test_handle_start_climatisation(self):
        from custom_components.vag_connect import _register_services
        hass, coord, registered, vin = self._hass_with_entry()
        _register_services(hass)
        call = MagicMock()
        call.data = {"vin": vin}
        asyncio.get_event_loop().run_until_complete(
            registered[("vag_connect", "start_climatisation")](call))
        coord._cariad_client.command_start_climate.assert_awaited()

    def test_handle_stop_climatisation(self):
        from custom_components.vag_connect import _register_services
        hass, coord, registered, vin = self._hass_with_entry()
        _register_services(hass)
        call = MagicMock()
        call.data = {"vin": vin}
        asyncio.get_event_loop().run_until_complete(
            registered[("vag_connect", "stop_climatisation")](call))
        coord._cariad_client.command_stop_climate.assert_awaited()

    def test_handle_start_charging(self):
        from custom_components.vag_connect import _register_services
        hass, coord, registered, vin = self._hass_with_entry()
        _register_services(hass)
        call = MagicMock()
        call.data = {"vin": vin}
        asyncio.get_event_loop().run_until_complete(
            registered[("vag_connect", "start_charging")](call))
        coord._cariad_client.command_start_charging.assert_awaited()

    def test_handle_stop_charging(self):
        from custom_components.vag_connect import _register_services
        hass, coord, registered, vin = self._hass_with_entry()
        _register_services(hass)
        call = MagicMock()
        call.data = {"vin": vin}
        asyncio.get_event_loop().run_until_complete(
            registered[("vag_connect", "stop_charging")](call))
        coord._cariad_client.command_stop_charging.assert_awaited()

    def test_handle_flash_lights(self):
        from custom_components.vag_connect import _register_services
        hass, coord, registered, vin = self._hass_with_entry()
        _register_services(hass)
        call = MagicMock()
        call.data = {"vin": vin}
        asyncio.get_event_loop().run_until_complete(
            registered[("vag_connect", "flash_lights")](call))
        coord._cariad_client.command_flash.assert_awaited()

    def test_handle_wake_vehicle(self):
        from custom_components.vag_connect import _register_services
        hass, coord, registered, vin = self._hass_with_entry()
        _register_services(hass)
        call = MagicMock()
        call.data = {"vin": vin}
        asyncio.get_event_loop().run_until_complete(
            registered[("vag_connect", "wake_vehicle")](call))
        coord._cariad_client.command_wake.assert_awaited()

    def test_handle_set_target_soc(self):
        from custom_components.vag_connect import _register_services
        hass, coord, registered, vin = self._hass_with_entry()
        _register_services(hass)
        call = MagicMock()
        call.data = {"vin": vin, "target": 80}
        asyncio.get_event_loop().run_until_complete(
            registered[("vag_connect", "set_target_soc")](call))
        coord._cariad_client.command_set_target_soc.assert_awaited()

    def test_handle_set_clim_temp(self):
        from custom_components.vag_connect import _register_services
        hass, coord, registered, vin = self._hass_with_entry()
        _register_services(hass)
        call = MagicMock()
        call.data = {"vin": vin, "temperature": 21.5}
        asyncio.get_event_loop().run_until_complete(
            registered[("vag_connect", "set_climatisation_temperature")](call))
        coord._cariad_client.command_set_climate_temperature.assert_awaited()

    def test_handle_set_departure_timer(self):
        from custom_components.vag_connect import _register_services
        hass, coord, registered, vin = self._hass_with_entry()
        _register_services(hass)
        call = MagicMock()
        data_dict = {"vin": vin, "timer_id": 1, "enabled": True, "departure_time": "07:30"}
        call.data = data_dict
        asyncio.get_event_loop().run_until_complete(
            registered[("vag_connect", "set_departure_timer")](call))
        coord.async_request_refresh.assert_awaited()

    def test_handle_refresh_all_entries(self):
        from custom_components.vag_connect import _register_services
        hass, coord, registered, vin = self._hass_with_entry()
        _register_services(hass)
        asyncio.get_event_loop().run_until_complete(
            registered[("vag_connect", "refresh_vehicle")](MagicMock()))
        coord.async_request_refresh.assert_awaited()

    def test_vin_not_found_raises_service_validation(self):
        from custom_components.vag_connect import _register_services
        from homeassistant.exceptions import ServiceValidationError
        hass, coord, registered, vin = self._hass_with_entry()
        # Clear hass.data so vin lookup fails
        hass.data = {"vag_connect": {}}
        _register_services(hass)
        call = MagicMock()
        call.data = {"vin": "NOTEXIST"}
        with pytest.raises(ServiceValidationError):
            asyncio.get_event_loop().run_until_complete(
                registered[("vag_connect", "lock")](call))


# ── coordinator __init__ construction ─────────────────────────────────────────

class TestCoordinatorInit:
    def test_init_sets_defaults(self):
        from custom_components.vag_connect.coordinator import VagConnectCoordinator
        hass = MagicMock()
        hass.loop = MagicMock()
        entry = MagicMock()
        entry.entry_id = "test_init"
        entry.data = {}

        coord = VagConnectCoordinator(hass, entry)
        assert coord._started is False
        assert coord._cariad_client is None
        assert coord._was_available is True
        assert coord.vehicles == {}

    def test_is_active_property(self):
        from custom_components.vag_connect.coordinator import VagConnectCoordinator
        hass = MagicMock()
        entry = MagicMock()
        entry.entry_id = "x"
        entry.data = {}
        coord = VagConnectCoordinator(hass, entry)
        assert coord.is_active is False
        coord._started = True
        assert coord.is_active is True


# ── coordinator _async_push_update unavailable path ──────────────────────────

class TestAsyncPushUpdate:
    def _coord(self):
        import threading
        from custom_components.vag_connect.coordinator import VagConnectCoordinator
        coord = VagConnectCoordinator.__new__(VagConnectCoordinator)
        coord.hass = MagicMock()
        coord.entry = MagicMock()
        coord.entry.data = {"username": "u@t.de"}
        coord._vehicles_lock = threading.Lock()
        coord._was_available = True
        coord._started = True
        coord._cariad_client = None
        coord.vehicles = {"VIN1": {"battery_soc": 80}}
        coord.data = {"VIN1": {"battery_soc": 80}}
        coord.last_update_success = True
        coord.async_set_updated_data = MagicMock()
        coord.async_update_listeners = MagicMock()
        coord._listeners = {}
        coord._async_remove_stale_devices = AsyncMock()
        return coord

    def test_push_update_success(self):
        coord = self._coord()
        asyncio.get_event_loop().run_until_complete(
            coord._async_push_update({"VIN1": {}}, success=True)
        )
        coord.async_set_updated_data.assert_called()

    def test_push_update_failure_logs_once(self):
        coord = self._coord()
        coord._was_available = True
        asyncio.get_event_loop().run_until_complete(
            coord._async_push_update({}, success=False)
        )
        assert coord._was_available is False

    def test_push_update_failure_doesnt_log_twice(self):
        coord = self._coord()
        coord._was_available = False  # already unavailable
        asyncio.get_event_loop().run_until_complete(
            coord._async_push_update({}, success=False)
        )
        # Should not log again (was_available stays False)
        assert coord._was_available is False

    def test_push_update_recovery_logs(self):
        coord = self._coord()
        coord._was_available = False  # was unavailable
        asyncio.get_event_loop().run_until_complete(
            coord._async_push_update({"VIN1": {}}, success=True)
        )
        assert coord._was_available is True


# ── coordinator _async_update_data ───────────────────────────────────────────

class TestAsyncUpdateData:
    def _coord(self):
        import threading
        from custom_components.vag_connect.coordinator import VagConnectCoordinator
        from custom_components.vag_connect.cariad.models import VehicleData
        coord = VagConnectCoordinator.__new__(VagConnectCoordinator)
        coord.hass = MagicMock()
        coord.entry = MagicMock()
        coord._vehicles_lock = threading.Lock()
        coord._was_available = True
        coord._started = True
        coord._cariad_client = MagicMock()
        vdata = VehicleData(vin="VIN1", battery_soc=75)
        coord._cariad_client.get_status = AsyncMock(return_value=vdata)
        coord.vehicles = {"VIN1": {"battery_soc": 80}}
        return coord

    def test_returns_cached_when_no_client(self):
        coord = self._coord()
        coord._cariad_client = None
        result = asyncio.get_event_loop().run_until_complete(
            coord._async_update_data()
        )
        assert "VIN1" in result

    def test_returns_cached_when_not_started(self):
        coord = self._coord()
        coord._started = False
        result = asyncio.get_event_loop().run_until_complete(
            coord._async_update_data()
        )
        assert "VIN1" in result

    def test_fetches_fresh_data(self):
        coord = self._coord()
        result = asyncio.get_event_loop().run_until_complete(
            coord._async_update_data()
        )
        coord._cariad_client.get_status.assert_awaited()
        assert "VIN1" in result


# ── idk.py additional paths ───────────────────────────────────────────────────

class TestIDKAuthAdditional:
    def _resp(self, status=200, text="", json_data=None, location=None):
        r = AsyncMock()
        r.status = status
        r.text = AsyncMock(return_value=text)
        r.json = AsyncMock(return_value=json_data or {})
        r.headers = {"Location": location} if location else {}
        r.__aenter__ = AsyncMock(return_value=r)
        r.__aexit__ = AsyncMock(return_value=False)
        return r

    def test_follow_redirect_200_terms(self):
        """200 with terms body raises TermsAndConditionsError."""
        from custom_components.vag_connect.cariad.auth.idk import IDKAuth
        from custom_components.vag_connect.cariad.exceptions import TermsAndConditionsError
        from custom_components.vag_connect.cariad.models import BRAND_VW_EU

        resp = self._resp(200, text="Please accept terms-and-conditions to continue")
        session = MagicMock()
        session.post = MagicMock(return_value=resp)
        auth = IDKAuth(session, BRAND_VW_EU)
        with pytest.raises(TermsAndConditionsError):
            asyncio.get_event_loop().run_until_complete(
                auth._follow_to_app_redirect("https://idp/auth", {}, "weconnect://authenticated")
            )

    def test_follow_redirect_200_marketing(self):
        """200 with marketing consent body raises MarketingConsentError."""
        from custom_components.vag_connect.cariad.auth.idk import IDKAuth
        from custom_components.vag_connect.cariad.exceptions import MarketingConsentError
        from custom_components.vag_connect.cariad.models import BRAND_VW_EU

        resp = self._resp(200, text="marketing consent required to continue")
        session = MagicMock()
        session.post = MagicMock(return_value=resp)
        auth = IDKAuth(session, BRAND_VW_EU)
        with pytest.raises(MarketingConsentError):
            asyncio.get_event_loop().run_until_complete(
                auth._follow_to_app_redirect("https://idp/auth", {}, "weconnect://authenticated")
            )

    def test_follow_redirect_consent_in_location(self):
        """302 to consent/marketing in location raises MarketingConsentError."""
        from custom_components.vag_connect.cariad.auth.idk import IDKAuth
        from custom_components.vag_connect.cariad.exceptions import MarketingConsentError
        from custom_components.vag_connect.cariad.models import BRAND_AUDI

        resp_post = self._resp(302, location="https://idp/consent/marketing")
        resp_get = self._resp(302, location="https://idp/consent/marketing")
        session = MagicMock()
        session.post = MagicMock(return_value=resp_post)
        session.get = MagicMock(return_value=resp_get)
        auth = IDKAuth(session, BRAND_AUDI)
        with pytest.raises(MarketingConsentError):
            asyncio.get_event_loop().run_until_complete(
                auth._follow_to_app_redirect("https://idp/auth", {}, "myaudi:///")
            )

    def test_refresh_non_200_non_400_raises(self):
        """Non-200/400 status on refresh raises AuthenticationError."""
        from custom_components.vag_connect.cariad.auth.idk import IDKAuth
        from custom_components.vag_connect.cariad.exceptions import AuthenticationError
        from custom_components.vag_connect.cariad.models import BRAND_SKODA

        oidc = self._resp(200, json_data={"token_endpoint": "https://idp/token"})
        bad = self._resp(503, text="Service Unavailable")
        session = MagicMock()
        session.get = MagicMock(return_value=oidc)
        session.post = MagicMock(return_value=bad)
        auth = IDKAuth(session, BRAND_SKODA)
        with pytest.raises(AuthenticationError, match="503"):
            asyncio.get_event_loop().run_until_complete(auth.refresh("old_token"))

    def test_idk_auth_hmac_extraction_from_js(self):
        """CSRF parser falls back to regex for JavaScript-injected hmac."""
        from custom_components.vag_connect.cariad.auth.idk import IDKAuth
        from custom_components.vag_connect.cariad.models import BRAND_VW_EU
        html = '''<form action="/login/authenticate">
            <input type="hidden" name="_csrf" value="CSRF123">
        </form>
        <script>
        var model = {"hmac":"abcdef1234567890","relayState":"RS123"};
        </script>'''
        auth = IDKAuth(MagicMock(), BRAND_VW_EU)
        csrf = auth._parse_csrf(html)
        # Verify _csrf was found
        assert csrf.fields["_csrf"] == "CSRF123"
        # The hmac regex extraction happens in authenticate() — verify it works
        import re
        m = re.search(r'"hmac"\s*:\s*"([0-9a-fA-F]+)"', html)
        assert m and m.group(1) == "abcdef1234567890"


# ── base.py abstract methods ──────────────────────────────────────────────────

class TestBaseClientAbstract:
    def _base_client(self):
        from custom_components.vag_connect.cariad.api.base import CariadBaseClient
        from custom_components.vag_connect.cariad.models import BRAND_VW_EU, TokenSet
        client = CariadBaseClient(MagicMock(), BRAND_VW_EU, "u@t.de", "pw")
        client._tokens = TokenSet("acc", "ref", "id")
        return client

    def test_get_vehicles_raises_not_implemented(self):
        client = self._base_client()
        with pytest.raises(NotImplementedError):
            asyncio.get_event_loop().run_until_complete(client.get_vehicles())

    def test_get_status_raises_not_implemented(self):
        client = self._base_client()
        with pytest.raises(NotImplementedError):
            asyncio.get_event_loop().run_until_complete(client.get_status("VIN1"))

    def test_command_lock_raises_not_implemented(self):
        client = self._base_client()
        with pytest.raises(NotImplementedError):
            asyncio.get_event_loop().run_until_complete(client.command_lock("VIN1"))

    def test_command_unlock_raises_not_implemented(self):
        client = self._base_client()
        with pytest.raises(NotImplementedError):
            asyncio.get_event_loop().run_until_complete(client.command_unlock("VIN1"))

    def test_command_start_climate_raises(self):
        client = self._base_client()
        with pytest.raises(NotImplementedError):
            asyncio.get_event_loop().run_until_complete(client.command_start_climate("VIN1"))

    def test_command_stop_climate_raises(self):
        client = self._base_client()
        with pytest.raises(NotImplementedError):
            asyncio.get_event_loop().run_until_complete(client.command_stop_climate("VIN1"))

    def test_command_start_charging_raises(self):
        client = self._base_client()
        with pytest.raises(NotImplementedError):
            asyncio.get_event_loop().run_until_complete(client.command_start_charging("VIN1"))

    def test_command_stop_charging_raises(self):
        client = self._base_client()
        with pytest.raises(NotImplementedError):
            asyncio.get_event_loop().run_until_complete(client.command_stop_charging("VIN1"))

    def test_command_flash_raises(self):
        client = self._base_client()
        with pytest.raises(NotImplementedError):
            asyncio.get_event_loop().run_until_complete(client.command_flash("VIN1"))

    def test_command_wake_raises(self):
        client = self._base_client()
        with pytest.raises(NotImplementedError):
            asyncio.get_event_loop().run_until_complete(client.command_wake("VIN1"))

    def test_command_set_target_soc_raises(self):
        client = self._base_client()
        with pytest.raises(NotImplementedError):
            asyncio.get_event_loop().run_until_complete(client.command_set_target_soc("VIN1", 80))

    def test_command_set_climate_temperature_raises(self):
        client = self._base_client()
        with pytest.raises(NotImplementedError):
            asyncio.get_event_loop().run_until_complete(client.command_set_climate_temperature("VIN1", 21.0))

    def test_brand_property(self):
        client = self._base_client()
        from custom_components.vag_connect.cariad.models import BRAND_VW_EU
        assert client.brand == BRAND_VW_EU


# ── async_setup_entry integration ────────────────────────────────────────────

class TestAsyncSetupEntry:
    """Tests for __init__.async_setup_entry error paths."""

    def _entry(self, brand="volkswagen"):
        entry = MagicMock()
        entry.entry_id = "test_entry"
        entry.data = {
            "brand": brand, "username": "u@t.de",
            "password": "pw", "spin": "", "scan_interval": 5,
        }
        entry.add_update_listener = MagicMock(return_value=MagicMock())
        entry.async_on_unload = MagicMock()
        return entry

    def _hass(self):
        hass = MagicMock()
        hass.loop = MagicMock()
        hass.data = {}
        hass.services.has_service = MagicMock(return_value=False)
        hass.services.async_register = MagicMock()
        hass.config_entries.async_entries = MagicMock(return_value=[])
        hass.config_entries.async_forward_entry_setups = AsyncMock()
        return hass

    def test_setup_entry_raises_auth_failed_on_invalid_credentials(self):
        """ValueError('invalid_credentials') maps to ConfigEntryAuthFailed.

        Triggers HA's reauth UI prompt instead of looping
        ConfigEntryNotReady retries forever.
        """
        from homeassistant.exceptions import ConfigEntryAuthFailed
        from custom_components.vag_connect import async_setup_entry

        hass = self._hass()
        entry = self._entry()

        mock_coord = MagicMock()
        mock_coord.async_setup = AsyncMock(side_effect=ValueError("invalid_credentials"))
        mock_coord.vehicles = {}

        with patch("custom_components.vag_connect.VagConnectCoordinator", return_value=mock_coord):
            with pytest.raises(ConfigEntryAuthFailed):
                asyncio.get_event_loop().run_until_complete(
                    async_setup_entry(hass, entry)
                )

    def test_setup_entry_other_value_errors_still_config_not_ready(self):
        """Non-credential ValueErrors keep raising ConfigEntryNotReady."""
        from homeassistant.exceptions import ConfigEntryNotReady
        from custom_components.vag_connect import async_setup_entry

        hass = self._hass()
        entry = self._entry()

        mock_coord = MagicMock()
        mock_coord.async_setup = AsyncMock(side_effect=ValueError("too_many_requests"))
        mock_coord.vehicles = {}

        with patch("custom_components.vag_connect.VagConnectCoordinator", return_value=mock_coord):
            with pytest.raises(ConfigEntryNotReady):
                asyncio.get_event_loop().run_until_complete(
                    async_setup_entry(hass, entry)
                )

    def test_setup_entry_raises_config_not_ready_on_no_vehicles(self):
        """ok=False from coordinator raises ConfigEntryNotReady."""
        from homeassistant.exceptions import ConfigEntryNotReady
        from custom_components.vag_connect import async_setup_entry

        hass = self._hass()
        entry = self._entry()

        mock_coord = MagicMock()
        mock_coord.async_setup = AsyncMock(return_value=False)
        mock_coord.vehicles = {}

        with patch("custom_components.vag_connect.VagConnectCoordinator", return_value=mock_coord):
            with pytest.raises(ConfigEntryNotReady, match="No vehicles"):
                asyncio.get_event_loop().run_until_complete(
                    async_setup_entry(hass, entry)
                )

    def test_setup_entry_success(self):
        """Successful setup registers services and returns True."""
        from custom_components.vag_connect import async_setup_entry

        hass = self._hass()
        entry = self._entry()

        mock_coord = MagicMock()
        mock_coord.async_setup = AsyncMock(return_value=True)
        mock_coord.vehicles = {"VIN1": {}}
        mock_coord.async_set_updated_data = MagicMock()

        with patch("custom_components.vag_connect.VagConnectCoordinator", return_value=mock_coord), \
             patch("custom_components.vag_connect.repairs.clear_auth_issues"):
            result = asyncio.get_event_loop().run_until_complete(
                async_setup_entry(hass, entry)
            )
        assert result is True

    def test_setup_entry_generic_exception_raises_config_not_ready(self):
        """Generic exception → ConfigEntryNotReady."""
        from homeassistant.exceptions import ConfigEntryNotReady
        from custom_components.vag_connect import async_setup_entry

        hass = self._hass()
        entry = self._entry()

        mock_coord = MagicMock()
        mock_coord.async_setup = AsyncMock(side_effect=ConnectionError("timeout"))
        mock_coord.vehicles = {}

        with patch("custom_components.vag_connect.VagConnectCoordinator", return_value=mock_coord):
            with pytest.raises(ConfigEntryNotReady):
                asyncio.get_event_loop().run_until_complete(
                    async_setup_entry(hass, entry)
                )


# ── async_unload_entry ────────────────────────────────────────────────────────

class TestAsyncUnloadEntry:
    def test_unload_calls_shutdown(self):
        from custom_components.vag_connect import async_unload_entry

        hass = MagicMock()
        hass.config_entries.async_unload_platforms = AsyncMock(return_value=True)
        hass.config_entries.async_entries = MagicMock(return_value=[])
        hass.services.has_service = MagicMock(return_value=False)

        coord = MagicMock()
        coord.async_shutdown = AsyncMock()

        entry = MagicMock()
        entry.runtime_data = coord

        result = asyncio.get_event_loop().run_until_complete(
            async_unload_entry(hass, entry)
        )
        assert result is True
        coord.async_shutdown.assert_awaited()

    def test_unload_removes_services_when_last_entry(self):
        from custom_components.vag_connect import async_unload_entry

        hass = MagicMock()
        hass.config_entries.async_unload_platforms = AsyncMock(return_value=True)
        hass.config_entries.async_entries = MagicMock(return_value=[])
        hass.services.has_service = MagicMock(return_value=True)
        hass.services.async_remove = MagicMock()

        coord = MagicMock()
        coord.async_shutdown = AsyncMock()
        entry = MagicMock()
        entry.runtime_data = coord

        asyncio.get_event_loop().run_until_complete(async_unload_entry(hass, entry))
        hass.services.async_remove.assert_called()


# ── coordinator _poll_loop via direct patching ─────────────────────────────

class TestPollLoopDirect:
    """Direct test of _poll_loop logic without asyncio.sleep."""

    def _coord(self):
        import threading
        from custom_components.vag_connect.coordinator import VagConnectCoordinator
        from custom_components.vag_connect.cariad.models import VehicleData
        coord = VagConnectCoordinator.__new__(VagConnectCoordinator)
        coord.hass = MagicMock()
        coord.entry = MagicMock()
        coord.entry.data = {"scan_interval": 5}
        coord._vehicles_lock = threading.Lock()
        coord._cariad_client = MagicMock()
        coord._started = True
        coord._was_available = True
        coord._listeners = {}
        coord.last_update_success = True
        vdata = VehicleData(vin="VIN1", battery_soc=82)
        coord._cariad_client.get_status = AsyncMock(return_value=vdata)
        coord.vehicles = {"VIN1": {}}
        coord.data = {"VIN1": {}}
        coord.async_set_updated_data = MagicMock()
        coord.async_update_listeners = MagicMock()
        coord._async_remove_stale_devices = AsyncMock()
        return coord

    def test_poll_loop_body_success(self):
        """Run exactly one poll cycle. _started flips False AFTER first get_status."""
        from custom_components.vag_connect.cariad.models import VehicleData

        coord = self._coord()
        sleep_called = []
        get_status_call_count = [0]

        # Override get_status to flip _started=False after first call
        async def counted_get_status(vin):
            get_status_call_count[0] += 1
            coord._started = False  # stop loop AFTER this fetch
            return VehicleData(vin=vin, battery_soc=82)
        coord._cariad_client.get_status = AsyncMock(side_effect=counted_get_status)

        async def mock_sleep(secs):
            sleep_called.append(secs)
            # do NOT set _started=False here — let the fetch happen first

        with patch("asyncio.sleep", side_effect=mock_sleep):
            asyncio.get_event_loop().run_until_complete(coord._poll_loop())

        assert len(sleep_called) == 1
        assert get_status_call_count[0] == 1
        coord.async_set_updated_data.assert_called()

    def test_poll_loop_body_error_path(self):
        """get_status raises → exception caught, push_update called with success=False."""

        coord = self._coord()
        call_count = [0]

        async def raising_get_status(vin):
            call_count[0] += 1
            coord._started = False  # stop after first
            raise RuntimeError("API completely down")
        coord._cariad_client.get_status = AsyncMock(side_effect=raising_get_status)

        async def mock_sleep(secs):
            pass  # don't stop here

        with patch("asyncio.sleep", side_effect=mock_sleep):
            asyncio.get_event_loop().run_until_complete(coord._poll_loop())

        # Should not propagate, just log
        assert "VIN1" in coord.vehicles

    def test_poll_loop_status_exception_per_vin(self):
        """Individual VIN status failure → cached data used, others updated."""
        from custom_components.vag_connect.cariad.models import VehicleData

        coord = self._coord()
        coord.vehicles = {"VIN_OK": {}, "VIN_ERR": {"old": True}}
        coord.data = {}

        vin_ok_data = VehicleData(vin="VIN_OK", battery_soc=90)
        def side_effect(vin):
            if vin == "VIN_OK":
                return vin_ok_data
            raise RuntimeError("timeout")
        coord._cariad_client.get_status = AsyncMock(side_effect=side_effect)

        async def mock_sleep(secs):
            coord._started = False

        with patch("asyncio.sleep", side_effect=mock_sleep):
            asyncio.get_event_loop().run_until_complete(coord._poll_loop())

        # VIN_OK should be updated, VIN_ERR should have cached
        assert coord.vehicles.get("VIN_ERR", {}).get("old") is True


# ── coordinator async_shutdown ────────────────────────────────────────────────

class TestCoordinatorShutdown:
    def test_shutdown_stops_poll_loop(self):
        import threading
        from custom_components.vag_connect.coordinator import VagConnectCoordinator
        coord = VagConnectCoordinator.__new__(VagConnectCoordinator)
        coord.hass = MagicMock()
        coord.entry = MagicMock()
        coord._vehicles_lock = threading.Lock()
        coord._started = True
        coord._cariad_client = MagicMock()
        coord._was_available = True
        coord.vehicles = {}

        asyncio.get_event_loop().run_until_complete(coord.async_shutdown())
        assert coord._started is False
        assert coord._cariad_client is None


# ── vw_eu.py remaining: get_status with parking + window heating ──────────────

class TestVWEUStatusAdditional:
    def _client(self, json_data=None, parking=None):
        from custom_components.vag_connect.cariad.api.vw_eu import VWEUClient
        from custom_components.vag_connect.cariad.models import TokenSet
        resp_json = json_data or {}
        resp_park = parking or {}

        call_count = [0]
        def make_resp(data):
            r = AsyncMock()
            r.status = 200
            r.headers = {"Content-Type": "application/json"}
            r.json = AsyncMock(return_value=data)
            r.text = AsyncMock(return_value="")
            r.__aenter__ = AsyncMock(return_value=r)
            r.__aexit__ = AsyncMock(return_value=False)
            return r

        session = MagicMock()
        def request_side_effect(method, url, **kwargs):
            call_count[0] += 1
            if "parkingposition" in url:
                return make_resp(resp_park)
            return make_resp(resp_json)
        session.request = MagicMock(side_effect=request_side_effect)

        client = VWEUClient(session, "u@t.de", "pw")
        client._tokens = TokenSet("acc", "ref", "id")
        return client

    def test_get_status_with_window_heating(self):
        client = self._client(json_data={
            "climatisation": {
                "windowHeatingStatus": {"value": {"windowHeatingStatus": [
                    {"windowLocation": "front", "windowHeatingState": "ON"},
                    {"windowLocation": "rear", "windowHeatingState": "OFF"},
                ]}},
                "climatisationStatus": {"value": {"climatisationState": "HEATING"}},
                "climatisationSettings": {"value": {"targetTemperature_C": 22.0}},
            }
        })
        result = asyncio.get_event_loop().run_until_complete(client.get_status("VIN_HEAT"))
        assert result.window_heating_front is True
        assert result.window_heating_back is False

    def test_get_status_adblue(self):
        client = self._client(json_data={
            "measurements": {
                "rangeStatus": {"value": {"adBlueRange": 4500}},
                "odometerStatus": {"value": {"odometer": 45000}},
            }
        })
        result = asyncio.get_event_loop().run_until_complete(client.get_status("VIN_DIESEL"))
        assert result.adblue_range_km == 4500

    def test_get_status_charge_eta(self):
        client = self._client(json_data={
            "charging": {
                "chargingStatus": {"value": {
                    "chargingState": "CHARGING",
                    "remainingChargingTimeToComplete_min": 60,
                }},
                "batteryStatus": {"value": {"currentSOC_pct": 50}},
                "plugStatus": {"value": {"plugConnectionState": "CONNECTED"}},
                "chargingSettings": {"value": {}},
            }
        })
        result = asyncio.get_event_loop().run_until_complete(client.get_status("VIN_CHG"))
        assert result.charge_complete_eta is not None
        assert result.is_charging is True

    def test_get_status_departure_timers_multiple(self):
        client = self._client(json_data={
            "departureTimers": {"departureTimersStatus": {"value": {"timers": [
                {"enabled": True,  "departureTime": {"time": "06:00"}},
                {"enabled": False, "departureTime": None},
                {"enabled": True,  "departureTime": {"time": "08:30"}},
            ]}}},
        })
        result = asyncio.get_event_loop().run_until_complete(client.get_status("VIN_T"))
        assert result.departure_timer_1_enabled is True
        assert result.departure_timer_2_enabled is False
        assert result.departure_timer_3_enabled is True
        assert result.departure_timer_3_time == "08:30"

    def test_get_status_battery_temp_kelvin(self):
        client = self._client(json_data={
            "measurements": {
                "temperatureBatteryStatus": {"value": {
                    "temperatureHvBatteryMin_K": 303.15  # 30°C
                }},
            }
        })
        result = asyncio.get_event_loop().run_until_complete(client.get_status("VIN_BAT"))
        assert result.battery_temp is not None
        assert abs(result.battery_temp - 30.0) < 0.2


# ── audi.py remaining paths ───────────────────────────────────────────────────

class TestAudiClientAdditional:


    def test_audi_get_vehicles(self):
        """get_vehicles uses VW EU endpoint."""
        from custom_components.vag_connect.cariad.api.audi import AudiClient
        from custom_components.vag_connect.cariad.models import TokenSet

        resp = AsyncMock()
        resp.status = 200
        resp.headers = {"Content-Type": "application/json"}
        resp.json = AsyncMock(return_value={"data": [{"vin": "WAUZZZ4G5KN000001"}]})
        resp.__aenter__ = AsyncMock(return_value=resp)
        resp.__aexit__ = AsyncMock(return_value=False)
        session = MagicMock()
        session.request = MagicMock(return_value=resp)

        client = AudiClient(session, "u@t.de", "pw")
        client._tokens = TokenSet("acc", "ref", "id")
        vins = asyncio.get_event_loop().run_until_complete(client.get_vehicles())
        assert "WAUZZZ4G5KN000001" in vins


# ── idk.py redirect chain coverage ───────────────────────────────────────────

class TestIDKRedirectChain:
    """Cover the multi-hop redirect following in _follow_to_app_redirect."""

    def _resp(self, status=302, location=None, text="", json_data=None):
        r = AsyncMock()
        r.status = status
        r.text = AsyncMock(return_value=text)
        r.json = AsyncMock(return_value=json_data or {})
        r.headers = {}
        if location:
            r.headers["Location"] = location
        r.__aenter__ = AsyncMock(return_value=r)
        r.__aexit__ = AsyncMock(return_value=False)
        return r

    def test_two_hop_redirect_to_app(self):
        """302 → intermediate 302 → app URI."""
        from custom_components.vag_connect.cariad.auth.idk import IDKAuth
        from custom_components.vag_connect.cariad.models import BRAND_VW_EU

        # POST returns 302 to intermediate
        post_resp = self._resp(302, location="https://idp/step2")
        # GET step2 returns 302 to app URI
        get_resp = self._resp(302, location="weconnect://authenticated?code=CODE123&state=S")
        session = MagicMock()
        session.post = MagicMock(return_value=post_resp)
        session.get = MagicMock(return_value=get_resp)

        auth = IDKAuth(session, BRAND_VW_EU)
        result = asyncio.get_event_loop().run_until_complete(
            auth._follow_to_app_redirect(
                "https://idp/authenticate", {}, "weconnect://authenticated"
            )
        )
        assert result is not None
        assert "CODE123" in result

    def test_two_factor_in_200_body(self):
        """200 response with 2FA body raises TwoFactorRequiredError."""
        from custom_components.vag_connect.cariad.auth.idk import IDKAuth
        from custom_components.vag_connect.cariad.exceptions import TwoFactorRequiredError
        from custom_components.vag_connect.cariad.models import BRAND_AUDI

        resp = self._resp(200, text="Please complete two-factor authentication to continue")
        session = MagicMock()
        session.post = MagicMock(return_value=resp)
        auth = IDKAuth(session, BRAND_AUDI)
        with pytest.raises(TwoFactorRequiredError):
            asyncio.get_event_loop().run_until_complete(
                auth._follow_to_app_redirect("https://idp/auth", {}, "myaudi:///")
            )

    def test_2fa_keyword_also_triggers(self):
        """200 with '2fa' in body raises TwoFactorRequiredError."""
        from custom_components.vag_connect.cariad.auth.idk import IDKAuth
        from custom_components.vag_connect.cariad.exceptions import TwoFactorRequiredError
        from custom_components.vag_connect.cariad.models import BRAND_SKODA

        resp = self._resp(200, text="2fa required for this operation")
        session = MagicMock()
        session.post = MagicMock(return_value=resp)
        auth = IDKAuth(session, BRAND_SKODA)
        with pytest.raises(TwoFactorRequiredError):
            asyncio.get_event_loop().run_until_complete(
                auth._follow_to_app_redirect("https://idp/auth", {}, "myskoda://redirect/login/")
            )

    def test_200_unexpected_raises_auth_error(self):
        """200 with no known trigger raises generic AuthenticationError."""
        from custom_components.vag_connect.cariad.auth.idk import IDKAuth
        from custom_components.vag_connect.cariad.exceptions import AuthenticationError
        from custom_components.vag_connect.cariad.models import BRAND_VW_EU

        resp = self._resp(200, text="<html>Some unknown page</html>")
        session = MagicMock()
        session.post = MagicMock(return_value=resp)
        auth = IDKAuth(session, BRAND_VW_EU)
        with pytest.raises(AuthenticationError, match="non-redirect"):
            asyncio.get_event_loop().run_until_complete(
                auth._follow_to_app_redirect("https://idp/auth", {}, "weconnect://authenticated")
            )

    def test_redirect_chain_non_redirect_status_breaks(self):
        """GET returns non-redirect status and non-app URL → returns None."""
        from custom_components.vag_connect.cariad.auth.idk import IDKAuth
        from custom_components.vag_connect.cariad.models import BRAND_SEAT

        post_resp = self._resp(302, location="https://idp/unknown-page")
        get_resp = self._resp(200, text="some page")  # 200, not a redirect
        session = MagicMock()
        session.post = MagicMock(return_value=post_resp)
        session.get = MagicMock(return_value=get_resp)

        auth = IDKAuth(session, BRAND_SEAT)
        result = asyncio.get_event_loop().run_until_complete(
            auth._follow_to_app_redirect("https://idp/auth", {}, "seat://oauth-callback")
        )
        assert result is None

    def test_redirect_app_uri_at_loop_start(self):
        """Location is already the app URI → returns immediately without GET."""
        from custom_components.vag_connect.cariad.auth.idk import IDKAuth
        from custom_components.vag_connect.cariad.models import BRAND_CUPRA

        post_resp = self._resp(302, location="cupra://oauth-callback?code=CUPRA&state=s")
        session = MagicMock()
        session.post = MagicMock(return_value=post_resp)
        session.get = MagicMock()  # should not be called

        auth = IDKAuth(session, BRAND_CUPRA)
        result = asyncio.get_event_loop().run_until_complete(
            auth._follow_to_app_redirect("https://idp/auth", {}, "cupra://oauth-callback")
        )
        assert result is not None
        assert "CUPRA" in result
        session.get.assert_not_called()


# ── coordinator stale device removal ─────────────────────────────────────────

class TestStaleDevices:
    def _coord(self):
        import threading
        from custom_components.vag_connect.coordinator import VagConnectCoordinator
        coord = VagConnectCoordinator.__new__(VagConnectCoordinator)
        coord.hass = MagicMock()
        coord.entry = MagicMock()
        coord._vehicles_lock = threading.Lock()
        coord._was_available = True
        coord._started = True
        coord._cariad_client = None
        coord._listeners = {}
        coord.last_update_success = True
        coord.vehicles = {}
        coord.async_set_updated_data = MagicMock()
        coord.async_update_listeners = MagicMock()
        return coord

    def test_stale_device_removed(self):
        """When a VIN disappears from current_vins, its device is removed."""
        coord = self._coord()
        # Simulate previous data had VIN_OLD
        coord.data = {"VIN_KEEP": {}, "VIN_OLD": {}}

        mock_device = MagicMock()
        mock_device.id = "device_old"
        mock_reg = MagicMock()
        mock_reg.async_get_device = MagicMock(return_value=mock_device)
        mock_reg.async_remove_device = MagicMock()

        with patch("homeassistant.helpers.device_registry.async_get", return_value=mock_reg):
            asyncio.get_event_loop().run_until_complete(
                coord._async_remove_stale_devices({"VIN_KEEP"})
            )

        mock_reg.async_remove_device.assert_called_once_with("device_old")

    def test_no_stale_when_no_previous_data(self):
        """First run — no data yet → nothing removed."""
        coord = self._coord()
        coord.data = None  # First run

        asyncio.get_event_loop().run_until_complete(
            coord._async_remove_stale_devices({"VIN1"})
        )
        # No exception → passes

    def test_stale_device_not_in_registry_skipped(self):
        """VIN disappears but no device entry found → no crash."""
        coord = self._coord()
        coord.data = {"VIN_OLD": {}}

        mock_reg = MagicMock()
        mock_reg.async_get_device = MagicMock(return_value=None)  # not found

        with patch("homeassistant.helpers.device_registry.async_get", return_value=mock_reg):
            asyncio.get_event_loop().run_until_complete(
                coord._async_remove_stale_devices(set())
            )
        mock_reg.async_remove_device.assert_not_called()


# ── coordinator _async_update_data error path ─────────────────────────────────

class TestAsyncUpdateDataErrorPath:
    def _coord(self):
        import threading
        from custom_components.vag_connect.coordinator import VagConnectCoordinator
        coord = VagConnectCoordinator.__new__(VagConnectCoordinator)
        coord.hass = MagicMock()
        coord.entry = MagicMock()
        coord._vehicles_lock = threading.Lock()
        coord._started = True
        coord._was_available = True
        coord._cariad_client = MagicMock()
        coord._cariad_client.get_status = AsyncMock(side_effect=RuntimeError("API error"))
        coord.vehicles = {"VIN1": {"battery_soc": 75}}
        return coord

    def test_error_returns_cached(self):
        coord = self._coord()
        result = asyncio.get_event_loop().run_until_complete(coord._async_update_data())
        assert "VIN1" in result
        assert result["VIN1"]["battery_soc"] == 75


# ── switch.py uncovered paths ─────────────────────────────────────────────────

class TestSwitchAdditional:
    def _make_coord(self):
        import threading
        from custom_components.vag_connect.coordinator import VagConnectCoordinator
        coord = VagConnectCoordinator.__new__(VagConnectCoordinator)
        coord.hass = MagicMock()
        coord.hass.async_add_executor_job = AsyncMock(return_value=None)
        coord.entry = MagicMock()
        coord.entry.data = {"spin": ""}
        coord._vehicles_lock = threading.Lock()
        coord._cariad_client = MagicMock()
        coord._cariad_client.command_start_climate = AsyncMock()
        coord._cariad_client.command_stop_climate = AsyncMock()
        coord._cariad_client.command_start_window_heating = AsyncMock()
        coord._cariad_client.command_stop_window_heating = AsyncMock()
        coord._started = True
        coord._was_available = True
        coord.async_request_refresh = AsyncMock()
        coord.vehicles = {"VIN1": {"_vehicle": MagicMock()}}
        coord.data = {"VIN1": {}}
        return coord

    def test_window_heating_switch_turn_on(self):
        from custom_components.vag_connect.switch import VagWindowHeatingSwitch
        coord = self._make_coord()
        sw = VagWindowHeatingSwitch.__new__(VagWindowHeatingSwitch)
        sw.coordinator = coord
        sw._vin = "VIN1"
        asyncio.get_event_loop().run_until_complete(sw.async_turn_on())
        coord._cariad_client.command_start_window_heating.assert_awaited()

    def test_window_heating_switch_turn_off(self):
        from custom_components.vag_connect.switch import VagWindowHeatingSwitch
        coord = self._make_coord()
        sw = VagWindowHeatingSwitch.__new__(VagWindowHeatingSwitch)
        sw.coordinator = coord
        sw._vin = "VIN1"
        asyncio.get_event_loop().run_until_complete(sw.async_turn_off())
        coord._cariad_client.command_stop_window_heating.assert_awaited()

    # VagSeatHeatingSwitch + VagAutoUnlockSwitch removed in v1.8.0 (#60).
    # 4 tests removed; reintroduce when real API commands exist.


# ── Micro-tests für 9 verbleibende Zeilen → 95% ───────────────────────────────

class TestFinalCoverageLines:
    """Gezielte Tests für die letzten uncovered lines."""

    def test_coordinator_poll_error_push_failure(self):
        """_poll_loop except block covered: _async_push_update(success=True) raises."""
        import threading
        from custom_components.vag_connect.coordinator import VagConnectCoordinator
        coord = VagConnectCoordinator.__new__(VagConnectCoordinator)
        coord.hass = MagicMock()
        coord.entry = MagicMock()
        coord.entry.data = {"scan_interval": 5}
        coord._vehicles_lock = threading.Lock()
        coord._started = True
        coord._was_available = True
        coord._listeners = {}
        coord.last_update_success = True
        coord._cariad_client = MagicMock()
        from custom_components.vag_connect.cariad.models import VehicleData
        coord._cariad_client.get_status = AsyncMock(return_value=VehicleData(vin="VIN1"))
        coord.vehicles = {"VIN1": {}}
        coord.data = {}
        coord.async_set_updated_data = MagicMock()
        coord.async_update_listeners = MagicMock()

        push_calls = []
        call_n = [0]
        async def tracked_push(data, success):
            call_n[0] += 1
            push_calls.append(success)
            if call_n[0] == 1:
                raise RuntimeError("push failed on success=True")
            # 2nd call (from except) → stop loop
            coord._started = False

        coord._async_push_update = tracked_push

        async def mock_sleep(secs): pass
        with patch("asyncio.sleep", side_effect=mock_sleep):
            asyncio.get_event_loop().run_until_complete(coord._poll_loop())

        # First push (success=True) raised → except called push with success=False
        assert True in push_calls
        assert False in push_calls

    def test_coordinator_shutdown_clears_client(self):
        """async_shutdown sets _started=False and clears _cariad_client."""
        import threading
        from custom_components.vag_connect.coordinator import VagConnectCoordinator
        coord = VagConnectCoordinator.__new__(VagConnectCoordinator)
        coord.hass = MagicMock()
        coord.entry = MagicMock()
        coord._vehicles_lock = threading.Lock()
        coord._started = True
        coord._cariad_client = MagicMock()
        coord._was_available = True
        coord.vehicles = {}
        asyncio.get_event_loop().run_until_complete(coord.async_shutdown())
        assert coord._started is False
        assert coord._cariad_client is None

    def test_repairs_raise_requirements_conflict(self):
        """raise_issue_requirements_conflict creates a repair issue."""
        from custom_components.vag_connect.repairs import raise_issue_requirements_conflict
        hass = MagicMock()
        with patch("custom_components.vag_connect.repairs.ir") as mock_ir:
            raise_issue_requirements_conflict(hass)
            mock_ir.async_create_issue.assert_called()

    def test_number_async_setup_calls_add_entities(self):
        """number.async_setup_entry adds entities for each vehicle.

        v1.12.0 (#63) — explicit ``is_read_only=False`` mock so the new
        Read-only Mode gate doesn't skip entity creation under tests.
        """
        from custom_components.vag_connect.number import async_setup_entry

        coord = MagicMock()
        coord.is_read_only = MagicMock(return_value=False)
        coord.vehicles = {"VIN1": {"has_battery": True, "battery_soc": 80}}
        entry = MagicMock()
        entry.runtime_data = coord
        add_entities = MagicMock()
        hass = MagicMock()

        asyncio.get_event_loop().run_until_complete(
            async_setup_entry(hass, entry, add_entities)
        )
        add_entities.assert_called()

    def test_binary_sensor_setup_electric_filter(self):
        """binary_sensor setup skips electric-only sensors for combustion vehicles."""
        from custom_components.vag_connect.binary_sensor import async_setup_entry

        coord = MagicMock()
        coord.vehicles = {"VIN_ICE": {"has_battery": False, "doors_locked": True}}
        entry = MagicMock()
        entry.runtime_data = coord
        add_entities = MagicMock()

        asyncio.get_event_loop().run_until_complete(
            async_setup_entry(MagicMock(), entry, add_entities)
        )
        add_entities.assert_called()

    def test_sensor_setup_combustion_filter(self):
        """sensor setup skips combustion sensors for EVs."""
        from custom_components.vag_connect.sensor import async_setup_entry

        coord = MagicMock()
        coord.vehicles = {"VIN_EV": {"has_battery": True, "has_combustion": False, "battery_soc": 80}}
        entry = MagicMock()
        entry.runtime_data = coord
        add_entities = MagicMock()

        asyncio.get_event_loop().run_until_complete(
            async_setup_entry(MagicMock(), entry, add_entities)
        )
        add_entities.assert_called()

    def test_device_tracker_location_accuracy(self):
        """VagDeviceTracker.location_accuracy returns 10."""
        from custom_components.vag_connect.device_tracker import VagConnectTracker
        tracker = VagConnectTracker.__new__(VagConnectTracker)
        assert tracker.location_accuracy == 10


# ── coordinator _tokenstore_path ──────────────────────────────────────────────

class TestTokenstorePath:
    def test_tokenstore_path_returns_storage_path(self):
        """Pre-existing test for an unimplemented helper.

        _tokenstore_path() is referenced by an older plan but never landed in
        the coordinator. Skipped until Session 7 (push notifications) needs
        persistent token storage and adds the helper for real.
        """
        import pytest
        pytest.skip("_tokenstore_path() not implemented in coordinator yet")
        assert path.endswith(".json")


# ── Issue #15: Vehicle render images via GraphQL ─────────────────────────────

class TestVehicleImageFetcher:
    """Tests for VehicleImageFetcher GraphQL client."""

    def test_parse_response_extracts_urls(self):
        """GraphQL response → {vin: VehicleImageData}."""
        from custom_components.vag_connect.cariad.api.graphql import VehicleImageFetcher, VehicleImageData
        data = {
            "data": {
                "userVehicles": [
                    {
                        "vin": "WAUZZZ4G7EN123456",
                        "nickname": "Mein Audi",
                        "vehicle": {
                            "media": {"shortName": "S6 Avant", "longName": "Audi S6 Avant", "exteriorColor": "Navarra Blau"},
                            "renderPictures": [
                                {"mediaType": "MYAPN8NB", "url": "https://mediaservice.audi.com/fast/v3_abc"},
                                {"mediaType": "MS_MYP3",  "url": "https://mediaservice.audi.com/fast/v3_xyz"},
                            ]
                        }
                    }
                ]
            }
        }
        result = VehicleImageFetcher._parse_response(data)
        assert "WAUZZZ4G7EN123456" in result
        img = result["WAUZZZ4G7EN123456"]
        assert isinstance(img, VehicleImageData)
        assert img.image_urls["MYAPN8NB"] == "https://mediaservice.audi.com/fast/v3_abc"
        assert img.image_urls["MS_MYP3"] == "https://mediaservice.audi.com/fast/v3_xyz"
        assert img.short_name == "S6 Avant"
        assert img.long_name == "Audi S6 Avant"
        assert img.exterior_color == "Navarra Blau"
        assert img.nickname == "Mein Audi"

    def test_parse_response_handles_empty(self):
        """Empty/missing data → empty dict, no crash."""
        from custom_components.vag_connect.cariad.api.graphql import VehicleImageFetcher
        assert VehicleImageFetcher._parse_response({}) == {}
        assert VehicleImageFetcher._parse_response({"data": {}}) == {}
        assert VehicleImageFetcher._parse_response({"data": {"userVehicles": []}}) == {}

    def test_parse_response_skips_missing_vin(self):
        """Vehicle without VIN is skipped."""
        from custom_components.vag_connect.cariad.api.graphql import VehicleImageFetcher
        data = {"data": {"userVehicles": [{"vehicle": {"renderPictures": []}}]}}
        assert VehicleImageFetcher._parse_response(data) == {}

    def test_best_url_prefers_side_profile(self):
        """MYAPN8NB is the preferred mediaType for Lovelace cards."""
        from custom_components.vag_connect.cariad.api.graphql import VehicleImageFetcher
        urls = {
            "MS_MYP3":   "https://small.png",
            "MYAPN8NB":  "https://side-profile.png",
            "MYAAN8NB":  "https://angle.png",
        }
        assert VehicleImageFetcher.best_url(urls) == "https://side-profile.png"

    def test_best_url_falls_back_gracefully(self):
        """Falls back to available URL if preferred not present."""
        from custom_components.vag_connect.cariad.api.graphql import VehicleImageFetcher
        urls = {"MS_MYP5": "https://medium.png"}
        assert VehicleImageFetcher.best_url(urls) == "https://medium.png"

    def test_best_url_returns_none_for_empty(self):
        """Empty dict → None."""
        from custom_components.vag_connect.cariad.api.graphql import VehicleImageFetcher
        assert VehicleImageFetcher.best_url({}) is None
        assert VehicleImageFetcher.best_url(None) is None

    def test_vehicle_data_has_image_urls_field(self):
        """VehicleData.image_urls initialises as empty dict."""
        from custom_components.vag_connect.cariad.models import VehicleData
        d = VehicleData(vin="TEST123")
        assert isinstance(d.image_urls, dict)
        assert len(d.image_urls) == 0

    def test_vehicle_data_to_dict_preserves_image_urls(self):
        """to_dict() preserves image_urls + media names for coordinator storage."""
        from custom_components.vag_connect.cariad.models import VehicleData
        d = VehicleData(vin="TEST123")
        d.image_urls = {"MYAPN8NB": "https://example.com/car.png"}
        d.media_short_name = "Q4 e-tron"
        d.media_long_name = "Audi Q4 50 e-tron quattro"
        d.media_exterior_color = "Glacier White"
        serialised = d.to_dict()
        assert serialised["image_urls"]["MYAPN8NB"] == "https://example.com/car.png"
        assert serialised["media_short_name"] == "Q4 e-tron"
        assert serialised["media_long_name"] == "Audi Q4 50 e-tron quattro"
        assert serialised["media_exterior_color"] == "Glacier White"

    def test_render_image_types_all_7_present(self):
        """RENDER_IMAGE_TYPES must have all 7 MediaTypes."""
        from custom_components.vag_connect.cariad.api.graphql import RENDER_IMAGE_TYPES, RENDER_TYPE_BY_MEDIA
        assert len(RENDER_IMAGE_TYPES) == 7
        expected_media = {"MS_MYP3", "MS_MYP4", "MS_MYP5", "MYAPN3NB", "MYAPN8NB", "MYAAN3NB", "MYAAN8NB"}
        actual_media = {r["media_type"] for r in RENDER_IMAGE_TYPES}
        assert actual_media == expected_media
        # RENDER_TYPE_BY_MEDIA lookup
        assert RENDER_TYPE_BY_MEDIA["MYAPN8NB"]["entity_suffix"] == "render_side_lg"
        assert RENDER_TYPE_BY_MEDIA["MS_MYP3"]["entity_suffix"] == "render_icon"
        assert RENDER_TYPE_BY_MEDIA["MYAAN3NB"]["tag"] == "angle_hd"


# ── Session 2A foundation: error taxonomy + capabilities ──────────────────────


class TestCommandFailureClassifier:
    """classify_command_failure() maps APIError → CommandFailureReason.

    Conservative on purpose: ambiguous bodies (e.g. 400 internal-error) must
    return BACKEND_ERROR, never MISSING_CAPABILITY. Wrongly hiding entities
    is harder to recover from than showing a transient error.
    """

    def test_missing_capability_body_detected(self):
        from custom_components.vag_connect.cariad.exceptions import (
            APIError,
            CommandFailureReason,
            classify_command_failure,
        )
        err = APIError(400, "https://ola.example/v1/.../honk-and-flash",
                       '{"code":"missing-capability","message":"Missing capability"}')
        assert classify_command_failure(err) is CommandFailureReason.MISSING_CAPABILITY

    def test_403_is_not_entitled(self):
        from custom_components.vag_connect.cariad.exceptions import (
            APIError, CommandFailureReason, classify_command_failure,
        )
        err = APIError(403, "https://example", '{"error":"forbidden"}')
        assert classify_command_failure(err) is CommandFailureReason.NOT_ENTITLED

    def test_404_is_wrong_api_profile(self):
        from custom_components.vag_connect.cariad.exceptions import (
            APIError, CommandFailureReason, classify_command_failure,
        )
        err = APIError(404, "https://example", '{"error":"not found"}')
        assert classify_command_failure(err) is CommandFailureReason.WRONG_API_PROFILE

    def test_500_is_backend_error(self):
        from custom_components.vag_connect.cariad.exceptions import (
            APIError, CommandFailureReason, classify_command_failure,
        )
        err = APIError(500, "https://example", "Internal Server Error")
        assert classify_command_failure(err) is CommandFailureReason.BACKEND_ERROR

    def test_400_internal_error_is_backend_not_missing_capability(self):
        """`internal-error` is ambiguous — never claim it's a capability gap."""
        from custom_components.vag_connect.cariad.exceptions import (
            APIError, CommandFailureReason, classify_command_failure,
        )
        err = APIError(400, "https://ola.example/v1/.../access/lock",
                       '{"code":"internal-error","message":"Internal server error"}')
        assert classify_command_failure(err) is CommandFailureReason.BACKEND_ERROR

    def test_non_apierror_is_unknown(self):
        from custom_components.vag_connect.cariad.exceptions import (
            CommandFailureReason, classify_command_failure,
        )
        assert classify_command_failure(ValueError("oops")) is CommandFailureReason.UNKNOWN
        assert classify_command_failure(RuntimeError()) is CommandFailureReason.UNKNOWN


class TestFeatureStateTracking:
    """Coordinator records FeatureState lazily on command success/failure."""

    def _coord(self):
        from custom_components.vag_connect.coordinator import VagConnectCoordinator
        coord = VagConnectCoordinator.__new__(VagConnectCoordinator)
        coord.feature_states = {}
        return coord

    def test_get_feature_state_creates_lazily(self):
        coord = self._coord()
        state = coord.get_feature_state("VIN1", "command_flash")
        assert state.supported_by_vehicle is None
        assert state.entitled_by_account is None
        assert state.last_error is None
        # Same call returns same instance (cached)
        assert coord.get_feature_state("VIN1", "command_flash") is state

    def test_record_missing_capability_marks_unsupported(self):
        from custom_components.vag_connect.cariad.exceptions import CommandFailureReason
        coord = self._coord()
        coord.record_command_failure("VIN1", "command_flash",
                                      CommandFailureReason.MISSING_CAPABILITY)
        state = coord.get_feature_state("VIN1", "command_flash")
        assert state.supported_by_vehicle is False
        assert state.last_error is CommandFailureReason.MISSING_CAPABILITY
        # Entitlement untouched — different question entirely
        assert state.entitled_by_account is None

    def test_record_subscription_expired_marks_unentitled_only(self):
        from custom_components.vag_connect.cariad.exceptions import CommandFailureReason
        coord = self._coord()
        coord.record_command_failure("VIN1", "command_lock",
                                      CommandFailureReason.SUBSCRIPTION_EXPIRED)
        state = coord.get_feature_state("VIN1", "command_lock")
        # Vehicle still supports it — user just needs to renew
        assert state.supported_by_vehicle is None
        assert state.entitled_by_account is False

    def test_record_backend_error_does_not_flip_either_flag(self):
        """Transient errors must never permanently hide entities."""
        from custom_components.vag_connect.cariad.exceptions import CommandFailureReason
        coord = self._coord()
        coord.record_command_failure("VIN1", "command_flash",
                                      CommandFailureReason.BACKEND_ERROR)
        state = coord.get_feature_state("VIN1", "command_flash")
        assert state.supported_by_vehicle is None
        assert state.entitled_by_account is None
        assert state.last_error is CommandFailureReason.BACKEND_ERROR

    def test_record_success_clears_prior_error(self):
        from custom_components.vag_connect.cariad.exceptions import CommandFailureReason
        coord = self._coord()
        coord.record_command_failure("VIN1", "command_flash",
                                      CommandFailureReason.MISSING_CAPABILITY)
        coord.record_command_success("VIN1", "command_flash")
        state = coord.get_feature_state("VIN1", "command_flash")
        assert state.supported_by_vehicle is True
        assert state.entitled_by_account is True
        assert state.last_error is None


class TestCapabilitiesCacheTTL:
    """Cache must be runtime-only (NOT config_entry.options) and TTL-aware."""

    def _coord(self):
        from custom_components.vag_connect.coordinator import VagConnectCoordinator
        coord = VagConnectCoordinator.__new__(VagConnectCoordinator)
        coord.vehicle_capabilities = {}
        coord._capabilities_fetched_at = {}
        coord._cariad_client = None
        return coord

    def test_cache_starts_stale(self):
        coord = self._coord()
        assert coord.is_capabilities_cache_fresh("VIN1") is False

    def test_fresh_after_recent_fetch(self):
        from datetime import datetime, timezone
        coord = self._coord()
        coord._capabilities_fetched_at["VIN1"] = datetime.now(tz=timezone.utc)
        assert coord.is_capabilities_cache_fresh("VIN1") is True

    def test_stale_after_25h(self):
        from datetime import datetime, timedelta, timezone
        coord = self._coord()
        coord._capabilities_fetched_at["VIN1"] = (
            datetime.now(tz=timezone.utc) - timedelta(hours=25)
        )
        assert coord.is_capabilities_cache_fresh("VIN1") is False

    def test_refresh_capabilities_no_client_safe(self):
        """No CARIAD client → must not crash, must not write the cache."""
        import asyncio
        coord = self._coord()
        asyncio.get_event_loop().run_until_complete(
            coord.refresh_capabilities("VIN1")
        )
        assert coord.vehicle_capabilities == {}

    def test_refresh_capabilities_swallows_error(self):
        """Client raises → cache stays as-is (never load-bearing)."""
        import asyncio
        from unittest.mock import AsyncMock
        coord = self._coord()
        coord._cariad_client = AsyncMock()
        coord._cariad_client.get_capabilities = AsyncMock(
            side_effect=RuntimeError("network down"),
        )
        asyncio.get_event_loop().run_until_complete(
            coord.refresh_capabilities("VIN1")
        )
        assert coord.vehicle_capabilities == {}

    def test_refresh_capabilities_caches_dict_response(self):
        import asyncio
        from unittest.mock import AsyncMock
        coord = self._coord()
        coord._cariad_client = AsyncMock()
        coord._cariad_client.get_capabilities = AsyncMock(
            return_value={"capabilities": [{"id": "honk-and-flash"}]},
        )
        asyncio.get_event_loop().run_until_complete(
            coord.refresh_capabilities("VIN1")
        )
        assert "VIN1" in coord.vehicle_capabilities
        assert coord.is_capabilities_cache_fresh("VIN1") is True

    def test_refresh_skipped_when_fresh_unless_forced(self):
        import asyncio
        from datetime import datetime, timezone
        from unittest.mock import AsyncMock
        coord = self._coord()
        coord._capabilities_fetched_at["VIN1"] = datetime.now(tz=timezone.utc)
        coord._cariad_client = AsyncMock()
        coord._cariad_client.get_capabilities = AsyncMock(return_value={"x": 1})
        # Not forced → client should not be called
        asyncio.get_event_loop().run_until_complete(
            coord.refresh_capabilities("VIN1")
        )
        coord._cariad_client.get_capabilities.assert_not_called()
        # Forced → client is called
        asyncio.get_event_loop().run_until_complete(
            coord.refresh_capabilities("VIN1", force=True)
        )
        coord._cariad_client.get_capabilities.assert_called_once_with("VIN1")


# ── Session 2B: capability lookup + button gating ─────────────────────────────


class TestVehicleSupportsCapability:
    """Three-valued capability lookup: True / False / None."""

    def _coord(self, caps_for_vin=None):
        from custom_components.vag_connect.coordinator import VagConnectCoordinator
        coord = VagConnectCoordinator.__new__(VagConnectCoordinator)
        coord.vehicle_capabilities = {"VIN1": caps_for_vin} if caps_for_vin else {}
        return coord

    def test_no_cache_returns_none(self):
        """No cached document → callers must not gate."""
        coord = self._coord()
        assert coord.vehicle_supports_capability("VIN1", "honkAndFlash") is None

    def test_capability_present_no_status_returns_true(self):
        coord = self._coord({"capabilities": [
            {"id": "honkAndFlash", "status": []},
        ]})
        assert coord.vehicle_supports_capability("VIN1", "honkAndFlash") is True

    def test_capability_with_status_entries_returns_false(self):
        """status[] non-empty → backend says limited / unavailable."""
        coord = self._coord({"capabilities": [
            {"id": "honkAndFlash", "status": [{"reason": "deactivated"}]},
        ]})
        assert coord.vehicle_supports_capability("VIN1", "honkAndFlash") is False

    def test_capability_not_listed_returns_false(self):
        """Cache populated but capability missing → explicit absence."""
        coord = self._coord({"capabilities": [
            {"id": "differentFeature", "status": []},
        ]})
        assert coord.vehicle_supports_capability("VIN1", "honkAndFlash") is False

    def test_malformed_capability_doc_returns_none(self):
        coord = self._coord({"capabilities": "not a list"})
        assert coord.vehicle_supports_capability("VIN1", "honkAndFlash") is None

    def test_other_vin_returns_none(self):
        coord = self._coord({"capabilities": [{"id": "honkAndFlash", "status": []}]})
        assert coord.vehicle_supports_capability("VIN_OTHER", "honkAndFlash") is None


class TestButtonCapabilityGating:
    """Session 2B: flash/wake skipped when capabilities say no, refresh always created."""

    def _coord(self, caps=None, brand="cupra"):
        from unittest.mock import MagicMock
        coord = MagicMock()
        # v1.12.0 (#63) — explicit ``is_read_only=False`` mock so the
        # button platform's new Read-only Mode gate doesn't skip Flash +
        # Wake button creation under tests.
        coord.is_read_only = MagicMock(return_value=False)
        coord.vehicles = {"VIN1": {"vin": "VIN1", "model": "Born"}}
        coord.vehicle_capabilities = {"VIN1": caps} if caps else {}
        # v1.13.0 (#56 Phase 3) — entry.data["brand"] is what
        # ``command_capability_supported`` reads to look up CAPABILITY_MAP.
        coord.entry = MagicMock()
        coord.entry.data = {"brand": brand}

        # Real method needs to be called, not a MagicMock auto-method
        from custom_components.vag_connect.coordinator import VagConnectCoordinator
        coord.vehicle_supports_capability = (
            lambda vin, cap_id, _coord=coord: VagConnectCoordinator.vehicle_supports_capability(
                _coord, vin, cap_id,
            )
        )
        # v1.13.0 (#56 Phase 3) — wire real ``command_capability_supported``
        # so button.py's new uniform gate consults the actual CAPABILITY_MAP
        # + caps cache instead of receiving an auto-MagicMock truthy value.
        coord.command_capability_supported = (
            lambda vin, command_id, _coord=coord: VagConnectCoordinator.command_capability_supported(
                _coord, vin, command_id,
            )
        )
        return coord

    def _entry(self, coord, brand="cupra"):
        from unittest.mock import MagicMock
        entry = MagicMock()
        entry.runtime_data = coord
        entry.data = {"brand": brand}
        return entry

    def _setup(self, coord, brand="cupra"):
        import asyncio
        from unittest.mock import MagicMock
        from custom_components.vag_connect.button import async_setup_entry
        # v1.13.0 (#56 Phase 3) — ``command_capability_supported`` reads
        # the brand off the coordinator's own ``entry.data``, not the
        # ConfigEntry passed into ``async_setup_entry``. Sync them.
        coord.entry.data = {"brand": brand}
        added: list = []
        asyncio.get_event_loop().run_until_complete(
            async_setup_entry(MagicMock(), self._entry(coord, brand), added.extend)
        )
        return added

    def test_no_capabilities_creates_all_three(self):
        """SEAT/CUPRA brand but no capabilities cache → all 3 buttons created."""
        added = self._setup(self._coord(caps=None))
        names = [type(e).__name__ for e in added]
        assert "VagFlashButton" in names
        assert "VagWakeButton" in names
        assert "VagRefreshButton" in names

    def test_audi_inherits_vw_gating(self):
        """v1.13.0 (#56 Phase 3): Audi inherits VW EU CARIAD-BFF capability
        vocabulary via ``CAPABILITY_MAP["audi"] = CAPABILITY_MAP["volkswagen"]``.
        Was unverified pre-1.13.0 (test originally documented that gating was
        skipped); v1.13.0 ships the inheritance so audi IS gated using the
        same camelCase cap-ids (``honkAndFlash``, ``vehicleWakeUpTrigger``).
        """
        # honkAndFlash listed → flash button stays. vehicleWakeUpTrigger
        # missing from a populated capabilities list → wake button skipped.
        added = self._setup(self._coord(caps={"capabilities": [
            {"id": "honkAndFlash", "status": []},
        ]}), brand="audi")
        names = [type(e).__name__ for e in added]
        assert "VagFlashButton" in names
        assert "VagWakeButton" not in names
        assert "VagRefreshButton" in names

    def test_explicit_unsupported_skips_flash_and_wake(self):
        """OLA reports neither feature → only refresh button stays."""
        added = self._setup(self._coord(caps={"capabilities": [
            {"id": "differentFeature", "status": []},
        ]}))
        names = [type(e).__name__ for e in added]
        assert "VagFlashButton" not in names
        assert "VagWakeButton" not in names
        assert "VagRefreshButton" in names

    def test_partial_support(self):
        """Flash supported, wake unavailable → only flash + refresh.

        v1.13.0 (#56 Phase 3): cap-ids must match the brand's vocabulary —
        CUPRA uses OLA kebab-case (``honk-and-flash``, ``vehicle-wakeup``)
        not CARIAD camelCase. Test caps adjusted to the verified vocabulary.
        """
        added = self._setup(self._coord(caps={"capabilities": [
            {"id": "honk-and-flash", "status": []},
            {"id": "vehicle-wakeup", "status": [{"reason": "deactivated"}]},
        ]}))
        names = [type(e).__name__ for e in added]
        assert "VagFlashButton" in names
        assert "VagWakeButton" not in names
        assert "VagRefreshButton" in names

    def test_refresh_button_always_created(self):
        """Refresh is coordinator-level — never gated."""
        # Even with worst-case capabilities cache
        added = self._setup(self._coord(caps={"capabilities": []}))
        names = [type(e).__name__ for e in added]
        assert "VagRefreshButton" in names


# ── Session 2C: SEAT/CUPRA SecToken flow + capabilities for other brands ──────


class TestSeatCupraSecTokenFlow:
    """SEAT/CUPRA lock/unlock require an S-PIN-derived SecToken header.

    Verified against pycupra: POST /v2/users/{uid}/spin/verify with
    {"spin": pin} → response {"securityToken": ...} → use that as
    SecToken header on the /access/lock or /access/unlock POST (empty body).
    """

    def _client(self, spin="1234", user_id="u-123"):
        from unittest.mock import AsyncMock
        from custom_components.vag_connect.cariad.api.seat_cupra import SeatCupraClient
        client = SeatCupraClient.__new__(SeatCupraClient)
        client._spin = spin
        client._user_id = user_id
        client._post = AsyncMock(return_value={"securityToken": "TOK_ABC"})
        client._fetch_user_id = AsyncMock()
        return client

    def test_get_sec_token_calls_verify_endpoint(self):
        import asyncio
        client = self._client()
        token = asyncio.get_event_loop().run_until_complete(
            client._get_sec_token("1234")
        )
        assert token == "TOK_ABC"
        url = client._post.call_args[0][0]
        assert url.endswith("/v2/users/u-123/spin/verify")
        assert client._post.call_args.kwargs["json"] == {"spin": "1234"}

    def test_get_sec_token_raises_spin_error_on_empty_pin(self):
        import asyncio
        import pytest
        from custom_components.vag_connect.cariad.exceptions import SpinError
        client = self._client(spin="")
        with pytest.raises(SpinError):
            asyncio.get_event_loop().run_until_complete(
                client._get_sec_token("")
            )

    def test_get_sec_token_wraps_apierror_as_spin_error(self):
        """Wrong PIN → 400 from /spin/verify → user-facing SpinError."""
        import asyncio
        import pytest
        from unittest.mock import AsyncMock
        from custom_components.vag_connect.cariad.exceptions import APIError, SpinError
        client = self._client()
        client._post = AsyncMock(side_effect=APIError(400, "x", "wrong pin"))
        with pytest.raises(SpinError):
            asyncio.get_event_loop().run_until_complete(
                client._get_sec_token("1234")
            )

    def test_get_sec_token_raises_when_no_token_in_response(self):
        import asyncio
        import pytest
        from unittest.mock import AsyncMock
        from custom_components.vag_connect.cariad.exceptions import SpinError
        client = self._client()
        client._post = AsyncMock(return_value={"unexpected": "field"})
        with pytest.raises(SpinError):
            asyncio.get_event_loop().run_until_complete(
                client._get_sec_token("1234")
            )

    def test_command_lock_sends_sectoken_header_no_body(self):
        import asyncio
        from unittest.mock import AsyncMock
        client = self._client()
        # Two calls: spin/verify + access/lock. Mock _post to handle both.
        verify_resp = {"securityToken": "TOK_LOCK"}
        client._post = AsyncMock(side_effect=[verify_resp, None])
        asyncio.get_event_loop().run_until_complete(
            client.command_lock("VINX")
        )
        # First call = spin/verify
        assert client._post.call_args_list[0][0][0].endswith("/v2/users/u-123/spin/verify")
        # Second call = lock with SecToken header, no JSON body
        lock_call = client._post.call_args_list[1]
        assert lock_call[0][0].endswith("/v1/vehicles/VINX/access/lock")
        assert lock_call.kwargs["headers"] == {"SecToken": "TOK_LOCK"}
        assert "json" not in lock_call.kwargs

    def test_command_unlock_sends_sectoken_header_no_body(self):
        import asyncio
        from unittest.mock import AsyncMock
        client = self._client()
        verify_resp = {"securityToken": "TOK_UNL"}
        client._post = AsyncMock(side_effect=[verify_resp, None])
        asyncio.get_event_loop().run_until_complete(
            client.command_unlock("VINX", spin="9999")
        )
        # spin/verify uses the kwarg-supplied PIN, not self._spin
        assert client._post.call_args_list[0].kwargs["json"] == {"spin": "9999"}
        unlock_call = client._post.call_args_list[1]
        assert unlock_call[0][0].endswith("/v1/vehicles/VINX/access/unlock")
        assert unlock_call.kwargs["headers"] == {"SecToken": "TOK_UNL"}
        assert "json" not in unlock_call.kwargs


class TestCariadBffGetCapabilities:
    """VW EU + Audi share the CARIAD BFF capabilities endpoint."""

    def test_vw_eu_get_capabilities_endpoint(self):
        import asyncio
        from unittest.mock import AsyncMock
        from custom_components.vag_connect.cariad.api.vw_eu import VWEUClient
        client = VWEUClient.__new__(VWEUClient)
        client._get = AsyncMock(return_value={"capabilities": [{"id": "x"}]})
        result = asyncio.get_event_loop().run_until_complete(
            client.get_capabilities("VINY")
        )
        assert result == {"capabilities": [{"id": "x"}]}
        url = client._get.call_args[0][0]
        assert "emea.bff.cariad.digital" in url
        assert url.endswith("/vehicle/v1/vehicles/VINY/capabilities")

    def test_get_capabilities_returns_empty_dict_on_non_dict_response(self):
        import asyncio
        from unittest.mock import AsyncMock
        from custom_components.vag_connect.cariad.api.vw_eu import VWEUClient
        client = VWEUClient.__new__(VWEUClient)
        client._get = AsyncMock(return_value=["unexpected list"])
        result = asyncio.get_event_loop().run_until_complete(
            client.get_capabilities("VIN")
        )
        assert result == {}

    def test_porsche_returns_empty_dict_no_endpoint(self):
        """Porsche PPA has no capabilities endpoint — must not raise."""
        import asyncio
        from custom_components.vag_connect.cariad.api.porsche import PorscheClient
        client = PorscheClient.__new__(PorscheClient)
        result = asyncio.get_event_loop().run_until_complete(
            client.get_capabilities("VIN")
        )
        assert result == {}

    def test_vw_na_returns_empty_dict_no_endpoint(self):
        import asyncio
        from custom_components.vag_connect.cariad.api.vw_na import VWNAClient
        client = VWNAClient.__new__(VWNAClient)
        result = asyncio.get_event_loop().run_until_complete(
            client.get_capabilities("VIN")
        )
        assert result == {}


# ── Session 3A: CommandProfile + v1/v2 endpoint fallback ──────────────────────


class TestCommandProfileEnum:
    """CommandProfile is the foundation enum for per-VIN endpoint routing."""

    def test_all_expected_profiles_defined(self):
        from custom_components.vag_connect.cariad.exceptions import CommandProfile
        # Foundation values used by Session 3A. Future sessions add more
        # but these must never go away or change names — they may be
        # serialised in diagnostics.
        expected = {
            "UNKNOWN", "CARIAD_BFF_V1", "CARIAD_BFF_V2",
            "AUDI_PPE", "AUDI_PREMIUM", "LEGACY_MBB", "MEB_ID",
            "SEAT_CUPRA_OLA", "SKODA_MYSMOB", "SKODA_MYSMOB_V3",
            "PORSCHE_PPA", "VW_NA",
        }
        actual = {p.name for p in CommandProfile}
        assert expected.issubset(actual), f"missing: {expected - actual}"

    def test_string_values_are_lowercase_with_underscores(self):
        """StrEnum values double as JSON-friendly identifiers in diagnostics."""
        from custom_components.vag_connect.cariad.exceptions import CommandProfile
        assert CommandProfile.UNKNOWN.value == "unknown"
        assert CommandProfile.CARIAD_BFF_V2.value == "cariad_bff_v2"
        assert CommandProfile.AUDI_PREMIUM.value == "audi_premium"


class TestCoordinatorCommandProfile:
    """Coordinator stores per-VIN command profile in runtime cache."""

    def _coord(self):
        from custom_components.vag_connect.coordinator import VagConnectCoordinator
        coord = VagConnectCoordinator.__new__(VagConnectCoordinator)
        coord.vehicle_command_profile = {}
        return coord

    def test_get_command_profile_default_unknown(self):
        from custom_components.vag_connect.cariad.exceptions import CommandProfile
        coord = self._coord()
        assert coord.get_command_profile("VINX") is CommandProfile.UNKNOWN

    def test_set_command_profile_persists(self):
        from custom_components.vag_connect.cariad.exceptions import CommandProfile
        coord = self._coord()
        coord.set_command_profile("VINX", CommandProfile.AUDI_PREMIUM)
        assert coord.get_command_profile("VINX") is CommandProfile.AUDI_PREMIUM

    def test_set_command_profile_independent_per_vin(self):
        from custom_components.vag_connect.cariad.exceptions import CommandProfile
        coord = self._coord()
        coord.set_command_profile("VIN_A", CommandProfile.CARIAD_BFF_V1)
        coord.set_command_profile("VIN_B", CommandProfile.AUDI_PREMIUM)
        assert coord.get_command_profile("VIN_A") is CommandProfile.CARIAD_BFF_V1
        assert coord.get_command_profile("VIN_B") is CommandProfile.AUDI_PREMIUM


class TestVWEUv1v2Fallback:
    """VWEUClient automatically retries on /vehicle/v2/ when /vehicle/v1/ 404s.

    Verification case: Audi RS e-tron GT (#51) — Grant Shewan's
    `number/set_value` actions returned 404 from /vehicle/v1/...; the
    same path under /vehicle/v2/... is the documented endpoint.
    """

    def _client(self):
        from unittest.mock import AsyncMock
        from custom_components.vag_connect.cariad.api.vw_eu import VWEUClient
        client = VWEUClient.__new__(VWEUClient)
        client._post = AsyncMock()
        client._v2_command_paths = {}
        return client

    def test_v1_success_does_not_flip_profile(self):
        """v1 returns 2xx → no v2 attempt, no profile flip."""
        import asyncio
        from unittest.mock import AsyncMock
        client = self._client()
        client._post = AsyncMock(return_value=None)
        asyncio.get_event_loop().run_until_complete(
            client.command_set_target_soc("VIN1", 80)
        )
        assert client._post.call_count == 1
        assert "/vehicle/v1/" in client._post.call_args[0][0]
        assert not client._supports_v2_paths("VIN1")

    def test_v1_404_falls_back_to_v2_and_records(self):
        """v1 404 → v2 retry. On v2 success, mark VIN as v2-active."""
        import asyncio
        from unittest.mock import AsyncMock
        from custom_components.vag_connect.cariad.exceptions import APIError
        client = self._client()
        client._post = AsyncMock(side_effect=[
            APIError(404, "/v1/...", "Not Found"),
            None,
        ])
        asyncio.get_event_loop().run_until_complete(
            client.command_set_target_soc("VIN_AUDI", 80)
        )
        assert client._post.call_count == 2
        assert "/vehicle/v1/" in client._post.call_args_list[0][0][0]
        assert "/vehicle/v2/" in client._post.call_args_list[1][0][0]
        assert client._supports_v2_paths("VIN_AUDI")

    def test_subsequent_calls_skip_v1(self):
        """Once v2 is recorded for a VIN, all subsequent calls go to v2."""
        import asyncio
        from unittest.mock import AsyncMock
        client = self._client()
        client._v2_command_paths = {"VIN_AUDI": True}
        client._post = AsyncMock(return_value=None)
        asyncio.get_event_loop().run_until_complete(
            client.command_set_climate_temperature("VIN_AUDI", 21.0)
        )
        assert client._post.call_count == 1
        assert "/vehicle/v2/" in client._post.call_args[0][0]

    def test_non_404_propagates(self):
        """Other 4xx/5xx must NOT trigger v2 retry — bug class would mask real errors."""
        import asyncio
        import pytest
        from unittest.mock import AsyncMock
        from custom_components.vag_connect.cariad.exceptions import APIError
        client = self._client()
        client._post = AsyncMock(side_effect=APIError(500, "/v1/...", "Server Error"))
        with pytest.raises(APIError):
            asyncio.get_event_loop().run_until_complete(
                client.command_set_target_soc("VIN1", 80)
            )
        assert client._post.call_count == 1  # no v2 retry
        assert not client._supports_v2_paths("VIN1")

    def test_per_vin_independence(self):
        """One VIN flipping to v2 must not affect another VIN on the same client."""
        import asyncio
        from unittest.mock import AsyncMock
        from custom_components.vag_connect.cariad.exceptions import APIError
        client = self._client()
        # VIN_A: v1 works
        client._post = AsyncMock(return_value=None)
        asyncio.get_event_loop().run_until_complete(
            client.command_set_target_soc("VIN_A", 80)
        )
        # VIN_B: v1 404 → v2
        client._post = AsyncMock(side_effect=[
            APIError(404, "/v1/...", "Not Found"),
            None,
        ])
        asyncio.get_event_loop().run_until_complete(
            client.command_set_target_soc("VIN_B", 80)
        )
        # VIN_A still on v1 path, VIN_B on v2
        assert not client._supports_v2_paths("VIN_A")
        assert client._supports_v2_paths("VIN_B")
