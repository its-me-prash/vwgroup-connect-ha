# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Scout #1757 — the warnings-history timestamp, and the three blanks beside it.

A VW Touareg eHybrid reported four new EU-Data-Act fields. They split cleanly:

* ``history_active_warnings_in_instrument_cluster_fff`` carries an absolute ISO
  timestamp — on every sample we have (#1164, #1230, #1276, #1757) — so it gets
  a sensor of its own. The field catalogue calls this UUID a number; four live
  payloads say otherwise and the code follows the payloads.
* ``first/second/third_active_consumer_`` are zFDI/PPE-only placeholders with no
  meaning and no unit in the catalogue, and every sample is an empty string.
  They get no entity — but they are NOT suppressed: they stay in
  ``raw_unmapped_fields`` and on the raw-fields sensor, so a car that one day
  delivers a real value is still discoverable. Only the user-facing Scout repair
  is skipped, exactly as ``scope_potential_total`` already is.

The tests that matter here are the ones about NOT consuming: a Scout field that
is read but unused disappears from discovery, which is the one outcome the
project's field policy forbids.
"""
from __future__ import annotations

import json
from pathlib import Path

from custom_components.vag_connect.cariad.auth._eu_data_act import (
    map_dataset_to_vehicle_data,
)
from custom_components.vag_connect.cariad.models import VehicleData

_ROOT = Path(__file__).resolve().parents[1] / "custom_components" / "vag_connect"
_LANGS = ("cs", "da", "de", "en", "es", "fi", "fr", "it", "nb", "nl", "pl", "sv")
_HIST = "history_active_warnings_in_instrument_cluster_fff"
_CONSUMERS = (
    "first_active_consumer_",
    "second_active_consumer_",
    "third_active_consumer_",
)


def _map(fields: dict[str, str]) -> VehicleData:
    return map_dataset_to_vehicle_data(dict(fields), VehicleData(vin="X"))


# ── the timestamp ───────────────────────────────────────────────────────────


def test_the_history_field_becomes_a_timestamp() -> None:
    # the exact value from #1757
    d = _map({_HIST: "2026-09-12T14:32:34"})
    assert d.dashboard_warnings_last_at == "2026-09-12T14:32:34"


def test_every_sample_we_have_ever_seen_parses() -> None:
    """#1164, #1230, #1276, #1757 — two with milliseconds, two without."""
    for sample in (
        "2026-08-13T16:52:05",
        "2026-08-08T09:35:18.000",
        "2026-08-19T09:53:51.000",
        "2026-09-12T14:32:34",
    ):
        assert _map({_HIST: sample}).dashboard_warnings_last_at == sample


def test_a_blank_history_value_is_not_a_timestamp() -> None:
    assert _map({_HIST: ""}).dashboard_warnings_last_at is None
    assert _map({_HIST: "   "}).dashboard_warnings_last_at is None


def test_the_mask_and_the_timestamp_stay_separate_fields() -> None:
    """A time and a bitmask are different vocabularies; folding one into the
    other would have made both unreadable."""
    d = _map({
        "active_warnings_in_instrument_cluster_fff": "0x1A",
        _HIST: "2026-09-12T14:32:34",
    })
    assert d.dashboard_warnings_raw == "0x1A"
    assert d.dashboard_warnings_last_at == "2026-09-12T14:32:34"


def test_a_blank_mask_no_longer_lands_as_an_empty_reading() -> None:
    """Found while mapping the sibling: the guard was ``is not None``, so a car
    shipping an empty string set the raw sensor to ``""``."""
    assert _map({"active_warnings_in_instrument_cluster_fff": ""}).dashboard_warnings_raw is None
    assert _map({"active_warnings_in_instrument_cluster_fff": "0x0"}).dashboard_warnings_raw == "0x0"


def test_the_0001_variant_is_left_for_discovery() -> None:
    """It has never been delivered by any car and is declared Boolean. Reading
    it would mark it used and strip it from raw_unmapped_fields — paying the
    discovery for nothing."""
    d = _map({"history_active_warnings_in_instrument_cluster_0001": "true"})
    assert d.dashboard_warnings_last_at is None


# ── the three blanks: skipped repair, kept discovery ────────────────────────


def test_the_consumer_fields_do_not_raise_the_scout_repair() -> None:
    from custom_components.vag_connect.cariad._reporter_pipeline import (
        _SCOUT_REPAIR_SKIP_LEAVES,
        _is_scout_repair_skipped,
    )
    from custom_components.vag_connect.cariad._unexpected_keys import UnexpectedField

    for leaf in _CONSUMERS:
        assert leaf in _SCOUT_REPAIR_SKIP_LEAVES
        field = UnexpectedField(
            path=f"eu_data_act.{leaf}", sample_masked='""',
            endpoint="eu_data_act", first_seen_at="2026-10-07T18:26:59+00:00",
        )
        assert _is_scout_repair_skipped(field) is True, leaf


def test_a_sibling_that_is_not_on_the_list_still_raises_it() -> None:
    """Proves the skip is keyed on those exact leaves and not on the family."""
    from custom_components.vag_connect.cariad._reporter_pipeline import (
        _is_scout_repair_skipped,
    )
    from custom_components.vag_connect.cariad._unexpected_keys import UnexpectedField

    field = UnexpectedField(
        path="eu_data_act.fourth_active_consumer_", sample_masked='""',
        endpoint="eu_data_act", first_seen_at="2026-10-07T18:26:59+00:00",
    )
    assert _is_scout_repair_skipped(field) is False


def test_the_consumer_fields_are_never_consumed_by_the_parser() -> None:
    """Skipping the repair must not become suppression: the parser must leave
    them unmapped so they stay in raw_unmapped_fields."""
    d = _map(dict.fromkeys(_CONSUMERS, ""))
    unmapped = set(d.raw_unmapped_fields or {})
    for leaf in _CONSUMERS:
        assert leaf in unmapped, f"{leaf} vanished from discovery"


# ── the entity ──────────────────────────────────────────────────────────────


def test_the_sensor_is_a_disabled_diagnostic_timestamp() -> None:
    from homeassistant.components.sensor import SensorDeviceClass
    from homeassistant.helpers.entity import EntityCategory

    from custom_components.vag_connect.sensor import SENSOR_DESCRIPTIONS

    found = [d for d in SENSOR_DESCRIPTIONS if d.key == "dashboard_warnings_last_at"]
    assert len(found) == 1
    desc = found[0]
    assert desc.device_class == SensorDeviceClass.TIMESTAMP
    assert desc.entity_category == EntityCategory.DIAGNOSTIC
    assert desc.entity_registry_enabled_default is False
    assert desc.data_key == "dashboard_warnings_last_at"


def test_the_sensor_cannot_spawn_as_a_phantom() -> None:
    """EU-Data-Act dialect only — every other channel must leave it absent."""
    from custom_components.vag_connect.sensor import _DATA_PRESENT_REQUIRED

    assert "dashboard_warnings_last_at" in _DATA_PRESENT_REQUIRED


def test_the_name_exists_in_every_language() -> None:
    for name in ("strings.json", *(f"translations/{lang}.json" for lang in _LANGS)):
        data = json.loads((_ROOT / name).read_text(encoding="utf-8"))
        entry = data["entity"]["sensor"].get("dashboard_warnings_last_at")
        assert entry and entry.get("name"), f"{name} is missing the sensor name"
