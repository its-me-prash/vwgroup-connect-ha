# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
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
    CONF_ABRP_API_KEY,
    CONF_ABRP_USER_TOKEN,
    CONF_BRAND,
    CONF_ENABLE_REVERSE_GEOCODING,
    CONF_PASSWORD,
    CONF_SPIN,
    CONF_SPIN_BY_VIN,
    CONF_SUPPLEMENTARY_AUTHPROXY_COOKIES,
    CONF_SUPPLEMENTARY_EU_PORTAL_PASSWORD,
    CONF_SUPPLEMENTARY_EU_PORTAL_USERNAME,
    CONF_USERNAME,
)
from .coordinator import VagConnectCoordinator

_REDACT_KEYS = frozenset({
    CONF_PASSWORD,
    CONF_SPIN,
    # v2.18.0 — the per-VIN S-PIN map (#759, shipped 2.17.5) is a
    # {VIN: S-PIN} dict. Without this it fell through to the generic dict
    # branch and got walked, emitting a real VIN as the key and the S-PIN
    # as a plaintext value into every diagnostics download — the same class
    # of leak the b11 note below documents fixing. Redact the whole map.
    CONF_SPIN_BY_VIN,
    # v2.18.0 — both ABRP credentials leaked in plaintext, despite the
    # options help text promising "Never logged".
    CONF_ABRP_API_KEY,
    CONF_ABRP_USER_TOKEN,
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
    # b11 — supplementary-channel credentials/secrets (added in b8/b9 but never
    # registered here, so the portal password leaked in PLAINTEXT in the
    # diagnostics download — exactly the file users attach to GitHub issues).
    # The vw.de cookie list carries the auth0 / auth0-mf SSO session tokens.
    CONF_SUPPLEMENTARY_EU_PORTAL_PASSWORD,
    CONF_SUPPLEMENTARY_EU_PORTAL_USERNAME,
    CONF_SUPPLEMENTARY_AUTHPROXY_COOKIES,
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


def _mask_key(k: Any) -> Any:
    """Mask PII that appears as a dict KEY, not just as a value.

    v3.0.1 (#923, #1088) — some payloads key a container by the VIN itself
    (e.g. ``data_act_identifiers: {"<VIN>": {...}}``). The recursive scrubbers
    only ran the VIN/JWT regexes over string VALUES, so a VIN used as a key
    survived in plain text — two reporters had to hand-redact their download
    before posting. VIN + JWT are masked here; UUID keys are deliberately kept
    (they are structural grounding data, not PII).
    """
    if not isinstance(k, str):
        return k
    masked = _VIN_RE.sub(lambda m: mask_vin(m.group(0)), k)
    masked = _JWT_RE.sub("[token]", masked)
    return masked


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
            # v3.0.1 — mask PII in the KEY too (a VIN can be a container key).
            sk = _mask_key(k)
            if k in _HASH_KEYS and isinstance(v, str):
                # v1.15.0 — stable hash so repeat reporters cross-link
                # without leaking the real ID. Pattern from myskoda.
                scrubbed[sk] = f"sha256:{_stable_hash(v)}" if v else "**REDACTED**"
            elif k in _REDACT_KEYS:
                scrubbed[sk] = "**REDACTED**"
            elif k == "email" and isinstance(v, str):
                # Partial mask preserves debug context.
                scrubbed[sk] = _mask_email(v)
            elif k in ("latitude", "longitude"):
                # Privacy-by-default: full removal. Opt-in 1-decimal
                # rounding when user already opted into reverse-geocoding
                # (signals comfort with GPS processing).
                if gps_round and isinstance(v, (int, float)):
                    scrubbed[sk] = round(float(v), 1)
                else:
                    scrubbed[sk] = "**REDACTED**"
            else:
                scrubbed[sk] = _scrub(v, gps_round=gps_round)
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


# v3.0.0 — extra PII keys that only turn up in RAW brand API payloads (the
# key-based _scrub above targets OUR own field names). Matched case-insensitively
# because raw wire keys are camelCase. GPS is always removed in raw payloads,
# never rounded — a raw capture is the most sensitive thing we export.
_RAW_REDACT_KEYS = frozenset({
    # NOTE: bare "id" is deliberately NOT here — it catches harmless
    # profile/enum ids and costs grounding value, while VIN/JWT/UUID regexes
    # already mask real identifiers in the VALUES below.
    "vin", "carid", "vehicleid", "userid", "accountid", "customerid",
    "gpscoordinates", "carcapturedgpscoordinates", "coordinates",
    "latitude", "longitude", "lat", "lng", "lon",
    "licenceplate", "licenseplate", "numberplate", "registrationnumber",
    "nickname", "firstname", "lastname", "givenname", "familyname", "fullname",
    "dateofbirth", "birthdate", "phone", "phonenumber", "mobile",
    "email", "emailaddress", "salutation",
    "street", "streetname", "housenumber", "zipcode", "postalcode", "city",
    "address", "formattedaddress",
})


def _scrub_raw(value: Any) -> Any:
    """Aggressively redact a RAW brand API payload before it goes into the
    downloadable diagnostics. Single pass that combines every rule we trust:

    * the key-based ``_REDACT_KEYS`` / ``_HASH_KEYS`` rules from ``_scrub``;
    * a raw-only PII key set (``_RAW_REDACT_KEYS``, case-insensitive) for wire
      names we don't use ourselves (licencePlate, gpsCoordinates, nickname…);
    * regex masking of VIN / JWT / UUID in EVERY string value, because raw
      payloads embed identifiers in URLs and free text under unpredictable keys.

    Keeps field NAMES and non-PII sample values intact — that structure is
    exactly what lets us map a new field into a feature. GPS is always removed.
    """
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for k, v in value.items():
            kl = k.lower() if isinstance(k, str) else ""
            # v3.0.1 — mask PII in the KEY too (a VIN can be a container key).
            sk = _mask_key(k)
            if k in _REDACT_KEYS or kl in _RAW_REDACT_KEYS:
                out[sk] = "**REDACTED**"
            elif k in _HASH_KEYS and isinstance(v, str):
                out[sk] = f"sha256:{_stable_hash(v)}" if v else "**REDACTED**"
            else:
                out[sk] = _scrub_raw(v)
        return out
    if isinstance(value, list):
        return [_scrub_raw(v) for v in value]
    if isinstance(value, str):
        s = _mask_email(value)
        s = _mask_location_qs(s, gps_round=False)
        s = _VIN_RE.sub(lambda m: mask_vin(m.group(0)), s)
        s = _JWT_RE.sub("[token]", s)
        s = _UUID_RE.sub("[uuid]", s)
        return s
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

    # v3.0.0 — the RAW brand API responses (aggressively redacted). The Scout
    # already surfaces the unmapped field NAMES; this adds the surrounding
    # structure + sample values so a maintainer can turn a new field into a
    # feature without asking the reporter to capture anything by hand. This is
    # what the "help build features" repair points people at.
    raw_responses: dict[str, Any] = {}
    raw = getattr(client, "last_raw_responses", None) if client is not None else None
    if isinstance(raw, dict):
        for channel, payload in raw.items():
            try:
                raw_responses[str(channel)] = _scrub_raw(payload)
            except Exception as err:  # noqa: BLE001 — never let one channel break the export
                raw_responses[str(channel)] = {"error": f"{type(err).__name__}"}

    # #923/#1157 — surface the experimental vw.de probe outcomes so the test
    # cohort can see WHY a probe yielded nothing (a 403/404/412 refusal vs an
    # empty 200 vs a never-fired probe). Bare status labels only — no PII.
    probe_outcomes: dict[str, str] = {}
    _po = getattr(client, "probe_outcomes", None) if client is not None else None
    if isinstance(_po, dict):
        probe_outcomes = {str(k): str(v) for k, v in _po.items()}

    # #584 — surface the durable "no legacy MBB enrolment" verdict. These VINs
    # got the definitive ``gw.error.authentication`` reject on the MBB
    # operationList, i.e. the car/account is read-only (EU-DA / vw.de) and MBB
    # commands are unavailable — so a #584-class report is triageable straight
    # from the diagnostics instead of asking the reporter for a debug log.
    mbb_no_legacy: list[str] = []
    _nl = getattr(client, "mbb_no_legacy_vins", None) if client is not None else None
    if _nl:
        try:
            mbb_no_legacy = sorted(mask_vin(v) for v in _nl)
        except Exception:  # noqa: BLE001
            mbb_no_legacy = []

    return {
        "config": config_diag,
        "options": options_diag,
        "vehicles": vehicles_diag,
        "vehicle_count": len(coordinator.vehicles),
        "last_update_success": coordinator.last_update_success,
        "cloud_push_active": coordinator.cloud_push_active,
        "push_states": coordinator.push_states,
        "polling_active": coordinator.is_active,
        "unexpected_findings": unexpected,
        "raw_responses": raw_responses,
        "probe_outcomes": probe_outcomes,
        "error_buffer": error_records,
        "parser_stats": parser_stats_diag,
        "capabilities": capabilities,
        "mbb_no_legacy": mbb_no_legacy,
    }
