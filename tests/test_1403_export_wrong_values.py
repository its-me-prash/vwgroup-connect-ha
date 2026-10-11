# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#1403 grounding — four wrong values the portal mapper published, found while
tracing why @placidcasual98's one-time export produced no battery entity.

None of these is the #1403 bug itself. They were measured on the way to it, and
each one publishes a confidently WRONG reading rather than an absent one, which
is why they are fixed first and pinned here.

1. **No plausibility screen on the SoC leaf chain.** ``soc=255`` — the classic
   CAN "signal not available" byte — was published verbatim as ``battery_soc``,
   on a sensor declaring ``device_class=BATTERY`` and
   ``state_class=MEASUREMENT``, so the nonsense also entered long-term
   statistics. The VALID-gated ``battery_level_HV`` pair already screened its
   own value with exactly ``0 <= v <= 100``; the leaf chain never did.

2. **A petrol car read as electric.** The nested export shape ships
   ``batteryStatus.cruisingRange.{range,engineType}`` and the walker emits the
   bare leaves beside the dotted names. Bare ``range`` is the first alias of the
   headline range chain, while neither engine-type spelling is in the
   orientation gate — so a dataset that says PETROL had its range copied onto
   the EV range sensor, with ``has_battery`` and ``is_electric`` both True.

3. **A connected plug reported "not connected".** The plug value never passed
   through ``_shorten_enum``, so ``PLUG_CONNECTION_STATE_CONNECTED`` was
   compared against ``("connected", ...)`` and matched nothing — ``False``, not
   ``None``. The documented ``_INVALID`` token became a confident False too.

4. **A dead alias spelling.** ``targetSOC_pct`` (capital O-C) appears in no
   catalogue entry in any spelling, so on an exact lookup it could never match a
   real car. The one-time export's actual name is ``targetSoc_pct``
   (catalogue 5ec53403).

The regression half matters as much as the fix half: the engine-type reading is
deliberately scoped to the range fallback instead of widening the shared
orientation gate, because widening it was measured to flip the combustion-primary
PHEVs (#555/#565) back to the swapped ranges they were fixed for. Those cars are
pinned below and must not move.
"""
from __future__ import annotations

import pytest

from custom_components.vag_connect.cariad.auth._eu_data_act import (
    _walk_fields,
    map_dataset_to_vehicle_data,
)
from custom_components.vag_connect.cariad.models import VehicleData


def _map(fields: dict, *, nested: dict | None = None) -> VehicleData:
    """Map through the REAL portal envelope and the production call shape.

    The portal sends a ``Data`` list of ``{dataFieldName, value}`` records whose
    names are the dotted catalogue paths (see test_1780 — building a nested
    shape where the portal sends a flat list produced tests that failed against
    correct code). ``nested`` covers the other real shape, the structured
    member, which is what makes the walker emit bare leaves at all.

    All four companion dicts are passed because production does
    (``get_vehicle_data`` and ``parse_export_zip`` both do): a harness that
    omits them silently disables the timestamp-aware resolution and measures a
    different mapper than the one that ships.
    """
    payload: dict = nested if nested is not None else {
        "Data": [
            {"dataFieldName": name, "value": value}
            for name, value in fields.items()
        ]
    }
    ts: dict = {}
    syn: dict = {}
    contested: dict = {}
    uuids: dict = {}
    walked = _walk_fields(payload, ts, syn, contested, uuids)
    return map_dataset_to_vehicle_data(
        walked, VehicleData(vin="TESTVIN0000000001"), ts, syn, contested, uuids
    )


# ── 1. SoC plausibility ──────────────────────────────────────────────────────

@pytest.mark.parametrize("raw", ["255", "310", "101", "-5"])
def test_implausible_soc_is_dropped_not_published(raw: str) -> None:
    """A percentage outside 0..100 is not a reading, so nothing is published.

    FAILS BEFORE THE FIX: every one of these came through verbatim
    (measured 255 -> 255, 310 -> 310).
    """
    d = _map({"soc": raw})
    assert d.battery_soc is None
    # The drivetrain flag is derived from the SoC, so a dropped reading must not
    # leave a phantom battery behind on a car that reported nothing valid.
    assert d.has_battery is False


@pytest.mark.parametrize("raw,expected", [("0", 0), ("1", 1), ("31", 31), ("100", 100)])
def test_plausible_soc_still_published_including_both_bounds(
    raw: str, expected: int
) -> None:
    """The screen is inclusive: 0 % and 100 % are both real readings.

    An exclusive bound would blank a fully charged car and an empty one — the
    two states an owner is most likely to be looking at.
    """
    d = _map({"soc": raw})
    assert d.battery_soc == expected
    assert d.has_battery is True


def test_garbage_leaf_does_not_mask_a_valid_hv_pair() -> None:
    """Screening happens before the HV/leaf choice, not after it.

    A car shipping a nonsense leaf next to a VALID ``battery_level_HV`` pair
    must still publish the HV value. Screening the resolved value instead would
    have thrown away a perfectly good reading because of its stale neighbour.
    """
    d = _map({
        "soc": "255",
        "battery_level_HV.value": "36",
        "battery_level_HV.state": "VALID",
    })
    assert d.battery_soc == 36
    assert d.battery_soc_from_hv is True


# ── 2. The export states its engine type ─────────────────────────────────────

def test_nested_export_petrol_range_is_not_electric() -> None:
    """The structured export member: PETROL range must not land on the EV sensor.

    FAILS BEFORE THE FIX: measured electric_range_km=380, has_battery=True,
    is_electric=True on exactly this payload.
    """
    d = _map({}, nested={
        "batteryStatus": {
            "cruisingRange": {
                "range": "380",
                "engineType": "ENGINE_TYPE_PETROL_GASOLINE",
            }
        }
    })
    assert d.range_km == 380
    assert d.electric_range_km is None
    # Honest placement: it IS this car's range, just not an electric one.
    assert d.combustion_range_km == 380
    assert d.has_battery is False
    assert d.is_electric is False


def test_flat_export_engine_type_counts_too() -> None:
    """The flat ``Data``-list shape carries the same leaf and must behave alike."""
    d = _map({"range": "380", "engineType": "ENGINE_TYPE_PETROL_DIESEL"})
    assert d.electric_range_km is None
    assert d.combustion_range_km == 380
    assert d.has_battery is False


@pytest.mark.parametrize("fields", [
    {"range": "300"},
    {"range": "300", "engineType": "ENGINE_TYPE_ELECTRIC"},
    {"range": "300", "soc": "62"},
    {"primaryEngineRange": "148", "soc": "31"},
])
def test_battery_electric_cars_are_untouched(fields: dict) -> None:
    """A BEV's single range stays the electric range, exactly as before."""
    d = _map(fields)
    assert d.electric_range_km == int(fields.get("range", fields.get("primaryEngineRange")))
    assert d.combustion_range_km is None
    assert d.is_electric is True


@pytest.mark.parametrize("extra", [
    {},
    {"engineType": "ENGINE_TYPE_ELECTRIC"},
    {"engine_type": "ENGINE_TYPE_PETROL_GASOLINE"},
])
def test_combustion_primary_phev_does_not_move(extra: dict) -> None:
    """#555/#565 regression guard: the GTE-class swap fix must be untouched.

    These cars resolve their orientation from the live dialect (an explicit
    ``engine_type``, or a secondary range plus a fuel reading), so their
    electric range is already set from the SECONDARY range before the range
    fallback is reached. Adding the export's per-engine ``engineType`` to the
    shared orientation gate was measured to break precisely this, which is why
    the new read is scoped to the fallback. The third case carries both
    dialects' engine-type leaves at once.
    """
    d = _map({
        "cruising_range_primary_engine": "380",
        "cruising_range_secondary_engine": "20",
        "fuel_level": "55",
        **extra,
    })
    assert d.combustion_range_km == 380
    assert d.electric_range_km == 20
    assert d.is_hybrid is True
    assert d.fuel_level == 55


# ── 3. Plug connection state ─────────────────────────────────────────────────

def test_connected_plug_reads_connected() -> None:
    """FAILS BEFORE THE FIX: measured plug_connected=False on this exact token,
    which is @placidcasual98's own export value."""
    d = _map({"plugConnectionState": "PLUG_CONNECTION_STATE_CONNECTED"})
    assert d.plug_connected is True
    # And the label is shortened like every sibling enum in the mapper.
    assert d.plug_state == "CONNECTED"


def test_disconnected_plug_reads_disconnected() -> None:
    d = _map({"plugConnectionState": "PLUG_CONNECTION_STATE_DISCONNECTED"})
    assert d.plug_connected is False
    assert d.plug_state == "DISCONNECTED"


def test_invalid_plug_token_is_not_a_confident_false() -> None:
    """``_INVALID`` is a documented no-reading token.

    Reporting it as "not connected" tells an owner their cable is out when the
    car never said so — the same reasoning as the UNSUPPORTED/INVALID handling
    pinned in test_1780.
    """
    d = _map({"plugConnectionState": "PLUG_CONNECTION_STATE_INVALID"})
    assert d.plug_connected is None
    assert d.plug_state is None


def test_already_short_plug_tokens_still_work() -> None:
    """Regression guard: cars that ship the bare token are unaffected."""
    assert _map({"plug_connection_state": "connected"}).plug_connected is True
    assert _map({"plug_connection_state": "disconnected"}).plug_connected is False


def test_export_container_spelling_of_the_plug_state() -> None:
    """``plugStatusItem.plugConnectionState`` is the one-time export's name for
    the same datum (catalogue 17e75411) and was not in the alias list."""
    d = _map({"plugStatusItem.plugConnectionState": "PLUG_CONNECTION_STATE_CONNECTED"})
    assert d.plug_connected is True
    assert d.plug_state == "CONNECTED"


# ── 4. The target-SoC spelling the catalogue actually carries ────────────────

def test_catalogue_target_soc_spelling_resolves() -> None:
    """FAILS BEFORE THE FIX: ``targetSoc_pct`` was in no alias list, and the
    spelling that was there (``targetSOC_pct``) is in no catalogue entry, so no
    real export could ever match it."""
    d = _map({"targetSoc_pct": "80"})
    assert d.target_soc == 80


def test_the_other_target_soc_spellings_are_unchanged() -> None:
    """Appending to a ``first()`` chain is order-safe: the canonical names win."""
    assert _map({"target_soc": "90"}).target_soc == 90
    assert _map({"settings.target_soc": "70", "target_soc": "90"}).target_soc == 70
