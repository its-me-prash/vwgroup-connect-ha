# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#1154 (neuweddemer, Audi) — silence climatisation.auxiliaryHeatingStatus.requests.

The Scout kept re-flagging ``climatisation.auxiliaryHeatingStatus.requests`` (an
internal request-queue counter that arrives as an empty list). It slipped through
because ``_path_matches`` is exact / equal-length — not prefix — so the 2-seg
``auxiliaryHeatingStatus`` leaf and the 4-seg ``.value.*`` / ``.error.*`` globs
never covered the 3-seg ``.requests`` path (exactly the case the sibling
``climatisationTimers.climatisationTimersStatus.requests`` silencer already
handles for #801). Now silenced — so the maintainer reply ("noted so the Scout
stops flagging it") is actually true.
"""
from __future__ import annotations

from custom_components.vag_connect.cariad._unexpected_keys import detect_unexpected


def test_auxheating_requests_is_not_flagged() -> None:
    payload = {"climatisation": {"auxiliaryHeatingStatus": {"requests": []}}}
    flagged = [f.path for f in detect_unexpected("audi", "selectivestatus", payload)]
    assert flagged == [], f"expected .requests silenced, got {flagged}"


def test_a_genuinely_unknown_sibling_is_still_flagged() -> None:
    """The silence is targeted — an unrelated new child must still surface."""
    payload = {"climatisation": {"auxiliaryHeatingStatus": {"somethingBrandNew": 1}}}
    flagged = [f.path for f in detect_unexpected("audi", "selectivestatus", payload)]
    assert any("somethingBrandNew" in p for p in flagged)
