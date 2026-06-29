# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""ABRP / A Better Routeplanner — iternio telemetry (``/tlm/send``) client.

v2.15.5 — optional outbound live-telemetry push to A Better Routeplanner.

This module is deliberately isolated + unit-testable: it holds the pure
``VehicleData``→``tlm``-dict mapping plus the thin aiohttp POST. It does
NOT import Home Assistant, the coordinator, or any entity code, so the
mapping + sign conventions can be exercised in plain-Python tests (mirrors
the pattern of the other ``cariad/`` helpers).

Wire contract (grounded against the official iternio field reference,
cross-checked with robske110/IDDataLogger, snaptec/openWB,
DasBasti/SmartHashtag, adamsanta/abrp-vehicle-telemetry, mtandersson/aioabrp):

    POST https://api.iternio.com/1/tlm/send
        ?api_key=<DEVELOPER_KEY>   developer/partner key (per integration)
        &token=<USER_TOKEN>        per-vehicle token from the ABRP app
        &tlm=<url-encoded JSON>    the telemetry payload below

LEGACY WIRE UNITS (raw /tlm/send — NOT the aioabrp SI-normalised model):
    utc                [s]    epoch seconds, UTC.        REQUIRED
    soc                [%]    0–100.                     REQUIRED (core)
    power              [kW]   + = output/discharge, − = input/charge
    is_charging        [0/1]
    is_parked          [0/1]
    lat / lon          [°]    decimal degrees
    heading            [°]
    soe                [kWh]  energy currently in pack
    capacity           [kWh]  usable capacity
    est_battery_range  [km]
    ext_temp           [°C]   ambient
    batt_temp          [°C]
    odometer           [km]

POWER SIGN — the official iternio convention is "output POSITIVE, input
(charging) NEGATIVE". We only ever know charging power, so we send
``-abs(charging_power_kw)`` while charging and OMIT power otherwise (we
have no instantaneous driving/discharge power). Sending +charging_power
would tell ABRP the car is DISCHARGING at that rate — wrong.

FIELDS WE LACK → never emitted: soh (no state-of-health), speed (only avg
aggregates, wrong for live telemetry), voltage (only the 12V starter
battery, not the HV pack), current (no live HV pack amperage), is_dcfc (no
reliable DC discriminator yet). Omitting beats guessing.

SECURITY: the api_key + token are credentials. They go on the URL as query
params, never into a log line. ``redact()`` masks them; ``send_telemetry``
only ever logs the redacted endpoint.
"""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urlencode

_LOGGER = logging.getLogger(__name__)

# Official iternio telemetry endpoint (versioned path "1").
ABRP_TLM_SEND_URL = "https://api.iternio.com/1/tlm/send"

# Default POST timeout (seconds). ABRP is a fire-and-forget side channel —
# never block the poll loop waiting on it.
ABRP_TIMEOUT_S = 15

# The fingerprint keys that decide "is this a NEW telemetry snapshot worth
# uploading?". Deliberately the upload-relevant signals only — model name,
# warning lights, subscription counters etc. don't change the telemetry and
# would cause redundant uploads. ``last_seen`` (the car's own sample time)
# is the strongest change signal; soc/odometer/charging/gps cover the cases
# where last_seen is absent for a brand.
_FINGERPRINT_KEYS: tuple[str, ...] = (
    "battery_soc",
    "odometer_km",
    "is_charging",
    "charging_power_kw",
    "latitude",
    "longitude",
    "last_seen_at",
)


def redact(secret: str | None) -> str:
    """Mask an api_key / token for safe logging.

    Shows nothing of the value beyond its presence + length bucket, so a
    log line can confirm "a token was supplied" without leaking it. Never
    returns any character of the original secret.
    """
    if not secret:
        return "<unset>"
    return f"<redacted:{len(secret)} chars>"


def _coerce_utc_seconds(value: Any) -> int | None:
    """Best-effort convert a timestamp-ish value to epoch seconds (int).

    Accepts a ``datetime`` (aware or naive→assumed UTC), an int/float epoch,
    or a numeric string. Returns None when it can't make sense of the value
    so the caller falls back to "now".
    """
    if value is None:
        return None
    # datetime → epoch
    try:
        from datetime import datetime, timezone

        if isinstance(value, datetime):
            dt = value
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return int(dt.timestamp())
    except Exception:  # noqa: BLE001 — never let a bad sample break the send
        return None
    # numeric epoch (int/float or numeric string)
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        try:
            return int(float(value))
        except ValueError:
            return None
    return None


def build_tlm(vehicle: dict[str, Any], utc: int) -> dict[str, Any]:
    """Map a coordinator vehicle dict to the ABRP ``tlm`` payload.

    ``vehicle`` is the brand-agnostic ``VehicleData.to_dict()`` snapshot
    the coordinator stores in ``self.vehicles[vin]``. ``utc`` is the sample
    time in epoch seconds (the caller prefers ``last_seen_at`` /
    ``last_updated_at`` and falls back to "now").

    Only keys whose source value is present (not None) are included, except
    ``utc`` + ``soc`` which are the REQUIRED core fields and always emitted.
    Applies the charging power SIGN FLIP and derives ``is_parked`` from
    ``is_driving``.
    """
    tlm: dict[str, Any] = {"utc": int(utc)}

    # soc — REQUIRED core field. We always include it; if absent it goes as
    # None which ABRP rejects loudly (better than silently dropping the core
    # field). In practice the caller gates on soc-present before sending.
    soc = vehicle.get("battery_soc")
    tlm["soc"] = soc

    # power [kW] — charging only, with sign flip. We have no instantaneous
    # driving/discharge power, so positive power stays unset (omitted). Send
    # negative power ONLY while actively charging AND we have a rate.
    is_charging = vehicle.get("is_charging")
    charging_power_kw = vehicle.get("charging_power_kw")
    if is_charging and charging_power_kw is not None:
        tlm["power"] = -abs(float(charging_power_kw))

    if is_charging is not None:
        tlm["is_charging"] = 1 if is_charging else 0

    # is_parked = NOT is_driving — only when we actually know is_driving.
    is_driving = vehicle.get("is_driving")
    if is_driving is not None:
        tlm["is_parked"] = 0 if is_driving else 1

    # Location.
    lat = vehicle.get("latitude")
    lon = vehicle.get("longitude")
    if lat is not None:
        tlm["lat"] = float(lat)
    if lon is not None:
        tlm["lon"] = float(lon)
    heading = vehicle.get("heading")
    if heading is not None:
        tlm["heading"] = float(heading)

    # Energy.
    soe = vehicle.get("battery_available_kwh")
    if soe is not None:
        tlm["soe"] = float(soe)
    capacity = vehicle.get("battery_cap_kwh")
    if capacity is not None:
        tlm["capacity"] = float(capacity)

    # Range — prefer the EV electric range, fall back to the headline range.
    est_range = vehicle.get("electric_range_km")
    if est_range is None:
        est_range = vehicle.get("range_km")
    if est_range is not None:
        tlm["est_battery_range"] = float(est_range)

    # Temperatures.
    ext_temp = vehicle.get("outside_temp")
    if ext_temp is not None:
        tlm["ext_temp"] = float(ext_temp)
    batt_temp = vehicle.get("battery_temp")
    if batt_temp is not None:
        tlm["batt_temp"] = float(batt_temp)

    # Odometer.
    odometer = vehicle.get("odometer_km")
    if odometer is not None:
        tlm["odometer"] = float(odometer)

    return tlm


def telemetry_fingerprint(vehicle: dict[str, Any]) -> tuple[Any, ...]:
    """Return a hashable fingerprint of the upload-relevant telemetry.

    Two snapshots with the same fingerprint carry the same information for
    ABRP, so re-uploading the second is wasteful. The "ABRP data changed"
    binary sensor compares this against the last successfully-sent
    fingerprint to drive idempotent automations. ``datetime`` values are
    normalised to a stable string so equality is reliable across copies.
    """
    parts: list[Any] = []
    for key in _FINGERPRINT_KEYS:
        val = vehicle.get(key)
        # Normalise datetime-ish values to ISO string for stable equality.
        try:
            from datetime import datetime

            if isinstance(val, datetime):
                val = val.isoformat()
        except Exception:  # noqa: BLE001
            val = None
        parts.append(val)
    return tuple(parts)


def resolve_sample_utc(vehicle: dict[str, Any], *, now_epoch: int) -> int:
    """Pick the best sample timestamp for the ``utc`` field.

    Prefer the car's own last-seen time, then our last poll time, then the
    supplied "now". Always returns a sane epoch-seconds int.
    """
    for key in ("last_seen_at", "last_updated_at"):
        secs = _coerce_utc_seconds(vehicle.get(key))
        if secs is not None and secs > 0:
            return secs
    return now_epoch


class AbrpError(Exception):
    """Raised when an ABRP telemetry send fails (non-2xx or transport error).

    The message never contains the api_key or token.
    """


async def send_telemetry(
    session: Any,
    api_key: str,
    token: str,
    tlm: dict[str, Any],
    *,
    url: str = ABRP_TLM_SEND_URL,
    timeout_s: int = ABRP_TIMEOUT_S,
) -> dict[str, Any]:
    """POST a telemetry payload to ABRP's ``/tlm/send`` endpoint.

    ``session`` is an aiohttp ``ClientSession`` (HA's shared session in
    production). The api_key + token go on the query string with the
    URL-encoded ``tlm`` JSON, exactly as the iternio contract specifies.

    Returns the parsed JSON response (iternio replies ``{"status": "ok"}``
    on success). Raises ``AbrpError`` on a non-2xx status, an
    ``{"status": ...}`` that isn't ``ok``, or a transport error. The
    api_key + token are NEVER included in any log line or exception text.
    """
    import json as _json

    # Validate credentials WITHOUT echoing them.
    if not api_key or not token:
        raise AbrpError(
            "ABRP send skipped: missing api_key or token "
            f"(api_key={redact(api_key)}, token={redact(token)})"
        )

    params = {
        "api_key": api_key,
        "token": token,
        "tlm": _json.dumps(tlm, separators=(",", ":")),
    }
    # Build a redacted form of the request for logging — the real request
    # uses the full params, but nothing secret ever reaches the logger.
    safe_query = urlencode(
        {"api_key": redact(api_key), "token": redact(token), "tlm": "<json>"}
    )
    _LOGGER.debug("ABRP send → %s?%s (tlm keys: %s)", url, safe_query, sorted(tlm))

    try:
        import aiohttp  # noqa: PLC0415

        timeout = aiohttp.ClientTimeout(total=timeout_s)
        async with session.post(url, params=params, timeout=timeout) as resp:
            status = resp.status
            try:
                body: dict[str, Any] = await resp.json(content_type=None)
            except Exception:  # noqa: BLE001 — non-JSON error body
                text = await resp.text()
                body = {"_raw": text[:200]}
            if status < 200 or status >= 300:
                raise AbrpError(
                    f"ABRP /tlm/send returned HTTP {status}: "
                    f"{_safe_body(body)}"
                )
            # iternio replies {"status":"ok"} on success.
            api_status = body.get("status")
            if api_status is not None and api_status != "ok":
                raise AbrpError(
                    f"ABRP /tlm/send rejected the payload: {_safe_body(body)}"
                )
            return body
    except AbrpError:
        raise
    except Exception as exc:  # noqa: BLE001 — transport/timeout → AbrpError
        # Stringify defensively: an aiohttp exception repr could in theory
        # echo the URL (with query). Strip anything that smells like our
        # secrets so a leaked credential can't ride out on an error string.
        raise AbrpError(f"ABRP /tlm/send transport error: {type(exc).__name__}") from exc


def _safe_body(body: dict[str, Any]) -> str:
    """Stringify an ABRP response body for an error message.

    ABRP error bodies never contain our credentials, but cap the length so a
    huge HTML error page doesn't flood the log.
    """
    s = str(body)
    return s if len(s) <= 300 else s[:300] + "…"
