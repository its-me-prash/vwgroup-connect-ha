# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#2122 — a command a client only inherits as the base-class placeholder is not available.

``CariadBaseClient`` declares the shared ``command_*`` methods as bare
``raise NotImplementedError`` placeholders. ``command_method_available`` used to
answer with ``hasattr``, which is true for every inherited placeholder, so a
Škoda Elroq got a charge-mode select showing ``unknown`` whose every choice
raised NotImplementedError. The same gate also let a SEAT/CUPRA car get that
select, and both brands a minimum-charge slider with the same fault.

The oracle in ``test_gate_matches_the_method_body`` is independent of the fix:
it reads the body of the method a client would really run and checks the gate
agrees with it, for every client that inherits from the base class.
"""
from __future__ import annotations

import ast
import asyncio
import importlib
import inspect
import pkgutil
import textwrap
from functools import partial
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import custom_components.vag_connect.cariad.api as api_pkg
from custom_components.vag_connect.cariad.api.audi import AudiClient
from custom_components.vag_connect.cariad.api.base import CariadBaseClient
from custom_components.vag_connect.cariad.api.seat_cupra import SeatCupraClient
from custom_components.vag_connect.cariad.api.skoda import SkodaClient
from custom_components.vag_connect.cariad.api.skoda_official import SkodaOfficialClient
from custom_components.vag_connect.cariad.api.vw_eu import VWEUClient
from custom_components.vag_connect.coordinator import VagConnectCoordinator

_BASE_COMMANDS = sorted(n for n in CariadBaseClient.__dict__ if n.startswith("command_"))


def _bare(cls: type) -> Any:
    return cls.__new__(cls)


def _coord(client: Any) -> VagConnectCoordinator:
    c = VagConnectCoordinator.__new__(VagConnectCoordinator)
    c._cariad_client = client
    return c


def _is_bare_stub(fn: Any) -> bool:
    """True when the body is (a docstring and) nothing but ``raise NotImplementedError``."""
    src = textwrap.dedent(inspect.getsource(inspect.unwrap(fn)))
    body = list(ast.parse(src).body[0].body)  # type: ignore[attr-defined]
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
        body = body[1:]
    if len(body) != 1 or not isinstance(body[0], ast.Raise) or body[0].exc is None:
        return False
    exc = body[0].exc
    if isinstance(exc, ast.Call):
        exc = exc.func
    return isinstance(exc, ast.Name) and exc.id == "NotImplementedError"


def _base_subclasses() -> list[type]:
    found: dict[str, type] = {}
    for info in pkgutil.iter_modules(api_pkg.__path__):
        mod = importlib.import_module(f"{api_pkg.__name__}.{info.name}")
        for obj in vars(mod).values():
            if (
                inspect.isclass(obj)
                and issubclass(obj, CariadBaseClient)
                and obj is not CariadBaseClient
            ):
                found[f"{obj.__module__}.{obj.__qualname__}"] = obj
    return [found[k] for k in sorted(found)]


def test_the_base_class_still_declares_placeholders() -> None:
    # Positive control for the oracle below: without bare stubs in the base
    # class there would be nothing for the gate to tell apart.
    stubs = [n for n in _BASE_COMMANDS if _is_bare_stub(CariadBaseClient.__dict__[n])]
    assert "command_set_charge_mode" in stubs
    assert len(stubs) >= 10


@pytest.mark.parametrize(
    "command",
    [
        "command_set_charge_mode",
        "command_set_min_soc",
        "command_set_battery_care_target",
        "command_start_climate_control",
    ],
)
def test_skoda_inherited_placeholders_are_not_available(command: str) -> None:
    assert _coord(_bare(SkodaClient)).command_method_available(command) is False


@pytest.mark.parametrize(
    "command",
    [
        "command_lock",
        "command_set_target_soc",
        "command_set_battery_care",
        "command_update_charging_settings",
        "command_start_active_ventilation",
    ],
)
def test_skoda_real_commands_stay_available(command: str) -> None:
    assert _coord(_bare(SkodaClient)).command_method_available(command) is True


@pytest.mark.parametrize(
    ("command", "expected"),
    [
        ("command_set_charge_mode", False),
        ("command_set_min_soc", False),
        ("command_start_climate_control", False),
        ("command_set_battery_care_target", True),
        ("command_flash", True),
        ("command_update_charging_settings", True),
    ],
)
def test_seat_cupra_gate(command: str, expected: bool) -> None:
    assert _coord(_bare(SeatCupraClient)).command_method_available(command) is expected


def test_a_command_the_client_lacks_entirely_stays_unavailable() -> None:
    assert (
        _coord(_bare(SkodaClient)).command_method_available("command_set_max_charge_current")
        is False
    )


@pytest.mark.parametrize("cls", [VWEUClient, AudiClient], ids=lambda c: c.__name__)
def test_vw_eu_family_keeps_every_shared_command(cls: type) -> None:
    coord = _coord(_bare(cls))
    missing = [c for c in _BASE_COMMANDS if not coord.command_method_available(c)]
    assert missing == []


def test_gate_matches_the_method_body() -> None:
    wrong: list[str] = []
    for cls in _base_subclasses():
        coord = _coord(_bare(cls))
        for command in _BASE_COMMANDS:
            runs = getattr(cls, command)
            expected = not _is_bare_stub(runs)
            if coord.command_method_available(command) is not expected:
                wrong.append(f"{cls.__name__}.{command} (expected {expected})")
    assert wrong == []


def test_a_method_set_on_the_instance_counts() -> None:
    # The dispatcher calls getattr(client, name), so an instance attribute is
    # what would run; the gate must judge that, not the class placeholder.
    client = _bare(SkodaClient)
    client.command_set_charge_mode = AsyncMock()
    assert _coord(client).command_method_available("command_set_charge_mode") is True


def test_mock_clients_keep_every_command() -> None:
    # Many platform tests hand the coordinator a MagicMock client and rely on
    # every command being offered; the gate must not start hiding those.
    assert _coord(MagicMock()).command_method_available("command_set_charge_mode") is True


# ── spawn level: what the platforms create ───────────────────────────────────


def _platform_coord(client: Any) -> MagicMock:
    coord = MagicMock()
    coord._cariad_client = client
    coord.command_method_available = partial(
        VagConnectCoordinator.command_method_available, coord
    )
    coord.is_read_only.return_value = False
    coord.is_companion.return_value = False
    coord.command_capability_supported.return_value = None
    coord.read_capability_hidden.return_value = False
    coord.entry.entry_id = "ENTRY_A"
    coord.entry.data = {}
    return coord


def _built(
    module_name: str, brand: str, client: Any, vehicle: dict[str, Any] | None = None,
) -> list[str]:
    """Names (description key, else class name) of what ``_added`` returns."""
    names = []
    for ent in _added(module_name, brand, client, vehicle):
        desc = getattr(ent, "entity_description", None)
        names.append(getattr(desc, "key", None) or type(ent).__name__)
    return names


def _added(
    module_name: str, brand: str, client: Any, vehicle: dict[str, Any] | None = None,
) -> list[Any]:
    """What the platform adds in its FIRST spawn pass, through the real spawner.

    The first pass is the one that matters: the spawner adds entities and never
    removes them. The client is built synchronously in ``async_setup`` before
    the platforms are forwarded, so this gate is already decidable here, unlike
    a gate that waits for the capability document fetched in the background.
    """
    module = importlib.import_module(f"custom_components.vag_connect.{module_name}")
    coord = _platform_coord(client)
    coord.vehicles = {"VIN0000000000TEST": vehicle or {"has_battery": True}}
    entry = MagicMock()
    entry.runtime_data = coord
    entry.data = {"brand": brand}
    added: list[Any] = []
    asyncio.run(module.async_setup_entry(MagicMock(), entry, added.extend))
    return added


@pytest.mark.parametrize(
    ("brand", "cls"),
    [("skoda", SkodaClient), ("seat", SeatCupraClient), ("cupra", SeatCupraClient)],
)
def test_no_charge_mode_select_without_the_command(brand: str, cls: type) -> None:
    # Read-only is switched off by hand here. A real SEAT/CUPRA entry is forced
    # read-only (coordinator.is_read_only), so for those brands this guards the
    # client gate, not a control a user could see today.
    assert "VagChargeModeSelect" not in _built("select", brand, _bare(cls))


def test_vw_eu_still_gets_the_charge_mode_select() -> None:
    assert "VagChargeModeSelect" in _built("select", "volkswagen", _bare(VWEUClient))


def test_skoda_keeps_its_charge_current_select() -> None:
    assert "VagSkodaChargeCurrentSelect" in _built("select", "skoda", _bare(SkodaClient))


@pytest.mark.parametrize(
    ("brand", "cls"),
    [("skoda", SkodaClient), ("seat", SeatCupraClient)],
)
def test_no_min_soc_slider_without_the_command(brand: str, cls: type) -> None:
    built = _built("number", brand, _bare(cls))
    assert "min_soc" not in built
    assert "target_soc" in built  # positive control: the builder did run


def test_vw_eu_still_gets_the_min_soc_slider() -> None:
    assert "min_soc" in _built("number", "volkswagen", _bare(VWEUClient))


# ── battery care: read-gated controls also need a command that can be sent ───

_CARE = {"has_battery": True, "battery_care_enabled": True, "battery_care_target_soc_pct": 80}


def test_skoda_gets_no_battery_care_target_slider() -> None:
    # Škoda reports the care target but only inherits the placeholder for
    # setting it, so the slider could only ever raise NotImplementedError.
    built = _built("number", "skoda", _bare(SkodaClient), _CARE)
    assert "battery_care_target" not in built
    assert "target_soc" in built  # positive control: the builder did run


def test_skoda_keeps_its_battery_care_switch() -> None:
    # SkodaClient implements command_set_battery_care itself.
    assert "VagBatteryCareSwitch" in _built("switch", "skoda", _bare(SkodaClient), _CARE)


def test_skoda_official_gets_neither_battery_care_control() -> None:
    # The official API reads battery care but has no command for it at all.
    client = _bare(SkodaOfficialClient)
    assert "VagBatteryCareSwitch" not in _built("switch", "skoda_official", client, _CARE)
    assert "battery_care_target" not in _built("number", "skoda_official", client, _CARE)


def test_vw_eu_keeps_both_battery_care_controls() -> None:
    client = _bare(VWEUClient)
    assert "VagBatteryCareSwitch" in _built("switch", "volkswagen", client, _CARE)
    assert "battery_care_target" in _built("number", "volkswagen", client, _CARE)


# ── registry: a control an earlier version created is removed once ──────────

_VIN = "VIN0000000000TEST"


class _FakeRegistry:
    """The four registry calls the cleanup uses, recording removals."""

    def __init__(self, entries: dict[tuple[str, str], tuple[str, str]]) -> None:
        # (platform, unique_id) -> (entity_id, owning config entry id)
        self.entries = dict(entries)
        self.removed: list[str] = []

    def async_get_entity_id(self, platform: str, domain: str, unique_id: str) -> str | None:
        assert domain == "vag_connect"
        hit = self.entries.get((platform, unique_id))
        return hit[0] if hit else None

    def async_get(self, entity_id: str) -> Any:
        for eid, owner in self.entries.values():
            if eid == entity_id:
                return MagicMock(config_entry_id=owner)
        return None

    def async_remove(self, entity_id: str) -> None:
        self.removed.append(entity_id)


def _removed_after_setup(
    module_name: str, brand: str, client: Any, entries: dict[tuple[str, str], tuple[str, str]],
) -> list[str]:
    registry = _FakeRegistry(entries)
    with patch("homeassistant.helpers.entity_registry.async_get", return_value=registry):
        _built(module_name, brand, client, _CARE)
    return registry.removed


@pytest.mark.parametrize(
    ("module_name", "brand", "cls", "key"),
    [
        ("select", "skoda", SkodaClient, "charge_mode_select"),
        ("number", "skoda", SkodaClient, "min_soc"),
        ("number", "skoda", SkodaClient, "battery_care_target"),
        ("switch", "skoda_official", SkodaOfficialClient, "battery_care_switch"),
    ],
)
def test_an_unsendable_control_left_by_an_earlier_version_is_removed(
    module_name: str, brand: str, cls: type, key: str,
) -> None:
    entity_id = f"{module_name}.old_{key}"
    entries = {(module_name, f"{_VIN}_{key}"): (entity_id, "ENTRY_A")}
    assert _removed_after_setup(module_name, brand, _bare(cls), entries) == [entity_id]


def test_a_sendable_control_is_never_removed() -> None:
    entries = {
        ("select", f"{_VIN}_charge_mode_select"): ("select.vw_mode", "ENTRY_A"),
        ("number", f"{_VIN}_min_soc"): ("number.vw_min", "ENTRY_A"),
        ("number", f"{_VIN}_battery_care_target"): ("number.vw_care", "ENTRY_A"),
        ("switch", f"{_VIN}_battery_care_switch"): ("switch.vw_care", "ENTRY_A"),
    }
    for module_name in ("select", "number", "switch"):
        assert _removed_after_setup(module_name, "volkswagen", _bare(VWEUClient), entries) == []


def test_skoda_keeps_its_working_battery_care_switch_entry() -> None:
    entries = {("switch", f"{_VIN}_battery_care_switch"): ("switch.care", "ENTRY_A")}
    assert _removed_after_setup("switch", "skoda", _bare(SkodaClient), entries) == []


def test_an_entity_of_another_entry_is_never_removed() -> None:
    # A Škoda entry and an official-API entry for the same car share unique
    # ids; the official entry must not delete the Škoda entry's working switch.
    entries = {("switch", f"{_VIN}_battery_care_switch"): ("switch.care", "ENTRY_B")}
    assert _removed_after_setup("switch", "skoda_official", _bare(SkodaOfficialClient), entries) == []


def test_cleanup_keys_are_the_keys_the_platforms_build() -> None:
    # A renamed entity key would make the cleanup miss silently; every listed
    # key must be one the platform really creates where the command exists.
    from custom_components.vag_connect.entity_base import UNSENDABLE_CONTROLS

    for platform, controls in UNSENDABLE_CONTROLS.items():
        keys = {getattr(e, "_key", None) for e in _added(platform, "volkswagen", _bare(VWEUClient), _CARE)}
        for key, _command in controls:
            assert key in keys, f"{platform}: {key} is not a key the platform builds"


def _real_entity_registry() -> Any:
    """A real ``EntityRegistry`` on a mocked hass, persistence stubbed out."""
    from homeassistant.helpers import entity_registry as ha_er

    hass = MagicMock()
    registry = ha_er.EntityRegistry(hass)
    registry.async_schedule_save = MagicMock()  # type: ignore[method-assign]
    # What async_load sets up for an empty store, without reading one.
    registry.entities = ha_er.EntityRegistryItems(hass)
    registry.deleted_entities = {}
    registry.settings = ha_er.EntityRegistrySettings()
    registry._entities_data = registry.entities.data
    return registry


def _owned_by(entry_id: str) -> Any:
    entry = MagicMock(entry_id=entry_id, disabled_by=None)
    entry.domain = "vag_connect"
    return entry


def test_cleanup_against_a_real_entity_registry() -> None:
    # The fake above cannot catch a wrong argument order or attribute name;
    # this pins the four registry calls against the installed Home Assistant.
    registry = _real_entity_registry()
    mine = registry.async_get_or_create(
        "select", "vag_connect", f"{_VIN}_charge_mode_select", config_entry=_owned_by("ENTRY_A"),
    )
    theirs = registry.async_get_or_create(
        "number", "vag_connect", f"{_VIN}_min_soc", config_entry=_owned_by("ENTRY_B"),
    )
    with patch("homeassistant.helpers.entity_registry.async_get", return_value=registry):
        _built("select", "skoda", _bare(SkodaClient), _CARE)
        _built("number", "skoda", _bare(SkodaClient), _CARE)
    assert registry.async_get(mine.entity_id) is None
    # Control: the other entry's entity survives, so removal is not wholesale.
    assert registry.async_get(theirs.entity_id) is not None
