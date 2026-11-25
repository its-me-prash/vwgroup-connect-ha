# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#2084 — the climate entity provides the native temperature names as well.

Home Assistant 2026.11 deprecated ``temperature_unit``, ``current_temperature``
and ``target_temperature`` on ``ClimateEntity`` in favour of ``native_*`` names
(removal announced for 2027.11) and logs three warnings at start for a class
that provides only the old ones. #1965 kept the old names because the native
ones do not exist before 2026.11 and the integration supports 2026.6 onwards.

``migrate_deprecated_entity_members`` (HA 2026.11.0 to 2026.12.0b0) settles
the case of a class that provides both: "the native one when a class provides
both" wins, nothing is migrated and nothing is logged. Older versions do not
know the native names and read the old ones. So the class now defines both,
with the old names returning the native values.

Pinned on every Home Assistant version: both name sets are on the class, the
old names return what the native ones return, and the state attributes Home
Assistant builds carry the vehicle values. Pinned only where the native API
exists (CI installs the latest release): importing the module logs no
deprecation warning, the native members are our own properties rather than a
migration fallback, and the companion subclass is not migrated either.
"""
from __future__ import annotations

import importlib
import logging
from unittest.mock import MagicMock

import pytest
from homeassistant.components.climate import ClimateEntity
from homeassistant.const import UnitOfTemperature
from homeassistant.util.unit_system import METRIC_SYSTEM

from custom_components.vag_connect import climate as climate_mod

VIN = "WVWZZZTESTVIN2084"
_HAS_NATIVE = "native_current_temperature" in vars(ClimateEntity)
_needs_native = pytest.mark.skipif(
    not _HAS_NATIVE, reason="Home Assistant before 2026.11 has no native climate names",
)
_NATIVE = ("_attr_native_temperature_unit", "native_current_temperature",
           "native_target_temperature")
_OLD = ("_attr_temperature_unit", "current_temperature", "target_temperature")


def _coord(vehicle: dict) -> MagicMock:
    coord = MagicMock()
    coord.command_method_available = MagicMock(return_value=True)
    coord.is_companion = MagicMock(return_value=False)
    coord.data = {VIN: dict(vehicle)}
    return coord


def _entity() -> climate_mod.VagClimate:
    return climate_mod.VagClimate(
        _coord({"cabin_temp": 19.5, "target_temperature": 22}), VIN,
    )


# ── every Home Assistant version ──────────────────────────────────────────────


def test_both_name_sets_are_defined_on_the_class() -> None:
    own = vars(climate_mod.VagClimate)
    for name in _NATIVE + _OLD:
        assert name in own, f"VagClimate does not define {name} itself"


def test_old_names_return_the_native_values() -> None:
    e = _entity()
    assert e.native_current_temperature == 19.5
    assert e.current_temperature == e.native_current_temperature
    assert e.native_target_temperature == 22.0
    assert e.target_temperature == e.native_target_temperature
    assert e._attr_native_temperature_unit == UnitOfTemperature.CELSIUS


def test_state_attributes_carry_the_vehicle_values() -> None:
    """What Home Assistant itself builds, from whichever names it reads."""
    e = _entity()
    e.hass = MagicMock()
    e.hass.config.units = METRIC_SYSTEM
    attrs = e.state_attributes
    assert attrs["current_temperature"] == 19.5
    assert attrs["temperature"] == 22.0


# ── where the native API exists (HA 2026.11 onwards) ─────────────────────────


@_needs_native
def test_native_members_are_ours_not_a_migration_fallback() -> None:
    """A class with only the old names gets a fallback object put in place of
    each native name when it is created; ours must stay real properties."""
    own = vars(climate_mod.VagClimate)
    assert isinstance(own["native_current_temperature"], property)
    assert isinstance(own["native_target_temperature"], property)


@_needs_native
def test_importing_the_module_logs_no_deprecation_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The warning is written when the class is created, so the module has to
    be executed again inside the test for the check to see it."""
    caplog.set_level(logging.WARNING)
    importlib.reload(climate_mod)
    hits = [r.getMessage() for r in caplog.records
            if "provides the deprecated" in r.getMessage()]
    assert hits == []


@_needs_native
def test_companion_subclass_is_not_migrated() -> None:
    own = vars(climate_mod.VagCompanionClimate)
    for name in ("native_current_temperature", "native_target_temperature"):
        assert name not in own, (
            f"{name} was put on VagCompanionClimate, which means the subclass "
            f"was migrated instead of inheriting the native member"
        )
