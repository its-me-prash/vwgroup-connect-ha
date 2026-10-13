# SPDX-License-Identifier: AGPL-3.0-or-later
"""The overview's lock and climate tiles read by the app's own labels."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from custom_components.vag_connect.companion.resources import read_overview_resources
from custom_components.vag_connect.companion.screen import UiNode, parse_ui_dump

FIXTURES = Path(__file__).parent / "fixtures"
STRINGS = {
    k: set(v) for k, v in json.loads(
        (FIXTURES / "companion_battery" / "vw_432_resources.json").read_text(encoding="utf-8")
    ).items()
}
GERMAN = {
    "acc_vehicle_tab_label_lock_unlock_vehicle": {"Fahrzeug"},
    "acc_vehicle_tab_value_lock_unlock_vehicle_state_locked": {"Verriegelt"},
    "acc_vehicle_tab_value_lock_unlock_vehicle_state_unlocked": {"Entriegelt"},
    "acc_vehicle_tab_clima_tile_label": {"Vorklimatisierung"},
    "acc_vehicle_tab_clima_tile_value_all_clima_on": {"Ein"},
    "acc_vehicle_tab_clima_tile_value_all_clima_off": {"Aus"},
}


def _dump(name: str) -> list[UiNode]:
    return parse_ui_dump((FIXTURES / "companion_climate" / f"{name}.xml").read_text(encoding="utf-8"))


def _tiles(*descs: str) -> list[UiNode]:
    return [UiNode("", d, "", "android.view.View", False, None) for d in descs]


def test_tiguan_overview():
    xml = (FIXTURES / "companion_overview" / "tiguan_overview_locked.xml").read_text(encoding="utf-8")
    assert read_overview_resources(parse_ui_dump(xml), STRINGS) == {
        "doors_locked": True, "climatisation_active": False, "climatisation_state": "Off",
    }


def test_golf_with_climate_running():
    out = read_overview_resources(_dump("gte_overview_climate_on"), STRINGS)
    assert out["climatisation_active"] is True and out["climatisation_state"] == "On"


def test_german_tiles_by_their_own_labels():
    out = read_overview_resources(_dump("id4_overview_de"), GERMAN)
    assert out["climatisation_active"] is False and out["climatisation_state"] == "Aus"


def test_a_language_the_selectors_do_not_know():
    italian = {
        "acc_vehicle_tab_label_lock_unlock_vehicle": {"Veicolo"},
        "acc_vehicle_tab_value_lock_unlock_vehicle_state_unlocked": {"Sbloccato"},
    }
    assert read_overview_resources(_tiles("Veicolo. Sbloccato. Apri dettagli"), italian) == {
        "doors_locked": False,
    }


@pytest.mark.parametrize("desc", [
    "Vehicle. Is being locked. Open details",
    "Climate control. Air conditioning information not available. Open details",
    "Vehicle Health Report. Open details",
])
def test_values_the_app_does_not_name_as_a_state_are_left_alone(desc):
    assert read_overview_resources(_tiles(desc), STRINGS) == {}
