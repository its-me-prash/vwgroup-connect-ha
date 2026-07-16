# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The push opt-in toggles have to be reachable from the UI.

`async_start_push_managers` gated on `entry.options` only. The options update
listener folds options into `entry.data` and blanks `entry.options`
(__init__.py), so all three toggles read False forever and no push manager
could ever start — Škoda MQTT, CUPRA/SEAT FCM and Audi/VW FCM were
unreachable from the UI for as long as they shipped.

Nothing caught it because the push foundation tests construct the managers
directly and never go through the toggle-reading path.

These tests put the toggle where the listener actually leaves it (entry.data).
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.vag_connect.const import (
    CONF_BRAND,
    CONF_ENABLE_PUSH_AUDI_VW,
    CONF_ENABLE_PUSH_FCM,
    CONF_ENABLE_PUSH_MQTT,
)


def _coord(data=None, options=None):
    from custom_components.vag_connect.coordinator import VagConnectCoordinator

    c = VagConnectCoordinator.__new__(VagConnectCoordinator)
    c.entry = MagicMock()
    c.entry.data = data if data is not None else {}
    c.entry.options = options if options is not None else {}
    c.hass = MagicMock()
    client = MagicMock()
    client.user_id = "user-uuid-123"
    c._cariad_client = client
    c.vehicles = {"VINA": {}}
    c._skoda_push = None
    c._cupra_seat_push = None
    c._audi_vw_push = None
    return c


@pytest.mark.asyncio
async def test_skoda_mqtt_toggle_read_from_data() -> None:
    c = _coord(data={CONF_BRAND: "skoda", CONF_ENABLE_PUSH_MQTT: True}, options={})
    with patch(
        "custom_components.vag_connect.cariad.push.skoda_mqtt.SkodaPushManager"
    ) as mgr:
        mgr.return_value.start = AsyncMock()
        await c.async_start_push_managers()
    assert c._skoda_push is not None, "Škoda MQTT toggle did not reach the manager"


@pytest.mark.asyncio
async def test_cupra_seat_fcm_toggle_read_from_data() -> None:
    c = _coord(data={CONF_BRAND: "cupra", CONF_ENABLE_PUSH_FCM: True}, options={})
    with patch(
        "custom_components.vag_connect.cariad.push.cupra_seat_fcm.CupraSeatPushManager"
    ) as mgr:
        mgr.return_value.start = AsyncMock()
        await c.async_start_push_managers()
    assert c._cupra_seat_push is not None


@pytest.mark.asyncio
async def test_audi_vw_fcm_toggle_read_from_data() -> None:
    c = _coord(
        data={CONF_BRAND: "volkswagen", CONF_ENABLE_PUSH_AUDI_VW: True}, options={}
    )
    with patch(
        "custom_components.vag_connect.cariad.push.audi_vw_fcm.AudiVWPushManager"
    ) as mgr:
        mgr.return_value.start = AsyncMock()
        await c.async_start_push_managers()
    assert c._audi_vw_push is not None


@pytest.mark.asyncio
async def test_options_still_win_over_data() -> None:
    # An in-flight options dict must still take precedence (pre-listener state).
    c = _coord(
        data={CONF_BRAND: "skoda", CONF_ENABLE_PUSH_MQTT: False},
        options={CONF_ENABLE_PUSH_MQTT: True},
    )
    with patch(
        "custom_components.vag_connect.cariad.push.skoda_mqtt.SkodaPushManager"
    ) as mgr:
        mgr.return_value.start = AsyncMock()
        await c.async_start_push_managers()
    assert c._skoda_push is not None


@pytest.mark.asyncio
async def test_toggle_off_starts_nothing() -> None:
    # Default-off must stay default-off — this is an opt-in feature.
    c = _coord(data={CONF_BRAND: "skoda"}, options={})
    await c.async_start_push_managers()
    assert c._skoda_push is None
