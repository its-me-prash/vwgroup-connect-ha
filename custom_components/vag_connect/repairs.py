# Copyright 2026 Prash Balan (@its-me-prash) — Apache License 2.0
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
    exhaustion. Most likely cause: VW updated their app-identifying
    requirements again and our centralized header constants
    (``cariad/_ola_headers.py``) need bumping.

    Args:
        hass: Home Assistant runtime instance.
        entry_id: ConfigEntry ID owning this client.
        brand: ``"seat"`` or ``"cupra"`` — included in the message
            so the user knows which brand-app version to check.
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
        learn_more_url=(
            "https://github.com/its-me-prash/vwgroup-connect-ha/blob/main/"
            "custom_components/vag_connect/cariad/_ola_headers.py"
        ),
    )
    _LOGGER.warning(
        "VW Group Connect OLA-Headers Repair-Issue created: brand=%s "
        "consecutive_403=%d. Likely cause: OLA backend updated app-"
        "identifying requirements. Check for integration update or "
        "use the advanced OptionsFlow override.",
        brand, consecutive_403_count,
    )


def clear_ola_headers_issue(hass: HomeAssistant, entry_id: str) -> None:
    """v2.4.1 — Clear the OLA headers repair issue when 403s stop."""
    ir.async_delete_issue(hass, DOMAIN, f"{entry_id}_ola_headers_outdated")


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


async def async_create_fix_flow(
    hass: HomeAssistant,
    issue_id: str,
    data: dict[str, Any] | None,
) -> RepairsFlow:
    """v2.0.0 — HA RepairsFlow factory. Called when user clicks 'Repair'."""
    entry_id = (data or {}).get("entry_id", "")
    reason = (data or {}).get("reason", "auth_failed")
    return _AuthRepairFlow(entry_id, reason)
