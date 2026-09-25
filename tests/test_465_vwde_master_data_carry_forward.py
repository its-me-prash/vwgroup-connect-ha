# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#465 (toglo) — vw.de STATIC master data survives a walled / omitted poll.

toglo runs a portal-primary VW (EU Data Act primary + supplementary vw.de) whose
live vw.de reads are walled per-car. Two gaps this pins:

1. ``vehicle_cache.reconcile`` never carried the vw.de-ONLY static master data
   (model / year / colour / engine power / plate / nickname / render images), so
   a supplementary poll that lacked them blanked those attributes to "unknown"
   with no last-known fallback — even though they are immutable per car.
2. ``WebsiteAuthProxyConnector.get_vehicle_data`` aborted the whole poll the
   moment a CORE read (relations/charging/maintenance) hit a per-car wall, so the
   INDEPENDENT tail reads (exterior renders + model master data) — which may still
   answer — never ran, and nothing named WHICH read was walled. The tail now runs
   best-effort on a walled poll, the wall is recorded (probe_outcomes + one INFO
   line, host+path masked), and the core exception is re-raised so the caller's
   refresh+retry is unchanged.
"""
from __future__ import annotations

import logging
from typing import Any

import pytest

from custom_components.vag_connect.cariad.auth._website_authproxy import (
    WebsiteAuthProxyConnector,
)
from custom_components.vag_connect.cariad.exceptions import AuthenticationError
from custom_components.vag_connect.cariad.vehicle_cache import (
    STATIC_MASTER_FIELDS,
    reconcile,
)

VIN = "WVGZZZ5NZPM465017"


# ── (A) reconcile carry-forward of the immutable vw.de master data ──────────────

class TestStaticMasterCarryForward:
    def test_static_fields_survive_an_empty_supplementary_poll(self) -> None:
        prev = {
            "model": "Tayron",
            "model_year": 2026,
            "exterior_color": "Deep Black",
            "engine_power": "110 kW (150 PS)",
            "license_plate": "AG 123456",
            "vehicle_nickname": "Toglo's Tayron",
            "image_urls": {"side_left": "https://vw.example/1.png"},
        }
        # a poll with none of the vw.de supplement present
        fresh = {"odometer_km": 12_345}
        merged, _notes = reconcile(prev, fresh)
        for field in STATIC_MASTER_FIELDS:
            assert merged[field] == prev[field], field

    def test_image_urls_empty_dict_keeps_previous(self) -> None:
        # image_urls defaults to {} (models.py __post_init__), NOT None — a bare
        # ``is None`` carry would miss it, so the truthiness test is load-bearing.
        prev = {"image_urls": {"front": "https://vw.example/f.png"}}
        merged, _ = reconcile(prev, {"image_urls": {}})
        assert merged["image_urls"] == {"front": "https://vw.example/f.png"}

    def test_empty_string_and_empty_list_are_held(self) -> None:
        prev = {"model": "Tayron", "exterior_color": "Deep Black"}
        merged, _ = reconcile(prev, {"model": "", "exterior_color": []})
        assert merged["model"] == "Tayron"
        assert merged["exterior_color"] == "Deep Black"

    def test_fresh_truthy_value_always_wins(self) -> None:
        prev = {"model": "Tayron", "image_urls": {"a": "https://vw.example/a.png"}}
        fresh = {"model": "Tiguan", "image_urls": {"b": "https://vw.example/b.png"}}
        merged, _ = reconcile(prev, fresh)
        assert merged["model"] == "Tiguan"
        assert merged["image_urls"] == {"b": "https://vw.example/b.png"}

    def test_no_previous_returns_fresh_untouched(self) -> None:
        fresh = {"model": "Tayron"}
        merged, notes = reconcile(None, fresh)
        assert merged == fresh
        assert notes == []


# ── (B) authproxy: a walled core read still runs the tail and returns its data ──

_RELATIONS_TEXT = '{"relations":[{"vin":"%s","role":"PRIMARY_USER"}]}' % VIN
_IMAGES_JSON = {"images": [
    {"url": "https://vw.example/side.png", "angle": "Left", "viewDirection": "Side"},
]}
_DETAILS_JSON = {
    "modelName": "Tayron",
    "modelYear": "2026",
    "engine": "110 kW (150 PS)",
    "exteriorColorText": "Deep Black",
}
_DATA_JSON = {"vin": VIN, "modelName": "Tayron", "exteriorColor": "2T2T"}


class _FakeResp:
    def __init__(self, url: str, *, status: int = 200, text: str = "",
                 json_data: Any = None) -> None:
        self.url = url
        self.status = status
        self._text = text
        self._json = json_data

    async def __aenter__(self) -> "_FakeResp":
        return self

    async def __aexit__(self, *_a: Any) -> bool:
        return False

    async def text(self, errors: str | None = None) -> str:
        return self._text

    async def json(self, content_type: Any = None) -> Any:
        return self._json


class _ChargingWalledSession:
    """relations OK, charging 401 (per-car wall), tail endpoints answer."""

    def __init__(self) -> None:
        self.gets: list[str] = []

    def get(self, url: str, **kw: Any) -> _FakeResp:
        self.gets.append(url)
        if "charging/status" in url:
            return _FakeResp(url, status=401)
        if "vehicleimages/exterior" in url:
            return _FakeResp(url, json_data=_IMAGES_JSON)
        if "/details/" in url:
            return _FakeResp(url, json_data=_DETAILS_JSON)
        if "/data/" in url:
            return _FakeResp(url, json_data=_DATA_JSON)
        if "relations" in url:
            return _FakeResp(url, text=_RELATIONS_TEXT)
        if "maintenance/status" in url:
            return _FakeResp(url, status=401)
        # Any other live probe just yields no data (no wall).
        return _FakeResp(url, status=404)

    def post(self, url: str, **kw: Any) -> _FakeResp:  # pragma: no cover
        raise AssertionError("get_vehicle_data must not POST")


@pytest.mark.asyncio
async def test_walled_core_read_returns_tail_data_instead_of_reraising(
    caplog: pytest.LogCaptureFixture,
) -> None:
    session = _ChargingWalledSession()
    conn = WebsiteAuthProxyConnector(session, "u@x.z", "pw")  # type: ignore[arg-type]
    with caplog.at_level(
        logging.INFO,
        "custom_components.vag_connect.cariad.auth._website_authproxy",
    ):
        d = await conn.get_vehicle_data(VIN)

    # v4.7.12+ — the walled poll returns the PARTIAL snapshot the tail built
    # (static fields only); 4.7.11 re-raised here and threw it away.
    assert d.image_urls == {"side_left": "https://vw.example/side.png"}
    assert d.model == "Tayron" and d.model_year == 2026
    assert d.exterior_color == "Deep Black"
    assert d.battery_soc is None  # live fields stay with the primary channel

    # the tail was attempted despite the walled charging read
    assert any("vehicleimages/exterior" in u for u in session.gets)
    assert any("/details/" in u for u in session.gets)

    # the wall is attributable in diagnostics: status-only, keyed by read name
    assert conn.probe_outcomes.get("vwde_core_read:charging") == "401"
    # #1 — maintenance is attempted too and records its own wall
    assert conn.probe_outcomes.get("vwde_core_read:maintenance") == "401"
    # the tail reads record their own outcome so diagnostics can tell a refused
    # render/master-data read apart from one that answered with nothing
    assert conn.probe_outcomes.get("vwde_images") == "200"
    assert conn.probe_outcomes.get("vwde_master_details") == "200"

    # exactly one INFO line names the walled read; no VIN / query leaked
    info = [r for r in caplog.records if r.levelno == logging.INFO
            and "walled" in r.getMessage()]
    # #1 — both live core reads (charging + maintenance) are now attempted
    # independently, so each walled read logs its own line.
    assert len(info) == 2
    msgs = [r.getMessage() for r in info]
    assert any("charging" in m for m in msgs)
    assert any("maintenance" in m for m in msgs)
    for m in msgs:
        assert VIN not in m        # only the last-6 mask may appear
        assert "?" not in m        # never the query string


@pytest.mark.asyncio
async def test_walled_core_read_with_empty_tail_still_reraises() -> None:
    """Session genuinely dead: core read AND tail fail → re-raise so the caller's
    refresh + retry runs (unchanged behaviour for the dead-session case)."""

    class _AllWalledSession(_ChargingWalledSession):
        def get(self, url: str, **kw: Any) -> _FakeResp:
            self.gets.append(url)
            if "relations" in url:
                return _FakeResp(url, text=_RELATIONS_TEXT)
            return _FakeResp(url, status=401)

    session = _AllWalledSession()
    conn = WebsiteAuthProxyConnector(session, "u@x.z", "pw")  # type: ignore[arg-type]
    with pytest.raises(AuthenticationError):
        await conn.get_vehicle_data(VIN)
    assert conn.probe_outcomes.get("vwde_core_read:charging") == "401"


@pytest.mark.asyncio
async def test_clean_poll_is_unaffected(caplog: pytest.LogCaptureFixture) -> None:
    """No wall → no diagnostic INFO line, no captured core exception."""

    class _OkSession:
        def __init__(self) -> None:
            self.gets: list[str] = []

        def get(self, url: str, **kw: Any) -> _FakeResp:
            self.gets.append(url)
            if "charging/status" in url:
                return _FakeResp(url, json_data={"data": {
                    "batteryStatus": {"currentSOC_pct": 55},
                    "chargingStatus": {"chargingState": "readyForCharging"},
                }})
            if "maintenance/status" in url:
                return _FakeResp(url, json_data={"data": {
                    "maintenanceStatus": {"value": {"mileage_km": 100}}}})
            if "vehicleimages/exterior" in url:
                return _FakeResp(url, json_data=_IMAGES_JSON)
            if "/details/" in url:
                return _FakeResp(url, json_data=_DETAILS_JSON)
            if "/data/" in url:
                return _FakeResp(url, json_data=_DATA_JSON)
            if "relations" in url:
                return _FakeResp(url, text=_RELATIONS_TEXT)
            return _FakeResp(url, status=404)

    session = _OkSession()
    conn = WebsiteAuthProxyConnector(session, "u@x.z", "pw")  # type: ignore[arg-type]
    with caplog.at_level(
        logging.INFO,
        "custom_components.vag_connect.cariad.auth._website_authproxy",
    ):
        d = await conn.get_vehicle_data(VIN)

    assert d.connection_state == "online"
    assert d.model == "Tayron"
    assert d.image_urls  # renders wired through the tail
    assert not any("vwde_core_read:" in k for k in conn.probe_outcomes)
    assert not any("walled" in r.getMessage() for r in caplog.records)
