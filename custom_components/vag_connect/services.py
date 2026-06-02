# Copyright 2026 Prash Balan (@its-me-prash) — Apache License 2.0
# SPDX-License-Identifier: Apache-2.0
"""v2.8.0 quick-win B — `vag_connect.open_app` service.

Opens the brand's native mobile app via a deeplink scheme on the
calling device. The integration itself cannot open URLs on a phone —
that must happen on the dashboard side — so this service simply emits
a `vag_connect_open_app` event on the HA event bus with the payload
the dashboard card needs:

    {
        "vin":          str,   # vehicle identifier
        "brand":        str,   # brand key (audi, volkswagen, skoda, ...)
        "deeplink_url": str,   # full deeplink including action path
        "action":       str,   # one of OPEN_APP_ACTIONS
    }

A small Lovelace card subscribes to the event and routes the user to
``window.location.href = deeplink_url`` on iOS / Android. The event
is broadcast so multiple dashboards can subscribe independently.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import voluptuous as vol

from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv

from .const import CONF_BRAND, DEEPLINK_SCHEMES, DOMAIN

if TYPE_CHECKING:
    from .coordinator import VagConnectCoordinator

_LOGGER = logging.getLogger(__name__)

SERVICE_OPEN_APP = "open_app"
EVENT_OPEN_APP = "vag_connect_open_app"

OPEN_APP_ACTIONS: list[str] = [
    "open",
    "lock",
    "unlock",
    "climate_on",
    "climate_off",
    "charging",
]

OPEN_APP_SCHEMA = vol.Schema(
    {
        vol.Required("vin"): cv.string,
        vol.Optional("action", default="open"): vol.In(OPEN_APP_ACTIONS),
    }
)


def _build_deeplink_url(brand: str, action: str) -> str:
    """Compose the full deeplink URL for the given brand + action.

    The brand-scheme value from ``DEEPLINK_SCHEMES`` is a base URL
    ending in ``://``. The action is appended as a path segment for
    every action except the default ``open`` (which just opens the
    app to its home screen). Each brand's app router may interpret
    the action path differently — the v2.8.0 contract is "best effort
    on the action, always succeed on opening the app".
    """
    base = DEEPLINK_SCHEMES.get(brand, "")
    if not base:
        return ""
    if action == "open":
        return base
    return f"{base}{action}"


def _get_coordinator_for_vin(
    hass: HomeAssistant, vin: str
) -> VagConnectCoordinator | None:
    """Return the coordinator that owns *vin* across all config entries.

    Kept private to this module to avoid a circular import with
    ``__init__.py`` which owns the canonical ``_get_coordinator``.
    Behaviour is identical: scan all loaded entries, return the
    coordinator whose ``vehicles`` dict contains the VIN.
    """
    for entry in hass.config_entries.async_entries(DOMAIN):
        coordinator: VagConnectCoordinator | None = getattr(
            entry, "runtime_data", None
        )
        if coordinator is None:
            continue
        if vin in coordinator.vehicles:
            return coordinator
    return None


def async_register_open_app_service(hass: HomeAssistant) -> None:
    """Register the ``vag_connect.open_app`` service on the bus.

    Called from ``async_setup_entry`` after the existing service
    registration block. Idempotent: re-registering the same service
    name is a no-op in HA core.
    """

    async def _handle_open_app(call: ServiceCall) -> None:
        vin: str = call.data["vin"]
        action: str = call.data.get("action", "open")

        coordinator = _get_coordinator_for_vin(hass, vin)
        if coordinator is None:
            raise ServiceValidationError(
                f"Vehicle '{vin}' not found.",
                translation_domain=DOMAIN,
                translation_key="vehicle_not_found",
            )

        brand: str = str(coordinator.entry.data.get(CONF_BRAND, "")).strip()
        deeplink_url = _build_deeplink_url(brand, action)

        if not deeplink_url:
            _LOGGER.warning(
                "vag_connect.open_app: no deeplink scheme known for brand "
                "%r (vin=...%s) — emitting event with empty URL so the "
                "dashboard card can surface the gap to the user",
                brand,
                vin[-4:] if len(vin) >= 4 else vin,
            )

        payload = {
            "vin": vin,
            "brand": brand,
            "deeplink_url": deeplink_url,
            "action": action,
        }
        _LOGGER.debug(
            "vag_connect.open_app: firing %s event for brand=%s action=%s",
            EVENT_OPEN_APP,
            brand,
            action,
        )
        hass.bus.async_fire(EVENT_OPEN_APP, payload)

    hass.services.async_register(
        DOMAIN, SERVICE_OPEN_APP, _handle_open_app, schema=OPEN_APP_SCHEMA
    )
