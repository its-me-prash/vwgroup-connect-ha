# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""v2.15.5 — tests for the optional ABRP (A Better Routeplanner) push.

Coverage:

Pure mapping / fingerprint / send (no Home Assistant — run everywhere):
  * build_tlm sign flip: charging → NEGATIVE power; +charging never emitted.
  * is_parked = NOT is_driving; omitted when is_driving is None.
  * None-source fields are omitted; soh / speed / voltage / current never
    emitted; utc + soc always present.
  * unit/value pass-through (lat/lon/heading/soe/capacity/range/temps/odo).
  * telemetry_fingerprint: change → differs, same → equal, datetime-stable.
  * send_telemetry: posts api_key + token + url-encoded tlm; non-200 and
    {"status":"error"} raise AbrpError; api_key + token never appear in the
    AbrpError text or in a caplog record.
  * redact() never leaks the secret.

Service + sensor (needs HA — ``ha_required``, auto-skipped without HA):
  * data-changed binary sensor: ON when nothing sent yet, OFF after the
    fingerprint is recorded, ON again when telemetry changes.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

import pytest

from custom_components.vag_connect import abrp


# ───────────────────────────── fixtures ────────────────────────────────────


def _ev_vehicle(**overrides: Any) -> dict[str, Any]:
    """A representative EV snapshot (coordinator vehicle dict shape)."""
    v: dict[str, Any] = {
        "vin": "WVWZZZ1234567890X",
        "battery_soc": 63,
        "is_charging": False,
        "is_driving": True,
        "charging_power_kw": None,
        "latitude": 47.3769,
        "longitude": 8.5417,
        "heading": 180,
        "battery_available_kwh": 48.2,
        "battery_cap_kwh": 77.0,
        "electric_range_km": 310,
        "range_km": 999,  # must be IGNORED when electric_range_km present
        "outside_temp": 14.5,
        "battery_temp": 21.0,
        "odometer_km": 42000,
        # fields we must NEVER emit even if present in the dict:
        "voltage_12v": 12.6,
        "lifetime_avg_speed_kmh": 55.0,
    }
    v.update(overrides)
    return v


# ───────────────────────── build_tlm: core fields ──────────────────────────


def test_utc_and_soc_always_present() -> None:
    tlm = abrp.build_tlm({"vin": "X", "battery_soc": 50}, utc=1_700_000_000)
    assert tlm["utc"] == 1_700_000_000
    assert tlm["soc"] == 50


def test_soc_emitted_even_when_other_fields_missing() -> None:
    tlm = abrp.build_tlm({"vin": "X", "battery_soc": 0}, utc=1)
    # soc 0 is a real value (empty battery), not "missing".
    assert tlm["soc"] == 0


# ───────────────────────── build_tlm: power sign flip ───────────────────────


def test_charging_power_is_sent_negative() -> None:
    v = _ev_vehicle(is_charging=True, charging_power_kw=11.0, is_driving=False)
    tlm = abrp.build_tlm(v, utc=1)
    assert tlm["power"] == -11.0  # charge = NEGATIVE (iternio convention)


def test_charging_power_abs_then_negated_even_if_source_positive() -> None:
    v = _ev_vehicle(is_charging=True, charging_power_kw=7.4, is_driving=False)
    tlm = abrp.build_tlm(v, utc=1)
    assert tlm["power"] == -7.4
    assert tlm["power"] < 0


def test_power_omitted_when_not_charging() -> None:
    # Driving / discharging: we have no instantaneous power → omit entirely.
    v = _ev_vehicle(is_charging=False, charging_power_kw=11.0)
    tlm = abrp.build_tlm(v, utc=1)
    assert "power" not in tlm


def test_power_omitted_when_charging_but_rate_unknown() -> None:
    v = _ev_vehicle(is_charging=True, charging_power_kw=None, is_driving=False)
    tlm = abrp.build_tlm(v, utc=1)
    assert "power" not in tlm


# ───────────────────────── build_tlm: is_charging / is_parked ───────────────


def test_is_charging_flag_int() -> None:
    assert abrp.build_tlm(_ev_vehicle(is_charging=True, is_driving=False), 1)[
        "is_charging"
    ] == 1
    assert abrp.build_tlm(_ev_vehicle(is_charging=False), 1)["is_charging"] == 0


def test_is_charging_omitted_when_none() -> None:
    tlm = abrp.build_tlm(_ev_vehicle(is_charging=None), 1)
    assert "is_charging" not in tlm


def test_is_parked_is_not_is_driving() -> None:
    assert abrp.build_tlm(_ev_vehicle(is_driving=True), 1)["is_parked"] == 0
    assert abrp.build_tlm(_ev_vehicle(is_driving=False), 1)["is_parked"] == 1


def test_is_parked_omitted_when_is_driving_none() -> None:
    tlm = abrp.build_tlm(_ev_vehicle(is_driving=None), 1)
    assert "is_parked" not in tlm


# ───────────────────────── build_tlm: pass-through values ───────────────────


def test_location_energy_range_temps_odometer_passthrough() -> None:
    tlm = abrp.build_tlm(_ev_vehicle(), utc=1)
    assert tlm["lat"] == 47.3769
    assert tlm["lon"] == 8.5417
    assert tlm["heading"] == 180.0
    assert tlm["soe"] == 48.2
    assert tlm["capacity"] == 77.0
    assert tlm["ext_temp"] == 14.5
    assert tlm["batt_temp"] == 21.0
    assert tlm["odometer"] == 42000.0


def test_range_prefers_electric_over_headline() -> None:
    tlm = abrp.build_tlm(_ev_vehicle(), utc=1)
    assert tlm["est_battery_range"] == 310.0  # electric_range_km, NOT range_km


def test_range_falls_back_to_range_km() -> None:
    v = _ev_vehicle(electric_range_km=None, range_km=222)
    tlm = abrp.build_tlm(v, utc=1)
    assert tlm["est_battery_range"] == 222.0


# ───────────────────────── build_tlm: omissions ────────────────────────────


def test_none_source_fields_are_omitted() -> None:
    v = {
        "vin": "X",
        "battery_soc": 40,
        "latitude": None,
        "longitude": None,
        "heading": None,
        "battery_available_kwh": None,
        "battery_cap_kwh": None,
        "electric_range_km": None,
        "range_km": None,
        "outside_temp": None,
        "battery_temp": None,
        "odometer_km": None,
        "is_charging": None,
        "is_driving": None,
    }
    tlm = abrp.build_tlm(v, utc=99)
    # Only the two required core fields survive.
    assert set(tlm) == {"utc", "soc"}


def test_unsupported_fields_never_emitted() -> None:
    # Even when the source dict carries 12V volts / avg speed / soh / current,
    # build_tlm must NOT map them onto the ABRP voltage/speed/soh/current keys.
    v = _ev_vehicle(
        is_charging=True, charging_power_kw=5.0, is_driving=False,
        soh=98, speed=60, voltage=400, current=12,
    )
    tlm = abrp.build_tlm(v, utc=1)
    for forbidden in ("soh", "speed", "voltage", "current", "is_dcfc"):
        assert forbidden not in tlm, f"{forbidden} must never be sent"


# ───────────────────────── resolve_sample_utc ──────────────────────────────


def test_resolve_utc_prefers_last_seen() -> None:
    dt = datetime(2026, 6, 22, 12, 0, tzinfo=timezone.utc)
    epoch = int(dt.timestamp())
    v = _ev_vehicle(last_seen_at=dt, last_updated_at=datetime.now(timezone.utc))
    assert abrp.resolve_sample_utc(v, now_epoch=123) == epoch


def test_resolve_utc_falls_back_to_now() -> None:
    v = _ev_vehicle(last_seen_at=None, last_updated_at=None)
    assert abrp.resolve_sample_utc(v, now_epoch=555) == 555


# ───────────────────────── telemetry_fingerprint ───────────────────────────


def test_fingerprint_same_snapshot_equal() -> None:
    a = abrp.telemetry_fingerprint(_ev_vehicle())
    b = abrp.telemetry_fingerprint(_ev_vehicle())
    assert a == b


def test_fingerprint_changes_on_soc() -> None:
    a = abrp.telemetry_fingerprint(_ev_vehicle(battery_soc=63))
    b = abrp.telemetry_fingerprint(_ev_vehicle(battery_soc=64))
    assert a != b


def test_fingerprint_changes_on_gps_and_odometer_and_charging() -> None:
    base = _ev_vehicle()
    f0 = abrp.telemetry_fingerprint(base)
    assert f0 != abrp.telemetry_fingerprint(_ev_vehicle(latitude=48.0))
    assert f0 != abrp.telemetry_fingerprint(_ev_vehicle(odometer_km=42001))
    assert f0 != abrp.telemetry_fingerprint(_ev_vehicle(is_charging=True))


def test_fingerprint_datetime_stable_across_copies() -> None:
    dt = datetime(2026, 6, 22, 12, 0, tzinfo=timezone.utc)
    a = abrp.telemetry_fingerprint(_ev_vehicle(last_seen_at=dt))
    b = abrp.telemetry_fingerprint(
        _ev_vehicle(last_seen_at=datetime(2026, 6, 22, 12, 0, tzinfo=timezone.utc))
    )
    assert a == b
    assert hash(a) == hash(b)  # hashable for the listener-set


# ───────────────────────── redact ──────────────────────────────────────────


def test_redact_never_leaks() -> None:
    secret = "super-secret-token-abcdef"
    out = abrp.redact(secret)
    assert secret not in out
    assert "abcdef" not in out
    assert abrp.redact("") == "<unset>"
    assert abrp.redact(None) == "<unset>"


# ───────────────────────── send_telemetry (mocked HTTP) ─────────────────────


class _FakeResp:
    def __init__(self, status: int = 200, payload: Any = None) -> None:
        self.status = status
        self._payload = payload if payload is not None else {"status": "ok"}

    async def __aenter__(self) -> "_FakeResp":
        return self

    async def __aexit__(self, *exc: Any) -> None:
        return None

    async def json(self, content_type: Any = None) -> Any:
        return self._payload

    async def text(self) -> str:
        return json.dumps(self._payload)


class _FakeSession:
    def __init__(self, resp: _FakeResp) -> None:
        self._resp = resp
        self.calls: list[dict[str, Any]] = []

    def post(self, url: str, **kw: Any) -> _FakeResp:
        self.calls.append({"url": url, "params": kw.get("params")})
        return self._resp


async def test_send_telemetry_posts_credentials_and_tlm() -> None:
    session = _FakeSession(_FakeResp(200, {"status": "ok"}))
    tlm = {"utc": 1, "soc": 50}
    out = await abrp.send_telemetry(session, "DEVKEY", "USERTOK", tlm)
    assert out == {"status": "ok"}
    assert len(session.calls) == 1
    params = session.calls[0]["params"]
    assert params["api_key"] == "DEVKEY"
    assert params["token"] == "USERTOK"
    # tlm is a url-encodable JSON string carrying the payload.
    assert json.loads(params["tlm"]) == tlm
    assert session.calls[0]["url"] == abrp.ABRP_TLM_SEND_URL


async def test_send_telemetry_non_200_raises_without_leaking() -> None:
    session = _FakeSession(_FakeResp(403, {"status": "error", "message": "bad key"}))
    with pytest.raises(abrp.AbrpError) as ei:
        await abrp.send_telemetry(session, "DEVKEY", "USERTOK", {"utc": 1, "soc": 5})
    msg = str(ei.value)
    assert "DEVKEY" not in msg
    assert "USERTOK" not in msg


async def test_send_telemetry_status_not_ok_raises() -> None:
    session = _FakeSession(_FakeResp(200, {"status": "error"}))
    with pytest.raises(abrp.AbrpError):
        await abrp.send_telemetry(session, "K", "T", {"utc": 1, "soc": 5})


async def test_send_telemetry_missing_credentials_raises() -> None:
    session = _FakeSession(_FakeResp(200))
    with pytest.raises(abrp.AbrpError):
        await abrp.send_telemetry(session, "", "T", {"utc": 1, "soc": 5})
    with pytest.raises(abrp.AbrpError):
        await abrp.send_telemetry(session, "K", "", {"utc": 1, "soc": 5})
    # No POST attempted when a credential is missing.
    assert session.calls == []


async def test_send_telemetry_does_not_log_secrets(
    caplog: pytest.LogCaptureFixture,
) -> None:
    session = _FakeSession(_FakeResp(200, {"status": "ok"}))
    with caplog.at_level(logging.DEBUG, logger="custom_components.vag_connect.abrp"):
        await abrp.send_telemetry(
            session, "DEVKEY-SECRET", "USERTOK-SECRET", {"utc": 1, "soc": 5}
        )
    blob = "\n".join(r.getMessage() for r in caplog.records)
    assert "DEVKEY-SECRET" not in blob
    assert "USERTOK-SECRET" not in blob


# ───────────────────────── HA-side: binary sensor logic ────────────────────

pytestmark_ha = pytest.mark.ha_required


@pytest.mark.ha_required
def test_data_changed_sensor_state_machine() -> None:
    """ON when nothing sent → OFF after fingerprint recorded → ON on change."""
    from unittest.mock import MagicMock

    from custom_components.vag_connect.binary_sensor import (
        VagAbrpDataChangedSensor,
    )

    vin = "WVWZZZ1234567890X"
    veh = _ev_vehicle(vin=vin)

    coord = MagicMock()
    coord.data = {vin: veh}
    coord.abrp_last_sent_fingerprint = {}

    sensor = VagAbrpDataChangedSensor(coord, vin)

    # Nothing sent yet → there IS something new to upload.
    assert sensor.is_on is True

    # Record the current fingerprint (what abrp_send does on success).
    coord.abrp_last_sent_fingerprint[vin] = abrp.telemetry_fingerprint(veh)
    assert sensor.is_on is False

    # Telemetry changes (e.g. SoC ticks up) → ON again.
    coord.data = {vin: _ev_vehicle(vin=vin, battery_soc=64)}
    assert sensor.is_on is True


@pytest.mark.ha_required
def test_data_changed_sensor_off_without_soc() -> None:
    from unittest.mock import MagicMock

    from custom_components.vag_connect.binary_sensor import (
        VagAbrpDataChangedSensor,
    )

    vin = "WVWZZZ1234567890X"
    coord = MagicMock()
    coord.data = {vin: {"vin": vin, "battery_soc": None}}
    coord.abrp_last_sent_fingerprint = {}
    sensor = VagAbrpDataChangedSensor(coord, vin)
    assert sensor.is_on is False
