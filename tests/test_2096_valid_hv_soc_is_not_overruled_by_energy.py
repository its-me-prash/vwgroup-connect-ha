# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#2096 — the pack-energy check must not overrule a VALID ``battery_level_HV``.

The single-value energy check (#1195) replaces a charge level that sits 15 points
or more above the pack-energy ratio on a car that is not charging. It was built
on a car whose leaf value stuck at 94 while the energy said 67.6, and whose
payload has no ``battery_level_HV`` pair.

A CUPRA Born on the EU Data Act portal showed the other side. One delivery
carried ``battery_level_HV.value = 81.0`` with state VALID, after a night's charge
to a target of 80, next to ``energy_contents`` of 391.0 / 785.0 (39.1 of 78.5 kWh,
49.8 %). The check fired and the sensor showed 50. Nothing in that flat delivery
dates the two energy values, so nothing says the energy figure is the newer one,
and the VALID pair is the reading the rest of the charge-level logic already
treats as the reliable one.

The contract pinned here:

* a charge level that is this poll's VALID pair is not replaced;
* the recorded VALID reading, shown again on a poll without the pair, is replaced
  only when the energy figures differ from the previous poll's. That is what the
  check did before on every such poll, and the one case of it that is kept;
* everything else is checked exactly as before: a car that never sent the pair,
  and a charge level that is neither of the two readings above even though the
  provenance flag is set.
"""
from __future__ import annotations

from typing import Any

from custom_components.vag_connect.cariad.auth._eu_data_act import (
    _walk_fields,
    map_dataset_to_vehicle_data,
)
from custom_components.vag_connect.cariad.models import VehicleData
from custom_components.vag_connect.cariad.vehicle_cache import reconcile, strip_runtime

# The two energy figures of the reported delivery, as the mapper yields them.
_ENERGY = {"battery_available_kwh": 39.1, "battery_cap_kwh": 78.5}  # 49.8 %
_PARKED = {"charging_state": "NOT_READY_FOR_CHARGING", "is_charging": False}
_PORTAL = {"field_sources": {"battery_soc": "eu_data_act"}}


def _poll(previous: dict[str, Any], fresh: dict[str, Any]) -> tuple[Any, list[str]]:
    merged, notes = reconcile(previous, fresh)
    return merged.get("battery_soc"), notes


def _energy_notes(notes: list[str]) -> list[str]:
    return [n for n in notes if "energy-derived" in n]


# ── this poll carries the VALID pair ──────────────────────────────────────────

def test_a_valid_hv_reading_is_not_replaced_by_the_energy_ratio() -> None:
    """The reported case: 81 from the VALID pair, energy 49.8 %, parked → 81."""
    soc, notes = _poll(
        {"battery_soc": 76, "battery_soc_from_hv": True, **_ENERGY},
        {"battery_soc": 81, "battery_soc_from_hv": True, **_ENERGY, **_PARKED, **_PORTAL},
    )
    assert soc == 81
    assert _energy_notes(notes) == []


def test_a_valid_hv_reading_stands_on_every_following_poll() -> None:
    """The sensor stayed at 50 for hours because each poll repeated the override.
    Three polls with the same delivery must read 81 three times."""
    fresh = {"battery_soc": 81, "battery_soc_from_hv": True, **_ENERGY, **_PARKED, **_PORTAL}
    previous: dict[str, Any] = {"battery_soc": 76, "battery_soc_from_hv": True}
    seen = []
    for _ in range(3):
        merged, _notes = reconcile(previous, dict(fresh))
        seen.append(merged.get("battery_soc"))
        previous = strip_runtime(merged)
    assert seen == [81, 81, 81]


def test_the_first_valid_hv_reading_of_a_car_is_not_replaced_either() -> None:
    """No recorded provenance yet (the car was read from the leaf so far): the
    poll's own VALID pair is enough to keep the check away."""
    soc, notes = _poll(
        {"battery_soc": 60, "battery_soc_from_hv": False},
        {"battery_soc": 81, "battery_soc_from_hv": True, **_ENERGY, **_PARKED, **_PORTAL},
    )
    assert soc == 81
    assert _energy_notes(notes) == []


# ── the delivery itself, through the mapper ───────────────────────────────────

def _delivery(entries: list[tuple[str, str]]) -> dict[str, Any]:
    """A flat portal delivery: name/value entries with no grouping."""
    return {
        "vin": "<REDACTED>",
        "Data": [
            {"key": f"00000000-0000-3000-8000-{i:012d}", "dataFieldName": name, "value": value}
            for i, (name, value) in enumerate(entries)
        ],
    }


# Field names, values and their order follow the reported delivery (129 entries).
# Kept are the charge level, the energy contents and what the delivery says about
# charging; the rest is left out. With entries missing, a field here does not
# inherit the capture time it inherits in the full delivery, so these tests say
# nothing about capture times.
_REPORTED_DELIVERY = _delivery([
    ("car_captured_time", "2026-11-13T06:37:09.338Z"),
    ("car_captured_utc_timestamp", "2026-11-06T18:04:39Z"),
    ("settings.target_soc", "80"),
    ("battery_state_report.remaining_charging_time_complete", "5700s"),
    ("energy_contents.maximal_energy_content.physical_value", "785.0"),
    ("car_captured_utc_timestamp", "2026-11-06T18:04:38Z"),
    ("mileage.value", "9101"),
    ("car_captured_time", "2026-11-13T06:37:22Z"),
    ("report_type", "REPORT_TYPE_CONSUMPTION_VALUES"),
    ("car_captured_utc_timestamp", "2026-11-11T06:04:30Z"),
    ("mileage.state", "VALID"),
    ("battery_level_HV.value", "81.0"),
    ("charging_state_report.charge_type", "CHARGE_TYPE_AC"),
    ("battery_state_report.charge_energy", "41.5"),
    ("battery_state_report.charge_rate", "62.0"),
    ("battery_level_HV.state", "VALID"),
    ("energy_contents.maximal_energy_content.value_type", "VALUE_TYPE_PHYSICAL"),
    ("energy_contents.current_energy_content.value_type", "VALUE_TYPE_PHYSICAL"),
    ("report_type", "REPORT_TYPE_ENERGY_CONTENTS"),
    ("energy_contents.current_energy_content.physical_value", "391.0"),
    ("car_captured_utc_timestamp", "2026-11-06T18:04:38Z"),
])


def _mapped(payload: dict[str, Any]) -> dict[str, Any]:
    fts: dict = {}
    fsyn: dict = {}
    cont: dict = {}
    fuu: dict = {}
    fields = _walk_fields(payload, fts, fsyn, cont, fuu)
    data = VehicleData(vin="TESTVIN0000000000")
    return map_dataset_to_vehicle_data(fields, data, fts, fsyn, cont, fuu).to_dict()


def test_the_reported_delivery_carries_what_the_case_rests_on() -> None:
    """Guards the fixture: if the mapper stops reading one of these, the two
    delivery tests below would pass for the wrong reason."""
    fresh = _mapped(_REPORTED_DELIVERY)
    assert fresh["battery_soc"] == 81
    assert fresh["battery_soc_from_hv"] is True
    assert fresh["battery_available_kwh"] == 39.1
    assert fresh["battery_cap_kwh"] == 78.5
    assert fresh.get("is_charging") is not True


def test_the_reported_delivery_reads_81_on_every_poll() -> None:
    """The first poll has nothing recorded and passes through untouched, before
    and after the change. The second and third are the ones the check ran on."""
    fresh = _mapped(_REPORTED_DELIVERY)
    previous: dict[str, Any] | None = None
    seen, notes_all = [], []
    for _ in range(3):
        merged, notes = reconcile(previous, dict(fresh))
        seen.append(merged.get("battery_soc"))
        notes_all += notes
        previous = strip_runtime(merged)
    assert seen == [81, 81, 81]
    assert _energy_notes(notes_all) == []


def test_an_installation_already_showing_50_recovers_with_the_next_delivery() -> None:
    """The record a 5.3.0 installation holds: 50, provenance VALID pair, the same
    energy figures. The next delivery with the VALID pair must bring 81 back."""
    fresh = _mapped(_REPORTED_DELIVERY)
    soc, notes = _poll({"battery_soc": 50, "battery_soc_from_hv": True, **_ENERGY}, fresh)
    assert soc == 81
    assert _energy_notes(notes) == []


# ── a poll without the pair: the recorded VALID reading is held ───────────────

def test_a_held_hv_reading_is_not_replaced_while_the_energy_has_not_moved() -> None:
    """A leaf-only poll holds the recorded 81 (#1195). With the energy figures
    unchanged since the previous poll there is no sign the energy is live, so the
    held reading stands; otherwise the sensor would flip between 81 and 50 with
    every delivery that happens to lack the pair."""
    soc, notes = _poll(
        {"battery_soc": 81, "battery_soc_from_hv": True, **_ENERGY},
        {"battery_soc": 79, "battery_soc_from_hv": False, **_ENERGY, **_PARKED, **_PORTAL},
    )
    assert soc == 81
    assert _energy_notes(notes) == []


def test_a_held_hv_reading_is_replaced_when_the_energy_has_moved() -> None:
    """The pair stopped arriving and the energy figures differ from the previous
    poll's: the held 81 is corrected, as it was before the change. Nothing else
    releases a held reading downwards, e.g. when the car was driven meanwhile."""
    soc, notes = _poll(
        {"battery_soc": 81, "battery_soc_from_hv": True,
         "battery_available_kwh": 43.0, "battery_cap_kwh": 78.5},
        {"battery_soc": 79, "battery_soc_from_hv": False, **_ENERGY, **_PARKED, **_PORTAL},
    )
    assert soc == 50
    assert len(_energy_notes(notes)) == 1


def test_a_held_hv_reading_stands_when_the_previous_poll_had_no_energy() -> None:
    """Nothing to compare the energy with: no evidence that it moved."""
    soc, notes = _poll(
        {"battery_soc": 81, "battery_soc_from_hv": True},
        {"battery_soc": 79, "battery_soc_from_hv": False, **_ENERGY, **_PARKED, **_PORTAL},
    )
    assert soc == 81
    assert _energy_notes(notes) == []


def test_a_carried_hv_reading_follows_the_same_rule() -> None:
    """A poll with no charge level at all carries the recorded one forward. It is
    the same recorded VALID reading, so the same rule applies both ways."""
    carried = {**_ENERGY, **_PARKED, **_PORTAL}
    still, _n1 = _poll({"battery_soc": 81, "battery_soc_from_hv": True, **_ENERGY}, dict(carried))
    moved, n2 = _poll(
        {"battery_soc": 81, "battery_soc_from_hv": True,
         "battery_available_kwh": 43.0, "battery_cap_kwh": 78.5},
        dict(carried),
    )
    assert still == 81
    assert moved == 50
    assert len(_energy_notes(n2)) == 1


def test_a_held_hv_reading_is_not_replaced_while_the_car_is_charging() -> None:
    """Changed energy figures do not lift the charging gate: during a charge the
    energy trails the charge level, and the held reading stands."""
    soc, notes = _poll(
        {"battery_soc": 81, "battery_soc_from_hv": True,
         "battery_available_kwh": 43.0, "battery_cap_kwh": 78.5},
        {"battery_soc": 79, "battery_soc_from_hv": False, **_ENERGY, **_PORTAL,
         "charging_state": "CHARGING", "is_charging": True},
    )
    assert soc == 81
    assert _energy_notes(notes) == []


def test_energy_figures_that_keep_changing_on_polls_without_the_pair() -> None:
    """Where this change stops. The recorded 81 is replaced on the first poll
    whose energy figures differ, and the derived 50 then stays while the pair is
    missing: it is held like the reading it replaced, and the check only ever
    corrects downwards. All of that is what happened before the change; the
    delivery that brings the pair back restores the reading."""
    previous: dict[str, Any] = {
        "battery_soc": 81, "battery_soc_from_hv": True,
        "battery_available_kwh": 43.0, "battery_cap_kwh": 78.5,
    }
    seen = []
    for available in (39.1, 43.0, 39.1, 43.0):
        merged, _notes = reconcile(previous, {
            "battery_soc": 79, "battery_soc_from_hv": False,
            "battery_available_kwh": available, "battery_cap_kwh": 78.5,
            **_PARKED, **_PORTAL,
        })
        seen.append(merged.get("battery_soc"))
        previous = strip_runtime(merged)
    assert seen == [50, 50, 50, 50]
    back, notes = _poll(
        previous,
        {"battery_soc": 81, "battery_soc_from_hv": True, **_ENERGY, **_PARKED, **_PORTAL},
    )
    assert back == 81
    assert _energy_notes(notes) == []


# ── the flag is set, but the charge level is neither of the two readings ──────

def test_a_level_of_unknown_provenance_next_to_a_valid_record_is_still_checked() -> None:
    """The mapper sets no provenance flag for a charge level it reads from the
    export spelling. Such a level is not held and is not the recorded reading,
    so a VALID record from earlier must not shield it from the check."""
    soc, notes = _poll(
        {"battery_soc": 60, "battery_soc_from_hv": True, **_ENERGY},
        {"battery_soc": 81, **_ENERGY, **_PARKED, **_PORTAL},
    )
    assert soc == 50
    assert len(_energy_notes(notes)) == 1


def test_a_leaf_level_is_still_checked_when_the_record_has_the_flag_but_no_level() -> None:
    """Nothing recorded to hold: the leaf value is shown, and it is a leaf value."""
    soc, notes = _poll(
        {"battery_soc_from_hv": True, **_ENERGY},
        {"battery_soc": 79, "battery_soc_from_hv": False, **_ENERGY, **_PARKED, **_PORTAL},
    )
    assert soc == 50
    assert len(_energy_notes(notes)) == 1


def test_a_carried_level_is_not_this_polls_pair_even_when_the_poll_has_the_flag() -> None:
    """A dongle value yields to the recorded one and leaves the poll without a
    charge level. The recorded leaf value is carried, and the flag the poll
    still carries says nothing about it."""
    merged, notes = reconcile(
        {"battery_soc": 94, "battery_soc_from_hv": False, "has_battery": True},
        {
            "battery_soc": 88, "battery_soc_from_hv": True, "has_battery": True,
            "battery_available_kwh": 49.6, "battery_cap_kwh": 73.4, **_PARKED,
            "field_sources": {"battery_soc": "drivepulse"},
            "field_captured_ts": {"battery_soc": "2026-11-13T06:37:22+00:00"},
        },
    )
    assert merged["battery_soc"] == 68
    assert len(_energy_notes(notes)) == 1


def test_a_dongle_held_reading_next_to_this_polls_pair_keeps_its_own_handling() -> None:
    """The dongle exclusion covers both readings: a held value that stays in the
    poll is taken out when the energy contradicts it, flag or no flag."""
    energy = {"battery_available_kwh": 20.0, "battery_cap_kwh": 58.0}  # 34.5 %
    merged, notes = reconcile(
        {"has_battery": True, "battery_soc_from_hv": True, **energy, "field_sources": {}},
        {
            "battery_soc": 88, "battery_soc_from_hv": True, "has_battery": True, **energy,
            "field_sources": {"battery_soc": "drivepulse"},
            "field_captured_ts": {"battery_soc": "2026-11-13T06:37:22+00:00"},
        },
    )
    assert merged["battery_soc"] is None
    assert any("not shown" in n for n in notes)


def test_a_dongle_held_reading_keeps_its_own_handling_on_a_car_with_the_pair() -> None:
    """A value held from a linked dongle is taken out, not kept, when the pack
    energy contradicts it. That handling must not depend on whether the car has
    ever sent the VALID pair."""
    energy = {"battery_available_kwh": 20.0, "battery_cap_kwh": 58.0}  # 34.5 %
    merged, notes = reconcile(
        {"has_battery": True, "battery_soc_from_hv": True, **energy, "field_sources": {}},
        {
            "battery_soc": 88, "has_battery": True, **energy,
            "field_sources": {
                "battery_soc": "drivepulse",
                "battery_available_kwh": "eu_data_act",
                "battery_cap_kwh": "eu_data_act",
            },
            "field_captured_ts": {"battery_soc": "2026-11-13T06:37:22+00:00"},
        },
    )
    assert merged["battery_soc"] is None
    assert any("not shown" in n for n in notes)


# ── cars that never sent the pair: the check is what it was ───────────────────

def test_a_car_without_the_pair_is_still_corrected() -> None:
    """The case the check was built for: a leaf stuck at 94, energy 67.6 %."""
    soc, notes = _poll(
        {"battery_soc": 94, "battery_soc_from_hv": False},
        {"battery_soc": 94, "battery_soc_from_hv": False,
         "battery_available_kwh": 49.6, "battery_cap_kwh": 73.4, **_PARKED, **_PORTAL},
    )
    assert soc == 68
    assert len(_energy_notes(notes)) == 1


def test_a_car_without_the_pair_is_corrected_even_with_unchanged_energy() -> None:
    """The moved-energy condition belongs to a held VALID reading only. A leaf car
    with the same energy figures on two polls is corrected on both."""
    energy = {"battery_available_kwh": 49.6, "battery_cap_kwh": 73.4}
    soc, notes = _poll(
        {"battery_soc": 94, "battery_soc_from_hv": False, **energy},
        {"battery_soc": 94, "battery_soc_from_hv": False, **energy, **_PARKED, **_PORTAL},
    )
    assert soc == 68
    assert len(_energy_notes(notes)) == 1


def test_a_car_with_no_recorded_provenance_is_still_corrected() -> None:
    """Records written before the provenance flag existed carry no flag at all."""
    soc, _notes = _poll(
        {"battery_soc": 94},
        {"battery_soc": 94, "battery_available_kwh": 49.6, "battery_cap_kwh": 73.4, **_PARKED},
    )
    assert soc == 68
