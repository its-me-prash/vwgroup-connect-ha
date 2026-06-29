# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""v2.15.4 (#530 audi) — next-charging-timer fields under the alt container.

Scout #530 (brand audi) reported the BFF/selectivestatus next-charging-timer
fields arriving under ``chargingProfiles.chargingProfilesStatus.value.
nextChargingTimer.*`` instead of the long-parsed
``automation.chargingProfiles.value.nextChargingTimer.*`` path.

``_parse_status`` (vw_eu.py — inherited unchanged by ``AudiClient``) now reads
the chargingProfilesStatus container as a FALLBACK behind the automation path
(first-non-null wins), reusing the existing model fields/entities/i18n.
"""
from __future__ import annotations

from unittest.mock import MagicMock


def _audi_client() -> object:
    from custom_components.vag_connect.cariad.api.audi import AudiClient
    from custom_components.vag_connect.cariad.models import TokenSet

    client = AudiClient(MagicMock(), "u@t.de", "pw")
    client._tokens = TokenSet("acc", "ref", "id")
    return client


def _vw_client() -> object:
    from custom_components.vag_connect.cariad.api.vw_eu import VWEUClient
    from custom_components.vag_connect.cariad.models import TokenSet

    client = VWEUClient(MagicMock(), "u@t.de", "pw")
    client._tokens = TokenSet("acc", "ref", "id")
    return client


def test_audi_routes_status_through_vw_eu_reader() -> None:
    # AudiClient does not override _parse_status / _val — it inherits VWEUClient.
    from custom_components.vag_connect.cariad.api.audi import AudiClient
    from custom_components.vag_connect.cariad.api.vw_eu import VWEUClient

    assert issubclass(AudiClient, VWEUClient)
    assert AudiClient._parse_status is VWEUClient._parse_status


def test_530_fallback_container_populates() -> None:
    # ONLY the chargingProfilesStatus container present (no automation path).
    raw = {
        "chargingProfiles": {
            "chargingProfilesStatus": {
                "value": {
                    "nextChargingTimer": {
                        "id": 0,
                        "targetSOCreachable": "reachable",
                    }
                }
            }
        }
    }
    client = _audi_client()
    d = client._parse_status("VIN1", raw, {})
    assert d.next_charging_timer_id == 0
    assert d.next_charging_timer_target_soc_reachable == "reachable"


def test_530_target_soc_reachable_stays_string_verbatim() -> None:
    # No enum invention — the string passes through unchanged.
    for token in ("reachable", "notReachable", "calculating", "80"):
        raw = {
            "chargingProfiles": {
                "chargingProfilesStatus": {
                    "value": {"nextChargingTimer": {"targetSOCreachable": token}}
                }
            }
        }
        d = _audi_client()._parse_status("VIN1", raw, {})
        assert d.next_charging_timer_target_soc_reachable == token


def test_530_automation_path_still_primary() -> None:
    # Original automation.* path keeps working when it is the only one present.
    raw = {
        "automation": {
            "chargingProfiles": {
                "value": {
                    "nextChargingTimer": {
                        "id": 3,
                        "targetSOCreachable": "notReachable",
                    }
                }
            }
        }
    }
    d = _vw_client()._parse_status("VIN1", raw, {})
    assert d.next_charging_timer_id == 3
    assert d.next_charging_timer_target_soc_reachable == "notReachable"


def test_530_automation_wins_over_fallback() -> None:
    # When BOTH containers are present, the primary automation path wins.
    raw = {
        "automation": {
            "chargingProfiles": {
                "value": {
                    "nextChargingTimer": {
                        "id": 3,
                        "targetSOCreachable": "notReachable",
                    }
                }
            }
        },
        "chargingProfiles": {
            "chargingProfilesStatus": {
                "value": {
                    "nextChargingTimer": {
                        "id": 9,
                        "targetSOCreachable": "reachable",
                    }
                }
            }
        },
    }
    d = _audi_client()._parse_status("VIN1", raw, {})
    assert d.next_charging_timer_id == 3
    assert d.next_charging_timer_target_soc_reachable == "notReachable"


def test_530_scout_no_longer_reports_consumed_paths() -> None:
    # Once consumed, the two 5-segment leaves must be in EXPECTED_KEYS so the
    # Vehicle Data Scout does not re-report them.
    from custom_components.vag_connect.cariad._unexpected_keys import detect_unexpected

    raw = {
        "chargingProfiles": {
            "chargingProfilesStatus": {
                "value": {
                    "nextChargingTimer": {
                        "id": 0,
                        "targetSOCreachable": "reachable",
                    }
                }
            }
        }
    }
    paths = {f.path for f in detect_unexpected("audi", "vehicle-status", raw)}
    assert (
        "chargingProfiles.chargingProfilesStatus.value.nextChargingTimer.id"
        not in paths
    )
    assert (
        "chargingProfiles.chargingProfilesStatus.value."
        "nextChargingTimer.targetSOCreachable" not in paths
    )
