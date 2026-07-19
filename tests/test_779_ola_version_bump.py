# Copyright 2026 Prash Balan (@its-me-prash) - Apache License 2.0
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#779 (rmalbrecht, Cupra Born) — OLA app-version header bump.

The OLA backend kept returning HTTP 403 on the older app-version header values.
Both brands are bumped to 2.19.1 (the current Play-Store myCUPRA/mySEAT version,
app-atlas-verified), and the previous primaries move into the fallback chain so
the multi-version retry layer has something to fall back to on the next bump.
These are behaviour tests over get_ola_headers so they pin position (primary vs
fallback), not just the presence of a version string in the source.
"""
from __future__ import annotations

from custom_components.vag_connect.cariad._ola_headers import (
    get_fallback_count,
    get_ola_headers,
)


def test_cupra_primary_is_current_version() -> None:
    assert get_ola_headers("cupra")["app-version"] == "2.19.1"


def test_seat_primary_is_current_version() -> None:
    assert get_ola_headers("seat")["app-version"] == "2.19.1"


def test_cupra_fallback_retains_previous_version() -> None:
    assert get_fallback_count("cupra") == 1
    assert get_ola_headers("cupra", fallback_index=0)["app-version"] == "2.15.0"


def test_seat_fallback_retains_previous_version() -> None:
    assert get_fallback_count("seat") == 1
    assert get_ola_headers("seat", fallback_index=0)["app-version"] == "2.17.0"


def test_brand_app_consistency_preserved() -> None:
    # the OLA backend enforces brand-app consistency — never claim the wrong
    # brand. Both the primary and the fallback must carry the right app-brand.
    for brand in ("seat", "cupra"):
        assert get_ola_headers(brand)["app-brand"] == brand
        assert get_ola_headers(brand, fallback_index=0)["app-brand"] == brand


def test_override_still_wins_over_bumped_primary() -> None:
    # the OptionsFlow power-user override must still take precedence.
    h = get_ola_headers("cupra", app_version_override="9.9.9")
    assert h["app-version"] == "9.9.9"
