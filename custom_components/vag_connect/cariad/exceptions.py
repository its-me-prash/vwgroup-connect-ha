# Copyright 2026 Prash Balan (@its-me-prash) — Apache License 2.0
"""Exceptions for the VAG Connect CARIAD API client."""

from __future__ import annotations

from enum import StrEnum


class CommandProfile(StrEnum):
    """Per-VIN command-routing profile.

    Different VAG vehicles speak the same authentication backend (CARIAD)
    but expose commands at different URL prefixes. The most common split:
    pre-2024 Audis use ``/vehicle/v1/`` for everything, while newer
    premium models (RS e-tron GT, Q6 e-tron, A3 2024+ on PPC/PPE) use
    ``/vehicle/v2/`` paths and reject ``/v1/`` with HTTP 404.

    Currently used by ``AudiClient`` to remember which prefix worked for
    a given VIN, so a 404-induced fallback only happens once per VIN per
    integration lifetime. Other brand clients ignore the profile until
    they grow analogous needs.

    The full enum is defined upfront so future sessions (PPE, MBB
    legacy, mysmob v3, …) can extend the same dispatch table without
    breaking existing serialised state.
    """

    UNKNOWN = "unknown"
    CARIAD_BFF_V1 = "cariad_bff_v1"
    CARIAD_BFF_V2 = "cariad_bff_v2"
    AUDI_PPE = "audi_ppe"
    AUDI_PREMIUM = "audi_premium"
    LEGACY_MBB = "legacy_mbb"
    MEB_ID = "meb_id"
    SEAT_CUPRA_OLA = "seat_cupra_ola"
    SKODA_MYSMOB = "skoda_mysmob"
    SKODA_MYSMOB_V3 = "skoda_mysmob_v3"
    PORSCHE_PPA = "porsche_ppa"
    VW_NA = "vw_na"


class CommandFailureReason(StrEnum):
    """Why a vehicle command failed.

    Used by the coordinator to decide whether an entity should be hidden,
    flagged as not-entitled, or just shown as temporarily unavailable.
    Three failures that look similar at the HTTP layer can have very
    different correct responses:

    - ``MISSING_CAPABILITY`` — the vehicle's VIN is not registered for the
      feature in the manufacturer backend (e.g. CUPRA Born without
      honk-and-flash). Hide the entity at next reload.
    - ``SUBSCRIPTION_EXPIRED`` — paid online-services subscription expired.
      Same vehicle would support the command if the user renewed; surface
      a clear error, do NOT hide the entity.
    - ``NOT_ENTITLED`` — free tier (e.g. We Connect Go) that never
      included remote commands. Same handling as expired but with
      different user messaging.
    - ``WRONG_API_PROFILE`` — newer model uses a different endpoint
      version. Needs the per-VIN command profile from #61.
    - ``VEHICLE_UNREACHABLE`` — car offline / asleep / out of coverage.
      Transient — entity stays available.
    - ``SPIN_REQUIRED`` — already raised as ``ServiceValidationError``
      before reaching the API; included here for completeness.
    - ``INVALID_PAYLOAD`` — our bug. Fix and ship.
    - ``BACKEND_ERROR`` — manufacturer 5xx or unexpected 4xx body.
      Transient; do not derive long-term decisions.
    - ``UNKNOWN`` — default. Don't make assumptions.
    """

    MISSING_CAPABILITY = "missing_capability"
    SUBSCRIPTION_EXPIRED = "subscription_expired"
    NOT_ENTITLED = "not_entitled"
    WRONG_API_PROFILE = "wrong_api_profile"
    VEHICLE_UNREACHABLE = "vehicle_unreachable"
    SPIN_REQUIRED = "spin_required"
    INVALID_PAYLOAD = "invalid_payload"
    BACKEND_ERROR = "backend_error"
    UNKNOWN = "unknown"


def classify_command_failure(exc: BaseException) -> CommandFailureReason:
    """Map a CARIAD ``APIError`` (or any exception) to a failure reason.

    Conservative on purpose — when in doubt return ``UNKNOWN`` or
    ``BACKEND_ERROR`` rather than ``MISSING_CAPABILITY``. The latter
    leads to entities being permanently hidden, so we only return it for
    backend responses that explicitly say so.

    v1.9.1 (Capability-Filter Phase 2, #56) — body-content sniffing for
    common subscription / spin-error markers so the coordinator can
    auto-update ``FeatureState`` instead of treating every 4xx as
    ``BACKEND_ERROR``. Verified marker strings:

    - ``spin_error`` / ``spinState`` — confirmed live on Audi S6 C8 2021
      (#92): CARIAD BFF returns ``403`` with body
      ``{"error":{"message":"spin_error", "spinState":"DEFINED",
      "remainingTries":3}}`` when S-PIN is required but absent.
    - ``subscription`` / ``expired`` / ``license_required`` — the
      vocabulary used by audi_connect_ha #47 and migendi's #42 reports
      for paid online-services lapses.
    - ``not_entitled`` / ``entitlement`` — the OLA vocabulary used by
      gleeballs's free-tier We Connect Go report (#51).

    If the body has none of these markers we fall back to the
    HTTP-status-only classification.
    """
    if not isinstance(exc, APIError):
        return CommandFailureReason.UNKNOWN

    status = getattr(exc, "status", 0) or 0
    body = str(exc).lower()

    # Body-content first — these are unambiguous markers regardless of
    # which 4xx the backend used.
    if "missing-capability" in body or "missing_capability" in body:
        return CommandFailureReason.MISSING_CAPABILITY
    if "spin_error" in body or "spinstate" in body:
        return CommandFailureReason.SPIN_REQUIRED
    if "subscription" in body and ("expired" in body or "lapsed" in body):
        return CommandFailureReason.SUBSCRIPTION_EXPIRED
    if (
        "not_entitled" in body
        or "not-entitled" in body
        or "license_required" in body
        or "license-required" in body
        or "entitlement" in body
    ):
        return CommandFailureReason.NOT_ENTITLED

    # v1.20.3 — Cariad-BFF wraps real upstream backend issues in
    # fake-404 responses with a specific body marker. User-report
    # 2026-05-07 (Audi A4 B9 + Q5 2021 + VW Golf 7) showed all 3
    # vehicles WITH active Audi Connect Plus subscriptions hit the
    # same 404 for write commands. Body sample:
    #   {"error":{"message":"Not Found",
    #     "info":"Upstream service responded with an unexpected status",
    #     "code":4112,"group":2,"retry":true}}
    # The ``retry:true`` + "Upstream service" marker = transient
    # backend issue, NOT missing capability. Classify as
    # BACKEND_ERROR so the entity stays visible (user can retry)
    # instead of being hidden by Capability-Filter Phase 3.
    if (
        "upstream service responded" in body
        or "\"retry\":true" in body
        or "'retry': true" in body
    ):
        return CommandFailureReason.BACKEND_ERROR

    # Fall back to status-code-only classification.
    if status == 403:
        return CommandFailureReason.NOT_ENTITLED
    if status == 404:
        # 404 without a body marker is ambiguous: could mean we have
        # the wrong URL (integration bug) OR backend route doesn't
        # exist for this model (missing capability). Keep as
        # WRONG_API_PROFILE — Capability-Filter Phase 2 records the
        # failure for entity-availability tracking but doesn't
        # permanently hide. Phase 3 only hides on confirmed missing-
        # capability body markers.
        return CommandFailureReason.WRONG_API_PROFILE
    if status >= 500:
        return CommandFailureReason.BACKEND_ERROR
    if status == 400:
        # 400 with `internal-error` is ambiguous — could be expired
        # subscription, could be a transient backend error, could be
        # our payload. We can't tell from the HTTP layer alone, so we
        # return BACKEND_ERROR (the safe default) and let the
        # coordinator decide based on entitlement state if known.
        return CommandFailureReason.BACKEND_ERROR
    return CommandFailureReason.UNKNOWN


class CariadError(Exception):
    """Base exception for all CARIAD client errors."""


class AuthenticationError(CariadError):
    """Login failed — wrong credentials or account issue."""


class TermsAndConditionsError(AuthenticationError):
    """Terms and conditions must be accepted in the app before API access."""

    def __init__(self) -> None:
        super().__init__(
            "Terms and conditions pending. Open the brand app, sign in, and accept."
        )


class MarketingConsentError(AuthenticationError):
    """New privacy/marketing consent required."""

    def __init__(self) -> None:
        super().__init__(
            "Privacy consent required. App → Profile → Consents."
        )


class TwoFactorRequiredError(AuthenticationError):
    """2FA challenge — must be resolved once in the app."""

    def __init__(self) -> None:
        super().__init__(
            "2FA required. Sign in manually in the brand app once to confirm."
        )


class EmailTwoFactorRequiredError(TwoFactorRequiredError):
    """v2.2.0 (#183 follow-on) — Email-OTP 2FA challenge.

    Discriminated subclass of ``TwoFactorRequiredError`` for the case
    where the IDP issued an **email OTP** rather than an authenticator-
    app TOTP code. Detected via the ``/u/email-challenge`` URL fragment
    (Auth0 path) or ``email-otp`` / ``email-code`` body markers (Legacy
    path).

    UX matters: Email-2FA users need to check their **inbox** (and
    potentially spam) for a 6-digit code from VAG IDP, while TOTP users
    need their authenticator-app rolling code. Different messages →
    different mental models.

    Both flows ultimately need a one-time human ack in the brand app
    before headless API access works, so the Repair-issue surfacing is
    identical except for the actionable text. ``isinstance(err,
    TwoFactorRequiredError)`` keeps the existing handler chain working.
    """

    def __init__(self) -> None:
        # Skip parent's __init__ — we want the more specific message
        AuthenticationError.__init__(
            self,
            "Email 2FA required. Check your inbox (and spam) for a 6-digit "
            "code from VAG IDP, then sign in manually in the brand app once.",
        )


class RateLimitError(CariadError):
    """Account temporarily blocked by VAG rate limiter."""

    def __init__(self) -> None:
        super().__init__(
            "Account temporarily rate-limited. Wait 15 minutes, then retry."
        )


class UpstreamUnavailableError(CariadError):
    """v2.5.7 (#313 follow-on) — VAG backend (CARIAD-BFF / Azure WAF)
    is returning HTTP 5xx on requests that would normally succeed.

    Distinct from ``AuthenticationError`` so the config-flow + Repair
    surface can show a non-credentials message: it's NOT the user's
    password, it's VW's server side. Users were re-configuring their
    integration during the 2026-05-28 + 2026-05-29 502-storms because
    the failure looked like "wrong credentials" — this exception class
    + dedicated strings.json key prevents that misdiagnosis.

    Cross-references for the 502-storm class of failure:
    - evcc #30280 + #30324 (2026-05-29)
    - ioBroker.vw-connect #425 + #426 (2026-05-28 14:00 UTC onward)
    - our #309 moltke69 + 9mrcookie9 fresh dumps (2026-05-29)
    """

    def __init__(self, status: int, brand: str = "") -> None:
        msg = (
            f"VAG backend temporarily unavailable (HTTP {status})"
        )
        if brand:
            msg += f" for brand {brand}"
        msg += (
            ". This is a server-side issue at VW, not a credentials problem. "
            "Please wait 5–15 minutes and try again. Do NOT reconfigure the "
            "integration."
        )
        super().__init__(msg)
        self.status = status
        self.brand = brand


class TokenExpiredError(CariadError):
    """Access token expired and could not be refreshed."""


class SpinError(CariadError):
    """S-PIN required or incorrect — needed for lock/unlock commands."""


class VehicleNotFoundError(CariadError):
    """VIN not found in the account garage."""

    def __init__(self, vin: str) -> None:
        super().__init__(f"Vehicle {vin} not found in account garage.")
        self.vin = vin


class VehicleCommandError(CariadError):
    """Remote command rejected or timed out."""

    def __init__(self, command: str, reason: str = "") -> None:
        msg = f"Command '{command}' failed"
        if reason:
            msg += f": {reason}"
        super().__init__(msg)
        self.command = command


class APIError(CariadError):
    """Unexpected API response."""

    def __init__(self, status: int, url: str, body: str = "") -> None:
        super().__init__(f"API error {status} for {url}: {body[:200]}")
        self.status = status
        self.url = url
