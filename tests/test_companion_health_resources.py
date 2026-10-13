# SPDX-License-Identifier: AGPL-3.0-or-later
"""The Vehicle Health Report read by the installed app's own subheads."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from custom_components.vag_connect.companion.resources import read_health_resources
from custom_components.vag_connect.companion.screen import UiNode, parse_ui_dump

FIXTURES = Path(__file__).parent / "fixtures"
STRINGS = {
    k: set(v) for k, v in json.loads(
        (FIXTURES / "companion_battery" / "vw_432_resources.json").read_text(encoding="utf-8")
    ).items()
}


def _read(name: str) -> dict[str, object]:
    xml = (FIXTURES / "companion_health" / f"{name}.xml").read_text(encoding="utf-8")
    return read_health_resources(parse_ui_dump(xml), STRINGS)


def test_tiguan_service_has_days_and_distance():
    assert _read("tiguan_health") == {
        "odometer_km": 322, "service_due_in_days": 711, "service_km": 29700,
        "warning_active": False, "warning_count": 0, "warning_messages": "",
    }


def test_imperial_golf_converts_miles():
    assert _read("gte_health") == {
        "odometer_km": 35430,
        "service_due_in_days": 71, "service_km": 19473,
        "oil_service_due_in_days": 71, "oil_service_km": 2414,
        "warning_active": False, "warning_count": 0, "warning_messages": "",
    }


def _rows(*texts: str) -> list[UiNode]:
    return [UiNode("", "", t, "android.widget.TextView", False, None) for t in texts]


@pytest.mark.parametrize(("value", "expected"), [
    ("120 Tage / 12.100 km", {"service_due_in_days": 120, "service_km": 12100}),
    ("15 000 km", {"service_km": 15000}),
    ("30 days", {"service_due_in_days": 30}),
    ("Currently due", {}),
])
def test_service_value_forms(value, expected):
    assert read_health_resources(_rows("Next service", value), STRINGS) == expected


def test_translated_subhead():
    strings = {"screen_vehiclehealth_subhead_totaldistance": {"Kilometerstand"}}
    assert read_health_resources(_rows("Kilometerstand", "12.345 km"), strings) == {"odometer_km": 12345}


def _warning_rows(title: str, *rows: tuple[str, str, str | None]) -> list[UiNode]:
    nodes = [UiNode("warningHeaderTitle", "", title, "android.widget.TextView", False, (0, 0, 9, 9))]
    for index, (rid, name, value) in enumerate(rows):
        top = 100 * (index + 1)
        nodes.append(UiNode(rid, "", name, "android.widget.TextView", False, (50, top, 300, top + 40)))
        if value is not None:
            nodes.append(UiNode("warningValue", "", value, "android.widget.TextView", False,
                                (600, top + 5, 900, top + 35)))
    return nodes


def test_issues_found_names_the_categories_with_a_value():
    nodes = _warning_rows(
        "Issues found",
        ("warningNameBrake", "Brakes", "Brake fluid"),
        ("warningNameTire", "Tyres", None),
        ("warningNameLighting", "Lighting", "Low beam left"),
    )
    assert read_health_resources(nodes, STRINGS) == {
        "warning_active": True, "warning_count": 2,
        "warning_messages": "Brakes: Brake fluid, Lighting: Low beam left",
    }


def test_issues_found_without_rows_sets_only_the_flag():
    nodes = _warning_rows("Issues found", ("warningNameBrake", "Brakes", None))
    assert read_health_resources(nodes, STRINGS) == {"warning_active": True}


def test_unknown_warning_header_reads_nothing():
    assert read_health_resources(_warning_rows("Something else"), STRINGS) == {}
