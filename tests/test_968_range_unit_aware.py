# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#968 — the companion range read must be unit-aware (miles -> km).

The We Connect app narrates the range unit in words. A Mk8 Golf on imperial units
reads "14 miles"; a metric car reads "253 Kilometer". The old parser matched only
"km"/"Kilometer" and pulled the bare integer, so an imperial car either read
nothing or would have stored 14 and mislabelled it km. The selector now captures
the number AND the unit, and ``range_km`` converts miles to km. (kgroshert/plainmad.)
"""
from __future__ import annotations

import re

from custom_components.vag_connect.companion.presets import PRESETS, coerce


def test_range_km_keeps_metric() -> None:
    assert coerce("range_km", "253 Kilometer") == 253
    assert coerce("range_km", "253 km") == 253


def test_range_km_converts_imperial() -> None:
    assert coerce("range_km", "14 miles") == round(14 * 1.60934)  # 23
    assert coerce("range_km", "14 mi") == 23
    assert coerce("range_km", "1 mile") == 2


def test_range_km_rejects_junk() -> None:
    assert coerce("range_km", "n/a") is None
    assert coerce("range_km", "") is None


def _vw_range_selector():
    fields = PRESETS["volkswagen"].fields
    return next(f for f in fields if f.target == "electric_range_km")


def test_vw_range_selector_captures_number_and_unit() -> None:
    sel = _vw_range_selector()
    assert sel.parse == "range_km"
    rx = re.compile(sel.content_desc_re, re.I)
    # metric narration
    m = rx.search("Battery range 253 Kilometer")
    assert m and m.group(1).strip() == "253 Kilometer"
    # imperial narration — the whole miles value is captured so coerce converts
    m = rx.search("Battery range 14 miles")
    assert m and m.group(1).strip() == "14 miles"
    assert coerce("range_km", m.group(1)) == 23
