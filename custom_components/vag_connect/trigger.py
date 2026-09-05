# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""b14 (EXPERIMENTAL) — integration-registered named triggers for VW Group
Connect vehicles (HA 2026.7+ named-trigger platform).

⚠️ The developer API for this platform is upstream-flagged "still in very active
development and should not be used yet by integrations. The API may change
without a deprecation notice" — and it DID change between HA 2026.6 and dev
(``async_attach_runner`` gained a ``did_not_trigger`` param). So this is opt-in /
experimental, modeled on ``homeassistant/components/sun/trigger.py``, and its
signatures must be re-verified at each HA bump. If the platform is absent on an
older core, ``async_get_triggers`` simply registers nothing.

Each trigger fires when the vehicle state edge is detected on a REAL data update
(coordinator._transition_detector) — no new API calls, purely derived from state
we already poll. v1 fires for ANY of the account's vehicles and hands the action
a payload with the ``vin`` (filter with ``{{ trigger.vin }}`` for one car);
per-device targeting is a future enhancement.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers.typing import ConfigType

from .const import DOMAIN
from .trigger_detect import EVENT_KEYS

# The named-trigger platform only exists on HA 2026.7+ (and is upstream-flagged
# "may change without a deprecation notice"). Import it defensively so the module
# stays importable — and static-analysable against an older HA baseline — on
# cores that don't have it yet; there, async_get_triggers simply registers
# nothing.
if TYPE_CHECKING:
    from homeassistant.helpers.trigger import (  # type: ignore[attr-defined]
        Trigger,
        TriggerActionRunner,
    )
else:
    try:
        from homeassistant.helpers.trigger import Trigger, TriggerActionRunner
    except ImportError:  # HA < 2026.7 — platform not available
        Trigger = object
        TriggerActionRunner = object


def _coordinators(hass: HomeAssistant) -> list[Any]:
    """Every loaded vag_connect coordinator (one per brand/account entry)."""
    out: list[Any] = []
    for entry in hass.config_entries.async_entries(DOMAIN):
        coord = getattr(entry, "runtime_data", None)
        if coord is not None and hasattr(coord, "register_transition_listener"):
            out.append(coord)
    return out


class _VagVehicleTrigger(Trigger):
    """Base for a single vehicle state-transition trigger.

    Subclasses set ``_event_key`` to one of :data:`trigger_detect.EVENT_KEYS`.
    """

    _event_key: str = ""

    @classmethod
    async def async_validate_config(
        cls, hass: HomeAssistant, config: ConfigType
    ) -> ConfigType:
        return config

    def __init__(self, hass: HomeAssistant, config: Any) -> None:
        super().__init__(hass, config)
        self._hass = hass

    async def async_attach_runner(
        self,
        run_action: TriggerActionRunner,
        did_not_trigger: Any = None,
    ) -> CALLBACK_TYPE:
        # did_not_trigger is accepted for forward-compat with newer HA cores that
        # pass it (HA 2026.6 does not); we don't use it.
        event_key = self._event_key

        def _on_transition(payload: dict[str, Any]) -> None:
            run_action(payload, f"vehicle {payload.get('event', event_key)}")

        unsubs = [
            coord.register_transition_listener(event_key, None, _on_transition)
            for coord in _coordinators(self._hass)
        ]

        @callback
        def _remove() -> None:
            for unsub in unsubs:
                unsub()

        return _remove


def _make_trigger(event_key: str) -> type[Trigger]:
    """Build a concrete Trigger subclass for one event key."""

    class _T(_VagVehicleTrigger):
        _event_key = event_key

    _T.__name__ = f"VagVehicle_{event_key}_Trigger"
    _T.__qualname__ = _T.__name__
    return _T


# Registered trigger names → classes. Keys are the stable snake_case ids the
# strings.json "triggers" section + triggers.yaml describe.
TRIGGERS: dict[str, type[Trigger]] = {
    event_key: _make_trigger(event_key) for event_key in sorted(EVENT_KEYS)
}


async def async_get_triggers(hass: HomeAssistant) -> dict[str, type[Trigger]]:
    """HA named-trigger platform hook — expose our vehicle triggers.

    Robust against the experimental API changing: only classes that are actually
    CONCRETE (all abstractmethods implemented) are registered, so if a future HA
    adds/renames a required method, we degrade to registering nothing instead of
    handing HA a class it cannot instantiate.
    """
    return {
        key: cls
        for key, cls in TRIGGERS.items()
        if not getattr(cls, "__abstractmethods__", frozenset())
    }
