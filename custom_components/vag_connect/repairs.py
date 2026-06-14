# Copyright 2026 Prash Balan (@its-me-prash) — Apache License 2.0
# SPDX-License-Identifier: Apache-2.0
"""
VAG Connect Repair-Flows für Auth-Probleme + Quota-Warnings.

Wenn Login fehlschlägt (2FA, T&C, gesperrter Account) ODER die API-Quota
zur Neige geht, erscheint eine persistente Warnung im HA UI unter
Einstellungen → System → Reparaturen. Der Nutzer kann direkt reagieren
ohne in die Logs schauen zu müssen.

v1.19.4 (Bundle 1):
- Brand-aware deeplinks für T&C-Repair (Skoda → skodaid.vwgroup.io,
  VW EU → vwid.vwgroup.io, Audi → my.audi.com, SEAT/CUPRA → seat-cupra.cloud)
- Quota-Warning Repair-Issue (extension von v1.19.1 quota sensor)
v2.0.0 (Big-Bang):
- Reasons that the user can ACT on (invalid_credentials, two_factor_required,
  terms_and_conditions, marketing_consent) now ship as ``is_fixable=True``.
  Clicking "Repair" in HA UI triggers the matching config-flow step so the
  user fixes the credentials in one click instead of removing + re-adding
  the integration.
"""

from typing import Any

import logging

import voluptuous as vol

from homeassistant import data_entry_flow
from homeassistant.components.repairs import RepairsFlow
from homeassistant.core import HomeAssistant
import homeassistant.helpers.issue_registry as ir

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

# v2.0.0 — reasons whose remediation maps to a config-flow step. When one
# of these issues is created, HA shows a "Repair" button; clicking it kicks
# off the linked flow ("reauth" for credentials, "reconfigure" for setting
# changes). Everything else stays informational (is_fixable=False).
_FIXABLE_REASONS: dict[str, str] = {
    "invalid_credentials":   "reauth",
    "two_factor_required":   "reauth",
    # v2.2.0 PR #7/20 (#183 follow-on) — Email-OTP discriminated reason.
    "email_two_factor_required": "reauth",
    "terms_and_conditions":  "reauth",
    "marketing_consent":     "reauth",
}

# v1.19.4 Bundle 1 — Brand-aware deeplinks für T&C-Repair-Issue.
# Wenn IDK-Backend "terms-and-conditions" / "terms_of_use" body sendet,
# zeigt das Repair-Issue einen "Learn more" Link direkt zum Account-
# Portal des passenden Brands (statt generisch zum README). Pattern aus
# skodaconnect/myskoda issues.py — saubere brand-spezifische URLs.
_BRAND_TNC_URLS: dict[str, str] = {
    "skoda":          "https://skodaid.vwgroup.io/landing-page",
    "volkswagen":     "https://vwid.vwgroup.io/account",
    "audi":           "https://my.audi.com",
    "seat":           "https://seat-cupra.cloud.vwgroup.com",
    "cupra":          "https://seat-cupra.cloud.vwgroup.com",
    "porsche":        "https://my.porsche.com",
    "volkswagen_na":  "https://www.vw.com/myvw",
}

# Default fallback URL when brand is unknown (e.g. legacy entries).
_DEFAULT_LEARN_URL = "https://github.com/its-me-prash/vag-connect-ha/blob/main/README.md"


def _learn_url_for_reason(brand: str | None, reason: str) -> str:
    """Return the most actionable learn-more URL for a repair reason.

    For T&C / marketing-consent reasons: brand-specific account-portal
    deeplink so user can accept the new terms in one click. For other
    reasons: integration README.
    """
    if reason in ("terms_and_conditions", "marketing_consent") and brand:
        return _BRAND_TNC_URLS.get(brand.lower(), _DEFAULT_LEARN_URL)
    return _DEFAULT_LEARN_URL


def raise_issue_auth_required(
    hass: HomeAssistant, entry_id: str, reason: str, *, brand: str | None = None,
) -> None:
    """
    Erstellt ein HA-Repair-Issue wenn die Authentifizierung fehlschlägt.
    Erscheint unter Einstellungen → System → Reparaturen.
    Surfaces actionable guidance in the HA Repairs dashboard.

    v1.19.4 — accepts optional ``brand`` for brand-aware learn-more
    deeplinks. Backwards-compatible: callers without brand still work.
    """
    issue_map = {
        "two_factor_required": (
            ir.IssueSeverity.WARNING,
            "two_factor_required",
        ),
        # v2.2.0 PR #7/20 (#183 follow-on) — distinct copy from generic
        # 2FA so Email-OTP users know to check inbox (not app).
        "email_two_factor_required": (
            ir.IssueSeverity.WARNING,
            "email_two_factor_required",
        ),
        "terms_and_conditions": (
            ir.IssueSeverity.ERROR,
            "terms_and_conditions",
        ),
        "marketing_consent": (
            ir.IssueSeverity.WARNING,
            "marketing_consent",
        ),
        "too_many_requests": (
            ir.IssueSeverity.WARNING,
            "too_many_requests",
        ),
        "invalid_credentials": (
            ir.IssueSeverity.ERROR,
            "invalid_credentials",
        ),
    }

    severity, translation_key = issue_map.get(
        reason, (ir.IssueSeverity.ERROR, "auth_failed")
    )

    # v2.0.0 — fixable reasons get is_fixable=True so HA UI shows a
    # "Repair" button that delegates to async_create_fix_flow below.
    is_fixable = reason in _FIXABLE_REASONS

    ir.async_create_issue(
        hass,
        DOMAIN,
        f"{entry_id}_{reason}",
        is_fixable=is_fixable,
        is_persistent=False,
        severity=severity,
        translation_key=translation_key,
        # v2.14.3/.4 — several of these titles/descriptions embed {brand} and
        # {username}; without the placeholders the frontend fails to render and
        # spams "MISSING_VALUE" errors. Supply both for every auth repair (the
        # email_two_factor_required TITLE also had {brand} dropped in v2.14.4 so
        # even pre-2.14.3 issues lingering in the registry render cleanly).
        translation_placeholders={
            "brand": (brand or "").title() or "VW Group",
            "username": "",
        },
        learn_more_url=_learn_url_for_reason(brand, reason),
        data={"entry_id": entry_id, "reason": reason},
    )
    _LOGGER.warning(
        "VAG Connect Repair-Issue erstellt: %s (brand=%s, fixable=%s)",
        reason, brand, is_fixable,
    )


def clear_auth_issues(hass: HomeAssistant, entry_id: str) -> None:
    """Alle Auth-Issues für diesen Entry löschen (nach erfolgreichem Login)."""
    for reason in ["two_factor_required", "email_two_factor_required",
                   "terms_and_conditions",
                   "marketing_consent", "too_many_requests",
                   "invalid_credentials", "auth_failed"]:
        ir.async_delete_issue(hass, DOMAIN, f"{entry_id}_{reason}")


def raise_issue_requirements_conflict(hass: HomeAssistant) -> None:
    """Raise a repair issue for configuration problems."""
    ir.async_create_issue(
        hass,
        DOMAIN,
        "requirements_conflict",
        is_fixable=False,
        is_persistent=True,
        severity=ir.IssueSeverity.ERROR,
        translation_key="requirements_conflict",
        learn_more_url="https://github.com/its-me-prash/vag-connect-ha/issues",
    )


# v1.19.4 Bundle 1 — Quota Warning Repair-Issue.
# Extension von v1.19.1 (X-RateLimit-Remaining sensor): jetzt auch
# proactive UI-Warning wenn der user kurz vor dem täglichen Quota-Cap
# steht. Pycupra-Pattern als persistent_notification (older HA), wir
# nutzen Repair-Issue (more discoverable + auto-clears wenn quota
# sich wieder erholt).

# Threshold-Konstanten — community research (pycupra README) zeigt
# MyCupra/MySeat ~1500/day quota; warning bei 100 ist ~6.7%, critical
# bei 25 ist ~1.7%. User hat dann genug Zeit Polling-Interval zu
# erhöhen via OptionsFlow bevor der Cap erreicht wird.
QUOTA_WARN_THRESHOLD = 100
QUOTA_CRITICAL_THRESHOLD = 25


def raise_issue_quota_low(
    hass: HomeAssistant,
    entry_id: str,
    *,
    remaining: int,
    limit: int | None = None,
    critical: bool = False,
) -> None:
    """v1.19.4 Bundle 1 — Repair-Issue wenn API-Quota zur Neige geht.

    Wird vom Coordinator gerufen wenn ``requests_remaining_today``
    unter ``QUOTA_WARN_THRESHOLD`` (oder ``QUOTA_CRITICAL_THRESHOLD``)
    fällt. Idempotent — wiederholtes Rufen mit gleicher issue_id
    überschreibt nur den state, kein neuer notification spam.

    Args:
        hass: HomeAssistant instance
        entry_id: Config entry ID for per-entry isolation
        remaining: Current X-RateLimit-Remaining value
        limit: Total X-RateLimit-Limit (for percentage display)
        critical: True if remaining < CRITICAL_THRESHOLD (more
            urgent, ERROR severity); False = WARNING.
    """
    severity = ir.IssueSeverity.ERROR if critical else ir.IssueSeverity.WARNING
    translation_key = "quota_critical" if critical else "quota_low"
    placeholders = {"remaining": str(remaining)}
    if limit is not None:
        placeholders["limit"] = str(limit)
        placeholders["pct"] = f"{(remaining / limit * 100):.1f}" if limit else "?"
    ir.async_create_issue(
        hass,
        DOMAIN,
        f"{entry_id}_quota_low",
        is_fixable=False,
        is_persistent=False,
        severity=severity,
        translation_key=translation_key,
        translation_placeholders=placeholders,
        learn_more_url="https://github.com/its-me-prash/vag-connect-ha/blob/main/docs/FAQ.md#api-quota",
    )
    _LOGGER.info(
        "VAG Connect Quota-Warning Repair-Issue erstellt: %d remaining "
        "(critical=%s)",
        remaining, critical,
    )


def clear_quota_issue(hass: HomeAssistant, entry_id: str) -> None:
    """v1.19.4 — Quota-Warning Repair-Issue auflösen wenn remaining
    sich erholt hat (z.B. midnight reset).
    """
    ir.async_delete_issue(hass, DOMAIN, f"{entry_id}_quota_low")


def raise_issue_ola_headers_outdated(
    hass: HomeAssistant,
    entry_id: str,
    brand: str,
    consecutive_403_count: int,
) -> None:
    """v2.4.1 (#281+#282) — OLA defense-in-depth Layer 4.

    Raise an HA Repair issue when the OLA backend has returned 403
    consecutively despite our header-injection + fallback chain
    exhaustion. As of 2026-06 the cause is a VW server-side access
    revocation for SEAT/CUPRA — NOT a header/app-version problem the
    user can fix. The notice text is worded accordingly (no header-bump
    or OptionsFlow-override advice; data falls back to the read-only EU
    Data Act portal where available).

    Args:
        hass: Home Assistant runtime instance.
        entry_id: ConfigEntry ID owning this client.
        brand: ``"seat"`` or ``"cupra"`` — included in the message
            so the user knows which brand is affected.
        consecutive_403_count: how many in a row we've seen — included
            in the message to give the user a sense of certainty
            (10+ = high confidence, 5-9 = possible).
    """
    ir.async_create_issue(
        hass,
        DOMAIN,
        f"{entry_id}_ola_headers_outdated",
        is_fixable=False,
        is_persistent=True,
        severity=ir.IssueSeverity.WARNING,
        translation_key="ola_headers_outdated",
        translation_placeholders={
            "brand": brand.upper(),
            "count": str(consecutive_403_count),
        },
    )
    _LOGGER.warning(
        "VW Group Connect OLA Repair-Issue created: brand=%s "
        "consecutive_403=%d. Cause: VW server-side online-services "
        "access revocation for SEAT/CUPRA (not a fixable header/app-"
        "version problem); data falls back to the read-only EU Data "
        "Act portal where available.",
        brand, consecutive_403_count,
    )


def clear_ola_headers_issue(hass: HomeAssistant, entry_id: str) -> None:
    """v2.4.1 — Clear the OLA headers repair issue when 403s stop."""
    ir.async_delete_issue(hass, DOMAIN, f"{entry_id}_ola_headers_outdated")


# v2.9.0 — VW account-lock detection.
# The 2026-05-31 ecosystem-wide VW Auth chaos surfaced a new failure
# mode: when an integration retries auth too aggressively after a
# failed token exchange, VW (and Audi via the same IDP) temporarily
# lock the underlying brand account for ~24h. The lock manifests as
# repeated HTTP 423 (Locked) responses on /auth/v1/idk/oidc/token,
# sometimes 403 with a body indicating throttling. Multiple competitor
# integrations had users hit this between 2026-05-31 and 2026-06-02
# (oliverrahner on volkswagencarnet#332 explicitly reported the lock-
# and-unlock cycle).
#
# Our v1.8.7 token-refresh-storm protection caps refreshes at 3/hour
# but cannot prevent the lock once VW's threshold is crossed. The
# detection here closes the loop: when we see 3 lock-class responses
# in 30 minutes, surface a Repair issue telling the user to (a) wait
# for the lock to expire, (b) raise scan_interval to reduce future
# pressure, (c) optionally switch to read-only Data Act portal mode
# while the lock is active.
_ACCOUNT_LOCK_THRESHOLD = 3
_ACCOUNT_LOCK_WINDOW_S = 1800


def raise_issue_account_locked(
    hass: HomeAssistant,
    entry_id: str,
    brand: str,
    last_status: int,
) -> None:
    """Surface a VW account-lock detection in HA Repairs.

    Called by the coordinator after ``_ACCOUNT_LOCK_THRESHOLD`` token-
    refresh attempts inside ``_ACCOUNT_LOCK_WINDOW_S`` have returned
    HTTP 423 or 403-with-throttle-marker. Idempotent: repeated calls
    with the same ``issue_id`` refresh in place.

    Args:
        hass: Home Assistant instance.
        entry_id: Config entry id (per-entry isolation, two accounts
            on different entries get two issues).
        brand: Brand name for the placeholder text. Lower-case.
        last_status: HTTP status of the most recent locked response,
            included in the placeholder so the user sees the exact
            backend signal.
    """
    issue_id = f"{entry_id}_account_locked"
    # is_fixable=False on purpose: there is no integration-side action
    # that unlocks the account. The user just reads the description,
    # waits, and the issue auto-clears on the next successful auth.
    ir.async_create_issue(
        hass,
        DOMAIN,
        issue_id,
        is_fixable=False,
        severity=ir.IssueSeverity.WARNING,
        translation_key="account_locked",
        translation_placeholders={
            "brand": brand,
            "last_status": str(last_status),
        },
    )


def clear_account_locked_issue(hass: HomeAssistant, entry_id: str) -> None:
    """Clear the account-lock repair issue once a successful auth lands."""
    ir.async_delete_issue(hass, DOMAIN, f"{entry_id}_account_locked")


# v2.8.0 (Action #5) — DAG -> hybrid_full degradation Repair issue.
# Brands listed in DAG_ENABLED_BRANDS (Audi/Skoda/SEAT/CUPRA) prefer the
# browser-login Device Authorization Grant flow because it yields a real
# refresh_token from the IDP and avoids the 2-hour re-login cycle that
# hybrid_full forces. When DAG fails (network outage, missing cookies,
# IDP downtime, etc.) the multi-strategy resolver in cariad/api/base.py
# silently falls back to hybrid_full and the integration keeps working
# in a degraded mode. The user notices "the integration logs me out a
# lot" without understanding why. This Repair issue surfaces the
# degradation in the HA UI and offers two guided remediations: re-run
# the browser-login setup, or pin the read-only Data Act portal mode.
DAG_DEGRADED_BRANDS: frozenset[str] = frozenset({"audi", "skoda", "seat", "cupra"})


def raise_issue_auth_strategy_degraded(
    hass: HomeAssistant,
    entry_id: str,
    brand: str,
    current_strategy: str,
) -> None:
    """v2.8.0 — Surface the DAG → hybrid_full degradation in HA Repairs.

    Called by the coordinator's poll loop after it has seen the same
    degraded strategy for at least 3 consecutive successful polls.
    Idempotent — repeated calls with the same issue_id refresh in place.

    Args:
        hass: Home Assistant runtime instance.
        entry_id: ConfigEntry ID — included in the issue_id so each
            account gets its own Repair entry when the user has set up
            more than one brand.
        brand: lowercase brand key from CONF_BRAND. Included in the
            translation placeholders so the title/description can name
            the brand (uppercased for display).
        current_strategy: actual TokenSet.strategy we observed. Carried
            into the translation placeholders so the user sees the
            same string we logged at DEBUG level.
    """
    ir.async_create_issue(
        hass,
        DOMAIN,
        f"{entry_id}_auth_strategy_degraded",
        is_fixable=True,
        is_persistent=False,
        severity=ir.IssueSeverity.WARNING,
        translation_key="auth_strategy_degraded",
        translation_placeholders={
            "brand": brand.upper(),
            "strategy": current_strategy,
        },
        data={
            "entry_id": entry_id,
            "reason": "auth_strategy_degraded",
            "brand": brand,
        },
        learn_more_url=(
            "https://github.com/its-me-prash/vwgroup-connect-ha/blob/main/"
            "docs/auth-strategies.md"
        ),
    )
    _LOGGER.warning(
        "VW Group Connect auth-strategy degraded Repair-Issue created: "
        "brand=%s current_strategy=%s (DAG unavailable — falling back to "
        "hybrid_full 2-hour re-login cycle)",
        brand, current_strategy,
    )


def clear_auth_strategy_degraded_issue(
    hass: HomeAssistant, entry_id: str
) -> None:
    """v2.8.0 — Clear the degradation issue once DAG is healthy again.

    Called by the coordinator when ``TokenSet.strategy`` flips back to
    ``"device_grant"``. Same delete-by-id pattern as the OLA helper.
    """
    ir.async_delete_issue(hass, DOMAIN, f"{entry_id}_auth_strategy_degraded")


# ─── v2.0.0 Repair-Flow Handler ──────────────────────────────────────────
class _AuthRepairFlow(RepairsFlow):
    """v2.0.0 — Generic repair flow for auth-related issues.

    Delegates to the matching config-flow step (reauth or reconfigure) so
    the user fixes credentials without removing the integration.
    """

    def __init__(self, entry_id: str, reason: str) -> None:
        self._entry_id = entry_id
        self._reason = reason

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> data_entry_flow.FlowResult:
        return await self.async_step_confirm()

    async def async_step_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> data_entry_flow.FlowResult:
        if user_input is None:
            return self.async_show_form(
                step_id="confirm",
                description_placeholders={"reason": self._reason},
            )
        # User confirmed — kick off the matching config_flow step
        flow_step = _FIXABLE_REASONS.get(self._reason, "reauth")
        await self.hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": flow_step, "entry_id": self._entry_id},
        )
        return self.async_create_entry(title="", data={})


# v2.8.0 (Action #5) — auth-strategy degradation guided flow.
# Two options for the user to choose from on the Repair form:
#   - ``rerun_browser_login`` → kicks the reauth config-flow which routes
#     DAG-eligible brands through the browser-login (Device Grant) path
#     again. Best fix when the original DAG failure was a transient
#     network or IDP glitch.
#   - ``switch_to_data_act_portal`` → pins
#     ``CONF_PREFERRED_AUTH_STRATEGY`` = ``"data_act_portal"`` in
#     ``entry.options``. Stays in read-only Data Act mode without
#     retrying the DAG QR-code dance. Best fix when the user does not
#     have access to the browser-login flow right now and is OK with
#     the read-only entitlement until they can re-run setup.
_DAG_FLOW_OPTION_RERUN_DAG  = "rerun_browser_login"
_DAG_FLOW_OPTION_DATA_ACT   = "switch_to_data_act_portal"
_DAG_FLOW_VALID_CHOICES = (
    _DAG_FLOW_OPTION_RERUN_DAG,
    _DAG_FLOW_OPTION_DATA_ACT,
)


class _AuthStrategyDegradedFlow(RepairsFlow):
    """v2.8.0 — Guided remediation for DAG → hybrid_full degradation.

    Two-button form. Each button persists a clear user intent before
    delegating to either the reauth config flow (re-run browser login)
    or an in-place entry.options update (pin Data Act portal).
    """

    def __init__(self, entry_id: str, brand: str) -> None:
        self._entry_id = entry_id
        self._brand = brand

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> data_entry_flow.FlowResult:
        return await self.async_step_choose_remediation()

    async def async_step_choose_remediation(
        self, user_input: dict[str, Any] | None = None
    ) -> data_entry_flow.FlowResult:
        if user_input is None:
            return self.async_show_form(
                step_id="choose_remediation",
                data_schema=vol.Schema({
                    vol.Required("remediation"): vol.In(_DAG_FLOW_VALID_CHOICES),
                }),
                description_placeholders={"brand": self._brand.upper()},
            )

        choice = user_input.get("remediation", _DAG_FLOW_OPTION_RERUN_DAG)
        if choice == _DAG_FLOW_OPTION_DATA_ACT:
            from .const import CONF_PREFERRED_AUTH_STRATEGY  # noqa: PLC0415
            entry = self.hass.config_entries.async_get_entry(self._entry_id)
            if entry is not None:
                self.hass.config_entries.async_update_entry(
                    entry,
                    options={
                        **entry.options,
                        CONF_PREFERRED_AUTH_STRATEGY: "data_act_portal",
                    },
                )
                _LOGGER.info(
                    "VW Group Connect auth-strategy degraded: user pinned "
                    "read-only Data Act portal for brand=%s entry=%s",
                    self._brand, self._entry_id,
                )
            # Clear the Repair issue now that the user has chosen the
            # explicit-degraded posture — no further nag.
            clear_auth_strategy_degraded_issue(self.hass, self._entry_id)
            return self.async_create_entry(title="", data={})

        # Default: re-run browser-login. The reauth config-flow already
        # routes DAG-eligible brands through the device-grant path, so
        # we don't need a separate browser-login source here.
        await self.hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": "reauth", "entry_id": self._entry_id},
        )
        return self.async_create_entry(title="", data={})


async def async_create_fix_flow(
    hass: HomeAssistant,
    issue_id: str,
    data: dict[str, Any] | None,
) -> RepairsFlow:
    """v2.0.0 — HA RepairsFlow factory. Called when user clicks 'Repair'."""
    entry_id = (data or {}).get("entry_id", "")
    reason = (data or {}).get("reason", "auth_failed")
    # v2.8.0 (Action #5) — DAG-degradation Repair has its own guided
    # two-option flow. Other reasons keep the generic
    # ``_AuthRepairFlow`` that simply delegates to reauth.
    if reason == "auth_strategy_degraded":
        brand = (data or {}).get("brand", "")
        return _AuthStrategyDegradedFlow(entry_id, brand)
    return _AuthRepairFlow(entry_id, reason)
