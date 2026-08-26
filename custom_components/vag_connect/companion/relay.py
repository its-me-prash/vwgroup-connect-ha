# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Outbound relay for a companion agent app — v4.4.0, EXPERIMENTAL.

Why this exists (#968). Both existing companion transports need Home Assistant
to reach INTO the phone: the direct one opens a TCP ADB socket to it, and the
add-on one drives a real ``adb`` binary that does the same. That is where users
get stuck. Android 11+ wireless debugging has to be re-paired by hand, the
debugging toggle switches itself off, phone IPs move under DHCP, and a guest or
IoT SSID with client isolation blocks the connection outright.

The relay inverts the direction. A small agent app on the phone opens an
ordinary outbound HTTPS request to Home Assistant and holds it; HA answers with
the next command when it has one, and the agent posts the result back on its
next poll. Nothing has to reach the phone, so NAT, changing IPs, client
isolation and wireless debugging all stop mattering.

What crosses the wire is a short list of high-level verbs (dump the visible
screen, tap a point, press BACK, bring the app forward, report the app version),
NOT a shell. A non-rooted phone cannot run shell commands anyway, and keeping
the vocabulary this narrow means a compromised HA cannot ask the agent for
anything beyond what the companion channel already does.

Security model:

- The endpoint is unauthenticated in HA's sense (``requires_auth = False``)
  because the phone has no HA user, and is protected instead by a random
  per-entry token that the agent sends in a header. It is compared with
  ``hmac.compare_digest``, never logged, and redacted in diagnostics.
- A token resolves to exactly ONE entry. If two entries somehow carry the same
  token the lookup fails closed rather than binding the phone to an arbitrary
  car — a wrong binding would drive the wrong vehicle's app.
- The agent is never handed the config-entry id, so nothing internal to HA
  leaks to the device.

The phone-side agent is a separate artifact; ``docs/COMPANION_AGENT.md``
specifies the protocol so it can be implemented (and re-implemented) against
this file alone.
"""
from __future__ import annotations

import asyncio
import hmac
import logging
from typing import TYPE_CHECKING, Any

from .transport import CompanionTransportError

if TYPE_CHECKING:  # pragma: no cover - typing only
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

_REGISTRY_KEY = "vag_connect_companion_relays"
_VIEW_REGISTERED_KEY = "vag_connect_companion_relay_view"

# How long HA holds an agent's poll open before answering "nothing to do". Short
# enough to stay well inside any reverse proxy's read timeout, long enough that
# an idle phone is not re-connecting every other second.
_HOLD_S = 25.0

# The verbs an agent must implement. Anything else is refused before it reaches
# the device, so a future HA-side bug cannot ask a phone to do something outside
# this list.
KNOWN_VERBS = frozenset(
    {
        "dump_ui",
        "tap",
        "swipe",
        "back",
        "foreground",
        "is_foreground",
        "app_version",
        "wake",
        "sleep",
    }
)

# A token below this length is refused at setup: it is the only thing standing
# between the open endpoint and a phone binding.
MIN_TOKEN_LEN = 32


class CompanionRelayBroker:
    """One config entry's rendezvous point between HA and its agent.

    The companion channel drives one command at a time (it dumps, decides, then
    taps), so the broker holds a single command slot rather than a queue. That
    also makes the poll path race-free: a command left in the slot when a poll
    times out is simply picked up by the next poll.
    """

    def __init__(self, token: str, *, hold_s: float = _HOLD_S) -> None:
        self._token = token
        self._hold_s = hold_s
        self._slot: dict[str, Any] | None = None
        self._slot_ready = asyncio.Event()
        self._pending: dict[str, asyncio.Future[Any]] = {}
        self._lock = asyncio.Lock()
        self._seq = 0
        self._online = asyncio.Event()
        # Last heartbeat the agent reported. Read by diagnostics; the token is
        # never part of it.
        self.agent_version: str | None = None
        self.app_version: str | None = None
        self.phone_battery: int | None = None
        self.closed = False

    @property
    def token(self) -> str:
        return self._token

    @property
    def online(self) -> bool:
        """True once an agent has polled at least once since setup."""
        return self._online.is_set()

    async def wait_online(self, timeout_s: float) -> None:
        """Block until an agent polls, or raise a transport error.

        Used by ``connect()``: with no socket to open, "connected" means an
        agent is actually calling in.
        """
        if self._online.is_set():
            return
        try:
            await asyncio.wait_for(self._online.wait(), timeout_s)
        except (TimeoutError, asyncio.TimeoutError) as err:
            raise CompanionTransportError(
                "no companion agent has called in yet; check that the agent app "
                "is running on the phone, that its Home Assistant URL is "
                "reachable from the phone, and that its token matches this entry"
            ) from err

    # -- HA side --------------------------------------------------------------

    async def command(
        self, verb: str, args: dict[str, Any] | None = None, *, timeout_s: float = 20.0
    ) -> Any:
        """Hand one verb to the agent and wait for its result.

        Serialised: the companion channel never has two commands in flight, and
        the single slot enforces it rather than trusting the caller.
        """
        if verb not in KNOWN_VERBS:  # pragma: no cover - guarded at call sites
            raise CompanionTransportError(f"unknown companion agent verb: {verb}")
        if self.closed:
            raise CompanionTransportError("the companion relay is shut down")
        async with self._lock:
            self._seq += 1
            cid = f"c{self._seq}"
            loop = asyncio.get_running_loop()
            fut: asyncio.Future[Any] = loop.create_future()
            self._pending[cid] = fut
            self._slot = {"id": cid, "verb": verb, "args": args or {}}
            self._slot_ready.set()
            try:
                return await asyncio.wait_for(fut, timeout_s)
            except (TimeoutError, asyncio.TimeoutError) as err:
                raise CompanionTransportError(
                    f"the companion agent did not answer '{verb}' within "
                    f"{int(timeout_s)}s; the phone may be asleep, offline or the "
                    "agent app stopped"
                ) from err
            finally:
                self._pending.pop(cid, None)
                # Drop an unclaimed command so a dead agent cannot pick up a
                # stale tap minutes later, on a screen that has moved on.
                if self._slot is not None and self._slot.get("id") == cid:
                    self._slot = None
                    self._slot_ready.clear()

    def close(self) -> None:
        """Tear the broker down and fail anything still waiting."""
        self.closed = True
        self._slot = None
        self._slot_ready.clear()
        for fut in list(self._pending.values()):
            if not fut.done():
                fut.set_exception(
                    CompanionTransportError("the companion relay was shut down")
                )
        self._pending.clear()

    # -- agent side -----------------------------------------------------------

    async def handle_poll(self, payload: dict[str, Any]) -> dict[str, Any] | None:
        """Take an agent's poll: record its result and heartbeat, hand back work.

        Returns the next command, or None when the hold window elapsed with
        nothing to do (the agent then polls again).
        """
        self._online.set()
        self._note_heartbeat(payload)
        self._resolve_result(payload.get("result"))
        if self._slot is None:
            try:
                await asyncio.wait_for(self._slot_ready.wait(), self._hold_s)
            except (TimeoutError, asyncio.TimeoutError):
                return None
        command = self._slot
        self._slot = None
        self._slot_ready.clear()
        return command

    def _note_heartbeat(self, payload: dict[str, Any]) -> None:
        agent = payload.get("agent_version")
        if isinstance(agent, str):
            self.agent_version = agent[:64]
        app = payload.get("app_version")
        if isinstance(app, str):
            self.app_version = app[:64]
        battery = payload.get("battery")
        if isinstance(battery, int) and 0 <= battery <= 100:
            self.phone_battery = battery

    def _resolve_result(self, result: Any) -> None:
        """Complete the waiting command with the agent's answer, if any."""
        if not isinstance(result, dict):
            return
        fut = self._pending.get(str(result.get("id") or ""))
        if fut is None or fut.done():
            # A late answer to a command that already timed out. Dropping it is
            # correct: the caller has moved on and the screen with it.
            return
        if result.get("ok", True):
            fut.set_result(result.get("value"))
        else:
            fut.set_exception(
                CompanionTransportError(
                    str(result.get("error") or "the companion agent reported a failure")
                )
            )


# ── registry ────────────────────────────────────────────────────────────────


def _registry(hass: HomeAssistant) -> dict[str, CompanionRelayBroker]:
    return hass.data.setdefault(_REGISTRY_KEY, {})  # type: ignore[no-any-return]


def register_relay(
    hass: HomeAssistant, entry_id: str, token: str, *, hold_s: float = _HOLD_S
) -> CompanionRelayBroker:
    """Create (or replace) the broker for one entry and make sure the view is up."""
    registry = _registry(hass)
    existing = registry.pop(entry_id, None)
    if existing is not None:
        existing.close()
    broker = CompanionRelayBroker(token, hold_s=hold_s)
    registry[entry_id] = broker
    ensure_relay_view(hass)
    return broker


def unregister_relay(hass: HomeAssistant, entry_id: str) -> None:
    """Drop an entry's broker (entry unload/reload)."""
    broker = _registry(hass).pop(entry_id, None)
    if broker is not None:
        broker.close()


def broker_for_token(
    hass: HomeAssistant, supplied: str
) -> CompanionRelayBroker | None:
    """Resolve exactly one broker by token, or None.

    A duplicate token resolves to nothing on purpose: binding a phone to an
    arbitrary one of two cars would drive the wrong vehicle's app.
    """
    if not supplied:
        return None
    matches = [
        broker
        for broker in _registry(hass).values()
        if not broker.closed and hmac.compare_digest(supplied, broker.token)
    ]
    if len(matches) != 1:
        if len(matches) > 1:
            _LOGGER.error(
                "companion relay: two entries share one agent token; refusing to "
                "bind the phone to either. Give each companion entry its own token."
            )
        return None
    return matches[0]


AGENT_URL = "/api/vag_connect/companion_agent"
AGENT_TOKEN_HEADER = "X-Agent-Token"


async def handle_agent_request(hass: "HomeAssistant", request: Any) -> tuple[int, dict]:
    """The endpoint's whole behaviour, as a plain function.

    Kept out of the view class so it can be tested without Home Assistant
    installed — the same reason the screen parser lives apart from the ADB
    transport. Returns (status, json body).
    """
    supplied = request.headers.get(AGENT_TOKEN_HEADER, "")
    broker = broker_for_token(hass, supplied)
    if broker is None:
        # Same answer for "wrong token" and "no such entry": an unauthorised
        # caller learns nothing about which tokens exist.
        return 404, {"error": "unknown agent token"}
    try:
        payload = await request.json()
    except Exception:  # noqa: BLE001 - untrusted device input
        return 400, {"error": "invalid json"}
    if not isinstance(payload, dict):
        return 400, {"error": "invalid payload"}
    command = await broker.handle_poll(payload)
    return 200, {"command": command}


def ensure_relay_view(hass: "HomeAssistant") -> None:
    """Register the agent view once per HA run.

    The view class is built here rather than at module import so this module
    stays importable (and testable) without Home Assistant present.
    """
    if hass.data.get(_VIEW_REGISTERED_KEY):
        return
    if getattr(hass, "http", None) is None:
        # Only reachable on an HA without the http component, which the
        # frontend itself requires. Say so plainly instead of failing later
        # with an AttributeError the user cannot act on.
        raise CompanionTransportError(
            "the companion agent relay needs Home Assistant's http component, "
            "which is not set up on this instance"
        )
    from homeassistant.components.http import HomeAssistantView  # noqa: PLC0415

    class CompanionAgentView(HomeAssistantView):  # type: ignore[misc]
        """The agent's long-poll endpoint. Open by necessity, token-gated in fact."""

        url = AGENT_URL
        name = "api:vag_connect:companion_agent"
        requires_auth = False

        async def post(self, request: Any) -> Any:
            status, body = await handle_agent_request(request.app["hass"], request)
            return self.json(body, status_code=status)

    hass.http.register_view(CompanionAgentView)
    hass.data[_VIEW_REGISTERED_KEY] = True
