# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#2256 — the hero image (map marker, shared ``image_url``) is never an
interior view while another view is there.

On a Škoda Octavia the composite renders came in the order interior side,
exterior side, ...; "first key with 'side'" picked ``interior_side`` and the
map showed the rear seats. A Karoq in the same installation listed the
exterior first and was fine.
"""
from __future__ import annotations

from custom_components.vag_connect.cariad.api.graphql import VehicleImageFetcher

_I_SIDE = "https://example.invalid/studiovint_side1080.png"
_E_SIDE = "https://example.invalid/dayvext_side1080.png"


def _octavia() -> dict[str, str]:
    # interior views first, as the reporter's car listed them
    return {
        "interior_side": _I_SIDE,
        "interior_front": "https://example.invalid/studiovint_front1080.png",
        "interior_boot": "https://example.invalid/studiovint_boot1080.png",
        "exterior_front": "https://example.invalid/dayvext_front1080.png",
        "exterior_side": _E_SIDE,
        "exterior_rear": "https://example.invalid/dayvext_rear1080.png",
    }


def test_the_exterior_side_wins_over_an_interior_side_listed_first() -> None:
    assert VehicleImageFetcher.primary_url(_octavia()) == _E_SIDE
    assert VehicleImageFetcher.best_url(_octavia()) == _E_SIDE


def test_an_exterior_front_wins_over_an_interior_side() -> None:
    urls = {"interior_side": _I_SIDE, "exterior_front": "F"}
    assert VehicleImageFetcher.primary_url(urls) == "F"


def test_a_curated_media_id_wins_over_an_interior_side() -> None:
    urls = {"interior_side": _I_SIDE, "MYAPN8NB": "M"}
    assert VehicleImageFetcher.primary_url(urls) == "M"


def test_any_outside_view_wins_over_an_interior_side() -> None:
    urls = {"interior_side": _I_SIDE, "exterior_rear": "R"}
    assert VehicleImageFetcher.primary_url(urls) == "R"


def test_only_interior_views_still_give_a_picture() -> None:
    urls = {"interior_boot": "B", "interior_side": _I_SIDE}
    assert VehicleImageFetcher.primary_url(urls) == _I_SIDE


def test_the_vwde_view_keys_are_unchanged() -> None:
    urls = {"front_left": "F", "side_left": "S"}
    assert VehicleImageFetcher.primary_url(urls) == "S"


def test_an_exterior_first_order_is_unchanged() -> None:
    urls = {"exterior_side": _E_SIDE, "interior_side": _I_SIDE}
    assert VehicleImageFetcher.primary_url(urls) == _E_SIDE
