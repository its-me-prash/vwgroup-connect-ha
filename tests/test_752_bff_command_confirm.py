# Copyright 2026 Prash Balan (@its-me-prash) - Apache License 2.0
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#752 audit — CARIAD BFF command completion poll.

The BFF 202-accepts a command, then runs it asynchronously. Previously we
reported success on accept, so a command the vehicle later REJECTED still showed
as success (the #666 optimistic snap-back). _post_command now polls
.../pendingrequests to a terminal status and raises on an explicit failure —
best-effort: it never raises on a missing id, a poll error, or a timeout.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest

from custom_components.vag_connect.cariad.api import vw_eu
from custom_components.vag_connect.cariad.api.vw_eu import (
    VWEUClient,
    _bff_request_id,
    _bff_status_for,
)
from custom_components.vag_connect.cariad.exceptions import VehicleCommandError


# ── pure helpers ─────────────────────────────────────────────────────────────

def test_request_id_extraction() -> None:
    assert _bff_request_id({"data": {"requestID": "R1"}}) == "R1"
    assert _bff_request_id({"data": {"requestId": "R2"}}) == "R2"
    assert _bff_request_id({"data": {"id": "R4"}}) == "R4"
    assert _bff_request_id({"requestID": "R3"}) == "R3"
    assert _bff_request_id(None) is None
    assert _bff_request_id({}) is None
    assert _bff_request_id({"data": {}}) is None


def test_status_lookup() -> None:
    pend = {"data": [
        {"id": "R1", "status": "successful"},
        {"id": "R2", "status": "failed"},
    ]}
    assert _bff_status_for(pend, "R1") == "successful"
    assert _bff_status_for(pend, "R2") == "failed"
    assert _bff_status_for(pend, "R9") is None
    assert _bff_status_for([{"requestID": "R1", "state": "inProgress"}], "R1") == "inProgress"
    assert _bff_status_for({}, "R1") is None


# ── the poll wired into _post_command ────────────────────────────────────────

@pytest.fixture(autouse=True)
def _fast(monkeypatch) -> None:
    monkeypatch.setattr(vw_eu, "_BFF_CONFIRM_SLEEP_S", 0.0)
    monkeypatch.setattr(vw_eu, "_BFF_CONFIRM_ATTEMPTS", 3)


def _client(post_resp, *, get_resp=None, get_exc=None) -> VWEUClient:
    c = VWEUClient.__new__(VWEUClient)
    c._tokens = None
    c._v2_command_paths = {}
    c._post = AsyncMock(return_value=post_resp)
    if get_exc is not None:
        c._get = AsyncMock(side_effect=get_exc)
    else:
        c._get = AsyncMock(return_value=get_resp)
    return c


def test_success_status_polls_and_returns() -> None:
    c = _client({"data": {"requestID": "R1"}},
                get_resp={"data": [{"id": "R1", "status": "successful"}]})
    asyncio.run(c._post_command("VINX", "climatisation/start-stop", json={"action": "start"}))
    c._get.assert_awaited()  # the completion poll ran


def test_failed_status_raises() -> None:
    c = _client({"data": {"requestID": "R1"}},
                get_resp={"data": [{"id": "R1", "status": "failed"}]})
    with pytest.raises(VehicleCommandError):
        asyncio.run(c._post_command("VINX", "climatisation/start-stop", json={"action": "start"}))


def test_no_request_id_skips_poll() -> None:
    c = _client(None)  # 204/None response — nothing to confirm
    asyncio.run(c._post_command("VINX", "access/lock", json={}))
    c._get.assert_not_awaited()


def test_poll_error_is_best_effort() -> None:
    c = _client({"data": {"requestID": "R1"}}, get_exc=RuntimeError("boom"))
    asyncio.run(c._post_command("VINX", "access/lock", json={}))  # must NOT raise


def test_in_progress_through_whole_window_raises_unconfirmed() -> None:
    """#912/#940 — a request the car accepts but never terminalises (perpetual
    in_progress, the PPE e:CV.PA.29 "vehicle does not answer" signature) is now
    reported as UNCONFIRMED so the optimistic UI reverts, instead of leaving a
    false "OK". Distinct from the never-listed fast-clear case below."""
    c = _client({"data": {"requestID": "R1"}},
                get_resp={"data": [{"id": "R1", "status": "inProgress"}]})
    with pytest.raises(VehicleCommandError):
        asyncio.run(c._post_command("VINX", "access/lock", json={}))


def test_never_listed_request_times_out_without_raising() -> None:
    """A fast command that cleared before we polled (its id never appears in
    pendingrequests) still returns optimistically — unchanged, so a normal quick
    command is never turned into a false failure."""
    c = _client({"data": {"requestID": "R1"}},
                get_resp={"data": []})  # request id never listed → status None
    asyncio.run(c._post_command("VINX", "access/lock", json={}))  # must NOT raise
