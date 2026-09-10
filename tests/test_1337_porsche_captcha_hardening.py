# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#1337 — hardening of the Porsche captcha config-flow step (G1/G3/G4/G7).

Covers the in-flow GitHub report affordance (must be PII-free), the bounded
captcha loop (cooldown abort after repeated challenges — repeated failures have
locked Porsche accounts), clean give-up aborts instead of re-showing a consumed
captcha, the blank-submit guard, the transient network re-show, and that
Reconfigure now survives a captcha instead of propagating it uncaught.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.vag_connect.config_flow import (
    CONF_CAPTCHA_CODE,
    VagConnectConfigFlow,
)
from custom_components.vag_connect.const import (
    CONF_BRAND,
    CONF_PASSWORD,
    CONF_USERNAME,
    DOMAIN,
)
from custom_components.vag_connect.cariad.exceptions import PorscheCaptchaRequiredError

_VALIDATE = "custom_components.vag_connect.config_flow._validate_credentials"
_IMG = "data:image/svg+xml;base64,PHN2Zz48L3N2Zz4="


def _flow() -> VagConnectConfigFlow:
    f = VagConnectConfigFlow()
    f.hass = MagicMock()
    f.context = {}
    f.handler = DOMAIN
    f.flow_id = "test"
    f._pending_username = "secret-user@example.com"
    f._pending_password = "hunter2-secret"
    f._pending_entry_data = {}
    f._porsche_captcha_image = _IMG
    f._porsche_captcha_state = "state-abc"
    f._porsche_captcha_verifier = "verifier-xyz"
    f._porsche_captcha_return = "email_password"
    f._porsche_captcha_attempts = 0
    return f


# ── G7: the report URL must never carry anything identifying ───────────────────
class TestReportUrlIsPiiFree:
    def test_well_formed_and_carries_only_non_identifying_context(self) -> None:
        url = VagConnectConfigFlow._porsche_report_url(
            "email_password", "porsche_login_wall", screen="captcha"
        )
        assert url.startswith(
            "https://github.com/its-me-prash/vwgroup-connect-ha/issues/new?"
        )
        assert "porsche_login_wall" in url  # error key is fine (not PII)
        assert "email_password" in url      # step name is fine (not PII)

    def test_never_embeds_credentials_state_or_secrets(self) -> None:
        # Build a URL the way every call site does, then prove the sensitive
        # values the flow is holding can NEVER reach the query string — the
        # helper simply takes no such argument (redaction by construction).
        url = VagConnectConfigFlow._porsche_report_url(
            "reauth", "porsche_captcha_cooldown"
        )
        for leak in (
            "secret-user@example.com", "hunter2-secret",
            "state-abc", "verifier-xyz", _IMG, "password",
        ):
            assert leak not in url


# ── G3/G4: bounded, clean captcha step behavior ────────────────────────────────
@pytest.mark.asyncio
async def test_blank_submit_shows_missing_error_without_calling_server() -> None:
    f = _flow()
    with patch(_VALIDATE, new=AsyncMock()) as val:
        res = await f.async_step_porsche_captcha({CONF_CAPTCHA_CODE: "   "})
    val.assert_not_awaited()  # never hit Porsche Auth0 on a blank submit
    assert res["type"] == "form"
    assert res["errors"]["base"] == "missing_captcha"
    assert "report_url" in res["description_placeholders"]


@pytest.mark.asyncio
async def test_chained_captcha_loop_is_bounded_with_cooldown_abort() -> None:
    f = _flow()
    err = PorscheCaptchaRequiredError(_IMG, "state-2", "verifier-2")
    with patch(_VALIDATE, new=AsyncMock(side_effect=err)):
        r1 = await f.async_step_porsche_captcha({CONF_CAPTCHA_CODE: "AAAA"})
        r2 = await f.async_step_porsche_captcha({CONF_CAPTCHA_CODE: "BBBB"})
        r3 = await f.async_step_porsche_captcha({CONF_CAPTCHA_CODE: "CCCC"})
    assert r1["type"] == "form" and r1["errors"]["base"] == "captcha_retry"
    assert r2["type"] == "form"
    # bounded: the 3rd attempt stops instead of hammering on / risking a lock
    assert r3["type"] == "abort"
    assert r3["reason"] == "porsche_captcha_cooldown"
    assert "report_url" in r3["description_placeholders"]


@pytest.mark.asyncio
async def test_non_wall_rejection_aborts_clean_not_reshowing_dead_captcha() -> None:
    f = _flow()
    with patch(_VALIDATE, new=AsyncMock(side_effect=ValueError("invalid_credentials"))):
        res = await f.async_step_porsche_captcha({CONF_CAPTCHA_CODE: "AAAA"})
    assert res["type"] == "abort"
    assert res["reason"] == "porsche_captcha_failed"
    assert "report_url" in res["description_placeholders"]


@pytest.mark.asyncio
async def test_post_password_wall_aborts_with_report() -> None:
    f = _flow()
    with patch(_VALIDATE, new=AsyncMock(side_effect=ValueError("porsche_login_wall"))):
        res = await f.async_step_porsche_captcha({CONF_CAPTCHA_CODE: "AAAA"})
    assert res["type"] == "abort"
    assert res["reason"] == "porsche_login_wall"
    assert "report_url" in res["description_placeholders"]


@pytest.mark.asyncio
async def test_transient_network_error_reshows_form_not_abort() -> None:
    f = _flow()
    with patch(_VALIDATE, new=AsyncMock(side_effect=ValueError("cannot_connect"))):
        res = await f.async_step_porsche_captcha({CONF_CAPTCHA_CODE: "AAAA"})
    assert res["type"] == "form"  # retryable — the challenge may still be valid
    assert res["errors"]["base"] == "cannot_connect"


# ── G1: Reconfigure survives a Porsche captcha instead of crashing ─────────────
@pytest.mark.asyncio
async def test_reconfigure_routes_captcha_to_step_instead_of_crashing() -> None:
    f = VagConnectConfigFlow()
    f.hass = MagicMock()
    entry = MagicMock()
    entry.entry_id = "e1"
    entry.unique_id = "porsche_a@b.com"
    entry.data = {}
    f.hass.config_entries.async_get_entry = MagicMock(return_value=entry)
    f.context = {"entry_id": "e1"}
    f.handler = DOMAIN
    f.flow_id = "test"
    err = PorscheCaptchaRequiredError(_IMG, "st", "ver")
    with patch(_VALIDATE, new=AsyncMock(side_effect=err)):
        res = await f.async_step_reconfigure({
            CONF_BRAND: "porsche",
            CONF_USERNAME: "a@b.com",
            CONF_PASSWORD: "pw",
        })
    assert res["type"] == "form"
    assert res["step_id"] == "porsche_captcha"
    assert f._porsche_captcha_return == "reconfigure"
    assert f._porsche_reconfigure_entry_id == "e1"


# ── strings integrity: every new reason/error exists + placeholders wired ──────
def test_new_strings_present_and_report_placeholder_wired() -> None:
    import json
    import pathlib

    base = pathlib.Path(__file__).resolve().parents[1] / "custom_components" / "vag_connect"
    cfg = json.loads((base / "strings.json").read_text(encoding="utf-8"))["config"]
    assert "missing_captcha" in cfg["error"]
    assert "captcha_retry" in cfg["error"]
    for key in (
        "porsche_captcha_failed", "porsche_captcha_cooldown",
        "reconfigure_failed", "reauth_failed",
    ):
        assert key in cfg["abort"], key
    assert "{report_url}" in cfg["abort"]["porsche_login_wall"]
    assert "{report_url}" in cfg["abort"]["porsche_captcha_failed"]
    assert "{report_url}" in cfg["abort"]["porsche_captcha_cooldown"]
    assert "{report_url}" in cfg["step"]["porsche_captcha"]["description"]
