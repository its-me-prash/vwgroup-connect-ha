# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Pure parser/builder tests for the volkswagen.de authproxy data-layer.

Fixtures are the REAL captured response bodies (Golf GTE, MBB, 2026-06), VIN
redacted to a test value. Validates VIN + mbbUserId discovery, master-data and
image parsing, and the proxy URL shape.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

from custom_components.vag_connect.cariad import _authproxy as ap
from custom_components.vag_connect.cariad.auth._website_authproxy import (
    WebsiteAuthProxyConnector,
)

_VIN = "WVWZZZAUZFW805377"

_RELATIONS = {
    "user": {
        "idKitUserId": "76b39a5c-63eb-4054-9271-f382b5b455b5",
        "mbbUserId": "MMjVRD25UEHSL31wBcHXG5FdAJN",
        "legalEntityCode": "VOLKSWAGEN",
    },
    "relations": [
        {
            "vehicleNickname": "Golf GTE",
            "relationId": "018014f9-b642-46fe-9b9b-f2710bb90f5c",
            "licensePlate": "AG412994",
            "primaryCar": True,
            "role": "PRIMARY_USER",
            "enrollmentStatus": "COMPLETED",
            "roleStatus": "ENABLED",
            "tags": ["EUDA_SCOPED"],
            "vehicle": {"vin": _VIN, "commissionId": None, "modBackend": "MBB"},
        }
    ],
    "isCompleteResponse": True,
}

_IMAGES = {
    "service": "VILMA",
    "imageUrls": [
        "https://media.volkswagen.com/Vilma/V/5G1/2015/Side_Left/a.png",
        "https://media.volkswagen.com/Vilma/V/5G1/2015/Front_Center/b.png",
    ],
    "images": [
        {"url": "https://m/Side_Left.png", "angle": "Left", "viewDirection": "Side"},
        {"url": "https://m/Back_Left.png", "angle": "Left", "viewDirection": "Back"},
        {"url": "https://m/Front_Center.png", "angle": "Center", "viewDirection": "Front"},
        {"url": "https://m/Front_Left.png", "angle": "Left", "viewDirection": "Front"},
    ],
}

_DATA = {"vin": _VIN, "modelName": "Golf GTE Plug in Hybrid", "exteriorColor": "0R"}

_DETAILS = {
    "modelName": "Golf GTE Plug in Hybrid 1,4 l TSI Plug-In-Hybrid",
    "engine": "110 kW (150 PS)",
    "modelYear": "2015",
    "exteriorColorText": "Oryxweiß Perlmutteffekt",
    "importerId": None,
    "specifications": [{"codeText": "x", "origin": "L"}] * 202,
}


class TestRelations:
    def test_user_identity_and_mbb_user_id(self) -> None:
        rel = ap.parse_relations(_RELATIONS)
        assert rel is not None
        assert rel.user_id == "76b39a5c-63eb-4054-9271-f382b5b455b5"
        assert rel.mbb_user_id == "MMjVRD25UEHSL31wBcHXG5FdAJN"
        assert rel.legal_entity == "VOLKSWAGEN"

    def test_vehicle_discovery(self) -> None:
        rel = ap.parse_relations(_RELATIONS)
        assert rel.vins == [_VIN]
        v = rel.vehicles[0]
        assert v.vin == _VIN
        assert v.nickname == "Golf GTE"
        assert v.license_plate == "AG412994"
        assert v.role == "PRIMARY_USER"
        assert v.mod_backend == "MBB"
        assert v.primary_car is True
        assert v.euda_scoped is True

    def test_non_dict_returns_none(self) -> None:
        assert ap.parse_relations(None) is None
        assert ap.parse_relations([1, 2]) is None

    def test_empty_relations_keeps_user(self) -> None:
        rel = ap.parse_relations({"user": {"mbbUserId": "X"}, "relations": []})
        assert rel.mbb_user_id == "X"
        assert rel.vins == []


class TestMasterData:
    def test_details_then_data_merge(self) -> None:
        info = ap.parse_vehicle_details(_DETAILS)
        info = ap.parse_vehicle_data(_DATA, into=info)
        assert info.vin == _VIN
        assert info.model_year == "2015"
        assert info.engine == "110 kW (150 PS)"
        assert info.exterior_color_text == "Oryxweiß Perlmutteffekt"
        assert info.exterior_color_code == "0R"
        assert info.spec_count == 202
        assert info.model_name.startswith("Golf GTE")

    def test_partial_inputs_are_safe(self) -> None:
        assert ap.parse_vehicle_details({}).model_name is None
        assert ap.parse_vehicle_data("nope").vin is None


class TestImages:
    def test_structured_images_preferred(self) -> None:
        imgs = ap.parse_vehicle_images(_IMAGES)
        assert len(imgs) == 4
        assert imgs[0].angle == "Left"
        assert imgs[0].view_direction == "Side"

    def test_primary_prefers_front(self) -> None:
        imgs = ap.parse_vehicle_images(_IMAGES)
        assert ap.primary_image_url(imgs) == "https://m/Front_Center.png"

    def test_fallback_to_flat_urls(self) -> None:
        imgs = ap.parse_vehicle_images({"imageUrls": ["https://x/a.png"]})
        assert len(imgs) == 1
        assert imgs[0].url == "https://x/a.png"
        assert imgs[0].angle is None

    def test_empty_is_empty(self) -> None:
        assert ap.parse_vehicle_images({}) == []
        assert ap.parse_vehicle_images(None) == []


class TestUrlBuilders:
    def test_relations_url(self) -> None:
        u = ap.build_relations_url()
        assert u.endswith("/vw-de/proxy/v2/users/me/relations?resourceHost=myvw-vum-prod")

    def test_vehicle_urls_carry_vin_and_host(self) -> None:
        assert f"vehicles/{_VIN}/details/de-DE" in ap.build_vehicle_details_url(_VIN)
        assert f"vehicles/{_VIN}/data/de-DE" in ap.build_vehicle_data_url(_VIN)
        assert f"vehicleimages/exterior/{_VIN}" in ap.build_vehicle_images_url(_VIN)
        assert "resourceHost=myvw-vilma-proxy-prod" in ap.build_vehicle_images_url(_VIN)


def _conn() -> WebsiteAuthProxyConnector:
    return WebsiteAuthProxyConnector(MagicMock(), "u@t.de", "pw")  # type: ignore[arg-type]


class TestConnectorReadMethods:
    """The additive a13 read methods that wire the data-layer onto the session."""

    def test_get_relations_discovers_vin_and_mbb_user_id(self) -> None:
        c = _conn()
        c._get_json = AsyncMock(return_value=_RELATIONS)  # type: ignore[method-assign]
        rel = asyncio.run(c.get_relations())
        assert rel is not None
        assert rel.mbb_user_id == "MMjVRD25UEHSL31wBcHXG5FdAJN"
        assert rel.vins == [_VIN]

    def test_get_relations_none_when_no_body(self) -> None:
        c = _conn()
        c._get_json = AsyncMock(return_value=None)  # type: ignore[method-assign]
        assert asyncio.run(c.get_relations()) is None

    def test_get_master_data_merges_details_and_data(self) -> None:
        c = _conn()
        c._get_json = AsyncMock(side_effect=[_DETAILS, _DATA])  # type: ignore[method-assign]
        info = asyncio.run(c.get_master_data(_VIN))
        assert info.model_year == "2015"
        assert info.exterior_color_code == "0R"
        assert info.spec_count == 202

    def test_get_exterior_images(self) -> None:
        c = _conn()
        c._get_json = AsyncMock(return_value=_IMAGES)  # type: ignore[method-assign]
        imgs = asyncio.run(c.get_exterior_images(_VIN))
        assert len(imgs) == 4
        assert ap.primary_image_url(imgs) == "https://m/Front_Center.png"


_WARNINGLIGHTS_TWO = {
    "data": {
        "warningLights": [
            {"category": "engine", "text": "Motorkontrollleuchte"},
            {"category": "tyre", "text": "Reifendruck"},
        ]
    }
}
_WARNINGLIGHTS_EMPTY = {"data": {"warningLights": []}}

_TRANSACTIONS = {
    "data": {
        "messages": [
            {
                "category": "remotelockunlock",
                "action": "lock",
                "actionSuccess": True,
                "timestamp": "2026-06-20T08:00:00Z",
            },
            {
                "category": "remotehonkandflash",
                "action": "honk",
                "actionSuccess": True,
                "timestamp": "2026-06-21T09:00:00Z",
            },
            {
                "category": "remotelockunlock",
                "action": "unlock",
                "actionSuccess": True,
                "timestamp": "2026-06-22T10:30:00Z",
            },
            {
                # newest lock/unlock overall, but FAILED — must be skipped in
                # favour of the newest successful one above.
                "category": "remotelockunlock",
                "action": "lock",
                "actionSuccess": False,
                "timestamp": "2026-06-23T11:00:00Z",
            },
        ]
    }
}

_RELATION_DETAIL = {
    "relation": {
        "vehicleNickname": "Golf GTE",
        "licensePlate": "AG412994",
        "role": "PRIMARY_USER",
        "primaryCar": True,
        "vehicle": {"vin": _VIN, "modBackend": "MBB"},
    }
}


class TestWarningLights:
    def test_counts_active_lights(self) -> None:
        assert ap.parse_warning_lights(_WARNINGLIGHTS_TWO) == 2

    def test_empty_list_is_zero_not_none(self) -> None:
        assert ap.parse_warning_lights(_WARNINGLIGHTS_EMPTY) == 0

    def test_missing_or_non_list_is_none(self) -> None:
        assert ap.parse_warning_lights({"data": {}}) is None
        assert ap.parse_warning_lights({"data": {"warningLights": "x"}}) is None
        assert ap.parse_warning_lights(None) is None
        assert ap.parse_warning_lights({}) is None


class TestLockHistory:
    def test_prefers_newest_successful_lock_action(self) -> None:
        result = ap.parse_lock_history(_TRANSACTIONS)
        assert result is not None
        action, ts = result
        # newest successful remotelockunlock = the unlock @ 10:30 (the 11:00
        # lock FAILED; the honk is a different category).
        assert action == "unlock"
        assert ts == "2026-06-22T10:30:00Z"

    def test_falls_back_to_newest_when_none_successful(self) -> None:
        raw = {"data": {"messages": [
            {"category": "remotelockunlock", "action": "lock",
             "actionSuccess": False, "timestamp": "2026-06-01T00:00:00Z"},
            {"category": "remotelockunlock", "action": "unlock",
             "actionSuccess": False, "timestamp": "2026-06-02T00:00:00Z"},
        ]}}
        result = ap.parse_lock_history(raw)
        assert result == ("unlock", "2026-06-02T00:00:00Z")

    def test_no_lock_messages_is_none(self) -> None:
        raw = {"data": {"messages": [
            {"category": "remotehonkandflash", "action": "honk"},
        ]}}
        assert ap.parse_lock_history(raw) is None
        assert ap.parse_lock_history({"data": {}}) is None
        assert ap.parse_lock_history(None) is None

    def test_action_without_timestamp_returns_none_time(self) -> None:
        raw = {"data": {"messages": [
            {"category": "remotelockunlock", "action": "lock",
             "actionSuccess": True},
        ]}}
        assert ap.parse_lock_history(raw) == ("lock", None)


class TestRelationDetail:
    def test_singular_relation_yields_nickname_and_plate(self) -> None:
        rel = ap.parse_relation_detail(_RELATION_DETAIL)
        assert rel is not None
        assert rel.vin == _VIN
        assert rel.nickname == "Golf GTE"
        assert rel.license_plate == "AG412994"
        assert rel.mod_backend == "MBB"

    def test_non_dict_or_missing_relation_is_none(self) -> None:
        assert ap.parse_relation_detail(None) is None
        assert ap.parse_relation_detail({}) is None
        assert ap.parse_relation_detail({"relation": {"vehicle": {}}}) is None


class TestLiveStatusUrlBuilders:
    def test_warninglights_url_realm_and_params(self) -> None:
        u = ap.build_warninglights_url(_VIN)
        assert f"/vwag-weconnect/proxy/vehicles/{_VIN}/warninglights/last" in u
        assert "gdc=myvw-wcar-prod" in u
        assert "resourceHost=myvw-vcf-prod" in u

    def test_transactionhistory_url_realm_and_params(self) -> None:
        u = ap.build_transactionhistory_url(_VIN)
        assert f"/vw-de/proxy/vehicles/{_VIN}/transactionhistory" in u
        assert "gdc=myvw-wcar-prod" in u
        assert "resourceHost=myvw-vcf-prod" in u

    def test_relation_detail_url(self) -> None:
        u = ap.build_relation_detail_url(_VIN)
        assert u.endswith(
            f"/vw-de/proxy/v2/users/me/relations/{_VIN}?resourceHost=myvw-vum-prod"
        )


class TestConnectorLiveStatusReads:
    """The v2.16.0 fail-soft transport methods over the pure parsers."""

    def test_get_warning_lights_returns_count(self) -> None:
        c = _conn()
        c._get_json = AsyncMock(return_value=_WARNINGLIGHTS_TWO)  # type: ignore[method-assign]
        assert asyncio.run(c.get_warning_lights(_VIN)) == 2

    def test_get_warning_lights_none_when_no_body(self) -> None:
        c = _conn()
        c._get_json = AsyncMock(return_value=None)  # type: ignore[method-assign]
        assert asyncio.run(c.get_warning_lights(_VIN)) is None

    def test_get_last_lock_action_returns_action_and_time(self) -> None:
        c = _conn()
        c._get_json = AsyncMock(return_value=_TRANSACTIONS)  # type: ignore[method-assign]
        assert asyncio.run(c.get_last_lock_action(_VIN)) == (
            "unlock", "2026-06-22T10:30:00Z"
        )

    def test_get_last_lock_action_none_when_no_body(self) -> None:
        c = _conn()
        c._get_json = AsyncMock(return_value=None)  # type: ignore[method-assign]
        assert asyncio.run(c.get_last_lock_action(_VIN)) is None

    def test_get_relation_detail_threads_nickname_plate(self) -> None:
        c = _conn()
        c._get_json = AsyncMock(return_value=_RELATION_DETAIL)  # type: ignore[method-assign]
        rel = asyncio.run(c.get_relation_detail(_VIN))
        assert rel is not None
        assert rel.nickname == "Golf GTE"
        assert rel.license_plate == "AG412994"


class TestMaintenanceRealShape:
    """Locks in the REAL authproxy maintenance body (live-captured, Golf GTE):
    flat fields directly under ``data`` (NOT wrapped in maintenanceStatus.value)."""

    def test_flat_golf_shape_maps_odometer_service_and_captured_ts(self) -> None:
        from custom_components.vag_connect.cariad.auth._website_authproxy import (
            map_maintenance_to_vehicle_data,
        )
        from custom_components.vag_connect.cariad.models import VehicleData

        payload = {"data": {
            "carCapturedTimestamp": "2026-06-22T18:20:30Z",
            "inspectionDue_days": 155, "inspectionDue_km": 14900,
            "mileage_km": 162062,
            "oilServiceDue_days": 17, "oilServiceDue_km": 1700,
        }}
        d = map_maintenance_to_vehicle_data(payload, VehicleData(vin="X"))
        assert d.odometer_km == 162062
        assert d.service_km == 14900
        assert d.service_due_in_days == 155
        assert d.oil_service_km == 1700
        assert d.oil_service_due_in_days == 17
        assert d.maintenance_report_captured_at == "2026-06-22T18:20:30Z"
