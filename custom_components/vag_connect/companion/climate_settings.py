# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The Air Conditioning sheet's Climate Settings page and its Zones page.

What the app does, from the VW 4.6.4 captures (settings-save/, zone runs):

* Settings carries two switches tagged ``ClimatisationAtUnlockEnabled``
  ("Auxiliary air conditioning") and ``WindowHeatingEnabled`` ("Automatic
  window heating"), and a Zones row whose value is one zone by name, "2 zones"
  or nothing. Its toolbar has ``climatisationSettingsLeading`` (back) and,
  only while the page differs from what is saved, ``climatisationSettingsTrailing``
  (Save). Toggling a switch back removes Save again.
* The Zones row opens a page with one switch per zone and no ids at all: each
  row is found by the app's own zone label, its switch on the same line. The
  toolbar arrow (a Button left of the "Zones" title) carries the change back
  to Settings; Android BACK leaves the Zones page without it.
* Save sends and closes Settings onto the sheet; opening Settings again shows
  the saved state.

Everything here is a pure finder over one dump; ``CompanionChannel`` does the
walking, tapping and reading back.
"""
from __future__ import annotations

from .presets import ActionSelector
from .resources import CLIMA_ZONE_KEYS, CLIMA_ZONES, StringResources, _labels
from .screen import UiNode, _rid_matches, find_node_for

SAVE = ActionSelector(action="save_climate_settings", resource_id="climatisationSettingsTrailing")
LEADING_RID = "climatisationSettingsLeading"
# Setting → the switch's test tag on the Settings page.
TOGGLES: dict[str, str] = {
    "climate_at_unlock": "ClimatisationAtUnlockEnabled",
    "window_heating_enabled": "WindowHeatingEnabled",
}
# Zone setting → the app string that labels its row on the Zones page.
ZONES: dict[str, str] = {
    target: key for key, target in CLIMA_ZONE_KEYS.items()
    if target in ("climate_zone_front_left", "climate_zone_front_right")
}
# Names for messages; the app's own words are not needed to say what failed.
NAMES: dict[str, str] = {
    "climate_at_unlock": "auxiliary air conditioning",
    "window_heating_enabled": "automatic window heating",
    "climate_zone_front_left": "front left zone",
    "climate_zone_front_right": "front right zone",
}


def on_settings_page(nodes: list[UiNode]) -> bool:
    return any(_rid_matches(n.resource_id, LEADING_RID) for n in nodes)


def find_save(nodes: list[UiNode]) -> UiNode | None:
    """Save, drawn only while a change is staged."""
    node = find_node_for(nodes, SAVE)
    return node if node is not None and node.enabled and node.tap_point else None


def find_toggle(nodes: list[UiNode], key: str) -> UiNode | None:
    rid = TOGGLES[key]
    return next(
        (n for n in nodes if n.checkable and n.tap_point and _rid_matches(n.resource_id, rid)),
        None,
    )


def _same_line(a: UiNode, b: UiNode) -> bool:
    """``b`` spans the vertical centre of ``a`` (a label and its control)."""
    if a.bounds is None or b.bounds is None:
        return False
    centre = (a.bounds[1] + a.bounds[3]) / 2
    return b.bounds[1] <= centre <= b.bounds[3]


def _contains(outer: UiNode, inner: UiNode) -> bool:
    if outer.bounds is None or inner.bounds is None:
        return False
    left, top, right, bottom = outer.bounds
    i_left, i_top, i_right, i_bottom = inner.bounds
    return left <= i_left and top <= i_top and i_right <= right and i_bottom <= bottom


def _area(node: UiNode) -> int:
    assert node.bounds is not None
    return (node.bounds[2] - node.bounds[0]) * (node.bounds[3] - node.bounds[1])


def find_zones_row(nodes: list[UiNode], resources: StringResources) -> UiNode | None:
    """The Settings page's Zones row: the smallest clickable box around its title."""
    titles = _labels(resources, CLIMA_ZONES)
    label = next(
        (n for n in nodes if n.text and n.text.strip().casefold() in titles and n.bounds),
        None,
    )
    if label is None:
        return None
    rows = [
        n for n in nodes
        if n.clickable and n.enabled and n.tap_point and n is not label and _contains(n, label)
    ]
    return min(rows, key=_area) if rows else None


def _zones_title(nodes: list[UiNode], resources: StringResources) -> UiNode | None:
    titles = _labels(resources, CLIMA_ZONES)
    return next(
        (
            n for n in nodes
            if n.content_desc and n.content_desc.strip().casefold() in titles and n.bounds
        ),
        None,
    )


def on_zones_page(nodes: list[UiNode], resources: StringResources) -> bool:
    return not on_settings_page(nodes) and _zones_title(nodes, resources) is not None


def find_zone_switch(
    nodes: list[UiNode], resources: StringResources, key: str,
) -> UiNode | None:
    """The switch on the line of the zone's own label, on the Zones page only."""
    if not on_zones_page(nodes, resources):
        return None
    names = _labels(resources, ZONES[key])
    label = next(
        (n for n in nodes if n.text and n.text.strip().casefold() in names and n.bounds),
        None,
    )
    if label is None or label.bounds is None:
        return None
    return next(
        (
            n for n in nodes
            if n.checkable and n.tap_point and n.bounds is not None
            and n.bounds[0] >= label.bounds[2] and _same_line(label, n)
        ),
        None,
    )


def find_zones_back(nodes: list[UiNode], resources: StringResources) -> UiNode | None:
    """The Zones page's toolbar arrow: the Button on the title's line, left of it."""
    title = _zones_title(nodes, resources)
    if title is None or title.bounds is None or on_settings_page(nodes):
        return None
    title_centre = (title.bounds[0] + title.bounds[2]) / 2
    return next(
        (
            n for n in nodes
            if n.clickable and n.enabled and n.tap_point and n.clazz.endswith("Button")
            and _same_line(title, n) and n.tap_point[0] < title_centre
        ),
        None,
    )
