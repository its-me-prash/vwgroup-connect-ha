# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""b14 (EXPERIMENTAL) — integration-registered named conditions for VW Group
Connect vehicles (HA 2026.7+ named-condition platform).

Same experimental caveat as ``trigger.py``: the developer API is upstream-flagged
"do not use yet by integrations" and may change without a deprecation notice, so
this is opt-in and modeled on ``homeassistant/components/sun/condition.py``.

v1 tests whether ANY of the account's vehicles is in the given state (e.g.
"a vehicle is charging") — read purely from the state we already poll, no new API
calls. Per-vehicle targeting is a future enhancement.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.typing import ConfigType

from .const import DOMAIN

# The named-condition platform only exists on HA 2026.7+ (upstream-flagged "do not
# use yet by integrations"). Import it defensively so the module stays importable
# — and static-analysable against an older HA baseline — on cores that don't have
# it yet; there, async_get_conditions simply registers nothing.
if TYPE_CHECKING:
    from homeassistant.helpers.condition import (  # type: ignore[attr-defined]
        Condition,
    )
else:
    try:
        from homeassistant.helpers.condition import Condition
    except ImportError:  # HA < 2026.7 — platform not available
        Condition = object

# condition id (is_* per HA naming rules) → the vehicle-dict boolean field it maps.
_BOOL_CONDITIONS: dict[str, str] = {
    "is_charging": "is_charging",
    "is_plugged_in": "plug_connected",
    "is_locked": "doors_locked",
    "is_preconditioning": "climatisation_active",
}
_CONDITION_KEYS: tuple[str, ...] = (*_BOOL_CONDITIONS, "is_charge_target_reached")


def _coordinators(hass: HomeAssistant) -> list[Any]:
    out: list[Any] = []
    for entry in hass.config_entries.async_entries(DOMAIN):
        coord = getattr(entry, "runtime_data", None)
        if coord is not None and getattr(coord, "vehicles", None) is not None:
            out.append(coord)
    return out


def _vehicle_matches(condition_key: str, veh: dict[str, Any]) -> bool:
    field = _BOOL_CONDITIONS.get(condition_key)
    if field is not None:
        return veh.get(field) is True
    if condition_key == "is_charge_target_reached":
        soc, tgt = veh.get("battery_soc"), veh.get("target_soc")
        return (
            isinstance(soc, int) and isinstance(tgt, int)
            and not isinstance(soc, bool) and not isinstance(tgt, bool)
            and soc >= tgt
        )
    return False


def _any_vehicle_matches(hass: HomeAssistant, condition_key: str) -> bool:
    for coord in _coordinators(hass):
        for vin, veh in (coord.vehicles or {}).items():
            if str(vin).startswith("_") or not isinstance(veh, dict):
                continue
            if _vehicle_matches(condition_key, veh):
                return True
    return False


class _VagVehicleCondition(Condition):
    """Base for a single 'any vehicle is <state>' condition."""

    _condition_key: str = ""

    @classmethod
    async def async_validate_config(
        cls, hass: HomeAssistant, config: ConfigType
    ) -> ConfigType:
        return config

    def __init__(self, hass: HomeAssistant, config: Any) -> None:
        super().__init__(hass, config)
        self._hass = hass

    def _async_check(self, **kwargs: Any) -> bool:
        return _any_vehicle_matches(self._hass, self._condition_key)


def _make_condition(condition_key: str) -> type[Condition]:
    class _C(_VagVehicleCondition):
        _condition_key = condition_key

    _C.__name__ = f"VagVehicle_{condition_key}_Condition"
    _C.__qualname__ = _C.__name__
    return _C


CONDITIONS: dict[str, type[Condition]] = {
    key: _make_condition(key) for key in _CONDITION_KEYS
}


async def async_get_conditions(hass: HomeAssistant) -> dict[str, type[Condition]]:
    """HA named-condition platform hook — expose our vehicle conditions.

    Only concrete classes are registered, so an experimental-API change degrades
    to registering nothing rather than a class HA cannot instantiate.
    """
    return {
        key: cls
        for key, cls in CONDITIONS.items()
        if not getattr(cls, "__abstractmethods__", frozenset())
    }
