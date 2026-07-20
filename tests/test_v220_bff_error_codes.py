"""v2.20.0 — CARIAD BFF numeric error-code decode + classification.

Grounds the 46-entry BFFError$Code table (from the decoded myAudi app) and its
wiring into ``classify_command_failure``: the authoritative numeric ``code`` in
the BFF error envelope now drives the failure reason instead of leaving a
licence lapse / deep-sleep car / missing capability all collapsed to the same
opaque status-only guess.
"""

from __future__ import annotations

import pytest

from custom_components.vag_connect.cariad._bff_error_codes import (
    bff_error_name,
    decode_bff_error,
    reason_for_bff_code,
)
from custom_components.vag_connect.cariad.exceptions import (
    APIError,
    CommandFailureReason,
    classify_command_failure,
)


def _err(code: int | str, extra: str = "") -> APIError:
    """An APIError whose body is a realistic BFF error envelope."""
    inner = f'"code": {code}' if isinstance(code, int) else f'"code": "{code}"'
    body = f'{{"error": {{"message": "Not Found", {inner}{extra}}}}}'
    return APIError(404, "https://emea.bff.cariad.digital/x", body)


# ── decode_bff_error ────────────────────────────────────────────────────


def test_decode_nested_envelope() -> None:
    assert decode_bff_error('{"error": {"code": 4112}}') == (4112, "missingCapability")


def test_decode_bare_top_level() -> None:
    assert decode_bff_error('{"code": 2101}') == (2101, "userNotEnrolled")


def test_decode_numeric_string_code() -> None:
    assert decode_bff_error('{"error": {"code": "4104"}}') == (
        4104,
        "operationNotSupported",
    )


def test_decode_unknown_code_returns_none() -> None:
    # A numeric code that is not in the table → None (fall through, don't guess).
    assert decode_bff_error('{"error": {"code": 99999}}') is None


def test_decode_non_json_returns_none() -> None:
    assert decode_bff_error("<html>502 Bad Gateway</html>") is None


def test_decode_empty_returns_none() -> None:
    assert decode_bff_error("") is None


def test_decode_bool_is_not_a_code() -> None:
    # JSON true would coerce to 1 via int() — must be rejected.
    assert decode_bff_error('{"error": {"code": true}}') is None


# ── bff_error_name / reason_for_bff_code ────────────────────────────────


def test_name_known_and_unknown() -> None:
    assert bff_error_name(0x10C9) == "vehicleIsInDeepSleep"
    assert bff_error_name(0x1234) is None


def test_reason_ambiguous_code_is_unmapped() -> None:
    # parkingPositionNotAvailable (0x4fb1) is a known NAME but deliberately has
    # no reason mapping → None, so classify falls through to its heuristics.
    assert bff_error_name(0x4FB1) == "parkingPositionNotAvailable"
    assert reason_for_bff_code(0x4FB1) is None


# ── classify_command_failure via numeric code ──────────────────────────


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        (4112, CommandFailureReason.MISSING_CAPABILITY),  # missingCapability
        (4104, CommandFailureReason.MISSING_CAPABILITY),  # operationNotSupported
        (4113, CommandFailureReason.MISSING_CAPABILITY),  # capabilityDisabledByUser
        (4007, CommandFailureReason.SUBSCRIPTION_EXPIRED),  # connectivityLicenseInactive
        # missingUserConsent must NOT hide the entity — reversible consent gap,
        # so it maps to non-hiding BACKEND_ERROR, not NOT_ENTITLED.
        (4004, CommandFailureReason.BACKEND_ERROR),  # missingUserConsent
        (2101, CommandFailureReason.NOT_ENTITLED),  # userNotEnrolled
        (2103, CommandFailureReason.NOT_ENTITLED),  # userIsNotLinkedToVehicleBackend
        (4003, CommandFailureReason.NOT_ENTITLED),  # unauthorizedCall
        (4297, CommandFailureReason.VEHICLE_UNREACHABLE),  # vehicleIsInDeepSleep
        (4122, CommandFailureReason.VEHICLE_UNREACHABLE),  # vehicleOffline
        (4291, CommandFailureReason.BACKEND_ERROR),  # tooManyRequests
        (4101, CommandFailureReason.INVALID_PAYLOAD),  # invalidPayload
        (2105, CommandFailureReason.INVALID_PAYLOAD),  # requestIsIncorrect
    ],
)
def test_classify_from_numeric_code(
    code: int, expected: CommandFailureReason
) -> None:
    assert classify_command_failure(_err(code)) == expected


def test_numeric_string_code_also_classifies() -> None:
    assert (
        classify_command_failure(_err("4297"))
        == CommandFailureReason.VEHICLE_UNREACHABLE
    )


def test_retry_true_wins_over_numeric_code() -> None:
    # {"code":4112,"retry":true} is the transient upstream wrap (v1.20.3) — must
    # stay BACKEND_ERROR (entity visible), NOT MISSING_CAPABILITY (entity hidden).
    exc = _err(4112, extra=', "retry": true')
    assert classify_command_failure(exc) == CommandFailureReason.BACKEND_ERROR


def test_unmapped_known_code_falls_through_to_status() -> None:
    # parkingPositionNotAvailable → no reason mapping → HTTP-404 fallback
    # (WRONG_API_PROFILE), proving we don't invent a reason.
    assert (
        classify_command_failure(_err(0x4FB1))
        == CommandFailureReason.WRONG_API_PROFILE
    )


def test_unknown_numeric_code_falls_through() -> None:
    exc = APIError(403, "https://emea.bff.cariad.digital/x", '{"error":{"code":99999}}')
    # 403 with an unknown code → status fallback → NOT_ENTITLED.
    assert classify_command_failure(exc) == CommandFailureReason.NOT_ENTITLED


def test_string_marker_still_wins_when_present() -> None:
    # An explicit attestation marker must still classify before the numeric path.
    exc = APIError(
        403,
        "https://emea.bff.cariad.digital/x",
        '{"error":{"message":"forbidden device detected","code":4003}}',
    )
    assert classify_command_failure(exc) == CommandFailureReason.ATTESTATION_LOCKED
