# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Scout #998 (Audi, neuhausf) — userCapabilities.capabilitiesStatus.requests is
the pending-request queue counter (a ``*.requests`` command-queue envelope, the
sample was ``[0 items]``), not a vehicle reading. It is registered as known-
structural so the Vehicle Data Scout stops re-reporting the wrapper, exactly like
windowHeatingStatus.requests / climatisationStatus.requests already are.
"""
from __future__ import annotations

from custom_components.vag_connect.cariad._unexpected_keys import (
    EXPECTED_KEYS,
    _path_matches,
    detect_unexpected,
)


def test_requests_registered_for_volkswagen() -> None:
    vw = EXPECTED_KEYS["volkswagen"]["selectivestatus"]
    assert _path_matches("userCapabilities.capabilitiesStatus.requests", vw)


def test_requests_registered_for_audi_inherited() -> None:
    # #998 was reported on audi, which inherits the volkswagen selectivestatus set.
    audi = EXPECTED_KEYS["audi"]["selectivestatus"]
    assert _path_matches("userCapabilities.capabilitiesStatus.requests", audi)


def test_scout_no_longer_reports_the_requests_wrapper() -> None:
    # the exact #998 shape: capabilitiesStatus.requests as an (empty) list.
    response = {"userCapabilities": {"capabilitiesStatus": {"requests": []}}}
    reported = {
        f.path for f in detect_unexpected("audi", "selectivestatus", response)
    }
    assert "userCapabilities.capabilitiesStatus.requests" not in reported
