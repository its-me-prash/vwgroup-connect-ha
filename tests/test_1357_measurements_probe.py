# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#1357 (Ra72xx) — the attestation-free vw.de measurements/range probe.

A portal-only ID.3 surfaces a null electric range: the EU-DA portal ships that leaf
null AND the charging/status body the authproxy already reads carries no
``measurements`` block — while the CARIAD BFF reads the range from
``measurements.rangeStatus.value.electricRange`` (vw_eu.py:3834). Filling that gap
over vw.de needs a separate ``selectivestatus?jobs=measurements`` read, whose
allowlist-pass through the proxy is UNCONFIRMED. So it ships behind the opt-in test
cohort exactly like the #923 GPS / SoH probes: ranked candidate subpaths, self-
limiting budget, fail-soft, DIAGNOSTICS-ONLY (raw body captured redacted; NO entity
fed until a live #1357 capture confirms the leaf + allowlist-pass). These tests pin
the URL recipe, the tolerant BFF-mirroring parse contract, the self-limiting gate,
the candidate-pinning read, and — critically — the diagnostics-only guarantee.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from custom_components.vag_connect.cariad._authproxy import (
    _MEASUREMENTS_PROBE_SUBPATHS,
    build_measurements_url,
    parse_range_measurements,
)
from custom_components.vag_connect.cariad.auth._website_authproxy import (
    WebsiteAuthProxyConnector,
)
from custom_components.vag_connect.cariad.models import VehicleData

VIN = "WVWZZZAUZ1234567"


# ── URL recipe (mirrors warning-lights / parkingposition / SoH: WeConnect + VCF) ─

def test_selectivestatus_candidate_merges_its_query_after_proxy_params() -> None:
    url = build_measurements_url(VIN, "selectivestatus?jobs=measurements")
    assert url.count("?") == 1
    assert "/vwag-weconnect/proxy/vehicles/%s/selectivestatus" % VIN in url
    assert "resourceHost=myvw-vcf-prod" in url
    assert "gdc=myvw-wcar-prod" in url
    assert "jobs=measurements" in url


def test_multi_job_candidate_keeps_its_comma_list() -> None:
    url = build_measurements_url(VIN, "selectivestatus?jobs=fuelStatus,measurements")
    assert url.count("?") == 1
    assert "jobs=fuelStatus,measurements" in url


def test_dedicated_candidate_has_no_extra_query() -> None:
    url = build_measurements_url(VIN, "measurements")
    assert url.count("?") == 1  # only the proxy params
    assert "/proxy/vehicles/%s/measurements?" % VIN in url
    assert "jobs=" not in url


def test_url_honours_an_mbb_gdc_for_legacy_cars() -> None:
    url = build_measurements_url(VIN, "measurements", gdc="myvw-mbb-prod")
    assert "gdc=myvw-mbb-prod" in url


def test_candidate_list_is_ranked_app_form_first() -> None:
    assert _MEASUREMENTS_PROBE_SUBPATHS[0] == "selectivestatus?jobs=measurements"
    assert "measurements" in _MEASUREMENTS_PROBE_SUBPATHS


# ── parse contract (tolerant walk, mirrors the BFF range mapping) ───────────────

def test_1357_measurements_electric_range_leaf() -> None:
    """The exact #1357 shape: electric range only under measurements.rangeStatus."""
    body = {"measurements": {"rangeStatus": {"value": {"electricRange": 237}}}}
    assert parse_range_measurements(body) == {"electric_range_km": 237}


def test_adblue_range_leaf_diesel_item2() -> None:
    body = {"measurements": {"rangeStatus": {"value": {"adBlueRange": 8500}}}}
    assert parse_range_measurements(body) == {"adblue_range_km": 8500}


def test_combustion_scalar_and_wrapped_distance_forms() -> None:
    scalar = {"measurements": {"rangeStatus": {"value": {"dieselRange": 640}}}}
    assert parse_range_measurements(scalar) == {"combustion_range_km": 640}
    wrapped = {"measurements": {"rangeStatus": {"value": {
        "gasolineRange": {"distanceInKm": 512}}}}}
    assert parse_range_measurements(wrapped) == {"combustion_range_km": 512}


def test_total_range_leaf() -> None:
    body = {"measurements": {"rangeStatus": {"value": {"totalRange_km": 700}}}}
    assert parse_range_measurements(body) == {"total_range_km": 700}


def test_per_engine_mapped_by_type_not_position() -> None:
    """A GTE with primary=gasoline, secondary=electric — mapped by TYPE."""
    body = {"fuelStatus": {"rangeStatus": {"value": {
        "primaryEngine": {"type": "gasoline", "remainingRange_km": 480},
        "secondaryEngine": {"type": "electric", "remainingRange_km": 52},
    }}}}
    assert parse_range_measurements(body) == {
        "combustion_range_km": 480,
        "electric_range_km": 52,
    }


def test_measurements_and_fuelstatus_blocks_both_read() -> None:
    """A full jobs=fuelStatus,measurements body — both rangeStatus blocks walked."""
    body = {
        "fuelStatus": {"rangeStatus": {"value": {
            "primaryEngine": {"type": "electric", "remainingRange_km": 300}}}},
        "measurements": {"rangeStatus": {"value": {
            "adBlueRange": 0, "totalRange_km": 300}}},
    }
    out = parse_range_measurements(body)
    assert out["electric_range_km"] == 300
    assert out["adblue_range_km"] == 0        # 0 km AdBlue is a valid reading
    assert out["total_range_km"] == 300


def test_first_found_wins_across_blocks() -> None:
    """Per-engine electric is read first; a later scalar electricRange won't clobber."""
    body = {
        "fuelStatus": {"rangeStatus": {"value": {
            "primaryEngine": {"type": "electric", "remainingRange_km": 210}}}},
        "measurements": {"rangeStatus": {"value": {"electricRange": 999}}},
    }
    assert parse_range_measurements(body)["electric_range_km"] == 210


def test_degraded_and_non_dict_bodies_yield_empty() -> None:
    assert parse_range_measurements({"measurements": {"rangeStatus": {"value": {}}}}) == {}
    assert parse_range_measurements({"nothing": "useful"}) == {}
    assert parse_range_measurements(None) == {}
    assert parse_range_measurements("nope") == {}
    assert parse_range_measurements([1, 2, 3]) == {}


def test_bool_and_junk_leaves_rejected() -> None:
    body = {"measurements": {"rangeStatus": {"value": {
        "electricRange": True, "dieselRange": "640"}}}}
    assert parse_range_measurements(body) == {}


# ── self-limiting gate ─────────────────────────────────────────────────────────

def _conn() -> WebsiteAuthProxyConnector:
    c = WebsiteAuthProxyConnector.__new__(WebsiteAuthProxyConnector)
    c.probe_measurements = False
    c._measurements_probe_tries = 0
    c._measurements_available = False
    c._measurements_subpath = None
    c.probe_outcomes = {}
    return c


def test_opted_out_never_probes() -> None:
    assert _conn()._should_probe_measurements() is False


def test_opted_in_probes_within_budget_then_stops() -> None:
    c = _conn()
    c.probe_measurements = True
    assert c._should_probe_measurements() is True
    c._measurements_probe_tries = c._MEASUREMENTS_PROBE_MAX_TRIES
    assert c._should_probe_measurements() is False


def test_a_confirmed_read_latches_on_forever() -> None:
    c = _conn()
    c.probe_measurements = False       # even opted-out again…
    c._measurements_available = True   # …a car that once returned range keeps reading
    assert c._should_probe_measurements() is True


# ── candidate-pinning read (fail-soft, stops at first hit) ─────────────────────

def test_get_range_measurements_pins_the_candidate_that_hits() -> None:
    c = _conn()
    c._ensure_backend = AsyncMock(return_value=None)
    c._gdc = lambda vin: "myvw-wcar-prod"
    c._get_json = AsyncMock(side_effect=[
        None,  # first candidate 404s
        {"measurements": {"rangeStatus": {"value": {"electricRange": 240}}}},
    ])
    leaves = asyncio.run(c.get_range_measurements(VIN))
    assert leaves == {"electric_range_km": 240}
    assert c._measurements_subpath == _MEASUREMENTS_PROBE_SUBPATHS[1]
    # diagnostics label refined to the leaves seen (no PII — range names only)
    base = _MEASUREMENTS_PROBE_SUBPATHS[1].split("?")[0]
    assert c.probe_outcomes[f"measurements:{base}"].startswith("200 ")
    assert "electric_range_km" in c.probe_outcomes[f"measurements:{base}"]
    # a subsequent poll issues a SINGLE request against the pinned subpath
    c._get_json = AsyncMock(return_value={
        "measurements": {"rangeStatus": {"value": {"electricRange": 235}}}})
    assert asyncio.run(c.get_range_measurements(VIN)) == {"electric_range_km": 235}
    assert c._get_json.await_count == 1


def test_get_range_measurements_returns_none_when_all_candidates_miss() -> None:
    c = _conn()
    c._ensure_backend = AsyncMock(return_value=None)
    c._gdc = lambda vin: "myvw-wcar-prod"
    c._get_json = AsyncMock(return_value=None)
    assert asyncio.run(c.get_range_measurements(VIN)) is None
    assert c._measurements_subpath is None
    assert c._get_json.await_count == len(_MEASUREMENTS_PROBE_SUBPATHS)


def test_degraded_200_refined_to_no_range_label() -> None:
    c = _conn()
    c._ensure_backend = AsyncMock(return_value=None)
    c._gdc = lambda vin: "myvw-wcar-prod"
    c._get_json = AsyncMock(return_value={"nothing": "useful"})
    assert asyncio.run(c.get_range_measurements(VIN)) is None
    base = _MEASUREMENTS_PROBE_SUBPATHS[0].split("?")[0]
    assert c.probe_outcomes[f"measurements:{base}"] == "200 no-range"


# ── DIAGNOSTICS-ONLY guarantee: the probe feeds NO entity (the #1357 guardrail) ─

def _full_conn() -> WebsiteAuthProxyConnector:
    c = WebsiteAuthProxyConnector.__new__(WebsiteAuthProxyConnector)
    # probe flags: measurements armed, GPS/SoH off
    c.probe_position = False
    c._position_available = False
    c.probe_soh = False
    c._soh_available = False
    c.probe_measurements = True
    c._measurements_available = False
    c._measurements_probe_tries = 0
    c._measurements_subpath = None
    c.probe_outcomes = {}
    c.last_raw_responses = {}
    # stub every dependency get_vehicle_data touches
    c._ensure_backend = AsyncMock(return_value=None)
    c._gdc = lambda vin: "myvw-wcar-prod"
    c._get_json = AsyncMock(return_value=None)  # charging + maintenance → no data
    c.get_relations = AsyncMock(return_value=None)
    c.get_warning_lights = AsyncMock(return_value=None)
    c.get_last_lock_action = AsyncMock(return_value=None)
    c.get_relation_detail = AsyncMock(return_value=None)
    c.get_exterior_images = AsyncMock(return_value=[])
    c.get_master_data = AsyncMock(return_value=SimpleNamespace(
        model_name=None, model_year=None, exterior_color_text=None, engine=None))
    return c


def test_get_vehicle_data_does_not_feed_range_entities_from_the_probe() -> None:
    """Even when the probe returns real range leaves, get_vehicle_data must leave
    electric_range_km / adblue_range_km / combustion_range_km None — DIAGNOSTICS-ONLY
    until a live #1357 capture confirms the leaf. This pins the guardrail."""
    c = _full_conn()
    c.get_range_measurements = AsyncMock(return_value={
        "electric_range_km": 240, "adblue_range_km": 8000, "combustion_range_km": 30})
    d: VehicleData = asyncio.run(c.get_vehicle_data(VIN))
    assert d.electric_range_km is None
    assert d.adblue_range_km is None
    assert d.combustion_range_km is None
    # but the probe DID run and latched (its outcome/raw body reach diagnostics)
    assert c._measurements_available is True
    c.get_range_measurements.assert_awaited_once()
