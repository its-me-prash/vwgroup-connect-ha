# Copyright 2026 Prash Balan (@its-me-prash) - Apache License 2.0
# SPDX-License-Identifier: Apache-2.0
"""v2.10.0 - tests for the unified ``vag_connect.execute_vehicle_action`` service.

Coverage:

1. ``EXECUTE_VEHICLE_ACTION_MAP`` has the expected 14 action keys and
   every key maps to a method that exists on ``VagConnectCoordinator``.
2. The service is registered on ``hass.services`` after
   ``_register_services`` runs.
3. The handler resolves ``device_id`` to the matching VIN via the
   device registry, then dispatches to the mapped coordinator method
   with that VIN.
4. An unknown ``action`` value bypasses the schema (which is defended
   in depth) and raises ``HomeAssistantError``.
5. An unknown ``device_id`` raises ``ServiceValidationError``.

The ``custom_components.vag_connect`` package imports Home Assistant at
top level so every test in this file is tagged ``ha_required`` and
auto-skips when HA is not installed (see ``tests/conftest.py``).
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.vag_connect.const import DOMAIN

pytestmark = pytest.mark.ha_required


# ---------------------------------------------------------------------------
# Action-map coverage
# ---------------------------------------------------------------------------


class TestExecuteVehicleActionMap:
    """``EXECUTE_VEHICLE_ACTION_MAP`` is the contract between the
    services.yaml dropdown and the coordinator methods.

    We pin both the expected keys (so removing one is a deliberate
    diff) and the existence of the matching coordinator method (so a
    coordinator-method rename breaks loudly here instead of silently
    in production).
    """

    EXPECTED_KEYS = {
        "lock",
        "unlock",
        "start_climatisation",
        "stop_climatisation",
        "start_charging",
        "stop_charging",
        "flash_lights",
        "start_window_heating",
        "stop_window_heating",
        "wake_vehicle",
        "start_aux_heating",
        "stop_aux_heating",
        "start_ventilation",
        "stop_ventilation",
    }

    def test_map_has_expected_keys(self) -> None:
        from custom_components.vag_connect import EXECUTE_VEHICLE_ACTION_MAP

        assert set(EXECUTE_VEHICLE_ACTION_MAP.keys()) == self.EXPECTED_KEYS

    def test_every_action_has_matching_coordinator_method(self) -> None:
        from custom_components.vag_connect import EXECUTE_VEHICLE_ACTION_MAP
        from custom_components.vag_connect.coordinator import VagConnectCoordinator

        missing = [
            (action, method_name)
            for action, method_name in EXECUTE_VEHICLE_ACTION_MAP.items()
            if not hasattr(VagConnectCoordinator, method_name)
        ]
        assert missing == [], (
            f"actions without a matching coordinator method: {missing}"
        )

    def test_yaml_dropdown_options_match_action_map(self) -> None:
        """services.yaml dropdown options must match the dispatch map.

        Drift between the two would let a user pick an action in the UI
        that the dispatcher does not know about (HomeAssistantError at
        call-time) - that defeats the dropdown's point.
        """
        from pathlib import Path

        import yaml

        from custom_components.vag_connect import EXECUTE_VEHICLE_ACTION_MAP

        yaml_path = (
            Path(__file__).resolve().parent.parent
            / "custom_components"
            / "vag_connect"
            / "services.yaml"
        )
        parsed = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
        dropdown_options = (
            parsed["execute_vehicle_action"]["fields"]["action"]["selector"][
                "select"
            ]["options"]
        )
        assert set(dropdown_options) == set(EXECUTE_VEHICLE_ACTION_MAP.keys())


# ---------------------------------------------------------------------------
# Service-registration + dispatch coverage
# ---------------------------------------------------------------------------


def _make_hass_with_device(
    vin: str, device_id: str = "dev-1"
) -> tuple[MagicMock, MagicMock, MagicMock]:
    """Synthesise a minimal hass + coordinator + device-registry triple.

    The handler scans ``hass.config_entries.async_entries(DOMAIN)`` to
    find a coordinator that owns the resolved VIN, and uses
    ``device_registry.async_get(device_id)`` to map the device back to
    the VIN. We wire both so the handler can dispatch end-to-end
    without a live config-flow.
    """
    coordinator = MagicMock()
    coordinator.vehicles = {vin: {"vin": vin}}
    coordinator.is_read_only = MagicMock(return_value=False)
    # Coordinator action methods are async; AsyncMock so ``await`` works.
    for method_name in (
        "async_lock",
        "async_unlock",
        "async_start_climatisation",
        "async_stop_climatisation",
        "async_start_charging",
        "async_stop_charging",
        "async_flash_lights",
        "async_start_window_heating",
        "async_stop_window_heating",
        "async_wake_vehicle",
        "async_start_aux_heating",
        "async_stop_aux_heating",
        "async_start_ventilation",
        "async_stop_ventilation",
    ):
        setattr(coordinator, method_name, AsyncMock())

    entry = MagicMock()
    entry.runtime_data = coordinator
    entry.data = {"brand": "audi"}

    device = MagicMock()
    device.identifiers = {(DOMAIN, vin)}

    device_registry = MagicMock()
    device_registry.async_get = MagicMock(return_value=device)

    hass = MagicMock()
    hass.config_entries.async_entries.return_value = [entry]
    hass.services.has_service = MagicMock(return_value=False)

    # Capture the registered handlers so the test can invoke
    # execute_vehicle_action directly without a live HA loop.
    registered: dict[str, Any] = {}

    def _capture(_domain: str, name: str, handler: Any, *_a: Any, **_kw: Any) -> None:
        registered[name] = handler

    hass.services.async_register.side_effect = _capture
    hass._registered_services = registered  # type: ignore[attr-defined]
    hass._device_registry = device_registry  # type: ignore[attr-defined]

    return hass, coordinator, device_registry


def _register_services_with_patched_dr(hass: MagicMock) -> None:
    """Run ``_register_services`` with ``dr.async_get`` patched to
    return our synthesised registry.

    The internal helper imports ``device_registry as dr`` at module
    top level. We monkey-patch ``dr.async_get`` and intentionally do
    NOT restore it within this helper, because the registered service
    handlers capture the patched ``dr`` reference and are invoked
    LATER (after this function returns) by the test body. Restoring
    too early would make the handler see the real HA dr.async_get and
    crash on the MagicMock'd hass. Pytest's test isolation cleans up
    any module-level side effects between tests anyway.
    """
    from custom_components.vag_connect import _register_services
    from custom_components.vag_connect import dr as _dr_mod  # type: ignore[attr-defined]

    _dr_mod.async_get = MagicMock(return_value=hass._device_registry)  # type: ignore[attr-defined]
    _register_services(hass)


def test_execute_vehicle_action_is_registered() -> None:
    """After ``_register_services`` the service appears on the bus."""
    vin = "WVWZZZ123456"
    hass, _coord, _dr = _make_hass_with_device(vin)

    _register_services_with_patched_dr(hass)

    assert "execute_vehicle_action" in hass._registered_services  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_execute_vehicle_action_dispatches_lock_to_coordinator() -> None:
    """Happy path: device_id resolves to VIN, coordinator method runs."""
    vin = "WVWZZZ123456"
    hass, coord, _dr = _make_hass_with_device(vin)

    _register_services_with_patched_dr(hass)
    handler = hass._registered_services["execute_vehicle_action"]  # type: ignore[attr-defined]

    call = MagicMock()
    call.data = {"device_id": "dev-1", "action": "lock"}
    await handler(call)

    coord.async_lock.assert_awaited_once_with(vin)


@pytest.mark.asyncio
async def test_execute_vehicle_action_dispatches_start_ventilation() -> None:
    """Smoke-test a non-lock action so we know the dispatch is generic."""
    vin = "WSKODATEST00001"
    hass, coord, _dr = _make_hass_with_device(vin)

    _register_services_with_patched_dr(hass)
    handler = hass._registered_services["execute_vehicle_action"]  # type: ignore[attr-defined]

    call = MagicMock()
    call.data = {"device_id": "dev-1", "action": "start_ventilation"}
    await handler(call)

    coord.async_start_ventilation.assert_awaited_once_with(vin)
    coord.async_lock.assert_not_called()


@pytest.mark.asyncio
async def test_execute_vehicle_action_unknown_action_raises() -> None:
    """Schema would reject this; we still guard defensively."""
    from homeassistant.exceptions import HomeAssistantError

    vin = "WVWZZZ123456"
    hass, _coord, _dr = _make_hass_with_device(vin)

    _register_services_with_patched_dr(hass)
    handler = hass._registered_services["execute_vehicle_action"]  # type: ignore[attr-defined]

    call = MagicMock()
    call.data = {"device_id": "dev-1", "action": "do_a_barrel_roll"}

    with pytest.raises(HomeAssistantError):
        await handler(call)


@pytest.mark.asyncio
async def test_execute_vehicle_action_unknown_device_raises() -> None:
    """Unknown device_id surfaces as ``ServiceValidationError``."""
    from homeassistant.exceptions import ServiceValidationError

    vin = "WVWZZZ123456"
    hass, _coord, dr_reg = _make_hass_with_device(vin)

    # Device-registry returns None for the unknown id.
    dr_reg.async_get = MagicMock(return_value=None)

    _register_services_with_patched_dr(hass)
    handler = hass._registered_services["execute_vehicle_action"]  # type: ignore[attr-defined]

    call = MagicMock()
    call.data = {"device_id": "not-a-real-device", "action": "lock"}

    with pytest.raises(ServiceValidationError) as excinfo:
        await handler(call)

    assert getattr(excinfo.value, "translation_domain", None) == DOMAIN
    assert getattr(excinfo.value, "translation_key", None) == "vehicle_not_found"
