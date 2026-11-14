# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Options flow: link / unlink a local OBD source (DrivePulse) to a car.

The source knows no VIN, so the user picks the car by hand. The link map
{VIN: device_id} lives in entry.data and a reload applies it.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.vag_connect.config_flow import VagConnectOptionsFlow
from custom_components.vag_connect.const import (
    CONF_DRIVEPULSE_LINKS,
    CONF_SCAN_INTERVAL,
    CONF_SUPPLEMENTARY_TIBBER,
)

VIN_A = "WVWZZZTESTFAKE001"
VIN_B = "WVWZZZTESTFAKE002"


def _device(dev_id: str, domain: str = "drivepulse") -> MagicMock:
    dev = MagicMock()
    dev.id = dev_id
    dev.identifiers = {(domain, f"x-{dev_id}")}
    dev.config_entries = set()
    return dev


def _other_entry(links: dict | None) -> MagicMock:
    other = MagicMock()
    other.entry_id = "E2"
    other.data = {CONF_DRIVEPULSE_LINKS: links} if links is not None else {}
    return other


def _flow(
    data: dict,
    devices: list | None = None,
    others: list | None = None,
    vehicles: dict | None = None,
) -> VagConnectOptionsFlow:
    entry = MagicMock()
    entry.entry_id = "E1"
    entry.data = data
    entry.options = {}
    entry.runtime_data = MagicMock(
        vehicles={VIN_A: object(), VIN_B: object()} if vehicles is None else vehicles
    )
    flow = VagConnectOptionsFlow(entry)
    hass = MagicMock()

    def _update(target, *, data):
        # like Home Assistant: the entry carries the new data at once
        target.data = data

    hass.config_entries.async_update_entry = MagicMock(side_effect=_update)
    hass.config_entries.async_entries = MagicMock(
        return_value=[entry, *(others or [])]
    )
    hass.config_entries.async_reload = MagicMock(return_value="reload-task")
    hass.async_create_task = MagicMock()
    flow.hass = hass
    registry = MagicMock()
    registry.devices = {d.id: d for d in (devices or [])}
    flow._test_registry = registry  # noqa: SLF001
    return flow


def _run(flow: VagConnectOptionsFlow, coro):
    with patch(
        "homeassistant.helpers.device_registry.async_get",
        return_value=flow._test_registry,  # noqa: SLF001
    ):
        return asyncio.run(coro)


def _keys(result: dict) -> set[str]:
    return {getattr(k, "schema", None) for k in result["data_schema"].schema}


def test_toggle_leads_into_substep() -> None:
    flow = _flow({CONF_SCAN_INTERVAL: 5}, [_device("d1")])
    result = _run(flow, flow.async_step_init(
        {CONF_SCAN_INTERVAL: 5, "link_obd_source": True}
    ))
    assert result["type"] == "form"
    assert result["step_id"] == "link_obd_source"


def test_no_device_gives_error_and_saves_nothing() -> None:
    flow = _flow({CONF_SCAN_INTERVAL: 5}, [])
    result = _run(flow, flow.async_step_link_obd_source(
        {"vehicle": VIN_A, "obd_device": "gone"}
    ))
    assert result["type"] == "form"
    assert result["errors"] == {"base": "no_obd_source"}
    flow.hass.config_entries.async_update_entry.assert_not_called()
    flow.hass.async_create_task.assert_not_called()


def test_valid_pick_writes_map_and_reloads() -> None:
    flow = _flow({CONF_SCAN_INTERVAL: 5, "other": 1}, [_device("d1")])
    with patch.object(flow, "async_create_entry", return_value={"type": "create_entry"}):
        _run(flow, flow.async_step_link_obd_source(
            {"vehicle": VIN_A, "obd_device": "d1"}
        ))
    new_data = flow.hass.config_entries.async_update_entry.call_args.kwargs["data"]
    assert new_data[CONF_DRIVEPULSE_LINKS] == {VIN_A: "d1"}
    assert new_data["other"] == 1
    flow.hass.async_create_task.assert_called_once()


def test_device_already_on_other_car_is_refused() -> None:
    flow = _flow(
        {CONF_SCAN_INTERVAL: 5, CONF_DRIVEPULSE_LINKS: {VIN_A: "d1"}},
        [_device("d1")],
    )
    result = _run(flow, flow.async_step_link_obd_source(
        {"vehicle": VIN_B, "obd_device": "d1"}
    ))
    assert result["errors"] == {"base": "obd_device_in_use"}
    flow.hass.config_entries.async_update_entry.assert_not_called()


def test_relinking_same_car_replaces_entry() -> None:
    flow = _flow(
        {CONF_SCAN_INTERVAL: 5, CONF_DRIVEPULSE_LINKS: {VIN_A: "d1", VIN_B: "d9"}},
        [_device("d1"), _device("d2")],
    )
    with patch.object(flow, "async_create_entry", return_value={"type": "create_entry"}):
        _run(flow, flow.async_step_link_obd_source(
            {"vehicle": VIN_A, "obd_device": "d2"}
        ))
    new_data = flow.hass.config_entries.async_update_entry.call_args.kwargs["data"]
    assert new_data[CONF_DRIVEPULSE_LINKS] == {VIN_A: "d2", VIN_B: "d9"}


def test_same_car_same_device_is_not_in_use() -> None:
    flow = _flow(
        {CONF_SCAN_INTERVAL: 5, CONF_DRIVEPULSE_LINKS: {VIN_A: "d1"}},
        [_device("d1")],
    )
    with patch.object(flow, "async_create_entry", return_value={"type": "create_entry"}):
        _run(flow, flow.async_step_link_obd_source(
            {"vehicle": VIN_A, "obd_device": "d1"}
        ))
    flow.hass.config_entries.async_update_entry.assert_called_once()


def test_remove_deletes_map_and_reloads() -> None:
    flow = _flow({CONF_SCAN_INTERVAL: 5, CONF_DRIVEPULSE_LINKS: {VIN_A: "d1"}})
    with patch.object(flow, "async_create_entry", return_value={"type": "create_entry"}):
        _run(flow, flow.async_step_init(
            {CONF_SCAN_INTERVAL: 5, "remove_obd_source": True}
        ))
    new_data = flow.hass.config_entries.async_update_entry.call_args.kwargs["data"]
    assert CONF_DRIVEPULSE_LINKS not in new_data
    flow.hass.async_create_task.assert_called_once()


def test_remove_switch_only_with_existing_map() -> None:
    without = _flow({CONF_SCAN_INTERVAL: 5}, [_device("d1")])
    keys = _keys(_run(without, without.async_step_init(None)))
    assert "link_obd_source" in keys
    assert "remove_obd_source" not in keys
    withmap = _flow(
        {CONF_SCAN_INTERVAL: 5, CONF_DRIVEPULSE_LINKS: {VIN_A: "d1"}},
        [_device("d1")],
    )
    keys = _keys(_run(withmap, withmap.async_step_init(None)))
    assert "link_obd_source" in keys
    assert "remove_obd_source" in keys


def test_link_switch_only_when_the_step_behind_it_can_be_completed() -> None:
    """Without a DrivePulse device or without a car the step is a dead end,
    and everything else changed in the same submit would be lost with it."""
    no_device = _flow({CONF_SCAN_INTERVAL: 5}, [])
    assert "link_obd_source" not in _keys(
        _run(no_device, no_device.async_step_init(None))
    )
    foreign = _flow({CONF_SCAN_INTERVAL: 5}, [_device("d1", domain="other")])
    assert "link_obd_source" not in _keys(
        _run(foreign, foreign.async_step_init(None))
    )
    no_car = _flow({CONF_SCAN_INTERVAL: 5}, [_device("d1")], vehicles={})
    assert "link_obd_source" not in _keys(
        _run(no_car, no_car.async_step_init(None))
    )
    # the remove switch does not depend on any of that
    stale = _flow({CONF_SCAN_INTERVAL: 5, CONF_DRIVEPULSE_LINKS: {VIN_A: "d1"}}, [])
    assert "remove_obd_source" in _keys(_run(stale, stale.async_step_init(None)))


@pytest.mark.parametrize("picked", ["d2", "", "  "])
def test_a_device_that_is_not_a_drivepulse_device_is_refused(picked: str) -> None:
    flow = _flow({CONF_SCAN_INTERVAL: 5}, [_device("d1")])
    result = _run(flow, flow.async_step_link_obd_source(
        {"vehicle": VIN_A, "obd_device": picked}
    ))
    assert result["errors"] == {"base": "no_obd_source"}
    flow.hass.config_entries.async_update_entry.assert_not_called()
    flow.hass.async_create_task.assert_not_called()


def test_a_device_linked_in_another_entry_is_refused() -> None:
    """Two entries would both take the same dongle's readings."""
    flow = _flow(
        {CONF_SCAN_INTERVAL: 5}, [_device("d1")],
        others=[_other_entry({"WVWZZZTESTFAKE009": "d1"})],
    )
    result = _run(flow, flow.async_step_link_obd_source(
        {"vehicle": VIN_A, "obd_device": "d1"}
    ))
    assert result["errors"] == {"base": "obd_device_in_use"}
    flow.hass.config_entries.async_update_entry.assert_not_called()


def test_control_another_entry_with_a_different_device_does_not_block() -> None:
    flow = _flow(
        {CONF_SCAN_INTERVAL: 5}, [_device("d1")],
        others=[_other_entry({"WVWZZZTESTFAKE009": "d7"}), _other_entry(None)],
    )
    with patch.object(flow, "async_create_entry", return_value={"type": "create_entry"}):
        _run(flow, flow.async_step_link_obd_source(
            {"vehicle": VIN_A, "obd_device": "d1"}
        ))
    assert flow._config_entry.data[CONF_DRIVEPULSE_LINKS] == {VIN_A: "d1"}


def test_remove_survives_a_sub_flow_ticked_in_the_same_submit() -> None:
    """The sub-flow returns early; the removal must not be lost with it, and
    neither switch may ride along in the options that wait for the sub-flow."""
    flow = _flow({CONF_SCAN_INTERVAL: 5, CONF_DRIVEPULSE_LINKS: {VIN_A: "d1"}})
    sub = AsyncMock(return_value={"type": "form", "step_id": "add_tibber"})
    with patch.object(flow, "async_step_add_tibber", sub):
        result = _run(flow, flow.async_step_init({
            CONF_SCAN_INTERVAL: 5,
            CONF_SUPPLEMENTARY_TIBBER: True,
            "remove_obd_source": True,
            "link_obd_source": True,
        }))
    assert result["step_id"] == "add_tibber"
    assert CONF_DRIVEPULSE_LINKS not in flow._config_entry.data
    flow.hass.async_create_task.assert_called_once()
    assert "remove_obd_source" not in flow._otib_pending_options
    assert "link_obd_source" not in flow._otib_pending_options


def test_remove_and_link_together_start_from_an_empty_map() -> None:
    flow = _flow(
        {CONF_SCAN_INTERVAL: 5, CONF_DRIVEPULSE_LINKS: {VIN_A: "d1"}},
        [_device("d1")],
    )
    result = _run(flow, flow.async_step_init({
        CONF_SCAN_INTERVAL: 5, "remove_obd_source": True, "link_obd_source": True,
    }))
    assert result["step_id"] == "link_obd_source"
    assert CONF_DRIVEPULSE_LINKS not in flow._config_entry.data
    # the device is free again, so it can go to the other car now
    with patch.object(flow, "async_create_entry", return_value={"type": "create_entry"}):
        _run(flow, flow.async_step_link_obd_source(
            {"vehicle": VIN_B, "obd_device": "d1"}
        ))
    assert flow._config_entry.data[CONF_DRIVEPULSE_LINKS] == {VIN_B: "d1"}


def test_link_with_a_channel_remove_switch_applies_the_removal_first() -> None:
    flow = _flow(
        {CONF_SCAN_INTERVAL: 5, CONF_SUPPLEMENTARY_TIBBER: True},
        [_device("d1")],
    )
    result = _run(flow, flow.async_step_init({
        CONF_SCAN_INTERVAL: 5,
        "remove_supplementary_tibber": True,
        "link_obd_source": True,
    }))
    assert result["step_id"] == "link_obd_source"
    assert CONF_SUPPLEMENTARY_TIBBER not in flow._config_entry.data
    assert flow._oobd_pending_options[CONF_SCAN_INTERVAL] == 5
    assert not [
        key for key in flow._oobd_pending_options
        if str(key).startswith("remove_") or key == "link_obd_source"
    ], "no switch may wait in the options that are saved after the step"


def test_remove_without_a_map_changes_nothing() -> None:
    flow = _flow({CONF_SCAN_INTERVAL: 5})
    with patch.object(flow, "async_create_entry", return_value={"type": "create_entry"}):
        _run(flow, flow.async_step_init(
            {CONF_SCAN_INTERVAL: 5, "remove_obd_source": True}
        ))
    flow.hass.config_entries.async_update_entry.assert_not_called()
    flow.hass.async_create_task.assert_not_called()


def test_switches_never_saved_as_options() -> None:
    flow = _flow({CONF_SCAN_INTERVAL: 5, CONF_DRIVEPULSE_LINKS: {VIN_A: "d1"}})
    captured: dict = {}

    def _capture(*, title, data):
        captured.update(data)
        return {"type": "create_entry"}

    with patch.object(flow, "async_create_entry", side_effect=_capture):
        _run(flow, flow.async_step_init({
            CONF_SCAN_INTERVAL: 5,
            "link_obd_source": False,
            "remove_obd_source": False,
        }))
    assert "link_obd_source" not in captured
    assert "remove_obd_source" not in captured
    flow2 = _flow({CONF_SCAN_INTERVAL: 5}, [_device("d1")])
    captured.clear()
    with patch.object(flow2, "async_create_entry", side_effect=_capture):
        _run(flow2, flow2.async_step_init({CONF_SCAN_INTERVAL: 5, "link_obd_source": True}))
        _run(flow2, flow2.async_step_link_obd_source(
            {"vehicle": VIN_A, "obd_device": "d1"}
        ))
    assert "link_obd_source" not in captured
    assert "vehicle" not in captured and "obd_device" not in captured


def test_strings_valid_json_and_complete() -> None:
    base = Path(__file__).parent.parent / "custom_components" / "vag_connect"
    for rel in ("strings.json", "translations/en.json"):
        opt = json.loads((base / rel).read_text(encoding="utf-8"))["options"]
        assert "link_obd_source" in opt["step"]["init"]["data"]
        assert "remove_obd_source" in opt["step"]["init"]["data"]
        step = opt["step"]["link_obd_source"]
        assert step["title"] and step["description"]
        assert "vehicle" in step["data"] and "obd_device" in step["data"]
        assert "no_obd_source" in opt["error"]
        assert "obd_device_in_use" in opt["error"]
