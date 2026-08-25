# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#1234 (@eddieari) — a non-credential portal interaction on the shared account
session must NOT tear the whole config entry into reauth and take every working
vehicle offline. Only genuine stale credentials trigger reauth.

The failure is injected at an ACCOUNT-level poll step (not a per-VIN get_status,
which is already isolated) so it reaches the outer poll-loop handler where the
reauth decision lives.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.vag_connect.cariad.exceptions import (
    AuthenticationError,
    PortalInteractionRequiredError,
)
from custom_components.vag_connect.cariad.models import VehicleData
from tests.test_v2159_transient_and_interaction_deescalation import (
    _build_coordinator,
    _run_one_poll,
)


def _account_step_raises(exc):
    # per-VIN read would succeed (VehicleData); the failure comes from a shared
    # account-level step, so it reaches the outer handler, not the per-VIN gate.
    coord, vin = _build_coordinator(VehicleData(vin="WVWZZZ1KZAW000596"))
    coord.hass = MagicMock()
    coord._refresh_mbb_command_capabilities = AsyncMock(side_effect=exc)
    coord.entry.async_start_reauth = MagicMock()
    return coord, vin


@pytest.mark.asyncio
async def test_portal_interaction_does_not_clobber_into_reauth():
    coord, vin = _account_step_raises(
        PortalInteractionRequiredError("browserFeaturesMissingError")
    )
    await _run_one_poll(coord)
    # the whole entry is NOT dragged into reauth (working vehicles stay up)
    coord.entry.async_start_reauth.assert_not_called()
    # the poll is still counted as failed → failure-tolerance keeps the car
    # available for a few cycles and the next poll retries
    assert coord.vehicle_success[vin] is False
    assert coord.vehicle_failure_count[vin] == 1
    # a transient block is not our bug → not error-reported
    assert len(coord.error_buffer) == 0


@pytest.mark.asyncio
async def test_genuine_stale_credentials_still_reauth():
    coord, _ = _account_step_raises(AuthenticationError("invalid_credentials"))
    await _run_one_poll(coord)
    coord.entry.async_start_reauth.assert_called_once()
