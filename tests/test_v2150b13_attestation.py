# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""b13 (H1) — device-attestation lock classification on the command path.

VW is rolling Firebase App Check / Play Integrity across its planes. When it
reaches a command plane, the 403 must be classified as ATTESTATION_LOCKED —
NOT as a subscription/entitlement problem — so users aren't sent chasing a
phantom renewal. The marker is the response BODY, never a bare 403.
"""
from __future__ import annotations

from custom_components.vag_connect.cariad.exceptions import (
    APIError,
    CommandFailureReason,
    classify_command_failure,
)


def test_appcheck_body_classifies_as_attestation_locked() -> None:
    for body in (
        '{"message":"Forbidden device detected","code":"missing-device-token"}',
        '{"error":"x-firebase-appcheck token missing"}',
        '{"detail":"Play Integrity verdict failed"}',
        '{"reason":"AppCheck rejected"}',
    ):
        err = APIError(403, "https://x", body)
        assert classify_command_failure(err) == CommandFailureReason.ATTESTATION_LOCKED, body


def test_bare_403_is_not_mislabeled_as_attestation() -> None:
    # a 403 with no attestation marker must still be NOT_ENTITLED, not the new reason
    assert classify_command_failure(
        APIError(403, "https://x", "")
    ) == CommandFailureReason.NOT_ENTITLED


def test_spin_403_still_spin_required() -> None:
    err = APIError(403, "https://x", '{"error":{"message":"spin_error","spinState":"DEFINED"}}')
    assert classify_command_failure(err) == CommandFailureReason.SPIN_REQUIRED


def test_entitlement_403_still_not_entitled() -> None:
    err = APIError(403, "https://x", '{"error":"not_entitled"}')
    assert classify_command_failure(err) == CommandFailureReason.NOT_ENTITLED


def test_subscription_403_still_subscription_expired() -> None:
    err = APIError(403, "https://x", '{"error":"subscription expired"}')
    assert classify_command_failure(err) == CommandFailureReason.SUBSCRIPTION_EXPIRED
