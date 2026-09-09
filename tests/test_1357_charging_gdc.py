# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#1357 root fix — the vw.de charging/maintenance reads carry the per-platform gdc.

Ra72xx's ID.3 read over vw.de returned SoC/range/odometer from the stale EU Data Act
portal, never from the live vw.de channel — even though his warning-lights read (which
DOES send ``gdc`` + ``resourceHost``) worked. The charging + maintenance reads were the
only live-status endpoints sent WITHOUT those params, so the WeConnect proxy returned no
body for his MEB car and every charging/odometer field fell back to the portal. The
other vw.de-reading integration sends ``?gdc=myvw-{gdc}-prod&resourceHost=myvw-vcf-prod``
on the same endpoints and gets the range. These tests pin that the URLs now carry the
gdc + live VCF host, and (B) that a supplementary connector's captured raw bodies now
reach the client so they surface in diagnostics.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock
from typing import Any

from custom_components.vag_connect.cariad._authproxy import (
    build_charging_url,
    build_maintenance_url,
)
from custom_components.vag_connect.cariad.api.base import CariadBaseClient
from custom_components.vag_connect.cariad.auth._website_authproxy import (
    WebsiteAuthProxyConnector,
)
from custom_components.vag_connect.cariad.models import VehicleData

VIN = "WVWZZZAUZ1234567"


# ── (A) URL recipe: gdc + live VCF host, matching warning-lights ───────────────

def test_charging_url_carries_gdc_and_vcf_host() -> None:
    url = build_charging_url(VIN, "myvw-wcar-prod")
    assert url.count("?") == 1
    assert "/vwag-weconnect/proxy/vehicles/%s/charging/status" % VIN in url
    assert "gdc=myvw-wcar-prod" in url
    assert "resourceHost=myvw-vcf-prod" in url


def test_maintenance_url_carries_gdc_and_vcf_host_in_vwde_realm() -> None:
    url = build_maintenance_url(VIN, "myvw-wcar-prod")
    assert url.count("?") == 1
    assert "/vw-de/proxy/vehicles/%s/maintenance/status" % VIN in url
    assert "gdc=myvw-wcar-prod" in url
    assert "resourceHost=myvw-vcf-prod" in url


def test_urls_default_to_weconnect_gdc_and_honour_mbb() -> None:
    assert "gdc=myvw-wcar-prod" in build_charging_url(VIN)
    assert "gdc=myvw-wcar-prod" in build_maintenance_url(VIN)
    assert "gdc=myvw-mbb-prod" in build_charging_url(VIN, "myvw-mbb-prod")
    assert "gdc=myvw-mbb-prod" in build_maintenance_url(VIN, "myvw-mbb-prod")


# ── (A) get_vehicle_data now issues the gdc'd charging + maintenance reads ──────

def _live_conn(backend: str | None = None) -> WebsiteAuthProxyConnector:
    c = WebsiteAuthProxyConnector.__new__(WebsiteAuthProxyConnector)
    c._vin_backend = {VIN: backend} if backend else {}
    # probes all off
    c.probe_position = False
    c._position_available = False
    c.probe_soh = False
    c._soh_available = False
    c.probe_measurements = False
    c._measurements_available = False
    c.probe_outcomes = {}
    c.last_raw_responses = {}
    # stub every dependency get_vehicle_data touches
    c._ensure_backend = AsyncMock(return_value=None)
    c.get_relations = AsyncMock(return_value=None)
    c.get_warning_lights = AsyncMock(return_value=None)
    c.get_last_lock_action = AsyncMock(return_value=None)
    c.get_relation_detail = AsyncMock(return_value=None)
    c.get_exterior_images = AsyncMock(return_value=[])
    c.get_master_data = AsyncMock(return_value=SimpleNamespace(
        model_name=None, model_year=None, exterior_color_text=None, engine=None))
    return c


def _run_and_capture_urls(c: WebsiteAuthProxyConnector) -> list[str]:
    urls: list[str] = []

    async def fake_get_json(url: str, **_kw: Any) -> None:
        urls.append(url)
        return None

    c._get_json = fake_get_json  # type: ignore[assignment]
    asyncio.run(c.get_vehicle_data(VIN))
    return urls


def test_get_vehicle_data_charging_read_now_sends_gdc() -> None:
    urls = _run_and_capture_urls(_live_conn())  # no backend → WeConnect default
    charging = [u for u in urls if "charging/status" in u]
    maint = [u for u in urls if "maintenance/status" in u]
    assert charging and "gdc=myvw-wcar-prod" in charging[0]
    assert "resourceHost=myvw-vcf-prod" in charging[0]
    assert maint and "gdc=myvw-wcar-prod" in maint[0]
    assert "resourceHost=myvw-vcf-prod" in maint[0]


def test_mbb_car_gets_the_mbb_gdc_on_charging() -> None:
    urls = _run_and_capture_urls(_live_conn(backend="MBB_ODP"))
    charging = [u for u in urls if "charging/status" in u]
    assert charging and "gdc=myvw-mbb-prod" in charging[0]


# ── (B) supplementary connector's raw bodies now reach the client (→ diagnostics)

def test_read_authproxy_merges_raw_bodies_up_to_client() -> None:
    """The connector captures raw vw.de bodies VIN-stripped; diagnostics reads them
    off the CLIENT. Confirm _read_authproxy copies them up — even when the read
    itself fail-softs — so a portal-primary reporter's diagnostics carry the vw.de
    charging / probe bodies instead of nothing."""
    client = CariadBaseClient.__new__(CariadBaseClient)
    client.probe_outcomes = {}
    client.last_raw_responses = {}

    connector = WebsiteAuthProxyConnector.__new__(WebsiteAuthProxyConnector)
    connector.probe_outcomes = {}
    connector.last_raw_responses = {
        "vwde:charging/status": {"batteryStatus": {"currentSOC_pct": 77}},
        "vwde:selectivestatus": {"measurements": {"rangeStatus": {"value": {}}}},
    }
    # the read itself raises → fail-soft to None, but the raw bodies must still merge
    connector.get_vehicle_data = AsyncMock(side_effect=RuntimeError("boom"))

    res = asyncio.run(client._read_authproxy(connector, VIN))
    assert res is None
    assert client.last_raw_responses["vwde:charging/status"] == {
        "batteryStatus": {"currentSOC_pct": 77}}
    assert "vwde:selectivestatus" in client.last_raw_responses


def test_read_authproxy_raw_merge_is_noop_when_connector_has_none() -> None:
    client = CariadBaseClient.__new__(CariadBaseClient)
    client.probe_outcomes = {}
    client.last_raw_responses = {"scout:existing": {"a": 1}}
    connector = WebsiteAuthProxyConnector.__new__(WebsiteAuthProxyConnector)
    connector.probe_outcomes = {}
    connector.last_raw_responses = {}
    connector.get_vehicle_data = AsyncMock(return_value=VehicleData(vin=VIN))
    asyncio.run(client._read_authproxy(connector, VIN))
    # untouched
    assert client.last_raw_responses == {"scout:existing": {"a": 1}}
