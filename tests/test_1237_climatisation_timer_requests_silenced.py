# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#1237 (@arcticMariner, Audi) — silence automation.climatisationTimer.requests.

The Scout kept re-flagging the SINGULAR-"Timer" Audi variant
``automation.climatisationTimer.requests`` — an internal request-queue counter
whose value is ALREADY consumed into ``climatisation_timers_pending`` (vw_eu.py).
It slipped through because ``_path_matches`` is exact / equal-length, so the
2-seg ``climatisationTimers.*`` wildcard never covered this 3-seg ``automation.``
path — exactly the case the sibling ``automation.chargingProfiles.requests``
silencer already handles for #799. Now silenced, so a maintainer "noted, it's
already parsed" reply is actually true.
"""
from __future__ import annotations

from custom_components.vag_connect.cariad._unexpected_keys import detect_unexpected


def test_climatisation_timer_requests_is_not_flagged() -> None:
    payload = {"automation": {"climatisationTimer": {"requests": []}}}
    flagged = [f.path for f in detect_unexpected("audi", "selectivestatus", payload)]
    assert flagged == [], f"expected .requests silenced, got {flagged}"


def test_a_genuinely_unknown_sibling_is_still_flagged() -> None:
    """The silence is targeted — an unrelated new child must still surface."""
    payload = {"automation": {"climatisationTimer": {"somethingBrandNew": 1}}}
    flagged = [f.path for f in detect_unexpected("audi", "selectivestatus", payload)]
    assert any("somethingBrandNew" in p for p in flagged)
