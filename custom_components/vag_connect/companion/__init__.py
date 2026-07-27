# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Companion-phone (ADB) channel — v3.0.0-alpha, EXPERIMENTAL.

An optional fourth source, picked in the hub menu at the start of setup. It
drives the official manufacturer Android app on a spare, signed-in phone over
ADB and reads the displayed values off the screen. Because it is the real app
on a real device, it needs no separate login, stores no credentials, and is a
last-resort two-way path on cars where every network channel is read-only.

Design notes and honesty markers live in the individual modules. The short
version:

- We do NOT root the phone, read its stored tokens, or intercept traffic. The
  whole contract is: screen in (uiautomator dump), taps out (input tap).
- Values are matched from the accessibility tree by resource-id and
  content-description where the app exposes them, falling back to localized
  visible labels. That label fallback is why the app language has to be German
  or English for now, exactly like the prior-art projects in this space.
- Volkswagen is the only brand we can test in-house (a Golf GTE). Audi, Škoda,
  SEAT and CUPRA ship as ``verified=False`` presets: the structure is there,
  but the field selectors are best-effort until a real uiautomator dump from
  that brand's app confirms them. An unverified preset reads what it can and
  refuses writes, rather than guessing a tap onto the wrong button.
"""
from __future__ import annotations

from .channel import CompanionChannel
from .client import CompanionClient
from .presets import PRESETS, BrandPreset, FieldSelector

__all__ = [
    "CompanionChannel",
    "CompanionClient",
    "PRESETS",
    "BrandPreset",
    "FieldSelector",
]
