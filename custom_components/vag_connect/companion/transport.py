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
import functools
import logging
import re
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


# The longest gap between two burst taps, in 1/100 s (/proc/uptime's unit).
_BURST_MAX_GAP_CS = 70
_BURST_DONE = re.compile(r"^taps=(\d+)$", re.M)


def tap_burst_script(x: int, y: int, count: int) -> str:
    """The shell script behind ``tap_burst`` (POSIX sh, so mksh and toybox).

    Each ``input tap`` is its own process (about 315 ms on a live phone), so
    the gap between taps is whatever that process takes. After every tap the
    script reads /proc/uptime (a builtin ``read``: no extra process) and stops
    when the tap ended more than 700 ms after the previous one. A slow tap can
    still exceed 1 s once, so an aborted burst costs at most two debounced
    sends; it never runs on. The seconds are cut to six digits so the sum
    stays inside mksh's 32-bit arithmetic. A phone whose uptime does not read
    as "<s>.<cc>" gets no taps at all.
    """
    tap = (
        f"input tap {int(x)} {int(y)}; n=$((n+1)); echo t; "
        "read u r </proc/uptime; s=000000${u%.*}; s=${s#\"${s%??????}\"}; "
        "c=$((1$s${u#*.}-100000000)); "
        "if [ -n \"$l\" ]; then d=$((c-l)); "
        "if [ $d -lt 0 ]; then d=$((d+100000000)); fi; "
        f"if [ $d -gt {_BURST_MAX_GAP_CS} ]; then break; fi; fi; l=$c"
    )
    steps = " ".join(str(i) for i in range(int(count)))
    return (
        "n=0; l=; read u r </proc/uptime; "
        "case \"$u\" in *[0-9].[0-9][0-9]) "
        f"for i in {steps}; do {tap}; done;; esac; echo taps=$n"
    )


def parse_tap_burst(out: str) -> int | None:
    match = _BURST_DONE.search(out or "")
    return int(match.group(1)) if match else None


class NetworkAdbTransport:
    """Talks to one phone over TCP ADB. All methods are async and best-effort.

    The device object and the blocking adb-shell calls are marshalled onto a
    worker thread via ``asyncio.to_thread`` so nothing blocks the event loop.
    """

    # Set by ``shutdown`` (entry unload/reload): this transport never connects
    # again, so nothing left over on the old client can drive the phone while
    # the reloaded entry's new client does.
    _shut_down = False

    def __init__(
        self, host: str, port: int, adbkey_path: str, *, wake_sleep: bool = False,
        close_app: bool = False,
    ) -> None:
        self._host = host
        self._port = int(port)
        self._adbkey_path = adbkey_path
        self._device: Any = None
        # v2.26.0 (#974) — when True, the display is put back to SLEEP after each
        # read so a locked/asleep phone shows the app during the dump but does
        # not stay lit permanently. The wake happens anyway (foreground_app);
        # this adds the matching sleep.
        self._wake_sleep = bool(wake_sleep)
        # v4.9.0 (#1552) — when True, the car app is force-stopped after each read
        # so the next poll relaunches it fresh instead of scraping a stale cached
        # screen. OFF by default (a cold relaunch is slower).
        self._close_app = bool(close_app)

    # -- connection -----------------------------------------------------------

    async def connect(self, timeout_s: float = 10.0) -> None:
        """Open (or reopen) the ADB connection, loading/creating the RSA key."""
        self._refuse_if_shut_down()
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

    async def shutdown(self) -> bool:
        """Close for good, on entry unload/reload: ``connect`` refuses after this.

        ``close`` alone is also the reconnect-on-next-read path after a shell
        error, so it must not be final. Returns whether every command sent got
        its answer (here: always, as nothing is tracked in flight).
        """
        self._shut_down = True
        await self.close()
        return True

    def _refuse_if_shut_down(self) -> None:
        if self._shut_down:
            raise CompanionTransportError(
                "the companion connection was closed when the entry unloaded"
            )

    @property
    def connected(self) -> bool:
        return self._device is not None and getattr(self._device, "available", False)

    # -- operations -----------------------------------------------------------

    async def shell(self, cmd: str, timeout_s: float = 10.0) -> str:
        if self._device is None:
            raise CompanionTransportError("not connected")
        try:
            # adb-shell 0.4.4: shell(command, transport_timeout_s,
            # read_timeout_s=10, timeout_s=None). A positional timeout lands in
            # the socket slot and leaves the output wait at the fixed 10 s.
            return await asyncio.to_thread(
                functools.partial(
                    self._device.shell,
                    cmd,
                    transport_timeout_s=timeout_s,
                    read_timeout_s=timeout_s,
                    timeout_s=timeout_s + 5,
                )
            )
        except Exception as err:  # noqa: BLE001 - adb-shell raises many types
            # adb-shell keeps ``available`` True after the socket breaks (a phone
            # that dropped off Wi-Fi, a restarted adbd: "Broken pipe"), so
            # ``connected`` would never ask for a reconnect and every later read
            # would fail the same way. Drop the device so the next call connects
            # afresh, and raise the channel's own error so the failure backoff
            # applies.
            await self.close()
            raise CompanionTransportError(
                f"the ADB connection to {self._host}:{self._port} failed "
                f"({type(err).__name__}); reconnecting on the next read"
            ) from err

    async def dump_ui(self, timeout_s: float = 15.0) -> str:
        """Run uiautomator, return the screen's accessibility XML.

        Two steps on the same shell: dump to a file, then cat it back. The dump
        command prints a status line to stdout, not the XML, so reading the file
        is the reliable path.
        """
        # v2.26.0 (ckomma #20/#22) — delete any previous dump FIRST. uiautomator
        # prints its status to stdout, not into the file, and on a failed dump
        # (secure screen, overlay, idle display) it does NOT overwrite the file.
        # Without this rm, the cat below would return the PREVIOUS run's XML,
        # which still contains "<hierarchy>" and sails past the guard, so we
        # would parse a frozen screen as if it were live, the connector
        # manufacturing its own stale value. Removing it first turns a failed
        # dump into an honest no-data (empty cat, guard raises) instead.
        # One shell round trip for all three steps; the dump itself (~1.5 s,
        # uiautomator waits for the UI to go idle) is the cost that remains.
        xml = await self.shell(
            f"rm -f {_DUMP_PATH}; uiautomator dump {_DUMP_PATH} >/dev/null; "
            f"cat {_DUMP_PATH}",
            timeout_s,
        )
        if "<hierarchy" not in xml:
            raise CompanionTransportError(
                "uiautomator returned no screen dump; the phone may be asleep, "
                "the app may not be in the foreground, or the screen may be "
                "secured"
            )
        return xml

    async def foreground_app(self, package: str, timeout_s: float = 10.0) -> None:
        """Bring the app to the front and let it settle.

        v2.26.0 — wake the display first (ckomma #23a: a sleeping screen is the
        commonest cause of an empty dump), then skip the monkey-launch if the
        app is already frontmost (ckomma #21: relaunching every read is needless
        churn and a possible backend nudge). A cold launch still gets the settle
        delay; an already-foreground app returns immediately.
        """
        await self.wake(timeout_s)
        if await self.is_foreground(package, timeout_s):
            return
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

    async def app_resource_paths(self, package: str) -> tuple[str, ...]:
        """Cheap installed-split identity; no APK contents are transferred."""
        import shlex  # noqa: PLC0415

        paths = await self.shell(f"pm path {shlex.quote(package)}")
        self._resource_paths = tuple(sorted(
            line.removeprefix("package:").strip()
            for line in paths.splitlines() if line.startswith("package:/data/app/")
        ))
        return self._resource_paths

    async def battery_strings(self, package: str) -> dict[str, set[str]]:
        """Read the complete relevant translation table, or fail atomically.

        Cache only the cheap path listing, not a partial extraction: losing a
        language split must never replace a previously usable limit detector.
        """
        import re  # noqa: PLC0415
        import shlex  # noqa: PLC0415

        out: dict[str, set[str]] = {}
        paths = getattr(self, "_resource_paths", None)
        if paths is None:
            paths = await self.app_resource_paths(package)
        for path in paths:
            if not (path.endswith("/base.apk") or re.search(r"/split_config\.[a-z]{2,3}\.apk$", path)):
                continue
            encoded = await self.shell(
                f"unzip -p {shlex.quote(path)} resources.arsc | gzip | base64", 30.0
            )
            try:
                strings = await asyncio.to_thread(_decode_app_strings, encoded)
            except (ValueError, OSError, EOFError) as err:
                raise CompanionTransportError("app translation resources unavailable") from err
            if not strings:
                return {}
            for key, values in strings.items():
                out.setdefault(key, set()).update(values)
        return out

    async def tap(self, x: int, y: int, timeout_s: float = 10.0) -> None:
        await self.shell(f"input tap {int(x)} {int(y)}", timeout_s)
        # Short: every tap is followed by a dump, and uiautomator itself waits
        # for the UI to go idle before it reads the tree.
        await asyncio.sleep(0.25)

    # Shell transports (direct ADB, the Bridge add-on) can send taps back to
    # back; the relay agent has no shell and taps one command at a time.
    can_tap_burst = True

    async def tap_burst(self, x: int, y: int, count: int) -> int | None:
        """Tap one point up to ``count`` times in ONE shell call; return how many.

        The phone times the taps itself (see ``tap_burst_script``) and stops
        once one tap ended more than 700 ms after the previous, so a slow phone
        cannot leave a gap past an app's 1 s debounce for the remaining taps.
        None when the phone did not report a count, 0 when it has no clock.
        """
        out = await self.shell(tap_burst_script(x, y, count), 10.0 + 2 * count)
        await asyncio.sleep(0.25)
        return parse_tap_burst(out)

    # v2.26.0 — reliability primitives adapted from the prior-art ADB projects.

    async def wake(self, timeout_s: float = 10.0) -> None:
        """Wake the display (KEYCODE_WAKEUP) before a dump.

        ckomma #23a: a sleeping screen makes ``dump_ui`` return no hierarchy,
        which otherwise trips the failure cooldown. Waking first removes the
        single most common false trip. Raw keyevent, identical on every app.
        """
        await self.shell("input keyevent 224", timeout_s)  # KEYCODE_WAKEUP
        await asyncio.sleep(0.4)

    async def sleep_if_enabled(self, timeout_s: float = 10.0) -> None:
        """Put the display back to sleep (KEYCODE_SLEEP) after a poll (#974).

        No-op unless the wake/sleep opt-in is on. Best-effort: a failure here
        must never turn a good read into an error, so it swallows exceptions.
        """
        if not self._wake_sleep:
            return
        try:
            await self.shell("input keyevent 223", timeout_s)  # KEYCODE_SLEEP
        except Exception:  # noqa: BLE001
            pass

    async def force_stop_if_enabled(
        self, package: str, timeout_s: float = 10.0
    ) -> None:
        """Force-stop ``package`` after a poll (#1552), if the close-app opt-in is
        on. No-op otherwise. Best-effort: a failure here must never turn a good
        read into an error, so it swallows exceptions.
        """
        if not self._close_app or not package:
            return
        try:
            await self.shell(f"am force-stop {package}", timeout_s)
        except Exception:  # noqa: BLE001
            pass

    async def key_back(self, timeout_s: float = 10.0) -> None:
        """Press BACK (KEYCODE_BACK). The dismissal primitive for overlay
        recovery. Deliberately BACK-only: BACK can never actuate the car, so
        overlay recovery is safe to run even on the unverified read-only brands.
        """
        await self.shell("input keyevent 4", timeout_s)  # KEYCODE_BACK
        await asyncio.sleep(0.25)

    async def is_foreground(self, package: str, timeout_s: float = 10.0) -> bool:
        """True if ``package`` is the frontmost app.

        ckomma #21: monkey-launching on every read even when the app is already
        in front is needless churn. Lets the caller skip the relaunch. Best
        effort: on any parse failure it returns False so the caller relaunches
        (safe default).
        """
        out = await self.shell(
            "dumpsys activity activities | grep -E 'mResumedActivity|mCurrentFocus'",
            timeout_s,
        )
        return package in (out or "")

    async def swipe(
        self, x1: int, y1: int, x2: int, y2: int, dur_ms: int = 300,
        timeout_s: float = 10.0,
    ) -> None:
        """Swipe gesture (e.g. pull-to-refresh).

        CAUTION: unlike a local uiautomator dump, a pull-to-refresh forces an
        app->backend sync, so it re-introduces the rate-limit surface a passive
        read avoids. The channel only ever calls this behind its rate-limit
        backoff, never as a free local op.
        """
        await self.shell(
            f"input swipe {int(x1)} {int(y1)} {int(x2)} {int(y2)} {int(dur_ms)}",
            timeout_s,
        )
        await asyncio.sleep(0.6)


def _decode_app_strings(encoded: str) -> dict[str, set[str]]:
    """Decode, bounded-decompress and parse entirely on the worker thread."""
    import base64  # noqa: PLC0415
    import gzip  # noqa: PLC0415
    import io  # noqa: PLC0415

    from .resources import extract_app_strings  # noqa: PLC0415

    compressed = base64.b64decode("".join(encoded.split()), validate=True)
    with gzip.GzipFile(fileobj=io.BytesIO(compressed)) as table:
        data = table.read(16 * 1024 * 1024 + 1)
    if len(data) > 16 * 1024 * 1024:
        raise ValueError("app translation resources too large")
    return extract_app_strings(data)
