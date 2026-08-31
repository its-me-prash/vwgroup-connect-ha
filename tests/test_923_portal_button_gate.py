# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#923 (@naked-head/@dazzzl) — the EU-Data-Act export / data-request buttons
must also be created for a portal feed brought up by the AUTO-KICKOFF path on a
command-capable primary, not only for a read-only portal or the explicit
supplementary toggle.

On such a setup (source_channel ``eu_data_act+website_authproxy``) is_read_only()
is False (the MBB-command carve-out keeps command entities alive) and the
supplementary flag is unset (the portal came from the kickoff, not the options
toggle) — so the old two-clause gate returned False and the buttons never
spawned. naked-head's A/B proved it: flipping only the supplementary flag turned
the buttons on. The gate now also recognises an armed portal connector or a
persisted Custom Data Request identifier.
"""
from __future__ import annotations

from types import SimpleNamespace

from custom_components.vag_connect.coordinator import VagConnectCoordinator
from custom_components.vag_connect.const import (
    CONF_DATA_ACT_IDENTIFIERS,
    CONF_SUPPLEMENTARY_EU_PORTAL,
)


def _coord(*, read_only=False, supp_flag=False, eu_portal=False,
           supp_portal=False, data_ids=None, opt_ids=None):
    s = SimpleNamespace()
    s.is_read_only = lambda: read_only
    entry = SimpleNamespace(data={}, options={})
    if supp_flag:
        entry.data[CONF_SUPPLEMENTARY_EU_PORTAL] = True
    if data_ids:
        entry.data[CONF_DATA_ACT_IDENTIFIERS] = data_ids
    if opt_ids:
        entry.options[CONF_DATA_ACT_IDENTIFIERS] = opt_ids
    s.entry = entry
    s._cariad_client = SimpleNamespace(
        _eu_portal=object() if eu_portal else None,
        _supplementary_eu_portal=object() if supp_portal else None,
    )
    return s


def _gate(s) -> bool:
    return VagConnectCoordinator.has_data_act_portal_channel(s)


# ── existing clauses still hold ──────────────────────────────────────────────

def test_read_only_portal_true():
    assert _gate(_coord(read_only=True)) is True


def test_supplementary_toggle_true():
    assert _gate(_coord(supp_flag=True)) is True


# ── the #923 auto-kickoff cases (were False pre-fix) ─────────────────────────

def test_auto_kickoff_armed_primary_portal_connector():
    # naked-head: command primary, portal via auto-kickoff, no toggle.
    assert _gate(_coord(eu_portal=True)) is True


def test_auto_kickoff_armed_supplementary_portal_connector():
    assert _gate(_coord(supp_portal=True)) is True


def test_persisted_identifier_in_data_is_durable_anchor():
    # after reload the connector may not be armed yet, but the kickoff persisted
    # an active request identifier — the durable anchor keeps the buttons.
    assert _gate(_coord(data_ids={"WVW...": "abc"})) is True


def test_persisted_identifier_in_options_before_fold():
    # the kickoff writes to options; the options→data fold can lag a session.
    assert _gate(_coord(opt_ids={"WVW...": "abc"})) is True


# ── the guard: a plain command entry with no portal gets NO buttons ──────────

def test_plain_command_entry_without_portal_is_false():
    assert _gate(_coord()) is False
