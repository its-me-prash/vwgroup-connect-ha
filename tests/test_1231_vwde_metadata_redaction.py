# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""D#1231 — the volkswagen.de profile block (number plate, owner nickname, render
image URLs) is personal and must be redacted in a diagnostics download, like the
VIN and address already are. A tester had to hand-mask these before attaching the
file. Empty ones stay visibly empty so "no data" never looks like "hidden".
"""
from __future__ import annotations

from custom_components.vag_connect.diagnostics import _scrub


def test_vwde_profile_metadata_is_redacted():
    scrubbed = _scrub(
        {
            "license_plate": "M-AB 1234",
            "vehicle_nickname": "Graue Ratte",
            "image_urls": {"back_left": "https://media.volkswagen.com/Vilma/x.png"},
            "battery_soc": 53,  # genuine telemetry — must NOT be touched
        },
        gps_round=False,
    )
    assert scrubbed["license_plate"] == "**REDACTED**"
    assert scrubbed["vehicle_nickname"] == "**REDACTED**"
    assert scrubbed["image_urls"] == "**REDACTED**"
    assert scrubbed["battery_soc"] == 53


def test_empty_vwde_metadata_stays_visibly_empty():
    scrubbed = _scrub(
        {"license_plate": "", "vehicle_nickname": None, "image_urls": {}},
        gps_round=False,
    )
    assert scrubbed["license_plate"] == ""
    assert scrubbed["vehicle_nickname"] is None
    assert scrubbed["image_urls"] == {}
