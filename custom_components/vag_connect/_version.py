# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The manifest version, for reports that are read on a build we cannot see.

#1736/#1738 — a Scout report, an error report or a Porsche login report is
read by us days later, on an installation we have no view of, so the report
has to name the version it came from. Three issues in one week opened with us
asking the reporter which build they were on.

Lives in its own module because two callers need it (the coordinator's two
reporter pipelines and the config flow's Porsche report link) and because the
trap below is worth documenting exactly once.
"""
from __future__ import annotations

from typing import Any

from .const import DOMAIN


def integration_version(hass: Any) -> str:
    """The manifest version, or ``""`` — never raises.

    Deliberately NOT the awaitable ``async_get_integration``: handed a test's
    mocked hass that one goes looking for the integration on disk and does not
    come back, and a cosmetic header field has no business being able to hang
    setup. ``async_get_loaded_integration`` is a @callback — one dict lookup,
    no import, no executor, no I/O — and raises ``IntegrationNotLoaded`` when
    it is not there, which is a perfectly good answer here.
    """
    try:
        from homeassistant.loader import (  # noqa: PLC0415
            async_get_loaded_integration,
        )

        integration = async_get_loaded_integration(hass, DOMAIN)
        return str(integration.version or "")
    except Exception:  # noqa: BLE001
        return ""
