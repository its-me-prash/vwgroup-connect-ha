# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#1655 + 9 — ``cycle_data_mileage``, the third trip-computer memory.

Ten reports from seven accounts (#1492 @4ndy-bo, #1592 + #1578 @iansyder8,
#1603 @checkner89, #1579 @DanyZdog93, #1655 @user222008, #1681/#1682/#1683
@Nicohlav, #1687 @Neurupp2) and the leaf is in NONE of the 6610 entries of the
official V6.0 portal catalogue, so it was held unmapped rather than given a
guessed unit. Two findings resolved it:

1. **It accumulates while driving.** @iansyder8 reported the same car twice on
   one day: 26432 at 14:25 UTC (#1578) and 26448 at 20:00 UTC (#1592). Not an
   index, not a status code, not a countdown.
2. **The catalogue documents its two siblings.** ``short_term_data_mileage`` and
   ``long_term_data_mileage`` — "Overall Mileage for short/long term trips",
   unit **km**, category "Trip Statistics". Both are already mapped in the
   parser with NO scale factor, so the third member of the ``*_data_mileage``
   scheme is read the same way. (The ``*_distance`` siblings are the 100 m ones
   — a different suffix; conflating them would be a factor-10 error, which is
   what the no-scaling test below pins.)

Still open, and the reason the entity is MEASUREMENT rather than
TOTAL_INCREASING: whether this memory can be reset in the car (asked in #1578).
"""
from __future__ import annotations

import glob
import json
import os

from custom_components.vag_connect.cariad.auth._eu_data_act import (
    _walk_fields,
    map_dataset_to_vehicle_data,
)
from custom_components.vag_connect.cariad.models import VehicleData

# The real reported values, per reporter.
REPORTED = {
    "#1492 @4ndy-bo": "784",
    "#1592 @iansyder8 (20:00 UTC)": "26448",
    "#1578 @iansyder8 (14:25 UTC)": "26432",
    "#1603 @checkner89": "465",
    "#1579 @DanyZdog93": "141",
    "#1655 @user222008": "109",
    "#1681 @Nicohlav": "1830",
    "#1687 @Neurupp2": "43",
}


def _map(payload: dict, base: VehicleData | None = None) -> VehicleData:
    syn: dict = {}
    flat = _walk_fields(payload, None, syn)
    return map_dataset_to_vehicle_data(
        flat, base or VehicleData(vin="X"), field_syn=syn
    )


def test_every_reported_value_maps_as_kilometres_unscaled() -> None:
    for who, raw in REPORTED.items():
        d = _map({"cycle_data_mileage": raw})
        assert d.cyclic_trip_distance_km == float(raw), who


def test_no_scale_factor_is_applied() -> None:
    """The guard against reading the ``*_distance`` (100 m) convention into the
    ``*_mileage`` (km) one — a factor-10 error that would look plausible."""
    d = _map({"cycle_data_mileage": "26432"})
    assert d.cyclic_trip_distance_km == 26432.0
    assert d.cyclic_trip_distance_km != 2643.2


def test_the_two_samples_from_one_car_preserve_the_evidence() -> None:
    """@iansyder8's pair is the evidence that it ACCUMULATES: +16 over five and a
    half hours on one car. The mapping must carry that delta through untouched —
    any scaling or rounding would destroy the one measurement that settled what
    kind of quantity this is."""
    earlier = _map({"cycle_data_mileage": "26432"}).cyclic_trip_distance_km
    later = _map({"cycle_data_mileage": "26448"}).cyclic_trip_distance_km
    assert (earlier, later) == (26432.0, 26448.0)
    assert later - earlier == 16.0


def test_a_car_that_declares_miles_is_not_converted() -> None:
    """A DECISION, pinned so a future "fix" fails loudly.

    A review of this change argued the value should go through the portal's
    miles→km post-process. The official catalogue says otherwise: unit
    companions exist for exactly four fields (``mileage.unit``,
    ``distance.unit`` and the two cruising-range units), which is why ``mileage``
    itself is documented with NO unit — while every ``*_data_mileage`` field
    documents a FIXED ``km``. Converting this one on a miles car would create
    the 1.6x error, not remove it. The odometer beside it IS converted, and that
    difference is the point.
    """
    d = _map({
        "distance_unit": "miles",
        "mileage": "26500",
        "cycle_data_mileage": "26432",
    })
    assert d.odometer_km == round(26500 * 1.60934)   # unit-companion field
    assert d.cyclic_trip_distance_km == 26432.0        # fixed-km field


def test_the_prefixed_spelling_maps_too() -> None:
    d = _map({"eu_data_act": {"cycle_data_mileage": "1830"}})
    assert d.cyclic_trip_distance_km == 1830.0


def test_it_no_longer_floods_the_scout() -> None:
    """The whole reason it is mapped: an unconsumed leaf is re-reported on every
    poll, which is what produced ten issues."""
    for payload in (
        {"cycle_data_mileage": "109"},
        {"eu_data_act": {"cycle_data_mileage": "109"}},
    ):
        d = _map(payload)
        leaves = {k.rsplit(".", 1)[-1] for k in (d.raw_unmapped_fields or {})}
        assert "cycle_data_mileage" not in leaves, payload


def test_the_odometer_is_not_filled_from_it() -> None:
    """A trip memory and the odometer are different quantities, and this one may
    be resettable — filling the odometer from it would be a confident wrong
    answer on every car whose memory has been cleared."""
    d = _map({"cycle_data_mileage": "26432"})
    assert d.odometer_km is None
    assert d.lifetime_trip_distance_km is None
    assert d.last_trip_distance_km is None


def test_a_value_already_present_wins() -> None:
    base = VehicleData(vin="X")
    base.cyclic_trip_distance_km = 999.0
    assert _map({"cycle_data_mileage": "26432"}, base).cyclic_trip_distance_km == 999.0


def test_the_minus_one_not_set_sentinel_is_dropped() -> None:
    """#764 (Motii08): this family ships -1 as "not set yet", and it leaked
    -1 km onto a start odometer once already. Screened by
    ``drop_odometer_sentinel`` (negative → None), which is also why this
    mapping carries no separate ``>= 0`` check — one would be dead code."""
    for negative in ("-1", "-0.5", "-26432"):
        assert _map({"cycle_data_mileage": negative}).cyclic_trip_distance_km is None


def test_it_is_carried_forward_like_its_lifetime_siblings() -> None:
    """The portal re-sends the whole trip block when it has one, so a poll that
    omits the block must not blank this to "unknown" — the #1310 reasoning that
    put the lifetime_* memories in the carry-forward set. Found missing by an
    adversarial review of this change."""
    from custom_components.vag_connect.cariad.vehicle_cache import (
        CARRY_FORWARD_FIELDS,
        MONOTONIC_INCREASING_FIELDS,
    )

    assert "cyclic_trip_distance_km" in CARRY_FORWARD_FIELDS
    # ...but NOT monotonic: if the memory turns out to be resettable, a genuine
    # reset has to win instead of being latched at the old high value.
    assert "cyclic_trip_distance_km" not in MONOTONIC_INCREASING_FIELDS


def test_the_uint32_sentinels_are_dropped() -> None:
    for sentinel in ("4294967295", "2147483647", "429496729"):
        d = _map({"cycle_data_mileage": sentinel})
        assert d.cyclic_trip_distance_km is None, sentinel


def test_sixty_five_thousand_is_a_real_reading_not_a_sentinel() -> None:
    """65535 is VW's uint16 "no reading" marker on BOUNDED fields, but a car
    sitting at exactly 65,535 km is perfectly plausible — the parser's
    mileage/odometer carve-out must keep it."""
    assert _map({"cycle_data_mileage": "65535"}).cyclic_trip_distance_km == 65535.0


def test_garbage_does_not_raise_or_map() -> None:
    for raw in ("", "   ", "n/a", "NaN", "inf", "-inf", "Infinity"):
        d = _map({"cycle_data_mileage": raw})
        assert d.cyclic_trip_distance_km is None, raw


def test_the_sibling_memories_still_map() -> None:
    """Regression guard: the new block sits inside the trip-computer family, so
    the two catalogue-documented siblings must keep working unchanged."""
    d = _map({
        "short_term_data_mileage": "120",
        "long_term_data_mileage": "26000",
        "short_term_data_start_mileage": "25880",
        "cycle_data_mileage": "1830",
    })
    assert d.last_trip_distance_km == 120
    assert d.lifetime_trip_distance_km == 26000
    assert d.last_trip_start_odometer_km == 25880
    assert d.cyclic_trip_distance_km == 1830


def test_it_is_in_the_diagnostics_dump() -> None:
    assert _map({"cycle_data_mileage": "43"}).to_dict()["cyclic_trip_distance_km"] == 43


def test_the_sensor_is_measurement_until_the_reset_question_is_answered() -> None:
    """The sibling entities split exactly along "does it reset": the lifetime
    memory is TOTAL_INCREASING, the per-trip one is MEASUREMENT. We do not know
    which this is, and TOTAL_INCREASING would publish a statistics SUM that
    silently double-counts distance if the memory turns out to be resettable.
    Changing this to TOTAL_INCREASING should fail until #1578 is answered.
    """
    from homeassistant.components.sensor import (
        SensorDeviceClass,
        SensorStateClass,
    )
    from homeassistant.const import UnitOfLength

    from custom_components.vag_connect.sensor import (
        _DATA_PRESENT_REQUIRED,
        SENSOR_DESCRIPTIONS,
    )

    d = next(x for x in SENSOR_DESCRIPTIONS if x.key == "cyclic_trip_distance_km")
    assert d.data_key == "cyclic_trip_distance_km"
    assert d.native_unit_of_measurement == UnitOfLength.KILOMETERS
    assert d.device_class == SensorDeviceClass.DISTANCE
    assert d.state_class == SensorStateClass.MEASUREMENT
    # This used to assert entity_registry_enabled_default is False. That
    # caution was for a field nobody had seen on a real car yet; it has been
    # read on several since, and @fschulte2812 went looking for the entity
    # and could not find it. The presentation now matches its two siblings,
    # asserted for all three in test_1655_trip_memories_are_consistent.py.
    # portal-only leaf → gated, so no phantom "unknown" entity elsewhere
    assert "cyclic_trip_distance_km" in _DATA_PRESENT_REQUIRED


def test_the_entity_name_names_the_refuel_memory_in_every_language() -> None:
    """The name follows the manufacturer's OWN label for this memory ("From
    refuelling" / "All journeys between two fill-ups", from the app's decoded
    string resources, key family ``..._rts_cyclicTrips*``), independently
    identified by @DanyZdog93 from his dashboard. So every translation has to
    name the refuel/fill-up concept rather than the raw field name — a generic
    "cycle distance" would throw that grounding away.
    """
    base = os.path.join(
        os.path.dirname(__file__), "..", "custom_components", "vag_connect"
    )
    #: the refuel/fill-up word each language uses
    word = {
        "strings": "refuel", "en": "refuel", "de": "tanken", "nl": "tanken",
        "fr": "plein", "it": "rifornimento", "es": "repostaje",
        "cs": "tankov", "da": "optankning", "fi": "tankkauksesta",
        "nb": "fylling", "pl": "tankowania", "sv": "tankning",
    }
    files = [os.path.join(base, "strings.json")] + glob.glob(
        os.path.join(base, "translations", "*.json")
    )
    assert len(files) >= 13, files
    for f in files:
        with open(f, encoding="utf-8") as fh:
            sensor = json.load(fh)["entity"]["sensor"]
        lang = os.path.splitext(os.path.basename(f))[0]
        name = sensor["cyclic_trip_distance_km"]["name"]
        assert word[lang] in name.lower(), (f, name, word[lang])


def test_the_name_is_translated_everywhere() -> None:
    base = os.path.join(
        os.path.dirname(__file__), "..", "custom_components", "vag_connect"
    )
    files = [os.path.join(base, "strings.json")] + glob.glob(
        os.path.join(base, "translations", "*.json")
    )
    assert len(files) >= 13, files
    for f in files:
        with open(f, encoding="utf-8") as fh:
            sensor = json.load(fh)["entity"]["sensor"]
        assert "cyclic_trip_distance_km" in sensor, f
        name = sensor["cyclic_trip_distance_km"]["name"]
        assert isinstance(name, str) and name.strip(), f
