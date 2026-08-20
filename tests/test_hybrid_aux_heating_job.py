# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""4.0.x — PHEV parking-/pre-heater via the hybridCarAuxiliaryHeating job.

Grounding We Connect 4.3.2 (androguard) showed the SelectiveStatusJob enum has a
DISTINCT ``hybridCarAuxiliaryHeating`` job alongside the BEV ``auxiliaryHeating``:
PHEVs (Golf/Passat GTE etc.) report their pre-heater under the hybrid variant. We
requested only the BEV job, so PHEV aux-heat status was never fetched. The job is
now requested and the parser reads the parallel ``hybridCarAuxiliaryHeatingStatus``
block onto the same ``aux_heating_active`` / status / remaining fields.
"""
from __future__ import annotations

from custom_components.vag_connect.cariad.api.vw_eu import (
    _SELECTIVE_STATUS_JOBS,
    VWEUClient,
)


def _vw_client() -> VWEUClient:
    client = VWEUClient.__new__(VWEUClient)
    client._vehicle_metadata = {}
    client._tokens = None
    client._spin = ""
    return client


def test_hybrid_job_is_requested() -> None:
    jobs = _SELECTIVE_STATUS_JOBS.split(",")
    assert "hybridCarAuxiliaryHeating" in jobs
    # the BEV sibling is still there — the hybrid is an addition, not a swap.
    assert "auxiliaryHeating" in jobs


def test_hybrid_status_populates_aux_heating() -> None:
    client = _vw_client()
    raw = {
        "hybridCarAuxiliaryHeating": {
            "hybridCarAuxiliaryHeatingStatus": {
                "value": {"operationMode": "heating", "remainingTime_min": 20},
            },
        },
    }
    data = client._parse_status("VINX", raw, parking={})
    assert data.auxiliary_heating_status == "heating"
    assert data.aux_heating_active is True
    assert data.auxiliary_heating_remaining_min == 20


def test_bev_path_still_wins_when_both_present() -> None:
    # A car reporting both prefers the canonical BEV path (tried first).
    client = _vw_client()
    raw = {
        "auxiliaryHeating": {
            "auxiliaryHeatingStatus": {"value": {"operationMode": "off"}},
        },
        "hybridCarAuxiliaryHeating": {
            "hybridCarAuxiliaryHeatingStatus": {"value": {"operationMode": "heating"}},
        },
    }
    data = client._parse_status("VINX", raw, parking={})
    assert data.auxiliary_heating_status == "off"
    assert data.aux_heating_active is False
