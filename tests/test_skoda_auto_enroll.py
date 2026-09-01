# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Škoda official-API auto-enrollment orchestration in the coordinator.

An already-logged-in Škoda user is auto-enrolled: we mint a per-VIN X-API-Key from
the existing mysmob login, persist it, arm the official failover channel, and raise
a one-time HA repair. Idempotent (skip VINs with a stored key, honour the 5-key
quota) + fail-soft + gated on a native login.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from custom_components.vag_connect.coordinator import VagConnectCoordinator
from custom_components.vag_connect.const import CONF_BRAND, CONF_SKODA_OFFICIAL_KEYS

VIN1, VIN2 = "TMBEL9NEXP1000001", "TMBEL9NEXP1000002"


def _coord(entry_data: dict, client) -> VagConnectCoordinator:
    c = VagConnectCoordinator.__new__(VagConnectCoordinator)
    c.hass = MagicMock()
    c.entry = MagicMock()
    c.entry.entry_id = "e1"
    c.entry.data = dict(entry_data)
    c._cariad_client = client
    return c


def _client(can_mint: bool = True, remaining: int = 5):
    cl = MagicMock()
    cl.can_mint_official_key = can_mint
    cl.list_api_keys = AsyncMock(return_value={
        "maxKeys": 5,
        "vehicleKeys": [
            {"vin": VIN1, "keysRemaining": remaining},
            {"vin": VIN2, "keysRemaining": remaining},
        ],
    })
    cl.mint_api_key = AsyncMock(side_effect=lambda vin: {
        "id": f"id-{vin}", "key": f"KEY-{vin}", "validUntil": "2027-09-01T00:00:00Z"})
    cl.arm_supplementary_official = MagicMock()
    cl.probe_outcomes = {}  # real dict so _skoda_probe captures (not a MagicMock attr)
    return cl


def test_enrolls_mints_persists_arms_and_notifies():
    cl = _client()
    c = _coord({CONF_BRAND: "skoda"}, cl)
    with patch(
        "custom_components.vag_connect.repairs.raise_issue_skoda_official_enrolled"
    ) as rep:
        asyncio.run(c._auto_enroll_skoda_official([VIN1, VIN2]))
    assert cl.mint_api_key.await_count == 2
    kw = cl.arm_supplementary_official.call_args.kwargs
    assert kw["keys_by_vin"] == {VIN1: f"KEY-{VIN1}", VIN2: f"KEY-{VIN2}"}
    data = c.hass.config_entries.async_update_entry.call_args.kwargs["data"]
    assert data[CONF_SKODA_OFFICIAL_KEYS][VIN1]["key"] == f"KEY-{VIN1}"
    assert data[CONF_SKODA_OFFICIAL_KEYS][VIN1]["id"] == f"id-{VIN1}"
    rep.assert_called_once()


def test_non_skoda_is_noop():
    cl = _client()
    c = _coord({CONF_BRAND: "volkswagen"}, cl)
    asyncio.run(c._auto_enroll_skoda_official([VIN1]))
    cl.mint_api_key.assert_not_awaited()
    cl.arm_supplementary_official.assert_not_called()


def test_portal_fallback_gate_blocks_mint():
    # can_mint_official_key False = portal-fallback / non-native login → never mint
    cl = _client(can_mint=False)
    c = _coord({CONF_BRAND: "skoda"}, cl)
    asyncio.run(c._auto_enroll_skoda_official([VIN1]))
    cl.mint_api_key.assert_not_awaited()


def test_already_enrolled_arms_without_re_minting():
    cl = _client()
    c = _coord({
        CONF_BRAND: "skoda",
        CONF_SKODA_OFFICIAL_KEYS: {VIN1: {"key": "OLD", "id": "x", "validUntil": "y"}},
    }, cl)
    asyncio.run(c._auto_enroll_skoda_official([VIN1]))
    cl.mint_api_key.assert_not_awaited()
    assert cl.arm_supplementary_official.call_args.kwargs["keys_by_vin"] == {VIN1: "OLD"}
    c.hass.config_entries.async_update_entry.assert_not_called()  # nothing new to persist


def test_quota_full_raises_quota_repair_and_does_not_mint():
    cl = _client(remaining=0)
    c = _coord({CONF_BRAND: "skoda"}, cl)
    with patch(
        "custom_components.vag_connect.repairs.raise_issue_skoda_official_quota"
    ) as rep:
        asyncio.run(c._auto_enroll_skoda_official([VIN1]))
    cl.mint_api_key.assert_not_awaited()
    rep.assert_called_once()
    c.hass.config_entries.async_update_entry.assert_not_called()


def test_success_records_enrolled_probe():
    cl = _client()
    c = _coord({CONF_BRAND: "skoda"}, cl)
    with patch("custom_components.vag_connect.repairs.raise_issue_skoda_official_enrolled"):
        asyncio.run(c._auto_enroll_skoda_official([VIN1, VIN2]))
    assert cl.probe_outcomes["skoda_official"] == "enrolled (2 new key(s))"


def test_gate_block_records_probe():
    cl = _client(can_mint=False)
    c = _coord({CONF_BRAND: "skoda"}, cl)
    asyncio.run(c._auto_enroll_skoda_official([VIN1]))
    assert cl.probe_outcomes["skoda_official"] == "gate: not a native mysmob login"


def test_quota_full_records_probe():
    cl = _client(remaining=0)
    c = _coord({CONF_BRAND: "skoda"}, cl)
    with patch("custom_components.vag_connect.repairs.raise_issue_skoda_official_quota"):
        asyncio.run(c._auto_enroll_skoda_official([VIN1]))
    assert cl.probe_outcomes["skoda_official"].startswith("quota-full")


def test_multi_integration_detected_raises_repair():
    # maxKeys 5, 2 keys in use (remaining 3) but we hold only 1 → a foreign key
    # exists → another integration/app is using the same official API.
    cl = _client()
    c = _coord({CONF_BRAND: "skoda"}, cl)
    listing = {"maxKeys": 5, "vehicleKeys": [{"vin": VIN1, "keysRemaining": 3}]}
    with patch(
        "custom_components.vag_connect.repairs.raise_issue_skoda_official_multi_integration"
    ) as rep:
        c._check_skoda_multi_integration(listing, {VIN1: {"key": "K"}}, [VIN1])
    rep.assert_called_once()


def test_only_our_key_no_multi_integration_repair():
    cl = _client()
    c = _coord({CONF_BRAND: "skoda"}, cl)
    # 1 key in use (remaining 4) and it's ours → nobody else
    listing = {"maxKeys": 5, "vehicleKeys": [{"vin": VIN1, "keysRemaining": 4}]}
    with patch(
        "custom_components.vag_connect.repairs.raise_issue_skoda_official_multi_integration"
    ) as rep:
        c._check_skoda_multi_integration(listing, {VIN1: {"key": "K"}}, [VIN1])
    rep.assert_not_called()


def test_foreign_key_before_we_mint_raises():
    # 1 key in use, we hold none yet (about to mint) → the existing key is foreign
    cl = _client()
    c = _coord({CONF_BRAND: "skoda"}, cl)
    listing = {"maxKeys": 5, "vehicleKeys": [{"vin": VIN1, "keysRemaining": 4}]}
    with patch(
        "custom_components.vag_connect.repairs.raise_issue_skoda_official_multi_integration"
    ) as rep:
        c._check_skoda_multi_integration(listing, {}, [VIN1])
    rep.assert_called_once()


def test_multi_integration_bad_listing_never_crashes():
    cl = _client()
    c = _coord({CONF_BRAND: "skoda"}, cl)
    with patch(
        "custom_components.vag_connect.repairs.raise_issue_skoda_official_multi_integration"
    ) as rep:
        for bad in (None, {}, {"maxKeys": "x"}, {"vehicleKeys": "nope"},
                    {"maxKeys": 5, "vehicleKeys": [{"vin": None}]}):
            c._check_skoda_multi_integration(bad, {}, [VIN1])
    rep.assert_not_called()


def test_second_unmanaged_skoda_does_not_trip_repair():
    # A DIFFERENT Škoda on the same account (VIN2, not managed by this entry) has
    # its own legitimate app key — it must NOT trip the multi-integration warning.
    cl = _client()
    c = _coord({CONF_BRAND: "skoda"}, cl)
    listing = {"maxKeys": 5, "vehicleKeys": [
        {"vin": VIN1, "keysRemaining": 4},   # ours, only our key
        {"vin": VIN2, "keysRemaining": 4},   # a second, unmanaged car with a key
    ]}
    with patch(
        "custom_components.vag_connect.repairs.raise_issue_skoda_official_multi_integration"
    ) as rep:
        c._check_skoda_multi_integration(listing, {VIN1: {"key": "K"}}, [VIN1])
    rep.assert_not_called()


def test_manual_fallback_key_counts_as_ours():
    # The user's own manually-pasted key is one of the account's keys; it must not
    # be mistaken for another integration.
    from custom_components.vag_connect.const import CONF_SKODA_OFFICIAL_API_KEY
    cl = _client()
    c = _coord({CONF_BRAND: "skoda", CONF_SKODA_OFFICIAL_API_KEY: "PASTED"}, cl)
    # 1 key in use (the manual one), we hold no auto-minted key → still ours
    listing = {"maxKeys": 5, "vehicleKeys": [{"vin": VIN1, "keysRemaining": 4}]}
    with patch(
        "custom_components.vag_connect.repairs.raise_issue_skoda_official_multi_integration"
    ) as rep:
        c._check_skoda_multi_integration(listing, {}, [VIN1])
    rep.assert_not_called()


def test_failed_mint_not_retried_same_session():
    # A live mint that fails (returns None) must NOT be re-hammered every poll: the
    # attempted-set caps it at one try per HA session; the keygen probe stays visible.
    cl = _client()
    cl.mint_api_key = AsyncMock(return_value=None)
    c = _coord({CONF_BRAND: "skoda"}, cl)
    asyncio.run(c._auto_enroll_skoda_official([VIN1, VIN2]))
    asyncio.run(c._auto_enroll_skoda_official([VIN1, VIN2]))  # second poll, same session
    assert cl.mint_api_key.await_count == 2  # once per VIN, not four times
    assert cl.probe_outcomes["skoda_official"].startswith("no key minted")
