# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#968 Phase 1 — the companion channel can run through the ADB Bridge add-on.

Android 11+ only offers wireless debugging (TLS + SPAKE2 pairing), which the
pure-python transport cannot speak: it reaches the port and fails. The add-on
bundles the real adb binary and exposes ``/health`` and ``/shell``, so the
integration talks HTTP to it instead of ADB to the phone.

The point of the design is that ONLY the four connection primitives change.
``dump_ui``, ``foreground_app``, ``tap``, ``wake`` and the write quarantine are
all built on ``shell()`` in the base class, so they are inherited untouched and
the screen layer never learns which transport it got.
"""
from __future__ import annotations

import asyncio
from typing import Any

import pytest

from custom_components.vag_connect.companion.addon_transport import (
    AddOnAdbTransport,
    probe_addon,
)
from custom_components.vag_connect.companion.transport import (
    CompanionTransportError,
    NetworkAdbTransport,
)


class _Resp:
    def __init__(self, status: int, payload: Any = None) -> None:
        self.status = status
        self._payload = payload

    async def json(self, content_type: Any = None) -> Any:
        return self._payload

    async def __aenter__(self) -> _Resp:
        return self

    async def __aexit__(self, *_a: Any) -> bool:
        return False


class _Session:
    """Records calls and replays queued responses."""

    def __init__(self, health: Any = None, shell: Any = None) -> None:
        self._health = health
        self._shell = shell
        self.calls: list[tuple[str, str, dict]] = []

    def get(self, url: str, **kw: Any) -> Any:
        self.calls.append(("GET", url, kw))
        if isinstance(self._health, Exception):
            raise self._health
        return self._health

    def post(self, url: str, **kw: Any) -> Any:
        self.calls.append(("POST", url, kw))
        if isinstance(self._shell, Exception):
            raise self._shell
        return self._shell

    async def close(self) -> None:
        return None


def _t(session: _Session, token: str = "") -> AddOnAdbTransport:
    return AddOnAdbTransport("1.2.3.4", 8129, token=token, session=session)


class TestConnect:
    def test_connect_succeeds_when_the_addon_has_a_phone(self) -> None:
        sess = _Session(health=_Resp(200, {"connected": True, "serial": "ph:1"}))
        t = _t(sess)
        asyncio.run(t.connect())
        assert t.connected is True
        assert "/health" in sess.calls[0][1]

    def test_addon_without_a_phone_is_a_clear_error(self) -> None:
        sess = _Session(health=_Resp(200, {"connected": False, "last_error": "no phone found"}))
        t = _t(sess)
        with pytest.raises(CompanionTransportError, match="no phone"):
            asyncio.run(t.connect())
        assert t.connected is False

    def test_bad_token_names_the_token(self) -> None:
        sess = _Session(health=_Resp(403, {}))
        with pytest.raises(CompanionTransportError, match="token"):
            asyncio.run(_t(sess, token="wrong").connect())

    def test_unreachable_addon_points_at_the_addon(self) -> None:
        sess = _Session(health=OSError("refused"))
        with pytest.raises(CompanionTransportError, match="add-on"):
            asyncio.run(_t(sess).connect())

    def test_token_is_sent_when_configured(self) -> None:
        sess = _Session(health=_Resp(200, {"connected": True, "serial": "s"}))
        asyncio.run(_t(sess, token="secret").connect())
        assert sess.calls[0][2]["headers"]["X-Token"] == "secret"

    def test_no_token_header_when_blank(self) -> None:
        sess = _Session(health=_Resp(200, {"connected": True, "serial": "s"}))
        asyncio.run(_t(sess).connect())
        assert "X-Token" not in sess.calls[0][2]["headers"]


class TestShell:
    def _connected(self, shell_resp: Any) -> tuple[AddOnAdbTransport, _Session]:
        sess = _Session(
            health=_Resp(200, {"connected": True, "serial": "s"}), shell=shell_resp
        )
        t = _t(sess)
        asyncio.run(t.connect())
        return t, sess

    def test_shell_returns_stdout(self) -> None:
        t, sess = self._connected(_Resp(200, {"stdout": "ok\n", "stderr": "", "rc": 0}))
        assert asyncio.run(t.shell("echo ok")) == "ok\n"
        assert sess.calls[-1][0] == "POST"
        assert "/shell" in sess.calls[-1][1]

    def test_nonzero_exit_is_not_an_error(self) -> None:
        """grep with no match and rm -f on a missing file both exit non-zero
        as a normal outcome; the callers judge the output, exactly as over
        raw ADB."""
        t, _ = self._connected(_Resp(200, {"stdout": "", "stderr": "", "rc": 1}))
        assert asyncio.run(t.shell("grep nothing")) == ""

    def test_phone_lost_mid_session_marks_disconnected(self) -> None:
        t, _ = self._connected(_Resp(503, {"error": "phone not connected"}))
        with pytest.raises(CompanionTransportError):
            asyncio.run(t.shell("echo hi"))
        assert t.connected is False  # so the channel reconnects next time

    def test_shell_before_connect_raises(self) -> None:
        sess = _Session()
        with pytest.raises(CompanionTransportError, match="not connected"):
            asyncio.run(_t(sess).shell("echo hi"))


class TestInheritedBehaviour:
    """The whole point: everything above shell() is untouched."""

    def test_it_is_a_network_transport(self) -> None:
        assert issubclass(AddOnAdbTransport, NetworkAdbTransport)

    def test_dump_ui_runs_the_same_commands_over_http(self) -> None:
        """dump_ui is inherited, so it must work unchanged through the add-on:
        remove the stale dump, run uiautomator, cat the file back."""
        xml = '<?xml version="1.0"?><hierarchy rotation="0"></hierarchy>'
        sess = _Session(
            health=_Resp(200, {"connected": True, "serial": "s"}),
            shell=_Resp(200, {"stdout": xml, "stderr": "", "rc": 0}),
        )
        t = _t(sess)
        asyncio.run(t.connect())
        assert "<hierarchy" in asyncio.run(t.dump_ui())
        posts = [c for c in sess.calls if c[0] == "POST"]
        assert len(posts) == 3  # rm, uiautomator dump, cat
        assert b"uiautomator dump" in posts[1][2]["data"]

    def test_a_failed_dump_is_still_honest(self) -> None:
        """The stale-dump guard is inherited too: no hierarchy means no data,
        never a silently reused previous screen."""
        sess = _Session(
            health=_Resp(200, {"connected": True, "serial": "s"}),
            shell=_Resp(200, {"stdout": "", "stderr": "", "rc": 0}),
        )
        t = _t(sess)
        asyncio.run(t.connect())
        with pytest.raises(CompanionTransportError):
            asyncio.run(t.dump_ui())


class TestProbe:
    def test_probe_reports_ok(self) -> None:
        sess = _Session(health=_Resp(200, {"connected": True, "serial": "s"}))
        ok, reason = asyncio.run(probe_addon("1.2.3.4", 8129, "", session=sess))
        assert ok is True and reason == ""

    def test_probe_never_raises(self) -> None:
        sess = _Session(health=OSError("boom"))
        ok, reason = asyncio.run(probe_addon("1.2.3.4", 8129, "", session=sess))
        assert ok is False and reason
