# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""2026-10-07 — app updates no longer switch the companion's taps off.

Every version list accepts its verified builds and anything newer; an unknown
older build, or a version that cannot be read, stays blocked.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from custom_components.vag_connect.companion.channel import CompanionChannel
from custom_components.vag_connect.companion.presets import PRESETS, app_version_covered


@pytest.mark.parametrize(
    ("live", "verified", "ok"),
    [
        ("4.3.2", ("4.3.2",), True),
        ("4.6.4", ("4.3.2",), True),
        ("10.0.0", ("4.3.2",), True),
        ("4.3.10", ("4.3.2",), True),
        ("4.3.1", ("4.3.2",), False),
        ("3.64.0", ("4.3.2", "3.64.0"), True),   # listed internal versionName
        ("3.65.0", ("4.3.2", "3.64.0"), False),  # unlisted, below the newest
        ("4.7.0-beta", ("4.3.2",), False),
        (None, ("4.3.2",), False),
        ("4.6.4", None, False),
        ("4.6.4", "4.3.2", True),
    ],
)
def test_app_version_covered(live, verified, ok) -> None:
    assert app_version_covered(live, verified) is ok


def test_writes_stay_enabled_on_a_newer_build() -> None:
    ch = CompanionChannel(MagicMock(), PRESETS["volkswagen"], time_fn=lambda: 0.0)
    ch._live_app_version = "4.6.4"
    ch._version_ok = ch._decide_version_ok("4.6.4")
    assert ch.writes_enabled is True
