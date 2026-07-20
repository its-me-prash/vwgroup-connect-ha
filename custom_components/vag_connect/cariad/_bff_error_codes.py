# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""CARIAD BFF numeric error-code table — opaque codes → legible meaning.

The CARIAD Connected-Car BFF (``emea.bff.cariad.digital``) returns a numeric
``code`` inside its JSON error envelope, e.g.::

    {"error": {"message": "Not Found", "code": 4112, "group": 2, "retry": true}}

Until now the integration only string-sniffed the ``message``/``info`` text
(``"upstream service responded"``, ``"retry":true`` …) and fell back to a
HTTP-status-only guess. That left the authoritative numeric ``code`` — which
the official app decodes into a named reason — unused, so a licence lapse, a
deep-sleep car and a genuinely-missing capability all collapsed to the same
opaque ``BACKEND_ERROR`` / ``WRONG_API_PROFILE``.

``_BFF_ERROR_NAMES`` is the full 46-entry table lifted verbatim from the
official myAudi app's ``technology.cariad.cat.rccutility.BFFError$Code`` enum
(keys kept as hex literals so they line up 1:1 with the smali ``const`` values
for future re-verification). ``_BFF_ERROR_REASON`` maps only the *unambiguous*
codes onto the integration's ``CommandFailureReason``; ambiguous ones are left
out so they fall through to the existing status/body heuristics rather than
risk a wrong "hide the entity" decision.
"""

from __future__ import annotations

import json
from typing import Any

from .exceptions import CommandFailureReason

# ── Full BFFError$Code table (hex key = smali const → name) ──────────────
# Source: audi_550_decoded/.../rccutility/BFFError$Code.smali (46 entries).
_BFF_ERROR_NAMES: dict[int, str] = {
    0x835: "userNotEnrolled",
    0x837: "userIsNotLinkedToVehicleBackend",
    0x838: "userHasNoRelationWithVIN",
    0x839: "requestIsIncorrect",
    0xC1E: "missingIDKUserID",
    0xC1F: "invalidVIN",
    0xC20: "capabilityAlreadyHasRequestedState",
    0xC25: "newsFeedUrlAlreadySubscribed",
    0xFA1: "internalError",
    0xFA2: "underlyingSystemUnavailable",
    0xFA3: "unauthorizedCall",
    0xFA4: "missingUserConsent",
    0xFA5: "accessToThisResourceNotAllowed",
    0xFA6: "requestedFeatureUnavailable",
    0xFA7: "connectivityLicenseInactive",
    0x1005: "invalidPayload",
    0x1006: "systemCouldNotHandleRequest",
    0x1007: "resourceNotFound",
    0x1008: "operationNotSupported",
    0x1009: "systemNotRespondingProperly",
    0x100A: "systemCannotHandleThisAction",
    0x100B: "maximumAmountOfDestinationsReached",
    0x100C: "jobForGivenIDNotFound",
    0x100F: "operationInvalid",
    0x1010: "missingCapability",
    0x1011: "capabilityDisabledByUser",
    0x1012: "exactlyTwoClimatisationTimersRequired",
    0x1013: "multipleBrands",
    0x1014: "disablingCapabilityNotAllowedOnBackend",
    0x1015: "capabilityDisabledInVehicle",
    0x1016: "vehiclePositionUnknown",
    0x1017: "locationTooFarFromVehicle",
    0x1018: "departureProfilesNumberLimitReached",
    0x1019: "vehicleInGarageMode",
    0x101A: "vehicleOffline",
    0x101B: "fullPrivacyModeEnabled",
    0x101C: "vehicleIsInMotion",
    0x10C3: "tooManyRequests",
    0x10C4: "rejectedRequest",
    0x10C5: "operationInProgress",
    0x10C6: "numberOfRequestsLimitReached",
    0x10C7: "maximumAmountOfRequestsReached",
    0x10C8: "insufficientBatteryLevel",
    0x10C9: "vehicleIsInDeepSleep",
    0x270F: "undefinedError",
    0x4FB1: "parkingPositionNotAvailable",
}

# ── Only the UNAMBIGUOUS codes get a failure-reason mapping ──────────────
# Codes left out (payload/validation/timer/position/news) fall through to the
# existing string + HTTP-status heuristics in classify_command_failure.
_BFF_ERROR_REASON: dict[int, CommandFailureReason] = {
    # Capability genuinely not present / switched off for this VIN → hide.
    0x1010: CommandFailureReason.MISSING_CAPABILITY,  # missingCapability
    0x1008: CommandFailureReason.MISSING_CAPABILITY,  # operationNotSupported
    0x1011: CommandFailureReason.MISSING_CAPABILITY,  # capabilityDisabledByUser
    0x1015: CommandFailureReason.MISSING_CAPABILITY,  # capabilityDisabledInVehicle
    # Paid online-services licence lapsed → surface, do NOT hide.
    0xFA7: CommandFailureReason.SUBSCRIPTION_EXPIRED,  # connectivityLicenseInactive
    # Account not enrolled / not linked / unauthorized → entitlement problem.
    0x835: CommandFailureReason.NOT_ENTITLED,  # userNotEnrolled
    0x837: CommandFailureReason.NOT_ENTITLED,  # userIsNotLinkedToVehicleBackend
    0x838: CommandFailureReason.NOT_ENTITLED,  # userHasNoRelationWithVIN
    0xFA3: CommandFailureReason.NOT_ENTITLED,  # unauthorizedCall
    0xFA5: CommandFailureReason.NOT_ENTITLED,  # accessToThisResourceNotAllowed
    # missingUserConsent (0xFA4) is NOT an entitlement gap — the user just
    # hasn't accepted a consent in the brand app, which is reversible. Mapping
    # it to NOT_ENTITLED would flip entitled_by_account=False and HIDE the
    # control for 24h (and send the user chasing a phantom subscription). The
    # enum has no dedicated consent reason, so classify it as a non-hiding
    # BACKEND_ERROR: the control stays visible and the user can retry once they
    # accept the consent. (Same spirit as the invalidSecurityPin / attestation
    # carve-outs in classify_command_failure.)
    0xFA4: CommandFailureReason.BACKEND_ERROR,  # missingUserConsent
    # Car asleep / offline → transient, keep the entity available.
    0x10C9: CommandFailureReason.VEHICLE_UNREACHABLE,  # vehicleIsInDeepSleep
    0x101A: CommandFailureReason.VEHICLE_UNREACHABLE,  # vehicleOffline
    # Rate limiting / backend hiccups → transient backend error.
    0x10C3: CommandFailureReason.BACKEND_ERROR,  # tooManyRequests
    0x10C6: CommandFailureReason.BACKEND_ERROR,  # numberOfRequestsLimitReached
    0x10C7: CommandFailureReason.BACKEND_ERROR,  # maximumAmountOfRequestsReached
    0xFA1: CommandFailureReason.BACKEND_ERROR,  # internalError
    0xFA2: CommandFailureReason.BACKEND_ERROR,  # underlyingSystemUnavailable
    0x1006: CommandFailureReason.BACKEND_ERROR,  # systemCouldNotHandleRequest
    0x1009: CommandFailureReason.BACKEND_ERROR,  # systemNotRespondingProperly
    0x100A: CommandFailureReason.BACKEND_ERROR,  # systemCannotHandleThisAction
    # Our request was malformed → our bug, fix it.
    0x1005: CommandFailureReason.INVALID_PAYLOAD,  # invalidPayload
    0x839: CommandFailureReason.INVALID_PAYLOAD,  # requestIsIncorrect
}


def bff_error_name(code: int) -> str | None:
    """Return the official name for a numeric BFF error code, or ``None``."""
    return _BFF_ERROR_NAMES.get(code)


def reason_for_bff_code(code: int) -> CommandFailureReason | None:
    """Return the mapped failure reason for a code, or ``None`` if ambiguous."""
    return _BFF_ERROR_REASON.get(code)


def _coerce_code(value: Any) -> int | None:
    """Best-effort int from a JSON ``code`` field (int or numeric string)."""
    if isinstance(value, bool):  # bool is an int subclass — reject it
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        text = value.strip()
        if text.isdigit():
            return int(text)
    return None


def bff_error_retryable(body: str) -> bool:
    """True if the BFF error envelope flags the failure as retryable/transient.

    The CARIAD BFF wraps transient upstream problems in an otherwise-permanent
    error shape but sets ``retry: true`` (sometimes reusing a code like 4112
    ``missingCapability``). Such an error must never be read as a permanent
    verdict that hides an entity. Parsing the JSON makes this robust to
    whitespace, unlike a bare ``"retry":true`` substring match. Never raises.
    """
    if not body or not isinstance(body, str):
        return False
    try:
        parsed = json.loads(body)
    except (ValueError, TypeError):
        return False
    if not isinstance(parsed, dict):
        return False
    err = parsed.get("error")
    container = err if isinstance(err, dict) else parsed
    return bool(container.get("retry"))


def decode_bff_error(body: str) -> tuple[int, str] | None:
    """Extract ``(code, name)`` from a CARIAD BFF error body, or ``None``.

    Tolerant of the two envelope shapes seen in the wild — ``{"error":
    {"code": N}}`` and a bare top-level ``{"code": N}`` — and of the code
    arriving as an int or a numeric string. Only returns a hit when the code
    is a *known* BFFError$Code; an unknown numeric code returns ``None`` so
    callers fall through to their existing heuristics rather than inventing a
    meaning. Never raises: a non-JSON or unexpected body yields ``None``.
    """
    if not body or not isinstance(body, str):
        return None
    try:
        parsed = json.loads(body)
    except (ValueError, TypeError):
        return None
    if not isinstance(parsed, dict):
        return None
    err = parsed.get("error")
    container = err if isinstance(err, dict) else parsed
    code = _coerce_code(container.get("code"))
    if code is None:
        return None
    name = _BFF_ERROR_NAMES.get(code)
    if name is None:
        return None
    return code, name
