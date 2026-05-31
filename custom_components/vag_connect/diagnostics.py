# Copyright 2026 Prash Balan (@its-me-prash) — Apache License 2.0
"""Diagnostics for VAG Connect.

v1.13.0 (#62) — expanded redaction:
- Token fields (access_token / refresh_token / id_token) explicitly
  added to the keep-out list so future code paths that accidentally
  store tokens in entry.data (today they only live in coordinator
  in-memory cache) get caught.
- Email values get partial-mask format ``u***@***.com`` instead of
  bare ``**REDACTED**`` — keeps domain shape for context while
  hiding the local-part.
- GPS coordinates: opt-in toggle to keep them rounded to 1 decimal
  (~11 km bucket) instead of full removal. Default still removes
  for privacy-by-default; users who want better debug info can
  enable via the ``CONF_ENABLE_REVERSE_GEOCODING`` option (already
  signals "I'm OK with GPS being processed").
"""

from __future__ import annotations

import hashlib
import re
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .cariad._error_reporter import serialise_for_diagnostics
# v2.8.0 quick win D — reuse the Scout module's PII regexes (VIN / JWT
# / UUID) for the new parser-health ``last_error`` redactor. Email is
# handled by the partial-mask helper already defined below so we don't
# import that pattern here.
from .cariad._unexpected_keys import _JWT_RE, _UUID_RE, _VIN_RE
from .cariad._util import mask_vin
from .const import (
    CONF_BRAND,
    CONF_ENABLE_REVERSE_GEOCODING,
    CONF_PASSWORD,
    CONF_SPIN,
    CONF_USERNAME,
)
from .coordinator import VagConnectCoordinator

_REDACT_KEYS = frozenset({
    CONF_PASSWORD,
    CONF_SPIN,
    CONF_USERNAME,
    "vin",
    "address",
    "parking_address",
    "user_id",
    "account_id",
    # v1.13.0 (#62) — explicit token field names. Defensive registration:
    # today these only live in coordinator's in-memory cache, but if a
    # future change adds them to entry.data they'll automatically
    # redact instead of leaking. Includes both snake_case (Python) and
    # camelCase (JSON) forms.
    "access_token",
    "refresh_token",
    "id_token",
    "accessToken",
    "refreshToken",
    "idToken",
    "id_token_hint",
    "client_secret",
})

# v1.13.0 (#62) — email partial-mask. Keeps domain TLD shape (e.g.
# ``.com``/``.de``) for debug context but redacts the local-part and
# domain name.
_EMAIL_RE = re.compile(
    r"\b([A-Za-z0-9._%+-])([A-Za-z0-9._%+-]*)@[A-Za-z0-9.-]+\.([A-Za-z]{2,})\b"
)

# v1.15.0 — query-string GPS scrubbing borrowed from
# ``skodaconnect/myskoda/anonymize.py``. URLs like
# ``/v1/maps/positions?latitude=48.13743&longitude=11.57549&radius=...``
# leak GPS in path-side query-strings that the dict-key based
# ``_scrub`` couldn't catch (lat/lon are inside a string value, not
# their own dict keys). Replaces with rounded-1-decimal in opt-in mode
# or full ``REDACTED`` in privacy-by-default mode.
_LOCATION_QS_RE = re.compile(
    r"(latitude=)(-?\d+\.?\d*)(&\s*longitude=)(-?\d+\.?\d*)",
    re.IGNORECASE,
)


def _mask_email(value: str) -> str:
    """Replace ``user@example.com`` → ``u***@***.com``."""
    return _EMAIL_RE.sub(lambda m: f"{m.group(1)}***@***.{m.group(3)}", value)


def _mask_location_qs(value: str, *, gps_round: bool = False) -> str:
    """v1.15.0 — scrub ``latitude=...&longitude=...`` from URL query strings.

    Borrowed pattern from ``skodaconnect/myskoda/anonymize.py``. Catches
    GPS leaked in path-side query-strings that the dict-key based
    ``_scrub`` doesn't see (e.g. error messages logging the failing URL).

    ``gps_round=True`` mode keeps the URL valid with ~11 km granularity
    so the receiving log is still useful; default mode replaces with
    ``REDACTED`` markers.
    """
    if "latitude=" not in value:
        return value

    def _replace(m: re.Match[str]) -> str:
        if gps_round:
            try:
                lat = round(float(m.group(2)), 1)
                lon = round(float(m.group(4)), 1)
                return f"{m.group(1)}{lat}{m.group(3)}{lon}"
            except (TypeError, ValueError):
                pass
        return f"{m.group(1)}REDACTED{m.group(3)}REDACTED"

    return _LOCATION_QS_RE.sub(_replace, value)


def _redact_parser_error(value: Any) -> str:
    """v2.8.0 quick win D — scrub PII from a parser-stats ``last_error``.

    Parser errors can include arbitrary backend text or exception
    messages that the integration never auditioned for sensitivity.
    Strip VINs, JWT-shaped tokens, UUIDs (used for userIDs), embedded
    emails and query-string GPS pairs before the string lands in a
    user-shareable diagnostics file.

    Non-string inputs are coerced to ``""`` so callers don't need a
    pre-flight ``isinstance`` check.
    """
    if not isinstance(value, str) or not value:
        return ""
    out = _VIN_RE.sub("***VIN***", value)
    out = _JWT_RE.sub("***JWT***", out)
    out = _UUID_RE.sub("***UUID***", out)
    out = _mask_email(out)
    out = _mask_location_qs(out, gps_round=False)
    # Cap length defensively (same 200-char cap as the source counter)
    return out[:200]


# v1.15.0 — stable-hash helper from ``skodaconnect/myskoda/anonymize.py``.
# Produces a deterministic SHA-256-based pseudonym so a repeat reporter
# can be cross-referenced ("oh that's the same user as last week's bug")
# without revealing their real ID. Truncated to 12 hex chars — enough
# entropy to disambiguate, short enough to read at a glance.
def _stable_hash(value: str, *, salt: str = "vag-connect-ha") -> str:
    """Return a 12-hex stable digest of *value*. Empty input → empty string."""
    if not value:
        return ""
    digest = hashlib.sha256(f"{salt}:{value}".encode("utf-8")).hexdigest()
    return digest[:12]


# v1.15.0 — keys that get a stable SHA-256 pseudonym instead of bare
# ``REDACTED``. Lets a repeat reporter be cross-referenced (e.g. "this
# is the same Skoda user as the previous bug ticket") without revealing
# their real ID. Pattern from ``skodaconnect/myskoda/anonymize.py``.
_HASH_KEYS = frozenset({
    "user_id",
    "userId",
    "account_id",
    "accountId",
})


def _scrub(value: Any, *, gps_round: bool = False) -> Any:
    """Recursively redact sensitive fields from diagnostics output.

    Args:
        value: any nested structure (dict / list / scalar)
        gps_round: when True, round latitude/longitude to 1 decimal
            instead of redacting completely. Default False
            (privacy-by-default per Hard Rule #18).
    """
    if isinstance(value, dict):
        scrubbed: dict[str, Any] = {}
        for k, v in value.items():
            if k in ("_client", "_vehicle"):
                continue
            if k in _HASH_KEYS and isinstance(v, str):
                # v1.15.0 — stable hash so repeat reporters cross-link
                # without leaking the real ID. Pattern from myskoda.
                scrubbed[k] = f"sha256:{_stable_hash(v)}" if v else "**REDACTED**"
            elif k in _REDACT_KEYS:
                scrubbed[k] = "**REDACTED**"
            elif k == "email" and isinstance(v, str):
                # Partial mask preserves debug context.
                scrubbed[k] = _mask_email(v)
            elif k in ("latitude", "longitude"):
                # Privacy-by-default: full removal. Opt-in 1-decimal
                # rounding when user already opted into reverse-geocoding
                # (signals comfort with GPS processing).
                if gps_round and isinstance(v, (int, float)):
                    scrubbed[k] = round(float(v), 1)
                else:
                    scrubbed[k] = "**REDACTED**"
            else:
                scrubbed[k] = _scrub(v, gps_round=gps_round)
        return scrubbed
    if isinstance(value, list):
        return [_scrub(v, gps_round=gps_round) for v in value]
    if isinstance(value, str):
        # v1.13.0 — catch emails embedded in free text (log lines, error
        # messages). v1.15.0 — also scrub query-string GPS leaks (e.g.
        # mysmob ``/v1/maps/positions?latitude=...&longitude=...`` URLs
        # that surface in error traces).
        masked = _mask_email(value)
        return _mask_location_qs(masked, gps_round=gps_round)
    return value


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> dict[str, Any]:
    """Return diagnostics with VIN, GPS, credentials and other PII redacted.

    v1.13.0 (#62) — GPS rounding is opt-in: if the user already enabled
    ``CONF_ENABLE_REVERSE_GEOCODING`` they're comfortable with GPS
    processing for parking-address resolution, so the diagnostics
    surfaces 1-decimal-rounded coords (~11 km bucket — useful for
    debug, still privacy-safe). Otherwise full removal.
    """
    coordinator: VagConnectCoordinator = entry.runtime_data

    # GPS-rounding opt-in — same signal as the reverse-geocoding toggle.
    gps_round = bool(
        entry.options.get(CONF_ENABLE_REVERSE_GEOCODING, False) is True
        or entry.data.get(CONF_ENABLE_REVERSE_GEOCODING, False) is True
    )

    config_diag = _scrub(dict(entry.data), gps_round=False)  # config never rounds
    options_diag = _scrub(dict(entry.options), gps_round=False)

    vehicles_diag: dict[str, Any] = {}
    for vin, vdata in coordinator.vehicles.items():
        vehicles_diag[mask_vin(vin)] = _scrub(vdata, gps_round=gps_round)

    # v1.9.0 — Vehicle Data Scout findings + Error Reporter buffer.
    # Already masked at the source (mask_value / _redact). Surfaced here so
    # users who download diagnostics for forum / Facebook posts get the
    # full anonymised picture in one file.
    unexpected: dict[str, list[dict[str, Any]]] = {}
    for vin, per_vin in getattr(coordinator, "unexpected_findings", {}).items():
        unexpected[mask_vin(vin)] = [
            {
                "path": f.path,
                "sample": f.sample_masked,
                "endpoint": f.endpoint,
                "first_seen_at": f.first_seen_at,
            }
            for f in per_vin.values()
        ]

    error_buffer = getattr(coordinator, "error_buffer", None)
    error_records = (
        serialise_for_diagnostics(error_buffer) if error_buffer is not None else []
    )

    # v2.8.0 quick win D — parser-health telemetry. Each brand client
    # accumulates per-job success/fail counters in ``parser_stats``.
    # The coordinator owns a single brand client per config entry; we
    # surface its snapshot keyed by brand so multi-entry installations
    # show the same shape as a future multi-brand single-entry would.
    brand = entry.data.get(CONF_BRAND, "")
    client = getattr(coordinator, "_cariad_client", None)
    raw_parser_stats = (
        getattr(client, "parser_stats", {}) if client is not None else {}
    )
    parser_stats_diag: dict[str, dict[str, Any]] = {}
    if brand and isinstance(raw_parser_stats, dict):
        parser_stats_diag[brand] = {
            job: {
                "success": stats.get("success", 0),
                "fail": stats.get("fail", 0),
                "last_error": _redact_parser_error(stats.get("last_error", "")),
            }
            for job, stats in raw_parser_stats.items()
            if isinstance(stats, dict)
        }

    # v2.8.0 quick win E — per-brand declared vs observed capability
    # snapshot. Tells us at-a-glance whether a missing entity is
    # because the brand never supported it, the vehicle does not have
    # it, or the parser dropped a payload key. Defensive ``getattr``
    # so older coordinator instances in tests / partial setups do not
    # break the diagnostics export.
    capabilities_fn = getattr(coordinator, "capabilities_snapshot", None)
    capabilities: dict[str, Any] = {}
    if callable(capabilities_fn):
        try:
            capabilities = capabilities_fn()
        except Exception as err:  # noqa: BLE001
            capabilities = {"error": f"{type(err).__name__}: {err}"}

    return {
        "config": config_diag,
        "options": options_diag,
        "vehicles": vehicles_diag,
        "vehicle_count": len(coordinator.vehicles),
        "last_update_success": coordinator.last_update_success,
        "cloud_push_active": coordinator.is_active,
        "unexpected_findings": unexpected,
        "error_buffer": error_records,
        "parser_stats": parser_stats_diag,
        "capabilities": capabilities,
    }
