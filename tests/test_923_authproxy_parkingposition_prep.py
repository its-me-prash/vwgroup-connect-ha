# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#923 — PREP (unmerged until a live probe confirms it): the VW EU authproxy
parkingposition lever.

VW EU GPS is structurally unavailable on every channel we currently ship: the
CARIAD app backend's position endpoint is attestation-walled (403 for EU
passenger cars post-lockdown) and the EU Data Act live feed has no coordinate
field. The one remaining attestation-free lever is whether the volkswagen.de
reverse-proxy will pass a parkingposition read through the same WeConnect realm
that already carries charging + warning-lights. This wiring is prepared and
tested but only ships once a live probe on a portal-enrolled car returns a
coordinate — these tests pin the URL recipe and the parse contract so the moment
that happens it's one merge away.
"""
from __future__ import annotations

from custom_components.vag_connect.cariad._authproxy import (
    build_parkingposition_url,
    parse_parking_position,
)


# ── URL recipe (mirrors warning-lights: WeConnect realm + live VCF host + gdc) ──

def test_url_uses_the_weconnect_realm_and_live_host() -> None:
    url = build_parkingposition_url("WVWZZZAUZ1234567")
    assert "/vwag-weconnect/proxy/vehicles/WVWZZZAUZ1234567/parkingposition" in url
    assert "resourceHost=myvw-vcf-prod" in url
    assert "gdc=myvw-wcar-prod" in url  # WeConnect default when no platform given


def test_url_honours_an_mbb_gdc_for_legacy_cars() -> None:
    url = build_parkingposition_url("WVWZZZAUZ1234567", gdc="myvw-mbb-prod")
    assert "gdc=myvw-mbb-prod" in url


# ── parse contract (same shape as the CARIAD-BFF read) ─────────────────────────

def test_data_wrapped_coordinates_parse() -> None:
    body = {"data": {"lat": 48.21, "lon": 16.37,
                     "carCapturedTimestamp": "2026-08-10T12:00:00Z"}}
    assert parse_parking_position(body) == (48.21, 16.37, "2026-08-10T12:00:00Z")


def test_top_level_coordinates_are_a_fallback() -> None:
    """Legacy/alternate firmwares may ship lat/lon at the top level."""
    assert parse_parking_position({"lat": 48.2, "lon": 16.3}) == (48.2, 16.3, None)


def test_a_degraded_empty_body_yields_no_coordinates() -> None:
    """#923: a 200 with an empty data node must NOT be read as (None, None) — it
    returns None so the last-known position carries forward instead of being
    overwritten."""
    assert parse_parking_position({"data": {}}) is None
    assert parse_parking_position({"data": {"lat": 48.2}}) is None  # lon missing


def test_non_numeric_or_bool_coordinates_are_rejected() -> None:
    assert parse_parking_position({"data": {"lat": "48.2", "lon": "16.3"}}) is None
    assert parse_parking_position({"data": {"lat": True, "lon": False}}) is None


def test_non_dict_bodies_pass_through_as_none() -> None:
    assert parse_parking_position(None) is None
    assert parse_parking_position("nope") is None
    assert parse_parking_position([{"lat": 1, "lon": 2}]) is None


def test_a_missing_timestamp_is_none_not_a_crash() -> None:
    assert parse_parking_position({"data": {"lat": 1.0, "lon": 2.0}}) == (1.0, 2.0, None)
    assert parse_parking_position(
        {"data": {"lat": 1.0, "lon": 2.0, "carCapturedTimestamp": ""}}
    ) == (1.0, 2.0, None)
