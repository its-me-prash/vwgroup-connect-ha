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

def _run_confirm() -> tuple[Any, MagicMock]:
    import asyncio

    from custom_components.vag_connect.repairs import (
        _SupplementaryReauthRepairFlow,
    )

    flow = _SupplementaryReauthRepairFlow(ENTRY)
    hass = MagicMock()
    hass.config_entries.options.async_init = AsyncMock(return_value={"type": "form"})
    flow.hass = hass
    loop = asyncio.new_event_loop()
    # First call with no input shows the confirm form ...
    form = loop.run_until_complete(flow.async_step_init())
    assert form["type"] == "form"
    # ... the second, after the user confirms, acts.
    result = loop.run_until_complete(flow.async_step_confirm({}))
    return result, hass


def test_confirming_starts_the_options_flow_for_that_entry() -> None:
    """The OPTIONS flow, not the config flow — and for the entry the notice
    belongs to, which is what removes the "which entry?" problem."""
    _, hass = _run_confirm()
    hass.config_entries.options.async_init.assert_awaited_once()
    args, kwargs = hass.config_entries.options.async_init.await_args
    assert args[0] == ENTRY
    assert kwargs["data"]["goto"] == "add_vwde"


def test_the_config_flow_is_not_touched() -> None:
    """A config flow here would land on reauth for the PRIMARY account, which is
    not what is broken — the primary channel keeps working throughout."""
    _, hass = _run_confirm()
    hass.config_entries.flow.async_init.assert_not_called()


# ── The options flow honours the marker ─────────────────────────────────────

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
