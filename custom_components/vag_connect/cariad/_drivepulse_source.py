# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""DrivePulse bus events: lowest-trust supplementary source (pure mapper).

DrivePulse is a third-party Home Assistant integration for a generic OBD2
dongle. It fires ``drivepulse_trip_start`` / ``drivepulse_trip_end`` on the HA
event bus. The payload is foreign, unvalidated input, carries **no VIN**, and
comes from a generic dongle that knows nothing of the car's drivetrain, so this
is the bottom of the source ladder: it may only fill four gaps (fuel level,
HV state of charge, range, 12 V voltage) and never anything that identifies or
classifies the vehicle. The caller owns the VIN pairing and the storage; this
module only turns an event into a small JSON-safe snapshot and a snapshot into
a thin ``VehicleData``. It imports nothing from Home Assistant and never raises.

Field names: DrivePulse webhook schema 1 (``schema/drivepulse-schema-1.json``
at tag ``v0.1.3`` of ``davidedrivepulse/drivepulse-home-assistant``). The names
were typed fresh from that schema; no code was taken over.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any

from .models import VehicleData

CHANNEL = "drivepulse"
EVENT_TRIP_START = "drivepulse_trip_start"
EVENT_TRIP_END = "drivepulse_trip_end"

_MAX_DEVICE_ID_LEN = 64
# How far a stored stamp may run ahead of the clock and still be believed.
_FUTURE_TOLERANCE_S = 300.0

# payload key -> (snapshot key, lo, hi, convert)
_FIELDS: tuple[tuple[str, str, float, float, bool], ...] = (
    ("fuel_level_pct", "fuel_level", 0.0, 100.0, True),
    ("hv_soc_pct", "battery_soc", 0.0, 100.0, True),
    ("range_km", "range_km", 0.0, 2000.0, True),
    ("battery_voltage", "voltage_12v", 6.0, 18.0, False),
)


def _number(value: Any, lo: float, hi: float, as_int: bool) -> int | float | None:
    """Return ``value`` as a bounded number, or ``None``.

    ``bool`` is an ``int`` subclass and would pass for 0/1, and a string or a
    NaN would slip through a naive ``float()``; the sender is not trusted, so
    only a real, finite, in-range number is accepted.
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    v = float(value)
    if not math.isfinite(v) or not lo <= v <= hi:
        return None
    return int(round(v)) if as_int else round(v, 2)


def _parse_ts(value: Any) -> datetime | None:
    """Parse an ISO-8601 string to an aware UTC datetime (naive counts as UTC)."""
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    if text.endswith(("Z", "z")):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _clean_values(raw: Any, keys: dict[str, tuple[float, float, bool]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    if not isinstance(raw, dict):
        return out
    for name, (lo, hi, as_int) in keys.items():
        v = _number(raw.get(name), lo, hi, as_int)
        if v is not None:
            out[name] = v
    return out


def parse_event(data: Any, received_at: datetime) -> dict[str, Any] | None:
    """Reduce a DrivePulse event payload to ``{device_id, ts, values}``.

    ``None`` when the payload is unusable (not a dict, no device id, or no
    value survived the range checks). The vehicle name is dropped on purpose:
    it is free text from a foreign system and has no use here.
    """
    try:
        if not isinstance(data, dict):
            return None
        device_id = data.get("device_id")
        if not isinstance(device_id, str):
            return None
        device_id = device_id.strip()
        if not device_id or len(device_id) > _MAX_DEVICE_ID_LEN:
            return None

        values: dict[str, Any] = {}
        for src, dst, lo, hi, as_int in _FIELDS:
            v = _number(data.get(src), lo, hi, as_int)
            if v is not None:
                values[dst] = v
        if not values:
            return None

        if received_at.tzinfo is None:
            received_at = received_at.replace(tzinfo=timezone.utc)
        received = received_at.astimezone(timezone.utc)
        # The dongle has no clock; sent_at is a phone's clock. A time in the
        # future must not make a reading look fresher than it is.
        sent = _parse_ts(data.get("sent_at"))
        ts = min(sent, received) if sent is not None else received
        return {"device_id": device_id, "ts": ts.isoformat(), "values": values}
    except Exception:  # noqa: BLE001 - foreign input must never break the bus handler
        return None


_SNAPSHOT_KEYS: dict[str, tuple[float, float, bool]] = {
    dst: (lo, hi, as_int) for _src, dst, lo, hi, as_int in _FIELDS
}


def build_vehicle_data(
    vin: str,
    snapshot: Any,
    *,
    has_battery: bool,
    has_combustion: bool,
    now: datetime,
    max_age_s: float,
) -> VehicleData | None:
    """Build a thin ``VehicleData`` from a stored snapshot, or ``None``.

    The snapshot may come from disk, so it is re-checked in full. Drivetrain
    flags are inputs, never outputs: a generic dongle cannot tell a fuel level
    from an HV level on a hybrid, so fuel and SoC are only set where the car is
    already known to have that energy store.

    Every field is dated on its own. ``stamps`` maps a field to the time its
    value was read; a field without an entry there falls back to the
    snapshot's ``ts``. One event rarely carries every field, so a single
    stamp for the whole snapshot would either date an old value as new or
    throw a still-good value away with it.
    """
    try:
        if not isinstance(snapshot, dict):
            return None
        raw_values = snapshot.get("values")
        if not isinstance(raw_values, dict):
            return None
        raw_stamps = snapshot.get("stamps")
        stamps = raw_stamps if isinstance(raw_stamps, dict) else {}
        default_ts = _parse_ts(snapshot.get("ts"))
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        now = now.astimezone(timezone.utc)

        values = _clean_values(raw_values, _SNAPSHOT_KEYS)
        if not has_combustion:
            values.pop("fuel_level", None)
        if not has_battery:
            values.pop("battery_soc", None)

        vd = VehicleData(vin=vin)
        filled = False
        for name, value in values.items():
            ts = _parse_ts(stamps[name]) if name in stamps else default_ts
            if ts is None:
                continue
            age = (now - ts).total_seconds()
            # Too old, or stamped well ahead of the clock: a stamp from the
            # future would never expire and would outrank every other reading
            # by age.
            if age > max_age_s or age < -_FUTURE_TOLERANCE_S:
                continue
            setattr(vd, name, value)
            # Inside the tolerance the stamp may still be ahead of the clock;
            # written out it is capped, so it never claims to be newer than now.
            vd.field_captured_ts[name] = min(ts, now).isoformat()
            filled = True
        return vd if filled else None
    except Exception:  # noqa: BLE001 - a supplementary source must not break the poll
        return None
