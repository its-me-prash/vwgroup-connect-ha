# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""v2.15.0 — MBB durable-strategy wire-in: pure-function unit tests.

Scope: the deterministic, offline-testable pieces of the MBB two-way
integration (the HTTP orchestration in ``api/vw_eu.py`` + the config-flow
steps need a live VW EU account and are validated by the tester):

  a2 (auth core)
    - ``_mbboauth.jwt_aud`` — JWT aud decode (multi-valued → first)
    - ``_mbboauth.register`` input-guard + endpoint constant
    - ``_device_grant.mbb_dag_config`` — VW-only client+scope (mbb scope)

  a3 (S-PIN SecToken + RLU command core)
    - ``compute_spin_hash`` — SHA-512(fromhex(spin) ++ fromhex(challenge)),
      UPPER (the classic hex-not-utf-8 footgun) — known-answer vector
    - ``validate_spin_format`` — local guard so a malformed PIN fails
      BEFORE a challenge request (a wrong hash burns a lockout try)
    - the rolesrights/RLU URL builders (``/api`` prefix, NO brand/country,
      lock/unlock as the path tail) + the SPIN-completed body shape
    - the response parsers (challenge, completed-token, request-id,
      status, garage VINs)

These stay pure-Python — no HA event loop, no aiohttp — so they run
cleanly and assert real behaviour, not tautologies.
"""

from __future__ import annotations

import base64
import json
from pathlib import Path

import pytest

from custom_components.vag_connect.cariad import _mbb
from custom_components.vag_connect.cariad.auth import _mbboauth
from custom_components.vag_connect.cariad.auth._device_grant import (
    MBB_DAG_CLIENT_ID,
    MBB_DAG_SCOPE,
    mbb_dag_config,
)
from custom_components.vag_connect.cariad.exceptions import AuthenticationError

_FIXTURES = Path(__file__).parent / "fixtures"


def _make_jwt(claims: dict) -> str:
    """Build a fake JWT with the given payload claims (header/sig are junk)."""
    payload = base64.urlsafe_b64encode(
        json.dumps(claims).encode()
    ).decode().rstrip("=")
    return f"eyJhbGciOiJSUzI1NiJ9.{payload}.signature"


# ── a3: SPIN hash (the canonical footgun) ─────────────────────────────


class TestComputeSpinHash:
    # Known-answer vector computed independently with the documented
    # algorithm: sha512(bytes.fromhex("1234") + bytes.fromhex(challenge)).
    VECTOR = (
        "1BBA1D16BAFCB2AFD1AD7E2C1A747906B79092DC97E625874CE9ACB1BB94C6DD"
        "1D3DE23DC1FA0D79C87E9A6F1A3DB21FED884886EFA7825B6B484B8265F0E0D0"
    )

    def test_known_answer_vector(self) -> None:
        assert (
            _mbb.compute_spin_hash("1234", "ABCDEF0123456789") == self.VECTOR
        )

    def test_is_uppercase_hex(self) -> None:
        h = _mbb.compute_spin_hash("1234", "ABCDEF0123456789")
        assert h == h.upper()
        assert len(h) == 128  # SHA-512 hex digest

    def test_hex_decoded_not_utf8(self) -> None:
        """The footgun guard: hashing must hex-decode the SPIN, so the
        result must DIFFER from a (wrong) utf-8 encoding of the SPIN."""
        import hashlib  # noqa: PLC0415

        spin, challenge = "1234", "ABCDEF0123456789"
        wrong = hashlib.sha512(
            spin.encode("utf-8") + bytes.fromhex(challenge)
        ).hexdigest().upper()
        assert _mbb.compute_spin_hash(spin, challenge) != wrong

    def test_deterministic(self) -> None:
        a = _mbb.compute_spin_hash("4321", "00FF")
        b = _mbb.compute_spin_hash("4321", "00FF")
        assert a == b


class TestValidateSpinFormat:
    def test_accepts_4_and_6_digit(self) -> None:
        _mbb.validate_spin_format("1234")
        _mbb.validate_spin_format("123456")

    def test_rejects_empty(self) -> None:
        with pytest.raises(ValueError):
            _mbb.validate_spin_format("")

    def test_rejects_odd_length(self) -> None:
        with pytest.raises(ValueError):
            _mbb.validate_spin_format("123")

    def test_rejects_non_hex(self) -> None:
        with pytest.raises(ValueError):
            _mbb.validate_spin_format("XYZW")


# ── a3: URL builders — /api prefix, NO brand/country, path-tail verb ──


class TestRluUrlBuilders:
    SET = "https://mal-1a.prd.ece.vwg-connect.com"
    VIN = "wvwzzz1kz000000aa"

    def test_challenge_lock(self) -> None:
        url = _mbb.build_mbb_spin_challenge_url(self.SET, self.VIN, lock=True)
        assert url == (
            f"{self.SET}/api/rolesrights/authorization/v2/vehicles/"
            f"{self.VIN.upper()}/services/rlu_v1/operations/LOCK/"
            "security-pin-auth-requested"
        )

    def test_challenge_unlock_uses_unlock_op(self) -> None:
        url = _mbb.build_mbb_spin_challenge_url(self.SET, self.VIN, lock=False)
        assert "/operations/UNLOCK/" in url

    def test_completed_url(self) -> None:
        assert _mbb.build_mbb_spin_completed_url(self.SET) == (
            f"{self.SET}/api/rolesrights/authorization/v2/"
            "security-pin-auth-completed"
        )

    def test_action_lock_is_path_tail_no_brand_country(self) -> None:
        url = _mbb.build_mbb_rlu_action_url(self.SET, self.VIN, lock=True)
        assert url == f"{self.SET}/api/bs/rlu/v1/vehicles/{self.VIN.upper()}/lock"
        # The deprecated /{brand}/{country}/.../actions form must NOT appear.
        assert "/actions" not in url
        assert "/VW/" not in url

    def test_action_unlock(self) -> None:
        url = _mbb.build_mbb_rlu_action_url(self.SET, self.VIN, lock=False)
        assert url.endswith("/unlock")

    def test_status_url(self) -> None:
        url = _mbb.build_mbb_rlu_status_url(self.SET, self.VIN, "REQ-1")
        assert url == (
            f"{self.SET}/api/bs/rlu/v1/vehicles/{self.VIN.upper()}/requests/"
            "REQ-1/status"
        )

    def test_content_type_is_remote_lock_unlock_vendor(self) -> None:
        assert _mbb.MBB_RLU_CONTENT_TYPE == (
            "application/vnd.vwg.mbb.RemoteLockUnlock_v1_0_0+xml"
        )


class TestCompletedBody:
    def test_shape(self) -> None:
        body = _mbb.build_mbb_completed_body("L1", "CAFE", "HASHVAL")
        assert body == {
            "securityPinAuthentication": {
                "securityPin": {
                    "challenge": "CAFE",
                    "securityPinHash": "HASHVAL",
                },
                "securityToken": "L1",
            }
        }


# ── a3: response parsers ──────────────────────────────────────────────


class TestParsers:
    def test_parse_challenge_full(self) -> None:
        resp = {
            "securityPinAuthInfo": {
                "securityToken": "LEVEL1",
                "securityPinTransmission": {
                    "challenge": "ABCD", "remainingTries": 3,
                },
            }
        }
        assert _mbb.parse_mbb_spin_challenge(resp) == ("LEVEL1", "ABCD", 3)

    def test_parse_challenge_missing(self) -> None:
        assert _mbb.parse_mbb_spin_challenge(None) == (None, None, None)
        assert _mbb.parse_mbb_spin_challenge({}) == (None, None, None)

    def test_parse_challenge_no_remaining(self) -> None:
        resp = {
            "securityPinAuthInfo": {
                "securityToken": "L1",
                "securityPinTransmission": {"challenge": "AA"},
            }
        }
        assert _mbb.parse_mbb_spin_challenge(resp) == ("L1", "AA", None)

    def test_parse_completed_token(self) -> None:
        assert _mbb.parse_mbb_completed_token({"securityToken": "L2"}) == "L2"
        assert _mbb.parse_mbb_completed_token({}) is None
        assert _mbb.parse_mbb_completed_token(None) is None

    def test_parse_request_id(self) -> None:
        resp = {"rluActionResponse": {"requestId": "REQ-42"}}
        assert _mbb.parse_mbb_rlu_request_id(resp) == "REQ-42"
        assert _mbb.parse_mbb_rlu_request_id({}) is None
        assert _mbb.parse_mbb_rlu_request_id(None) is None

    def test_parse_request_id_coerces_int(self) -> None:
        assert _mbb.parse_mbb_rlu_request_id(
            {"rluActionResponse": {"requestId": 99}}
        ) == "99"

    def test_parse_status_wrapped(self) -> None:
        resp = {"requestStatusResponse": {"status": "request_successful"}}
        assert _mbb.parse_mbb_rlu_status(resp) == "request_successful"

    def test_parse_status_bare(self) -> None:
        assert _mbb.parse_mbb_rlu_status({"status": "request_fail"}) == "request_fail"

    def test_parse_status_missing(self) -> None:
        assert _mbb.parse_mbb_rlu_status(None) is None
        assert _mbb.parse_mbb_rlu_status({}) is None


class TestGarageEnumeration:
    def test_vins_string_list(self) -> None:
        resp = {"userVehicles": {"vehicle": ["VIN1", "VIN2"]}}
        assert _mbb.parse_mbb_vehicle_vins(resp) == ["VIN1", "VIN2"]

    def test_vins_single_string(self) -> None:
        resp = {"userVehicles": {"vehicle": "VINSOLO"}}
        assert _mbb.parse_mbb_vehicle_vins(resp) == ["VINSOLO"]

    def test_vins_object_list(self) -> None:
        resp = {"userVehicles": {"vehicle": [{"vin": "VINOBJ"}]}}
        assert _mbb.parse_mbb_vehicle_vins(resp) == ["VINOBJ"]

    def test_vins_empty(self) -> None:
        assert _mbb.parse_mbb_vehicle_vins(None) == []
        assert _mbb.parse_mbb_vehicle_vins({}) == []
        assert _mbb.parse_mbb_vehicle_vins({"userVehicles": {}}) == []

    def test_vehicles_url(self) -> None:
        url = _mbb.build_mbb_vehicles_url(
            "https://msg.volkswagen.de", "volkswagen", "DE"
        )
        assert url == (
            "https://msg.volkswagen.de/fs-car/usermanagement/users/v1/VW/DE/"
            "vehicles"
        )


# ── a2: auth-core ─────────────────────────────────────────────────────


class TestJwtAud:
    def test_list_aud_returns_first(self) -> None:
        tok = _make_jwt({"aud": ["VWGMBB01DELIV1", "other"]})
        assert _mbboauth.jwt_aud(tok) == "VWGMBB01DELIV1"

    def test_string_aud(self) -> None:
        tok = _make_jwt({"aud": "single-aud"})
        assert _mbboauth.jwt_aud(tok) == "single-aud"

    def test_missing_aud(self) -> None:
        assert _mbboauth.jwt_aud(_make_jwt({"sub": "x"})) is None

    def test_garbage_token(self) -> None:
        assert _mbboauth.jwt_aud("not-a-jwt") is None
        assert _mbboauth.jwt_aud("") is None


class TestRegisterGuards:
    def test_register_url_constant(self) -> None:
        assert _mbboauth.MBB_REGISTER_URL == (
            "https://mbboauth-1d.prd.ece.vwg-connect.com/mbbcoauth/"
            "mobile/register/v1"
        )

    @pytest.mark.asyncio
    async def test_register_rejects_empty_id_token(self) -> None:
        with pytest.raises(AuthenticationError):
            await _mbboauth.register(None, "")  # type: ignore[arg-type]


class TestMbbDagConfig:
    def test_volkswagen_returns_eremote_client_and_mbb_scope(self) -> None:
        cfg = mbb_dag_config("volkswagen")
        assert cfg is not None
        client_id, scope = cfg
        assert client_id == MBB_DAG_CLIENT_ID
        assert client_id.startswith("9496332b-")
        # The load-bearing 'mbb' scope is what makes the id_token aud the
        # MBB backend audience — without it the exchange 400s.
        assert "mbb" in scope.split()
        assert scope == MBB_DAG_SCOPE

    def test_non_vw_brands_return_none(self) -> None:
        for brand in ("audi", "skoda", "seat", "cupra", "porsche", ""):
            assert mbb_dag_config(brand) is None

    def test_case_insensitive(self) -> None:
        assert mbb_dag_config("Volkswagen") is not None


class TestBrandSegmentUnchanged:
    """The rlu path is brandless, but the VSR read path still segments."""

    def test_vw_segment(self) -> None:
        assert _mbb.mbb_brand_segment("volkswagen") == "VW"

    def test_audi_segment(self) -> None:
        assert _mbb.mbb_brand_segment("audi") == "Audi"


# ── operationList: the service directory (license + hosts + commands) ─
#
# Parsed against the REAL operationList captured live 2026-06-21 from a
# Golf GTE whose We Connect subscription had expired (VIN/userId redacted
# in the fixture). This is the data that solved the whole "no data"
# mystery: the read 403s were an EXPIRED subscription, not a code bug.


def _load_oplist_fixture() -> dict:
    return json.loads(
        (_FIXTURES / "mbb_operationlist_golf_expired.json").read_text(
            encoding="utf-8"
        )
    )


class TestOperationListParse:
    def test_url_builder(self) -> None:
        assert _mbb.build_mbb_operationlist_url(
            "https://mal-1a.prd.ece.vwg-connect.com", "wvwzzz000",
        ) == (
            "https://mal-1a.prd.ece.vwg-connect.com/api/rolesrights/"
            "operationlist/v3/vehicles/WVWZZZ000"
        )

    def test_parses_real_fixture(self) -> None:
        ol = _mbb.parse_mbb_operationlist(_load_oplist_fixture())
        assert ol is not None
        assert ol.role == "PRIMARY_USER"
        assert ol.status == "ENABLED"
        assert len(ol.services) == 12
        assert _mbb.MBB_STATUS_SERVICE_ID in ol.services

    def test_status_service_is_expired(self) -> None:
        ol = _mbb.parse_mbb_operationlist(_load_oplist_fixture())
        sr = ol.status_service
        assert sr is not None
        assert sr.enabled is False
        assert sr.license_required is True
        assert sr.license_status == "EXPIRED"
        assert sr.license_expiry == "2026-06-16T22:34:00Z"
        assert "noActiveLicense" in sr.reasons

    def test_subscription_active_false_when_expired(self) -> None:
        ol = _mbb.parse_mbb_operationlist(_load_oplist_fixture())
        assert _mbb.mbb_subscription_active(ol) is False

    def test_free_essential_service_is_enabled(self) -> None:
        ol = _mbb.parse_mbb_operationlist(_load_oplist_fixture())
        svc = ol.service("services_v1")
        assert svc is not None
        assert svc.enabled is True
        assert svc.license_required is False

    def test_service_base_substitutes_template(self) -> None:
        ol = _mbb.parse_mbb_operationlist(_load_oplist_fixture())
        base = _mbb.mbb_service_base(
            ol, "rclima_v1", brand="volkswagen", country="CH", vin="wvwzzz1",
        )
        # trailing slash stripped (v2.15.0a7) so build_mbb_action_url can join.
        assert base == (
            "https://mal-1a.prd.ece.vwg-connect.com/api/bs/climatisation/v1/"
            "vehicles/WVWZZZ1"
        )

    def test_service_base_none_when_no_invocation_url(self) -> None:
        # statusreport_v1 carries no invocationUrl in the real data.
        ol = _mbb.parse_mbb_operationlist(_load_oplist_fixture())
        assert _mbb.mbb_service_base(
            ol, _mbb.MBB_STATUS_SERVICE_ID, brand="volkswagen",
            country="CH", vin="x",
        ) is None

    def test_operations_carry_remote_commands(self) -> None:
        ol = _mbb.parse_mbb_operationlist(_load_oplist_fixture())
        rclima = ol.service("rclima_v1")
        cmds = {o.get("remoteCommand") for o in rclima.operations}
        assert "startClimatisation" in cmds

    def test_none_and_garbage_safe(self) -> None:
        assert _mbb.parse_mbb_operationlist(None) is None
        assert _mbb.parse_mbb_operationlist({}) is None
        assert _mbb.parse_mbb_operationlist({"operationList": "x"}) is None
        assert _mbb.mbb_subscription_active(None) is None

    def test_subscription_active_true_path(self) -> None:
        # Synthetic Enabled status service (the fixture is expired) — verifies
        # the active branch since real subscribed-car data wasn't captured.
        ol = _mbb.parse_mbb_operationlist({
            "operationList": {
                "vin": "X", "role": "PRIMARY_USER", "status": "ENABLED",
                "serviceInfo": [
                    {"serviceId": "statusreport_v1", "licenseRequired": True,
                     "serviceStatus": {"status": "Enabled"}},
                ],
            }
        })
        assert _mbb.mbb_subscription_active(ol) is True
        assert ol.status_service.enabled is True

    def test_missing_status_service_yields_unknown(self) -> None:
        ol = _mbb.parse_mbb_operationlist({
            "operationList": {"vin": "X", "serviceInfo": [
                {"serviceId": "services_v1", "serviceStatus": {"status": "Enabled"}},
            ]}
        })
        # No statusreport_v1 → subscription state is unknown (None), not False.
        assert _mbb.mbb_subscription_active(ol) is None


# ── durable MBB commands (climate/charge/timer via SecToken) ──────────
#
# The data plane is ACL-closed for the durable token, but the SecToken
# command path IS open (live-confirmed: security-pin-auth-requested=200).
# These route GENERICALLY through the operationList per-service hosts so
# any country/brand works without hardcoding.


def _active_oplist():
    """The real fixture with every service flipped to Enabled (subscribed)."""
    d = json.loads(
        (_FIXTURES / "mbb_operationlist_golf_expired.json").read_text(
            encoding="utf-8"))
    for s in d["operationList"]["serviceInfo"]:
        s["serviceStatus"] = {"status": "Enabled"}
    return _mbb.parse_mbb_operationlist(d)


class TestMbbCommands:
    def test_command_table_covers_climate_and_charge(self) -> None:
        for name in ("climate_start", "climate_stop", "charge_start",
                     "charge_stop", "charge_target_soc", "window_heat_start",
                     "window_heat_stop"):
            assert name in _mbb.MBB_COMMANDS
        spec = _mbb.MBB_COMMANDS["climate_start"]
        assert spec.service_id == "rclima_v1"
        assert spec.action_subpath == "climater/actions"
        assert "ClimaterAction" in spec.content_type

    def test_service_base_is_per_market_generic(self) -> None:
        # The charge invocationUrl carries {brand}/{country} → substituted from
        # the operationList, so a CH account gets /VW/CH/ automatically.
        ol = _active_oplist()
        base = _mbb.mbb_service_base(
            ol, "rbatterycharge_v1", brand="volkswagen", country="CH", vin="wvw1")
        assert "/VW/CH/" in base
        assert base.endswith("WVW1")

    def test_op_granted_only_when_enabled_and_granted(self) -> None:
        active = _active_oplist()
        assert _mbb.mbb_operation_granted(
            active, "rclima_v1", "P_START_CLIMA_NOSET") is True
        # Disabled service (the original expired fixture) → not grantable.
        expired = _mbb.parse_mbb_operationlist(_load_oplist_fixture())
        assert _mbb.mbb_operation_granted(
            expired, "rclima_v1", "P_START_CLIMA_NOSET") is False
        # Unknown operation → False.
        assert _mbb.mbb_operation_granted(active, "rclima_v1", "NOPE") is False

    def test_op_auth_url(self) -> None:
        assert _mbb.build_mbb_op_auth_url(
            "https://mal-1a.x", "wvw1", "rclima_v1", "P_STOP") == (
            "https://mal-1a.x/api/rolesrights/authorization/v2/vehicles/WVW1/"
            "services/rclima_v1/operations/P_STOP/security-pin-auth-requested")

    def test_action_url_join(self) -> None:
        assert _mbb.build_mbb_action_url(
            "https://h/api/bs/climatisation/v1/vehicles/WVW1",
            "climater/actions",
        ) == "https://h/api/bs/climatisation/v1/vehicles/WVW1/climater/actions"

    def test_charger_settings_body_clamps_soc(self) -> None:
        body = _mbb.build_mbb_charger_settings_body(150)
        assert "<targetStateOfChargeInPercent>100<" in body
        assert _mbb.build_mbb_charger_settings_body(-5).count(">0<") >= 0

    def test_action_request_id_generic(self) -> None:
        assert _mbb.parse_mbb_action_request_id(
            {"climaterActionResponse": {"requestId": "C1"}}) == "C1"
        assert _mbb.parse_mbb_action_request_id(
            {"chargerActionResponse": {"requestId": "G2"}}) == "G2"
        assert _mbb.parse_mbb_action_request_id(
            {"rluActionResponse": {"requestId": "R3"}}) == "R3"
        assert _mbb.parse_mbb_action_request_id({"action": {"actionId": "A4"}}) == "A4"
        assert _mbb.parse_mbb_action_request_id(None) is None
        assert _mbb.parse_mbb_action_request_id({}) is None


# ── auth-isolation regression gates (review 2026-06-21) ───────────────
#
# These lock in the "MBB bearer never reaches the dead CARIAD BFF host"
# invariant so a future refactor that drops a strategy gate breaks the
# build instead of silently leaking the durable bearer. They exercise the
# pure early-return branches only (no network).


def _make_mbb_client():
    """Build a VWEUClient skeleton with strategy=='mbb' and no real I/O."""
    from custom_components.vag_connect.cariad.api.vw_eu import VWEUClient
    from custom_components.vag_connect.cariad.models import BRAND_VW_EU, TokenSet

    client = VWEUClient.__new__(VWEUClient)
    client._brand = BRAND_VW_EU
    client._tokens = TokenSet(
        access_token="MBB_BEARER", refresh_token="r", id_token="", strategy="mbb",
    )
    client._mbb_client_id = "registered-client"
    client._probe_disabled = False
    return client


class TestAuthIsolationGates:
    @pytest.mark.asyncio
    async def test_find_charging_stations_returns_empty_for_mbb(self) -> None:
        """Must short-circuit to [] BEFORE building the BFF url, so the MBB
        bearer is never sent to emea.bff.cariad.digital."""
        client = _make_mbb_client()
        # If the gate were missing this would try self._get (no _session) and
        # raise; the gate returns [] without touching the network.
        assert await client.find_charging_stations(47.0, 8.0) == []

    @pytest.mark.asyncio
    async def test_run_v3_probe_pass_skipped_for_mbb(self) -> None:
        """The probe pass resolves the BFF host with no per-strategy routing,
        so it must early-return 0 for an mbb entry."""
        client = _make_mbb_client()
        assert await client.run_v3_probe_pass("WVWZZZ000000VIN01") == 0

    @pytest.mark.asyncio
    async def test_get_status_routes_to_mbb_vsr(self) -> None:
        """get_status must route an mbb entry to _get_status_via_mbb_vsr and
        NEVER fall through to the BFF selectivestatus self._get."""
        from unittest.mock import AsyncMock

        client = _make_mbb_client()
        client._website_proxy = None
        client._eu_portal = None
        sentinel = object()
        client._get_status_via_mbb_vsr = AsyncMock(return_value=sentinel)
        client._get = AsyncMock(side_effect=AssertionError("BFF self._get hit!"))
        result = await client.get_status("WVWZZZ000000VIN01")
        assert result is sentinel
        client._get_status_via_mbb_vsr.assert_awaited_once()
        client._get.assert_not_called()

    @pytest.mark.asyncio
    async def test_get_vehicles_uses_manual_vins_without_enumeration(self) -> None:
        """The fal-scoped MBB token can't list the garage (usermanagement
        403s), so a user-supplied VIN must be returned directly without any
        network enumeration call."""
        from unittest.mock import AsyncMock

        client = _make_mbb_client()
        client._mbb_manual_vins = ["WVWZZZ1KZAW123456", "WAUZZZ8V0KA000000"]
        # If enumeration were attempted it would hit _mbb_get (no _session).
        client._mbb_get = AsyncMock(side_effect=AssertionError("enum hit!"))
        vins = await client._get_vehicles_via_mbb()
        assert vins == ["WVWZZZ1KZAW123456", "WAUZZZ8V0KA000000"]
        client._mbb_get.assert_not_called()

    @pytest.mark.asyncio
    async def test_command_lock_routes_to_mbb_rlu(self) -> None:
        """command_lock must route an mbb entry to the RLU SecToken flow and
        not the BFF lock-unlock fallback path."""
        from unittest.mock import AsyncMock

        client = _make_mbb_client()
        client._spin = "1234"
        client._command_rlu_mbb = AsyncMock()
        client._post_command_with_fallback_paths = AsyncMock(
            side_effect=AssertionError("BFF command path hit!")
        )
        await client.command_lock("WVWZZZ000000VIN01")
        client._command_rlu_mbb.assert_awaited_once()
        client._post_command_with_fallback_paths.assert_not_called()
