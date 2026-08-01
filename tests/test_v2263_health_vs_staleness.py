# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Connector health and vehicle-data staleness are two different things.

The coordinator has always carried a two-stage tolerance for a car whose poll
fails: up to ``_FAILURE_TOLERANCE`` consecutive failures are ignored, and even
past that the car stays visible while the last good poll is inside
``_STALE_CACHE_WINDOW`` (old but visible, with ``last_updated_at`` telling the
truth about the age). The poll-failure path says so in as many words.

It could not actually happen. ``VagConnectEntity.available`` checked the
CONNECTOR-level ``last_update_success`` first and returned, so the per-vehicle
policy was unreachable whenever the whole poll failed. On a single-vehicle
account that is every transient 5xx or timeout; on any account it is every
backend-wide outage, which is precisely what the tolerance was written for.

The fall-through is deliberately narrow: only a VIN that has polled
successfully at least once (it has a ``vehicle_last_good_at`` stamp) AND still
passes ``is_vehicle_available`` may stay available. A car that never polled is
unavailable exactly as before.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

from custom_components.vag_connect.coordinator import (
    _FAILURE_TOLERANCE,
    _STALE_CACHE_WINDOW,
    VagConnectCoordinator,
)
from custom_components.vag_connect.entity_base import VagConnectEntity

_VIN = "VIN123"


def _entity(
    *,
    connector_ok: bool,
    failures: int,
    last_good_ago: timedelta | None,
) -> VagConnectEntity:
    coord = MagicMock(spec=VagConnectCoordinator)
    coord.last_update_success = connector_ok
    coord.data = {_VIN: {"vin": _VIN}}
    coord.vehicles = {_VIN: {"vin": _VIN}}
    coord.vehicle_failure_count = {_VIN: failures}
    coord.vehicle_last_good_at = (
        {} if last_good_ago is None
        else {_VIN: datetime.now(tz=timezone.utc) - last_good_ago}
    )
    # Use the real policy, not a mock, so the test pins actual behaviour.
    coord.is_vehicle_available = lambda vin: (
        VagConnectCoordinator.is_vehicle_available(coord, vin)
    )
    ent = VagConnectEntity(coord, _VIN, "test_key")
    return ent


class TestStaleButVisible:
    def test_connector_failure_keeps_a_recently_good_car_visible(self) -> None:
        """THE regression: the documented tolerance now actually applies."""
        ent = _entity(
            connector_ok=False,
            failures=_FAILURE_TOLERANCE + 5,  # well past the failure tolerance
            last_good_ago=timedelta(minutes=30),  # but recent good data
        )
        assert ent.available is True

    def test_connector_failure_within_failure_tolerance_stays_visible(self) -> None:
        ent = _entity(
            connector_ok=False, failures=1, last_good_ago=timedelta(minutes=5)
        )
        assert ent.available is True

    def test_a_car_that_never_polled_is_still_unavailable(self) -> None:
        """The narrow guard: no last-known-good means no free pass."""
        ent = _entity(connector_ok=False, failures=1, last_good_ago=None)
        assert ent.available is False

    def test_data_older_than_the_stale_window_goes_unavailable(self) -> None:
        """Old but visible has a limit; past the window the car is gone."""
        ent = _entity(
            connector_ok=False,
            failures=_FAILURE_TOLERANCE + 1,
            last_good_ago=_STALE_CACHE_WINDOW + timedelta(hours=1),
        )
        assert ent.available is False

    def test_healthy_connector_is_unaffected(self) -> None:
        ent = _entity(
            connector_ok=True, failures=0, last_good_ago=timedelta(minutes=1)
        )
        assert ent.available is True

    def test_healthy_connector_still_hides_a_truly_dead_car(self) -> None:
        """Per-VIN policy keeps working on the healthy-connector path."""
        ent = _entity(
            connector_ok=True,
            failures=_FAILURE_TOLERANCE + 1,
            last_good_ago=_STALE_CACHE_WINDOW + timedelta(hours=2),
        )
        assert ent.available is False
