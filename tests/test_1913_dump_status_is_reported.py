# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#1913 — the empty-dump error guessed, and threw away the answer.

@stephanlasso's phone was awake, unlocked and showing the app, and the read
still got no screen dump. The message offered him three causes — asleep, not in
the foreground, secured screen — and he had ruled out all three. Two defects,
both in one line of shell:

1. **The message omitted the cause this file already documents.**
   ``uiautomator dump`` gives up when the UI does not go idle, and a single
   animation or a transient toast is enough; the comment saying so sits two
   lines above the message that did not mention it. On a phone that is awake,
   unlocked and in the app, that is the only candidate left, and it matches the
   animated-advert case traced on #968.
2. **The command discarded the reason.** ``uiautomator dump`` prints its status
   — including *why* it gave up — to stdout, and the command sent that to
   ``/dev/null`` and read the file instead. In the one case where the reason is
   printed, it was thrown away and then guessed at.

The status now goes to its own file and is read back only when the dump has
failed twice. Its own file on purpose: mixing it into the same stdout would put
a status line in front of the XML on the **success** path, and that path feeds
a parser. The success output stays byte-identical to what it was.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from custom_components.vag_connect.companion import transport as tmod
from custom_components.vag_connect.companion.transport import (
    CompanionTransportError,
    NetworkAdbTransport,
)

_XML = '<?xml version="1.0"?><hierarchy rotation="0"><node index="0"/></hierarchy>'


def _transport(device: object) -> NetworkAdbTransport:
    t = NetworkAdbTransport("phone", 5555, "/k")
    t._device = device
    return t


@pytest.fixture(autouse=True)
def _no_retry_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    """The retry delay is real (1.5 s) and not what these tests are about."""
    monkeypatch.setattr(tmod, "_DUMP_RETRY_DELAY_S", 0.0)


# --------------------------------------------------------------------------
# Defect 2: the status is captured instead of discarded.
# --------------------------------------------------------------------------

def test_the_dump_command_no_longer_throws_the_status_away() -> None:
    seen: list[str] = []
    device = MagicMock()
    device.available = True

    def _shell(cmd: str, **_kw: object) -> str:
        seen.append(cmd)
        return _XML

    device.shell.side_effect = _shell
    import asyncio
    asyncio.run(_transport(device).dump_ui())

    assert seen, "no shell command was issued"
    cmd = seen[0]
    assert ">/dev/null" not in cmd, (
        "uiautomator's status is still being discarded: " + cmd
    )
    # It must not be merged into the XML stream either.
    assert "cat " in cmd and tmod._DUMP_PATH in cmd
    assert tmod._DUMP_STATUS_PATH in cmd, cmd
    # The rm that stops a failed dump returning the PREVIOUS run's XML has to
    # cover the new file too, or a stale status gets reported as this run's.
    rm = cmd.split(";")[0]
    assert tmod._DUMP_PATH in rm and tmod._DUMP_STATUS_PATH in rm, rm


def test_the_success_path_returns_only_the_xml() -> None:
    """The hot path feeds a parser; a status line in front of it is a bug."""
    device = MagicMock()
    device.available = True
    device.shell.return_value = _XML
    import asyncio
    assert asyncio.run(_transport(device).dump_ui()) == _XML


def test_a_successful_dump_does_not_read_the_status_file() -> None:
    """One round trip on the happy path, as before."""
    calls: list[str] = []
    device = MagicMock()
    device.available = True

    def _shell(cmd: str, **_kw: object) -> str:
        calls.append(cmd)
        return _XML

    device.shell.side_effect = _shell
    import asyncio
    asyncio.run(_transport(device).dump_ui())
    assert len(calls) == 1, calls
    assert not any(c.strip().startswith("cat " + tmod._DUMP_STATUS_PATH)
                   for c in calls), calls


# --------------------------------------------------------------------------
# Defect 1: the message names the cause the code documents.
# --------------------------------------------------------------------------

def _failing(status: str | None) -> MagicMock:
    """A device whose dump always fails; ``status`` is what the file holds."""
    device = MagicMock()
    device.available = True

    def _shell(cmd: str, **_kw: object) -> str:
        if cmd.strip().startswith("cat " + tmod._DUMP_STATUS_PATH):
            if status is None:
                raise OSError("status unreadable")
            return status
        return ""           # no <hierarchy> → the dump failed

    device.shell.side_effect = _shell
    return device


def test_the_message_names_the_idle_cause() -> None:
    import asyncio
    with pytest.raises(CompanionTransportError) as err:
        asyncio.run(_transport(_failing("")).dump_ui())
    msg = str(err.value)
    assert "idle" in msg.lower(), msg
    # and still names the three it always named
    for alt in ("asleep", "foreground", "secured"):
        assert alt in msg.lower(), (alt, msg)


def test_the_status_reaches_the_message() -> None:
    import asyncio
    with pytest.raises(CompanionTransportError) as err:
        asyncio.run(_transport(
            _failing("ERROR: could not get idle state.")).dump_ui())
    assert "could not get idle state" in str(err.value)


def test_the_status_is_reduced_to_one_short_line() -> None:
    """uiautomator can answer with a Java stack trace.

    ``_redact`` caps the whole exception message at 500 chars, so an unbounded
    status would push the message that matters out of the record — the same
    reasoning ``_BODY_MAX_LEN`` already applies to an HTTP body.
    """
    import asyncio
    lang = "ERROR: first line of many\n" + "\n".join(
        f"\tat android.something.Frame{i}" for i in range(40))
    with pytest.raises(CompanionTransportError) as err:
        asyncio.run(_transport(_failing(lang)).dump_ui())
    msg = str(err.value)
    assert "first line of many" in msg
    assert "Frame7" not in msg, "the whole stack trace rode along"
    assert "\n" not in msg, "the message is multi-line"
    assert len(msg) < 400, len(msg)


def test_an_unreadable_status_does_not_replace_the_real_error() -> None:
    """Reading the status is a nice-to-have; it must never become the failure."""
    import asyncio
    with pytest.raises(CompanionTransportError) as err:
        asyncio.run(_transport(_failing(None)).dump_ui())
    msg = str(err.value)
    assert "no screen dump twice" in msg, msg
    assert "status unreadable" not in msg, msg
    assert "idle" in msg.lower(), msg


def test_an_empty_status_adds_nothing_rather_than_an_empty_bracket() -> None:
    import asyncio
    with pytest.raises(CompanionTransportError) as err:
        asyncio.run(_transport(_failing("   \n  \n")).dump_ui())
    msg = str(err.value)
    assert "()" not in msg and "said:" not in msg, msg


# --------------------------------------------------------------------------
# The status is device text. It must not reach an unredacted channel.
# --------------------------------------------------------------------------

def test_the_raw_status_is_not_logged() -> None:
    """Only the exception message carries it.

    The Error Reporter runs ``_redact`` over the exception message (VINs,
    e-mails, JWTs, UUIDs, Bearer and opaque tokens), which is what makes it
    safe to publish. ``_LOGGER`` has no such filter, so a debug line with the
    raw status would be a second, unredacted copy.
    """
    import asyncio
    import logging
    records: list[str] = []

    class _Catch(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record.getMessage())

    handler = _Catch()
    tmod._LOGGER.addHandler(handler)
    tmod._LOGGER.setLevel(logging.DEBUG)
    try:
        with pytest.raises(CompanionTransportError):
            asyncio.run(_transport(
                _failing("ERROR: secret-looking WVWZZZAUZFW000000")).dump_ui())
    finally:
        tmod._LOGGER.removeHandler(handler)
    joined = "\n".join(records)
    assert "secret-looking" not in joined, joined
    assert "WVWZZZAUZFW000000" not in joined, joined
