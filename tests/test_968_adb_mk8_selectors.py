# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#968: ADB companion reads State-of-Charge on a Mk8 Golf GTE.

Grounded verbatim in plainmad's uiautomator dumps (We Connect 4.2.1): on the Mk8
the SoC lives on the charge-detail sheet, not the overview, on a node with
resource-id "rangeArcBatterySoc" (text "Battery 41 %", content-desc "Charging
status. Battery charge level: 41 per cent. Charging stopped"). It is added to the
charge-detail nav-read, and resource-id matching is now suffix-tolerant so the
bare id in the dump matches a package-prefixed id on other builds.

(Range on imperial units — "14 miles" — needs a unit-aware parse and is a
separate follow-up so miles are never mislabelled as km.)
"""
from __future__ import annotations

from custom_components.vag_connect.companion.presets import _VW
from custom_components.vag_connect.companion.screen import (
    UiNode,
    _rid_matches,
    read_selectors,
)


def _node(resource_id="", content_desc="", text="", clickable=False):
    return UiNode(
        resource_id=resource_id,
        content_desc=content_desc,
        text=text,
        clazz="android.widget.TextView",
        clickable=clickable,
        bounds=(0, 0, 10, 10),
    )


def _soc_nav_selector():
    nav = next(n for n in _VW.nav_reads if n.name == "charge_detail")
    return next(v for v in nav.values if v.target == "battery_soc")


def test_charge_detail_nav_has_battery_soc():
    # the crux: a nav-read reads only its own values, so SoC must be listed there
    nav = next(n for n in _VW.nav_reads if n.name == "charge_detail")
    assert any(v.target == "battery_soc" for v in nav.values)


def test_soc_reads_from_rangeArcBatterySoc_bare_and_prefixed():
    sel = _soc_nav_selector()
    bare = [_node(resource_id="rangeArcBatterySoc", text="Battery 41 %")]
    assert read_selectors(bare, (sel,)).get("battery_soc") == 41
    prefixed = [_node(
        resource_id="com.volkswagen.weconnect:id/rangeArcBatterySoc",
        text="Battery 41 %",
    )]
    assert read_selectors(prefixed, (sel,)).get("battery_soc") == 41


def test_soc_reads_from_content_desc_per_cent():
    sel = _soc_nav_selector()
    nodes = [_node(content_desc=(
        "Charging status. Battery charge level: 41 per cent. Charging stopped"
    ))]
    assert read_selectors(nodes, (sel,)).get("battery_soc") == 41


def test_rid_matches_is_suffix_tolerant():
    assert _rid_matches("rangeArcBatterySoc", "rangeArcBatterySoc")
    assert _rid_matches("com.pkg:id/rangeArcBatterySoc", "rangeArcBatterySoc")
    assert not _rid_matches("XrangeArcBatterySoc", "rangeArcBatterySoc")
    assert not _rid_matches(None, "rangeArcBatterySoc")
