# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#1229 (@Ra72xx) — VW-EU render images come from vw.de, not the walled BFF.

VW-EU cars are read over the EU Data Act portal + vw.de authproxy; the CARIAD-BFF
image endpoint is walled for them. The vw.de connector already had a complete
get_exterior_images() fetcher that was never called; it's now wired into
get_vehicle_data (setting image_urls on the supplementary channel). This pins the
merge step: the empty image_urls on the portal-primary is a gap the vw.de channel
fills, so the render URLs reach data["image_urls"] and become Image entities.
"""
from __future__ import annotations

from custom_components.vag_connect.cariad._channel_merge import merge_channels
from custom_components.vag_connect.cariad.models import VehicleData


class TestVwDeImagesReachTheMerge:
    def test_supplementary_images_fill_the_empty_primary(self) -> None:
        primary = VehicleData(vin="V1")            # portal read: image_urls == {}
        supp = VehicleData(vin="V1")               # vw.de read
        supp.image_urls = {
            "side_left": "https://vw.example/1.png",
            "back_center": "https://vw.example/2.png",
        }
        merged = merge_channels([
            ("eu_data_act", primary),
            ("website_authproxy", supp),
        ])
        assert merged.image_urls == {
            "side_left": "https://vw.example/1.png",
            "back_center": "https://vw.example/2.png",
        }
        assert merged.field_sources.get("image_urls") == "website_authproxy"

    def test_primary_images_are_not_overwritten(self) -> None:
        # If the primary already carries images, the supplementary must not clobber.
        primary = VehicleData(vin="V1")
        primary.image_urls = {"front": "https://primary/f.png"}
        supp = VehicleData(vin="V1")
        supp.image_urls = {"side": "https://supp/s.png"}
        merged = merge_channels([("bff", primary), ("website_authproxy", supp)])
        assert merged.image_urls == {"front": "https://primary/f.png"}
