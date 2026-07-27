# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""v2.24.2 — an explainable refusal must not look like a crash, and a bare
401 must not silence a car for half a day.

Both came out of investigating reports that VW EU users had "lost two-way
control". That premise did not survive the sweep (three users, three different
losses, two channels, and no evidence of a VW-side MBB revocation), but two
real defects turned up on the way.

1. ``VehicleCommandError`` was left behind when ``SpinError`` got its clean
   surfacing in v2.17.1. Both are ``CariadError`` and neither is an ``APIError``,
   so it fell through the dispatcher's "not APIError → re-raise raw" branch and
   Home Assistant logged "Unexpected exception" with a traceback. The usual way
   to reach it is a gateway-denied MBB operationList, where the message is
   already a full explanation. A refusal we can state in one sentence should not
   read to the user as a crash — which is very likely part of why these reports
   sounded more dramatic than the underlying situation.

2. The #909 deny-cooldown applied 12 h to ANY bare 401/403, not just to the
   explicit ``gw.error.authentication`` verdict. That verdict really is an
   enrolment decision and deserves the long cooldown. A bare 401 does not: it
   also covers an expiring session and a gateway having a bad minute, so a
   single unlucky response could keep a working car quiet for half a day.
"""
from __future__ import annotations

from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError

VIN = "WVWZZZAUZFW805377"


# ── 1. a denied command explains itself ─────────────────────────────────────


def _coord(raises: BaseException | None):
    from custom_components.vag_connect.coordinator import VagConnectCoordinator

    c = VagConnectCoordinator.__new__(VagConnectCoordinator)
    client = MagicMock()
    client.command_lock = AsyncMock(side_effect=raises)
    c._cariad_client = client
    c.async_request_refresh = AsyncMock()
    c.record_command_success = MagicMock()
    c.record_command_failure = MagicMock()
    return c


async def _dispatch(coord):
    from custom_components.vag_connect.coordinator import VagConnectCoordinator

    await VagConnectCoordinator._dispatch_cmd_locked(coord, VIN, "command_lock")


@pytest.mark.asyncio
async def test_denied_command_surfaces_as_a_clean_validation_error() -> None:
    """THE fix. Before this it was a raw traceback in the HA log."""
    from custom_components.vag_connect.cariad.exceptions import VehicleCommandError

    c = _coord(VehicleCommandError(
        "command_lock",
        "rlu_v1 not available on this vehicle (not in the operationList)",
    ))
    with pytest.raises(ServiceValidationError):
        await _dispatch(c)


@pytest.mark.asyncio
async def test_the_explanation_survives_into_the_message() -> None:
    # Trading a traceback for a shrug would be no improvement: the sentence that
    # explains WHY is the whole value of this error.
    from custom_components.vag_connect.cariad.exceptions import VehicleCommandError

    c = _coord(VehicleCommandError(
        "command_lock", "rlu_v1 not available on this vehicle"))
    with pytest.raises(ServiceValidationError) as ei:
        await _dispatch(c)
    assert "not available on this vehicle" in str(ei.value)


@pytest.mark.asyncio
async def test_a_validation_error_is_still_a_ha_error() -> None:
    # ServiceValidationError subclasses HomeAssistantError, so callers that
    # catch the broader type keep working.
    from custom_components.vag_connect.cariad.exceptions import VehicleCommandError

    c = _coord(VehicleCommandError("command_lock", "nope"))
    with pytest.raises(HomeAssistantError):
        await _dispatch(c)


@pytest.mark.asyncio
async def test_the_refusal_is_still_recorded() -> None:
    # Surfacing it nicely must not cost the capability bookkeeping.
    from custom_components.vag_connect.cariad.exceptions import VehicleCommandError

    c = _coord(VehicleCommandError("command_lock", "nope"))
    with pytest.raises(HomeAssistantError):
        await _dispatch(c)
    c.record_command_failure.assert_called_once()


@pytest.mark.asyncio
async def test_spin_error_still_behaves_as_before() -> None:
    # The v2.17.1 precedent must not regress while adding its sibling.
    from custom_components.vag_connect.cariad.exceptions import SpinError

    c = _coord(SpinError("S-PIN required for MBB command_lock"))
    with pytest.raises(ServiceValidationError):
        await _dispatch(c)


@pytest.mark.asyncio
async def test_api_error_path_is_untouched() -> None:
    from custom_components.vag_connect.cariad.exceptions import APIError

    c = _coord(APIError(403, "https://x/y", '{"errorCode":"USER_NOT_AUTHORIZED"}'))
    with pytest.raises(HomeAssistantError) as ei:
        await _dispatch(c)
    assert "USER_NOT_AUTHORIZED" in str(ei.value)


# ── 2. only an explicit gateway verdict earns the long cooldown ─────────────


class TestDenyCooldownScope:
    def test_the_two_ttls_are_distinct_and_sanely_ordered(self) -> None:
        from custom_components.vag_connect.cariad.api.vw_eu import (
            _MBB_OPLIST_DENY_TTL,
            _MBB_OPLIST_SOFT_DENY_TTL,
        )

        assert _MBB_OPLIST_DENY_TTL == timedelta(hours=12)
        assert _MBB_OPLIST_SOFT_DENY_TTL == timedelta(minutes=30)
        assert _MBB_OPLIST_SOFT_DENY_TTL < _MBB_OPLIST_DENY_TTL

    def test_a_bare_401_no_longer_gets_the_twelve_hour_verdict(self) -> None:
        """A transient-looking 401 must self-heal without the user acting."""
        import inspect

        from custom_components.vag_connect.cariad.api import vw_eu

        src = inspect.getsource(vw_eu._VwEuMbbMixin) if hasattr(
            vw_eu, "_VwEuMbbMixin") else inspect.getsource(vw_eu)
        # the explicit gateway verdict keeps the long TTL...
        assert "gw.error.authentication" in src
        # ...and the bare-status branch uses the short one
        assert "_MBB_OPLIST_SOFT_DENY_TTL" in src

    def test_an_explicit_gateway_verdict_still_gets_the_long_cooldown(self) -> None:
        """It really is an enrolment decision: only the user can change it, so
        re-asking every poll is pure noise. That part of #909 must stay."""
        import inspect

        from custom_components.vag_connect.cariad.api import vw_eu

        src = inspect.getsource(vw_eu)
        idx = src.find('"gw.error.authentication" in body')
        assert idx > 0
        window = src[idx:idx + 700]
        assert "_MBB_OPLIST_DENY_TTL" in window, (
            "the explicit gateway verdict lost its long cooldown"
        )
        assert "_MBB_OPLIST_SOFT_DENY_TTL" not in window

    def test_a_success_still_clears_the_denial(self) -> None:
        import inspect

        from custom_components.vag_connect.cariad.api import vw_eu

        assert "_mbb_oplist_denied.pop(vin, None)" in inspect.getsource(vw_eu)
