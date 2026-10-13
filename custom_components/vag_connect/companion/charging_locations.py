# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Read the VW app's charging locations, without changing their settings."""
from __future__ import annotations

import re
from dataclasses import dataclass

from .departure import WEEKDAYS, _inside, departure_rows
from .resources import CHARGING_PLURAL, StringResources, _labels
from .screen import UiNode

LOCATION_PARTS = (
    "name", "active", "active_timers", "reduced_ac_current", "auto_release_connector",
    *(f"timer_{timer}_{part}" for timer in range(1, 4) for part in ("enabled", "time", "weekdays")),
)
LOCATION_FIELDS = (
    "charging_location_count", "charging_location_current",
    *(f"charging_location_{slot}_{part}" for slot in range(1, 6) for part in LOCATION_PARTS),
)
TOGGLES = {
    "vehiclesettingsscreen_reducedchargingspeed": "reduced_ac_current",
    "vehiclesettingsscreen_automaticplugunlock": "auto_release_connector",
}


def active_timer_count(text: str, resources: StringResources) -> int | None:
    """Match a plural's own template, including its numberless zero form."""
    text = text.strip().casefold()
    for quantity in ("zero", "one", "two", "few", "many", "other"):
        for label in _labels(resources, f"{CHARGING_PLURAL}#{quantity}"):
            parts = re.split(r"%(?:[1-9]\d*\$)?[sd]", label)
            pattern = r"(\d+)".join(re.escape(part) for part in parts)
            match = re.fullmatch(pattern, text)
            if match:
                if match.groups():
                    return int(match.group(1))
                digits = re.search(r"\d+", text)
                if digits:
                    return int(digits.group())
                if quantity in ("zero", "one", "two"):
                    return {"zero": 0, "one": 1, "two": 2}[quantity]
    return None


def recurrence_days(text: str, resources: StringResources) -> str | None:
    """TimerMapper's recurrence label as ordered Home Assistant weekdays."""
    text = text.strip().casefold()
    for suffix, days in (("every_day", WEEKDAYS), ("weekdays", WEEKDAYS[:5]), ("weekend", WEEKDAYS[5:])):
        if text in _labels(resources, f"departure_timer_subscreen_{suffix}"):
            return ",".join(days)
    full = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
    for code, day in zip(WEEKDAYS, full):
        if text in _labels(resources, f"weekday_{day}"):
            return code
    found = set()
    for token in text.split(","):
        matches = [code for code in WEEKDAYS if token.strip() in _labels(resources, f"departure_timer_subscreen_{code}")]
        if len(matches) != 1:
            return None
        found.add(matches[0])
    return ",".join(code for code in WEEKDAYS if code in found)


@dataclass(frozen=True)
class LocationRow:
    """A location's name is the only safe target inside its row."""

    name: UiNode
    active: bool
    active_timers: int


def location_rows(nodes: list[UiNode], resources: StringResources) -> list[LocationRow]:
    """Location rows, recognised by their active-timer plural, top to bottom."""
    rows = []
    seen = set()
    bottom = min((n.bounds[1] for n in nodes if n.bounds
                  and n.resource_id.rsplit("/", 1)[-1] == "vehicle_tab_navigation"), default=None)
    active = _labels(resources, "common_status_active")
    for count in nodes:
        value = active_timer_count(count.text, resources) if count.text else None
        if value is None or count.bounds is None or (bottom is not None and count.bounds[3] > bottom):
            continue
        row = min(
            (n for n in nodes if n.clickable and not n.checkable and n.bounds and _inside(count, n.bounds)),
            key=lambda n: (n.bounds[3] - n.bounds[1]) if n.bounds else 0, default=None,
        )
        if row is None or row.bounds is None or row.bounds in seen:
            continue
        if any(n.checkable and _inside(n, row.bounds) for n in nodes):
            continue
        inside = [n for n in nodes if n.text and _inside(n, row.bounds)]
        name = next((n for n in inside if n.bounds and n.bounds[3] <= count.bounds[1]
                     and n.bounds[0] <= count.bounds[0] and n.enabled and not n.checkable), None)
        if name is None:
            continue
        seen.add(row.bounds)
        badge = any(
            n is not name and n.text.strip().casefold() in active
            and any(control.clickable and not control.checkable and control.bounds
                    and control.bounds != row.bounds and _inside(control, row.bounds)
                    and _inside(n, control.bounds) for control in nodes)
            for n in inside
        )
        rows.append(LocationRow(name, badge, value))
    return sorted(rows, key=lambda row: row.name.bounds[1] if row.name.bounds else 0)


def on_location_list(nodes: list[UiNode], resources: StringResources) -> bool:
    titles = _labels(resources, "acc_vehicle_tab_label_departure_times")
    return any(n.content_desc.strip().casefold() in titles for n in nodes if n.content_desc)


def charging_section_visible(nodes: list[UiNode], resources: StringResources) -> bool:
    labels = _labels(resources, "common_charging")
    return any(n.text.strip().casefold() in labels for n in nodes if n.text)


def location_title(nodes: list[UiNode], name: str) -> UiNode | None:
    """The toolbar title, above the timer rows, must name this location."""
    rows = departure_rows(nodes)
    top = rows[0].top if rows else 0
    return next((n for n in nodes if n.content_desc == name and n.bounds and n.bounds[3] < top), None)


def settings_icon(nodes: list[UiNode], name: str) -> UiNode | None:
    title = location_title(nodes, name)
    if title is None or title.bounds is None:
        return None
    _, top, right, bottom = title.bounds
    candidates = [n for n in nodes if n.clickable and n.enabled and not n.checkable
                  and not n.text and not n.content_desc and n.bounds
                  and n.bounds[0] >= right and n.bounds[1] < bottom and n.bounds[3] > top]
    return candidates[0] if len(candidates) == 1 else None


def location_timers(nodes: list[UiNode], resources: StringResources, slot: int) -> dict[str, object]:
    out: dict[str, object] = {}
    for timer, row in enumerate(departure_rows(nodes)[:3], 1):
        prefix = f"charging_location_{slot}_timer_{timer}"
        out[prefix + "_enabled"] = row.enabled
        out[prefix + "_time"] = row.time
        box = min((n.bounds for n in nodes if n.clickable and not n.checkable and n.bounds
                   and _inside(row.switch, n.bounds)), key=lambda b: b[3] - b[1], default=None)
        label = next((n for n in nodes if n.text and n.bounds and row.clock.bounds and box
                      and _inside(n, box) and n.bounds[1] >= row.clock.bounds[3]), None)
        days = recurrence_days(label.text, resources) if label else None
        if days is not None:
            out[prefix + "_weekdays"] = days
    return out


def on_location_settings(nodes: list[UiNode], resources: StringResources) -> bool:
    titles = _labels(resources, "screen_charging_settings_title")
    return any(n.content_desc.strip().casefold() in titles for n in nodes if n.content_desc)


def location_settings(nodes: list[UiNode], resources: StringResources, slot: int, name: str) -> dict[str, object]:
    """The location chip verifies scope; it is never a tap target."""
    if not on_location_settings(nodes, resources):
        return {}
    labels = _labels(resources, "screen_charging_settings_relatedlocation")
    label = next((n for n in nodes if n.text.strip().casefold() in labels and n.bounds), None)
    if label is None or label.bounds is None:
        return {}
    chip = next((n for n in nodes if n.clickable and n.text and n.bounds
                 and n.bounds[1] >= label.bounds[3]), None)
    if chip is None or chip.text != name:
        return {}
    out: dict[str, object] = {}
    for key, part in TOGGLES.items():
        labels = _labels(resources, key)
        label = next((n for n in nodes if n.text.strip().casefold() in labels), None)
        if label is None or label.bounds is None:
            continue
        # Compose exports the switch beside its label, within a clickable row.
        row = min((n for n in nodes if n.clickable and n.bounds and _inside(label, n.bounds)),
                  key=lambda n: (n.bounds[3] - n.bounds[1]) if n.bounds else 0, default=None)
        switch = next((n for n in nodes if n.checkable and row and row.bounds and _inside(n, row.bounds)), None)
        if switch:
            out[f"charging_location_{slot}_{part}"] = switch.checked
    return out
