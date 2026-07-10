# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""v2.17.1 (#666) — SpinError → SPIN_REQUIRED + AWS-WAF → ATTESTATION_LOCKED."""
from __future__ import annotations

from custom_components.vag_connect.cariad.exceptions import (
    APIError,
    CommandFailureReason,
    SpinError,
    classify_command_failure,
)


class TestSpinErrorClassify:
    def test_local_spin_error_maps_to_spin_required(self):
        # A locally-raised SpinError must be a clean SPIN_REQUIRED, not UNKNOWN.
        assert (
            classify_command_failure(SpinError("set_climate_temperature", "no S-PIN"))
            is CommandFailureReason.SPIN_REQUIRED
        )

    def test_backend_spin_error_still_spin_required(self):
        exc = APIError(403, "/x", '{"error":{"message":"spin_error","spinState":"DEFINED","remainingTries":3}}')
        assert classify_command_failure(exc) is CommandFailureReason.SPIN_REQUIRED


class TestWafClassify:
    def test_aws_waf_marker_is_attestation_locked(self):
        for marker in (
            '{"x-amzn-waf-action":"challenge"}',
            "aws-waf-token missing",
            "WAFTokenUnavailable",
        ):
            exc = APIError(403, "/x", marker)
            assert (
                classify_command_failure(exc) is CommandFailureReason.ATTESTATION_LOCKED
            ), marker

    def test_plain_403_still_not_entitled(self):
        # A bare 403 with no marker must NOT be mis-flagged as attestation.
        assert (
            classify_command_failure(APIError(403, "/x", "forbidden"))
            is CommandFailureReason.NOT_ENTITLED
        )
