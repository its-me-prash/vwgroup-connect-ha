# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""b1/B2 — "MBB two-way available" symbol: a diagnostic binary_sensor that is on
only when the durable Car-Net backend grants a remote command on a licensed
service for this car."""
from __future__ import annotations

from unittest.mock import MagicMock

from custom_components.vag_connect.cariad._mbb import (
    MbbOperationList,
    MbbService,
    mbb_operation_granted,
)
from custom_components.vag_connect.cariad.api.vw_eu import VWEUClient
from custom_components.vag_connect.cariad.models import VehicleData


def _oplist(granted: bool, enabled: bool = True) -> MbbOperationList:
    svc = MbbService(
        service_id="rclima_v1",
        status="Enabled" if enabled else "Disabled",
        operations=[{
            "id": "P_START_CLIMA_NOSET",
            "permission": "granted" if granted else "notLicensed",
        }],
    )
    return MbbOperationList(vin="X", services={"rclima_v1": svc})


def _client() -> VWEUClient:
    return VWEUClient(MagicMock(), "u@t.de", "pw")


class TestTwoWaySymbol:
    def test_granted_command_is_available(self) -> None:
        assert mbb_operation_granted(_oplist(granted=True), "rclima_v1",
                                     "P_START_CLIMA_NOSET") is True
        d = VehicleData(vin="X")
        _client()._apply_mbb_subscription(d, _oplist(granted=True))
        assert d.mbb_two_way_available is True

    def test_not_granted_is_false(self) -> None:
        d = VehicleData(vin="X")
        _client()._apply_mbb_subscription(d, _oplist(granted=False))
        assert d.mbb_two_way_available is False

    def test_disabled_service_is_false(self) -> None:
        d = VehicleData(vin="X")
        _client()._apply_mbb_subscription(d, _oplist(granted=True, enabled=False))
        assert d.mbb_two_way_available is False

    def test_no_oplist_is_unknown_none(self) -> None:
        d = VehicleData(vin="X")
        _client()._apply_mbb_subscription(d, None)
        assert d.mbb_two_way_available is None
