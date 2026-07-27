# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Network-ADB transport for the companion channel — v3.0.0-alpha.

Pure-python ``adb-shell`` over TCP, so no ``adb`` binary is needed inside the
Home Assistant container. This is the only module that talks to the device, and
it is deliberately thin: everything that can be reasoned about without hardware
lives in ``screen.py`` and ``channel.py`` instead.

``adb-shell`` is imported lazily inside the methods, so importing this module
(and running the test suite) never requires the dependency to be present. The
requirement is declared in the manifest for real installs.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

_LOGGER = logging.getLogger(__name__)

# uiautomator writes the dump here, then we read it back over the same shell.
_DUMP_PATH = "/sdcard/vag_connect_ui.xml"

# Where adb-shell persists the RSA keypair that authorises this HA instance to
# the phone (the phone shows the "allow USB debugging" prompt once, then trusts
# this key). Kept under the config dir so it survives restarts.
_ADBKEY_BASENAME = "vag_connect_adbkey"


class CompanionTransportError(RuntimeError):
    """A device-side / connection failure. Carries a human-readable reason."""


class NetworkAdbTransport:
    """Talks to one phone over TCP ADB. All methods are async and best-effort.

    The device object and the blocking adb-shell calls are marshalled onto a
    worker thread via ``asyncio.to_thread`` so nothing blocks the event loop.
    """

    def __init__(self, host: str, port: int, adbkey_path: str) -> None:
        self._host = host
        self._port = int(port)
        self._adbkey_path = adbkey_path
        self._device: Any = None

    # -- connection -----------------------------------------------------------

    async def connect(self, timeout_s: float = 10.0) -> None:
        """Open (or reopen) the ADB connection, loading/creating the RSA key."""
        await asyncio.to_thread(self._connect_blocking, timeout_s)

    def _connect_blocking(self, timeout_s: float) -> None:
        try:
            from adb_shell.adb_device import AdbDeviceTcp  # noqa: PLC0415
            from adb_shell.auth.sign_pythonrsa import PythonRSASigner  # noqa: PLC0415
            from adb_shell.auth.keygen import keygen  # noqa: PLC0415
        except ImportError as err:  # pragma: no cover - requires the dependency
            raise CompanionTransportError(
                "the adb-shell library is not installed; it ships as a "
                "requirement of this integration, so this usually means the "
                "install did not complete"
            ) from err

        import os  # noqa: PLC0415

        if not os.path.exists(self._adbkey_path):
            # First run on this HA instance: mint a keypair. The phone will show
            # a one-time "allow USB debugging from this computer" prompt.
            keygen(self._adbkey_path)
        with open(self._adbkey_path, encoding="utf-8") as fh:
            priv = fh.read()
        with open(self._adbkey_path + ".pub", encoding="utf-8") as fh:
            pub = fh.read()
        signer = PythonRSASigner(pub, priv)

        device = AdbDeviceTcp(self._host, self._port, default_transport_timeout_s=timeout_s)
        try:
            device.connect(rsa_keys=[signer], auth_timeout_s=timeout_s)
        except Exception as err:  # noqa: BLE001 - adb-shell raises many types
            raise CompanionTransportError(
                f"could not reach the phone at {self._host}:{self._port} "
                f"({type(err).__name__}); check it is on the network, that ADB "
                "over Wi-Fi is enabled, and that you accepted the debugging "
                "prompt"
            ) from err
        self._device = device

    async def close(self) -> None:
        if self._device is not None:
            try:
                await asyncio.to_thread(self._device.close)
            except Exception:  # noqa: BLE001
                pass
            self._device = None

    @property
    def connected(self) -> bool:
        return self._device is not None and getattr(self._device, "available", False)

    # -- operations -----------------------------------------------------------

    async def shell(self, cmd: str, timeout_s: float = 10.0) -> str:
        if self._device is None:
            raise CompanionTransportError("not connected")
        return await asyncio.to_thread(self._device.shell, cmd, timeout_s)

    async def dump_ui(self, timeout_s: float = 15.0) -> str:
        """Run uiautomator, return the screen's accessibility XML.

        Two steps on the same shell: dump to a file, then cat it back. The dump
        command prints a status line to stdout, not the XML, so reading the file
        is the reliable path.
        """
        await self.shell(f"uiautomator dump {_DUMP_PATH}", timeout_s)
        xml = await self.shell(f"cat {_DUMP_PATH}", timeout_s)
        if "<hierarchy" not in xml:
            raise CompanionTransportError(
                "uiautomator returned no screen dump; the phone may be asleep "
                "or the app may not be in the foreground"
            )
        return xml

    async def foreground_app(self, package: str, timeout_s: float = 10.0) -> None:
        """Bring the app to the front (monkey launch) and let it settle."""
        await self.shell(
            f"monkey -p {package} -c android.intent.category.LAUNCHER 1", timeout_s
        )
        await asyncio.sleep(1.5)

    async def current_app_version(self, package: str) -> str | None:
        """Read the installed versionName of the app, for the write quarantine."""
        out = await self.shell(f"dumpsys package {package} | grep versionName")
        for line in (out or "").splitlines():
            line = line.strip()
            if line.startswith("versionName="):
                return line.split("=", 1)[1].strip() or None
        return None

    async def tap(self, x: int, y: int, timeout_s: float = 10.0) -> None:
        await self.shell(f"input tap {int(x)} {int(y)}", timeout_s)
        await asyncio.sleep(0.6)
