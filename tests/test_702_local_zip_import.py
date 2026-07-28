# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#702 — import a EU Data Act export ZIP downloaded from the portal by hand.

A car that is not enrolled in the EU Data Act portal has no export for the
connector to fetch, so ``import_historical_export`` brings nothing back. The new
``import_export_file`` service lets the user point the connector at the ZIP they
downloaded from the VW data portal themselves: the SAME offline parse the portal
path runs, the SAME gap-fill-only merge (live telemetry is never clobbered), no
portal session needed.
"""
from __future__ import annotations

import io
import json
import os
import threading
import zipfile
from unittest.mock import MagicMock

import pytest

from custom_components.vag_connect.cariad.auth._eu_data_act import parse_export_zip
from custom_components.vag_connect.coordinator import VagConnectCoordinator


def _zip_bytes(payload: dict) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("dataset.json", json.dumps(payload))
    return buf.getvalue()


# Nested payload like a real portal dataset; flattens to
# energy_contents.current_energy_content.physical_value (0.1-kWh units → /10).
_REAL_PAYLOAD = {
    "energy_contents": {
        "current_energy_content": {"physical_value": "461", "value_type": "valid"},
        "maximal_energy_content": {"physical_value": "756", "value_type": "valid"},
    }
}


# ── parse_export_zip: the offline parse ──────────────────────────────────────

def test_parse_export_zip_maps_real_fields() -> None:
    d = parse_export_zip(_zip_bytes(_REAL_PAYLOAD), vin="V", name="export.zip")
    assert d.no_data is False
    assert d.battery_available_kwh == 46.1
    assert d.battery_cap_kwh == 75.6


def test_parse_export_zip_non_zip_is_no_data() -> None:
    d = parse_export_zip(b"this is not a zip", vin="V", name="x.zip")
    assert d.no_data is True


def test_parse_export_zip_zip_without_json_is_no_data() -> None:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("readme.txt", "no dataset here")
    d = parse_export_zip(buf.getvalue(), vin="V", name="x.zip")
    assert d.no_data is True


# ── coordinator import: gap-fill + path guard ────────────────────────────────

def _coord(tmp_path, current, allowed: bool = True) -> VagConnectCoordinator:
    c = VagConnectCoordinator.__new__(VagConnectCoordinator)
    c.vehicles = {"V": current} if current is not None else {}
    c._vehicles_lock = threading.Lock()
    c.pushed = []  # type: ignore[attr-defined]
    c.async_set_updated_data = lambda data: c.pushed.append(data)  # type: ignore[assignment]
    hass = MagicMock()
    hass.config.path = lambda *p: os.path.join(str(tmp_path), *p)
    hass.config.is_allowed_path = lambda _p: allowed

    async def _exec(func, *args):
        return func(*args)

    hass.async_add_executor_job = _exec
    c.hass = hass
    return c


@pytest.mark.asyncio
async def test_import_file_fills_a_gap(tmp_path) -> None:
    (tmp_path / "export.zip").write_bytes(_zip_bytes(_REAL_PAYLOAD))
    c = _coord(tmp_path, {"soc": 80})  # no battery_available_kwh yet
    ok = await c.async_import_export_file("V", "export.zip")  # relative → config dir
    assert ok is True
    assert c.vehicles["V"]["battery_available_kwh"] == 46.1
    assert c.pushed  # data was pushed to entities


@pytest.mark.asyncio
async def test_import_file_never_clobbers_live(tmp_path) -> None:
    (tmp_path / "export.zip").write_bytes(_zip_bytes(_REAL_PAYLOAD))
    c = _coord(tmp_path, {"battery_available_kwh": 99.9})  # live value present
    await c.async_import_export_file("V", "export.zip")
    assert c.vehicles["V"]["battery_available_kwh"] == 99.9  # preserved


@pytest.mark.asyncio
async def test_import_file_portal_only_car_takes_snapshot(tmp_path) -> None:
    (tmp_path / "export.zip").write_bytes(_zip_bytes(_REAL_PAYLOAD))
    c = _coord(tmp_path, None)  # nothing live for this car yet
    assert await c.async_import_export_file("V", "export.zip") is True
    assert c.vehicles["V"]["battery_available_kwh"] == 46.1


@pytest.mark.asyncio
async def test_import_file_not_allowed_path_raises(tmp_path) -> None:
    from homeassistant.exceptions import ServiceValidationError

    (tmp_path / "export.zip").write_bytes(_zip_bytes(_REAL_PAYLOAD))
    c = _coord(tmp_path, {"soc": 80}, allowed=False)
    with pytest.raises(ServiceValidationError):
        await c.async_import_export_file("V", "export.zip")
    assert c.pushed == []


@pytest.mark.asyncio
async def test_import_file_missing_raises(tmp_path) -> None:
    from homeassistant.exceptions import ServiceValidationError

    c = _coord(tmp_path, {"soc": 80})
    with pytest.raises(ServiceValidationError):
        await c.async_import_export_file("V", "nope.zip")


@pytest.mark.asyncio
async def test_import_file_wrong_content_raises(tmp_path) -> None:
    from homeassistant.exceptions import ServiceValidationError

    (tmp_path / "bad.zip").write_bytes(b"not a zip at all")
    c = _coord(tmp_path, {"soc": 80})
    with pytest.raises(ServiceValidationError):
        await c.async_import_export_file("V", "bad.zip")
    assert c.pushed == []


def test_service_registered_and_documented() -> None:
    import pathlib

    base = pathlib.Path(__file__).resolve().parents[1] / "custom_components/vag_connect"
    src = (base / "__init__.py").read_text(encoding="utf-8")
    assert '"import_export_file"' in src
    assert "async_import_export_file" in src
    yaml = (base / "services.yaml").read_text(encoding="utf-8")
    assert "import_export_file:" in yaml
