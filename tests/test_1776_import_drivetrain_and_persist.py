# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#1776 — two defects that together made ``import_historical_export`` report
success while producing nothing a user could see.

Found grounding @placidcasual98's report on #1403: he imported an export that
demonstrably contained a state of charge, got a green tick, turned OFF "hide
entities without data", waited more than one poll, and still had no battery
entity at all — not even an unknown one.

1. **The flag the entities are gated on could never be set.** ``has_battery`` is
   a bool defaulting to ``False``, never ``None``, and the merge writes a field
   only where the current value ``is None``. So the export offered the SoC and
   the flag in the same object, the value landed and the flag was refused. The
   gate is evaluated before the hide-empty gate, which is why he saw no entity
   rather than an empty one.

2. **Nothing was persisted.** The snapshot is written in one place, inside the
   poll loop, so the reload we told people to do discarded the merge.

The fix re-derives the flags through the channel merge's own rule rather than a
second copy of it. The test that matters most here is
``test_a_phev_is_not_flattened_into_an_ev``: the gap-fill's refusal to write was
protecting against exactly that, so the replacement has to carry the protection
rather than drop it.
"""
from __future__ import annotations

from custom_components.vag_connect.cariad._channel_merge import (
    drivetrain_from_evidence,
)


def _flags(snapshot: dict, **asserted: bool) -> dict:
    return drivetrain_from_evidence(snapshot.get, **asserted)


def test_a_state_of_charge_alone_makes_the_car_electric() -> None:
    """@placidcasual98's case: the export carries a SoC, nothing else."""
    out = _flags({"battery_soc": 31})
    assert out["has_battery"] is True
    assert out["has_combustion"] is False
    assert out["is_electric"] is True
    assert out["is_hybrid"] is False


def test_an_asserted_flag_survives_without_its_value() -> None:
    """The promotion path. A channel can set the flag without the reading — the
    export parser does exactly that — and the recompute must believe it."""
    out = _flags({}, asserted_battery=True)
    assert out["has_battery"] is True
    assert out["is_electric"] is True


def test_a_phev_is_not_flattened_into_an_ev() -> None:
    """The hazard the old refusal-to-write was guarding.

    The legacy export dialect carries NO combustion evidence. A car already
    known to burn fuel must stay a hybrid when such an export is merged, even
    though nothing in the export mentions fuel.
    """
    out = _flags(
        {"battery_soc": 44},                 # export's evidence
        asserted_battery=True,
        asserted_combustion=True,            # what we already knew about the car
    )
    assert out["has_battery"] is True
    assert out["has_combustion"] is True
    assert out["is_hybrid"] is True
    assert out["is_electric"] is False


def test_fuel_evidence_alone_is_a_combustion_car() -> None:
    out = _flags({"fuel_level": 60})
    assert out["has_combustion"] is True
    assert out["has_battery"] is False
    assert out["is_electric"] is False
    assert out["is_hybrid"] is False


def test_a_car_we_know_nothing_about_stays_unclassified() -> None:
    """No evidence must not become a claim. @placidcasual98's four-field
    maintenance feed is this case, and calling such a car an EV would be a
    confident wrong answer."""
    out = _flags({"oil_warning": True})
    assert out["has_battery"] is False
    assert out["has_combustion"] is False
    assert "is_electric" not in out
    assert "is_hybrid" not in out


def test_every_documented_battery_signal_counts_on_its_own() -> None:
    for key, value in (
        ("battery_soc", 0),                  # 0 % is a reading, not an absence
        ("electric_range_km", 0),
        ("charging_state", "notReadyForCharging"),
    ):
        out = _flags({key: value})
        assert out["has_battery"] is True, key


def test_the_rule_cannot_demote_a_flag() -> None:
    """Additive in both directions: passing the current flags in as asserted is
    what makes a recompute unable to take something away."""
    out = _flags(
        {},                                   # no evidence left in the snapshot
        asserted_battery=True, asserted_combustion=True,
    )
    assert out["has_battery"] is True
    assert out["has_combustion"] is True


def test_the_channel_merge_still_uses_this_rule() -> None:
    """Control. The point of extracting it was that there is ONE rule; if the
    merge grew its own copy again, this file would stop proving anything about
    the import path.
    """
    import inspect

    from custom_components.vag_connect.cariad import _channel_merge

    src = inspect.getsource(_channel_merge._merge_drivetrain)
    assert "drivetrain_from_evidence" in src
    # and the old inline duplication is gone
    assert "merged.has_battery = has_battery" not in src


# ── the wiring in the import path, not just the rule ───────────────────────
import threading  # noqa: E402
from typing import Any  # noqa: E402
from unittest.mock import MagicMock  # noqa: E402

import pytest  # noqa: E402

from custom_components.vag_connect.cariad.models import VehicleData  # noqa: E402
from custom_components.vag_connect.coordinator import (  # noqa: E402
    VagConnectCoordinator,
)


class _Portal:
    def __init__(self, historical: VehicleData) -> None:
        self._historical = historical

    async def get_vehicle_data(
        self, vin: str, request_type: str = "partial"
    ) -> VehicleData:
        return self._historical


def _coord(historical: VehicleData, current: Any) -> VagConnectCoordinator:
    c = VagConnectCoordinator.__new__(VagConnectCoordinator)
    c._cariad_client = MagicMock()
    c._cariad_client._eu_portal = _Portal(historical)
    c.vehicles = {"V": current} if current is not None else {}
    c._vehicles_lock = threading.Lock()
    c.pushed: list[dict] = []
    c.saves: list[int] = []
    c.async_set_updated_data = lambda data: c.pushed.append(data)  # type: ignore[assignment]
    c._save_vehicle_cache = lambda: c.saves.append(1)  # type: ignore[assignment]
    return c


@pytest.mark.asyncio
async def test_the_import_promotes_the_flag_and_persists() -> None:
    """@placidcasual98's sequence end to end: an export with a SoC, a car not
    yet known to be electric. Before this fix the value landed, the flag did
    not, no entity was created, and a reload threw the merge away."""
    hist = VehicleData(vin="V")
    hist.no_data = False
    hist.battery_soc = 31
    hist.has_battery = True
    c = _coord(hist, {"oil_warning": False})   # four-field maintenance feed
    assert await c.async_import_historical_export("V") is True
    snap = c.vehicles["V"]
    assert snap["battery_soc"] == 31
    assert snap["has_battery"] is True, "the flag the entities are gated on"
    assert snap["is_electric"] is True
    assert c.saves, "the merge must be persisted or a reload discards it"
    assert c.pushed, "and pushed to the coordinator listeners"


@pytest.mark.asyncio
async def test_the_import_does_not_demote_a_hybrid() -> None:
    hist = VehicleData(vin="V")
    hist.no_data = False
    hist.battery_soc = 44
    hist.has_battery = True
    hist.is_electric = True            # the legacy dialect's wrong claim
    c = _coord(hist, {"is_hybrid": True, "is_electric": False,
                      "has_combustion": True, "fuel_level": 60})
    assert await c.async_import_historical_export("V") is True
    snap = c.vehicles["V"]
    assert snap["has_battery"] is True          # promoted
    assert snap["has_combustion"] is True       # kept
    assert snap["is_hybrid"] is True
    assert snap["is_electric"] is False, "a PHEV must not become an EV"


@pytest.mark.asyncio
async def test_writing_only_false_flags_is_not_reported_as_an_import() -> None:
    """A False flag alone must not make the service claim an import.

    The snapshot here already holds everything the export offers, so the
    gap-fill has nothing to write and the drivetrain recompute is the only thing
    left — and with no battery and no fuel evidence it can only write False.
    Counting that as a merge would report a successful import and mark the
    one-time export *done* on a car that gained nothing.

    (The snapshot is the export's own dict rather than a hand-written minimal
    one. A bare VehicleData still carries a VIN and several empty containers,
    none of which are None, and the drivetrain flags are False rather than
    absent — so a hand-written snapshot makes the GAP-FILL write them and count
    it, which is a different, pre-existing behaviour that production never hits
    because the parser always sets the flags.)
    """
    hist = VehicleData(vin="V")
    hist.no_data = False
    current = dict(hist.to_dict())   # flags present and already False
    c = _coord(hist, current)
    assert await c.async_import_historical_export("V") is False
    assert not c.saves, "nothing was gained, so nothing should be persisted"
    assert c.vehicles["V"]["has_battery"] is False
    assert c.vehicles["V"]["has_combustion"] is False
