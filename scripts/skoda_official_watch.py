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
"""
from __future__ import annotations

import json
import os
import re
import sys

TRIGGER_VERSION = (8, 16, 0)
_PKG = "cz.skodaauto.myskoda"
_VER_RE = re.compile(r"\b(8\.\d{1,2}\.\d{1,2})\b")


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


def main() -> int:
    latest = _play_version(_package_id())
    if latest is None:
        print("FOUND none")
        print("NO-TRIGGER")
        return 0
    print("FOUND " + ".".join(map(str, latest)))
    print("TRIGGER" if latest >= TRIGGER_VERSION else "NO-TRIGGER")
    return 0


if __name__ == "__main__":
    sys.exit(main())
