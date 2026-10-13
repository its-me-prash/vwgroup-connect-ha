# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The Volkswagen Departure times list and a timer's "Set time" page.

The list (overview → Departure times) shows the climate timers in id order,
each as a clickable row with its clock text and an on/off switch. Tapping the
switch sends at once (APK 4.3.2 ``DepartureTimerViewModel.onSwitchClicked``:
optimistic flip, request, flip back on failure). Tapping the row opens the
timer's page (``fragment_edit_departure_timer``, unchanged ids on 4.6.4):

- ``time_picker``: Android's spinner TimePicker. Each wheel is a NumberPicker
  whose current value is the ``numberpicker_input`` EditText, with the
  previous value drawn as a Button above it and the next one below. A tap on
  either Button moves the wheel one step, which is how the picker is set here:
  one step at a time, each read back. Minutes come in the app's 5-minute steps.
- ``cta_monday`` … ``cta_sunday``: the days, on when ``selected``.
- ``cta_repeat``: the Repeat switch. Off makes a one-time timer on its one day.

Nothing on the page sends until the toolbar's Save (``common_button_save``),
shown in place of the title only while something differs from the saved
timer, beside Cancel (``common_button_cancel``), which restores it. A
successful save goes back to the list (``EditDepartureTimerViewModel``).
Language independent: ids, digits and the picker's own layout only; Save and
Cancel come from the installed app's translations.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from .screen import UiNode

# Home Assistant's own weekday codes, in the app's button order.
WEEKDAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
_DAY_IDS = {
    "mon": "cta_monday", "tue": "cta_tuesday", "wed": "cta_wednesday",
    "thu": "cta_thursday", "fri": "cta_friday", "sat": "cta_saturday",
    "sun": "cta_sunday",
}
TIMER_SAVE = "common_button_save"
TIMER_CANCEL = "common_button_cancel"

_TIME_RE = re.compile(r"^(\d{1,2})[:.](\d{2})$")
_MERIDIEM_RE = re.compile(r"^([ap])\.?\s?m\.?$", re.I)


def _rid(node: UiNode) -> str:
    return node.resource_id.rsplit("/", 1)[-1]


def _inside(node: UiNode, box: tuple[int, int, int, int]) -> bool:
    if node.bounds is None:
        return False
    left, top, right, bottom = box
    n_left, n_top, n_right, n_bottom = node.bounds
    return left <= n_left <= n_right <= right and top <= n_top <= n_bottom <= bottom


@dataclass(frozen=True)
class DepartureRow:
    """One timer row of the list: its switch, its time and where to open it."""

    top: int
    enabled: bool
    time: str  # 24-hour "HH:MM"
    switch: UiNode
    clock: UiNode  # the time text: inside the row, clear of the switch


def departure_rows(nodes: list[UiNode]) -> list[DepartureRow]:
    """The list's timer rows, top to bottom (the app's id order).

    A row is the clickable box around a switch. Its ``checked`` state is the
    timer's on/off and its time is the clock text inside it ("07:25", with an
    "AM"/"PM" beside it on a 12-hour phone). Rows without a time (charging
    locations) are skipped.
    """
    switches: dict[tuple[int, int, int, int], UiNode] = {}
    for node in nodes:
        if node.checkable and node.bounds is not None:
            switches.setdefault(node.bounds, node)
    rows: list[DepartureRow] = []
    for box, switch in switches.items():
        centre_y = (box[1] + box[3]) // 2
        row = min(
            (n for n in nodes if n.clickable and n.bounds is not None and not n.checkable
             and n.bounds[1] <= centre_y <= n.bounds[3] and n.bounds[0] <= box[0]
             and n.bounds[2] >= box[2]),
            key=lambda n: (n.bounds[3] - n.bounds[1]) if n.bounds else 0,
            default=None,
        )
        if row is None or row.bounds is None:
            continue
        inside = [n for n in nodes if n.text and _inside(n, row.bounds)]
        clock = next((n for n in inside if _TIME_RE.match(n.text.strip())), None)
        if clock is None or clock.bounds is None or clock.bounds[2] > box[0]:
            continue
        match = _TIME_RE.match(clock.text.strip())
        assert match is not None
        hour, minute = int(match.group(1)), int(match.group(2))
        meridiem = next(
            (m.group(1).lower() for n in inside if (m := _MERIDIEM_RE.match(n.text.strip()))),
            None,
        )
        if meridiem is not None:
            if not 1 <= hour <= 12:
                continue
            hour = hour % 12 + (12 if meridiem == "p" else 0)
        if hour > 23 or minute > 59:
            continue
        rows.append(DepartureRow(row.bounds[1], switch.checked, f"{hour:02d}:{minute:02d}", switch, clock))
    rows.sort(key=lambda r: r.top)
    return rows


@dataclass(frozen=True)
class Wheel:
    """One NumberPicker: its value and the Buttons that step it."""

    value: str
    previous: UiNode | None  # drawn above; a tap steps back
    following: UiNode | None  # drawn below; a tap steps forward
    left: int


def _wheels(nodes: list[UiNode], box: tuple[int, int, int, int]) -> list[Wheel]:
    wheels = []
    for picker in nodes:
        if not picker.clazz.endswith("NumberPicker") or picker.bounds is None or not _inside(picker, box):
            continue
        current = next(
            (n for n in nodes if _rid(n) == "numberpicker_input" and _inside(n, picker.bounds)), None,
        )
        if current is None or current.bounds is None:
            continue
        buttons = [
            n for n in nodes if n.clickable and n.bounds is not None and n is not current
            and _rid(n) != "numberpicker_input" and _inside(n, picker.bounds)
            and n.clazz.endswith("Button")
        ]
        above = next((b for b in buttons if b.bounds and b.bounds[3] <= current.bounds[1]), None)
        below = next((b for b in buttons if b.bounds and b.bounds[1] >= current.bounds[3]), None)
        wheels.append(Wheel(current.text.strip(), above, below, picker.bounds[0]))
    return sorted(wheels, key=lambda w: w.left)


@dataclass(frozen=True)
class TimerPage:
    """What the "Set time" page shows now, and the controls that change it."""

    hour: int  # 0-23
    minute: int
    weekdays: tuple[str, ...]
    repeat: bool
    hour_wheel: Wheel
    minute_wheel: Wheel
    meridiem_wheel: Wheel | None  # None on a 24-hour phone
    minute_step: int
    days: dict[str, UiNode]
    repeat_switch: UiNode
    top: int  # the page content's top; the toolbar is above it

    @property
    def time(self) -> str:
        return f"{self.hour:02d}:{self.minute:02d}"


def read_timer_page(nodes: list[UiNode]) -> TimerPage | None:
    """The timer page, or None when any part of it is not as captured."""
    by_rid: dict[str, UiNode] = {}
    for node in nodes:
        by_rid.setdefault(_rid(node), node)
    picker = next(
        (n for n in nodes if _rid(n) == "time_picker" and n.clazz.endswith("TimePicker")),
        by_rid.get("time_picker"),
    )
    repeat = by_rid.get("cta_repeat")
    days = {code: by_rid.get(rid) for code, rid in _DAY_IDS.items()}
    if picker is None or picker.bounds is None or repeat is None or not repeat.checkable:
        return None
    if any(n is None or n.tap_point is None for n in days.values()):
        return None
    wheels = _wheels(nodes, picker.bounds)
    numeric = [w for w in wheels if w.value.isdigit()]
    named = [w for w in wheels if not w.value.isdigit()]
    if len(numeric) != 2 or len(named) > 1:
        return None
    # The hour wheel is left of the ":" divider, the minutes right of it.
    divider = next((n for n in nodes if _rid(n) == "divider" and n.bounds and _inside(n, picker.bounds)), None)
    if divider is not None and divider.bounds is not None:
        hour_w = next((w for w in numeric if w.left < divider.bounds[0]), None)
        minute_w = next((w for w in numeric if w.left > divider.bounds[0]), None)
    else:
        hour_w, minute_w = numeric
    if hour_w is None or minute_w is None:
        return None
    hour, minute = int(hour_w.value), int(minute_w.value)
    meridiem = named[0] if named else None
    if meridiem is not None:
        # AM is the wheel's first value and PM its last, without wrapping, so
        # the side its other value is drawn on says which one is showing.
        if (meridiem.previous is None) == (meridiem.following is None) or not 1 <= hour <= 12:
            return None
        hour = hour % 12 + (12 if meridiem.following is None else 0)
    step = _minute_step(minute_w)
    if hour > 23 or minute > 59 or step is None:
        return None
    return TimerPage(
        hour=hour, minute=minute,
        weekdays=tuple(code for code in WEEKDAYS if days[code].selected),  # type: ignore[union-attr]
        repeat=repeat.checked,
        hour_wheel=hour_w, minute_wheel=minute_w, meridiem_wheel=meridiem,
        minute_step=step,
        days={code: node for code, node in days.items() if node is not None},
        repeat_switch=repeat,
        top=picker.bounds[1],
    )


def _minute_step(wheel: Wheel) -> int | None:
    """The minute wheel's step, from its neighbours (5 in the app)."""
    for other, sign in ((wheel.following, 1), (wheel.previous, -1)):
        if other is not None and other.text.strip().isdigit():
            step = (sign * (int(other.text.strip()) - int(wheel.value))) % 60
            if step and 60 % step == 0:
                return step
    return None


def page_fields(page: TimerPage, slot: int) -> dict[str, object]:
    """The page's days and Repeat as the slot's companion-only fields."""
    return {
        f"departure_timer_{slot}_weekdays": ",".join(page.weekdays),
        f"departure_timer_{slot}_repeat": page.repeat,
    }


def find_toolbar_text(nodes: list[UiNode], labels: set[str], page_top: int) -> UiNode | None:
    """A toolbar text item (Save, Cancel) above the page, by its label."""
    for node in nodes:
        if node.bounds is None or node.bounds[3] > page_top or not node.enabled:
            continue
        for text in (node.text, node.content_desc):
            if text and text.strip().casefold() in labels:
                return node
    return None
