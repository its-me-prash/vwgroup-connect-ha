# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Legacy MBB endpoint paths for older Audi/VW models (pre-PPE/MEB).

v1.21.0 — implements per-VIN backend-detection + MBB-fallback for
the action commands that older Audi A4 B9 / Q5 2021 / VW Golf 7
models reject on Cariad-BFF (`emea.bff.cariad.digital`) with the
fake-404 + ``"Upstream service responded"`` body marker.

### Two backends, one client

Pre-v1.21.0 the integration assumed every VIN speaks Cariad-BFF
(`/vehicle/v1/...` and `/vehicle/v2/...` paths). That works for ID
series, MEB, PPE — the modern e-cars Cariad was built for. But the
older MIB3 cars (A4 B9 2018+, Q5 2021, A6 C8, Golf 7 2015+, Passat
B8 2015+, etc.) still answer on the **legacy MBB stack**:

- Discovery: `https://mal-1a.prd.ece.vwg-connect.com/api/cs/vds/v1/vehicles/{vin}/homeRegion`
- Per-VIN read base: usually `https://msg.volkswagen.de` or
  `https://fal-3a.prd.eu.dp.vwg-connect.com` (returned by discovery)
- Per-VIN setter base: always `https://mal-1a.prd.ece.vwg-connect.com`
- Path pattern: `{readBase}/fs-car/bs/{service}/v1/{Brand}/{country}/vehicles/{vin}/...`

Reference: ``upstream/upstream`` `audi_services.py` (lines
130–910) and `_fill_home_region` (line 372). MIT-licensed; endpoint
catalog adopted with attribution in `NOTICE.md`.

### Detection strategy

When a Cariad-BFF write command returns the wrapper-404 body marker
(``"Upstream service responded"`` or ``"retry":true``), we now know
the VIN is MBB-backed. Cache the flag per-VIN like the existing
v1/v2 detection. Subsequent writes for the same VIN go directly to
MBB endpoints — skip the dead Cariad-BFF call.

### Phase 1 (v1.21.0, this release)

- HomeRegion resolver wire-in (was scaffolding since v1.17.6)
- `MBBBackendCache` class — per-VIN backend flag
- `command_wake` MBB fallback (most-requested command)
- `_post_mbb_command` helper for future commands

### Phase 2 (v2.15.0 — this release)

- `command_lock` / `command_unlock` MBB with the S-PIN secure-token flow
  (3-leg rolesrights handshake + RLU action — builders/hash/parsers below,
  HTTP orchestration in `api/vw_eu.py` under the `mbb` auth strategy).
  NOTE: the RLU action + rolesrights paths use the SETTER host under the
  `/api` prefix and carry NO brand/country segment (DEX-confirmed) — unlike
  the `/fs-car/...{Brand}/{country}...` VSR read paths above.

### Phase 3+ (future releases)

- `command_start_climate` / `_stop` MBB
- `command_start_charging` / `_stop` MBB
- `command_set_target_soc` MBB

### Privacy

- VINs masked to last 6 chars in logs
- SPIN never logged (existing redaction in `_unexpected_keys.py`)
- HomeRegion lookup uses user's existing IDK token
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

_LOGGER = logging.getLogger(__name__)

# Setter base (lock/unlock + roles/rights queries) — same for all
# MBB-backed VINs regardless of region.
MBB_SETTER_BASE = "https://mal-1a.prd.ece.vwg-connect.com"

# Default reader base — used as fallback when discovery fails.
# upstream + volkswagencarnet historical default.
MBB_DEFAULT_READ_BASE = "https://msg.volkswagen.de"

# Brand prefix in URL path. Maps our brand-id to the segment that
# the MBB backend expects in `{readBase}/fs-car/bs/{service}/v1/{BRAND}/...`.
# Audi → "Audi", Volkswagen EU → "VW". Other brands route via different
# backends (Skoda mysmob, OLA for SEAT/CUPRA, Auth0/PPA for Porsche).
_BRAND_TO_MBB_SEGMENT: dict[str, str] = {
    "audi": "Audi",
    "volkswagen": "VW",
    "vw_eu": "VW",
}


def mbb_brand_segment(brand: str) -> str:
    """Return the URL-path segment for the given brand. Defaults to
    'VW' if brand is unknown — most cross-brand legacy cars were
    sold under VW group umbrella so this is a safe fallback."""
    return _BRAND_TO_MBB_SEGMENT.get(brand.lower(), "VW")


# Cache TTL for per-VIN backend flag. Once we detect MBB for a VIN,
# stick with it for at least 7 days. A vehicle migrating from MBB
# to Cariad-BFF (e.g. via firmware update) is a rare event; users
# can manually reload the integration if they need a fresh detection.
_BACKEND_CACHE_TTL = timedelta(days=7)


class MBBBackendCache:
    """Per-VIN cache of which backend the vehicle answers on.

    Three states:
    - ``"cariad"`` — VIN answered Cariad-BFF cleanly; future commands
      go to ``emea.bff.cariad.digital``
    - ``"mbb"`` — VIN returned Cariad-wrapper-404; future commands
      go to MBB legacy endpoints via HomeRegion resolution
    - ``None`` (not in cache) — first attempt, try Cariad first then
      detect on failure

    Persisted in-memory only (analog to ``_v2_command_paths``).
    Coordinator restart re-learns one extra request per VIN.
    """

    def __init__(self) -> None:
        # vin -> (backend_name, expires_at)
        self._entries: dict[str, tuple[str, datetime]] = {}

    def get(self, vin: str) -> str | None:
        """Return cached backend ('cariad' / 'mbb') or None."""
        entry = self._entries.get(vin)
        if not entry:
            return None
        backend, expires_at = entry
        if datetime.now(tz=timezone.utc) >= expires_at:
            self._entries.pop(vin, None)
            return None
        return backend

    def set(self, vin: str, backend: str) -> None:
        """Record backend for ``vin`` with TTL."""
        if backend not in ("cariad", "mbb"):
            raise ValueError(
                f"MBBBackendCache: backend must be 'cariad' or 'mbb', "
                f"got {backend!r}"
            )
        expires_at = datetime.now(tz=timezone.utc) + _BACKEND_CACHE_TTL
        self._entries[vin] = (backend, expires_at)

    def clear(self) -> None:
        """Wipe cache (e.g. after Reauth or option change)."""
        self._entries.clear()


def is_cariad_wrapper_404(body: str | None) -> bool:
    """Detect Cariad-BFF fake-404 wrapping an upstream-backend issue.

    User-report 2026-05-07 verbatim body sample:

        {"error":{"message":"Not Found",
          "info":"Upstream service responded with an unexpected status",
          "code":4112,"group":2,"retry":true}}

    Either the verbose ``"Upstream service responded"`` string OR
    just the ``"retry":true`` flag (truncated bodies) is enough to
    classify as wrapper-404. Cariad's own 4xx/5xx responses for
    real backend issues always include one of these markers.

    A genuine integration-bug 404 (we have wrong URL) won't carry
    these markers — Cariad just says ``{"error":{"message":"Not Found"}}``
    in that case. So: presence of marker → MBB-backed VIN candidate;
    absence → keep treating as Cariad.
    """
    if not body:
        return False
    # v1.24.2 (2026-05-08 audit, hypothesis property test): defensive
    # coerce bytes → str. Production always passes str (from
    # ``await resp.text()``) but bytes is the natural shape if a future
    # caller hands raw response bodies in. Best-effort decode; on
    # failure, classify as not-a-wrapper.
    if isinstance(body, (bytes, bytearray)):
        try:
            body = bytes(body).decode("utf-8", errors="replace")
        except (UnicodeError, ValueError):
            return False
    if not isinstance(body, str):
        return False
    body_lower = body.lower()
    return (
        "upstream service responded" in body_lower
        or '"retry":true' in body_lower
        or "'retry': true" in body_lower
    )


def build_mbb_wake_url(read_base: str, brand: str, country: str, vin: str) -> str:
    """Build the MBB VSR (Vehicle Status Refresh / Wake) URL.

    Pattern: ``{readBase}/fs-car/bs/vsr/v1/{Brand}/{country}/vehicles/{vin}/requests``
    Verified against upstream audi_services.py (lines 478-510).

    A POST to this URL queues a wake/refresh request; backend returns
    a request-id that can be polled via the same URL + ``/requests/{id}/jobstatus``.
    For our use case (just trigger wake), we ignore the request-id.
    """
    seg = mbb_brand_segment(brand)
    return f"{read_base}/fs-car/bs/vsr/v1/{seg}/{country}/vehicles/{vin}/requests"


# ─────────────────────────────────────────────────────────────────────────────
# v1.25.0 PR-G: MBB VSR Phase 2 read-side — Golf 7 GTE Tank-Level
# ─────────────────────────────────────────────────────────────────────────────

# MBB VSR (Vehicle Status Report) field IDs from upstream
# audi_models.py legacy IDS table. These IDs are guaranteed-stable
# across all Car-Net-era VAG vehicles (2010–2020 MIB1/MIB2/MIB3 OCUs):
#
#   0x030103000A — TANK_LEVEL_IN_PERCENTAGE (% only, no liters)
#   0x0301030005 — TOTAL_RANGE (km)
#   0x02040C0001 — ADBLUE_RANGE (km)
#
# Verified against:
# - upstream/upstream audi_models.py
# - upstream/weconnect-python (uses same field-ID table)
#
# Used by Golf 7 GTE PHEV + similar pre-PPE/MEB vehicles where the
# Cariad-BFF gateway returns ``fuelStatus.rangeStatus = {error: ...}``
# with no ``currentFuelLevel_pct`` — but the underlying MBB OCU still
# publishes the field via the legacy VSR endpoint.
MBB_VSR_FIELD_TANK_PCT = "0x030103000A"
MBB_VSR_FIELD_TOTAL_RANGE_KM = "0x0301030005"
MBB_VSR_FIELD_ADBLUE_RANGE_KM = "0x02040C0001"


def build_mbb_vsr_status_url(
    read_base: str, brand: str, country: str, vin: str,
) -> str:
    """Build the MBB VSR status-read URL (Phase 2 read-side).

    Pattern: ``{readBase}/fs-car/bs/vsr/v1/{Brand}/{country}/vehicles/{vin}/status``
    Verified against upstream + WeConnect-python references.

    Returns JSON shape::

        {"StoredVehicleDataResponse": {
            "vehicleData": {"data": [
              {"id": "0x0301", "field": [
                {"id": "0x030103000A", "tsCarCaptured": "...",
                 "value": "60", "unit": "%"},
                {"id": "0x0301030005", "value": "450", "unit": "km"},
                ...
              ]}
            ]}
        }}

    Use ``parse_mbb_vsr_field()`` to extract a value by field ID.
    """
    seg = mbb_brand_segment(brand)
    return f"{read_base}/fs-car/bs/vsr/v1/{seg}/{country}/vehicles/{vin}/status"


def build_mbb_vehicles_url(read_base: str, brand: str, country: str) -> str:
    """Build the MBB garage-enumeration (paired vehicles) URL.

    Pattern: ``{readBase}/fs-car/usermanagement/users/v1/{Brand}/{country}/vehicles``
    — the classic Car-Net endpoint that lists the VINs paired to the
    account (upstream audi_services ``_get_vehicles`` / volkswagencarnet).
    Returns ``{"userVehicles": {"vehicle": ["VIN1", ...]}}``.

    NOTE: needs live confirmation against a real VW EU MBB account; the
    caller treats an empty/failed response as "no VINs" and the config
    flow surfaces a clear message rather than crashing.
    """
    seg = mbb_brand_segment(brand)
    return f"{read_base}/fs-car/usermanagement/users/v1/{seg}/{country}/vehicles"


def parse_mbb_vehicle_vins(response: dict | None) -> list[str]:
    """Extract the list of VINs from an MBB usermanagement response.

    Defensive against the two observed envelopes:
      - ``{"userVehicles": {"vehicle": ["VIN", ...]}}`` (list of strings)
      - ``{"userVehicles": {"vehicle": [{"vin": "VIN"}, ...]}}`` (objects)
    Returns ``[]`` for any unexpected shape.
    """
    if not isinstance(response, dict):
        return []
    user_vehicles = response.get("userVehicles")
    if not isinstance(user_vehicles, dict):
        return []
    raw = user_vehicles.get("vehicle")
    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, list):
        return []
    vins: list[str] = []
    for item in raw:
        if isinstance(item, str) and item:
            vins.append(item)
        elif isinstance(item, dict):
            vin = item.get("vin") or item.get("content")
            if isinstance(vin, str) and vin:
                vins.append(vin)
    return vins


def parse_mbb_vsr_field(response: dict | None, field_id: str) -> str | None:
    """Walk a MBB VSR response and return the value for ``field_id``.

    Defensive against:
    - None response (request failed)
    - Missing ``StoredVehicleDataResponse`` (different envelope)
    - Missing ``vehicleData`` / ``data`` (older firmware)
    - Non-dict / non-list elements at any level
    - Field absent on this vehicle (returns None)

    Returns the raw value as string (caller converts via safe_int /
    safe_float). The MBB VSR shape always returns string values
    (``"60"``, ``"450"``, etc.) regardless of the underlying type.
    """
    if not isinstance(response, dict):
        return None
    svd = response.get("StoredVehicleDataResponse")
    if not isinstance(svd, dict):
        return None
    vehicle_data = svd.get("vehicleData")
    if not isinstance(vehicle_data, dict):
        return None
    data_groups = vehicle_data.get("data")
    if not isinstance(data_groups, list):
        return None
    for group in data_groups:
        if not isinstance(group, dict):
            continue
        fields = group.get("field")
        if not isinstance(fields, list):
            continue
        for f in fields:
            if not isinstance(f, dict):
                continue
            if f.get("id") == field_id:
                val = f.get("value")
                if val is None:
                    return None
                return str(val)
    return None


def mbb_vsr_field_ids(response: dict | None) -> list[str]:
    """Return every field ``id`` present in a MBB VSR response (diagnostics).

    Used to discover which field IDs a given car actually publishes, so the
    parser can be extended to map them. Returns [] for an unexpected shape.
    """
    ids: list[str] = []
    if not isinstance(response, dict):
        return ids
    svd = response.get("StoredVehicleDataResponse")
    if not isinstance(svd, dict):
        return ids
    vehicle_data = svd.get("vehicleData")
    if not isinstance(vehicle_data, dict):
        return ids
    data_groups = vehicle_data.get("data")
    if not isinstance(data_groups, list):
        return ids
    for group in data_groups:
        if not isinstance(group, dict):
            continue
        fields = group.get("field")
        if not isinstance(fields, list):
            continue
        for f in fields:
            if isinstance(f, dict):
                fid = f.get("id")
                if isinstance(fid, str):
                    ids.append(fid)
    return ids


# ─────────────────────────────────────────────────────────────────────────────
# v2.15.0 — MBB S-PIN SecToken + RLU lock/unlock (Phase 2 two-way payoff)
# ─────────────────────────────────────────────────────────────────────────────
#
# The classic Car-Net remote lock/unlock ("RLU") needs an action-bound
# security token minted from the user's S-PIN. The handshake is three legs,
# all on the homeRegion SETTER host (``MBB_SETTER_BASE``) under the ``/api``
# prefix (NOT the ``/fs-car`` prefix the VSR reads use), and the RLU action
# path carries NO brand/country segment — lock/unlock is the path tail:
#
#   1. GET  {setter}/api/rolesrights/authorization/v2/vehicles/{vin}
#             /services/rlu_v1/operations/{LOCK|UNLOCK}/security-pin-auth-requested
#        → securityPinAuthInfo.securityToken (level-1) + .securityPinTransmission
#          .challenge (hex) + .remainingTries
#   2. POST {setter}/api/rolesrights/authorization/v2/security-pin-auth-completed
#        body {securityPinAuthentication:{securityPin:{challenge,
#              securityPinHash}, securityToken: <level-1>}}
#        → securityToken (level-2) = the ``x-securityToken`` for the command
#   3. POST {setter}/api/bs/rlu/v1/vehicles/{vin}/{lock|unlock}
#        Content-Type application/vnd.vwg.mbb.RemoteLockUnlock_v1_0_0+xml,
#        header x-securityToken: <level-2>, EMPTY body
#        → rluActionResponse.requestId ; poll
#          {setter}/api/bs/rlu/v1/vehicles/{vin}/requests/{requestId}/status
#
# Grounding (two independent sources + our own DEX):
#   - DEX literals (de.volkswagen.carnet.eu.eremote + cz.skodaauto.connect +
#     SEAT/CUPRA mod2connectapp): ``/bs/rlu/v1/vehicles/{vehicleVin}/lock``,
#     ``…/unlock``, ``…/requests/{requestId}/status``; ``rlu_v1/operations/
#     LOCK|UNLOCK``; ``security-pin-auth-requested``/``-completed``;
#     ``securityPinHash``/``securityPinTransmission``/``challenge``.
#   - upstream audi_connect_ha ``audi_services.py`` (_get_security_token,
#     set_vehicle_lock, _generate_security_pin_hash) and the volkswagencarnet
#     ``vw_connection.hash_spin`` — both hex-DECODE the S-PIN and SHA-512 it
#     with the hex-decoded challenge (NOT HMAC, NOT utf-8).
MBB_RLU_CONTENT_TYPE = "application/vnd.vwg.mbb.RemoteLockUnlock_v1_0_0+xml"


def compute_spin_hash(spin: str, challenge: str) -> str:
    """Return the uppercase SHA-512 hex of hex(spin) ++ hex(challenge).

    CRITICAL (the classic footgun): the S-PIN is treated as a HEX string
    and decoded with ``bytes.fromhex`` — NOT utf-8 encoded. A 4-digit PIN
    ``"1234"`` hashes the bytes ``0x12 0x34``, not the ASCII ``0x31..0x34``.
    The challenge (server-supplied) is hex-decoded the same way. It is a
    plain SHA-512, not an HMAC. Confirmed in BOTH audi_connect_ha
    ``util.to_byte_array`` and volkswagencarnet ``hash_spin``.

    Raises ``ValueError`` (via ``bytes.fromhex``) if either input is not
    valid hex — call ``validate_spin_format`` up front so a malformed PIN
    fails BEFORE the challenge request (a wrong hash burns a SPIN try
    toward the 3-strike lockout).
    """
    pin_bytes = bytes.fromhex(spin)
    challenge_bytes = bytes.fromhex(challenge)
    return hashlib.sha512(pin_bytes + challenge_bytes).hexdigest().upper()


def validate_spin_format(spin: str) -> None:
    """Raise ``ValueError`` if ``spin`` is unusable for the hash.

    VW/Audi S-PINs are 4 digits (some 6); decimal digits are valid hex and
    even-length, so a normal PIN passes. Guarding here means a typo'd /
    empty / odd-length SPIN raises locally instead of wasting one of the
    three allowed attempts against the backend.
    """
    if not spin:
        raise ValueError("S-PIN is empty — configure it in the integration options")
    if len(spin) % 2 != 0:
        raise ValueError("S-PIN must have an even number of digits for the MBB hash")
    try:
        bytes.fromhex(spin)
    except ValueError as exc:
        raise ValueError("S-PIN must be digits only (hex-decodable)") from exc


def build_mbb_spin_challenge_url(setter_base: str, vin: str, *, lock: bool) -> str:
    """GET URL for leg 1 — request the SPIN challenge for LOCK/UNLOCK."""
    op = "LOCK" if lock else "UNLOCK"
    return (
        f"{setter_base}/api/rolesrights/authorization/v2/vehicles/"
        f"{vin.upper()}/services/rlu_v1/operations/{op}/security-pin-auth-requested"
    )


def build_mbb_spin_completed_url(setter_base: str) -> str:
    """POST URL for leg 2 — submit the hashed SPIN, get the level-2 token."""
    return f"{setter_base}/api/rolesrights/authorization/v2/security-pin-auth-completed"


def build_mbb_op_auth_url(
    setter_base: str, vin: str, service_id: str, operation_id: str,
) -> str:
    """GET URL for SecToken leg-1 for ANY service/operation (generic — drives
    climate/charge/timer commands, not just rlu). Live-confirmed HTTP 200 for
    rclima_v1/P_START_CLIMA_NOSET + rbatterycharge_v1/P_START."""
    return (
        f"{setter_base}/api/rolesrights/authorization/v2/vehicles/"
        f"{vin.upper()}/services/{service_id}/operations/{operation_id}/"
        "security-pin-auth-requested"
    )


def build_mbb_rlu_action_url(setter_base: str, vin: str, *, lock: bool) -> str:
    """POST URL for leg 3 — the actual lock/unlock action (no brand/country)."""
    tail = "lock" if lock else "unlock"
    return f"{setter_base}/api/bs/rlu/v1/vehicles/{vin.upper()}/{tail}"


def build_mbb_rlu_status_url(setter_base: str, vin: str, request_id: str) -> str:
    """GET URL to poll the RLU action's request status."""
    return (
        f"{setter_base}/api/bs/rlu/v1/vehicles/{vin.upper()}/requests/"
        f"{request_id}/status"
    )


def build_mbb_completed_body(level1_token: str, challenge: str, spin_hash: str) -> dict:
    """Build the leg-2 ``security-pin-auth-completed`` JSON body.

    Shape (upstream-confirmed)::

        {"securityPinAuthentication": {
            "securityPin": {"challenge": <hex>, "securityPinHash": <UPPER hex>},
            "securityToken": <level-1 token>}}
    """
    return {
        "securityPinAuthentication": {
            "securityPin": {
                "challenge": challenge,
                "securityPinHash": spin_hash,
            },
            "securityToken": level1_token,
        }
    }


def parse_mbb_spin_challenge(response: dict | None) -> tuple[str | None, str | None, int | None]:
    """Extract ``(level1_token, challenge, remaining_tries)`` from leg 1.

    Defensive against a missing ``securityPinAuthInfo`` envelope / fields.
    ``remaining_tries`` is None when the backend doesn't report it.
    """
    if not isinstance(response, dict):
        return None, None, None
    info = response.get("securityPinAuthInfo")
    if not isinstance(info, dict):
        return None, None, None
    level1 = info.get("securityToken")
    transmission = info.get("securityPinTransmission")
    challenge = None
    remaining = None
    if isinstance(transmission, dict):
        challenge = transmission.get("challenge")
        rt = transmission.get("remainingTries")
        if isinstance(rt, int):
            remaining = rt
    return (
        level1 if isinstance(level1, str) else None,
        challenge if isinstance(challenge, str) else None,
        remaining,
    )


def parse_mbb_completed_token(response: dict | None) -> str | None:
    """Extract the level-2 ``securityToken`` from the leg-2 response."""
    if not isinstance(response, dict):
        return None
    tok = response.get("securityToken")
    return tok if isinstance(tok, str) else None


def parse_mbb_rlu_request_id(response: dict | None) -> str | None:
    """Extract ``rluActionResponse.requestId`` from the leg-3 response."""
    if not isinstance(response, dict):
        return None
    action = response.get("rluActionResponse")
    if not isinstance(action, dict):
        return None
    request_id = action.get("requestId")
    if request_id is None:
        return None
    return str(request_id)


def parse_mbb_action_request_id(response: dict | None) -> str | None:
    """Extract the request/action id from ANY MBB action response envelope
    (rluActionResponse / climaterActionResponse / chargerActionResponse /
    action.actionId). Generic so one parser serves all command families."""
    if not isinstance(response, dict):
        return None
    for key, idfield in (
        ("rluActionResponse", "requestId"),
        ("climaterActionResponse", "requestId"),
        ("chargerActionResponse", "requestId"),
        ("action", "actionId"),
        ("action", "requestId"),
    ):
        wrapper = response.get(key)
        if isinstance(wrapper, dict) and wrapper.get(idfield) is not None:
            return str(wrapper[idfield])
    # last resort: a bare requestId/actionId
    for f in ("requestId", "actionId"):
        if response.get(f) is not None:
            return str(response[f])
    return None


def parse_mbb_rlu_status(response: dict | None) -> str | None:
    """Extract the RLU request status string from the poll response.

    Returns e.g. ``"request_successful"`` / ``"request_fail"`` /
    ``"request_in_progress"`` — or None if the envelope is unexpected.
    The status lives at ``requestStatusResponse.status`` (upstream shape);
    we also accept a bare top-level ``status`` for resilience.
    """
    if not isinstance(response, dict):
        return None
    wrapper = response.get("requestStatusResponse")
    if isinstance(wrapper, dict):
        status = wrapper.get("status")
        if isinstance(status, str):
            return status
    status = response.get("status")
    return status if isinstance(status, str) else None


# ─────────────────────────────────────────────────────────────────────────────
# v2.15.0a6 — MBB operationList: the service directory (license + hosts + cmds)
# ─────────────────────────────────────────────────────────────────────────────
#
# ``GET {setter}/api/rolesrights/operationlist/v3/vehicles/{vin}`` returns the
# per-vehicle service catalogue. Live-confirmed 2026-06-21 (real account):
# HTTP 200 even when the paid services are unlicensed — it is the authoritative
# source for (a) WHETHER a service is licensed/enabled (so we surface
# "subscription expired" instead of a cryptic 403, and skip doomed reads),
# (b) the per-service host (``invocationUrl``) for commands, and (c) the granted
# operations + their ``remoteCommand`` names. The whole "no data" mystery on a
# car turned out to be an EXPIRED We Connect subscription — every paid service
# (``statusreport_v1`` = vehicle status, ``rclima_v1``, ``rbatterycharge_v1`` …)
# was ``serviceStatus: Disabled, reason: noActiveLicense``.
#
# Shape (real, redacted)::
#
#   {"operationList": {"vin": "...", "role": "PRIMARY_USER", "status": "ENABLED",
#     "serviceInfo": [
#       {"serviceId": "statusreport_v1", "licenseRequired": true,
#        "serviceStatus": {"status": "Disabled", "reason": ["noActiveLicense"]},
#        "cumulatedLicense": {"status": "EXPIRED",
#          "expirationDate": {"content": "2026-06-16T22:34:00Z"}},
#        "operation": [{"id": "G_SVDATA", "permission": "granted"}, …]},
#       {"serviceId": "rclima_v1", …,
#        "invocationUrl": {"content": "https://mal-1a…/api/bs/climatisation/v1/vehicles/{vin}/"}},
#       …]}}

# The canonical status service — its licence is the proxy for "the user's
# We Connect / connect subscription is active" (all paid services share one
# cumulatedLicence in practice).
MBB_STATUS_SERVICE_ID = "statusreport_v1"


def build_mbb_operationlist_url(setter_base: str, vin: str) -> str:
    """GET URL for the per-VIN operationList (service directory)."""
    return (
        f"{setter_base}/api/rolesrights/operationlist/v3/vehicles/{vin.upper()}"
    )


@dataclass
class MbbService:
    """One entry of the operationList ``serviceInfo``."""

    service_id: str
    status: str                       # "Enabled" / "Disabled" / "" (unknown)
    license_required: bool = False
    license_status: str | None = None  # "EXPIRED" / "ACTIVE" / None
    license_expiry: str | None = None  # ISO-8601 string
    reasons: list[str] = field(default_factory=list)
    invocation_url: str | None = None  # template, may carry {vin}/{brand}/{country}
    operations: list[dict] = field(default_factory=list)

    @property
    def enabled(self) -> bool:
        return self.status.lower() == "enabled"


@dataclass
class MbbOperationList:
    """Parsed operationList for one VIN."""

    vin: str
    role: str | None = None
    status: str | None = None
    services: dict[str, MbbService] = field(default_factory=dict)

    def service(self, service_id: str) -> MbbService | None:
        return self.services.get(service_id)

    @property
    def status_service(self) -> MbbService | None:
        return self.services.get(MBB_STATUS_SERVICE_ID)


def parse_mbb_operationlist(
    response: dict | None, vin: str = "",
) -> MbbOperationList | None:
    """Parse the operationList response into a typed structure.

    Defensive against every level being absent / the wrong type. Returns
    None only when there is no recognisable ``operationList`` envelope.
    """
    if not isinstance(response, dict):
        return None
    ol = response.get("operationList")
    if not isinstance(ol, dict):
        return None
    result = MbbOperationList(
        vin=str(ol.get("vin") or vin),
        role=ol.get("role") if isinstance(ol.get("role"), str) else None,
        status=ol.get("status") if isinstance(ol.get("status"), str) else None,
    )
    services = ol.get("serviceInfo")
    if not isinstance(services, list):
        return result
    for svc in services:
        if not isinstance(svc, dict):
            continue
        sid = svc.get("serviceId")
        if not isinstance(sid, str):
            continue
        svc_status = svc.get("serviceStatus")
        status = ""
        reasons: list[str] = []
        if isinstance(svc_status, dict):
            status = str(svc_status.get("status") or "")
            raw_reasons = svc_status.get("reason")
            if isinstance(raw_reasons, list):
                reasons = [str(r) for r in raw_reasons]
        lic = svc.get("cumulatedLicense")
        lic_status: str | None = None
        lic_expiry: str | None = None
        if isinstance(lic, dict):
            lic_status = lic.get("status") if isinstance(lic.get("status"), str) else None
            exp = lic.get("expirationDate")
            if isinstance(exp, dict) and isinstance(exp.get("content"), str):
                lic_expiry = exp["content"]
        inv = svc.get("invocationUrl")
        inv_url: str | None = None
        if isinstance(inv, dict) and isinstance(inv.get("content"), str):
            inv_url = inv["content"]
        ops = svc.get("operation")
        operations = [o for o in ops if isinstance(o, dict)] if isinstance(ops, list) else []
        result.services[sid] = MbbService(
            service_id=sid,
            status=status,
            license_required=bool(svc.get("licenseRequired")),
            license_status=lic_status,
            license_expiry=lic_expiry,
            reasons=reasons,
            invocation_url=inv_url,
            operations=operations,
        )
    return result


def mbb_subscription_active(oplist: MbbOperationList | None) -> bool | None:
    """Is the vehicle-status service licensed/usable right now?

    True  → ``statusreport_v1`` is Enabled (subscription active → reads work).
    False → it exists but is Disabled (expired / no active licence).
    None  → unknown (no operationList / no status service entry).
    """
    if oplist is None:
        return None
    svc = oplist.status_service
    if svc is None:
        return None
    return svc.enabled


def mbb_service_base(
    oplist: MbbOperationList | None, service_id: str, *, brand: str, country: str,
    vin: str,
) -> str | None:
    """Return a fully-substituted host base for a service from its
    ``invocationUrl`` template, or None when the service has no URL.

    The template carries ``{vin}`` and sometimes ``{brand}``/``{country}``;
    substitute them so the caller gets a ready base (still ending in ``/``).
    This is what makes the command paths GENERIC across countries/brands — the
    portal hands us the right host per service per market, no hardcoding.
    """
    if oplist is None:
        return None
    svc = oplist.service(service_id)
    if svc is None or not svc.invocation_url:
        return None
    seg = mbb_brand_segment(brand)
    return (
        svc.invocation_url
        .replace("{vin}", vin.upper())
        .replace("{brand}", seg)
        .replace("{country}", country)
        .rstrip("/")
    )


def mbb_operation_granted(
    oplist: MbbOperationList | None, service_id: str, operation_id: str,
) -> bool:
    """True if the operationList lists ``operation_id`` as ``granted`` on a
    currently-Enabled service — so we only attempt commands the car/account
    actually allows (avoids burning S-PIN tries / hitting licence walls)."""
    if oplist is None:
        return False
    svc = oplist.service(service_id)
    if svc is None or not svc.enabled:
        return False
    for op in svc.operations:
        if op.get("id") == operation_id:
            return str(op.get("permission", "")).lower() == "granted"
    return False


# ── v2.15.0a7 — MBB write-command action recipes (SecToken + per-service) ────
#
# Grounded against upstream audi_services.py (legacy MBB action paths +
# content-types) + our live operationList (per-service invocationUrl +
# granted operations). The durable MBB token CANNOT read data (systemId ACL),
# but the SecToken/rolesrights command path IS open (live-confirmed:
# security-pin-auth-requested = HTTP 200 for rclima/rbatterycharge/rlu). So
# these drive DURABLE two-way: climate, charging, timers — actuated via the
# 3-leg S-PIN SecToken flow then a POST to the service's own host.
MBB_CLIMATER_ACTION_CT = "application/vnd.vwg.mbb.ClimaterAction_v1_0_0+xml"
MBB_CHARGER_ACTION_CT = "application/vnd.vwg.mbb.ChargerAction_v1_0_0+xml"

# Each command: (service_id, operation_id, action_subpath, content_type,
# payload). operation_id is what the SecToken leg-1 authorizes. payload is the
# request body (XML string for climater/charger actions; the {temp} placeholder
# is substituted for climate-start). ``None`` payload = empty body.
_MBB_CLIMATER_START = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    "<action><type>startClimatisation</type><settings>"
    "<heaterSource>electric</heaterSource></settings></action>"
)
_MBB_CLIMATER_STOP = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    "<action><type>stopClimatisation</type></action>"
)
_MBB_WINDOWHEAT_START = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    "<action><type>startWindowHeating</type></action>"
)
_MBB_WINDOWHEAT_STOP = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    "<action><type>stopWindowHeating</type></action>"
)
_MBB_CHARGER_START = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    "<action><type>start</type></action>"
)
_MBB_CHARGER_STOP = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    "<action><type>stop</type></action>"
)


@dataclass
class MbbCommandSpec:
    """A durable MBB write-command: which service+operation to authorize via
    the SecToken flow, and the action POST (subpath, content-type, body)."""

    service_id: str
    operation_id: str
    action_subpath: str          # appended to the service base (e.g. "climater/actions")
    content_type: str
    body: str | None             # XML string, or None for empty body


# The supported durable commands, keyed by a stable name the coordinator uses.
MBB_COMMANDS: dict[str, MbbCommandSpec] = {
    "climate_start": MbbCommandSpec(
        "rclima_v1", "P_START_CLIMA_NOSET", "climater/actions",
        MBB_CLIMATER_ACTION_CT, _MBB_CLIMATER_START),
    "climate_stop": MbbCommandSpec(
        "rclima_v1", "P_STOP", "climater/actions",
        MBB_CLIMATER_ACTION_CT, _MBB_CLIMATER_STOP),
    "window_heat_start": MbbCommandSpec(
        "rclima_v1", "P_START_WND", "climater/actions",
        MBB_CLIMATER_ACTION_CT, _MBB_WINDOWHEAT_START),
    "window_heat_stop": MbbCommandSpec(
        "rclima_v1", "P_STOP_WND", "climater/actions",
        MBB_CLIMATER_ACTION_CT, _MBB_WINDOWHEAT_STOP),
    "charge_start": MbbCommandSpec(
        "rbatterycharge_v1", "P_START", "charger/actions",
        MBB_CHARGER_ACTION_CT, _MBB_CHARGER_START),
    "charge_stop": MbbCommandSpec(
        "rbatterycharge_v1", "P_STOP", "charger/actions",
        MBB_CHARGER_ACTION_CT, _MBB_CHARGER_STOP),
    # body is supplied at call time via build_mbb_charger_settings_body(soc).
    "charge_target_soc": MbbCommandSpec(
        "rbatterycharge_v1", "P_SETTINGS", "charger/actions",
        MBB_CHARGER_ACTION_CT, None),
}


def build_mbb_action_url(service_base: str, action_subpath: str) -> str:
    """Join an operationList service base with a command's action subpath."""
    return f"{service_base.rstrip('/')}/{action_subpath.lstrip('/')}"


def build_mbb_charger_settings_body(target_soc_pct: int) -> str:
    """ChargerAction body to set the target state-of-charge (%)."""
    soc = max(0, min(100, int(target_soc_pct)))
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        "<action><type>setSettings</type><settings>"
        f"<targetStateOfChargeInPercent>{soc}</targetStateOfChargeInPercent>"
        "</settings></action>"
    )
