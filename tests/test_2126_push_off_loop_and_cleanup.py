"""#2126: push managers keep blocking work off the event loop and release
the firebase-messaging client when a connect attempt fails.

Reported on a CUPRA Born (5.3.0): Home Assistant flagged
``import_module('firebase_messaging')`` as a blocking call inside the
event loop, and a registration refused with ``PHONE_REGISTRATION_ERROR``
left "Unclosed client session" errors behind.

The second part traces to firebase-messaging 0.4.5 itself:
``FcmPushClient.checkin_or_register`` closes its ``FcmRegister`` (and with
it the aiohttp session the register opened) only after a successful
registration. When ``register()`` raises, the close is skipped. One open
session per failed attempt, three attempts before the breaker trips.
"""

from __future__ import annotations

import asyncio
import importlib
import sys
import threading
import types
from unittest.mock import AsyncMock

import pytest

from custom_components.vag_connect.cariad.push.base import PushManagerState

_PUSH = "custom_components.vag_connect.cariad.push"

# (module, class, extra constructor kwargs, optional libraries it checks)
_MANAGERS = [
    ("cupra_seat_fcm", "CupraSeatPushManager", {"brand": "cupra"},
     {"firebase_messaging"}),
    ("audi_vw_fcm", "AudiVWPushManager", {"brand": "audi"},
     {"firebase_messaging"}),
    ("skoda_mqtt", "SkodaPushManager", {},
     {"aiomqtt", "firebase_messaging"}),
]
_IDS = [m[0] for m in _MANAGERS]


def _make(module: str, cls: str, extra: dict):
    mod = importlib.import_module(f"{_PUSH}.{module}")
    return getattr(mod, cls)(
        AsyncMock(),
        user_id="user-0000-123456",
        access_token_provider=AsyncMock(return_value="oauth-token"),
        vins=["WVWZZZTESTVIN0001"],
        **extra,
    )


# ---------------------------------------------------------------------------
# Part 1: the dependency import runs in the executor, not on the loop.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(("module", "cls", "extra", "libs"), _MANAGERS, ids=_IDS)
async def test_dependency_import_runs_off_the_event_loop(
    module, cls, extra, libs, monkeypatch
):
    """The real ``_lazy_check_dependencies`` runs, with ``import_module``
    recording the thread it is called on."""
    m = _make(module, cls, extra)
    loop_thread = threading.get_ident()
    seen: dict[str, int] = {}
    original = importlib.import_module

    def recording_import(name, package=None):
        if name in libs:
            seen[name] = threading.get_ident()
            return types.ModuleType(name)
        return original(name, package)

    monkeypatch.setattr(importlib, "import_module", recording_import)

    async def no_network() -> None:
        await m._stop_event.wait()

    monkeypatch.setattr(m, "_run_loop", no_network)

    await m.start()
    try:
        assert set(seen) == libs, "the dependency check did not run"
        assert all(t != loop_thread for t in seen.values()), (
            "import_module ran on the event-loop thread"
        )
        assert m._loop_task is not None
    finally:
        await m.stop()


@pytest.mark.parametrize(("module", "cls", "extra", "libs"), _MANAGERS, ids=_IDS)
async def test_missing_dependency_still_counts_as_a_strike(
    module, cls, extra, libs, monkeypatch
):
    m = _make(module, cls, extra)

    def missing() -> None:
        raise ImportError("firebase_messaging: No module named 'firebase_messaging'")

    monkeypatch.setattr(m, "_lazy_check_dependencies", missing)
    await m.start()
    assert m._state == PushManagerState.UNAVAILABLE
    assert m.strike_count == 1
    assert m._loop_task is None


@pytest.mark.parametrize(("module", "cls", "extra", "libs"), _MANAGERS, ids=_IDS)
async def test_stop_during_the_check_does_not_start_the_loop(
    module, cls, extra, libs, monkeypatch
):
    """With the check in the executor, ``stop()`` can run while it waits.
    The start must then not spawn the receive loop afterwards."""
    m = _make(module, cls, extra)
    entered = threading.Event()
    release = threading.Event()

    def slow_check() -> None:
        entered.set()
        release.wait(timeout=5)

    loop_runs: list[bool] = []

    async def record_loop() -> None:
        loop_runs.append(True)

    monkeypatch.setattr(m, "_lazy_check_dependencies", slow_check)
    monkeypatch.setattr(m, "_run_loop", record_loop)

    starting = asyncio.create_task(m.start())
    for _ in range(200):
        if entered.is_set():
            break
        await asyncio.sleep(0.01)
    assert entered.is_set()
    await m.stop()
    release.set()
    await starting
    await asyncio.sleep(0)

    assert m._loop_task is None
    assert loop_runs == []
    assert m._state == PushManagerState.STOPPED


# ---------------------------------------------------------------------------
# Part 2: a failed connect attempt releases the firebase-messaging client.
# ---------------------------------------------------------------------------


class _FakeRegister:
    def __init__(self) -> None:
        self.closed = 0

    async def close(self) -> None:
        self.closed += 1


class _FakeFcmClient:
    """Shaped like firebase-messaging 0.4.5's ``FcmPushClient``."""

    fail_registration = True
    instances: list[_FakeFcmClient] = []

    def __init__(self, callback, config, credentials, credentials_cb) -> None:
        self.register: _FakeRegister | None = None
        self.started = False
        self.stops = 0
        _FakeFcmClient.instances.append(self)

    async def checkin_or_register(self) -> str:
        self.register = _FakeRegister()
        if self.fail_registration:
            # The library skips ``await self.register.close()`` here.
            raise RuntimeError(
                "Unable to establish subscription with Google Cloud Messaging."
            )
        await self.register.close()
        return "fcm-token"

    async def start(self) -> None:
        self.started = True

    async def stop(self) -> None:
        if not self.started:
            # 0.4.5: ``stopping_lock`` is None until start() has run.
            raise TypeError("'NoneType' object does not support the "
                            "asynchronous context manager protocol")
        self.stops += 1


@pytest.fixture
def fake_firebase(monkeypatch):
    fm = types.ModuleType("firebase_messaging")
    fm.FcmPushClient = _FakeFcmClient
    fm.FcmRegisterConfig = lambda *a, **k: object()
    monkeypatch.setitem(sys.modules, "firebase_messaging", fm)
    _FakeFcmClient.instances = []
    _FakeFcmClient.fail_registration = True
    return _FakeFcmClient


_FCM_MANAGERS = [m for m in _MANAGERS if m[0] != "skoda_mqtt"]
_FCM_IDS = [m[0] for m in _FCM_MANAGERS]


@pytest.mark.parametrize(("module", "cls", "extra", "libs"), _FCM_MANAGERS,
                         ids=_FCM_IDS)
async def test_failed_registration_closes_the_register_session(
    module, cls, extra, libs, fake_firebase
):
    m = _make(module, cls, extra)
    with pytest.raises(RuntimeError, match="Google Cloud Messaging"):
        await m._connect_and_listen()
    (client,) = fake_firebase.instances
    assert client.register is not None
    assert client.register.closed == 1
    assert m._fcm_client is None


@pytest.mark.parametrize(("module", "cls", "extra", "libs"), _FCM_MANAGERS,
                         ids=_FCM_IDS)
async def test_failed_subscription_does_not_keep_the_client(
    module, cls, extra, libs, fake_firebase, monkeypatch
):
    fake_firebase.fail_registration = False
    m = _make(module, cls, extra)
    refused = RuntimeError("subscription POST returned HTTP 403")
    for name in ("_post_ola_subscription", "_post_cariad_subscription"):
        if hasattr(m, name):
            monkeypatch.setattr(m, name, AsyncMock(side_effect=refused))
    with pytest.raises(RuntimeError, match="HTTP 403"):
        await m._connect_and_listen()
    (client,) = fake_firebase.instances
    assert not client.started
    assert m._fcm_client is None


@pytest.mark.parametrize(("module", "cls", "extra", "libs"), _FCM_MANAGERS,
                         ids=_FCM_IDS)
async def test_clean_stop_still_stops_a_started_client(
    module, cls, extra, libs, fake_firebase, monkeypatch
):
    fake_firebase.fail_registration = False
    m = _make(module, cls, extra)
    for name in ("_post_ola_subscription", "_post_cariad_subscription"):
        if hasattr(m, name):
            monkeypatch.setattr(m, name, AsyncMock())
    task = asyncio.create_task(m._connect_and_listen())
    for _ in range(100):
        if m._state == PushManagerState.CONNECTED:
            break
        await asyncio.sleep(0.01)
    assert m._state == PushManagerState.CONNECTED
    m._stop_event.set()
    await task
    (client,) = fake_firebase.instances
    assert client.stops == 1
    assert m._fcm_client is None
    assert m._state == PushManagerState.STOPPED


async def test_skoda_failed_token_registration_closes_the_register_session(
    fake_firebase,
):
    m = _make("skoda_mqtt", "SkodaPushManager", {})
    with pytest.raises(RuntimeError, match="Google Cloud Messaging"):
        await m._register_fcm_token()
    (client,) = fake_firebase.instances
    assert client.register is not None
    assert client.register.closed == 1
    assert m._fcm_token is None


async def test_skoda_token_registration_still_returns_the_token(fake_firebase):
    fake_firebase.fail_registration = False
    m = _make("skoda_mqtt", "SkodaPushManager", {})
    assert await m._register_fcm_token() == "fcm-token"
    assert m._fcm_token == "fcm-token"


async def test_skoda_tls_context_is_built_off_the_event_loop(monkeypatch):
    """``SSLContext.load_default_certs`` reads the certificate store; Home
    Assistant reports it as blocking when it runs on the loop."""
    aiomqtt = types.ModuleType("aiomqtt")
    paho = types.ModuleType("paho")
    paho_mqtt = types.ModuleType("paho.mqtt")
    pkt = types.ModuleType("paho.mqtt.packettypes")
    pkt.PacketTypes = types.SimpleNamespace(CONNECT=1)
    props = types.ModuleType("paho.mqtt.properties")

    class _Properties:
        def __init__(self, ptype) -> None:
            self.UserProperty = None

    props.Properties = _Properties
    for name, mod in (("aiomqtt", aiomqtt), ("paho", paho),
                      ("paho.mqtt", paho_mqtt),
                      ("paho.mqtt.packettypes", pkt),
                      ("paho.mqtt.properties", props)):
        monkeypatch.setitem(sys.modules, name, mod)

    m = _make("skoda_mqtt", "SkodaPushManager", {})
    monkeypatch.setattr(m, "_register_fcm_token", AsyncMock(return_value="tok"))
    loop_thread = threading.get_ident()
    built_on: list[int] = []

    class _Stop(Exception):
        pass

    def recording_build():
        built_on.append(threading.get_ident())
        raise _Stop

    monkeypatch.setattr(m, "_build_ssl_context", recording_build)
    with pytest.raises(_Stop):
        await m._connect_and_listen()
    assert built_on and built_on[0] != loop_thread


# ---------------------------------------------------------------------------
# Part 3: the same against the real library, where it is installed.
# ---------------------------------------------------------------------------


async def test_real_library_session_is_closed_after_a_refused_registration(
    monkeypatch,
):
    """Uses firebase-messaging itself: its ``FcmRegister`` opens a real
    aiohttp session, then ``register()`` fails the way it does when GCM
    answers PHONE_REGISTRATION_ERROR on both tries."""
    fcmregister = pytest.importorskip("firebase_messaging.fcmregister")
    sessions = []

    async def refused_register(self):
        sessions.append(self._session)  # opens the register's own session
        raise RuntimeError(
            "Unable to establish subscription with Google Cloud Messaging."
        )

    monkeypatch.setattr(fcmregister.FcmRegister, "register", refused_register)
    m = _make("cupra_seat_fcm", "CupraSeatPushManager", {"brand": "cupra"})
    with pytest.raises(RuntimeError, match="Google Cloud Messaging"):
        await m._connect_and_listen()
    assert len(sessions) == 1
    assert sessions[0].closed


# ---------------------------------------------------------------------------
# Part 4: edges of the executor await and of the cleanup (review findings).
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(("module", "cls", "extra", "libs"), _MANAGERS, ids=_IDS)
async def test_stop_then_restart_during_the_check_spawns_one_loop(
    module, cls, extra, libs, monkeypatch
):
    """start(), stop(), start() while the first check still waits: both
    starts resume with the state STARTING, and only the newer may spawn."""
    m = _make(module, cls, extra)
    release = threading.Event()
    entered: list[int] = []

    def slow_check() -> None:
        entered.append(1)
        release.wait(timeout=5)

    loops: list[bool] = []

    async def record_loop() -> None:
        loops.append(True)
        await m._stop_event.wait()

    monkeypatch.setattr(m, "_lazy_check_dependencies", slow_check)
    monkeypatch.setattr(m, "_run_loop", record_loop)

    first = asyncio.create_task(m.start())
    for _ in range(200):
        if entered:
            break
        await asyncio.sleep(0.01)
    await m.stop()
    second = asyncio.create_task(m.start())
    for _ in range(200):
        if len(entered) == 2:
            break
        await asyncio.sleep(0.01)
    assert len(entered) == 2
    release.set()
    await asyncio.gather(first, second)
    await asyncio.sleep(0.01)
    try:
        assert loops == [True]
        assert m._loop_task is not None
    finally:
        await m.stop()


@pytest.mark.parametrize(("module", "cls", "extra", "libs"), _MANAGERS, ids=_IDS)
async def test_a_start_cancelled_during_the_check_does_not_block_the_next(
    module, cls, extra, libs, monkeypatch
):
    m = _make(module, cls, extra)
    release = threading.Event()
    entered = threading.Event()

    def slow_check() -> None:
        entered.set()
        release.wait(timeout=5)

    monkeypatch.setattr(m, "_lazy_check_dependencies", slow_check)
    starting = asyncio.create_task(m.start())
    for _ in range(200):
        if entered.is_set():
            break
        await asyncio.sleep(0.01)
    starting.cancel()
    with pytest.raises(asyncio.CancelledError):
        await starting
    release.set()
    assert m._state == PushManagerState.STOPPED

    async def no_network() -> None:
        await m._stop_event.wait()

    monkeypatch.setattr(m, "_lazy_check_dependencies", lambda: None)
    monkeypatch.setattr(m, "_run_loop", no_network)
    await m.start()
    try:
        assert m._loop_task is not None
    finally:
        await m.stop()


async def test_a_failing_register_close_keeps_the_original_error(
    fake_firebase, monkeypatch
):
    """A close() that raises must neither replace the registration error
    nor leave the client referenced."""

    async def broken_close(self) -> None:
        raise OSError("close failed")

    monkeypatch.setattr(_FakeRegister, "close", broken_close)
    m = _make("cupra_seat_fcm", "CupraSeatPushManager", {"brand": "cupra"})
    with pytest.raises(RuntimeError, match="Google Cloud Messaging"):
        await m._connect_and_listen()
    assert m._fcm_client is None
