# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#2198 (@SaschaWeicht) — the companion read the vehicle Settings screen but
skipped its "Reduced AC charging current" switch.

The app turns that switch on for ``maxChargeCurrentAC == "reduced"`` and off for
``"maximum"`` (ChargingSettingsMapper, We Connect 4.10.1). The switch is now
read into ``max_charge_current_ac`` with the EU Data Act portal's own values,
REDUCED or MAXIMUM, so the existing "Max AC charge current" sensor shows it.
The screen is a real capture (Tiguan eHybrid, app 4.3.2, switch off); the
"on" case flips that one switch in the same capture.
"""
from __future__ import annotations

import dataclasses
import json
from pathlib import Path

from custom_components.vag_connect.companion.presets import PRESETS
from custom_components.vag_connect.companion.resources import (
    SETTINGS_SWITCHES,
    read_settings_resources,
)
from custom_components.vag_connect.companion.screen import parse_ui_dump

FIXTURES = Path(__file__).parent / "fixtures" / "companion_battery"
_BASE = {
    k: set(v)
    for k, v in json.loads((FIXTURES / "vw_432_resources.json").read_text(encoding="utf-8")).items()
}
# The app's own English text for the key (strings.xml, We Connect 4.8.1 and 4.10.1).
STRINGS = {**_BASE, "vehiclesettingsscreen_reducedchargingspeed": {"Reduced AC charging current"}}


def _settings_nodes():
    return parse_ui_dump((FIXTURES / "tiguan_settings_switches.xml").read_text(encoding="utf-8"))


def _with_reduced_switch(checked: bool):
    nodes = _settings_nodes()
    label = next(n for n in nodes if n.text == "Reduced AC charging current")
    lx = (label.bounds[0] + label.bounds[2]) // 2
    ly = (label.bounds[1] + label.bounds[3]) // 2
    out, flipped = [], 0
    for n in nodes:
        b = n.bounds
        if n.checkable and b is not None and b[0] <= lx <= b[2] and b[1] <= ly <= b[3]:
            n = dataclasses.replace(n, checked=checked)
            flipped += 1
        out.append(n)
    assert flipped == 1, "exactly one switch row holds the label"
    return out


def test_switch_off_reads_maximum() -> None:
    out = read_settings_resources(_settings_nodes(), STRINGS)
    assert out == {"auto_unlock_when_charged": True, "max_charge_current_ac": "MAXIMUM"}


def test_switch_on_reads_reduced() -> None:
    out = read_settings_resources(_with_reduced_switch(True), STRINGS)
    assert out["max_charge_current_ac"] == "REDUCED"
    # The other switch on the same screen is untouched.
    assert out["auto_unlock_when_charged"] is True


def test_without_the_label_in_the_app_strings_nothing_is_read() -> None:
    # An app whose strings do not carry the key gives no value, not a guess.
    out = read_settings_resources(_settings_nodes(), _BASE)
    assert "max_charge_current_ac" not in out


def test_screen_without_switch_rows_reads_nothing() -> None:
    nodes = parse_ui_dump((FIXTURES / "tiguan_settings.xml").read_text(encoding="utf-8"))
    assert read_settings_resources(nodes, STRINGS) == {}


def test_values_match_the_portal_field() -> None:
    # Same field and same values the EU Data Act portal writes (_shorten_enum of
    # MAX_CHARGE_CURRENT_REDUCED / _MAXIMUM), so the two channels agree.
    assert SETTINGS_SWITCHES["vehiclesettingsscreen_reducedchargingspeed"] == (
        "max_charge_current_ac", "REDUCED", "MAXIMUM",
    )


def test_settings_walk_counts_the_new_value() -> None:
    # The walk is skipped only when every value it shows is known; the new
    # value has to be one of them, or a known charge limit would skip it.
    vw = PRESETS["volkswagen"]
    settings = next(nav for nav in vw.nav_reads if nav.name == "vehicle_settings")
    assert "max_charge_current_ac" in settings.resource_targets
