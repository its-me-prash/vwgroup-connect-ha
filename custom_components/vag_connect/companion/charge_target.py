# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The Volkswagen vehicle Settings "Charging up to" slider (app 4.3.2).

The slider itself (``GradientSlider``, a Material ``Slider``) is not in the
UIAutomator tree, so it cannot be found by id. Its two neighbours are, and the
installed 4.3.2 layout (``item_vehicle_settings_slider``) fixes how the track
sits between them, in dp:

- the card is inset 20 dp and ``subtitle`` another 20 dp, so ``subtitle.left``
  is 40 dp from the screen edge: that is the scale, measured on the phone;
- the slider starts 8 dp into the card and ends 8 dp before ``value``, and
  Material insets the track another 18 dp at each end;
- ``value`` is centred vertically on the slider.

Every number is therefore relative to nodes the phone reports, never a pixel
from one device. The result is checked against the slider's own bounds at
densities 320, 420 and 560 on a live phone, and every tap is read back from
``value`` before anything is saved.

Moving the slider sends nothing: the app keeps the value on screen and shows
a Save button (``vwd_save_button``). Only Save sends the setting.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass

from .screen import UiNode

CHARGE_TARGET_APP_VERSIONS = ("4.3.2",)
TARGET_MIN = 50
TARGET_MAX = 100
TARGET_STEP = 10

_CARD_TO_SUBTITLE_DP = 40.0  # card margin 20 dp + subtitle margin 20 dp
_TRACK_START_DP = 6.0        # -20 subtitle margin +8 slider margin +18 track inset
_TRACK_END_DP = 26.0         # 8 dp slider margin + 18 dp track inset, before value
_PERCENT_RE = re.compile(r"^\s*(\d{2,3})\s*%\s*$")


def snap_target(target: float) -> int:
    """The nearest value the slider can take: 50 … 100 in steps of 10."""
    # Half rounds up (75 → 80), as a person reading the slider would expect.
    step = math.floor((float(target) - TARGET_MIN) / TARGET_STEP + 0.5)
    return int(min(TARGET_MAX, max(TARGET_MIN, TARGET_MIN + step * TARGET_STEP)))


def _rid(node: UiNode) -> str:
    return node.resource_id.rsplit("/", 1)[-1]


@dataclass(frozen=True)
class ChargeTargetRow:
    """Where the slider's track is on this phone, and what it shows now."""

    current: int
    track_start: float
    track_end: float
    y: int

    def tap_point(self, target: int) -> tuple[int, int]:
        fraction = (target - TARGET_MIN) / (TARGET_MAX - TARGET_MIN)
        x = self.track_start + fraction * (self.track_end - self.track_start)
        return round(x), self.y


def find_charge_target_row(nodes: list[UiNode]) -> ChargeTargetRow | None:
    """Locate the slider row from its ``value`` and ``subtitle`` neighbours.

    Language-independent: ids and the digits of "80%" only. Returns None for
    anything that does not look like this row, so nothing is tapped blind.
    """
    for value in nodes:
        if _rid(value) != "value" or value.bounds is None:
            continue
        m = _PERCENT_RE.match(value.text)
        if not m or not TARGET_MIN <= int(m.group(1)) <= TARGET_MAX:
            continue
        v_left, v_top, _v_right, v_bottom = value.bounds
        # The row's own subtitle: the nearest one above the value, same card.
        above = [
            n for n in nodes
            if _rid(n) == "subtitle" and n.bounds is not None
            and n.bounds[3] <= v_top and n.bounds[0] < v_left
        ]
        if not above:
            continue
        subtitle = max(above, key=lambda n: n.bounds[3] if n.bounds else 0)
        assert subtitle.bounds is not None
        dp = subtitle.bounds[0] / _CARD_TO_SUBTITLE_DP
        start = subtitle.bounds[0] + _TRACK_START_DP * dp
        end = v_left - _TRACK_END_DP * dp
        # A track under 100 dp is not this layout.
        if dp <= 0 or end - start < 100 * dp:
            continue
        return ChargeTargetRow(
            current=int(m.group(1)),
            track_start=start,
            track_end=end,
            y=(v_top + v_bottom) // 2,
        )
    return None


def find_save_button(nodes: list[UiNode]) -> UiNode | None:
    """The toolbar's Save, shown only while a change is pending."""
    return next((
        n for n in nodes
        if _rid(n) == "vwd_save_button" and n.enabled and n.tap_point is not None
    ), None)


def is_syncing(nodes: list[UiNode]) -> bool:
    """The toolbar's "Synchronising ..." line while the app sends the change."""
    return any(_rid(n) == "vwd_progress_text" and n.text for n in nodes)
