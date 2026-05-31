# Copyright 2026 Prash Balan (@its-me-prash) — Apache License 2.0
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

### Phase 2+ (future releases)

- `command_lock` / `command_unlock` MBB with SPIN secure-token flow
- `command_start_climate` / `_stop` MBB
- `command_start_charging` / `_stop` MBB
- `command_set_target_soc` MBB

### Privacy

- VINs masked to last 6 chars in logs
- SPIN never logged (existing redaction in `_unexpected_keys.py`)
- HomeRegion lookup uses user's existing IDK token
"""

from __future__ import annotations

import logging
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
