# Copyright 2026 Prash Balan (@its-me-prash) — Apache License 2.0
# SPDX-License-Identifier: Apache-2.0
"""System Health for VAG Connect.

Surfaces integration-wide diagnostics in HA's Settings → System → Repairs
panel under "System Health". Visible at-a-glance:
- Integration version
- Configured brands + entry count
- Last successful poll per entry
- API quota remaining (if backend exposed)
- Push channel status (Skoda MQTT / FCM)

v2.0.0 (Big-Bang) — parity with upstream v2.0.1-beta.8.
Drop-in handler registered automatically by HA when this module exists.
"""
from __future__ import annotations

from typing import Any

from homeassistant.components import system_health
from homeassistant.core import HomeAssistant, callback

from .const import DOMAIN


@callback
def async_register(
    hass: HomeAssistant, register: system_health.SystemHealthRegistration
) -> None:
    """Register the system_health callback (HA-invoked at startup)."""
    register.async_register_info(_system_health_info)


async def _system_health_info(hass: HomeAssistant) -> dict[str, Any]:
    """Return key system-health metrics for the Repairs UI panel."""
    info: dict[str, Any] = {}

    entries = hass.config_entries.async_entries(DOMAIN)
    info["configured_entries"] = len(entries)

    if not entries:
        return info

    # Integration version from manifest
    try:
        integration = await hass.helpers.aiohttp_client.async_get_loaded_integration(  # type: ignore[attr-defined]
            DOMAIN
        )
        info["version"] = integration.version
    except Exception:  # noqa: BLE001
        # Fallback — read manifest directly
        try:
            from homeassistant.loader import async_get_integration  # noqa: PLC0415
            integration = await async_get_integration(hass, DOMAIN)
            info["version"] = integration.version
        except Exception:  # noqa: BLE001
            info["version"] = "unknown"

    # Per-entry brand + last poll + quota + push status
    brands: list[str] = []
    last_polls: list[str] = []
    quotas: list[str] = []
    push_states: list[str] = []

    for entry in entries:
        coord = entry.runtime_data if hasattr(entry, "runtime_data") else None
        if coord is None:
            continue

        brand = entry.data.get("brand", "?")
        brands.append(brand)

        last_poll = getattr(coord, "_last_successful_poll_at", None)
        if last_poll is not None:
            last_polls.append(f"{brand}: {last_poll.isoformat(timespec='seconds')}")

        # Aggregate quota across vehicles
        for vin, vehicle in getattr(coord, "vehicles", {}).items():
            remaining = vehicle.get("requests_remaining_today")
            if remaining is not None:
                quotas.append(f"{brand}/{vin[-4:]}: {remaining}")

        # Push manager state (if any of the 3 wired)
        for attr_name in ("_skoda_push", "_cupra_seat_push", "_audi_vw_push"):
            mgr = getattr(coord, attr_name, None)
            if mgr is not None:
                state = getattr(mgr, "state", "unknown")
                push_states.append(f"{attr_name.lstrip('_')}: {state}")

    if brands:
        info["brands"] = ", ".join(sorted(set(brands)))
    if last_polls:
        info["last_polls"] = " | ".join(last_polls)
    if quotas:
        info["quota_remaining"] = " | ".join(quotas)
    if push_states:
        info["push_channels"] = " | ".join(push_states)

    # Reachability ping to the most-used backend (cariad bff)
    info["cariad_bff_reachable"] = system_health.async_check_can_reach_url(
        hass, "https://emea.bff.cariad.digital/login/v1/idk/openid-configuration"
    )

    return info
