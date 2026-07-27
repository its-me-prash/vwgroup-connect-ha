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
from dataclasses import dataclass
from xml.etree import ElementTree as ET

from .presets import BrandPreset, FieldSelector, OverlaySelector, coerce


@dataclass(frozen=True)
class UiNode:
    """One node of the accessibility tree, flattened to what we match on."""

    resource_id: str
    content_desc: str
    text: str
    clazz: str
    clickable: bool
    bounds: tuple[int, int, int, int] | None  # (l, t, r, b) in device px

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
            )
        )
    return out


def _match_field_raw(nodes: list[UiNode], sel: FieldSelector) -> str | None:
    """Return the raw string a selector resolves to, or None.

    Tries resource-id, then content-description (with capture-group support),
    then a localized label whose value is on the node itself or its sibling.
    """
    # 1) resource-id — the value is the node's own text.
    if sel.resource_id:
        for n in nodes:
            if n.resource_id == sel.resource_id:
                return n.text or n.content_desc or None

    # 2) content-description — if the regex has a capture group, return it;
    #    otherwise the whole content-desc is the value (used for state strings).
    if sel.content_desc_re:
        rx = re.compile(sel.content_desc_re, re.I)
        for n in nodes:
            if not n.content_desc:
                continue
            m = rx.search(n.content_desc)
            if m:
                return m.group(1) if m.groups() else n.content_desc

    # 3) localized label — find the label node, then read the value.
    if sel.label_re:
        rx = re.compile(sel.label_re, re.I)
        for i, n in enumerate(nodes):
            hay = n.text or n.content_desc
            if not hay or not rx.search(hay):
                continue
            if sel.value_from == "self":
                return hay
            # "sibling": the next node in document order that actually carries
            # text and is not the label itself.
            for sib in nodes[i + 1:i + 4]:
                if sib.text and sib.text.strip() and sib.text != hay:
                    return sib.text
    return None


def read_fields(nodes: list[UiNode], preset: BrandPreset) -> dict[str, object]:
    """Resolve every field selector in the preset against the parsed screen.

    Returns only the fields that actually matched and coerced to a value, so a
    partial screen never writes a spurious ``None`` over anything downstream.
    """
    out: dict[str, object] = {}
    for sel in preset.fields:
        raw = _match_field_raw(nodes, sel)
        val = coerce(sel.parse, raw if isinstance(raw, str) else None)
        if val is not None:
            out[sel.target] = val
    return out


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


def has_anchor(nodes: list[UiNode], preset: BrandPreset) -> bool:
    """True if the preset's screen-identity anchor is present (or none is set).

    v2.26.0 (ckomma #10/#20). Gates a read/tap so a stray screen yields no_data
    rather than a wrong value. A preset with no ``screen_anchor`` returns True
    (best-effort, VW until a dump confirms an anchor).
    """
    if preset.screen_anchor is None:
        return True
    return _match_field_raw(nodes, preset.screen_anchor) is not None


def find_action_node(nodes: list[UiNode], preset: BrandPreset, action: str) -> UiNode | None:
    """Find the tappable node for a logical action, or None if not present.

    Prefers a clickable node; a matching but non-clickable node is returned only
    if nothing clickable matched, so the caller can decide whether to tap its
    centre anyway.
    """
    spec = next((a for a in preset.actions if a.action == action), None)
    if spec is None:
        return None
    candidates: list[UiNode] = []
    for n in nodes:
        hit = False
        if spec.resource_id and n.resource_id == spec.resource_id:
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
