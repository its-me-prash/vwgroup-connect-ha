# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#465/#1027 — a SUPPLEMENTARY EU Data Act portal hits VW Group's sign-in
interstitials (updated Terms & Conditions, marketing consent, a portal step) at
RUNTIME, past setup, so the setup-path Repair never fired and the user (foobarth,
Skoda) saw only a log line. The portal now records the actionable reason in
``last_login_interaction`` and the coordinator surfaces the matching Repair each
poll, self-clearing on the next good login.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from custom_components.vag_connect.cariad.auth._eu_data_act import (
    EUDataActConnector,
    classify_portal_login_failure,
)
from custom_components.vag_connect.const import CONF_BRAND, DOMAIN
from custom_components.vag_connect.coordinator import VagConnectCoordinator


class TestClassifierTag:
    def test_terms_page_is_tagged_terms_and_conditions(self) -> None:
        # The reason string the portal records comes straight from the
        # classifier's log_ctx, so pin it.
        exc, ctx = classify_portal_login_failure(
            "https://identity.vwgroup.io/signin-service/v1/CID/terms-and-conditions",
            '<script>window._IDK = {templateModel: {"template":"termsAndConditions"}};</script>',
        )
        assert ctx.get("classified") == "terms_and_conditions"

    def test_fresh_connector_has_no_interaction(self) -> None:
        c = EUDataActConnector(MagicMock())
        assert c.last_login_interaction == ""

    def test_set_bearer_clears_interaction(self) -> None:
        c = EUDataActConnector(MagicMock())
        c.last_login_interaction = "terms_and_conditions"
        c.set_bearer("tok")
        assert c.last_login_interaction == ""


def _fake_self(interaction: str, *, prev: str = "", supplementary: bool = True):
    portal = SimpleNamespace(
        last_login_interaction=interaction,
        last_no_data_reason="",
    )
    client = SimpleNamespace(
        _eu_portal=None if supplementary else portal,
        _supplementary_eu_portal=portal if supplementary else None,
    )
    entry = SimpleNamespace(
        entry_id="e1",
        data={CONF_BRAND: "skoda"},
    )
    return SimpleNamespace(
        _cariad_client=client,
        entry=entry,
        hass=MagicMock(),
        _portal_interaction_reason=prev,
    )


class TestCoordinatorSurfacing:
    def test_terms_interaction_raises_the_repair_and_suppresses_no_data(self) -> None:
        me = _fake_self("terms_and_conditions")
        with patch(
            "custom_components.vag_connect.repairs.raise_issue_auth_required"
        ) as raise_repair, patch(
            "homeassistant.helpers.issue_registry.async_delete_issue"
        ) as delete_issue, patch(
            "homeassistant.helpers.issue_registry.async_create_issue"
        ) as create_issue:
            VagConnectCoordinator._update_data_act_no_data_repair(me)
        raise_repair.assert_called_once()
        args, kwargs = raise_repair.call_args
        assert args[2] == "terms_and_conditions"
        assert kwargs.get("brand") == "skoda"
        # the "no data" repair must be cleared, not raised, while blocked
        assert not create_issue.called
        assert any(
            "data_act_no_data_e1" in str(c.args) for c in delete_issue.call_args_list
        )

    def test_no_interaction_clears_the_interaction_repairs(self) -> None:
        # simulate a prior poll that raised the T&C Repair; now login recovered
        me = _fake_self("", prev="terms_and_conditions")
        with patch(
            "custom_components.vag_connect.repairs.raise_issue_auth_required"
        ) as raise_repair, patch(
            "homeassistant.helpers.issue_registry.async_delete_issue"
        ) as delete_issue, patch(
            "homeassistant.helpers.issue_registry.async_create_issue"
        ):
            VagConnectCoordinator._update_data_act_no_data_repair(me)
        raise_repair.assert_not_called()
        cleared = {str(c.args) for c in delete_issue.call_args_list}
        assert any("e1_terms_and_conditions" in s for s in cleared)

    def test_primary_portal_interaction_is_also_surfaced(self) -> None:
        me = _fake_self("marketing_consent", supplementary=False)
        with patch(
            "custom_components.vag_connect.repairs.raise_issue_auth_required"
        ) as raise_repair, patch(
            "homeassistant.helpers.issue_registry.async_delete_issue"
        ), patch(
            "homeassistant.helpers.issue_registry.async_create_issue"
        ):
            VagConnectCoordinator._update_data_act_no_data_repair(me)
        raise_repair.assert_called_once()
        assert raise_repair.call_args.args[2] == "marketing_consent"
