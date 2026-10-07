# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#1740 — the portal-domain user-agent, as the operator asked for it.

Originally written by @VWGroupDatahub against a single module-wide agent. The
agent moved to the portal-domain requests (the ones they asked about) and the
login steps kept their browser string, so these assertions moved with it.
"""
from __future__ import annotations

from custom_components.vag_connect.cariad.auth import _eu_data_act


def test_the_portal_agent_carries_the_version() -> None:
    try:
        _eu_data_act.set_integration_version("9.9.9")
        assert _eu_data_act._portal_user_agent() == "HA_vag_connect/9.9.9"
    finally:
        _eu_data_act.set_integration_version("")


def test_an_unknown_version_falls_back_to_the_bare_product() -> None:
    """Never an agent ending in a bare slash."""
    _eu_data_act.set_integration_version("")
    assert _eu_data_act._portal_user_agent() == "HA_vag_connect"


def test_a_blank_version_is_treated_as_unknown() -> None:
    try:
        _eu_data_act.set_integration_version("   ")
        assert _eu_data_act._portal_user_agent() == "HA_vag_connect"
    finally:
        _eu_data_act.set_integration_version("")


def test_the_login_steps_keep_the_browser_agent() -> None:
    """#388/#393 — the IDP sits behind a WAF that refused a non-browser agent."""
    assert "Mozilla/5.0" in _eu_data_act._USER_AGENT
    assert _eu_data_act._USER_AGENT != _eu_data_act._portal_user_agent()
