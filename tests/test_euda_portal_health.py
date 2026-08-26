# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Stage-0 EU Data Act observability — the portal_health enum.

A user needs to tell "the portal snapshot is stale/empty" apart from "the
integration is broken". _portal_health maps the portal connector's
last_no_data_reason + capture-age onto a small enum the sensor localizes.
"""
from __future__ import annotations

from custom_components.vag_connect.coordinator import (
    PORTAL_HEALTH_STATES,
    _portal_health,
)

_HOUR = 3600.0


def test_ok_when_data_flows_and_fresh():
    assert _portal_health({"no_data": False}, "", 60.0, 72 * _HOUR) == "ok"
    # no age / no threshold available → still ok (cannot prove stale)
    assert _portal_health({"no_data": False}, "", None, None) == "ok"


def test_stale_when_capture_age_past_the_floor():
    assert _portal_health({"no_data": False}, "", 80 * _HOUR, 72 * _HOUR) == "stale"
    # exactly at the floor counts as stale (>=)
    assert _portal_health({"no_data": False}, "", 72 * _HOUR, 72 * _HOUR) == "stale"


def test_no_data_reasons_map_to_their_states():
    assert _portal_health({"no_data": True}, "no_request", None, None) == "waiting_for_portal_data"
    assert _portal_health({"no_data": True}, "no_content", None, None) == "empty_snapshots"
    assert _portal_health({"no_data": True}, "empty", None, None) == "delivery_not_ready"


def test_unknown_no_data_reason_defaults_to_waiting():
    assert _portal_health({"no_data": True}, "", None, None) == "waiting_for_portal_data"
    assert _portal_health({"no_data": True}, "weird", None, None) == "waiting_for_portal_data"


def test_no_data_wins_over_a_stale_age():
    # if the portal reports no data this poll, that reason is more informative
    # than a stale capture age from a previous snapshot
    assert _portal_health({"no_data": True}, "no_content", 99 * _HOUR, 72 * _HOUR) == "empty_snapshots"


def test_every_result_is_a_declared_state():
    for data, reason in (
        ({"no_data": False}, ""),
        ({"no_data": True}, "no_request"),
        ({"no_data": True}, "no_content"),
        ({"no_data": True}, "empty"),
        ({"no_data": True}, ""),
    ):
        assert _portal_health(data, reason, 99 * _HOUR, 72 * _HOUR) in PORTAL_HEALTH_STATES
