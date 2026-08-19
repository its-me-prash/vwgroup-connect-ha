# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#968 (Philip-Wiege) — the companion VW preset must accept the 4.3.2 app.

We Connect updated 4.2.1 → 4.3.2 and the single-value app-version quarantine then
disabled every nav-read ("app 4.3.2 > preset 4.2.1"). The quarantine now accepts a
SET of known-compatible versions (the Play "4.3.2" and the internal versionName
forms that ship the same accessibility tree), so 4.3.2 users get nav-reads back
while genuinely-unknown versions stay quarantined.
"""
from __future__ import annotations

from unittest.mock import MagicMock

from custom_components.vag_connect.companion.channel import CompanionChannel
from custom_components.vag_connect.companion.presets import PRESETS


def _vw_channel() -> CompanionChannel:
    return CompanionChannel(MagicMock(), PRESETS["volkswagen"], time_fn=lambda: 0.0)


def test_accepts_4_3_2_and_internal_version_strings() -> None:
    ch = _vw_channel()
    assert ch._decide_version_ok("4.3.2") is True
    assert ch._decide_version_ok("3.64.0") is True
    assert ch._decide_version_ok("3.63.2") is True
    assert ch._decide_version_ok("4.2.1") is True  # backward compatibility


def test_rejects_a_genuinely_unknown_version() -> None:
    ch = _vw_channel()
    assert ch._decide_version_ok("5.0.0") is False
    assert ch._decide_version_ok("1.0.0") is False
    assert ch._decide_version_ok(None) is False


def test_preset_lists_4_3_2_and_tile_is_resource_id_hardened() -> None:
    vw = PRESETS["volkswagen"]
    assert isinstance(vw.verified_app_version, tuple)
    assert "4.3.2" in vw.verified_app_version
    # #968 — the charge-detail nav tile now leads with the stable resource-id.
    assert vw.nav_reads[0].tile.resource_id == "rangeTile"


def test_read_only_brands_keep_single_or_none_version() -> None:
    """The unverified brands are unchanged (None) — the set is a VW widening."""
    for brand in ("audi", "skoda", "seat", "cupra"):
        assert PRESETS[brand].verified_app_version is None
