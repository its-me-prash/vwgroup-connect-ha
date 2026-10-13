# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The Volkswagen overview's "Synchronised … ago" line, as an age (app 4.3.2).

The vehicle toolbar's accessibility text ends with how old the app's data from
the car is, e.g. "Your vehicle: Tiguan. Synchronised 32 minutes ago". The app
builds it from its own translation tables, so it is parsed from the same tables
read off the phone, in whatever language the app runs. The 4.3.2 formatter
(``provideVehicleToolbarViewModel``) picks the wording by age:

- under a minute: "Synchronised just now";
- under an hour: N minutes;
- under a day: N hours, plus M minutes when M > 0 (so still minute precision);
- up to four calendar days: N days, plus M hours when M > 0 (hour precision);
- up to six days: N days (day precision);
- older: a date, then "Data no longer up-to-date" — not read: a car that old
  is already flagged stale by its last readable age.

Every count is rounded down, so the real age lies in ``[age, age + precision)``.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from .resources import SYNC_JUST_NOW, SYNC_LAST_UPDATE, SYNC_PLURALS, StringResources
from .screen import UiNode

_MINUTE, _HOUR, _DAY = 60, 3600, 86400
_UNIT_SECONDS = dict(zip(SYNC_PLURALS, (_MINUTE, _HOUR, _DAY)))
# A plural form with no number in it ("One minute") stands for its quantity.
_QUANTITY_VALUE = {"zero": 0, "one": 1, "two": 2}
_PLACEHOLDER = re.compile(r"%(?:\d+\$)?[sd]")

# The English 4.3.2 table, for a transport that cannot read the app's own
# tables (the agent relay has no shell).
ENGLISH_432: StringResources = {
    SYNC_LAST_UPDATE: {"Synchronised %s ago"},
    SYNC_JUST_NOW: {"Synchronised just now"},
    "duration_minutes_long_pluralised#one": {"One minute"},
    "duration_minutes_long_pluralised#other": {"%s minutes"},
    "duration_hours_long_pluralised#one": {"One hour"},
    "duration_hours_long_pluralised#other": {"%s hours"},
    "duration_days_long_pluralised#one": {"One day"},
    "duration_days_long_pluralised#other": {"%s days"},
}


@dataclass(frozen=True)
class SyncAge:
    """How old the app says its data is, and how coarsely it says it."""

    age_s: int
    precision_s: int


def _template(text: str, fill: str) -> str:
    """A translated template as a regex, its placeholder replaced by ``fill``."""
    parts = _PLACEHOLDER.split(text)
    return fill.join(re.escape(part) for part in parts)


def _unit_forms(strings: StringResources) -> list[tuple[str, int, int | None]]:
    """(regex, unit seconds, fixed count or None) for every duration form."""
    forms: list[tuple[str, int, int | None]] = []
    for key, texts in strings.items():
        name, _, quantity = key.partition("#")
        unit = _UNIT_SECONDS.get(name)
        if unit is None or not quantity:
            continue
        for text in texts:
            if _PLACEHOLDER.search(text):
                forms.append((_template(text, r"(\d+)"), unit, None))
            elif quantity in _QUANTITY_VALUE:
                forms.append((re.escape(text), unit, _QUANTITY_VALUE[quantity]))
    # Longest first, so "%s minutes" never loses to a shorter look-alike.
    return sorted(forms, key=lambda f: -len(f[0]))


def _precision(parts: list[tuple[int, int]]) -> int:
    """The bracket is set by the largest unit shown, as in the formatter."""
    if max(unit for _count, unit in parts) < _DAY:
        return _MINUTE  # under a day, minutes are shown whenever not zero
    days = sum(count for count, unit in parts if unit == _DAY)
    return _HOUR if days <= 4 else _DAY


def parse_sync_line(text: str, strings: StringResources) -> SyncAge | None:
    """The age in one accessibility text, or None if it has no sync line."""
    for just_now in strings.get(SYNC_JUST_NOW, ()):
        if just_now and just_now in text:
            return SyncAge(0, _MINUTE)
    forms = _unit_forms(strings)
    if not forms:
        return None
    one = "|".join(f"(?:{regex})" for regex, _unit, _fixed in forms)
    duration = rf"(?:{one})(?:\s+(?:{one}))?"
    token = re.compile("|".join(f"(?P<f{i}>{regex})" for i, (regex, _u, _f) in enumerate(forms)))
    for frame in strings.get(SYNC_LAST_UPDATE, ()):
        if not _PLACEHOLDER.search(frame):
            continue
        match = re.search(_template(frame, f"(?P<d>{duration})"), text)
        if match is None:
            continue
        parts: list[tuple[int, int]] = []
        for hit in token.finditer(match.group("d")):
            index = int(next(k for k, v in hit.groupdict().items() if v is not None)[1:])
            _regex, unit, fixed = forms[index]
            digits = re.search(r"\d+", hit.group(0))
            count = fixed if fixed is not None else int(digits.group(0)) if digits else None
            if count is None:
                break
            parts.append((count, unit))
        else:
            if parts:
                return SyncAge(sum(c * u for c, u in parts), _precision(parts))
    return None


def find_sync_line(nodes: list[UiNode], strings: StringResources) -> SyncAge | None:
    """The overview's sync age, from the first node that carries one."""
    table = strings if SYNC_LAST_UPDATE in strings else ENGLISH_432
    for node in nodes:
        for text in (node.content_desc, node.text):
            if text:
                age = parse_sync_line(text, table)
                if age is not None:
                    return age
    return None
