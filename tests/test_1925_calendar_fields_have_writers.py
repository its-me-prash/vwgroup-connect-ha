# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#1925 — every service-calendar field must have a producer, or the event is
declared, read, and can never fire.

``main_inspection_due_at`` (HU / TÜV) was listed and read by the calendar but no
brand connector or portal parser ever set it, so the "Main inspection (HU / TÜV)"
entry was permanently absent — worse than missing, because the calendar lists the
category and a user reads "no inspection due" instead of "we never knew". This
guard asserts every calendar field is actually written somewhere, so a future
dead calendar field fails here instead of silently never firing.
"""
from __future__ import annotations

import pathlib
import re

from custom_components.vag_connect.calendar import _CHARGE_FIELDS, _SERVICE_FIELDS

_CARIAD = pathlib.Path(__file__).resolve().parents[1] / "custom_components/vag_connect/cariad"


def _cariad_source() -> str:
    return "\n".join(p.read_text(encoding="utf-8") for p in _CARIAD.rglob("*.py"))


def _has_writer(field: str, src: str) -> bool:
    # a direct assignment `d.<field> = ...` (not the `==` comparison)
    if re.search(rf"\.{re.escape(field)}\s*=(?!=)", src):
        return True
    # a dynamic setattr family, e.g. departure_timer_{i}_time
    if re.match(r"^departure_timer_\d+_time$", field) and re.search(
        r'setattr\(\s*d\s*,\s*f"departure_timer_\{i\}_time"', src
    ):
        return True
    return False


def test_every_calendar_field_has_a_writer() -> None:
    src = _cariad_source()
    missing = [f for f in (_SERVICE_FIELDS + _CHARGE_FIELDS) if not _has_writer(f, src)]
    assert not missing, f"calendar fields with no writer (dead events): {missing}"
