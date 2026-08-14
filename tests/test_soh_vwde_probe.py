# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""4.3.2 batteryHealthState — the attestation-free vw.de battery-SoH probe.

We Connect 4.3.2 added a native ``batteryHealthState`` capability, read by the
app through the Play-Integrity-walled BFF selectivestatus job
(``stateOfHealth.ubeIndicator_pct``, 403 for VW EU). Whether the attestation-free
volkswagen.de reverse-proxy exposes the same value — and at which subpath — is
UNCONFIRMED, so it ships behind the opt-in test cohort exactly like the #923 GPS
probe: ranked candidate subpaths, self-limiting budget, fail-soft, diagnostics-only
(the raw body is captured redacted; the SoH entity stays the user-nominal estimate
until a real value is confirmed across cars). These tests pin the URL recipe, the
tolerant parse contract, the self-limiting gate, and the candidate-pinning read.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

from custom_components.vag_connect.cariad._authproxy import (
    _SOH_PROBE_SUBPATHS,
    build_batteryhealth_url,
    parse_battery_health,
)
from custom_components.vag_connect.cariad.auth._website_authproxy import (
    WebsiteAuthProxyConnector,
)

VIN = "WVWZZZAUZ1234567"


# ── URL recipe (mirrors warning-lights/parkingposition: WeConnect realm + VCF) ──

def test_selectivestatus_candidate_merges_its_query_after_proxy_params() -> None:
    """The selectivestatus candidate carries its own ``?jobs=...`` — it must be
    merged with ``&`` so the URL stays single-``?`` and all three params survive."""
    url = build_batteryhealth_url(VIN, "selectivestatus?jobs=batteryHealthState")
    assert url.count("?") == 1
    assert "/vwag-weconnect/proxy/vehicles/%s/selectivestatus" % VIN in url
    assert "resourceHost=myvw-vcf-prod" in url
    assert "gdc=myvw-wcar-prod" in url
    assert "jobs=batteryHealthState" in url


def test_dedicated_candidate_has_no_extra_query() -> None:
    url = build_batteryhealth_url(VIN, "batteryhealthstate")
    assert url.count("?") == 1  # only the proxy params
    assert "/proxy/vehicles/%s/batteryhealthstate?" % VIN in url
    assert "jobs=" not in url


def test_url_honours_an_mbb_gdc_for_legacy_cars() -> None:
    url = build_batteryhealth_url(VIN, "batteryhealthstate", gdc="myvw-mbb-prod")
    assert "gdc=myvw-mbb-prod" in url


def test_candidate_list_is_ranked_app_form_first() -> None:
    assert _SOH_PROBE_SUBPATHS[0].startswith("selectivestatus?jobs=batteryHealthState")
    assert "batteryhealthstate" in _SOH_PROBE_SUBPATHS


# ── parse contract (tolerant: walk for ubeIndicator_pct, whatever the nesting) ──

def test_app_selectivestatus_envelope_parses() -> None:
    """The BFF envelope shape the app deserialises (RE 2026-08-12)."""
    body = {"batteryHealthState": {"stateOfHealth": {
        "ubeIndicator_pct": 92.0,
        "carCapturedTimestamp": "2026-08-10T12:00:00Z"}}}
    assert parse_battery_health(body) == 92.0


def test_top_level_or_data_wrapped_value_also_parses() -> None:
    assert parse_battery_health({"ubeIndicator_pct": 88.5}) == 88.5
    assert parse_battery_health({"data": {"stateOfHealth": {"ubeIndicator_pct": 100}}}) == 100.0


def test_degraded_or_out_of_range_or_bool_values_are_rejected() -> None:
    assert parse_battery_health({"stateOfHealth": {}}) is None            # empty node
    assert parse_battery_health({"ubeIndicator_pct": 0}) is None          # 0 = degraded
    assert parse_battery_health({"ubeIndicator_pct": 120}) is None        # impossible %
    assert parse_battery_health({"ubeIndicator_pct": -5}) is None
    assert parse_battery_health({"ubeIndicator_pct": True}) is None       # bool subclass
    assert parse_battery_health({"ubeIndicator_pct": "92"}) is None       # string junk


def test_non_dict_bodies_pass_through_as_none() -> None:
    assert parse_battery_health(None) is None
    assert parse_battery_health("nope") is None
    assert parse_battery_health([1, 2, 3]) is None


# ── self-limiting gate ─────────────────────────────────────────────────────────

def _conn() -> WebsiteAuthProxyConnector:
    c = WebsiteAuthProxyConnector.__new__(WebsiteAuthProxyConnector)
    c.probe_soh = False
    c._soh_probe_tries = 0
    c._soh_available = False
    c._soh_subpath = None
    return c


def test_opted_out_never_probes() -> None:
    c = _conn()
    assert c._should_probe_soh() is False


def test_opted_in_probes_within_budget_then_stops() -> None:
    c = _conn()
    c.probe_soh = True
    assert c._should_probe_soh() is True
    c._soh_probe_tries = c._SOH_PROBE_MAX_TRIES
    assert c._should_probe_soh() is False  # budget exhausted


def test_a_confirmed_read_latches_on_forever() -> None:
    c = _conn()
    c.probe_soh = False            # even opted-out again…
    c._soh_available = True        # …a car that once returned a % keeps reading
    assert c._should_probe_soh() is True


# ── candidate-pinning read (fail-soft, stops at first hit) ─────────────────────

def test_get_battery_health_pins_the_candidate_that_hits() -> None:
    c = _conn()
    c._ensure_backend = AsyncMock(return_value=None)
    c._gdc = lambda vin: "myvw-wcar-prod"
    # first candidate 404s (None), second returns a real %
    c._get_json = AsyncMock(side_effect=[
        None,
        {"stateOfHealth": {"ubeIndicator_pct": 91.0}},
    ])
    soh = asyncio.run(c.get_battery_health(VIN))
    assert soh == 91.0
    assert c._soh_subpath == _SOH_PROBE_SUBPATHS[1]  # pinned the one that worked
    # a subsequent poll issues a SINGLE request against the pinned subpath
    c._get_json = AsyncMock(return_value={"ubeIndicator_pct": 90.0})
    assert asyncio.run(c.get_battery_health(VIN)) == 90.0
    assert c._get_json.await_count == 1


def test_get_battery_health_returns_none_when_all_candidates_miss() -> None:
    c = _conn()
    c._ensure_backend = AsyncMock(return_value=None)
    c._gdc = lambda vin: "myvw-wcar-prod"
    c._get_json = AsyncMock(return_value=None)  # every candidate 4xx/empty
    assert asyncio.run(c.get_battery_health(VIN)) is None
    assert c._soh_subpath is None
    # all candidates were tried once (nothing pinned)
    assert c._get_json.await_count == len(_SOH_PROBE_SUBPATHS)
