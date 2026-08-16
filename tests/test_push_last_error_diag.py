# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""v3.2.2 — the last push connect-failure reason is surfaced in diagnostics.

Marco Schmidt's v3.2.1 diag showed the Škoda MQTT push channel as ``tripped``
but not *why* (the reason was only in the HA WARNING log, not the config-entry
diagnostics he exported). The circuit-breaker now remembers a value-safe reason
string and the coordinator exposes it as ``push_last_errors`` so the diagnostics
dump is self-service.
"""
from __future__ import annotations

from custom_components.vag_connect.cariad.push.base import PushManager, PushManagerState


class _DummyPush(PushManager):
    async def start(self) -> None:  # pragma: no cover - not exercised
        pass

    async def stop(self) -> None:  # pragma: no cover - not exercised
        pass


def _mgr() -> _DummyPush:
    return _DummyPush(lambda _evt: None)


def test_record_failure_stores_reason():
    m = _mgr()
    assert m.last_failure_reason == ""
    m._record_failure("connect-loop: MqttError: not authorized")
    assert m.last_failure_reason == "connect-loop: MqttError: not authorized"


def test_empty_reason_becomes_placeholder():
    m = _mgr()
    m._record_failure("")
    assert m.last_failure_reason == "no-reason-given"


def test_success_clears_reason():
    m = _mgr()
    m._record_failure("connect-loop: MqttError: boom")
    m._record_success()
    assert m.last_failure_reason == ""


def test_reason_survives_until_trip():
    m = _mgr()
    for _ in range(3):  # CIRCUIT_BREAKER_MAX_STRIKES
        m._record_failure("connect-loop: ConnectionRefusedError: [Errno 111]")
    assert m.state == PushManagerState.TRIPPED
    assert "ConnectionRefusedError" in m.last_failure_reason


# ── coordinator aggregation ──────────────────────────────────────────────────


def _coord(managers: dict):
    from custom_components.vag_connect.coordinator import VagConnectCoordinator
    coord = VagConnectCoordinator.__new__(VagConnectCoordinator)
    coord._skoda_push = managers.get("skoda_mqtt")
    coord._cupra_seat_push = managers.get("cupra_seat_fcm")
    coord._audi_vw_push = managers.get("audi_vw_fcm")
    return coord


def test_push_last_errors_reports_only_failed_channels():
    tripped = _mgr()
    tripped._record_failure("connect-loop: MqttError: broker refused TOTP")
    healthy = _mgr()  # no failure recorded → omitted
    coord = _coord({"skoda_mqtt": tripped, "audi_vw_fcm": healthy})
    errors = coord.push_last_errors
    assert errors == {"skoda_mqtt": "connect-loop: MqttError: broker refused TOTP"}


def test_push_last_errors_empty_when_all_healthy():
    coord = _coord({"skoda_mqtt": _mgr()})
    assert coord.push_last_errors == {}
