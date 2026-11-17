# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Škoda commands survive mysmob refusing them — six of them, and only safely.

Every Škoda command goes through mysmob today, and mysmob is expected to be
retired. The official public API implements six of the same commands, and
nothing in the integration has ever called them. This is the bridge, shaped like
the Audi BFF → MBB precedent next to it.

The tests that matter here are the ones about NOT firing. A command fallback is
a machine for sending a physical instruction to a car twice, and this repository
has already fixed that bug once (the b7 note in ``_cariad_cmd``: a timeout
re-dispatched a non-idempotent charge/unlock/aux-heat). So the gate is pinned
from both sides: the three refusals that prove nothing was actuated fire it, and
everything else — above all 5xx and the transient ``APIError(0)``, which
``base._request`` has already retried up to three times — must not.
"""
from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.exceptions import HomeAssistantError

VIN = "TMBJJ7NE0J0123456"
OTHER_VIN = "TMBJJ7NE0J0999999"


# ── fixtures ────────────────────────────────────────────────────────────────


class _Official:
    """Stand-in for the official client, with the attributes the gate reads."""

    def __init__(self, *, raises: BaseException | None = None) -> None:
        self.calls: list[tuple[str, str]] = []
        self._raises = raises

    async def _run(self, name: str, vin: str) -> bool:
        self.calls.append((name, vin))
        if self._raises is not None:
            raise self._raises
        return True

    def __getattr__(self, name: str) -> Any:
        if name.startswith("command_"):
            async def _cmd(vin: str) -> bool:
                return await self._run(name, vin)
            return _cmd
        raise AttributeError(name)


def _coord(
    *,
    mysmob_raises: BaseException | None,
    official: _Official | None,
    brand: str = "skoda",
    mode: str = "auto",
    method: str = "command_start_charging",
):
    from custom_components.vag_connect.coordinator import VagConnectCoordinator

    c = VagConnectCoordinator.__new__(VagConnectCoordinator)
    client = MagicMock()
    setattr(client, method, AsyncMock(side_effect=mysmob_raises))
    client.official_command_connector = MagicMock(return_value=official)
    c._cariad_client = client
    c.entry = MagicMock()
    c.entry.data = {"brand": brand}
    c._skoda_official_mode = MagicMock(return_value=mode)
    c.async_request_refresh = AsyncMock()
    c.record_command_success = MagicMock()
    c.record_command_failure = MagicMock()
    return c


async def _dispatch(coord, method: str = "command_start_charging", **kwargs: Any):
    from custom_components.vag_connect.coordinator import VagConnectCoordinator

    await VagConnectCoordinator._dispatch_cmd_locked(coord, VIN, method, **kwargs)


def _api_error(status: int):
    from custom_components.vag_connect.cariad.exceptions import APIError

    return APIError(status, "https://mysmob.invalid/x", "body")


# ── the double-send rule ────────────────────────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [401, 403, 404])
async def test_a_refusal_that_proves_nothing_happened_is_retried(status: int) -> None:
    official = _Official()
    coord = _coord(mysmob_raises=_api_error(status), official=official)

    await _dispatch(coord)

    assert official.calls == [("command_start_charging", VIN)]
    coord.record_command_success.assert_called_once_with(VIN, "command_start_charging")


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [500, 502, 503, 504, 429, 430, 0])
async def test_a_failure_that_might_have_executed_is_never_retried(status: int) -> None:
    """base._request already retried 5xx and transients up to three times, so the
    car may well have received the command — a fallback here would be the fifth
    send of a non-idempotent instruction."""
    official = _Official()
    coord = _coord(mysmob_raises=_api_error(status), official=official)

    with pytest.raises(Exception):
        await _dispatch(coord)

    assert official.calls == []


@pytest.mark.asyncio
async def test_the_official_channel_is_tried_exactly_once() -> None:
    official = _Official(raises=RuntimeError("official is down too"))
    coord = _coord(mysmob_raises=_api_error(404), official=official)

    with pytest.raises(Exception):
        await _dispatch(coord)

    assert len(official.calls) == 1


@pytest.mark.asyncio
async def test_the_original_error_surfaces_when_both_channels_fail() -> None:
    """Never the fallback's error: the user's problem is the primary channel."""
    from custom_components.vag_connect.cariad.exceptions import AuthenticationError

    official = _Official(raises=AuthenticationError("Škoda official API: no API key"))
    coord = _coord(mysmob_raises=_api_error(403), official=official)

    with pytest.raises(HomeAssistantError) as caught:
        await _dispatch(coord)

    # the official client's AuthenticationError is a CariadError, not an
    # APIError — escaping would show a traceback for a button press
    assert not isinstance(caught.value, AuthenticationError)


# ── what is covered, and what must not be ───────────────────────────────────


def test_the_covered_set_is_exactly_the_six_matching_commands() -> None:
    from custom_components.vag_connect.coordinator import VagConnectCoordinator

    assert VagConnectCoordinator._SKODA_OFFICIAL_COMMANDS == frozenset({
        "command_start_charging",
        "command_stop_charging",
        "command_start_climate",
        "command_stop_climate",
        "command_start_active_ventilation",
        "command_stop_active_ventilation",
    })
    # lock/unlock have no official route at all; aux heating has one but a
    # different signature and an entry-wide S-PIN
    for absent in (
        "command_lock", "command_unlock", "command_start_aux_heating",
        "command_set_climate_temperature",
    ):
        assert absent not in VagConnectCoordinator._SKODA_OFFICIAL_COMMANDS


@pytest.mark.asyncio
async def test_an_uncovered_command_is_not_retried() -> None:
    official = _Official()
    coord = _coord(mysmob_raises=_api_error(404), official=official,
                   method="command_lock")

    with pytest.raises(Exception):
        await _dispatch(coord, "command_lock")

    assert official.calls == []


@pytest.mark.asyncio
async def test_any_kwarg_blocks_the_fallback() -> None:
    """The official signatures take vin only. A blind splat would raise
    TypeError, which leaves the dispatcher as a raw traceback."""
    official = _Official()
    coord = _coord(mysmob_raises=_api_error(404), official=official,
                   method="command_start_climate")

    with pytest.raises(Exception) as caught:
        await _dispatch(coord, "command_start_climate", target_c=21.0)

    assert official.calls == []
    assert not isinstance(caught.value, TypeError)


def test_every_covered_official_method_takes_vin_only() -> None:
    """Contract test: a signature drift on the official client fails here rather
    than as a TypeError in front of a user."""
    import inspect

    from custom_components.vag_connect.cariad.api.skoda_official import (
        SkodaOfficialClient,
    )
    from custom_components.vag_connect.coordinator import VagConnectCoordinator

    for name in VagConnectCoordinator._SKODA_OFFICIAL_COMMANDS:
        fn = getattr(SkodaOfficialClient, name, None)
        assert fn is not None, f"{name} is gone from the official client"
        params = list(inspect.signature(fn).parameters.values())
        required = [
            p for p in params[2:]  # skip self, vin
            if p.default is inspect.Parameter.empty
            and p.kind not in (p.VAR_POSITIONAL, p.VAR_KEYWORD)
        ]
        assert not required, f"{name} now needs {[p.name for p in required]}"


# ── the gates that are easy to get wrong ────────────────────────────────────


@pytest.mark.asyncio
async def test_a_mock_client_does_not_vivify_the_gate_open() -> None:
    """The gate reads the entry first. Reading the client first would pass on a
    MagicMock, and most of this suite's coordinators are MagicMocks."""
    from custom_components.vag_connect.coordinator import VagConnectCoordinator

    c = VagConnectCoordinator.__new__(VagConnectCoordinator)
    c._cariad_client = MagicMock()  # auto-vivifies every attribute
    c._cariad_client.command_start_charging = AsyncMock(side_effect=_api_error(404))
    c.entry = MagicMock()
    c.entry.data = {}  # no brand
    c.async_request_refresh = AsyncMock()
    c.record_command_success = MagicMock()
    c.record_command_failure = MagicMock()

    assert c._skoda_official_command_fallback(VIN, "command_start_charging",
                                              _api_error(404), {}) is None


@pytest.mark.asyncio
async def test_another_brand_never_reaches_the_skoda_bridge() -> None:
    official = _Official()
    coord = _coord(mysmob_raises=_api_error(403), official=official, brand="audi")

    with pytest.raises(Exception):
        await _dispatch(coord)

    assert official.calls == []


@pytest.mark.asyncio
async def test_mysmob_only_mode_means_mysmob_only() -> None:
    official = _Official()
    coord = _coord(mysmob_raises=_api_error(404), official=official,
                   mode="mysmob_only")

    with pytest.raises(Exception):
        await _dispatch(coord)

    assert official.calls == []


@pytest.mark.asyncio
async def test_no_armed_official_channel_changes_nothing() -> None:
    coord = _coord(mysmob_raises=_api_error(404), official=None)

    with pytest.raises(Exception):
        await _dispatch(coord)


# ── the shared quota ────────────────────────────────────────────────────────


def _skoda_client(**official_attrs: Any):
    from custom_components.vag_connect.cariad.api.skoda import SkodaClient

    c = SkodaClient.__new__(SkodaClient)
    off = MagicMock()
    # #2165 — the command path asks the budget of this VIN's key.
    off.over_rate_limit_for = MagicMock(
        return_value=official_attrs.get("over_rate_limit", False))
    off.rate_limit_remaining_for = MagicMock(
        return_value=official_attrs.get("rate_limit_remaining", None))
    off.has_key_for = MagicMock(
        return_value=official_attrs.get("has_key", True))
    c._supplementary_official = off
    return c, off


def test_an_exhausted_quota_refuses_the_command_channel() -> None:
    """The reads skip at the same guard; a command must not breach it either."""
    c, _ = _skoda_client(over_rate_limit=True)
    assert c.official_command_connector(VIN) is None


@pytest.mark.parametrize("remaining,expected", [(3, False), (4, True), (None, True)])
def test_headroom_is_reserved_for_the_reads(remaining, expected: bool) -> None:
    c, off = _skoda_client(rate_limit_remaining=remaining)
    assert (c.official_command_connector(VIN) is off) is expected


def test_a_vin_without_a_key_is_refused_before_any_request() -> None:
    """``_headers`` would raise anyway; refusing here keeps a mysmob failure from
    turning into a confusing authentication error."""
    c, _ = _skoda_client(has_key=False)
    assert c.official_command_connector(VIN) is None


def test_no_official_channel_armed_yields_nothing() -> None:
    from custom_components.vag_connect.cariad.api.skoda import SkodaClient

    c = SkodaClient.__new__(SkodaClient)
    c._supplementary_official = None
    assert c.official_command_connector(VIN) is None


# ── the companion fix, without which the fallback blinds the reads ──────────


def test_a_stale_retry_after_no_longer_blocks_the_read_channel() -> None:
    """``retry_after_s`` is set on a 429 and never cleared. Deciding the
    self-block from the attribute meant a later routine 403 — which a command
    fallback produces more of — re-armed the old 429's window and parked the
    READ channel with it."""
    from custom_components.vag_connect.cariad.api.skoda_official import (
        SkodaOfficialClient,
    )

    c = SkodaOfficialClient(MagicMock(), VIN, "key")

    throttled = MagicMock()
    throttled.status = 429
    throttled.headers = {"Retry-After": "600"}
    c._note_rate_limit(throttled, "key")
    assert c.over_rate_limit is True, "a real 429 must still block"
    assert c.over_rate_limit_for(VIN) is True

    # The 429's window has run out (simulated), then a routine 403 arrives.
    c._blocked_until = 0.0
    c._blocked_until_by_key.clear()
    refusal = MagicMock()
    refusal.status = 403
    refusal.headers = {}  # no Retry-After of its own
    c._note_rate_limit(refusal, "key")

    assert c.over_rate_limit is False
    assert c.over_rate_limit_for(VIN) is False
    assert c.retry_after_s == 600, "the last-seen value stays for diagnostics"
