# Copyright 2026 Prash Balan (@its-me-prash) - Apache License 2.0
"""v2.8.0 quick-win B - tests for the ``vag_connect.open_app`` service.

Coverage:

1. ``_build_deeplink_url`` returns the brand base for the default
   ``open`` action and appends the action path for non-default actions.
2. The service handler fires the ``vag_connect_open_app`` event with
   ``{vin, brand, deeplink_url, action}`` when called with a valid VIN.
3. The service handler raises ``ServiceValidationError`` when the VIN
   does not belong to any loaded config entry.
4. The ``action`` parameter is propagated into the event payload.

The ``services`` module imports Home Assistant at top level so every
test in this file is tagged ``ha_required`` and auto-skips when HA is
not installed (see ``tests/conftest.py``).
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from custom_components.vag_connect.const import DEEPLINK_SCHEMES, DOMAIN

# Module-level marker: the services module pulls in homeassistant.core
# + homeassistant.exceptions, so without HA installed the whole file
# would error during collection. ``ha_required`` lets conftest skip
# us cleanly in local pure-Python runs.
pytestmark = pytest.mark.ha_required


# ---------------------------------------------------------------------------
# ``_build_deeplink_url`` pure-helper coverage
# ---------------------------------------------------------------------------


class TestBuildDeeplinkUrl:
    """Exercise the deeplink composition independently of the handler.

    The helper itself does not touch HA, but importing the module
    requires HA so we sit under the ``ha_required`` umbrella.
    """

    def _build(self, brand: str, action: str) -> str:
        from custom_components.vag_connect.services import _build_deeplink_url

        return _build_deeplink_url(brand, action)

    def test_default_open_returns_base_scheme(self) -> None:
        assert self._build("audi", "open") == "myaudi://"

    def test_non_default_action_appends_path(self) -> None:
        assert self._build("audi", "lock") == "myaudi://lock"
        assert self._build("skoda", "climate_on") == "myskoda://climate_on"

    def test_unknown_brand_returns_empty(self) -> None:
        assert self._build("not-a-brand", "open") == ""
        assert self._build("", "open") == ""

    def test_every_known_brand_has_scheme(self) -> None:
        """Every brand in ``BRANDS`` should also have an entry in
        ``DEEPLINK_SCHEMES`` so the service never silently no-ops on
        a legitimate config entry.
        """
        from custom_components.vag_connect.const import BRANDS

        missing = sorted(set(BRANDS) - set(DEEPLINK_SCHEMES))
        assert missing == [], f"brands without deeplink scheme: {missing}"


# ---------------------------------------------------------------------------
# Service-handler coverage
# ---------------------------------------------------------------------------


def _make_hass_with_vin(vin: str, brand: str) -> tuple[MagicMock, MagicMock]:
    """Build a minimal hass + coordinator pair the handler can use.

    The handler scans ``hass.config_entries.async_entries(DOMAIN)`` and
    inspects each entry's ``runtime_data.vehicles`` +
    ``entry.data[CONF_BRAND]``. We synthesise both so we don't need a
    live config flow.
    """
    coordinator = MagicMock()
    coordinator.vehicles = {vin: {"vin": vin}}

    entry = MagicMock()
    entry.runtime_data = coordinator
    entry.data = {"brand": brand}
    coordinator.entry = entry

    hass = MagicMock()
    hass.config_entries.async_entries.return_value = [entry]
    hass.bus.async_fire = MagicMock()
    return hass, coordinator


async def _call_service(hass: MagicMock, **call_data: Any) -> None:
    """Invoke the open_app handler directly without a running HA loop.

    Registers the service through the public entry point so we exercise
    the same wiring the integration uses at runtime, then captures the
    registered callable and calls it with a synthesised ``ServiceCall``.
    """
    from custom_components.vag_connect.services import (
        async_register_open_app_service,
    )

    handler_box: dict[str, Any] = {}

    def _capture_register(
        _domain: str, _name: str, handler: Any, *_a: Any, **_kw: Any
    ) -> None:
        handler_box["handler"] = handler

    hass.services.async_register.side_effect = _capture_register
    async_register_open_app_service(hass)

    call = MagicMock()
    call.data = call_data
    await handler_box["handler"](call)


@pytest.mark.asyncio
async def test_open_app_fires_event_with_brand_and_url() -> None:
    """Happy path: valid VIN fires event with full payload."""
    vin = "WVWZZZ123456"
    hass, _coord = _make_hass_with_vin(vin, "audi")

    await _call_service(hass, vin=vin, action="open")

    hass.bus.async_fire.assert_called_once()
    event_name, payload = hass.bus.async_fire.call_args.args
    assert event_name == "vag_connect_open_app"
    assert payload == {
        "vin": vin,
        "brand": "audi",
        "deeplink_url": "myaudi://",
        "action": "open",
    }


@pytest.mark.asyncio
async def test_open_app_propagates_action_into_payload() -> None:
    """``action != open`` must be reflected in payload + deeplink path."""
    vin = "WSKODATEST00001"
    hass, _coord = _make_hass_with_vin(vin, "skoda")

    await _call_service(hass, vin=vin, action="lock")

    hass.bus.async_fire.assert_called_once()
    _event_name, payload = hass.bus.async_fire.call_args.args
    assert payload["action"] == "lock"
    assert payload["deeplink_url"] == "myskoda://lock"
    assert payload["brand"] == "skoda"


@pytest.mark.asyncio
async def test_open_app_unknown_vin_raises_validation_error() -> None:
    """Unknown VIN raises ``ServiceValidationError`` with i18n hooks."""
    from homeassistant.exceptions import ServiceValidationError

    hass, _coord = _make_hass_with_vin("OWNEDVIN0000001", "audi")

    with pytest.raises(ServiceValidationError) as excinfo:
        await _call_service(hass, vin="NOTOWNED9999999", action="open")

    assert getattr(excinfo.value, "translation_domain", None) == DOMAIN
    assert getattr(excinfo.value, "translation_key", None) == "vehicle_not_found"
    hass.bus.async_fire.assert_not_called()
