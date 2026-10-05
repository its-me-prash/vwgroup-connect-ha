# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The Volkswagen vehicle Settings "Synchronise now" button (app 4.3.2).

It sits under "Vehicle data" at the bottom of vehicle Settings, one swipe below
the fold, directly above "Delete vehicle" (``delete_cta``). It is found by its
own id, ``subtitle_cta``, and never by position or by text, so the translation
does not matter and the delete button can never be the match.

Tapping it asks the car for fresh data. On the live phone the button then turns
``enabled="false"`` and a "Synchronising with vehicle ..." snackbar shows; the
button stays disabled while the app waits for the car (a few minutes). The
disabled button is therefore both the proof that the tap was taken and the sign
that a sync is already running, in which case nothing is tapped.
"""
from __future__ import annotations

from .screen import UiNode

SYNC_BUTTON_ID = "subtitle_cta"


def find_sync_button(nodes: list[UiNode]) -> UiNode | None:
    """The "Synchronise now" node, enabled or not, or None if not on screen."""
    return next((
        n for n in nodes
        if n.resource_id.rsplit("/", 1)[-1] == SYNC_BUTTON_ID and n.bounds is not None
    ), None)
