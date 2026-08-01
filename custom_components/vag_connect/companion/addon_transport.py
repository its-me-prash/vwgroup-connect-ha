# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Companion transport that talks to the ADB Bridge add-on instead of a phone.

Why this exists: the direct transport (``NetworkAdbTransport``) speaks classic
ADB with the pure-python ``adb-shell`` library, which cannot do the TLS +
pairing handshake Android 11 and newer require for wireless debugging. On a
modern phone it reaches the port and fails. The add-on bundles the real ``adb``
binary, does the pairing, and exposes two endpoints:

    GET  /health  -> {"connected": bool, "serial": str|None, ...}
    POST /shell   -> body is a shell command, returns {"stdout", "stderr", "rc"}

Both take an ``X-Token`` header when the add-on has an ``api_token`` set.

Everything above the wire is unchanged: ``dump_ui``, ``foreground_app``,
``tap``, ``wake`` and the rest are all built on ``shell()`` in the base class,
so subclassing and replacing the four connection primitives is enough. The
screen parsing, the presets and the write quarantine never learn which
transport they are running on.
"""
from __future__ import annotations

import asyncio
import logging

from .transport import CompanionTransportError, NetworkAdbTransport

_LOGGER = logging.getLogger(__name__)

_DEFAULT_PORT = 8129


class AddOnAdbTransport(NetworkAdbTransport):
    """Runs shell commands through the add-on's local HTTP API."""

    def __init__(
        self,
        host: str,
        port: int = _DEFAULT_PORT,
        *,
        token: str = "",
        session: object | None = None,
        wake_sleep: bool = False,
    ) -> None:
        # The base class stores host/port and the wake_sleep opt-in; the adbkey
        # path is meaningless here (the add-on owns the key), so it is blank.
        super().__init__(host, port or _DEFAULT_PORT, "", wake_sleep=wake_sleep)
        self._token = token or ""
        self._session = session
        self._serial: str | None = None

    # -- helpers --------------------------------------------------------------

    @property
    def _base(self) -> str:
        return f"http://{self._host}:{self._port}"

    def _headers(self) -> dict[str, str]:
        return {"X-Token": self._token} if self._token else {}

    async def _get_session(self) -> object:
        if self._session is None:
            from aiohttp import ClientSession  # noqa: PLC0415

            self._session = ClientSession()
            self._owns_session = True
        return self._session

    # -- connection -----------------------------------------------------------

    async def connect(self, timeout_s: float = 10.0) -> None:
        """Ask the add-on whether it currently has a phone.

        There is no socket for us to open: the add-on holds the ADB connection.
        "Connected" therefore means the add-on reports a phone in device state,
        and the failure messages point at the add-on rather than at the phone,
        because that is where the user has to look.
        """
        from aiohttp import ClientError, ClientTimeout  # noqa: PLC0415

        session = await self._get_session()
        try:
            async with session.get(  # type: ignore[attr-defined]
                f"{self._base}/health",
                headers=self._headers(),
                timeout=ClientTimeout(total=timeout_s),
            ) as resp:
                if resp.status == 403:
                    raise CompanionTransportError(
                        "the add-on rejected the token; check that the token "
                        "here matches api_token in the add-on configuration"
                    )
                if resp.status >= 400:
                    raise CompanionTransportError(
                        f"the add-on answered HTTP {resp.status} on /health"
                    )
                payload = await resp.json(content_type=None)
        except (TimeoutError, ClientError, OSError) as err:
            raise CompanionTransportError(
                f"could not reach the ADB Bridge add-on at {self._base} "
                f"({type(err).__name__}); check the add-on is started and that "
                "the host and port match its configuration"
            ) from err

        if not isinstance(payload, dict) or not payload.get("connected"):
            reason = ""
            if isinstance(payload, dict):
                reason = str(payload.get("last_error") or "")
            raise CompanionTransportError(
                "the add-on is running but has no phone connected"
                + (f": {reason}" if reason else "")
            )
        self._serial = payload.get("serial") or None
        # The base class treats a non-None _device as "connected"; there is no
        # adb-shell device here, so the serial stands in for it.
        self._device = self._serial or True

    async def close(self) -> None:
        self._device = None
        self._serial = None
        if getattr(self, "_owns_session", False) and self._session is not None:
            try:
                await self._session.close()  # type: ignore[attr-defined]
            except Exception:  # noqa: BLE001
                pass
            self._session = None
            self._owns_session = False

    @property
    def connected(self) -> bool:
        return self._device is not None

    # -- operations -----------------------------------------------------------

    async def shell(self, cmd: str, timeout_s: float = 10.0) -> str:
        """Run one shell command on the phone via the add-on.

        Returns stdout, matching the base class. A non-zero exit code is NOT an
        error here for the same reason it is not over raw ADB: several of the
        commands we run (``grep`` with no match, ``rm -f`` on a missing file)
        exit non-zero as a normal outcome, and the callers judge the output.
        """
        if self._device is None:
            raise CompanionTransportError("not connected")

        from aiohttp import ClientError, ClientTimeout  # noqa: PLC0415

        session = await self._get_session()
        try:
            async with session.post(  # type: ignore[attr-defined]
                f"{self._base}/shell",
                data=cmd.encode("utf-8"),
                headers=self._headers(),
                timeout=ClientTimeout(total=timeout_s + 5),
            ) as resp:
                if resp.status == 503:
                    # The add-on lost the phone underneath us.
                    self._device = None
                    raise CompanionTransportError(
                        "the add-on reports no phone connected"
                    )
                if resp.status == 403:
                    raise CompanionTransportError(
                        "the add-on rejected the token"
                    )
                if resp.status >= 400:
                    raise CompanionTransportError(
                        f"the add-on answered HTTP {resp.status} running a command"
                    )
                payload = await resp.json(content_type=None)
        except (TimeoutError, ClientError, OSError) as err:
            raise CompanionTransportError(
                f"the ADB Bridge add-on became unreachable ({type(err).__name__})"
            ) from err

        if not isinstance(payload, dict):
            raise CompanionTransportError(
                "the add-on returned an unexpected response running a command"
            )
        return str(payload.get("stdout") or "")


async def probe_addon(
    host: str, port: int, token: str, *, session: object | None = None
) -> tuple[bool, str]:
    """Check an add-on address for the config flow. Returns (ok, reason).

    Never raises: the config flow turns the reason into a form error.
    """
    transport = AddOnAdbTransport(host, port, token=token, session=session)
    try:
        await transport.connect(timeout_s=10.0)
    except CompanionTransportError as err:
        return False, str(err)
    except Exception as err:  # noqa: BLE001 - a probe must never crash setup
        _LOGGER.debug("Companion add-on probe failed: %s", err, exc_info=True)
        return False, str(err)
    finally:
        with_close = transport.close()
        try:
            await asyncio.wait_for(with_close, timeout=5)
        except Exception:  # noqa: BLE001
            pass
    return True, ""
