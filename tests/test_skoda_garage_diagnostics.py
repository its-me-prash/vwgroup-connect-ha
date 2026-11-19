# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Škoda garage document → three read-only diagnostics (MyŠkoda 8.18.0).

``GET api/v2/garage/vehicles/{vin}`` returns ``VehicleDto`` (cz.myskoda.api.
bff_garage.v2). The integration already fetches it for the capability gate, but
dropped three fields the app reads:

* ``sunset2g3gImpact`` — whether the car's 3G modem is affected by the 2G/3G
  network shutdown. The app maps seven values (``OCU_3G_NOT_UPGRADABLE`` …) in
  ``uk0/b.a(VehicleDto)``; surfaced verbatim as a diagnostic string sensor.
* ``capabilities[].statuses`` + ``serviceExpiration`` — why a service is
  restricted (``LICENSE_EXPIRED``, ``INSUFFICIENT_SPIN``, ``WORKSHOP_MODE`` …) and
  when its licence ends. Surfaced through the existing ``connected_services``
  attribute of the ``capabilities_count`` sensor. Display only: the capability
  gate stays permissive (never hide a control on a status).
* ``workshopModeEnabled`` — diagnostic binary sensor.
"""
from __future__ import annotations

import asyncio
import json
import threading
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

from homeassistant.const import EntityCategory

from custom_components.vag_connect.cariad.api.skoda import SkodaClient
from custom_components.vag_connect.cariad.models import VehicleData
from custom_components.vag_connect.coordinator import (
    VagConnectCoordinator,
    _skoda_garage_extras,
)

VIN = "TMBJJ7NX0PY000001"
_GARAGE = f"/api/v2/garage/vehicles/{VIN}"
_PKG = Path(__file__).resolve().parents[1] / "custom_components" / "vag_connect"


def _doc(**over: Any) -> dict[str, Any]:
    doc: dict[str, Any] = {
        "vin": VIN,
        "workshopModeEnabled": False,
        "state": "ACTIVATED",
        "devicePlatform": "MBB_ODP",
        "sunset2g3gImpact": "OCU_3G_NOT_UPGRADABLE",
        "capabilities": {
            "capabilities": [
                {"id": "CHARGING", "statuses": [],
                 "serviceExpiration": "2031-04-30T00:00:00Z"},
                {"id": "AUXILIARY_HEATING", "statuses": ["LICENSE_EXPIRED"],
                 "serviceExpiration": "2025-01-31T00:00:00Z"},
                {"id": "HONK_AND_FLASH", "statuses": []},
            ],
        },
    }
    doc.update(over)
    return doc


class _Backend:
    def __init__(self, doc: Any) -> None:
        self.doc = doc
        self.calls: list[str] = []

    async def get(self, url: str, **_kw: Any) -> Any:
        self.calls.append(url)
        return self.doc if _GARAGE in url else {}


def _caps(doc: Any) -> dict[str, Any]:
    c = SkodaClient(MagicMock(), "u@t.de", "pw")
    c._get = _Backend(doc).get  # type: ignore[method-assign]
    return asyncio.run(c.get_capabilities(VIN))


# ── client: get_capabilities ─────────────────────────────────────────────────


def test_gate_entries_keep_id_and_statuses() -> None:
    out = _caps(_doc())
    ids = [e["id"] for e in out["capabilities"]]
    assert ids == ["CHARGING", "AUXILIARY_HEATING", "HONK_AND_FLASH"]
    assert out["capabilities"][1]["statuses"] == ["LICENSE_EXPIRED"]
    # The gate keys on these two; no synthetic ``active`` flag appears.
    assert all("active" not in e for e in out["capabilities"])


def test_service_expiration_rides_on_the_entry() -> None:
    out = _caps(_doc())
    assert out["capabilities"][0]["serviceExpiration"] == "2031-04-30T00:00:00Z"
    assert "serviceExpiration" not in out["capabilities"][2]


def test_workshop_mode_and_sunset_are_returned() -> None:
    out = _caps(_doc(workshopModeEnabled=True))
    assert out["workshopModeEnabled"] is True
    assert out["sunset2g3gImpact"] == "OCU_3G_NOT_UPGRADABLE"


def test_false_workshop_mode_is_kept_not_dropped() -> None:
    assert _caps(_doc())["workshopModeEnabled"] is False


def test_wrong_types_and_blank_values_are_left_out() -> None:
    out = _caps(_doc(workshopModeEnabled="true", sunset2g3gImpact="  "))
    assert "workshopModeEnabled" not in out
    assert "sunset2g3gImpact" not in out


def test_missing_capability_list_still_returns_the_extras() -> None:
    # A car whose document carries no capability block still has a workshop flag.
    out = _caps(_doc(capabilities=None, workshopModeEnabled=True))
    assert out.get("capabilities") in (None, [])
    assert out["workshopModeEnabled"] is True


def test_non_dict_document_returns_empty() -> None:
    assert _caps(["not", "a", "dict"]) == {}


# ── coordinator helper ───────────────────────────────────────────────────────


def test_extras_map_onto_vehicle_keys() -> None:
    out = _skoda_garage_extras(_caps(_doc(workshopModeEnabled=True)))
    assert out["workshop_mode"] is True
    assert out["connectivity_sunset_impact"] == "OCU_3G_NOT_UPGRADABLE"
    assert out["capabilities_count"] == 3


def test_connected_services_list_restricted_first_with_status_list() -> None:
    rows = _skoda_garage_extras(_caps(_doc()))["connected_services"]
    assert rows[0] == {
        "id": "AUXILIARY_HEATING",
        "expires_at": "2025-01-31T00:00:00Z",
        "status": ["LICENSE_EXPIRED"],
    }
    assert {"id": "CHARGING", "expires_at": "2031-04-30T00:00:00Z",
            "status": None} in rows
    assert {"id": "HONK_AND_FLASH", "expires_at": None, "status": None} in rows


def test_connected_services_capped_at_40_keeping_restricted_rows() -> None:
    caps = [{"id": f"CAP_{i:03d}", "statuses": []} for i in range(60)]
    caps.append({"id": "TRAILER", "statuses": ["WORKSHOP_MODE"]})
    rows = _skoda_garage_extras({"capabilities": caps})["connected_services"]
    assert len(rows) == 40
    assert rows[0]["id"] == "TRAILER"


def test_no_extras_from_garbage() -> None:
    assert _skoda_garage_extras(None) == {}
    assert _skoda_garage_extras({"capabilities": "x"}) == {}


def test_false_workshop_mode_survives_the_helper() -> None:
    assert _skoda_garage_extras({"workshopModeEnabled": False}) == {
        "workshop_mode": False,
    }


# ── coordinator._enrich ──────────────────────────────────────────────────────


def _coord(brand: str, caps: dict[str, Any] | None) -> VagConnectCoordinator:
    coord = VagConnectCoordinator.__new__(VagConnectCoordinator)
    coord.hass = MagicMock()
    coord.hass.async_add_executor_job = AsyncMock(return_value=None)
    coord.entry = MagicMock()
    coord.entry.data = {"brand": brand, "username": "t@t.com", "password": "x",
                        "spin": "", "update_interval": 300}
    coord._vehicles_lock = threading.Lock()
    coord._cariad_client = MagicMock()
    coord._cariad_client._image_data = {}
    coord.vehicle_static_info = {}
    coord.vehicle_capabilities = {VIN: caps} if caps is not None else {}
    coord._was_available = True
    coord.data = None
    coord.refresh_static_info = AsyncMock()  # type: ignore[method-assign]
    coord.refresh_capabilities = AsyncMock()  # type: ignore[method-assign]
    return coord


def _enrich(coord: VagConnectCoordinator, data: dict[str, Any]) -> dict[str, Any]:
    data.setdefault("latitude", None)
    data.setdefault("longitude", None)
    return asyncio.run(coord._enrich(data))


def test_enrich_surfaces_the_three_diagnostics_for_skoda() -> None:
    coord = _coord("skoda", _caps(_doc(workshopModeEnabled=True)))
    out = _enrich(coord, {"vin": VIN})
    assert out["workshop_mode"] is True
    assert out["connectivity_sunset_impact"] == "OCU_3G_NOT_UPGRADABLE"
    assert out["capabilities_count"] == 3
    assert out["connected_services"][0]["status"] == ["LICENSE_EXPIRED"]


def test_enrich_keeps_values_a_client_already_set() -> None:
    coord = _coord("skoda", _caps(_doc()))
    out = _enrich(coord, {"vin": VIN, "capabilities_count": 7,
                          "connected_services": [{"id": "X"}]})
    assert out["capabilities_count"] == 7
    assert out["connected_services"] == [{"id": "X"}]


def test_enrich_leaves_other_brands_alone() -> None:
    # SEAT/CUPRA also cache a capability list; their own parser owns these keys.
    coord = _coord("cupra", _caps(_doc(workshopModeEnabled=True)))
    out = _enrich(coord, {"vin": VIN})
    assert out.get("workshop_mode") is None
    assert out.get("connectivity_sunset_impact") is None
    assert out.get("capabilities_count") is None


def test_enrich_without_cached_document_adds_nothing() -> None:
    out = _enrich(_coord("skoda", None), {"vin": VIN})
    assert out.get("workshop_mode") is None
    assert out.get("connectivity_sunset_impact") is None


def test_enrich_refreshes_the_garage_document_lazily_for_skoda_only() -> None:
    sk = _coord("skoda", None)
    _enrich(sk, {"vin": VIN})
    sk.refresh_capabilities.assert_awaited_once_with(VIN)
    au = _coord("audi", None)
    _enrich(au, {"vin": VIN})
    au.refresh_capabilities.assert_not_awaited()


# ── coordinator.refresh_capabilities: an empty answer keeps the last document ─


def _refresh(previous: dict[str, Any] | None, answer: Any) -> VagConnectCoordinator:
    coord = VagConnectCoordinator.__new__(VagConnectCoordinator)
    coord.entry = MagicMock()
    coord.entry.data = {"brand": "skoda"}
    coord._cariad_client = MagicMock()
    coord._cariad_client._tokens = SimpleNamespace(strategy="")
    if isinstance(answer, Exception):
        coord._cariad_client.get_capabilities = AsyncMock(side_effect=answer)
    else:
        coord._cariad_client.get_capabilities = AsyncMock(return_value=answer)
    coord.vehicle_capabilities = {VIN: previous} if previous is not None else {}
    coord._capabilities_fetched_at = {}
    asyncio.run(coord.refresh_capabilities(VIN, force=True))
    return coord


def test_empty_answer_keeps_the_document_already_held() -> None:
    good = _caps(_doc(workshopModeEnabled=True))
    coord = _refresh(good, {})
    assert coord.vehicle_capabilities[VIN] is good
    # The next try waits for the TTL instead of running on every poll.
    assert VIN in coord._capabilities_fetched_at


def test_empty_answer_is_stored_when_nothing_was_held() -> None:
    assert _refresh(None, {}).vehicle_capabilities[VIN] == {}


def test_a_failed_fetch_keeps_the_document_and_waits_for_the_ttl() -> None:
    good = _caps(_doc(workshopModeEnabled=True))
    coord = _refresh(good, RuntimeError("HTTP 503"))
    assert coord.vehicle_capabilities[VIN] is good
    assert coord.is_capabilities_cache_fresh(VIN) is True
    # A second, non-forced refresh inside the TTL must not call the backend again.
    asyncio.run(coord.refresh_capabilities(VIN))
    assert coord._cariad_client.get_capabilities.await_count == 1


def test_a_real_answer_replaces_the_old_document() -> None:
    new = _caps(_doc(workshopModeEnabled=False))
    coord = _refresh(_caps(_doc(workshopModeEnabled=True)), new)
    assert coord.vehicle_capabilities[VIN]["workshopModeEnabled"] is False


# ── entities ─────────────────────────────────────────────────────────────────


def test_vehicle_data_fields_default_to_none() -> None:
    d = VehicleData(vin=VIN)
    assert d.workshop_mode is None
    assert d.connectivity_sunset_impact is None


def test_workshop_mode_binary_sensor_is_diagnostic_and_data_gated() -> None:
    from custom_components.vag_connect import binary_sensor as bs

    desc = next(d for d in bs.BINARY_DESCRIPTIONS if d.key == "workshop_mode")
    assert desc.data_key == "workshop_mode"
    assert desc.translation_key == "workshop_mode"
    assert desc.entity_category is EntityCategory.DIAGNOSTIC
    assert "workshop_mode" in bs._DATA_PRESENT_REQUIRED


def test_sunset_sensor_is_a_plain_string_and_data_gated() -> None:
    from custom_components.vag_connect import sensor as sn

    desc = next(d for d in sn.SENSOR_DESCRIPTIONS
                if d.key == "connectivity_sunset_impact")
    assert desc.data_key == "connectivity_sunset_impact"
    assert desc.entity_category is EntityCategory.DIAGNOSTIC
    # Verbatim string, like readiness_software_update_status (#1333): an ENUM
    # would drop a value the app adds later.
    assert desc.device_class is None
    assert not getattr(desc, "options", None)
    assert "connectivity_sunset_impact" in sn._DATA_PRESENT_REQUIRED


def test_entity_names_exist_in_strings_and_every_translation() -> None:
    files = [_PKG / "strings.json", *sorted((_PKG / "translations").glob("*.json"))]
    assert len(files) == 13
    for f in files:
        ent = json.loads(f.read_text(encoding="utf-8"))["entity"]
        assert ent["binary_sensor"]["workshop_mode"]["name"], f.name
        assert ent["sensor"]["connectivity_sunset_impact"]["name"], f.name


def test_status_list_reaches_the_capabilities_count_attribute() -> None:
    from custom_components.vag_connect.sensor import VagConnectSensor

    rows = _skoda_garage_extras(_caps(_doc()))["connected_services"]
    sensor = VagConnectSensor.__new__(VagConnectSensor)
    sensor.entity_description = MagicMock()
    sensor.entity_description.key = "capabilities_count"
    sensor._vin = VIN
    sensor.coordinator = SimpleNamespace(
        data={VIN: {"capabilities_count": 3, "connected_services": rows}})
    attrs = sensor._key_platform_attributes()
    assert attrs["connected_services"][0]["status"] == ["LICENSE_EXPIRED"]
