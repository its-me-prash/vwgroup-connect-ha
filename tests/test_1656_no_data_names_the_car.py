# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#1656 (@kalwados) — "Since I have two VW cars, I can't see which of these have
a problem."

The "portal returned no vehicle data" Repair is raised per config entry and its
title carried only the brand, so an account with two Volkswagens showed a warning
that could not be acted on. It really can be one car and not the other: the same
reporter's ID.4 delivers while the ID.3 does not (#923).

The title now names the cars that are actually flagged no-data, with the VIN
masked — a Repair's text is local, but people paste it into issue reports, which
is exactly how a raw VIN reached GitHub in #1626. With no per-vehicle state it
falls back to the brand name, i.e. the previous wording.
"""
from __future__ import annotations

from custom_components.vag_connect.coordinator import VagConnectCoordinator

VIN_A = "WVWZZZE1ZMP111111"
VIN_B = "WVWZZZE1ZMP222222"


def _coord(vehicles: dict | None, brand: str = "volkswagen"):
    c = VagConnectCoordinator.__new__(VagConnectCoordinator)
    c.entry = type("E", (), {"data": {"brand": brand}, "entry_id": "e1"})()
    if vehicles is not None:
        c.vehicles = vehicles
    return c


def test_names_only_the_starved_car() -> None:
    c = _coord({
        VIN_A: {"model": "ID.3 Pro", "no_data": True},
        VIN_B: {"model": "ID.4 Pro Performance", "no_data": False},
    })
    label = c._no_data_vehicle_labels()
    assert "ID.3 Pro" in label
    assert "ID.4" not in label, "a car that IS delivering must not be blamed"


def test_vin_is_masked() -> None:
    c = _coord({VIN_A: {"model": "ID.3 Pro", "no_data": True}})
    label = c._no_data_vehicle_labels()
    assert VIN_A not in label
    assert "111111" in label  # last six, the agreed masked form


def test_both_cars_listed_when_both_are_starved() -> None:
    c = _coord({
        VIN_A: {"model": "ID.3 Pro", "no_data": True},
        VIN_B: {"model": "Golf", "no_data": True},
    })
    label = c._no_data_vehicle_labels()
    assert "ID.3 Pro" in label and "Golf" in label
    assert ", " in label


def test_falls_back_to_the_brand_only_when_no_car_is_known() -> None:
    # a brand-new entry that has never had a successful read keeps the previous
    # wording rather than showing an empty bracket
    assert _coord({})._no_data_vehicle_labels() == "volkswagen"
    assert _coord(None)._no_data_vehicle_labels() == "volkswagen"


def test_names_the_known_car_even_when_nothing_is_flagged() -> None:
    """@kalwados installed the release with the first version of this and still
    saw only the brand. The Repair is raised from the PORTAL's no-data reason,
    which is independent of any per-vehicle flag — and that flag is not reliably
    set, so on the accounts this Repair fires for nothing matched. A car we know
    about is named even when it carries no flag."""
    c = _coord({VIN_A: {"model": "ID.3 Pro", "no_data": False}})
    assert c._no_data_vehicle_labels() == "ID.3 Pro (***111111)"
    # ...and with no flag key at all
    c = _coord({VIN_A: {"model": "ID.3 Pro"}})
    assert c._no_data_vehicle_labels() == "ID.3 Pro (***111111)"


def test_a_flagged_car_still_wins_over_the_unflagged_ones() -> None:
    # on a mixed account the starved car is the useful answer, so the
    # name-everything fallback must not dilute it
    c = _coord({
        VIN_A: {"model": "ID.3 Pro", "no_data": True},
        VIN_B: {"model": "ID.4", "no_data": False},
    })
    label = c._no_data_vehicle_labels()
    assert "ID.3 Pro" in label
    assert "ID.4" not in label


def test_bookkeeping_keys_are_not_mistaken_for_cars() -> None:
    c = _coord({"_meta": {"no_data": True}, VIN_A: {"no_data": True}})
    label = c._no_data_vehicle_labels()
    assert "_meta" not in label
    assert "111111" in label


def test_a_car_without_a_model_name_still_identifies_itself() -> None:
    c = _coord({VIN_A: {"no_data": True}})
    assert c._no_data_vehicle_labels() == "***111111"


def test_non_dict_vehicle_entries_are_skipped() -> None:
    c = _coord({VIN_A: "not-a-dict", VIN_B: {"model": "Golf", "no_data": True}})
    assert c._no_data_vehicle_labels() == "Golf (***222222)"
