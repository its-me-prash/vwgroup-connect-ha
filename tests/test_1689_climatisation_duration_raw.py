# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#1689 + 13 — ``climatisation_settings.duration``, mapped raw on purpose.

Fourteen reports from twelve accounts (#1451 @JuhaKoivisto, #1483 @JanFirlus,
#1503 @supersej, #1504 @StoneH74, #1518 @danilokl, #1527/#1534 @gfro84,
#1529/#1645 @skornehl, #1574 @iluebbe, #1577 @Dirk-fs, #1588 @Schraube11,
#1630 @alfons61, #1689 @mtwes) and the leaf is in none of the 6610 entries of
the official V6.0 catalogue. A run length, a configured timer length and a
remaining time would each want a different sensor AND a different unit, so the
value is surfaced raw — unitless, no device class, no state class — rather than
given an invented meaning. All fourteen reports read ``0``, and in the seven
that also carried ``climatisation_state`` it was OFF, which points at a run-time
without proving it; the other seven did not list the state (it is mapped on
their version), so theirs is unknown rather than different.

The sharp part of this change is the candidate list. The flattener emits a BARE
``duration`` leaf alongside the qualified path, and "duration" is generic enough
that a SECOND node can carry it — in which case the bare leaf holds the other
node's last-wins value. So the bare spelling is deliberately NOT a value
candidate, and is only reclaimed from the Scout surface when this node is its
one possible origin. Both halves are pinned below.
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

# @iluebbe (#1574) / @Dirk-fs (#1577): duration=0, target_temperature=120.
# @Schraube11 (#1588): duration=0, target_temperature=115.
NESTED_1574 = {
    "climatisation_settings": {"duration": "0", "target_temperature": "120"},
}


def _map(payload: dict, base: VehicleData | None = None) -> VehicleData:
    syn: dict = {}
    flat = _walk_fields(payload, None, syn)
    return map_dataset_to_vehicle_data(
        flat, base or VehicleData(vin="X"), field_syn=syn
    )


def test_the_reported_payload_maps_both_leaves() -> None:
    d = _map(NESTED_1574)
    assert d.climatisation_duration_raw == 0.0
    # the catalogue-documented neighbour keeps its own decode: 120 → 22.0 °C
    assert d.target_temperature == 22.0


def test_schraube11_half_step_still_decodes_beside_it() -> None:
    d = _map({"climatisation_settings": {"duration": "0",
                                         "target_temperature": "115"}})
    assert d.climatisation_duration_raw == 0.0
    assert d.target_temperature == 21.5


def test_a_non_zero_value_maps_unchanged() -> None:
    """No scaling, no unit conversion — the point of a raw value."""
    d = _map({"climatisation_settings": {"duration": "30"}})
    assert d.climatisation_duration_raw == 30.0


def test_the_prefixed_spelling_maps() -> None:
    d = _map({"eu_data_act": {"climatisation_settings": {"duration": "15"}}})
    assert d.climatisation_duration_raw == 15.0


def test_it_no_longer_floods_the_scout() -> None:
    d = _map(NESTED_1574)
    raw = d.raw_unmapped_fields or {}
    leaves = {k.rsplit(".", 1)[-1] for k in raw}
    assert "duration" not in leaves, raw
    assert not [k for k in raw if k.endswith("climatisation_settings.duration")]


def test_a_foreign_nodes_duration_is_never_mapped_here() -> None:
    """The reason the bare leaf is not a value candidate.

    With no climatisation duration present, another node's ``duration`` must not
    land in this field — a plausible-looking number with the wrong meaning is
    undetectable in a sensor whose unit is already unknown.
    """
    d = _map({"charging_timer": {"duration": "45"}})
    assert d.climatisation_duration_raw is None


def test_a_foreign_nodes_duration_stays_visible_for_discovery() -> None:
    """...and it must still reach the Scout, or we would be suppressing a
    genuinely undiscovered field."""
    d = _map({"charging_timer": {"duration": "45"}})
    assert "charging_timer.duration" in (d.raw_unmapped_fields or {})


def test_with_two_duration_nodes_the_climate_one_is_read_and_the_other_kept() -> None:
    d = _map({
        "climatisation_settings": {"duration": "0"},
        "charging_timer": {"duration": "45"},
    })
    # value comes from the qualified climate path, never from the ambiguous twin
    assert d.climatisation_duration_raw == 0.0
    raw = d.raw_unmapped_fields or {}
    # the other node keeps its own qualified path on the Scout surface
    assert "charging_timer.duration" in raw
    # and because a second origin exists, the ambiguous bare twin is NOT
    # reclaimed — silencing it could hide the other node's datum
    assert "duration" in raw


def test_a_root_level_duration_is_another_node_not_our_twin() -> None:
    """Found by an adversarial review of this change, and reproduced.

    The walker emits the bare twin UNPREFIXED, so a key spelled
    ``eu_data_act.duration`` can only be a ``duration`` sitting directly under
    the dataset root — a different reading. The first version of the reclaim
    exempted that spelling from the other-origin scan and then consumed it, so a
    root-level 45 vanished from the Scout while being mapped nowhere: hidden,
    which is the one thing the house rule forbids.
    """
    d = _map({"eu_data_act": {"duration": "45",
                              "climatisation_settings": {"duration": "0"}}})
    assert d.climatisation_duration_raw == 0.0          # ours, from the node
    raw = d.raw_unmapped_fields or {}
    assert raw.get("eu_data_act.duration") == "45", raw  # theirs, still visible


def test_a_foreign_bare_only_duration_is_not_consumed_as_the_twin() -> None:
    """The second hole the review found: two shapes emit a foreign ``duration``
    with NO dotted spelling for the other-origin scan to see — a data point
    whose field name is plainly "duration", and a node inside an array. The
    bare leaf then holds the FOREIGN value, so value equality is what separates
    a twin from someone else's reading."""
    d = _map({
        "climatisation_settings": {"duration": "0"},
        "data": [{"dataFieldName": "duration", "value": "1234",
                  "carCapturedTimestamp": "2026-10-02T10:00:00Z"}],
    })
    assert d.climatisation_duration_raw == 0.0
    assert (d.raw_unmapped_fields or {}).get("duration") == "1234"


def test_an_array_nested_foreign_duration_blocks_the_reclaim() -> None:
    d = _map({
        "climatisation_settings": {"duration": "0"},
        "timers": [{"duration": "99"}],
    })
    assert d.climatisation_duration_raw == 0.0
    raw = d.raw_unmapped_fields or {}
    assert raw.get("timers.duration") == "99"
    assert "duration" in raw


def test_the_catalogue_documented_minute_field_is_not_touched() -> None:
    """``climate_remaining_time_min`` is documented in minutes; filling it from
    an unknown unit would clobber a known-good value with a guess."""
    d = _map({"climatisation_settings": {"duration": "30"}})
    assert d.climate_remaining_time_min is None


def test_a_value_already_present_wins() -> None:
    base = VehicleData(vin="X")
    base.climatisation_duration_raw = 7.0
    assert _map(NESTED_1574, base).climatisation_duration_raw == 7.0


def test_garbage_does_not_raise_or_map() -> None:
    for raw in ("", "  ", "n/a", "NaN", "inf", "-inf"):
        d = _map({"climatisation_settings": {"duration": raw}})
        assert d.climatisation_duration_raw is None, raw


def test_it_is_in_the_diagnostics_dump() -> None:
    assert _map(NESTED_1574).to_dict()["climatisation_duration_raw"] == 0.0


def test_the_sensor_claims_no_unit_and_no_statistics() -> None:
    from custom_components.vag_connect.sensor import (
        _DATA_PRESENT_REQUIRED,
        SENSOR_DESCRIPTIONS,
    )

    d = next(
        x for x in SENSOR_DESCRIPTIONS if x.key == "climatisation_duration_raw"
    )
    assert d.data_key == "climatisation_duration_raw"
    # unknown unit → no unit, no device class, and no long-term statistics
    assert d.native_unit_of_measurement is None
    assert d.device_class is None
    assert d.state_class is None
    assert d.entity_registry_enabled_default is False
    assert "climatisation_duration_raw" in _DATA_PRESENT_REQUIRED


#: the word each language uses for "raw" in the entity name. A name that reads
#: like minutes would undo the honesty of an unknown-unit value, so the
#: qualifier is checked per language rather than just "has brackets".
RAW_WORD = {
    "strings": "raw", "en": "raw", "de": "rohwert", "nl": "ruw",
    "fr": "brute", "it": "grezza", "es": "bruta", "cs": "nezpracovan",
    "da": "rå", "fi": "raaka", "nb": "rå", "pl": "surowy", "sv": "rå",
}


def test_the_name_says_raw_in_every_language() -> None:
    base = os.path.join(
        os.path.dirname(__file__), "..", "custom_components", "vag_connect"
    )
    files = [os.path.join(base, "strings.json")] + glob.glob(
        os.path.join(base, "translations", "*.json")
    )
    assert len(files) >= 13, files
    seen = set()
    for f in files:
        with open(f, encoding="utf-8") as fh:
            sensor = json.load(fh)["entity"]["sensor"]
        assert "climatisation_duration_raw" in sensor, f
        name = sensor["climatisation_duration_raw"]["name"]
        assert isinstance(name, str) and name.strip(), f
        lang = os.path.splitext(os.path.basename(f))[0]
        lang = "strings" if lang == "strings" else lang
        seen.add(lang)
        word = RAW_WORD[lang]
        assert word in name.lower(), (f, name, word)
        # the qualifier must be set off, not read as part of the quantity
        assert "(" in name and ")" in name, (f, name)
    assert seen >= set(RAW_WORD), set(RAW_WORD) - seen
