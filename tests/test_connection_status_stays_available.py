# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Connection-status diagnostics stay available when the vehicle poll fails.

When a car's poll fails past the tolerance window every one of its entities goes
unavailable — which used to include the "last reported", "data source",
error-reporter and per-source connectivity entities, i.e. exactly the ones that
explain WHY the car went dark. Those now stay available regardless of the poll
outcome (by ``entity_description.key`` or a class ``_stay_available_on_poll_failure``),
so the user is never blinded at the moment they need the diagnostics.
"""
from __future__ import annotations

from unittest.mock import MagicMock

from custom_components.vag_connect.entity_base import (
    _CONNECTION_STATUS_KEYS,
    VagConnectEntity,
)


def _coord(*, poll_ok: bool, vehicle_ok: bool) -> MagicMock:
    c = MagicMock()
    c.last_update_success = poll_ok
    c.is_vehicle_available.return_value = vehicle_ok
    c.vehicle_last_good_at = {}  # no last-known-good → normal entities go unavailable
    return c


def _entity(coord: MagicMock, *, key: str | None = None, flag: bool = False) -> VagConnectEntity:
    e = VagConnectEntity.__new__(VagConnectEntity)
    e.coordinator = coord
    e._vin = "VIN1"
    e._command_id = None
    if key is not None:
        desc = MagicMock()
        desc.key = key
        e.entity_description = desc  # type: ignore[attr-defined]
    if flag:
        e._stay_available_on_poll_failure = True  # type: ignore[attr-defined]
    return e


def test_connection_status_keys_stay_available_on_total_poll_failure() -> None:
    coord = _coord(poll_ok=False, vehicle_ok=False)  # worst case: everything down
    for key in _CONNECTION_STATUS_KEYS:
        assert _entity(coord, key=key).available is True, key


def test_flagged_class_stays_available_on_total_poll_failure() -> None:
    coord = _coord(poll_ok=False, vehicle_ok=False)
    assert _entity(coord, flag=True).available is True


def test_ordinary_entity_still_goes_unavailable() -> None:
    # a normal per-car entity (not a connection-status one) must still disappear
    # when the poll has genuinely failed and there is no last-known-good snapshot
    coord = _coord(poll_ok=False, vehicle_ok=False)
    assert _entity(coord, key="doors_locked").available is False


def test_connection_status_still_available_when_healthy() -> None:
    coord = _coord(poll_ok=True, vehicle_ok=True)
    assert _entity(coord, key="connection_active").available is True
    assert _entity(coord, key="doors_locked").available is True
