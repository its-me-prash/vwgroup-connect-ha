# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Escalating EU-DA portal 5xx backoff (adopted from TommiG1: 5/15/30 min).

During a SUSTAINED VW-side portal outage the drop-anchored scheduler collapses to
``_DROP_RETRY_S`` (~60 s), so we hammered VW's portal every minute for hours. This
layers an escalating backoff on top: consecutive ``portal_error`` polls widen the
minimum sleep 5→15→30 min, and any healthy/empty/non-portal poll resets it.
"""
from __future__ import annotations

from custom_components.vag_connect.coordinator import (
    _PORTAL_5XX_BACKOFF_S,
    _portal_5xx_backoff_s,
    VagConnectCoordinator,
)


def test_backoff_curve() -> None:
    assert _portal_5xx_backoff_s(0) == 0.0        # no outage → no floor raised
    assert _portal_5xx_backoff_s(1) == 300.0      # 5 min
    assert _portal_5xx_backoff_s(2) == 900.0      # 15 min
    assert _portal_5xx_backoff_s(3) == 1800.0     # 30 min
    assert _portal_5xx_backoff_s(4) == 1800.0     # saturates
    assert _portal_5xx_backoff_s(99) == 1800.0
    assert _portal_5xx_backoff_s(-1) == 0.0       # defensive


def test_streak_increments_and_saturates_then_resets() -> None:
    c = VagConnectCoordinator.__new__(VagConnectCoordinator)
    c._consecutive_portal_5xx = 0
    # sustained outage → 1, 2, 3, then saturates at len(_PORTAL_5XX_BACKOFF_S)
    cap = len(_PORTAL_5XX_BACKOFF_S)
    for expected in (1, 2, 3, cap, cap):
        c._note_portal_outage(True)
        assert c._consecutive_portal_5xx == expected
    # a healthy (or empty / non-portal) poll resets the streak
    c._note_portal_outage(False)
    assert c._consecutive_portal_5xx == 0
    # the backoff floor tracks the streak
    c._note_portal_outage(True)
    assert _portal_5xx_backoff_s(c._consecutive_portal_5xx) == 300.0


def test_streak_survives_uninitialised_instance() -> None:
    # __new__ without __init__ (the MagicMock test pattern) must not crash.
    c = VagConnectCoordinator.__new__(VagConnectCoordinator)
    c._note_portal_outage(True)
    assert c._consecutive_portal_5xx == 1
    c._note_portal_outage(False)
    assert c._consecutive_portal_5xx == 0
