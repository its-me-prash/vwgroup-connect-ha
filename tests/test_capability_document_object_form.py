# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The capability document as an object keyed by capability id.

The vehicle backend for Volkswagen and Audi sends

    {"capabilities": {"access": {"id": "access", "status": [], ...}, ...},
     "parameters": ..., "vin": ...}

(measured on an Audi S6 C8, 52 entries), while the gate only understood a
list of entries. With the object form every answer came out as "unknown", so
nothing was ever gated and a refused command could not name its reason. Both
forms must give the same answers.
"""
from __future__ import annotations

import threading
from typing import Any
from unittest.mock import MagicMock

import pytest

from custom_components.vag_connect.cariad._capabilities import cap_id_for
from custom_components.vag_connect.const import CONF_BRAND
from custom_components.vag_connect.coordinator import (
    VagConnectCoordinator,
    _capability_listed,
)

_OK = {"id": "access", "status": [], "isEnabled": True}
_NO_LICENCE = {"id": "onlineLogBook", "status": ["MissingLicense"], "isEnabled": False}
_SWITCHED_OFF = {
    "id": "dealerAppointment",
    "status": ["InitiallyDisabled", "DisabledByUser"],
    "isEnabled": False,
}
_ENTRIES = (_OK, _NO_LICENCE, _SWITCHED_OFF)

_AS_LIST: dict[str, Any] = {"capabilities": list(_ENTRIES)}
_AS_OBJECT: dict[str, Any] = {
    "capabilities": {str(e["id"]): e for e in _ENTRIES},
    "parameters": [],
    "vin": "VIN1",
}


def _coord(doc: Any, brand: str = "audi") -> VagConnectCoordinator:
    coord = VagConnectCoordinator.__new__(VagConnectCoordinator)
    coord.entry = MagicMock()
    coord.entry.data = {CONF_BRAND: brand}
    coord._vehicles_lock = threading.Lock()
    coord.vehicles = {"VIN1": {}}
    coord.vehicle_capabilities = {"VIN1": doc}
    return coord


@pytest.mark.parametrize("doc", [_AS_LIST, _AS_OBJECT], ids=["list", "object"])
@pytest.mark.parametrize(
    ("capability", "expected"),
    [
        ("access", True),              # listed, no limitation
        ("onlineLogBook", False),      # listed, no licence
        ("dealerAppointment", False),  # listed, switched off
        ("climatisation", False),      # document loaded, not listed
    ],
)
def test_both_forms_give_the_same_answer(doc: Any, capability: str, expected: bool) -> None:
    assert _coord(doc).vehicle_supports_capability("VIN1", capability) is expected


@pytest.mark.parametrize("doc", [_AS_LIST, _AS_OBJECT], ids=["list", "object"])
def test_both_forms_name_the_reason(doc: Any) -> None:
    coord = _coord(doc)
    assert coord.capability_gating_reason("VIN1", "access") is None
    assert coord.capability_gating_reason("VIN1", "climatisation") is None
    for capability in ("onlineLogBook", "dealerAppointment"):
        reason = coord.capability_gating_reason("VIN1", capability)
        assert reason is not None, capability
        assert isinstance(reason[1], str) and reason[1]
    # the list form and the object form must agree word for word
    other = _coord(_AS_LIST if doc is _AS_OBJECT else _AS_OBJECT)
    for capability in ("onlineLogBook", "dealerAppointment"):
        assert coord.capability_gating_reason("VIN1", capability) == other.capability_gating_reason(
            "VIN1", capability
        )


@pytest.mark.parametrize("doc", [_AS_LIST, _AS_OBJECT], ids=["list", "object"])
def test_both_forms_answer_whether_a_capability_is_listed(doc: Any) -> None:
    assert _capability_listed(doc, "access") is True
    assert _capability_listed(doc, "onlineLogBook") is True  # listed, though limited
    assert _capability_listed(doc, "climatisation") is False


def test_object_entry_without_an_id_takes_it_from_its_key() -> None:
    doc = {"capabilities": {"honkAndFlash": {"status": []}, "access": {"status": ["MissingLicense"]}}}
    coord = _coord(doc)
    assert coord.vehicle_supports_capability("VIN1", "honkAndFlash") is True
    assert coord.vehicle_supports_capability("VIN1", "access") is False
    assert _capability_listed(doc, "honkAndFlash") is True


def test_object_entry_keeps_its_own_id() -> None:
    # The entry's own id decides, as it does in the list form.
    doc = {"capabilities": {"someKey": {"id": "access", "status": []}}}
    coord = _coord(doc)
    assert coord.vehicle_supports_capability("VIN1", "access") is True
    assert coord.vehicle_supports_capability("VIN1", "someKey") is False


def test_object_values_that_are_no_entries_are_skipped() -> None:
    doc = {"capabilities": {"access": {"status": []}, "broken": "text", "alsoBroken": None}}
    coord = _coord(doc)
    assert coord.vehicle_supports_capability("VIN1", "access") is True
    assert coord.vehicle_supports_capability("VIN1", "broken") is False


@pytest.mark.parametrize(
    "doc",
    [
        None,                              # nothing cached
        {},                                # an empty answer
        {"capabilities": None},
        {"capabilities": "text"},
        {"capabilities": 7},
        {"capabilities": {"access": _OK}, "errors": [{"code": "x"}]},  # backend flagged the document
        {"capabilities": [_OK], "errors": [{"code": "x"}]},
    ],
)
def test_no_usable_document_stays_unknown(doc: Any) -> None:
    coord = _coord(doc)
    assert coord.vehicle_supports_capability("VIN1", "access") is None
    assert coord.capability_gating_reason("VIN1", "access") is None
    assert _capability_listed(doc, "access") is None


@pytest.mark.parametrize(
    "capabilities",
    [[_NO_LICENCE], {"onlineLogBook": _NO_LICENCE}],
    ids=["list", "object"],
)
def test_flagged_document_is_not_gated_on_but_still_explains(capabilities: Any) -> None:
    # A document the backend flagged with ``errors`` must not gate anything.
    # The reason lookup never looked at that flag and still answers, so a
    # refused command keeps its explanation. Unchanged for the list form.
    doc = {"capabilities": capabilities, "errors": [{"code": "x"}]}
    coord = _coord(doc)
    assert coord.vehicle_supports_capability("VIN1", "onlineLogBook") is None
    assert _capability_listed(doc, "onlineLogBook") is None
    reason = coord.capability_gating_reason("VIN1", "onlineLogBook")
    assert reason is not None and reason[0] == "license"


def test_command_gate_follows_the_object_form() -> None:
    coord = _coord(
        {"capabilities": {
            "access": {"id": "access", "status": []},
            "honkAndFlash": {"id": "honkAndFlash", "status": ["MissingLicense"]},
        }}
    )
    assert coord.command_capability_supported("VIN1", "command_lock") is True
    assert coord.command_capability_supported("VIN1", "command_flash") is False
    assert coord.command_capability_supported("VIN1", "command_start_climate") is False
    reason = coord.command_gating_reason("VIN1", "command_flash")
    assert reason is not None


# ── the ids the gate asks for ────────────────────────────────────────────────
# With the object form read, a wrong id in the table no longer goes unnoticed:
# it would hide a control on every car. These rows are the ones the apps'
# vehicle library defines (myAudi 5.9.0 and We Connect 4.8.1, 133 ids each).


@pytest.mark.parametrize("brand", ["audi", "volkswagen"])
def test_window_heating_is_gated_by_climatisation(brand: str) -> None:
    # The library has no window heating capability of its own; the window
    # heating status and actions belong to climatisation. The older id stays
    # as a second one, so nothing that showed before is hidden by this row.
    for command in ("command_start_window_heating", "command_stop_window_heating"):
        assert cap_id_for(brand, command) == ("climatisation", "windowHeating")


def test_engine_start_is_gated_by_engine_control() -> None:
    # ``engineControl`` is the id the app's engine start checks. The earlier
    # guess stays as a second id, so the row hides nothing it showed before.
    for command in ("command_engine_start", "command_engine_stop"):
        assert cap_id_for("audi", command) == ("engineControl", "engineRemoteStart")


@pytest.mark.parametrize("listed", ["engineControl", "engineRemoteStart"])
def test_engine_start_shows_under_either_id(listed: str) -> None:
    coord = _coord({"capabilities": {listed: {"id": listed, "status": []}}})
    assert coord.command_capability_supported("VIN1", "command_engine_start") is True


def test_engine_start_hides_when_neither_id_is_listed() -> None:
    coord = _coord({"capabilities": {"access": {"id": "access", "status": []}}})
    assert coord.command_capability_supported("VIN1", "command_engine_start") is False


@pytest.mark.parametrize("brand", ["audi", "volkswagen"])
def test_wake_is_offered_under_either_wake_capability(brand: str) -> None:
    assert cap_id_for(brand, "command_wake") == ("vehicleWakeUpTrigger", "vehicleWakeUp")


def test_window_heating_shows_on_a_car_with_climatisation() -> None:
    coord = _coord({"capabilities": {"climatisation": {"id": "climatisation", "status": []}}})
    assert coord.command_capability_supported("VIN1", "command_start_window_heating") is True


def test_window_heating_shows_on_a_document_with_the_older_id() -> None:
    coord = _coord({"capabilities": [{"id": "windowHeating", "status": []}]})
    assert coord.command_capability_supported("VIN1", "command_start_window_heating") is True


def test_window_heating_hides_when_neither_id_is_listed() -> None:
    coord = _coord({"capabilities": {"access": {"id": "access", "status": []}}})
    assert coord.command_capability_supported("VIN1", "command_start_window_heating") is False


def test_wake_shows_when_only_the_plain_wake_capability_is_listed() -> None:
    coord = _coord({"capabilities": {"vehicleWakeUp": {"id": "vehicleWakeUp", "status": []}}})
    assert coord.command_capability_supported("VIN1", "command_wake") is True


def test_wake_hides_when_no_wake_capability_is_listed() -> None:
    coord = _coord({"capabilities": {"access": {"id": "access", "status": []}}})
    assert coord.command_capability_supported("VIN1", "command_wake") is False
