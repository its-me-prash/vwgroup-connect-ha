# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Friendly channel-name mapping for the data-source provenance UI.

The raw ``source_channel`` / ``field_sources`` tokens stay jargon internally;
these helpers turn them into the wording a user saw at setup, and de-duplicate
so a combined car never shows the same source twice.
"""
from __future__ import annotations

from custom_components.vag_connect._channel_labels import (
    channel_display_name,
    channels_overview,
)
from custom_components.vag_connect.const import BRANDS


class TestDisplayName:
    def test_channel_tokens_are_friendly(self) -> None:
        assert channel_display_name("eu_data_act") == "EU Data Act portal"
        assert channel_display_name("website_authproxy") == "vw.de website"
        assert channel_display_name("mbb") == "Car-Net"

    def test_brand_tokens_reuse_setup_labels(self) -> None:
        # a brand slug shows exactly the name from the setup dialog
        assert channel_display_name("audi") == BRANDS["audi"]
        assert channel_display_name("skoda") == BRANDS["skoda"]

    def test_unknown_token_is_returned_as_is(self) -> None:
        # a channel added later must still show *something*, never vanish
        assert channel_display_name("some_new_channel") == "some_new_channel"

    def test_empty_is_safe(self) -> None:
        assert channel_display_name("") == ""


class TestOverview:
    def test_multi_channel_join_is_friendly(self) -> None:
        display, labels = channels_overview("eu_data_act+mbb")
        assert display == "EU Data Act portal + Car-Net"
        assert labels == ["EU Data Act portal", "Car-Net"]

    def test_dedup_on_mapped_label(self) -> None:
        # two tokens that map to the same friendly label collapse to one entry
        display, labels = channels_overview("companion_adb+companion_adb")
        assert labels == ["Companion app (ADB)"]
        assert display == "Companion app (ADB)"

    def test_single_channel(self) -> None:
        assert channels_overview("audi") == (BRANDS["audi"], [BRANDS["audi"]])

    def test_empty_and_none(self) -> None:
        assert channels_overview(None) == (None, [])
        assert channels_overview("") == (None, [])

    def test_order_follows_sorted_raw_join(self) -> None:
        # merge_channels emits a sorted token join; the display preserves it
        display, _ = channels_overview("audi+eu_data_act+website_authproxy")
        assert display == f"{BRANDS['audi']} + EU Data Act portal + vw.de website"
