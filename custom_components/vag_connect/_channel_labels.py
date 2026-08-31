# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Layperson-friendly names for the read channels a car is fed over.

A car can be read over several channels at once (see ``cariad/_channel_merge``).
Internally each channel is a short token — ``eu_data_act``, ``website_authproxy``,
``mbb``, a brand slug like ``audi``. Those tokens are the right thing to store and
to key logic on, but they read like jargon in the UI. This module maps a token to
the same wording a user already saw when they set the login up, so the
``data_source_channel`` sensor and each entity's ``source`` attribute say
"Car-Net" and "vw.de website" instead of ``mbb`` and ``website_authproxy``.

Pure display helper: the raw tokens in ``source_channel`` / ``field_sources`` are
never changed, so all provenance logic and tests keep working on the tokens.
"""
from __future__ import annotations

from .const import BRANDS

# Channel tokens that are not brand slugs. Brand slugs (audi, volkswagen, …) fall
# through to BRANDS so the name matches the setup dialog exactly.
_CHANNEL_LABELS: dict[str, str] = {
    "eu_data_act": "EU Data Act portal",
    "website_authproxy": "vw.de website",
    "tibber": "Tibber",
    "mbb": "Car-Net",
    "companion_adb": "Companion app (ADB)",
    "companion_relay": "Companion app (relay)",
    "brand_native": "Brand app",
    "primary": "Main login",
}


def channel_display_name(token: str) -> str:
    """One channel token → its friendly name. Unknown tokens are returned as-is
    (never silently hidden), so a channel added later still shows *something*."""
    if not token:
        return token
    if token in _CHANNEL_LABELS:
        return _CHANNEL_LABELS[token]
    return BRANDS.get(token, token)


def channels_overview(raw: str | None) -> tuple[str | None, list[str]]:
    """A ``"+"``-joined ``source_channel`` string → ``(display, labels)``.

    Maps every contributing token to its friendly name and de-duplicates on the
    *mapped* name (so two tokens that share a label never show twice), preserving
    the deterministic order of the sorted raw join. Returns ``(None, [])`` for an
    empty / single-source-with-no-data value.
    """
    if not raw:
        return None, []
    labels: list[str] = []
    seen: set[str] = set()
    for token in raw.split("+"):
        label = channel_display_name(token)
        if label and label not in seen:
            seen.add(label)
            labels.append(label)
    if not labels:
        return None, []
    return " + ".join(labels), labels
