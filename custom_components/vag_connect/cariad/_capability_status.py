# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Decode a capability's ``status`` array into a human-legible reason.

``coordinator.vehicle_supports_capability`` already gates entities on whether a
capability's ``status`` array is empty — but it treats every non-empty status
uniformly as "gated" and throws the specific value away. That leaves a user
whose climate button 404s with no idea *why*: an expired Audi connect
subscription, a car in deep sleep, a T&C step pending in the app, and a feature
the car simply doesn't have all looked identical.

This module maps each status value onto a coarse category and a short reason,
so the coordinator can surface "why" alongside the existing gating decision —
WITHOUT changing that decision. Two vocabularies coexist and are both handled
(normalised by casefold + stripping non-alphanumerics):

- CARIAD-BFF (Audi / VW EU), camelCase — the 31 values of the official app's
  ``technology.cariad.cat.capabilities.Status`` enum.
- Skoda mysmob, UPPER_SNAKE — the values documented in ``skodaconnect/myskoda``
  (``DEACTIVATED``, ``LICENSE_REQUIRED``, ``UNSUPPORTED``, ``NOT_ACTIVATED`` …).

The category is used to pick the most *actionable* reason when several statuses
are present, and to phrase the message.
"""

from __future__ import annotations

from typing import Final

# Categories, ordered most-actionable / most-informative first. The first
# category in this tuple that appears among a capability's statuses wins.
_CATEGORY_ORDER: Final[tuple[str, ...]] = (
    "license",
    "consent",
    "privacy",
    "permission",
    "unsupported",
    "deactivated",
    "transient",
    "unknown",
)

_CATEGORY_REASON: Final[dict[str, str]] = {
    "license": (
        "the online-services subscription/licence for this feature is "
        "inactive or expired — renew it in the brand app or portal"
    ),
    "consent": (
        "a consent or terms-and-conditions step is pending — open the brand "
        "app, sign in and accept it"
    ),
    "privacy": (
        "privacy mode is switched on in the car — turn it off in the "
        "vehicle to use remote features"
    ),
    "permission": (
        "your account lacks the required permission or security level "
        "(user role / S-PIN) for this feature"
    ),
    "unsupported": "this vehicle does not offer this feature",
    "deactivated": (
        "the feature is switched off — re-enable it in the brand app or the "
        "car's infotainment"
    ),
    "transient": (
        "temporarily unavailable — the car may be asleep, offline, or its "
        "battery/power budget too low right now"
    ),
    "unknown": "unavailable for a reason the backend did not specify",
}

# Normalised status value (casefold, alphanumerics only) → category.
# Keys are the normalised CARIAD-BFF WIRE values (the string constants in the
# app's ``capabilities.Status`` — e.g. field ``termsAndConditionsNotAccepted``
# actually serialises as ``"TAndCNotAccepted"``, so its key is the abbreviated
# ``tandcnotaccepted``, NOT the field name). Most values happen to serialise as
# the PascalCase of the field name, so casefold makes them line up with the
# camelCase field spelling — but abbreviated ones (T&C) must be keyed on the
# real wire form. Skoda mysmob UPPER_SNAKE values fold to the same keys.
_STATUS_CATEGORY: Final[dict[str, str]] = {
    # ── license / subscription ───────────────────────────────────────
    "licenseexpired": "license",
    "licenseinactive": "license",
    "missinglicense": "license",
    "licenserequired": "license",  # Skoda
    "connectivitylicenseinactive": "license",
    # ── consent / T&C / verification ─────────────────────────────────
    "consentmissing": "consent",  # wire "ConsentMissing"
    "tandcnotaccepted": "consent",  # real wire value (abbreviated in the app)
    "termsandconditionsnotaccepted": "consent",  # spelled-out fallback
    "usernotverified": "consent",
    # ── privacy mode (user toggled it ON in the car; not a consent gap) ──
    "privacymode": "privacy",
    # ── permission / rights / S-PIN ──────────────────────────────────
    "insufficientrights": "permission",
    "insufficientuserrole": "permission",
    "insufficientsecuritylevel": "permission",
    "backendiscustomerenforced": "permission",
    "vehicleiscustomerenforced": "permission",
    # ── not supported for this vehicle ───────────────────────────────
    "unsupported": "unsupported",
    "missingservice": "unsupported",
    "missingoperation": "unsupported",
    "vehicledisabled": "unsupported",
    # ── switched off (recoverable in app/car) ────────────────────────
    "deactivated": "deactivated",
    "deactivatedbyactivevehicleuser": "deactivated",
    "disabledbyuser": "deactivated",
    "frontendswitchedoff": "deactivated",
    "initiallydisabled": "deactivated",
    "singleservicedeactivationincar": "deactivated",
    "locationdatadisabled": "deactivated",
    "notactivated": "deactivated",  # Skoda
    "workshopmode": "deactivated",
    # ── transient (temporary) ────────────────────────────────────────
    "insufficientbatterylevel": "transient",
    "deepsleep": "transient",
    "vehiclenotreachable": "transient",
    "powerbudgetreached": "transient",
    "datasavingmodeenabledforvehicle": "transient",
    # ── explicit unknown ─────────────────────────────────────────────
    "unknown": "unknown",
    "companion": "unknown",
}


def _normalise(value: object) -> str:
    """Casefold + keep only alphanumerics, so camelCase == UPPER_SNAKE."""
    return "".join(ch for ch in str(value).casefold() if ch.isalnum())


def category_for_status(value: object) -> str:
    """Return the coarse category for a single status value.

    Unknown / unmapped values return ``"unknown"`` rather than raising, so a
    status vocabulary that grows on the backend degrades gracefully.
    """
    key = _normalise(value)
    if not key:
        return "unknown"
    return _STATUS_CATEGORY.get(key, "unknown")


def capability_status_reason(status_values: object) -> tuple[str, str] | None:
    """Return ``(category, human_reason)`` for a capability's status list.

    Picks the most actionable/informative status when several are present
    (``_CATEGORY_ORDER``). Returns ``None`` for an empty / non-list / all-empty
    status — i.e. "no limitation to explain", matching the gate's "empty status
    → usable" rule. Never raises.
    """
    if not status_values:
        return None
    if isinstance(status_values, (str, bytes)):
        items: list[object] = [status_values]
    elif isinstance(status_values, (list, tuple, set)):
        items = [v for v in status_values if v not in (None, "")]
    else:
        items = [status_values]
    if not items:
        return None
    categories = {category_for_status(v) for v in items}
    for cat in _CATEGORY_ORDER:
        if cat in categories:
            return cat, _CATEGORY_REASON[cat]
    return "unknown", _CATEGORY_REASON["unknown"]
