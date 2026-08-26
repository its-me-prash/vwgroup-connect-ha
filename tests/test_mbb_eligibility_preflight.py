# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Durable-MBB two-way pre-flight from the guest-readable relations read.

Whether the durable MBB Car-Net two-way is worth arming for a car is, today,
only learned post-hoc from the BFF operationList after the user opts in and logs
in. The vw.de relations read carries the deciding signal up front — attestation-
free, one GET, readable even for a guest. This pins the classifier + the parser
fields it needs, grounded on the exact shapes captured live on 2026-08-26:

  * a GUEST on a family MBB Golf → carnetIndicator=false, enrollment=NOT_STARTED,
    role=UNKNOWN, primaryCar=false → the MBB login could not command → skip it.
  * an enrolled owner / Car-Net car → eligible.
"""
from __future__ import annotations

from custom_components.vag_connect.cariad._authproxy import (
    AuthproxyRelation,
    mbb_eligibility,
    parse_relation_detail,
    parse_relations,
)

# The exact live guest shape (values are the account's own; no third-party PII).
_DETAIL_GUEST = {
    "relation": {
        "vehicleNickname": None,
        "licensePlate": None,
        "role": "UNKNOWN",
        "roleStatus": None,
        "enrollmentStatus": "NOT_STARTED",
        "primaryCar": False,
        "carnetIndicator": False,
        "carnetAllocationType": None,
        "vehicle": {"vin": "WVWZZZTESTVHN0001", "modBackend": "MBB"},
    }
}
_DETAIL_OWNER = {
    "relation": {
        "role": "PRIMARY_USER",
        "enrollmentStatus": "COMPLETED",
        "primaryCar": True,
        "carnetIndicator": True,
        "carnetAllocationType": "CARNET",
        "vehicle": {"vin": "WVWZZZTESTVHN0002", "modBackend": "MBB"},
    }
}


def _rel(**kw) -> AuthproxyRelation:
    kw.setdefault("vin", "V")
    return AuthproxyRelation(**kw)


class TestParserSurfacesCarnetFields:
    def test_guest_detail_carnet_false(self) -> None:
        rel = parse_relation_detail(_DETAIL_GUEST)
        assert rel is not None
        assert rel.mod_backend == "MBB"
        assert rel.carnet_indicator is False
        assert rel.carnet_allocation_type is None

    def test_owner_detail_carnet_true(self) -> None:
        rel = parse_relation_detail(_DETAIL_OWNER)
        assert rel is not None
        assert rel.carnet_indicator is True
        assert rel.carnet_allocation_type == "CARNET"

    def test_list_parser_also_surfaces_carnet(self) -> None:
        body = {
            "user": {"mbbUserId": "MMxxx"},
            "relations": [
                {
                    "carnetIndicator": True,
                    "carnetAllocationType": "CARNET",
                    "vehicle": {"vin": "WVWZZZTESTVHN0003", "modBackend": "MBB"},
                }
            ],
        }
        rels = parse_relations(body)
        assert rels is not None
        assert rels.vehicles[0].carnet_indicator is True
        assert rels.vehicles[0].carnet_allocation_type == "CARNET"
        # a body without the field defaults to False, never crashes
        rels2 = parse_relations({"relations": [{"vehicle": {"vin": "WVWZZZTESTVHN0004"}}]})
        assert rels2 is not None
        assert rels2.vehicles[0].carnet_indicator is False


class TestMbbEligibility:
    def test_live_guest_is_not_provisioned(self) -> None:
        rel = parse_relation_detail(_DETAIL_GUEST)
        assert rel is not None
        assert mbb_eligibility(rel) == "not_provisioned"

    def test_live_owner_is_eligible(self) -> None:
        rel = parse_relation_detail(_DETAIL_OWNER)
        assert rel is not None
        assert mbb_eligibility(rel) == "eligible"

    def test_carnet_indicator_alone_is_eligible(self) -> None:
        assert mbb_eligibility(_rel(mod_backend="MBB", carnet_indicator=True)) == "eligible"

    def test_primary_and_enrolled_without_flag_is_eligible(self) -> None:
        assert mbb_eligibility(_rel(
            mod_backend="MBB", primary_car=True, enrollment_status="COMPLETED",
        )) == "eligible"
        assert mbb_eligibility(_rel(
            mod_backend="MBB", role="PRIMARY_USER", enrollment_status="ENROLLED",
        )) == "eligible"

    def test_mbb_odp_suffix_matches_like_gdc(self) -> None:
        # real cars carry a suffixed sentinel ("MBB_ODP") — prefix match, not ==
        assert mbb_eligibility(_rel(mod_backend="MBB_ODP", carnet_indicator=True)) == "eligible"

    def test_meb_car_is_not_mbb(self) -> None:
        assert mbb_eligibility(_rel(mod_backend="MEB", carnet_indicator=True)) == "not_mbb"

    def test_primary_but_not_started_is_not_provisioned(self) -> None:
        # primaryCar true but enrollment NOT_STARTED → no Car-Net access yet
        assert mbb_eligibility(_rel(
            mod_backend="MBB", primary_car=True, enrollment_status="NOT_STARTED",
        )) == "not_provisioned"

    def test_missing_backend_is_unknown(self) -> None:
        assert mbb_eligibility(_rel(mod_backend=None)) == "unknown"
        assert mbb_eligibility(_rel(mod_backend="")) == "unknown"
