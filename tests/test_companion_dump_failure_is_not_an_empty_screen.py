# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""A screen that could not be read is not a screen with nothing on it.

Two defects of one shape, found by reading our own transports against each
other rather than against a report.

**The relay had no dump guard at all.** ``NetworkAdbTransport.dump_ui``
refuses a dump with no ``<hierarchy`` in it, and the comment above that guard
says exactly why: ``uiautomator`` does not overwrite its output file on a
failed dump, so without the guard a frozen screen gets parsed as a live one.
``AgentRelayTransport.dump_ui`` overrode the method and returned
``str(value or "")``. The agent is a separate app on the phone, and it answers
``{"ok": true, "value": …}``; an agent that walks the accessibility tree and
finds no window — screen off, secured, app not foreground — can report success
with nothing in it. That empty string then parsed to zero nodes, which the read
path treats as a *successful* poll: the anchor gate is skipped (it is guarded
on ``nodes`` being non-empty), ``_consecutive_failures`` is reset to zero, and
``{}`` is returned, which the channel documents as "a genuine empty screen".
A failed read was therefore indistinguishable from a car that reported nothing,
in the log and in the backoff.

**And one transient dump failure cost half an hour of reads.** The failure
backoff is 30 minutes, doubling per consecutive failure to six hours. A single
dump that came back empty tripped it, with no retry. ``uiautomator dump`` waits
for the UI to go idle and gives up if it does not — an animation or a transient
toast is enough — and that is a condition a second attempt a moment later
resolves. Paying 30 minutes of blindness for it is the wrong trade.

The retry is deliberately only on the ADB side, and only for a dump that
returned nothing:

* A ``shell`` that *raises* has already dropped the device so the next read
  reconnects (``transport.py`` ``shell``); retrying it in place would only
  produce "not connected". It propagates unchanged.
* On the relay, one more attempt means another round trip through the agent's
  own poll, and the commonest empty-tree cause there — a screen the agent
  cannot see — does not change in the seconds a retry would take. It gets the
  missing guard, which turns a silent empty into an honest failure, and no
  retry.
"""
from __future__ import annotations

import asyncio

import pytest

from custom_components.vag_connect.companion import transport as _tr
from custom_components.vag_connect.companion.relay import CompanionRelayBroker
from custom_components.vag_connect.companion.relay_transport import (
    AgentRelayTransport,
)
from custom_components.vag_connect.companion.transport import (
    CompanionTransportError,
    NetworkAdbTransport,
)

_XML = '<?xml version="1.0"?><hierarchy rotation="0"><node text="x"/></hierarchy>'


# ── the relay: an empty answer is a failure, not an empty screen ────────────


def _broker() -> CompanionRelayBroker:
    return CompanionRelayBroker("t" * 32, hold_s=0.01)


async def _answer(broker: CompanionRelayBroker, value: object) -> dict:
    """Play one agent poll: collect the command, then hand back its result."""
    command = await broker.handle_poll({"agent_version": "1.0.0"})
    assert command is not None
    await broker.handle_poll(
        {"result": {"id": command["id"], "ok": True, "value": value}}
    )
    return command


@pytest.mark.asyncio
@pytest.mark.parametrize("value", [None, "", "   ", "not xml at all"])
async def test_relay_refuses_an_answer_with_no_screen_in_it(value: object) -> None:
    """An ``ok`` result carrying no hierarchy must raise, exactly as the ADB
    transport's own guard does. Before the fix each of these returned a string
    the channel parsed to zero nodes and reported as a healthy empty read."""
    broker = _broker()
    transport = AgentRelayTransport(broker)

    task = asyncio.create_task(transport.dump_ui())
    await asyncio.sleep(0)
    await _answer(broker, value)
    with pytest.raises(CompanionTransportError) as err:
        await task
    assert "screen" in str(err.value).lower()


@pytest.mark.asyncio
async def test_relay_still_returns_a_real_dump_unchanged() -> None:
    """The guard must not become a filter: a real answer passes through byte
    for byte, because every selector in the presets parses this string."""
    broker = _broker()
    transport = AgentRelayTransport(broker)

    task = asyncio.create_task(transport.dump_ui())
    await asyncio.sleep(0)
    await _answer(broker, _XML)
    assert await task == _XML


# ── the ADB side: one retry before half an hour of blindness ───────────────


class _Phone(NetworkAdbTransport):
    """A transport whose ``shell`` replays a scripted list of answers."""

    def __init__(self, answers: list[object]) -> None:
        super().__init__("1.2.3.4", 5555, "")
        self._answers = list(answers)
        self.calls: list[str] = []

    async def shell(self, cmd: str, timeout_s: float = 10.0) -> str:
        self.calls.append(cmd)
        if not self._answers:  # pragma: no cover - a test scripted too few
            raise AssertionError("shell called more often than the test scripted")
        nxt = self._answers.pop(0)
        if isinstance(nxt, BaseException):
            raise nxt
        return str(nxt)


@pytest.fixture(autouse=True)
def _no_real_sleeping(monkeypatch: pytest.MonkeyPatch) -> None:
    """The retry waits for the UI to settle; the test must not."""
    async def _instant(_seconds: float) -> None:
        return None

    monkeypatch.setattr(_tr.asyncio, "sleep", _instant)


def test_a_dump_that_comes_back_empty_is_retried_once() -> None:
    phone = _Phone(["", _XML])
    assert asyncio.run(phone.dump_ui()) == _XML
    assert len(phone.calls) == 2


def test_the_retry_repeats_the_whole_command_so_a_stale_file_cannot_be_read() -> None:
    """The dump command deletes the previous output FIRST (ckomma #20/#22):
    without that, ``cat`` returns the last successful run's XML and a frozen
    screen is parsed as live. The retry must re-run that same command, not just
    the ``cat``."""
    phone = _Phone(["", _XML])
    asyncio.run(phone.dump_ui())
    assert len(phone.calls) == 2
    for call in phone.calls:
        assert "rm -f" in call
        assert "uiautomator dump" in call
        assert call == phone.calls[0]


def test_two_empty_dumps_raise_and_the_message_says_it_tried_twice() -> None:
    phone = _Phone(["", ""])
    with pytest.raises(CompanionTransportError) as err:
        asyncio.run(phone.dump_ui())
    text = str(err.value).lower()
    assert "twice" in text
    # The diagnosis the old message carried is the useful half; keep it.
    assert "asleep" in text
    # Counted on the DUMP command, not on every shell call. #1913 added one
    # further call on this path — reading uiautomator's own status, which used
    # to go to /dev/null — and that is not a retry. A plain call count made
    # this fail for the wrong reason: the intent here is "one retry, not a
    # loop", and that intent is unchanged.
    dumps = [c for c in phone.calls if "uiautomator dump" in c]
    assert len(dumps) == 2, f"exactly one retry, not a loop: {phone.calls}"
    status_reads = [c for c in phone.calls
                    if c.strip().startswith("cat /sdcard/vag_connect_ui.status")]
    assert len(status_reads) == 1, (
        f"the reason is read exactly once, after the retry: {phone.calls}"
    )


def test_a_shell_that_raises_is_not_retried() -> None:
    """``shell`` drops the device and raises on a broken socket, so the next
    read reconnects. A retry in place would run with no device and report "not
    connected", hiding the real reason. It must propagate on the first throw."""
    boom = CompanionTransportError("the ADB connection to 1.2.3.4:5555 failed")
    phone = _Phone([boom, _XML])
    with pytest.raises(CompanionTransportError) as err:
        asyncio.run(phone.dump_ui())
    assert "connection" in str(err.value)
    assert len(phone.calls) == 1


def test_a_good_dump_costs_exactly_one_shell_round_trip() -> None:
    """The healthy path is every poll of every Companion user; the retry must
    not add a call to it."""
    phone = _Phone([_XML])
    assert asyncio.run(phone.dump_ui()) == _XML
    assert len(phone.calls) == 1
