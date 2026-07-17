# Copyright 2026 Prash Balan (@its-me-prash) - Apache License 2.0
# SPDX-License-Identifier: AGPL-3.0-or-later
"""v2.18.1 — post-2.18.0 Scout triage: register/consume the fields that kept a
handful of Scout reports open after the release, verified against the SAME
``_path_matches`` the detector uses and the real mapper.

Covered:
  · selectivestatus (audi inherits volkswagen): aux-heating now also nested under
    the climatisation / climatisationTimers jobs (#752), and climatisationTimers
    gained the standard CARIAD-BFF ``.error`` envelope (#785/#789).
  · skoda charging: ``settings.maxChargeCurrentAcAmpere`` — the integer-amps
    spelling the parser already reads (skoda.py) but EXPECTED_KEYS never listed
    (#781/#795), classic silencer-lag.
  · EU-Data-Act 15-min feed: ``oil_level_status`` raw enum is now CONSUMED into
    the diagnostic ``oil_level_status`` field (#794) instead of surfacing unmapped.

NOT covered on purpose: the feed's bare ``open`` boolean (#794/#807) is left
Scout-visible — its meaning is ambiguous and the no-suppression policy forbids
silencing it; we map real fields, we never hide.
"""
from __future__ import annotations

from custom_components.vag_connect.cariad._unexpected_keys import (
    EXPECTED_KEYS,
    _path_matches,
)
from custom_components.vag_connect.cariad.auth._eu_data_act import (
    map_dataset_to_vehicle_data,
)
from custom_components.vag_connect.cariad.models import VehicleData


def test_v2181_selectivestatus_aux_heating_and_timer_error_registered() -> None:
    vw = EXPECTED_KEYS["volkswagen"]["selectivestatus"]
    for path in (
        "climatisation.auxiliaryHeatingStatus",  # #752 (2-seg leaf)
        "climatisation.auxiliaryHeatingStatus.value",
        "climatisationTimers.auxiliaryHeatingTimersStatus.value",  # #752 (3-seg)
        "climatisationTimers.climatisationTimersStatus.error",  # #785/#789
        "climatisationTimers.climatisationTimersStatus.error.retry",  # via .error.*
    ):
        assert _path_matches(path, vw), path


def test_v2181_audi_inherits_the_selectivestatus_additions() -> None:
    # EXPECTED_KEYS["audi"] = EXPECTED_KEYS["volkswagen"] at module load.
    audi = EXPECTED_KEYS["audi"]["selectivestatus"]
    assert _path_matches("climatisation.auxiliaryHeatingStatus", audi)
    assert _path_matches("climatisationTimers.climatisationTimersStatus.error", audi)


def test_v2181_skoda_max_charge_current_ampere_registered() -> None:
    charging = EXPECTED_KEYS["skoda"]["charging"]
    assert _path_matches("settings.maxChargeCurrentAcAmpere", charging)
    # the lowercase-c variant must still resolve (regression guard)
    assert _path_matches("settings.maxChargeCurrentAc", charging)


def test_v2181_feed_oil_level_status_is_consumed() -> None:
    d = VehicleData(vin="WVWZZZ1KZAW000000")
    map_dataset_to_vehicle_data({"oil_level_status": "minWarning"}, d)
    assert d.oil_level_status == "minWarning"


def test_v2181_oil_level_status_does_not_clobber_existing() -> None:
    d = VehicleData(vin="X")
    d.oil_level_status = "ok"
    map_dataset_to_vehicle_data({"oil_level_status": "minWarning"}, d)
    assert d.oil_level_status == "ok"  # canonical/earlier value wins
