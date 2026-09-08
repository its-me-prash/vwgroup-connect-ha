# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#1316 (EcksteinU, VW T6.1 Kombi 2.0 TDI on the Nutzfahrzeuge EU-DA feed) —
a pure-combustion vehicle picked up a PHANTOM electric range and was mislabelled
hybrid.

The diagnostics showed a diesel Transporter (AdBlue 21500 km, fuel_level 80,
combustion_range 790, NO battery_soc, NO charging_state) reporting
``electric_range_km = 710`` and ``is_hybrid = True`` / ``has_battery = True``.

Root cause: the portal ships two range figures (a headline ``range`` plus the
primary-engine range, or a spurious secondary). The b14 range block mirrors one
of them onto ``electric_range_km`` when it is still None, and the b1/B3
drivetrain derivation then reads that phantom value as electric evidence →
has_battery → is_hybrid.

Fix: a combustion-only car (fuel present, no HV SoC, no charging, no secondary
engine range, no electric ``engine_type`` token) keeps ``electric_range_km``
None; the mislabelled range is reclaimed as the combustion range when that slot
is empty. BEV-safe — a BEV never reports a fuel reading.
"""
from __future__ import annotations

from custom_components.vag_connect.cariad.auth._eu_data_act import (
    map_dataset_to_vehicle_data,
)
from custom_components.vag_connect.cariad.models import VehicleData


def _map(fields: dict) -> VehicleData:
    return map_dataset_to_vehicle_data(fields, VehicleData(vin="X"))


# ── the reported car: diesel with an explicit engine_type + a bare range ──────
def test_diesel_with_engine_type_and_bare_range_is_not_hybrid() -> None:
    """Path A — engine_type names DIESEL, combustion range comes from the primary
    engine, and a separate headline ``range`` leaks onto electric via the
    fallback. electric must be suppressed; combustion is already set."""
    d = _map({
        "engine_type": "ENGINE_TYPE_PETROL_DIESEL",
        "cruising_range_primary_engine": "790",
        "range": "710",
        "fuel_level": "80",
        "adblue_range": "21500",
    })
    assert d.combustion_range_km == 790
    assert d.electric_range_km is None
    assert d.has_combustion is True
    assert d.has_battery is False
    assert d.is_hybrid is False
    assert d.is_electric is False


def test_diesel_without_engine_type_reclaims_range_as_combustion() -> None:
    """Path B — no engine_type token, only a single primary range + fuel. The old
    orientation default mapped the primary range to electric; the phantom is
    reclaimed as the combustion range and electric cleared."""
    d = _map({
        "cruising_range_primary_engine": "790",
        "fuel_level": "80",
    })
    assert d.electric_range_km is None
    assert d.combustion_range_km == 790
    assert d.has_combustion is True
    assert d.has_battery is False
    assert d.is_hybrid is False


# ── regression locks: genuine electric drivetrains must be untouched ──────────
def test_real_phev_petrol_with_secondary_electric_keeps_electric_range() -> None:
    """#1220 shape — a combustion-primary PHEV (PETROL engine_type + fuel + a real
    SECONDARY electric range) genuinely has an electric range. The suppression
    must NOT fire because a secondary engine range is present."""
    d = _map({
        "engine_type": "ENGINE_TYPE_PETROL_GASOLINE",
        "cruising_range_primary_engine": "40",
        "cruising_range_secondary_engine": "500",
        "fuel_level": "60",
    })
    assert d.combustion_range_km == 40
    assert d.electric_range_km == 500
    assert d.is_hybrid is True
    assert d.has_battery is True


def test_phev_with_soc_and_fuel_keeps_electric() -> None:
    """A PHEV that reports HV SoC + fuel is genuine electric evidence; the guard
    must not touch its electric range even without an engine_type token."""
    d = _map({
        "soc": "57",
        "fuel_level_current_level": "59",
        "cruising_range_primary_engine": "380",
        "cruising_range_secondary_engine": "20",
    })
    assert d.electric_range_km == 20
    assert d.combustion_range_km == 380
    assert d.is_hybrid is True


def test_bev_bare_range_still_electric() -> None:
    """A BEV (SoC, no fuel) with only the bare ``range`` keeps the legacy
    range→electric mirror — a BEV never reports fuel, so the guard is inert."""
    d = _map({"soc": "80", "range": "300"})
    assert d.electric_range_km == 300
    assert d.combustion_range_km is None
    assert d.is_electric is True


def test_pure_ice_no_range_stays_clean() -> None:
    """Combustion-only with fuel but no range field at all — no phantom to
    create, drivetrain stays ICE."""
    d = _map({"fuel_level_current_level": "50"})
    assert d.electric_range_km is None
    assert d.has_battery is False
    assert d.is_electric is False
    assert d.has_combustion is True


def test_diesel_with_zero_secondary_range_is_not_hybrid() -> None:
    """The reporter's ACTUAL shape — his diagnostics carried
    ``cruising_range_secondary_engine = 0`` alongside the diesel. A 0 is noise,
    not a second powertrain, so it must NOT count as electric evidence and must
    NOT shield the phantom. (An earlier form of the guard keyed on
    ``secondary_raw is None`` and would have skipped exactly this car.)"""
    d = _map({
        "engine_type": "ENGINE_TYPE_PETROL_DIESEL",
        "cruising_range_primary_engine": "790",
        "cruising_range_secondary_engine": "0",
        "range": "710",
        "fuel_level": "80",
        "adblue_range": "21500",
    })
    assert d.combustion_range_km == 790
    assert d.electric_range_km is None
    assert d.is_hybrid is False
    assert d.has_battery is False


# ── CNG (#1225 VW TGI class) — a natural-gas car is combustion, not hybrid ─────
def test_cng_car_is_not_hybrid() -> None:
    """A CNG car reports its tank as ``cng_gas_level`` (not a liquid-fuel field),
    so the phantom-electric guard must treat the CNG tank as combustion evidence
    too — otherwise the range→electric fallback makes a VW TGI look like a
    plug-in hybrid."""
    d = _map({
        "engine_type": "ENGINE_TYPE_GAS_CNG",
        "cruising_range_primary_engine": "450",
        "cng_gas_level": "60",
    })
    assert d.electric_range_km is None
    assert d.combustion_range_km == 450
    assert d.is_hybrid is False
    assert d.has_battery is False
    assert d.has_combustion is True


def test_real_phev_positive_secondary_survives_even_without_soc() -> None:
    """A genuine combustion-primary PHEV with a POSITIVE secondary electric range
    but no SoC in this poll keeps its electric range — the guard only discounts a
    zero/absent secondary, never a real one."""
    d = _map({
        "engine_type": "ENGINE_TYPE_PETROL_GASOLINE",
        "cruising_range_primary_engine": "600",
        "cruising_range_secondary_engine": "48",
        "fuel_level": "70",
    })
    assert d.electric_range_km == 48
    assert d.combustion_range_km == 600
    assert d.is_hybrid is True


# ── cache carry-forward heal — an already-affected user's snapshot self-cleans ─
class TestPhantomCacheHeal:
    """A user who polled the diesel under the pre-fix build has a cached
    electric_range_km. The fixed mapper yields None, but electric_range_km is a
    carry-forward field, so reconcile would re-latch the phantom forever. The
    heal drops a cached electric range that contradicts the drivetrain."""

    def test_reconcile_drops_contradictory_cached_electric_range(self) -> None:
        from custom_components.vag_connect.cariad.vehicle_cache import reconcile

        previous = {  # what the pre-fix build left in .storage after one post-fix poll
            "electric_range_km": 710,
            "range_km": 710,
            "total_range_km": 710,
            "combustion_range_km": 790,
            "has_battery": False,   # fresh (fixed) value already won here
            "is_hybrid": False,
            "is_electric": False,
            "has_combustion": True,
        }
        fresh = {  # the fixed mapper's fresh poll — no electric range
            "electric_range_km": None,
            "range_km": 710,
            "combustion_range_km": 790,
            "has_battery": False,
            "is_hybrid": False,
            "is_electric": False,
            "has_combustion": True,
        }
        merged, _notes = reconcile(previous, fresh)
        assert merged.get("electric_range_km") is None
        assert merged.get("combustion_range_km") == 790

    def test_reconcile_keeps_real_ev_carried_electric_range(self) -> None:
        """Regression lock: a genuine EV's cached electric range (has_battery
        True) is still carried forward across a partial poll — the heal must not
        touch it."""
        from custom_components.vag_connect.cariad.vehicle_cache import reconcile

        previous = {
            "electric_range_km": 320,
            "has_battery": True,
            "is_electric": True,
            "is_hybrid": False,
            "has_combustion": False,
        }
        fresh = {"electric_range_km": None, "has_battery": True, "is_electric": True}
        merged, _notes = reconcile(previous, fresh)
        assert merged.get("electric_range_km") == 320
