# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#1357 (@Ra72xx) — per-VIN read-source priority.

The per-field merge winner is the ORDER of the channel list, not the freshest
value — so a portal-primary car has the (batch) EU Data Act feed win every field
the live vw.de channel also carries. ``prefer_website_authproxy`` flips that PER
VIN: the live vw.de channel is stable-sorted to the front so it wins every field
it has, while EU-DA keeps filling the fields only it provides. ``auto`` (default)
is byte-for-byte identical to today. Only the read merge order changes — reconcile,
command routing and the write paths are untouched.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

from custom_components.vag_connect.cariad._channel_merge import gather_and_merge
from custom_components.vag_connect.cariad.models import VehicleData
from custom_components.vag_connect.const import (
    CONF_READ_PRIORITY,
    READ_PRIORITY_DEFAULT,
)
from custom_components.vag_connect.coordinator import VagConnectCoordinator

VIN = "WVWZZZAUZFW805377"


def _supp(name: str, vd: VehicleData):
    """(name, awaitable→vd) supplier tuple, matching gather_and_merge's contract."""
    async def _read() -> VehicleData:
        return vd
    return (name, _read())


def _merge(primary_name, primary, suppliers, preferred=None):
    return asyncio.run(
        gather_and_merge(primary_name, primary, suppliers, preferred=preferred)
    )


# ── the 49/8 flip: prefer vw.de reorders the winner ─────────────────────────
def test_auto_default_keeps_primary_winning() -> None:
    """No preferred → today's behaviour: the EU-DA primary wins the shared field."""
    primary = VehicleData(vin=VIN)
    primary.model = "portal-model"
    supp = VehicleData(vin=VIN)
    supp.model = "vwde-model"
    merged = _merge("eu_data_act", primary, [_supp("website_authproxy", supp)])
    assert merged.model == "portal-model"
    assert merged.field_sources.get("model") == "eu_data_act"


def test_prefer_vwde_flips_the_shared_field_to_vwde() -> None:
    """prefer_website_authproxy → the live vw.de value wins + is stamped as such."""
    primary = VehicleData(vin=VIN)
    primary.model = "portal-model"
    supp = VehicleData(vin=VIN)
    supp.model = "vwde-model"
    merged = _merge("eu_data_act", primary, [_supp("website_authproxy", supp)],
                    preferred="website_authproxy")
    assert merged.model == "vwde-model"
    assert merged.field_sources.get("model") == "website_authproxy"


def test_eu_da_only_field_still_comes_from_eu_da_when_preferring_vwde() -> None:
    """The ~49 fields only EU-DA carries must keep coming from EU-DA (gap-fill),
    so preferring vw.de improves freshness without losing portal-only data."""
    primary = VehicleData(vin=VIN)
    primary.model = "portal-model"          # shared with vw.de below
    primary.service_km = 12345              # EU-DA-only here
    supp = VehicleData(vin=VIN)
    supp.model = "vwde-model"   # no service_km
    merged = _merge("eu_data_act", primary, [_supp("website_authproxy", supp)],
                    preferred="website_authproxy")
    assert merged.model == "vwde-model"                       # flipped
    assert merged.service_km == 12345                         # portal-only kept
    assert merged.field_sources.get("service_km") == "eu_data_act"


def test_preferred_auto_is_a_noop() -> None:
    primary = VehicleData(vin=VIN)
    primary.model = "portal-model"
    supp = VehicleData(vin=VIN)
    supp.model = "vwde-model"
    merged = _merge("eu_data_act", primary, [_supp("website_authproxy", supp)],
                    preferred="auto")
    assert merged.model == "portal-model"


def test_single_channel_car_is_untouched_by_preference() -> None:
    """No supplier → gather_and_merge returns the primary verbatim, no crash."""
    primary = VehicleData(vin=VIN)
    primary.model = "only"
    merged = _merge("eu_data_act", primary, [], preferred="website_authproxy")
    assert merged.model == "only"


def test_prefer_missing_channel_is_a_noop() -> None:
    """Preferring a channel that isn't present must not reorder anything."""
    primary = VehicleData(vin=VIN)
    primary.model = "portal-model"
    supp = VehicleData(vin=VIN)
    supp.model = "vwde-model"
    merged = _merge("eu_data_act", primary, [_supp("website_authproxy", supp)],
                    preferred="tibber")  # not in sources
    assert merged.model == "portal-model"  # order unchanged


# ── the coordinator reader: per-VIN, options-then-data, unknown → None ──────
def _reader(entry) -> object:
    c = VagConnectCoordinator.__new__(VagConnectCoordinator)
    c.entry = entry
    return c


def test_reader_returns_channel_for_prefer_vwde() -> None:
    entry = SimpleNamespace(
        options={},  # options are always {} at read time (listener folds → data)
        data={CONF_READ_PRIORITY: {VIN: "prefer_website_authproxy"}},
    )
    assert VagConnectCoordinator._read_priority_channel(_reader(entry), VIN) \
        == "website_authproxy"


def test_reader_is_per_vin() -> None:
    entry = SimpleNamespace(
        options={},
        data={CONF_READ_PRIORITY: {"OTHERVIN00000000X": "prefer_website_authproxy"}},
    )
    # the queried VIN has no entry → auto → None (other VINs unaffected)
    assert VagConnectCoordinator._read_priority_channel(_reader(entry), VIN) is None


def test_reader_auto_and_unknown_and_missing_map_all_give_none() -> None:
    for data in (
        {CONF_READ_PRIORITY: {VIN: READ_PRIORITY_DEFAULT}},   # explicit auto
        {CONF_READ_PRIORITY: {VIN: "garbage"}},               # unknown mode
        {CONF_READ_PRIORITY: {}},                             # empty map
        {},                                                   # no map at all
    ):
        c = _reader(SimpleNamespace(options={}, data=data))
        assert VagConnectCoordinator._read_priority_channel(c, VIN) is None


def test_reader_matches_vin_case_insensitively() -> None:
    entry = SimpleNamespace(
        options={},
        data={CONF_READ_PRIORITY: {VIN.upper(): "prefer_website_authproxy"}},
    )
    assert VagConnectCoordinator._read_priority_channel(_reader(entry), VIN.lower()) \
        == "website_authproxy"
