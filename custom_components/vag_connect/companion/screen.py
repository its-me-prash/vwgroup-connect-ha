# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Parse a ``uiautomator dump`` and resolve preset selectors against it.

Pure, hardware-free, and therefore the part with the real test coverage. The
transport hands us the XML string that ``uiautomator dump`` produces; from here
on there is no device involved. Keeping the parse/match logic isolated like
this is what lets the fragile bit (ADB itself) stay a thin shell.
"""
from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass
from xml.etree import ElementTree as ET

from .presets import (
    ActionSelector,
    BrandPreset,
    FieldSelector,
    OverlaySelector,
    coerce,
)


def _rid_matches(node_rid: str | None, sel_rid: str) -> bool:
    """Match a selector resource-id against a node's, tolerant of the package
    prefix. Some builds render the full ``com.pkg:id/rangeArcBatterySoc``,
    others (e.g. plainmad's Mk8 dump, #968) the bare ``rangeArcBatterySoc``."""
    if not node_rid:
        return False
    return node_rid == sel_rid or node_rid.endswith("/" + sel_rid)


@dataclass(frozen=True)
class UiNode:
    """One node of the accessibility tree, flattened to what we match on."""

    resource_id: str
    content_desc: str
    text: str
    clazz: str
    clickable: bool
    bounds: tuple[int, int, int, int] | None  # (l, t, r, b) in device px
    # v4.4.0 — the three attributes uiautomator always emits and we previously
    # dropped. ``checked`` is the only way to read a settings toggle (the row's
    # text says what it is, not whether it is on), and ``enabled`` keeps a
    # greyed-out control from being treated as a live tap target.
    checkable: bool = False
    checked: bool = False
    enabled: bool = True

    @property
    def tap_point(self) -> tuple[int, int] | None:
        """Centre of the node, the point ``input tap`` would target."""
        if self.bounds is None:
            return None
        left, top, right, bottom = self.bounds
        return ((left + right) // 2, (top + bottom) // 2)


_BOUNDS_RE = re.compile(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]")


def _parse_bounds(raw: str | None) -> tuple[int, int, int, int] | None:
    if not raw:
        return None
    m = _BOUNDS_RE.search(raw)
    if not m:
        return None
    return (int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4)))


def parse_ui_dump(xml: str) -> list[UiNode]:
    """Flatten a uiautomator XML dump into an ordered list of ``UiNode``.

    Order is document order (a pre-order walk), which is what the sibling-value
    resolution below relies on: on these screens the value node follows its
    label node.
    """
    if not xml or not xml.strip():
        return []
    try:
        root = ET.fromstring(xml)
    except ET.ParseError:
        return []
    out: list[UiNode] = []
    for el in root.iter("node"):
        a = el.attrib
        out.append(
            UiNode(
                resource_id=a.get("resource-id", ""),
                content_desc=a.get("content-desc", ""),
                text=a.get("text", ""),
                clazz=a.get("class", ""),
                clickable=a.get("clickable", "false") == "true",
                bounds=_parse_bounds(a.get("bounds")),
                checkable=a.get("checkable", "false") == "true",
                checked=a.get("checked", "false") == "true",
                enabled=a.get("enabled", "true") == "true",
            )
        )
    return out


_BARE_NUMBER_RE = re.compile(r"-?\d{1,3}(?:[.,]\d)?")


def centre_number(nodes: list[UiNode], rid: str) -> str | None:
    """The numeric text nearest the horizontal centre of a container node.

    v4.4.0 — for a value the app renders with no label, no id and nothing
    beside it: the climate detail's target temperature, drawn in the middle of
    the temperature dial. Only nodes fully inside the container are considered,
    so a number elsewhere on the screen can never be picked up, and ties break
    towards the earlier node for determinism.
    """
    container = next(
        (n for n in nodes if _rid_matches(n.resource_id, rid) and n.bounds), None
    )
    if container is None or container.bounds is None:
        return None
    left, top, right, bottom = container.bounds
    centre_x = (left + right) / 2
    best: tuple[float, str] | None = None
    for node in nodes:
        if not node.text or node.bounds is None:
            continue
        text = node.text.strip()
        if not _BARE_NUMBER_RE.fullmatch(text):
            continue
        n_left, n_top, n_right, n_bottom = node.bounds
        if not (left <= n_left <= n_right <= right and top <= n_top <= n_bottom <= bottom):
            continue
        distance = abs((n_left + n_right) / 2 - centre_x)
        if best is None or distance < best[0]:
            best = (distance, text)
    return best[1] if best else None


def _iter_field_raws(nodes: list[UiNode], sel: FieldSelector) -> Iterator[str]:
    """Yield every raw string a selector could resolve to, in preference order.

    v2.26.0 (ckomma #19) — resource-id, then content-description, then a
    localized label's value. ``read_fields`` takes the first that COERCES to a
    valid value, so a leading placeholder ("--", "—", an out-of-range number)
    no longer drops the field when a later node carries the real reading.
    """
    # 0) geometric — a value with no label of any kind (v4.4.0).
    if sel.centre_of_rid:
        found = centre_number(nodes, sel.centre_of_rid)
        if found:
            yield found

    # 1) resource-id — the value is the node's own text.
    if sel.resource_id:
        for n in nodes:
            if _rid_matches(n.resource_id, sel.resource_id):
                v = n.text or n.content_desc
                if v:
                    yield v

    # 2) content-description — capture group if present, else the whole desc.
    if sel.content_desc_re:
        rx = re.compile(sel.content_desc_re, re.I)
        for n in nodes:
            if not n.content_desc:
                continue
            m = rx.search(n.content_desc)
            if m:
                yield m.group(1) if m.groups() else n.content_desc

    # 3) localized label — find the label node, then read the value.
    if sel.label_re:
        rx = re.compile(sel.label_re, re.I)
        for i, n in enumerate(nodes):
            hay = n.text or n.content_desc
            if not hay or not rx.search(hay):
                continue
            if sel.value_from == "self":
                yield hay
            else:
                # "sibling": nearby nodes that carry their own text.
                for sib in nodes[i + 1:i + 4]:
                    if sib.text and sib.text.strip() and sib.text != hay:
                        yield sib.text

    # 4) unit-adjacent bare number (#968, split-node apps like My CUPRA): the
    # value ("51") and its unit ("%") are separate text nodes with no label.
    # Match the UNIT node, take the nearest preceding bare-number node (within a
    # small window so a far-away number never binds to the wrong unit).
    if sel.unit_re:
        rx = re.compile(sel.unit_re)
        for i, n in enumerate(nodes):
            if not n.text or not rx.fullmatch(n.text.strip()):
                continue
            for prev in reversed(nodes[max(0, i - 3):i]):
                if prev.text and re.fullmatch(r"\d{1,4}", prev.text.strip()):
                    yield prev.text.strip()
                    break


def _match_field_raw(nodes: list[UiNode], sel: FieldSelector) -> str | None:
    """The first candidate a selector resolves to (presence check, for anchors)."""
    return next(_iter_field_raws(nodes, sel), None)


def read_selectors(
    nodes: list[UiNode], selectors: "tuple[FieldSelector, ...]"
) -> dict[str, object]:
    """Resolve a tuple of field selectors against the parsed screen.

    Returns only the fields that coerced to a value, so a partial screen never
    writes a spurious ``None``. Numeric-preferring (ckomma #19): the first
    candidate that coerces to a valid value wins, not merely the first that
    matches, so a "--" placeholder ahead of the real number is skipped.
    """
    out: dict[str, object] = {}
    for sel in selectors:
        for raw in _iter_field_raws(nodes, sel):
            val = coerce(sel.parse, raw)
            if val is not None:
                out[sel.target] = val
                break
    return out


def read_fields(nodes: list[UiNode], preset: BrandPreset) -> dict[str, object]:
    """Resolve every overview field selector against the parsed screen."""
    return read_selectors(nodes, preset.fields)


def find_overlay(nodes: list[UiNode], preset: BrandPreset) -> OverlaySelector | None:
    """Return the first known nag/interstitial overlay present on the screen.

    v2.26.0 (ckomma #8/#13/#20). Matched on content-description or visible text.
    The caller dismisses it with BACK and re-dumps.
    """
    for ov in preset.overlays:
        for n in nodes:
            if (
                ov.content_desc_re
                and n.content_desc
                and re.search(ov.content_desc_re, n.content_desc, re.I)
            ):
                return ov
            if ov.text_re and n.text and re.search(ov.text_re, n.text, re.I):
                return ov
    return None


def find_rate_limit_banner(
    nodes: list[UiNode], preset: BrandPreset
) -> OverlaySelector | None:
    """Return a "too many requests / temporarily blocked" banner if present.

    v2.26.0 (ckomma #21). Unlike a nag (dismissed with BACK), this means back
    off: the caller trips a long persisted cooldown and stops writing.
    """
    for banner in preset.rate_limit_banners:
        for n in nodes:
            if (
                banner.content_desc_re
                and n.content_desc
                and re.search(banner.content_desc_re, n.content_desc, re.I)
            ):
                return banner
            if banner.text_re and n.text and re.search(banner.text_re, n.text, re.I):
                return banner
    return None


def _unit_seconds(unit: str) -> int | None:
    u = unit.lower()
    if u.startswith(("sek", "sec")):
        return 1
    if u.startswith("min"):
        return 60
    if u.startswith(("std", "stund", "hour")) or u == "h":
        return 3600
    if u.startswith(("tag", "day")) or u == "d":
        return 86400
    return None


def find_sync_age(nodes: list[UiNode], preset: BrandPreset) -> float | None:
    """Parse the app's "synchronised N ago" line into an age in seconds.

    v2.26.0 (ckomma #22). Returns None if the preset has no sync line configured
    or none is on screen. Lets the channel report how old the CAR's data is
    (a VW-side freshness signal), separate from connector health.
    """
    if not preset.sync_age_re:
        return None
    rx = re.compile(preset.sync_age_re, re.I)
    for n in nodes:
        hay = n.text or n.content_desc
        if not hay:
            continue
        m = rx.search(hay)
        if m:
            mult = _unit_seconds(m.group(2))
            if mult is not None:
                return float(int(m.group(1)) * mult)
    return None


def has_anchor(nodes: list[UiNode], preset: BrandPreset) -> bool:
    """True if the preset's screen-identity anchor is present (or none is set).

    v2.26.0 (ckomma #10/#20). Gates a read/tap so a stray screen yields no_data
    rather than a wrong value. A preset with no ``screen_anchor`` returns True
    (best-effort, VW until a dump confirms an anchor).
    """
    if preset.screen_anchor is None:
        return True
    return _match_field_raw(nodes, preset.screen_anchor) is not None


def find_node_for(nodes: list[UiNode], spec: "ActionSelector") -> UiNode | None:
    """Find the tappable node matching an ActionSelector, or None if absent.

    Prefers a clickable node; a matching but non-clickable node is returned only
    if nothing clickable matched, so the caller can decide whether to tap its
    centre anyway. Used both for logical write actions and for the nav-read tile
    (C9) that opens a detail screen.
    """
    candidates: list[UiNode] = []
    for n in nodes:
        # v4.4.0 — a greyed-out control is on screen but not a live tap target;
        # tapping it does nothing and the walk would then read the wrong screen.
        if not n.enabled:
            continue
        hit = False
        if spec.resource_id and _rid_matches(n.resource_id, spec.resource_id):
            hit = True
        elif spec.content_desc_re and n.content_desc and re.search(
            spec.content_desc_re, n.content_desc, re.I
        ):
            hit = True
        elif spec.label_re and (n.text or n.content_desc) and re.search(
            spec.label_re, n.text or n.content_desc, re.I
        ):
            hit = True
        if hit:
            candidates.append(n)
    if not candidates:
        return None
    clickable = [n for n in candidates if n.clickable and n.tap_point]
    return clickable[0] if clickable else candidates[0]


def screen_bounds(nodes: list[UiNode]) -> tuple[int, int, int, int] | None:
    """The largest node's box, i.e. the screen itself.

    v4.4.0 — lets a scroll be expressed in fractions of the actual display
    rather than in pixels from whichever phone a flow was first written on.
    """
    best: tuple[int, tuple[int, int, int, int]] | None = None
    for node in nodes:
        if node.bounds is None:
            continue
        left, top, right, bottom = node.bounds
        area = (right - left) * (bottom - top)
        if area > 0 and (best is None or area > best[0]):
            best = (area, node.bounds)
    return best[1] if best else None


def tap_point_for(node: UiNode, fraction: tuple[float, float] | None) -> tuple[int, int] | None:
    """Where to tap on a node: its centre, or a fraction of its own box.

    v4.4.0 — the parked-car marker is drawn on the map but is absent from the
    accessibility tree, so the only way to open it is a point inside the map
    node. Expressed as a fraction so it holds across screen sizes.
    """
    if fraction is None:
        return node.tap_point
    if node.bounds is None:
        return None
    left, top, right, bottom = node.bounds
    frac_x, frac_y = fraction
    return (
        int(left + (right - left) * frac_x),
        int(top + (bottom - top) * frac_y),
    )


def find_action_node(nodes: list[UiNode], preset: BrandPreset, action: str) -> UiNode | None:
    """Find the tappable node for a logical action, or None if not present."""
    spec = next((a for a in preset.actions if a.action == action), None)
    if spec is None:
        return None
    return find_node_for(nodes, spec)
