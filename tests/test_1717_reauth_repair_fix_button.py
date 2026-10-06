# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#1717 — the "needs re-login" repair told you to navigate instead of doing it.

Raised by @Ra72xx on #1679. When the volkswagen.de session cannot resume,
Volkswagen wants the e-mail one-time code again — unavoidable, only the user has
it. What was avoidable was everything before that: the notice said "open this
integration's options and re-run Add a Volkswagen.de read channel", so the user
walked Settings → Devices & Services → find the integration → find the *right*
entry (several exist with two accounts or two cars) → Configure → tick the box
in the full options form → submit, and only then reached the login.

The stated reason it was not fixable — "re-login needs the email-OTP via the
OptionsFlow" — was not the real one. The generic auth repair flow already shows
a confirm form and hands the user into the matching step; it just starts a
**config** flow, and the volkswagen.de login step lives on the **options** flow,
which that launcher cannot reach.

So: the repair becomes fixable, its flow starts the options flow for its own
entry carrying a "go straight to the volkswagen.de step" marker, and the options
flow honours it. The one-time code step is untouched.
"""
from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

ENTRY = "01ABCDEFGHIJKLMNOPQRSTUVWX"


# ── The repair is now fixable, and carries what the flow needs ───────────────

def test_the_repair_is_fixable_and_carries_its_entry() -> None:
    """``is_fixable`` is what makes Home Assistant draw the Fix button, and the
    flow factory can only route the click if the issue carries entry + reason."""
    from custom_components.vag_connect.repairs import (
        raise_issue_supplementary_reauth,
    )

    hass = MagicMock()
    with patch(
        "custom_components.vag_connect.repairs.ir.async_create_issue"
    ) as create:
        raise_issue_supplementary_reauth(hass, ENTRY)

    kwargs = create.call_args.kwargs
    assert kwargs["is_fixable"] is True, "no Fix button would be drawn"
    assert kwargs["data"]["entry_id"] == ENTRY
    assert kwargs["data"]["reason"] == "supplementary_reauth"
    # The issue id is unchanged, so an already-raised notice is not duplicated.
    assert create.call_args.args[2] == f"{ENTRY}_supplementary_reauth"


def test_the_factory_routes_the_click_to_its_own_flow() -> None:
    """Not the generic auth flow: that one starts a CONFIG flow and would never
    reach the volkswagen.de step."""
    import asyncio

    from custom_components.vag_connect.repairs import (
        _AuthRepairFlow,
        async_create_fix_flow,
    )

    flow = asyncio.new_event_loop().run_until_complete(
        async_create_fix_flow(
            MagicMock(),
            f"{ENTRY}_supplementary_reauth",
            {"entry_id": ENTRY, "reason": "supplementary_reauth"},
        )
    )
    assert not isinstance(flow, _AuthRepairFlow), (
        "routed to the config-flow launcher, which cannot reach an options step"
    )
    assert getattr(flow, "_entry_id", None) == ENTRY


def test_the_other_repairs_still_route_as_before() -> None:
    """Unchanged: a credentials problem still goes to the generic auth flow."""
    import asyncio

    from custom_components.vag_connect.repairs import (
        _AuthRepairFlow,
        async_create_fix_flow,
    )

    loop = asyncio.new_event_loop()
    flow = loop.run_until_complete(
        async_create_fix_flow(
            MagicMock(), f"{ENTRY}_invalid_credentials",
            {"entry_id": ENTRY, "reason": "invalid_credentials"},
        )
    )
    assert isinstance(flow, _AuthRepairFlow)


# ── Clicking Fix opens the options flow at the right step ────────────────────

# A stand-in for a live config entry: the flow only passes it through to
# async_update_entry, so its identity is all that matters here.
_SENTINEL_ENTRY = MagicMock(name="config_entry")
_SENTINEL_ENTRY.data = {}
_SENTINEL_ENTRY.entry_id = ENTRY


def _run(coro: Any) -> Any:
    import asyncio

    return asyncio.new_event_loop().run_until_complete(coro)

# ── #1717 round two: the Fix button has to actually log in ──────────────────
#
# The first version of this feature started the options flow from the repair and
# then resolved the issue. @fschulte2812 reported the result on #1313: the
# dialog closed, the notice disappeared, no login appeared, and the channel
# stayed down. He read repairs.py and diagnosed it himself — Home Assistant
# presents CONFIG flows, so an options flow started in the backend is shown to
# nobody, while async_create_entry marked the issue fixed anyway.
#
# The tests below replace the ones that let that ship. The old pair asserted
# that options.async_init had been awaited with the right marker: both true, and
# both useless, because they checked the CALL and never that a human reaches a
# login. These check the outcome — above all that the issue cannot resolve
# unless cookies were captured.


def _repair_flow(entry: Any = _SENTINEL_ENTRY) -> tuple[Any, MagicMock]:
    """A repair flow with a stub hass. Returns (flow, hass)."""
    from custom_components.vag_connect.repairs import (
        _SupplementaryReauthRepairFlow,
    )

    flow = _SupplementaryReauthRepairFlow(ENTRY)
    hass = MagicMock()
    hass.config_entries.async_get_entry = MagicMock(return_value=entry)
    hass.config_entries.options.async_init = AsyncMock(return_value={"type": "form"})
    hass.config_entries.flow.async_init = AsyncMock(return_value={"type": "form"})
    hass.config_entries.async_update_entry = MagicMock()
    hass.async_create_task = MagicMock()
    flow.hass = hass
    return flow, hass


def test_confirming_now_asks_for_the_login_instead_of_claiming_success() -> None:
    """The regression that shipped: confirm used to resolve the issue outright."""
    flow, hass = _repair_flow()
    first = _run(flow.async_step_init())
    assert first["type"] == "form" and first["step_id"] == "confirm"

    second = _run(flow.async_step_confirm({}))
    assert second["type"] == "form", "confirm resolved the issue without a login"
    assert second["step_id"] == "credentials"
    hass.config_entries.options.async_init.assert_not_called()


def test_the_invisible_options_flow_is_never_started_again() -> None:
    """The specific mechanism of the bug, pinned so it cannot come back: an
    options flow started from here is presented to nobody."""
    flow, hass = _repair_flow()
    _run(flow.async_step_confirm({}))
    _run(flow.async_step_credentials())
    hass.config_entries.options.async_init.assert_not_called()
    hass.config_entries.flow.async_init.assert_not_called()


def test_a_rejected_password_keeps_the_issue_open() -> None:
    """A failed login re-shows the form with the error and resolves nothing."""
    flow, hass = _repair_flow()
    flow._ovw_begin_login = AsyncMock(side_effect=ValueError("invalid_credentials"))

    res = _run(flow.async_step_credentials({"username": "a@b.c", "password": "x"}))
    assert res["type"] == "form" and res["step_id"] == "credentials"
    assert res["errors"]["base"] == "invalid_credentials"
    hass.config_entries.async_update_entry.assert_not_called()


def test_a_login_needing_the_email_code_goes_to_the_code_step() -> None:
    flow, _hass = _repair_flow()
    flow._ovw_begin_login = AsyncMock(return_value=True)

    res = _run(flow.async_step_credentials({"username": "a@b.c", "password": "x"}))
    assert res["type"] == "form" and res["step_id"] == "otp"
    assert res["description_placeholders"]["username"] == "a@b.c"


def test_a_wrong_code_keeps_the_issue_open() -> None:
    flow, hass = _repair_flow()
    flow._ovw_submit_otp = AsyncMock(return_value=False)

    res = _run(flow.async_step_otp({"mfa_code": "000000"}))
    assert res["type"] == "form" and res["step_id"] == "otp"
    assert res["errors"]["base"] == "invalid_credentials"
    hass.config_entries.async_update_entry.assert_not_called()


def test_only_a_successful_login_writes_the_cookies_and_resolves() -> None:
    """The whole point. Cookies written AND the issue resolved, in that order."""
    from custom_components.vag_connect.const import (
        CONF_SUPPLEMENTARY_AUTHPROXY,
        CONF_SUPPLEMENTARY_AUTHPROXY_COOKIES,
    )

    flow, hass = _repair_flow()
    flow._ovw_begin_login = AsyncMock(return_value=False)
    flow._ovw_cookies = [{"name": "sess", "value": "v"}]

    res = _run(flow.async_step_credentials({"username": "a@b.c", "password": "x"}))
    assert res["type"] == "create_entry", "a good login did not resolve the issue"

    hass.config_entries.async_update_entry.assert_called_once()
    _args, kwargs = hass.config_entries.async_update_entry.call_args
    assert kwargs["data"][CONF_SUPPLEMENTARY_AUTHPROXY] is True
    assert kwargs["data"][CONF_SUPPLEMENTARY_AUTHPROXY_COOKIES] == [
        {"name": "sess", "value": "v"}
    ]
    # and the entry is reloaded so the coordinator arms the merged channel
    hass.async_create_task.assert_called_once()


def test_a_deleted_entry_aborts_instead_of_crashing() -> None:
    flow, hass = _repair_flow(entry=None)
    res = _run(flow.async_step_credentials())
    assert res["type"] == "abort" and res["reason"] == "entry_gone"
    hass.config_entries.async_update_entry.assert_not_called()


def test_the_login_is_shared_with_the_options_flow_not_copied() -> None:
    """One implementation. A second copy would drift from the error
    classification that several reports hardened."""
    from custom_components.vag_connect._vwde_reauth import VwDeReauthMixin
    from custom_components.vag_connect.config_flow import VagConnectOptionsFlow
    from custom_components.vag_connect.repairs import (
        _SupplementaryReauthRepairFlow,
    )

    assert issubclass(_SupplementaryReauthRepairFlow, VwDeReauthMixin)
    assert issubclass(VagConnectOptionsFlow, VwDeReauthMixin)
    # Neither may define its own copy of the mechanics.
    for cls in (_SupplementaryReauthRepairFlow, VagConnectOptionsFlow):
        for name in ("_ovw_begin_login", "_ovw_submit_otp", "_ovw_close_session"):
            assert name not in vars(cls), f"{cls.__name__} re-defines {name}"


def test_every_step_the_flow_can_show_has_strings_in_all_languages() -> None:
    """A form whose step_id has no strings renders as a raw key to the user."""
    import json
    from pathlib import Path

    root = Path("custom_components/vag_connect")
    files = [root / "strings.json"] + sorted((root / "translations").glob("*.json"))
    assert len(files) >= 13, f"only {len(files)} string files found"
    for path in files:
        fix = json.loads(path.read_text(encoding="utf-8"))["issues"][
            "supplementary_reauth"
        ]["fix_flow"]
        missing = {"confirm", "credentials", "otp"} - set(fix["step"])
        assert not missing, f"{path.name} is missing {sorted(missing)}"
        assert "invalid_credentials" in fix["error"], path.name
        assert fix["abort"].get("entry_gone"), path.name


def test_the_options_flow_jumps_straight_to_the_vwde_step() -> None:
    """Without this the user lands on the full settings form and still has to
    find the tick box — the six steps would become five, not one."""
    import asyncio

    from custom_components.vag_connect.config_flow import VagConnectOptionsFlow

    entry = MagicMock()
    entry.data = {}
    entry.options = {}
    flow = VagConnectOptionsFlow(entry)
    flow.hass = MagicMock()
    flow.init_data = {"goto": "add_vwde"}
    called: list[str] = []

    async def _fake_add_vwde(*_a: object, **_k: object) -> dict[str, Any]:
        called.append("add_vwde")
        return {"type": "form", "step_id": "add_vwde"}

    flow.async_step_add_vwde = _fake_add_vwde  # type: ignore[method-assign]
    res = asyncio.new_event_loop().run_until_complete(flow.async_step_init())
    assert called == ["add_vwde"], "did not jump to the volkswagen.de step"
    assert res["step_id"] == "add_vwde"


def test_without_the_marker_the_options_form_is_unchanged() -> None:
    """Opening options normally must still show the settings form. This is the
    regression that would annoy every user, not just the one with a dead
    session."""
    import asyncio

    from custom_components.vag_connect.config_flow import VagConnectOptionsFlow

    entry = MagicMock()
    entry.data = {}
    entry.options = {}
    flow = VagConnectOptionsFlow(entry)
    flow.hass = MagicMock()
    flow.init_data = None
    jumped: list[str] = []

    async def _fake_add_vwde(*_a: object, **_k: object) -> dict[str, Any]:
        jumped.append("add_vwde")
        return {"type": "form", "step_id": "add_vwde"}

    flow.async_step_add_vwde = _fake_add_vwde  # type: ignore[method-assign]
    try:
        asyncio.new_event_loop().run_until_complete(flow.async_step_init())
    except Exception:  # noqa: BLE001
        # The real settings form needs far more of Home Assistant than this
        # stub provides; what matters is that it did NOT take the shortcut.
        pass
    assert jumped == [], "a normal options open was hijacked to the vw.de step"


@pytest.mark.parametrize("marker", [None, {}, {"goto": "something_else"}])
def test_only_the_exact_marker_triggers_the_jump(marker: Any) -> None:
    """A stray payload must not reroute the options flow."""
    import asyncio

    from custom_components.vag_connect.config_flow import VagConnectOptionsFlow

    entry = MagicMock()
    entry.data = {}
    entry.options = {}
    flow = VagConnectOptionsFlow(entry)
    flow.hass = MagicMock()
    flow.init_data = marker
    jumped: list[str] = []

    async def _fake_add_vwde(*_a: object, **_k: object) -> dict[str, Any]:
        jumped.append("x")
        return {"type": "form"}

    flow.async_step_add_vwde = _fake_add_vwde  # type: ignore[method-assign]
    try:
        asyncio.new_event_loop().run_until_complete(flow.async_step_init())
    except Exception:  # noqa: BLE001
        pass
    assert jumped == []


# ── The text must stop telling people to navigate ───────────────────────────

def test_a_fixable_issue_carries_no_description_anywhere() -> None:
    """Home Assistant's translation schema treats ``description`` and
    ``fix_flow`` as MUTUALLY EXCLUSIVE — an issue is either fixable, and its text
    lives in the flow steps, or it is not, and its text lives in the
    description. Setting both fails hassfest with "two or more values in the
    same group of exclusion 'fixable'", which is how this was caught: in CI,
    after the local suite, ruff, mypy and the JSON validator had all passed.

    So the rule is asserted here for EVERY issue in EVERY locale file, not just
    the one this change touched.
    """
    import json
    import pathlib as _p

    files = [_p.Path("custom_components/vag_connect/strings.json")] + sorted(
        _p.Path("custom_components/vag_connect/translations").glob("*.json")
    )
    assert len(files) >= 13, "locale files missing — the check would be vacuous"
    offenders = [
        f"{f.name}:{key}"
        for f in files
        for key, val in (
            json.loads(f.read_text(encoding="utf-8")).get("issues") or {}
        ).items()
        if isinstance(val, dict) and "fix_flow" in val and "description" in val
    ]
    assert not offenders, (
        "description alongside fix_flow — hassfest rejects this: " + str(offenders)
    )


def test_the_notice_no_longer_instructs_a_navigation() -> None:
    """With a button present, "open this integration's options and re-run ..."
    is wrong advice, not just redundant."""
    import json
    import pathlib

    s = json.loads(
        pathlib.Path(
            "custom_components/vag_connect/strings.json"
        ).read_text(encoding="utf-8")
    )
    issue = s["issues"]["supplementary_reauth"]
    # The navigation advice is gone because the whole description is gone: a
    # fixable issue puts its text in the flow step instead.
    assert "description" not in issue
    assert set(issue) == {"title", "fix_flow"}
    # And the fix flow needs its own confirm strings, or the dialog renders blank.
    confirm = issue["fix_flow"]["step"]["confirm"]
    assert confirm["title"].strip()
    assert confirm["description"].strip()


def test_every_translation_carries_the_fix_flow_strings() -> None:
    """A missing fix_flow block renders an empty dialog in that language."""
    import json
    import pathlib

    missing = []
    for p in sorted(
        pathlib.Path("custom_components/vag_connect/translations").glob("*.json")
    ):
        d = json.loads(p.read_text(encoding="utf-8"))
        issue = (d.get("issues") or {}).get("supplementary_reauth")
        if not issue:
            continue
        step = (((issue.get("fix_flow") or {}).get("step") or {}).get("confirm") or {})
        if not (step.get("title") or "").strip() or not (
            step.get("description") or ""
        ).strip():
            missing.append(p.name)
    assert not missing, f"fix_flow confirm strings missing in: {missing}"
