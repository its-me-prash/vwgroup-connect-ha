#!/usr/bin/env python3
# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Watch for the MyŠkoda app version that ships the official-API key flow.

The official Škoda public API (``public.api.connect.skoda-auto.cz``) is live, but
a user can only mint an ``X-API-Key`` from **Settings → Smart Home → API Keys**,
which arrives with app **v8.16** (verified absent from 8.15.0). This script reads
the current MyŠkoda version from its Google Play listing and flags when it reaches
the trigger version, so we can be first to pull it, androguard the key-creation
endpoint, and evaluate auto-mint.

Google Play is the only source, as everywhere else in this repo since 2026-10-17.
It used to walk three APK mirrors, which had two problems: a mirror reports
whatever it last ingested, so this gate could fire late or on a build the store
no longer serves; and the config lookup in front of them read
``config.json["apps"]["skoda"]["sources"]``, a key path that never existed in
that file (it has ``brands``), so the lookup always raised and the hardcoded
mirror slugs in the fallback were in fact the only thing it ever used.

Fail-soft is unchanged: if no version is found it prints ``FOUND none`` and does
NOT trigger (no false alarms). Output is machine-readable for the workflow:

    FOUND <version-or-none>
    TRIGGER  |  NO-TRIGGER
    SEEING   |  BLIND

**The third line exists because fail-soft without it is indistinguishable from
"nothing new".** Measured on 2026-11-01: this watcher printed ``FOUND none`` on
every run since 2026-10-29 (``FOUND 8.17.0`` as late as 2026-10-25) and each run
still concluded *success*, so nothing said it had stopped looking. It never saw
8.18.0, which was on the device by 2026-11-01. ``BLIND`` is what the workflow
branches on to file a de-duplicated issue; it is a different claim from
``NO-TRIGGER``, which means "read a version, it is below the trigger".

Do NOT "fix" this by widening the pattern onto the page body. Measured the same
day: the listing carries no parseable version slot any more (neither of the
atlas scraper's two patterns matches a 1.17 MB body), while the page *does*
contain 8.16.0, 8.15.0, 8.14.0 and so on as review metadata. A pattern over
those would report 8.16.0 as current while the app is at 8.18.0 — a confidently
wrong answer, which is worse than none. ``_VER_RE`` below filters the version
the atlas scraper already extracted; it never sees the page.
"""
from __future__ import annotations

import json
import os
import re
import sys
import time

TRIGGER_VERSION = (8, 16, 0)
_PKG = "cz.skodaauto.myskoda"
# Three numeric parts at the START of whatever the scraper extracted. The major
# was hardcoded to 8 until 2026-11-01, which would have gone blind a second time
# and silently on a 9.x release — the same failure mode in a different place.
# Anchored, so Porsche-shaped "21.26.44-row+193583" parses to (21, 26, 44)
# rather than being rejected.
_VER_RE = re.compile(r"^(\d{1,3}\.\d{1,3}\.\d{1,3})")
# One retry, because a single network blip must not file an issue. Two attempts
# absorb that; a moved version slot fails both and is the case worth surfacing.
_ATTEMPTS = 2
_RETRY_SLEEP_S = 5.0


def _package_id() -> str:
    """The Play package for MyŠkoda, from the atlas config when it is there."""
    here = os.path.dirname(os.path.abspath(__file__))
    cfg = os.path.join(here, "app_atlas", "config.json")
    try:
        with open(cfg, encoding="utf-8") as fh:
            pkg = json.load(fh)["brands"]["skoda"]["package_id"]
    except Exception:  # noqa: BLE001 — the constant below is the same value
        return _PKG
    return str(pkg) or _PKG


def _play_version(package_id: str) -> tuple[int, int, int] | None:
    """Read the version-name off the Play listing, or None.

    Delegates to the atlas scraper rather than carrying a second copy of the
    page patterns: that module also encodes which shapes on a Play page are
    NOT the version (review metadata looks just like it), and two copies of
    that knowledge would drift.
    """
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "app_atlas"))
    try:
        from build_atlas import _try_google_play  # noqa: PLC0415
    except Exception:  # noqa: BLE001
        return None
    try:
        raw = _try_google_play(package_id)
    except Exception:  # noqa: BLE001 — fail soft, never a false alarm
        return None
    if not raw:
        return None
    m = _VER_RE.search(raw)
    if not m:
        return None
    parts = tuple(int(x) for x in m.group(1).split("."))
    return parts if len(parts) == 3 else None  # type: ignore[return-value]


def _read_with_retry(package_id: str, sleep: float = _RETRY_SLEEP_S) -> tuple[int, int, int] | None:
    """``_play_version`` up to ``_ATTEMPTS`` times; None only if all failed.

    ``sleep`` is a parameter so a test does not have to wait for it.
    """
    for attempt in range(_ATTEMPTS):
        got = _play_version(package_id)
        if got is not None:
            return got
        if attempt + 1 < _ATTEMPTS:
            time.sleep(sleep)
    return None


def main() -> int:
    latest = _read_with_retry(_package_id())
    if latest is None:
        print("FOUND none")
        print("NO-TRIGGER")
        # Not the same statement as NO-TRIGGER. See the module docstring: a
        # watcher that cannot read its source must say so, or its silence reads
        # as "nothing new" for as long as nobody checks the logs by hand.
        print("BLIND")
        return 0
    print("FOUND " + ".".join(map(str, latest)))
    print("TRIGGER" if latest >= TRIGGER_VERSION else "NO-TRIGGER")
    print("SEEING")
    return 0


if __name__ == "__main__":
    sys.exit(main())
