# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Companion: the data source names the app transport, not the brand's cloud.

Live, the companion entry's Data source channel and connectivity sensor read
"Volkswagen EU (WeConnect ID)": provenance was stamped with the brand slug.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from custom_components.vag_connect._channel_labels import channel_display_name
from custom_components.vag_connect.const import CONF_STRATEGY, STRATEGY_COMPANION_ADB
from custom_components.vag_connect.coordinator import VagConnectCoordinator


def _coord(data, client):
    c = VagConnectCoordinator.__new__(VagConnectCoordinator)
    c.entry = SimpleNamespace(data=data)
    c._cariad_client = client
    return c


@pytest.mark.parametrize(("token", "label"), [
    ("companion_adb", "Companion app (ADB)"),
    ("companion_relay", "Companion app (relay)"),
])
def test_a_companion_entry_names_its_transport(token, label):
    c = _coord(
        {CONF_STRATEGY: STRATEGY_COMPANION_ADB, "brand": "volkswagen"},
        SimpleNamespace(_source_channel=token),
    )
    assert c._primary_channel_name() == token
    assert channel_display_name(token) == label


def test_a_cloud_entry_keeps_the_brand():
    c = _coord({"brand": "volkswagen"}, MagicMock(spec=[]))
    assert c._primary_channel_name() == "volkswagen"
