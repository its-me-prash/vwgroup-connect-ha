# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#1809 — a backend refusal must not be reported as a fact about the car.

``17eab6f9`` took the "this is an MEB / ID-family car" claim out of the repair
notice and the setup abort. What replaced it is narrower and checkable: "the
durable Car-Net login answered ``Unknown user`` for this car". The rule that
decides when to say it was left as it was, and on that rule the sentence reaches
users whose login never answered it:

* ``"unknown user" in low or "invalid_grant" in low`` — a BARE ``invalid_grant``
  was enough. That is the generic OAuth2 rejection: the register/exchange chain
  returns it for an account with no MBB enrolment, for an audience mismatch
  (#464) and for a refused register alike.
* the second write site fired on ANY mint failure — a 5xx, a timeout, a
  ``ClientError`` — and wrote the same flag.
* and the one field that proves the marker, ``error_description``, was dropped
  by the #1355 redaction before the flow could read it, so even a true claim was
  unsubstantiated.

Measured against the live MBB token endpoint with an Audi e-tron 50 quattro
(MY2022 — an MLB-evo car, not MEB): ``HTTP 400``, ``error=invalid_grant``,
``error_description="Unknown user <account-uuid>"``. So the marker is real and
reachable — it just needed carrying, which is what ``CariadError.oauth_error*``
now does. The UUID is why the description is carried as an attribute and never
interpolated into the message.
"""
from __future__ import annotations

import json

from custom_components.vag_connect.cariad.auth._mbboauth import _refresh_error
from custom_components.vag_connect.cariad.exceptions import (
    APIError,
    AuthenticationError,
    TokenRefreshRetryError,
)
from custom_components.vag_connect.config_flow import classify_mbb_mint_failure

# The live rejection, with the account UUID replaced by a placeholder.
_UNKNOWN_USER_BODY = json.dumps(
    {
        "error": "invalid_grant",
        "error_description": "Unknown user 00000000-0000-0000-0000-000000000000",
    }
)
_BARE_INVALID_GRANT_BODY = json.dumps({"error": "invalid_grant"})
# #464 — pinning the wrong audience makes MBB answer invalid_grant too.
_UNKNOWN_AUDIENCE_BODY = json.dumps(
    {"error": "invalid_grant", "error_description": "unknown audience"}
)


# ── the bug ─────────────────────────────────────────────────────────────────


def test_bare_invalid_grant_is_not_a_carnet_verdict() -> None:
    # THE defect: this is what told an MLB e-tron it was an ID/MEB car, and
    # what now claims a login answered "Unknown user" when it said no such
    # thing. invalid_grant alone proves nothing about enrolment.
    err = _refresh_error(400, _BARE_INVALID_GRANT_BODY, False)
    assert classify_mbb_mint_failure(err) == "unknown"


def test_unknown_audience_invalid_grant_is_not_a_carnet_verdict() -> None:
    # #464 — a real, documented non-enrolment cause of invalid_grant.
    err = _refresh_error(400, _UNKNOWN_AUDIENCE_BODY, False)
    assert classify_mbb_mint_failure(err) == "unknown"


def test_server_error_is_not_a_carnet_verdict() -> None:
    err = _refresh_error(503, "", False)
    assert classify_mbb_mint_failure(err) == "unknown"


def test_transport_failures_are_not_a_carnet_verdict() -> None:
    for err in (TimeoutError("timed out"), OSError("connection reset")):
        assert classify_mbb_mint_failure(err) == "unknown"


# ── the GUARDs: what must keep working ──────────────────────────────────────


def test_unknown_user_marker_still_classifies_as_not_enrolled() -> None:
    # GUARD: the case the notice was written for must still reach it, now via
    # the carried description rather than by accident via "invalid_grant".
    err = _refresh_error(400, _UNKNOWN_USER_BODY, False)
    assert classify_mbb_mint_failure(err) == "not_enrolled"


def test_unknown_user_in_an_apierror_body_still_classifies() -> None:
    # GUARD: the pre-existing APIError.body path (#1355) keeps working.
    err = APIError(400, "https://mbboauth.example/token", _UNKNOWN_USER_BODY)
    assert classify_mbb_mint_failure(err) == "not_enrolled"


def test_retired_grant_is_recognised_in_phase_two() -> None:
    # #1364 — Phase 1 already recognised this; Phase 2 never consulted the
    # rule, so a retired MBB client was classified as an enrolment verdict.
    err = AuthenticationError(
        "Device grant: /device_authorization HTTP 403 (unauthorized_client): "
        "client is not allowed to use the device_code grant"
    )
    assert classify_mbb_mint_failure(err) == "grant_retired"


def test_retired_grant_is_recognised_from_the_description_too() -> None:
    err = _refresh_error(
        403,
        json.dumps(
            {"error": "unauthorized_client", "error_description": "not allowed"}
        ),
        False,
    )
    assert classify_mbb_mint_failure(err) == "grant_retired"


# ── the redaction contract ──────────────────────────────────────────────────


def test_description_is_carried_as_an_attribute() -> None:
    err = _refresh_error(400, _UNKNOWN_USER_BODY, False)
    assert err.oauth_error == "invalid_grant"
    assert "Unknown user" in err.oauth_error_description


def test_description_never_reaches_the_message() -> None:
    # The live description embeds an account UUID, and this exception is
    # logged. The message must stay exactly as redacted as before (#1355).
    err = _refresh_error(400, _UNKNOWN_USER_BODY, False)
    assert str(err) == "MBB token exchange HTTP 400 (error=invalid_grant)"
    assert "Unknown user" not in str(err)
    assert "0000" not in str(err)


def test_attributes_default_to_empty_for_an_unparseable_body() -> None:
    err = _refresh_error(502, "<html>gateway</html>", False)
    assert err.oauth_error == ""
    assert err.oauth_error_description == ""


def test_refresh_path_classification_is_unchanged() -> None:
    # GUARD: carrying the fields must not disturb which exception TYPE the
    # refresh path raises — only invalid_grant is hard there.
    hard = _refresh_error(400, _BARE_INVALID_GRANT_BODY, True)
    soft = _refresh_error(503, "", True)
    assert isinstance(hard, AuthenticationError)
    assert isinstance(soft, TokenRefreshRetryError)
    assert soft.oauth_error == ""


def test_classifier_tolerates_a_plain_object() -> None:
    # It is called from a flow-level `except Exception`, so it must never
    # raise on something that carries neither attribute.
    assert classify_mbb_mint_failure(object()) == "unknown"
    assert classify_mbb_mint_failure(None) == "unknown"
