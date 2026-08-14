# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#912 — opt-in capture of a command's BFF pendingrequests body.

To eventually map the Audi PPE rejection (E:CV.PA.31) into the confirmation logic
we need a real ``pendingrequests`` body. When a test-cohort user runs a command,
``_await_bff_command`` now keeps that body in ``command_captures`` (its own dict,
so the per-poll wipe of ``last_raw_responses`` can't clobber it) for the redacted
diagnostics. Off for everyone not in the cohort; no extra request, no command
regression.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import custom_components.vag_connect.cariad.api.vw_eu as vw_eu_mod
from custom_components.vag_connect.cariad.api.vw_eu import VWEUClient, _BFF_OK_STATES

_PEND = {"requests": [{"id": "req1", "status": "successful"}]}


def _client(cohort: bool) -> VWEUClient:
    c = VWEUClient.__new__(VWEUClient)
    c.command_captures = {}
    c._test_cohort = cohort
    c._get = AsyncMock(return_value=_PEND)  # type: ignore[assignment]
    return c


def _patch_flow(monkeypatch) -> None:
    ok = next(iter(_BFF_OK_STATES))
    monkeypatch.setattr(vw_eu_mod, "_bff_request_id", lambda resp: "req1")
    monkeypatch.setattr(vw_eu_mod, "_bff_status_for", lambda pend, rid: ok)
    monkeypatch.setattr(vw_eu_mod.asyncio, "sleep", AsyncMock())


def test_cohort_user_captures_the_pendingrequests_body(monkeypatch) -> None:
    _patch_flow(monkeypatch)
    c = _client(cohort=True)
    asyncio.run(c._await_bff_command("WVWZZZAUZ1234567", "https://bff", {"r": 1}))
    assert c.command_captures.get("bff_pendingrequests") == _PEND


def test_non_cohort_user_captures_nothing(monkeypatch) -> None:
    _patch_flow(monkeypatch)
    c = _client(cohort=False)
    asyncio.run(c._await_bff_command("WVWZZZAUZ1234567", "https://bff", {"r": 1}))
    assert c.command_captures == {}


def test_missing_flag_defaults_to_no_capture(monkeypatch) -> None:
    """A client without the attribute (belt-and-braces) must not capture."""
    _patch_flow(monkeypatch)
    c = _client(cohort=False)
    del c._test_cohort  # simulate an older/other client
    asyncio.run(c._await_bff_command("WVWZZZAUZ1234567", "https://bff", {"r": 1}))
    assert c.command_captures == {}
