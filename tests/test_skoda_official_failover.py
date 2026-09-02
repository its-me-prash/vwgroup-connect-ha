# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Škoda official public API — active live source AND hard-failure failover.

The official public API contributes on TWO paths, both rate-safe (20 req/hour/key):
- ACTIVE live source: on a healthy poll, ``_merge_official_live`` queries the
  manufacturer API and merges its readings into the primary payload as an
  authoritative live source (Prash: update existing entities live, not failover-only).
- FAILOVER: when the primary channel HARD-fails, ``_revive_after_hard_failure``
  falls back to the official API as a last resort.

Both go through the SAME rate guard (``_official_read_rate_safe``), and the official
channel is deliberately kept OUT of ``supplementary_readers`` (the rate-unsafe
continuous-merge path) — its active read is the dedicated, budget-gated one instead.
"""
from __future__ import annotations

import re
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.vag_connect.cariad.api.skoda import SkodaClient
from custom_components.vag_connect.cariad.api.skoda_official import SkodaOfficialClient
from custom_components.vag_connect.cariad.models import VehicleData
from custom_components.vag_connect.coordinator import VagConnectCoordinator


def _skoda_client() -> SkodaClient:
    c = SkodaClient.__new__(SkodaClient)
    c._session = object()
    c._spin = "1234"
    c._supplementary_authproxy = None
    c._supplementary_eu_portal = None
    c._supplementary_tibber = None
    c._supplementary_official = None
    return c


def test_arm_supplementary_official_creates_and_disarms():
    c = _skoda_client()
    c.arm_supplementary_official("key-abc")
    assert isinstance(c._supplementary_official, SkodaOfficialClient)
    # an empty key disarms it
    c.arm_supplementary_official("")
    assert c._supplementary_official is None


@pytest.mark.asyncio
async def test_official_failover_read_delegates_and_failsoft():
    c = _skoda_client()
    # not armed → None
    assert await c.official_failover_read("V") is None
    # armed → delegates to the official client's get_status
    c._supplementary_official = MagicMock()
    c._supplementary_official.get_status = AsyncMock(
        return_value=VehicleData(vin="V", battery_soc=55)
    )
    d = await c.official_failover_read("V")
    assert d is not None and d.battery_soc == 55
    # any error → None (a failover must never itself sink the poll)
    c._supplementary_official.get_status = AsyncMock(side_effect=RuntimeError("boom"))
    assert await c.official_failover_read("V") is None


def test_official_stays_out_of_continuous_supplementary_readers():
    """The 20/h/key rate limit means the official API must NEVER go through the
    rate-unsafe continuous-merge path (``supplementary_readers``, consulted every
    poll with no budget guard). Its active read happens via the dedicated,
    budget-gated ``_merge_official_live`` instead — so even when armed it must not
    appear in supplementary_readers."""
    c = _skoda_client()
    c.arm_supplementary_official("key")
    names = [name for name, _ in c.supplementary_readers("V")]
    assert "skoda_official" not in names
    assert names == []   # nothing else armed → readers empty (official stays out)


@pytest.mark.asyncio
async def test_official_live_read_delegates_and_failsoft():
    """The ACTIVE live-source path mirrors the failover path: delegates to the
    official client's get_status, is fail-soft, and honours the rate budget."""
    c = _skoda_client()
    # not armed → None
    assert await c.official_live_read("V") is None
    # armed → delegates
    c._supplementary_official = MagicMock()
    c._supplementary_official.over_rate_limit = False
    c._supplementary_official.get_status = AsyncMock(
        return_value=VehicleData(vin="V", battery_soc=61)
    )
    d = await c.official_live_read("V")
    assert d is not None and d.battery_soc == 61
    # over budget → skip the read entirely (do not breach the 20/h/key quota)
    c._supplementary_official.over_rate_limit = True
    c._supplementary_official.get_status.reset_mock()
    assert await c.official_live_read("V") is None
    c._supplementary_official.get_status.assert_not_called()
    # any error → None (must never sink the poll)
    c._supplementary_official.over_rate_limit = False
    c._supplementary_official.get_status = AsyncMock(side_effect=RuntimeError("boom"))
    assert await c.official_live_read("V") is None


@pytest.mark.asyncio
async def test_merge_official_live_merges_and_tags_provenance():
    """On a healthy cycle the official read merges its populated fields into the
    primary payload and tags their provenance as skoda_official."""
    coord = VagConnectCoordinator.__new__(VagConnectCoordinator)
    client = MagicMock()
    client.official_live_read = AsyncMock(
        return_value=VehicleData(vin="V", odometer_km=308, battery_soc=77)
    )
    coord._cariad_client = client
    enriched = {"odometer_km": 300, "field_sources": {"odometer_km": "primary"}}
    await coord._merge_official_live("V", enriched)
    # official wins for the fields it populated; provenance re-tagged
    assert enriched["odometer_km"] == 308
    assert enriched["battery_soc"] == 77
    assert enriched["field_sources"]["odometer_km"] == "skoda_official"
    assert enriched["field_sources"]["battery_soc"] == "skoda_official"


@pytest.mark.asyncio
async def test_merge_official_live_never_clobbers_with_defaults():
    """asdict() emits untouched False/0 defaults; those must NOT overwrite a real
    primary value. is_electric defaults False, so an official read that never set it
    must leave a primary is_electric=True untouched."""
    coord = VagConnectCoordinator.__new__(VagConnectCoordinator)
    client = MagicMock()
    client.official_live_read = AsyncMock(
        return_value=VehicleData(vin="V", odometer_km=308)  # is_electric stays default False
    )
    coord._cariad_client = client
    enriched = {"is_electric": True, "field_sources": {"is_electric": "primary"}}
    await coord._merge_official_live("V", enriched)
    assert enriched["is_electric"] is True                       # not clobbered
    assert enriched["field_sources"]["is_electric"] == "primary"  # provenance intact
    assert enriched["odometer_km"] == 308                        # real value still merged


@pytest.mark.asyncio
async def test_merge_official_live_last_seen_is_gap_fill_only():
    """last_seen_at must never jump backwards: if the primary already carries one,
    the official capture timestamp does not overwrite it; if absent, it fills."""
    coord = VagConnectCoordinator.__new__(VagConnectCoordinator)
    client = MagicMock()
    client.official_live_read = AsyncMock(
        return_value=VehicleData(vin="V", last_seen_at="2026-09-02T09:00:00Z")
    )
    coord._cariad_client = client
    # primary already has a (newer) timestamp → keep it
    enriched = {"last_seen_at": "2026-09-02T10:00:00Z", "field_sources": {}}
    await coord._merge_official_live("V", enriched)
    assert enriched["last_seen_at"] == "2026-09-02T10:00:00Z"
    assert "last_seen_at" not in enriched["field_sources"]
    # primary has none → gap-fill from official
    enriched2 = {"field_sources": {}}
    await coord._merge_official_live("V", enriched2)
    assert enriched2["last_seen_at"] == "2026-09-02T09:00:00Z"
    assert enriched2["field_sources"]["last_seen_at"] == "skoda_official"


@pytest.mark.asyncio
async def test_merge_official_live_noop_on_other_brands():
    """A non-Škoda client has no official_live_read → getattr None → no-op."""
    coord = VagConnectCoordinator.__new__(VagConnectCoordinator)
    coord._cariad_client = MagicMock(spec=[])   # no attributes at all
    enriched = {"odometer_km": 300, "field_sources": {"odometer_km": "primary"}}
    await coord._merge_official_live("V", enriched)
    assert enriched == {"odometer_km": 300, "field_sources": {"odometer_km": "primary"}}


def test_channel_status_reports_official_active_when_contributing():
    """Once the official read merges values, the connectivity map must report the
    skoda_official channel as active (with its live count) while still flagging it
    failover:True (it also serves on hard failure)."""
    coord = VagConnectCoordinator.__new__(VagConnectCoordinator)
    coord._channel_last_active = {}
    coord._armed_data_channels = lambda vin: ["primary", "skoda_official"]
    # official contributed one reading this cycle
    data = {"field_sources": {"odometer_km": "primary", "battery_soc": "skoda_official"}}
    status = coord._compute_channel_status("V", data)
    assert status["skoda_official"]["active"] is True
    assert status["skoda_official"]["active_values"] == 1
    assert status["skoda_official"]["failover"] is True
    # official armed but idle this cycle → not active (binary_sensor shows standby)
    data2 = {"field_sources": {"odometer_km": "primary"}}
    status2 = coord._compute_channel_status("V", data2)
    assert status2["skoda_official"]["active"] is False
    assert status2["skoda_official"]["active_values"] == 0


@pytest.mark.asyncio
async def test_revive_after_hard_failure_falls_over_to_official():
    coord = VagConnectCoordinator.__new__(VagConnectCoordinator)
    client = MagicMock()
    client.supplementary_readers = MagicMock(return_value=[])   # no continuous suppliers
    client.official_failover_read = AsyncMock(
        return_value=VehicleData(vin="V", battery_soc=42)
    )
    coord._cariad_client = client
    d = await coord._revive_after_hard_failure("V")
    assert d is not None and d.battery_soc == 42
    client.official_failover_read.assert_awaited_once_with("V")


@pytest.mark.asyncio
async def test_revive_prefers_supplementary_over_official():
    """A normal read-only supplementary (EU-DA / vw.de) still wins; the official
    API is the last resort, so its budget is only spent when nothing else has
    the car."""
    coord = VagConnectCoordinator.__new__(VagConnectCoordinator)
    client = MagicMock()
    client.supplementary_readers = MagicMock(return_value=[("eu_data_act", None)])
    client.official_failover_read = AsyncMock(return_value=VehicleData(vin="V", battery_soc=42))
    coord._cariad_client = client
    coord._revive_from_supplementary = AsyncMock(
        return_value=VehicleData(vin="V", battery_soc=90)
    )
    d = await coord._revive_after_hard_failure("V")
    assert d is not None and d.battery_soc == 90        # supplementary won
    client.official_failover_read.assert_not_called()   # official budget untouched


@pytest.mark.asyncio
async def test_no_official_on_other_brands_is_a_noop():
    """A non-Škoda client has no official_failover_read → getattr None → no-op."""
    coord = VagConnectCoordinator.__new__(VagConnectCoordinator)
    client = MagicMock(spec=[])           # no attributes at all
    coord._cariad_client = client
    assert await coord._revive_after_hard_failure("V") is None


def test_keygen_headers_match_the_app_byte_for_byte():
    """The api-keys management endpoint 400s without the app-identity headers (host,
    method, token, body were all confirmed identical to the app). _keygen_headers
    reproduces the 8.16 br0/b.smali set byte-for-byte."""
    c = _skoda_client()
    h = c._keygen_headers()
    assert h["User-Agent"] == "MySkoda/Android/8.16.0/260821007"
    assert h["X-APP-VERSION-NAME"] == "8.16.0"
    assert h["X-APP-VERSION-CODE"] == "260821007"
    assert h["X-APP-PLATFORM"] == "Android"
    assert h["X-DEVICE-LANGUAGE"] and h["X-DEVICE-COUNTRY"]
    # installation id is a well-formed UUID and STABLE across calls (like the app's
    # locally-persisted one — not a new id every request).
    uuid.UUID(h["X-APP-INSTALLATION-ID"])
    assert c._keygen_headers()["X-APP-INSTALLATION-ID"] == h["X-APP-INSTALLATION-ID"]
    # W3C traceparent 00-<32hex>-<16hex>-00, fresh per call.
    assert re.fullmatch(r"00-[0-9a-f]{32}-[0-9a-f]{16}-00", h["traceparent"])
    assert c._keygen_headers()["traceparent"] != h["traceparent"]


def test_keygen_headers_use_ha_locale_in_iso_form():
    """X-DEVICE-LANGUAGE/-COUNTRY come from the HA instance locale, normalized to the
    exact ISO forms the app sends: language ISO-639-1 lower 2-letter (region subtag
    dropped), country ISO-3166-1 alpha-2 upper."""
    c = _skoda_client()
    c._ha_language = "en-GB"   # HA language with a region subtag
    c._ha_country = "ch"       # lower-case country
    h = c._keygen_headers()
    assert h["X-DEVICE-LANGUAGE"] == "en"
    assert h["X-DEVICE-COUNTRY"] == "CH"
    c2 = _skoda_client()
    c2._ha_language = "de_DE"  # underscore locale form
    c2._ha_country = "DE"
    h2 = c2._keygen_headers()
    assert h2["X-DEVICE-LANGUAGE"] == "de"
    assert h2["X-DEVICE-COUNTRY"] == "DE"


def test_keygen_headers_fall_back_when_ha_locale_missing_or_garbage():
    """Missing or malformed HA locale → a valid ISO default, never an empty/invalid
    header (which could itself trip the backend)."""
    c = _skoda_client()
    c._ha_language = None
    c._ha_country = None
    h = c._keygen_headers()
    assert h["X-DEVICE-LANGUAGE"] == "en"
    assert h["X-DEVICE-COUNTRY"] == "DE"
    c._ha_language = "zzzz"    # too long / not a 2-letter code
    c._ha_country = "1"        # not alpha, wrong length
    h2 = c._keygen_headers()
    assert h2["X-DEVICE-LANGUAGE"] == "en"
    assert h2["X-DEVICE-COUNTRY"] == "DE"


@pytest.mark.asyncio
async def test_mint_sends_app_identity_headers_and_vin_first_body():
    """mint_api_key attaches the full app-identity header set and sends a vin-first
    body with a canonical (upper-case) VIN — byte-for-byte with the app."""
    c = _skoda_client()
    c._eu_portal = None
    c._tokens = SimpleNamespace(strategy="", access_token="tok")
    c.probe_outcomes = {}
    captured = {}

    async def fake_post(url, json=None, headers=None):
        captured.update(url=url, json=json, headers=headers)
        return {"id": "i", "key": "msk_x", "name": "Home Assistant",
                "validUntil": "2027-01-01"}

    c._post = fake_post
    out = await c.mint_api_key("wvwabc0000000001")
    assert out and out["key"] == "msk_x"
    # full app-identity header set on the create call
    hdr = captured["headers"]
    assert hdr["X-APP-VERSION-NAME"] == "8.16.0"
    assert hdr["X-APP-PLATFORM"] == "Android"
    assert "X-APP-INSTALLATION-ID" in hdr
    assert hdr["traceparent"].startswith("00-")
    # body is vin-first with a canonical upper-case VIN
    assert list(captured["json"].keys()) == ["vin", "name"]
    assert captured["json"]["vin"] == "WVWABC0000000001"
    assert captured["json"]["name"] == "Home Assistant"
