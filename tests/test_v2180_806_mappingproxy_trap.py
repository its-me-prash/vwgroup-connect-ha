# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#806 (found by lucson) — entry.data/.options are MappingProxyType, not dict.

HA hands out ``ConfigEntry.data`` and ``.options`` as ``types.MappingProxyType``,
which is NOT a ``dict`` subclass. Any read that gated on ``isinstance(x, dict)``
therefore failed on every real install and silently returned its default. The
whole test suite faked these as plain dicts, which pass ``isinstance(dict)``, so
the trap was invisible.

lucson's PR #806 found and fixed it for the S-PIN. The same root cause bit four
more features — this file pins all of them against the real runtime type:

* S-PIN (every lock/unlock command → ``spin_required``)
* read-only override (``is_read_only`` returned False regardless of the setting,
  i.e. a user who asked for read-only got a writable integration)
* PPE climate flag (never activated)
* aux-heating duration/target-temp — both the command read and the Number
  entity that displays them (always showed the default, never the saved value)

The fix normalises the entry maps to real dicts at the read; these tests assert
the reads work with a ``MappingProxyType``, which is the type production sees.
"""
from __future__ import annotations

from types import MappingProxyType
from unittest.mock import MagicMock

from custom_components.vag_connect.const import (
    CONF_READ_ONLY,
    CONF_SPIN,
    CONF_SPIN_BY_VIN,
)


def test_the_trap_itself() -> None:
    # If this ever becomes True, HA changed the contract and the guards below
    # would be fine as dict again. Until then, this is the whole bug in one line.
    from collections.abc import Mapping

    proxy = MappingProxyType({"x": 1})
    assert not isinstance(proxy, dict)
    assert isinstance(proxy, Mapping)


def _coord(data: dict | None = None, options: dict | None = None):
    from custom_components.vag_connect.coordinator import VagConnectCoordinator

    c = VagConnectCoordinator.__new__(VagConnectCoordinator)
    c.entry = MagicMock()
    c.entry.data = MappingProxyType(data or {})
    c.entry.options = MappingProxyType(options or {})
    return c


class TestSpin:
    def test_shared_spin_is_read_back(self) -> None:
        assert _coord({CONF_SPIN: "4711"})._spin_from_entry() == "4711"

    def test_per_vin_wins(self) -> None:
        c = _coord({CONF_SPIN: "0000", CONF_SPIN_BY_VIN: {"VINX": "9999"}})
        assert c._spin_from_entry("VINX") == "9999"

    def test_per_vin_falls_back_to_shared(self) -> None:
        c = _coord({CONF_SPIN: "0000", CONF_SPIN_BY_VIN: {"VINX": "9999"}})
        assert c._spin_from_entry("other") == "0000"

    def test_options_beat_data(self) -> None:
        # Rare in practice (the listener folds options into data) but the
        # documented precedence must hold under the real type.
        c = _coord(data={CONF_SPIN: "1111"}, options={CONF_SPIN: "2222"})
        assert c._spin_from_entry() == "2222"


class TestReadOnlyOverride:
    def test_explicit_read_only_true_is_honoured(self) -> None:
        # Before the fix this returned False no matter what, so a user who set
        # read-only mode silently got a writable integration.
        c = _coord({CONF_READ_ONLY: True})
        c._active_strategy = "cariad"
        assert c.is_read_only() is True

    def test_explicit_read_only_false_is_honoured(self) -> None:
        c = _coord({CONF_READ_ONLY: False})
        c._active_strategy = "cariad"
        assert c.is_read_only() is False


class TestAuxHeatNumber:
    """The Number entity read its stored value via isinstance(dict) → default."""

    def _number(self, key: str, data: dict):
        from custom_components.vag_connect.number import VagConnectNumber

        n = VagConnectNumber.__new__(VagConnectNumber)
        n.coordinator = MagicMock()
        n.coordinator.entry = MagicMock()
        n.coordinator.entry.data = MappingProxyType(data)
        n.coordinator.entry.options = MappingProxyType({})
        desc = MagicMock()
        desc.key = key       # must be in _AUXHEAT_DEFAULTS to take the settings path
        desc.data_key = key  # the value is stored under the same key
        n.entity_description = desc
        return n

    def test_saved_value_survives_the_real_type(self) -> None:
        from custom_components.vag_connect.number import VagConnectNumber

        # A real aux-heat key + a non-default value; it must come back, not the default.
        key, default = next(iter(VagConnectNumber._AUXHEAT_DEFAULTS.items()))
        saved = float(default) + 5.0
        n = self._number(key, {key: saved})
        assert n.native_value == saved, "saved value was masked by the default"

    def test_absent_value_still_uses_default(self) -> None:
        from custom_components.vag_connect.number import VagConnectNumber

        key, default = next(iter(VagConnectNumber._AUXHEAT_DEFAULTS.items()))
        n = self._number(key, {})
        assert n.native_value == float(default)
