# Copyright 2026 Prash Balan (@its-me-prash) - Apache License 2.0
# SPDX-License-Identifier: AGPL-3.0-or-later
"""v2.8.0 quick win E - per-brand capability advertisement tests.

Scope (per the v2.8.0 staging spec):

1. ``DECLARED_CAPABILITIES`` covers every brand the integration claims
   to support so a future brand added to the BRANDS registry without a
   matching capability row gets caught here.
2. ``capabilities_snapshot`` returns the documented shape:
   ``{brand: {"declared": {...}, "observed": {...}, "drift": [...]}}``.
3. The ``drift`` list flags capabilities the integration declared as
   supported but did not observe on any known VIN.
4. A brand that is NOT registered in ``DECLARED_CAPABILITIES`` still
   produces a well-formed snapshot (empty ``declared``, regular
   ``observed``, empty ``drift``) instead of crashing - the diagnostics
   export must never blow up because of a typo or a beta brand.

Tests stay pure-Python: the coordinator is built via ``__new__`` to
avoid the HA startup chain, matching the pattern from
``tests/test_coordinator.py``.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from custom_components.vag_connect.cariad._capabilities import (
    DECLARED_CAPABILITIES,
)
from custom_components.vag_connect.cariad.models import BRANDS
from custom_components.vag_connect.const import CONF_BRAND
from custom_components.vag_connect.coordinator import VagConnectCoordinator


def _make_coordinator(brand: str = "audi") -> VagConnectCoordinator:
    """Build a coordinator skeleton without running ``__init__``.

    Same pattern as ``tests/test_coordinator.py`` - bypass the HA wiring
    so the test can exercise the pure data-shape helpers in isolation.
    """
    coord = VagConnectCoordinator.__new__(VagConnectCoordinator)
    coord.hass = MagicMock()
    coord.entry = MagicMock()
    coord.entry.data = {CONF_BRAND: brand}
    coord.vehicles = {}
    coord._cariad_client = None
    coord._skoda_push = None
    coord._cupra_seat_push = None
    coord._audi_vw_push = None
    return coord


# ── Spec #1: declared table covers every supported brand ──────────────


def test_declared_capabilities_covers_every_supported_brand() -> None:
    """Every brand exported by ``BRANDS`` must appear in DECLARED_CAPABILITIES.

    If a future brand gets added to the registry without a row here,
    diagnostics for that brand would silently return an empty declared
    dict and the drift detection would not flag anything - users would
    not get the "you said Audi supports charging" signal we built this
    table for. The test makes that mistake a build break.
    """
    missing = sorted(set(BRANDS.keys()) - set(DECLARED_CAPABILITIES.keys()))
    assert not missing, (
        f"Brands present in BRANDS but missing from "
        f"DECLARED_CAPABILITIES: {missing}"
    )


def test_declared_capabilities_values_are_booleans() -> None:
    """Each declared cell must be a bool - the snapshot shape relies on
    ``is True`` / ``is False`` comparisons for drift detection."""
    for brand, table in DECLARED_CAPABILITIES.items():
        for key, value in table.items():
            assert isinstance(value, bool), (
                f"{brand}.{key} is {type(value).__name__}, expected bool"
            )


# ── Spec #2: snapshot returns the documented shape ────────────────────


def test_capabilities_snapshot_returns_documented_shape() -> None:
    """The snapshot must be keyed by brand and carry declared/observed/drift."""
    coord = _make_coordinator(brand="audi")
    snap = coord.capabilities_snapshot()

    assert "audi" in snap
    audi = snap["audi"]
    assert set(audi.keys()) == {"declared", "observed", "drift"}
    assert isinstance(audi["declared"], dict)
    assert isinstance(audi["observed"], dict)
    assert isinstance(audi["drift"], list)

    # Declared must match the table for the active brand.
    assert audi["declared"] == DECLARED_CAPABILITIES["audi"]


def test_snapshot_observes_charging_when_battery_soc_set() -> None:
    """Charging is observed=True when at least one VIN has battery_soc set.

    This is the canonical positive-path: parser populated the field on
    a real poll so the integration's pipeline understood the response.
    """
    coord = _make_coordinator(brand="audi")
    coord.vehicles = {
        "WAUZZZ1234567890A": {
            "vin": "WAUZZZ1234567890A",
            "battery_soc": 82,
            "charging_state": "notReadyForCharging",
        },
    }
    snap = coord.capabilities_snapshot()
    assert snap["audi"]["observed"]["charging"] is True


def test_snapshot_observes_false_when_field_is_none() -> None:
    """When the parser never populated the canonical field on any VIN,
    observed must be False - the brand declared support but we never
    saw the data."""
    coord = _make_coordinator(brand="audi")
    coord.vehicles = {
        "WAUZZZ1234567890A": {
            "vin": "WAUZZZ1234567890A",
            "battery_soc": None,
            "charging_state": None,
            "is_charging": None,
        },
    }
    snap = coord.capabilities_snapshot()
    assert snap["audi"]["observed"]["charging"] is False


# ── Spec #3: drift flags declared-True but observed-False ─────────────


def test_drift_lists_declared_true_observed_false_capabilities() -> None:
    """Drift must surface capabilities the integration declared but did
    not observe - that's the diagnostics signal for "parser broke" or
    "subscription missing"."""
    coord = _make_coordinator(brand="audi")
    # No vehicles -> nothing observed. Every declared=True capability
    # for Audi should appear in drift (minus the push/auth ones which
    # depend on coordinator-level state).
    coord.vehicles = {}
    snap = coord.capabilities_snapshot()
    drift = snap["audi"]["drift"]

    # All vehicle-data capabilities declared True must drift when there
    # is no vehicle data at all.
    for key in ("auxiliary_heating", "charging", "climatisation",
                "trip_statistics", "brake_service"):
        if DECLARED_CAPABILITIES["audi"].get(key) is True:
            assert key in drift, (
                f"{key} declared True for audi but missing from drift "
                f"when no vehicles are loaded"
            )


def test_drift_excludes_declared_false_capabilities() -> None:
    """A capability declared as False MUST NOT appear in drift, even if
    we have no observation - "we never claimed to support it" is not a
    bug."""
    coord = _make_coordinator(brand="audi")
    coord.vehicles = {}
    snap = coord.capabilities_snapshot()

    # ola_push is declared False for audi - it must not drift.
    assert DECLARED_CAPABILITIES["audi"]["ola_push"] is False
    assert "ola_push" not in snap["audi"]["drift"]


def test_drift_clears_when_capability_observed() -> None:
    """When the parser populates the canonical field, drift must drop
    the capability - the regression test for "did my fix actually
    fix it?"."""
    coord = _make_coordinator(brand="audi")
    coord.vehicles = {
        "WAUZZZ1234567890A": {
            "vin": "WAUZZZ1234567890A",
            "battery_soc": 73,  # charging observed
            "climatisation_state": "ventilation",  # climatisation observed
        },
    }
    snap = coord.capabilities_snapshot()
    assert "charging" not in snap["audi"]["drift"]
    assert "climatisation" not in snap["audi"]["drift"]


# ── Spec #4: unknown brand falls through without crashing ─────────────


def test_unknown_brand_returns_empty_declared_without_crashing() -> None:
    """A brand not in DECLARED_CAPABILITIES must still produce a
    well-formed snapshot. Empty declared, observed runs as normal,
    drift stays empty (nothing declared = nothing can drift)."""
    # v2.14.11 — "bentley" is now a declared brand; use a genuinely-unknown
    # brand-id to exercise the empty-declared path.
    coord = _make_coordinator(brand="acme_unknown")
    snap = coord.capabilities_snapshot()

    assert "acme_unknown" in snap
    unknown = snap["acme_unknown"]
    assert unknown["declared"] == {}
    assert isinstance(unknown["observed"], dict)
    assert unknown["drift"] == []


def test_empty_brand_string_returns_well_formed_snapshot() -> None:
    """Edge case: entry.data has no brand at all. Snapshot must not
    raise - the diagnostics export depends on this contract."""
    coord = _make_coordinator(brand="")
    snap = coord.capabilities_snapshot()
    assert "" in snap
    assert snap[""]["declared"] == {}
    assert snap[""]["drift"] == []


# ── push/auth observed-channel sanity ─────────────────────────────────


def test_observed_fcm_push_true_when_manager_initialised() -> None:
    """fcm_push observed must flip True once the push-manager slot is
    populated - validates the coordinator-level introspection path."""
    coord = _make_coordinator(brand="audi")
    assert coord.capabilities_snapshot()["audi"]["observed"]["fcm_push"] is False

    coord._audi_vw_push = MagicMock()  # simulate manager started
    assert coord.capabilities_snapshot()["audi"]["observed"]["fcm_push"] is True


def test_observed_mqtt_push_true_when_skoda_manager_initialised() -> None:
    """mqtt_push is the Skoda channel - observed flips on _skoda_push."""
    coord = _make_coordinator(brand="skoda")
    assert coord.capabilities_snapshot()["skoda"]["observed"]["mqtt_push"] is False

    coord._skoda_push = MagicMock()
    assert coord.capabilities_snapshot()["skoda"]["observed"]["mqtt_push"] is True
