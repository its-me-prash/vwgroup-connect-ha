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
    # #465 — a VW-side portal outage/throttle (5xx/429) is its own state, distinct
    # from "delivery not ready", so a fault doesn't read as a normal wait.
    assert _portal_health({"no_data": True}, "portal_error", None, None) == "portal_error"


def test_unknown_no_data_reason_defaults_to_waiting():
    assert _portal_health({"no_data": True}, "", None, None) == "waiting_for_portal_data"
    assert _portal_health({"no_data": True}, "weird", None, None) == "waiting_for_portal_data"


def test_supplementary_portal_reason_honoured_without_no_data_flag():
    # #1273 (@riteman): EU-DA is a SUPPLEMENTARY channel, so the merged data comes
    # from the primary (vw.de / BFF) and carries no ``no_data`` flag — yet the
    # portal never delivered a snapshot. The connector's own reason must still
    # classify it instead of falling through to ``ok``.
    assert _portal_health({"no_data": False}, "no_request", None, None) == "waiting_for_portal_data"
    assert _portal_health({"no_data": False}, "no_content", None, None) == "empty_snapshots"
    assert _portal_health({"no_data": False}, "empty", None, None) == "delivery_not_ready"
    # a merged dict with no ``no_data`` key at all (primary never set it) also honours the reason
    assert _portal_health({}, "no_content", None, None) == "empty_snapshots"
    # even with a fresh-looking capture age from the primary channel, the portal's
    # own no-data reason wins — this sensor reports on the portal, not on vw.de
    assert _portal_health({"no_data": False}, "no_content", 60.0, 72 * _HOUR) == "empty_snapshots"


def test_reason_cleared_stays_ok_when_data_present():
    # a genuinely delivered portal (reason cleared back to "") is still ok
    assert _portal_health({"no_data": False}, "", 60.0, 72 * _HOUR) == "ok"


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
        ({"no_data": True}, "portal_error"),
        ({"no_data": True}, ""),
    ):
        assert _portal_health(data, reason, 99 * _HOUR, 72 * _HOUR) in PORTAL_HEALTH_STATES
