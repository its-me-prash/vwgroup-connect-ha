# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Diagnostics for VW Group Connect.

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
from homeassistant.helpers.device_registry import DeviceEntry

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
    CONF_ADB_HOST,
    CONF_COMPANION_ADDON_TOKEN,
    CONF_COMPANION_AGENT_TOKEN,
    CONF_BRAND,
    CONF_DATA_ACT_IDENTIFIERS,
    CONF_DATA_ACT_KICKOFF_TS,
    CONF_ENABLE_REVERSE_GEOCODING,
    CONF_MBB_COMMAND_TOKENS,
    CONF_PASSWORD,
    CONF_SPIN,
    CONF_SPIN_BY_VIN,
    CONF_SUPPLEMENTARY_AUTHPROXY_COOKIES,
    CONF_SUPPLEMENTARY_EU_PORTAL_PASSWORD,
    CONF_SUPPLEMENTARY_EU_PORTAL_USERNAME,
    CONF_SUPPLEMENTARY_TIBBER_TOKENS,
    CONF_USERNAME,
    CONF_WEBSITE_COOKIES,
    CONF_VWEU_TWOWAY_COOKIES,
    CONF_VWEU_TWOWAY_EMAIL,
    CONF_VWEU_TWOWAY_PASSWORD,
    CONF_VWEU_TWOWAY_TOKENS,
    DOMAIN,
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
    # b7 (grounded audit P0-2a) — parking_address is redacted but its sibling
    # parking_city carried a CLEARTEXT city name straight into the diagnostics
    # download (the file owners attach to public GitHub issues). A plain city hits
    # only the generic string branch, which masks e-mail/VIN/latitude=&longitude=
    # but nothing matches a bare city name. myskoda treats the whole address block
    # as one PII unit for exactly this reason (their #477 was this leak class).
    # Redact it by key so it can't fall through regardless of the value form.
    "parking_city",
    # The two map renders of the parking position (OLA parkingposition supplies
    # them; the comment at their assignment calls them map URLs of the parking
    # location). Same family as parking_address and parking_city above, and the
    # only members of it that had no branch. Redacted by key, like the others,
    # because the generic string branch is not shaped for this value form.
    # Whether the URL encodes the position as numbers or as an opaque token is
    # not established — every sample in our fixtures is a bare "https://..." —
    # and redacting is the cheap side of that uncertainty. Pinned by
    # tests/test_diagnostics_parking_map_url.py, which also records why the
    # string branch does not cover it, so this entry is not removed as redundant.
    "parking_map_url_dark",
    "parking_map_url_light",
    "user_id",
    "account_id",
    # D#1231 — the volkswagen.de profile block is personal: the number plate
    # identifies the car, the owner-chosen nickname is personal, and the render
    # image URLs encode the exact model/colour/config. A tester rightly had to
    # hand-mask these before attaching a diagnostics file, so redact them by
    # default. (Empty ones stay visibly empty via the _is_empty_value guard.)
    "license_plate",
    "vehicle_nickname",
    "image_urls",
    # #1832 — our own two other render-URL fields: the same content as
    # ``image_urls`` directly above, under different names, and with no branch
    # at all. ``render_url`` is the Skoda widget's ``vehicle.renderUrl``
    # (cariad/models.py:1153); ``composite_render_urls`` is the multi-angle
    # render map the coordinator builds at coordinator.py:7134
    # (cariad/models.py:1166) and then merges INTO ``image_urls`` — so the merge
    # target was masked while the source dict went out whole. ``to_dict`` is a
    # bare ``asdict`` (cariad/models.py:2450-2453) and the per-vehicle export
    # runs no field allowlist, so both reached the download complete; the #1310
    # string branch below masked the VIN inside them, never the URL itself.
    # Cost, stated rather than hidden: masking the dict whole takes its
    # viewPoint labels with it. That is the cost ``image_urls`` has always paid,
    # and matching it beats inventing a third behaviour for our own parsed
    # state. Pinned by tests/test_1832_render_url_spellings.py.
    "render_url",
    "composite_render_urls",
    # Companion: the VW app's charging-location labels are the owner's own
    # names for where the car habitually charges ("Home", a street, an
    # employer), the same class as parking_city and vehicle_nickname above.
    "charging_location_1_name",
    "charging_location_2_name",
    "charging_location_3_name",
    "charging_location_4_name",
    "charging_location_5_name",
    "charging_location_current",
    # #923 follow-up — the Skoda / SEAT / CUPRA charging PROFILE carries the
    # same class of label under a different name, and the comment above was
    # already the argument for registering it: it is the owner's own word for
    # where the car habitually charges. The per-profile twin lives inside the
    # ``charging_profiles`` list and is handled by _redact_charging_profiles,
    # because a bare ``name`` key cannot be registered here without redacting
    # every brand, device and entity name in the file.
    "active_charging_profile_name",
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
    # VW EU Two-Way (650d46ca): the stored login password, email, the minted
    # device_grant token dict, and the re-auth cookies MUST never appear in a
    # diagnostics download (the file users attach to GitHub issues).
    CONF_VWEU_TWOWAY_PASSWORD,
    CONF_VWEU_TWOWAY_EMAIL,
    CONF_VWEU_TWOWAY_TOKENS,
    CONF_VWEU_TWOWAY_COOKIES,
    # Companion credentials and the phone/add-on LAN hostname or IP.
    CONF_COMPANION_AGENT_TOKEN,
    CONF_COMPANION_ADDON_TOKEN,
    CONF_ADB_HOST,
    # #1286 — the Škoda official public-API key IS a credential: it grants read
    # (and charge-control) access to the car's official API. The single manual key
    # (CONF_SKODA_OFFICIAL_API_KEY) leaked in PLAINTEXT in the diagnostics download
    # users attach to GitHub issues — a real ``msk_…`` key was exposed publicly.
    # Mask it here. The auto-enrolled per-VIN map (CONF_SKODA_OFFICIAL_KEYS) is a
    # ``{VIN: {key, id, validUntil}}`` dict and is routed through
    # _redact_identifier_map below (keeps the enrolment count, masks each record).
    "skoda_official_api_key",
    # #923 — three credential keys that were never registered here, found by
    # deriving the list from const.py instead of reading this one. The b11 note
    # above says in so many words that "the vw.de cookie list carries the
    # auth0 / auth0-mf SSO session tokens" — and then registers the
    # SUPPLEMENTARY slot's jar while leaving the PRIMARY one out. Both sibling
    # jars were covered, so the gap read as closed. Same shape for the tokens:
    # the Companion, VW-EU two-way and Škoda token maps were registered and
    # these two were not.
    #
    #   CONF_WEBSITE_COOKIES          — the live vw.de session jar, written back
    #                                   to the entry on every refresh.
    #   CONF_MBB_COMMAND_TOKENS       — per-VIN MBB command tokens.
    #   CONF_SUPPLEMENTARY_TIBBER_TOKENS — the Tibber account's tokens.
    #
    # All three land in ``entry.data``, which this module dumps as ``config``,
    # and a cookie or token value is opaque, so no generic branch below masks
    # it. ``test_diagnostics_redaction_completeness`` now derives the expected
    # set from const.py so the next one cannot be forgotten in the same way.
    CONF_WEBSITE_COOKIES,
    CONF_MBB_COMMAND_TOKENS,
    CONF_SUPPLEMENTARY_TIBBER_TOKENS,
})


def _is_empty_value(v: Any) -> bool:
    """#923 — True for a value that carries no information worth masking.

    Redacting an empty field to ``**REDACTED**`` hides the fact that it was
    empty, so a reporter can't distinguish "no data" from "present but hidden".
    We treat ``None``, empty string and empty container as empty; ``0``/``False``
    are real values and are left to the normal redaction path.
    """
    return v is None or v == "" or v == [] or v == {}


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


def _redact_identifier_map(value: Any) -> Any:
    """Redact the VALUES of a ``{VIN: identifier}`` map, keeping the masked keys.

    The EU-Data-Act identifier map (#923 / #1222) is keyed by VIN with the portal
    Custom-Data-Request identifier string as the value. v3.0.1 masked the VIN used
    as the key, but the identifier value stayed clear-text — the config scrubber
    only runs the email/GPS regexes over string values, so a per-VIN portal
    identifier went out in plaintext in the download users attach to public
    issues. Keep the container (the enrolment count stays useful) but redact each
    value. Reported by @ggfbrkt6mc-max.
    """
    if isinstance(value, dict):
        return {_mask_key(k): "**REDACTED**" for k in value}
    return "**REDACTED**"


# Every key name under which this integration writes a coordinate into its OWN
# output. Not the wire names - those go through _scrub_raw / _RAW_REDACT_KEYS,
# which already covers lat / lon / latitude / longitude.
#
# #923 follow-up, measured 31.10.2026. The cookie-jar defect was a SHAPE
# problem: a list of objects whose inner key names are in no set. Generalising
# from it turned up a second one of exactly that shape, and this one had been
# emitting in the clear: ``coordinator.py`` flattens each Skoda / SEAT / CUPRA
# charging profile into ``{"name": ..., "location_lat": ..., "location_lon":
# ...}`` (:1346-1370), and the GPS branch below only ever matched the two
# spellings ``latitude`` / ``longitude``. So the coordinates of the place the
# car habitually charges - home, for most people - went into the download at
# two decimals, about a kilometre, in BOTH the default and the opt-in mode,
# while this module's own contract promises privacy-by-default removal.
#
# Verified by measurement, not by reading: a profile in the production shape
# through the real _scrub returned both coordinates and the owner's label
# unchanged, with a positive control confirming that bare ``latitude`` does get
# removed, so the branch itself was working and the names were the gap.
_GPS_KEYS = frozenset({
    "latitude",
    "longitude",
    "location_lat",
    "location_lon",
})


def _redact_charging_profiles(value: Any, *, gps_round: bool = False) -> Any:
    """Mask the owner's label on each charging profile, keep the rest.

    Same reasoning as the ``charging_location_N_name`` registrations: the label
    is the owner's own word for a place ("Home", an employer). It cannot be
    registered by key, because inside a profile it is spelled ``name`` and a
    global ``name`` rule would redact every brand, device and entity name in
    the file.

    Everything else in a profile is useful for triage and stays: the target
    SoC, the current limit, the counts. The coordinates are handled by the
    _GPS_KEYS branch once the recursion reaches them.
    """
    if not isinstance(value, list):
        return _scrub(value, gps_round=gps_round)
    out = []
    for item in value:
        if not isinstance(item, dict):
            out.append(_scrub(item, gps_round=gps_round))
            continue
        scrubbed = _scrub(item, gps_round=gps_round)
        if isinstance(scrubbed, dict) and "name" in scrubbed:
            # An empty label stays visibly empty, never a fake redaction -
            # same rule as the _REDACT_KEYS branch.
            scrubbed["name"] = (
                "**REDACTED**"
                if not _is_empty_value(item.get("name"))
                else item.get("name")
            )
        out.append(scrubbed)
    return out


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
            # #923 follow-up, measured 31.10.2026 — every rule below that keys
            # off a NAME was defeated by a dotted name, because the test is
            # exact equality on the whole key. That matters here specifically:
            # EU Data Act field names ARE dotted (the dictionary's own count is
            # 3206 of 7990), and an UNMAPPED portal field lands verbatim in
            # ``raw_unmapped_fields``, which this module emits. Measured, with
            # one marker per key: ``latitude``, ``access_token`` and ``user_id``
            # were handled, while ``parking_position.latitude``,
            # ``vehicle.parking.longitude``, ``settings.access_token``,
            # ``auth.tokens.refresh_token`` and ``vehicle.user_id`` all came
            # through in the clear. The value-PATTERN rules (e-mail, VIN, JWT)
            # were never affected — ``profile.email`` masked correctly — which
            # is exactly why this went unnoticed: the file looked redacted.
            #
            # So match the last segment as well. A dotted name whose leaf is a
            # registered one carries the same KIND of data as the bare name, so
            # treating them alike is the conservative direction; the opposite
            # choice is what shipped. ``sk`` keeps the full dotted spelling, so
            # a reader can still see which field was redacted.
            kl = k.rsplit(".", 1)[-1] if isinstance(k, str) and "." in k else k
            if kl in _HASH_KEYS and isinstance(v, str):
                # v1.15.0 — stable hash so repeat reporters cross-link
                # without leaking the real ID. Pattern from myskoda.
                scrubbed[sk] = f"sha256:{_stable_hash(v)}" if v else "**REDACTED**"
            elif kl in _REDACT_KEYS:
                # #923 (@naked-head) — only mask when there is actually a value
                # to hide. Masking an empty field as "**REDACTED**" makes it
                # indistinguishable from a redacted *real* value, which misleads
                # triage: a reporter (or I) cannot tell "no position / no address"
                # from "present but hidden". Preserve empties so the diagnostic
                # stays truthful; ``field_sources`` then remains the honest signal.
                scrubbed[sk] = "**REDACTED**" if not _is_empty_value(v) else v
            elif kl == "email" and isinstance(v, str):
                # Partial mask preserves debug context.
                scrubbed[sk] = _mask_email(v)
            elif kl in _GPS_KEYS:
                # Privacy-by-default: full removal. Opt-in 1-decimal
                # rounding when user already opted into reverse-geocoding
                # (signals comfort with GPS processing).
                # #923 — an empty coordinate stays visibly empty, never a fake
                # redaction (see the _REDACT_KEYS note above).
                if _is_empty_value(v):
                    scrubbed[sk] = v
                elif gps_round and isinstance(v, (int, float)):
                    scrubbed[sk] = round(float(v), 1)
                else:
                    scrubbed[sk] = "**REDACTED**"
            elif k in (
                CONF_DATA_ACT_IDENTIFIERS,
                CONF_DATA_ACT_KICKOFF_TS,
                "skoda_official_keys",
            ):
                # #923/#1222 — mask the {VIN: portal-identifier} values, which
                # the string branch below would otherwise pass through.
                # #1286 — same shape for the Škoda official per-VIN key map
                # ({VIN: {key, id, validUntil}}): mask each record (the ``key`` is a
                # live credential) while keeping the masked-VIN count for triage.
                scrubbed[sk] = _redact_identifier_map(v)
            elif k == "charging_profiles":
                # #923 follow-up — the per-profile label; the coordinates in the
                # same objects are caught by the _GPS_KEYS branch above.
                scrubbed[sk] = _redact_charging_profiles(v, gps_round=gps_round)
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
        # #1310 (indigomejor) — a VIN can hide inside a string VALUE: the Škoda
        # widget render URL is ``.../widget-renders/<VIN>.png``. This branch
        # masked only email + GPS, so the full VIN leaked out of a URL that no
        # key-based branch above listed. Mask the VIN here too (VIN only — UUIDs
        # stay as structural grounding data, see _mask_key).
        # Re-checked for #1832, because the note that stood here overstated what
        # was masked: it said the raw camelCase ``renderUrl`` was masked, and
        # only the VIN INSIDE that value ever was — by this same regex in
        # ``_scrub_raw``. The key was in neither set, so the URL itself went out
        # whole in both sections. Both spellings are key-redacted as of #1832,
        # so for those two this branch is no longer what does the work; it stays
        # as the fallback for a URL under a key neither set lists, which is what
        # tests/test_1310_indigomejor_fixes.py measures.
        masked = _VIN_RE.sub(lambda m: mask_vin(m.group(0)), masked)
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
    # #1828 — the bare "nickname" below does not cover the key the wire actually
    # sends. vw.de, the authproxy relations read and SEAT/CUPRA send
    # ``vehicleNickname``; VW North America sends ``vehicleNickName``. Both
    # lowercase to this, so one entry covers them, and neither matched before:
    # our own snake_case ``vehicle_nickname`` is in _REDACT_KEYS and the bare
    # ``nickname`` is here, but the compound wire spelling was in neither set and
    # no value regex catches a free-text name. The raw-payload section is not
    # opt-in, so an owner-chosen nickname went out in cleartext in every vw.de
    # diagnostics download — and it reached a public issue that way the same day
    # this was found, sitting two lines below a correctly redacted licensePlate.
    "vehiclenickname",
    # #1832 — one more reader, with a spelling of its own: the CARIAD garage
    # list sends ``vehicleNick``, with no "name" on the end
    # (cariad/api/vw_eu.py:557, inside ``_pick_model`` at :553, inside
    # ``get_vehicles`` at :440). It lowercases to ``vehiclenick``, which the
    # compound entry above does not reach because the raw match is exact
    # lowercased membership (see ``_scrub_raw`` below), and no value regex
    # catches a free-text name.
    # Calibrated: this one is LATENT for the export today, NOT a second live
    # leak. The raw section walks ``client.last_raw_responses``, and on this
    # client that dict is rebuilt per poll from the status endpoints
    # (cariad/api/vw_eu.py:1047-1053) or copied from the website proxy (:851) —
    # the garage body ``get_vehicles`` parses is never recorded in it.
    # Registered anyway, because a key set is the wrong place to keep the
    # assumption that nobody will ever record that body.
    "vehiclenick",
    # #1828 — @Fishermanjb's own two privacy items, both the wire shapes of
    # things we already mask under our own names.
    #
    # The render image URLs: `image_urls` is in _REDACT_KEYS above with the
    # recorded reason that they "encode the exact model/colour/config". The wire
    # sends the same thing in two other shapes, and both walked past — a bare
    # `imageUrls` array, and an `images` array of objects each carrying a `url`.
    # Taken by their CONTAINER keys rather than by adding a bare `url`, which
    # would gut the payload shapes the raw export exists for. Safe as keys:
    # `images` is read in exactly one place in the integration, so neither can
    # swallow an unrelated harmless container.
    "imageurls", "images",
    # The dealer id. Not his data, but his reasoning is right and it is the same
    # class as parking_city above: "often in the area of the user".
    "dealerid",
    # #1832 — the wire spellings of render/map URL fields we already mask under
    # our own names. Unlike ``vehiclenick`` above, these three ARE live: the
    # Skoda widget body is a recorded raw channel (cariad/api/skoda.py:1480,
    # channel name "widget") and carries ``vehicle.renderUrl`` plus
    # ``parkingPosition.maps.lightMapUrl`` / ``darkMapUrl``; the expected-key
    # table spells all three out (cariad/_unexpected_keys.py:353 and :365-366)
    # and SEAT/CUPRA read the two map keys at
    # cariad/api/seat_cupra.py:1849-1850. Our ``render_url`` and
    # ``parking_map_url_dark`` / ``_light`` were masked while these were in
    # neither set — our name masked, the wire's not, the same shape of mistake
    # as the nickname above. All three are scalar URL strings, so taking them by
    # key costs no payload shape; their container ``maps`` is deliberately NOT
    # listed, so the block keeps its own key and its other contents are judged
    # on their own merits rather than vanishing with it. Not "only the two URLs
    # go": this set is matched at every depth, so any listed sibling inside
    # ``maps`` goes too — test_a_redacted_key_beside_the_url_is_still_redacted
    # asserts exactly that for ``licencePlate`` and ``vin``, one screen below.
    "renderurl", "lightmapurl", "darkmapurl",
    # #1832 — and the two render CONTAINERS on the same recorded Skoda
    # ``vehicle-status`` channel, found by sweeping the expected-key table
    # rather than by guessing. ``renders`` holds the lightMode / darkMode render
    # blocks that a community Scout report observed on that channel
    # (cariad/_unexpected_keys.py:114-115, from #107), so it is live the same
    # way the three above are. ``compositeRenders`` is the wire shape of
    # ``composite_render_urls`` and is registered on that same channel
    # (cariad/_unexpected_keys.py:116); unlike ``renders`` its entry records no
    # observation, so whether a vehicle-status body carries it is not
    # established here — it is listed because leaving the wire spelling open
    # while masking our own name is the mistake this issue is about.
    # Both taken by the container key, like ``images``, because the per-layer
    # URLs sit under a bare ``url`` and this set deliberately does not carry
    # that. At all three places this integration touches ``renders`` the key
    # names a render-image container: read at cariad/api/seat_cupra.py:563 and
    # coordinator.py:7103, and written at cariad/api/skoda.py:2501 — a write,
    # not a read, which the earlier wording had it as.
    #
    # That is evidence about what the name means in the bodies we parse, and it
    # is NOT a guarantee that nothing harmless is ever caught. This set matches
    # case-insensitively at every depth of brand bodies we do not parse, so a
    # key spelled ``renders`` somewhere we never look is masked too, and no
    # enumeration of our own call sites could show otherwise. The cost of that
    # is a container replaced by a note about its kind; the cost of leaving it
    # open is an image URL in a file people attach to public issues. The trade
    # is taken deliberately, not argued away. ``compositerenders`` is listed on
    # the same reasoning and its own read site (coordinator.py:7105), which the
    # earlier wording extended the ``renders`` evidence to without saying so.
    "renders", "compositerenders",
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
            # #923 follow-up — the same dotted-name gap as in _scrub, and it
            # had to be fixed in BOTH: after _scrub was corrected, this path
            # still returned parking_position.latitude, settings.access_token,
            # auth.tokens.refresh_token and vehicle.user_id in the clear.
            # Checking only the one function that happened to be measured
            # first would have left the raw sections leaking while the tests
            # for the other half went green — the schranke-nur-in-einem-skript
            # shape. ``kl`` is already taken for the lowercased whole key here,
            # hence the separate names.
            _leaf = k.rsplit(".", 1)[-1] if isinstance(k, str) and "." in k else k
            _leafl = _leaf.lower() if isinstance(_leaf, str) else ""
            # _GPS_KEYS is consulted here too. It was not, and the sweep that
            # runs the dotted guard over BOTH scrubbers caught it immediately:
            # location_lat / location_lon live only in _GPS_KEYS, which this
            # function never looked at, so they kept leaking through the raw
            # sections after _scrub was fixed. There is no gps_round here by
            # design — a raw payload is removed, never rounded.
            if (
                k in _REDACT_KEYS
                or _leaf in _REDACT_KEYS
                or k in _GPS_KEYS
                or _leaf in _GPS_KEYS
                or kl in _RAW_REDACT_KEYS
                or _leafl in _RAW_REDACT_KEYS
            ):
                out[sk] = "**REDACTED**"
            elif (k in _HASH_KEYS or _leaf in _HASH_KEYS) and isinstance(v, str):
                out[sk] = f"sha256:{_stable_hash(v)}" if v else "**REDACTED**"
            elif k in (CONF_DATA_ACT_IDENTIFIERS, CONF_DATA_ACT_KICKOFF_TS):
                out[sk] = _redact_identifier_map(v)
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


def _portal_no_data_reason(client: Any) -> str | None:
    """The EU-Data-Act portal's last "why no data" reason, or None.

    #1227 — the portal records ``last_no_data_reason`` (``no_request`` /
    ``empty`` / ``no_content``) each poll and it drives the ``data_act_no_data``
    Repair, but it was never in the diagnostics download, so a "no data" report
    cost a round-trip to read the HA log to learn which of the three it was.
    Surfacing it here makes such a report self-diagnosing. Bare enum label — no
    PII. Resolves the portal the same way the coordinator does (primary, then
    supplementary); ``getattr`` guards keep older/partial clients export-safe.
    """
    if client is None:
        return None
    portal = (
        getattr(client, "_eu_portal", None)
        or getattr(client, "_supplementary_eu_portal", None)
    )
    reason = getattr(portal, "last_no_data_reason", None) if portal is not None else None
    return reason or None


def _portal_throttle(client: Any) -> dict[str, Any] | None:
    """Whether this portal has ever throttled US, and whether it said for how long.

    #1969 — the portal's rate limits are known only from someone else's
    measurement of their own traffic: per-endpoint ceilings, a refill of about
    one request every two seconds, and a short explicit ``Retry-After``. We now
    honour such a cooldown, but whether this portal ever sends one to THIS
    integration had never been observed, and a rate limit taken on faith is how
    a poll loop gets paced against a number that does not apply.

    Three values make one report settle it:

    * ``count`` 0 — it has never happened to us, and any pacing work would be
      for a problem we do not have;
    * ``count`` above 0 with ``retry_after_s`` null — we are throttled and told
      nothing, so there is nothing to honour and a cap has to be guessed;
    * ``count`` above 0 with a number — the mechanism applies to us, and the
      number says whether the 30 s cap is the right one.

    Counts and one integer; no PII. Resolves the portal exactly like
    ``_portal_no_data_reason``, with the same ``getattr`` guards so an older or
    partial client stays export-safe.
    """
    if client is None:
        return None
    portal = (
        getattr(client, "_eu_portal", None)
        or getattr(client, "_supplementary_eu_portal", None)
    )
    if portal is None:
        return None
    count = getattr(portal, "throttle_count", None)
    if count is None:
        return None  # a client from before this existed
    return {
        "count": int(count),
        "retry_after_s": getattr(portal, "last_retry_after_s", None),
        "honoured": getattr(portal, "last_throttle_honoured", None),
    }


def _portal_field_delivery(client: Any) -> dict[str, Any] | None:
    """The EU-Data-Act portal's last value/value-less field split, or None.

    #465 (BooM80) — VW's export can ship a field's NAME + capture timestamp but
    omit the ``value`` (BooM80's official export: 10 names, only 3 valued), so a
    thin feed looks "complete". The connector records the last parse's split;
    surfacing it here makes a "most sensors are empty" report self-diagnosing
    (VW delivered nothing vs we dropped it) without a debug-log round-trip. Bare
    field names + counts — no PII (envelope-noise + credential names already
    excluded by the walker). Resolves the portal exactly like
    ``_portal_no_data_reason``; ``getattr`` guards keep older clients export-safe.
    """
    if client is None:
        return None
    portal = (
        getattr(client, "_eu_portal", None)
        or getattr(client, "_supplementary_eu_portal", None)
    )
    if portal is None:
        return None
    valueless = getattr(portal, "last_valueless_fields", None)
    return {
        "fields_with_values": getattr(portal, "last_valued_count", None),
        "fields_delivered_without_values": getattr(
            portal, "last_valueless_count", None
        ),
        "valueless_field_names": list(valueless) if valueless else [],
    }


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
    # b12 (#1340 @cyrano330) — on setup_error the entry never reached LOADED, so
    # entry.runtime_data is still None. Every coordinator.* deref below (first:
    # coordinator.vehicles.items()) would AttributeError → the diagnostics HTTP
    # view turns that into a 500, exactly when the download is most useful for
    # triaging a failed setup. Return the redacted config + a note instead.
    coordinator: VagConnectCoordinator | None = getattr(entry, "runtime_data", None)
    if coordinator is None:
        return {
            "note": (
                "Setup did not complete for this config entry: the coordinator "
                "(entry.runtime_data) is unavailable, so only the redacted config "
                "and options are included. See Settings > Devices & Services for "
                "the exact setup error / reauth prompt."
            ),
            "entry_state": str(getattr(entry, "state", "unknown")),
            "config": _scrub(dict(entry.data), gps_round=False),
            "options": _scrub(dict(entry.options), gps_round=False),
        }

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
            # class only — str(err) can carry a VIN/internal value; matches the
            # sibling raw_responses/command error handlers below.
            capabilities = {"error": type(err).__name__}

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
    # #912 — opt-in command-result captures (e.g. the BFF pendingrequests body for
    # a PPE climate command). Same redaction path; survives the per-poll wipe of
    # last_raw_responses because it lives in its own dict.
    cc = getattr(client, "command_captures", None) if client is not None else None
    if isinstance(cc, dict):
        for k, payload in cc.items():
            try:
                raw_responses[f"command:{k}"] = _scrub_raw(payload)
            except Exception as err:  # noqa: BLE001
                raw_responses[f"command:{k}"] = {"error": f"{type(err).__name__}"}

    # v4.4.0b3 — opt-in SEAT/CUPRA en_GB locale A/B capture (default vs en_GB
    # localized strings from mycar). Values are already VIN/email-masked at
    # capture; route through the same scrub for defense-in-depth.
    olc = getattr(client, "ola_locale_captures", None) if client is not None else None
    if isinstance(olc, dict):
        for vin_key, payload in olc.items():
            try:
                raw_responses[f"ola_locale:{str(vin_key)[-6:]}"] = _scrub_raw(payload)
            except Exception as err:  # noqa: BLE001
                raw_responses[f"ola_locale:{str(vin_key)[-6:]}"] = {"error": f"{type(err).__name__}"}

    # #923/#1157 — surface the experimental vw.de probe outcomes so the test
    # cohort can see WHY a probe yielded nothing (a 403/404/412 refusal vs an
    # empty 200 vs a never-fired probe). Bare status labels only — no PII.
    # #584 — the fetched-role leapfrog probe runs on WHICHEVER VWEUClient hit the
    # operationList; on the read-only-primary shape that is the ``_mbb_command``
    # sub-connector, not the parent (same reason mbb_no_legacy is unioned below).
    # Union the parent with both sub-connectors so the cohort's probe outcomes
    # reach the export regardless of which instance recorded them.
    probe_outcomes: dict[str, str] = {}
    for _obj in (
        client,
        getattr(client, "_mbb_command", None) if client is not None else None,
        getattr(client, "_mbb_fallback", None) if client is not None else None,
        # v4.7.11 (#1313) — the supplementary vw.de connector keeps its own probe
        # outcomes; _read_authproxy copies them up only after a read ran, so union
        # the connector directly too (a download before the first poll showed {}).
        getattr(client, "_supplementary_authproxy", None) if client is not None else None,
        getattr(client, "_website_proxy", None) if client is not None else None,
    ):
        _po = getattr(_obj, "probe_outcomes", None) if _obj is not None else None
        if isinstance(_po, dict):
            probe_outcomes.update({str(k): str(v) for k, v in _po.items()})

    # #584 — surface the durable "no legacy MBB enrolment" verdict. These VINs
    # got the definitive ``gw.error.authentication`` reject on the MBB
    # operationList, i.e. the car/account is read-only (EU-DA / vw.de) and MBB
    # commands are unavailable — so a #584-class report is triageable straight
    # from the diagnostics instead of asking the reporter for a debug log.
    mbb_no_legacy: list[str] = []
    # #1150 — the verdict is recorded on WHICHEVER VWEUClient ran the operationList.
    # On the #584 read-only-primary shape (VW-EU portal/vw.de primary + an armed MBB
    # command channel) it lands on the ``_mbb_command`` sub-connector, not the
    # parent — so reading only the parent exported an empty list even several polls
    # after the verdict was set. Union the parent with both sub-connectors so the
    # export reflects the real state regardless of which instance recorded it.
    _nl_union: set[str] = set()
    # #1766 — VINs whose operationList came from the EU-DP host (read-only).
    _eudp_union: set[str] = set()
    for _obj in (
        client,
        getattr(client, "_mbb_command", None) if client is not None else None,
        getattr(client, "_mbb_fallback", None) if client is not None else None,
        # v4.7.11 (#1313) — the supplementary vw.de connector keeps its own probe
        # outcomes; _read_authproxy copies them up only after a read ran, so union
        # the connector directly too (a download before the first poll showed {}).
        getattr(client, "_supplementary_authproxy", None) if client is not None else None,
        getattr(client, "_website_proxy", None) if client is not None else None,
    ):
        _s = getattr(_obj, "mbb_no_legacy_vins", None) if _obj is not None else None
        if _s:
            _nl_union.update(_s)
        _e = getattr(_obj, "mbb_eudp_oplist_vins", None) if _obj is not None else None
        if _e:
            _eudp_union.update(_e)
    mbb_eudp_oplist: list[str] = []
    if _eudp_union:
        try:
            mbb_eudp_oplist = sorted(mask_vin(v) for v in _eudp_union)
        except Exception:  # noqa: BLE001
            mbb_eudp_oplist = []
    if _nl_union:
        try:
            mbb_no_legacy = sorted(mask_vin(v) for v in _nl_union)
        except Exception:  # noqa: BLE001
            mbb_no_legacy = []

    # Pre-flight durable-MBB eligibility from the guest-readable vw.de relations
    # read (carnetIndicator / platform / role → eligible / not_provisioned /
    # not_mbb / unknown). The UP-FRONT companion to mbb_no_legacy (which is the
    # post-hoc operationList verdict): it lets a #584-class triage tell whether
    # arming the durable MBB channel is even worth it for a car before any MBB
    # login. Observability only — nothing in the poll/command path consumes it.
    mbb_elig: dict[str, str] = {}
    _me = getattr(client, "mbb_eligibility", None) if client is not None else None
    if isinstance(_me, dict):
        try:
            mbb_elig = {mask_vin(str(k)): str(v) for k, v in _me.items()}
        except Exception:  # noqa: BLE001
            mbb_elig = {}

    return {
        "config": config_diag,
        "options": options_diag,
        "vehicles": vehicles_diag,
        "vehicle_count": len(coordinator.vehicles),
        "last_update_success": coordinator.last_update_success,
        "portal_no_data_reason": _portal_no_data_reason(client),
        "portal_field_delivery": _portal_field_delivery(client),
        # #1969 — see _portal_throttle: this is the field that turns "the
        # portal's rate limits were measured by someone else, on their own
        # traffic" into something one report of ours can confirm or refute.
        "portal_throttle": _portal_throttle(client),
        "cloud_push_active": coordinator.cloud_push_active,
        "push_states": coordinator.push_states,
        "push_last_errors": coordinator.push_last_errors,
        "polling_active": coordinator.is_active,
        "unexpected_findings": unexpected,
        "raw_responses": raw_responses,
        "probe_outcomes": probe_outcomes,
        "data_act_kickoff_errors": {
            "***" + str(_k)[-6:]: str(_v)
            for _k, _v in (getattr(coordinator, "_data_act_kickoff_error", {}) or {}).items()
        },
        "error_buffer": error_records,
        "parser_stats": parser_stats_diag,
        "capabilities": capabilities,
        "mbb_no_legacy": mbb_no_legacy,
        "mbb_eudp_oplist": mbb_eudp_oplist,
        "mbb_eligibility": mbb_elig,
    }


async def async_get_device_diagnostics(
    hass: HomeAssistant,
    entry: ConfigEntry,
    device: DeviceEntry,
) -> dict[str, Any]:
    """Per-device (single-VIN) slice of the config-entry diagnostics.

    Lets a reporter share ONE car instead of the whole account. Built by slicing
    the already-redacted config-entry payload — identical redaction, no
    duplication. Only the genuinely VIN-keyed sections are sliced (``vehicles`` /
    ``unexpected_findings`` / ``mbb_no_legacy``, all keyed by ``mask_vin(vin)``);
    the channel/probe/command-keyed sections carry no VIN dimension and are
    account-scoped, so they are dropped from a single-car file rather than leaking
    another car's data.
    """
    full = await async_get_config_entry_diagnostics(hass, entry)

    vin = next((str(v) for d, v in device.identifiers if d == DOMAIN), None)
    # The options/settings device (number.py) shares the DOMAIN but is not a car.
    if not vin or vin.endswith("_settings"):
        return {
            "device_note": "non-vehicle device — no per-VIN slice",
            "config": full.get("config"),
            "options": full.get("options"),
        }

    masked = mask_vin(vin)  # the per-VIN diag sections are keyed by the masked VIN
    veh = full.get("vehicles", {})
    unexpected = full.get("unexpected_findings", {})
    elig = full.get("mbb_eligibility", {}) or {}
    return {
        "device_vin_masked": masked,
        "config": full.get("config"),
        "options": full.get("options"),
        "vehicles": {masked: veh[masked]} if masked in veh else {},
        "vehicle_count": 1 if masked in veh else 0,
        "unexpected_findings": (
            {masked: unexpected[masked]} if masked in unexpected else {}
        ),
        "mbb_no_legacy": (
            [masked] if masked in full.get("mbb_no_legacy", []) else []
        ),
        "mbb_eudp_oplist": (
            [masked] if masked in full.get("mbb_eudp_oplist", []) else []
        ),
        # v4.7.9 (#584/#923) — the cohort probe outcomes carry no VIN dimension
        # (status codes keyed by host/brand/country) and are the one datapoint a
        # no-legacy reporter's file is asked for: keep them. mbb_eligibility is
        # VIN-keyed, so it is sliced like the other per-VIN sections.
        "probe_outcomes": full.get("probe_outcomes", {}) or {},
        "mbb_eligibility": {masked: elig[masked]} if masked in elig else {},
        "last_update_success": full.get("last_update_success"),
        "cloud_push_active": full.get("cloud_push_active"),
        "push_states": full.get("push_states"),
        "push_last_errors": full.get("push_last_errors"),
        "polling_active": full.get("polling_active"),
    }
