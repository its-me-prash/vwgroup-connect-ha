# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""v4.4.0 (#968) — the companion agent relay.

The relay is the first companion transport where the PHONE opens the
connection, which removes wireless-debugging pairing, a fixed phone IP and
client-isolated Wi-Fi from the requirements. That inversion is also what makes
it worth testing hard: the endpoint is unauthenticated in Home Assistant's sense
and gated only by a token, and a command that goes to the wrong entry would
drive the wrong car's app.

Covered here:

- the rendezvous itself: a command waits for the agent's poll, the agent's
  answer completes it, and a stale answer to a timed-out command is dropped;
- the failure modes that must not hang: no agent, agent died mid-command,
  broker shut down under a waiting caller;
- token resolution, including the fail-closed duplicate-token case;
- the transport's verb mapping, and its refusal to pretend it has a shell.
"""
from __future__ import annotations

import asyncio

import pytest

from custom_components.vag_connect.companion.relay import (
    KNOWN_VERBS,
    CompanionRelayBroker,
)
from custom_components.vag_connect.companion.relay_transport import AgentRelayTransport
from custom_components.vag_connect.companion.transport import CompanionTransportError

_XML = '<?xml version="1.0"?><hierarchy rotation="0"></hierarchy>'


def _broker(hold_s: float = 0.05) -> CompanionRelayBroker:
    return CompanionRelayBroker("t" * 32, hold_s=hold_s)


async def _answer(broker: CompanionRelayBroker, value: object, **extra: object) -> dict:
    """Play one agent poll: collect the command, then hand back its result."""
    command = await broker.handle_poll({"agent_version": "1.0.0", **extra})
    assert command is not None
    await broker.handle_poll({"result": {"id": command["id"], "ok": True, "value": value}})
    return command


class TestRendezvous:
    @pytest.mark.asyncio
    async def test_command_is_delivered_and_its_result_returned(self) -> None:
        broker = _broker()
        task = asyncio.create_task(broker.command("dump_ui"))
        await asyncio.sleep(0)
        command = await _answer(broker, _XML)
        assert command["verb"] == "dump_ui"
        assert await task == _XML

    @pytest.mark.asyncio
    async def test_a_command_queued_before_the_poll_is_picked_up(self) -> None:
        # The phone polls on its own schedule, so a command routinely lands in
        # the slot while no poll is open. It must survive until the next one.
        broker = _broker()
        task = asyncio.create_task(broker.command("back"))
        await asyncio.sleep(0.01)
        command = await broker.handle_poll({})
        assert command is not None and command["verb"] == "back"
        await broker.handle_poll({"result": {"id": command["id"], "ok": True}})
        assert await task is None

    @pytest.mark.asyncio
    async def test_idle_poll_returns_no_command_after_the_hold_window(self) -> None:
        broker = _broker(hold_s=0.02)
        assert await broker.handle_poll({"agent_version": "1.0.0"}) is None

    @pytest.mark.asyncio
    async def test_agent_failure_surfaces_as_a_transport_error(self) -> None:
        broker = _broker()
        task = asyncio.create_task(broker.command("tap", {"x": 1, "y": 2}))
        await asyncio.sleep(0)
        command = await broker.handle_poll({})
        assert command is not None
        await broker.handle_poll(
            {"result": {"id": command["id"], "ok": False, "error": "no such node"}}
        )
        with pytest.raises(CompanionTransportError, match="no such node"):
            await task

    @pytest.mark.asyncio
    async def test_no_agent_times_out_instead_of_hanging(self) -> None:
        broker = _broker()
        with pytest.raises(CompanionTransportError, match="did not answer"):
            await broker.command("dump_ui", timeout_s=0.05)

    @pytest.mark.asyncio
    async def test_a_timed_out_command_is_withdrawn_not_left_to_be_tapped_later(
        self,
    ) -> None:
        # A tap that arrives minutes late lands on a screen that has moved on,
        # so an unclaimed command must not survive its own timeout.
        broker = _broker()
        with pytest.raises(CompanionTransportError):
            await broker.command("tap", {"x": 1, "y": 2}, timeout_s=0.05)
        assert await broker.handle_poll({}) is None

    @pytest.mark.asyncio
    async def test_a_late_answer_to_a_dead_command_is_ignored(self) -> None:
        broker = _broker()
        with pytest.raises(CompanionTransportError):
            await broker.command("dump_ui", timeout_s=0.05)
        # No raise, no crash: the future is long gone.
        await broker.handle_poll({"result": {"id": "c1", "ok": True, "value": _XML}})

    @pytest.mark.asyncio
    async def test_shutdown_fails_a_waiting_caller_rather_than_hanging(self) -> None:
        broker = _broker()
        task = asyncio.create_task(broker.command("dump_ui", timeout_s=5))
        await asyncio.sleep(0)
        broker.close()
        with pytest.raises(CompanionTransportError, match="shut down"):
            await task
        with pytest.raises(CompanionTransportError, match="shut down"):
            await broker.command("dump_ui")

    @pytest.mark.asyncio
    async def test_heartbeat_fields_are_recorded_and_bounded(self) -> None:
        broker = _broker(hold_s=0.01)
        await broker.handle_poll(
            {"agent_version": "1.2.3", "app_version": "4.3.2", "battery": 58}
        )
        assert (broker.agent_version, broker.app_version) == ("1.2.3", "4.3.2")
        assert broker.phone_battery == 58
        # Junk from an untrusted device must not land in the sensor.
        await broker.handle_poll({"battery": 900})
        await broker.handle_poll({"battery": "full"})
        assert broker.phone_battery == 58

    @pytest.mark.asyncio
    async def test_online_only_after_an_agent_actually_calls_in(self) -> None:
        broker = _broker(hold_s=0.01)
        assert broker.online is False
        with pytest.raises(CompanionTransportError, match="no companion agent"):
            await broker.wait_online(0.05)
        await broker.handle_poll({})
        assert broker.online is True
        await broker.wait_online(0.05)  # returns immediately


class TestTokenResolution:
    """``broker_for_token`` is the whole authentication story, so it gets tested
    like one."""

    @staticmethod
    def _hass(brokers: dict[str, CompanionRelayBroker]) -> object:
        class _Hass:
            data = {"vag_connect_companion_relays": brokers}

        return _Hass()

    def test_exact_token_resolves(self) -> None:
        from custom_components.vag_connect.companion.relay import broker_for_token

        broker = _broker()
        hass = self._hass({"entry1": broker})
        assert broker_for_token(hass, "t" * 32) is broker  # type: ignore[arg-type]

    def test_wrong_empty_and_prefix_tokens_do_not_resolve(self) -> None:
        from custom_components.vag_connect.companion.relay import broker_for_token

        hass = self._hass({"entry1": _broker()})
        for supplied in ("", "x" * 32, "t" * 31, "t" * 33):
            assert broker_for_token(hass, supplied) is None  # type: ignore[arg-type]

    def test_duplicate_token_fails_closed(self) -> None:
        # Two entries sharing a token must bind to NEITHER: picking one would
        # drive the wrong vehicle's app.
        from custom_components.vag_connect.companion.relay import broker_for_token

        hass = self._hass({"entry1": _broker(), "entry2": _broker()})
        assert broker_for_token(hass, "t" * 32) is None  # type: ignore[arg-type]

    def test_a_closed_broker_no_longer_answers_for_its_token(self) -> None:
        from custom_components.vag_connect.companion.relay import broker_for_token

        broker = _broker()
        broker.close()
        hass = self._hass({"entry1": broker})
        assert broker_for_token(hass, "t" * 32) is None  # type: ignore[arg-type]


class TestRelayTransport:
    @pytest.mark.asyncio
    async def test_dump_tap_and_back_map_onto_verbs(self) -> None:
        broker = _broker()
        transport = AgentRelayTransport(broker)

        task = asyncio.create_task(transport.dump_ui())
        await asyncio.sleep(0)
        assert (await _answer(broker, _XML))["verb"] == "dump_ui"
        assert await task == _XML

        task = asyncio.create_task(transport.tap(11, 22))
        await asyncio.sleep(0)
        command = await _answer(broker, None)
        assert command["verb"] == "tap"
        assert command["args"] == {"x": 11, "y": 22}
        await task

        task = asyncio.create_task(transport.key_back())
        await asyncio.sleep(0)
        assert (await _answer(broker, None))["verb"] == "back"
        await task

    @pytest.mark.asyncio
    async def test_app_version_returns_none_on_failure_so_taps_stay_disabled(
        self,
    ) -> None:
        # The channel treats an unknown app version as "do not tap", which is
        # the safe outcome; a raise here would instead fail the whole poll.
        broker = _broker()
        transport = AgentRelayTransport(broker)
        broker.close()
        assert await transport.current_app_version("com.volkswagen.weconnect") is None

    @pytest.mark.asyncio
    async def test_shell_is_refused_rather_than_silently_broken(self) -> None:
        transport = AgentRelayTransport(_broker())
        with pytest.raises(CompanionTransportError, match="not a shell"):
            await transport.shell("echo hi")

    @pytest.mark.asyncio
    async def test_sleep_after_read_is_opt_in_and_never_fails_a_poll(self) -> None:
        broker = _broker()
        off = AgentRelayTransport(broker, wake_sleep=False)
        await off.sleep_if_enabled()  # no command issued at all

        on = AgentRelayTransport(broker, wake_sleep=True)
        broker.close()
        await on.sleep_if_enabled()  # swallowed, not raised

    @pytest.mark.asyncio
    async def test_connect_waits_for_the_agent_then_reports_connected(self) -> None:
        broker = _broker(hold_s=0.01)
        transport = AgentRelayTransport(broker)
        assert transport.connected is False
        with pytest.raises(CompanionTransportError):
            await transport.connect(timeout_s=0.05)
        await broker.handle_poll({})
        await transport.connect(timeout_s=0.05)
        assert transport.connected is True
        await transport.close()
        assert transport.connected is False

    @pytest.mark.asyncio
    async def test_unknown_verbs_are_refused_before_they_reach_the_phone(self) -> None:
        with pytest.raises(CompanionTransportError, match="unknown companion agent"):
            await _broker().command("install_apk")

    def test_every_verb_the_transport_sends_is_in_the_allow_list(self) -> None:
        assert {
            "dump_ui", "tap", "swipe", "back", "foreground",
            "is_foreground", "app_version", "wake", "sleep",
        } == set(KNOWN_VERBS)


class _Request:
    """The parts of an aiohttp request the endpoint touches."""

    def __init__(self, token: str, body: object = None, *, bad_json: bool = False):
        self.headers = {"X-Agent-Token": token} if token else {}
        self._body = body if body is not None else {}
        self._bad_json = bad_json

    async def json(self) -> object:
        if self._bad_json:
            raise ValueError("not json")
        return self._body


class TestEndpoint:
    """The HTTP surface. It is unauthenticated in HA's sense, so what it does
    with a wrong token is the security boundary."""

    @staticmethod
    def _hass(brokers: dict[str, CompanionRelayBroker]) -> object:
        class _Hass:
            data = {"vag_connect_companion_relays": brokers}

        return _Hass()

    @pytest.mark.asyncio
    async def test_a_valid_poll_gets_its_command(self) -> None:
        from custom_components.vag_connect.companion.relay import handle_agent_request

        broker = _broker(hold_s=5)
        hass = self._hass({"entry1": broker})
        task = asyncio.create_task(broker.command("back", timeout_s=5))
        await asyncio.sleep(0)
        status, body = await handle_agent_request(
            hass, _Request("t" * 32, {"agent_version": "1.0.0"})  # type: ignore[arg-type]
        )
        assert status == 200
        assert body["command"]["verb"] == "back"
        await handle_agent_request(
            hass,  # type: ignore[arg-type]
            _Request("t" * 32, {"result": {"id": body["command"]["id"], "ok": True}}),
        )
        await task

    @pytest.mark.asyncio
    async def test_wrong_token_is_404_and_never_reaches_a_broker(self) -> None:
        from custom_components.vag_connect.companion.relay import handle_agent_request

        broker = _broker(hold_s=5)
        hass = self._hass({"entry1": broker})
        status, body = await handle_agent_request(
            hass, _Request("x" * 32, {"battery": 10})  # type: ignore[arg-type]
        )
        assert status == 404
        assert "unknown agent token" in body["error"]
        # The rejected poll must not have registered as a heartbeat either.
        assert broker.phone_battery is None
        assert broker.online is False

    @pytest.mark.asyncio
    async def test_missing_token_is_refused_the_same_way(self) -> None:
        from custom_components.vag_connect.companion.relay import handle_agent_request

        hass = self._hass({"entry1": _broker()})
        status, _ = await handle_agent_request(hass, _Request(""))  # type: ignore[arg-type]
        assert status == 404

    @pytest.mark.asyncio
    async def test_malformed_bodies_are_rejected_not_crashed_on(self) -> None:
        from custom_components.vag_connect.companion.relay import handle_agent_request

        hass = self._hass({"entry1": _broker(hold_s=0.01)})
        status, _ = await handle_agent_request(
            hass, _Request("t" * 32, bad_json=True)  # type: ignore[arg-type]
        )
        assert status == 400
        status, _ = await handle_agent_request(
            hass, _Request("t" * 32, ["not", "a", "dict"])  # type: ignore[arg-type]
        )
        assert status == 400

    @pytest.mark.asyncio
    async def test_an_idle_poll_answers_with_a_null_command(self) -> None:
        from custom_components.vag_connect.companion.relay import handle_agent_request

        hass = self._hass({"entry1": _broker(hold_s=0.02)})
        status, body = await handle_agent_request(
            hass, _Request("t" * 32, {})  # type: ignore[arg-type]
        )
        assert (status, body) == (200, {"command": None})
