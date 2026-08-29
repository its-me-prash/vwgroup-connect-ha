#!/usr/bin/env python3
# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Watch for the MyŠkoda app version that ships the official-API key flow.

The official Škoda public API (``public.api.connect.skoda-auto.cz``) is live, but
a user can only mint an ``X-API-Key`` from **Settings → Smart Home → API Keys**,
which arrives with app **v8.16** (verified absent from 8.15.0). This script polls
the mirrors listed in ``scripts/app_atlas/config.json`` for the current MyŠkoda
version and flags when it reaches the trigger version, so we can be first to pull
it, androguard the key-creation endpoint, and evaluate auto-mint.

Fail-soft: any mirror that errors is skipped; if no version is found at all it
prints ``FOUND none`` and does NOT trigger (no false alarms). Output is
machine-readable for the workflow:

    FOUND <version-or-none>
    TRIGGER  |  NO-TRIGGER
"""
from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.request

TRIGGER_VERSION = (8, 16, 0)
_PKG = "cz.skodaauto.myskoda"
_VER_RE = re.compile(r"\b(8\.\d{1,2}\.\d{1,2})\b")
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/128.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


def _cfg_sources() -> dict[str, str]:
    here = os.path.dirname(os.path.abspath(__file__))
    cfg = os.path.join(here, "app_atlas", "config.json")
    try:
        with open(cfg, encoding="utf-8") as fh:
            src = json.load(fh)["apps"]["skoda"]["sources"]
    except Exception:  # noqa: BLE001 — fall back to hardcoded slugs
        src = {
            "apkcombo_slug": "myskoda/cz.skodaauto.myskoda",
            "uptodown_subdomain": "cz-skodaauto-myskoda",
            "apkmirror_slug": "skoda-auto-as/myskoda",
        }
    return src


def _urls(src: dict[str, str]) -> list[str]:
    urls: list[str] = []
    if src.get("apkcombo_slug"):
        urls.append(f"https://apkcombo.com/{src['apkcombo_slug']}/")
        urls.append(f"https://apkcombo.com/{src['apkcombo_slug']}/download/apk")
    if src.get("uptodown_subdomain"):
        urls.append(f"https://{src['uptodown_subdomain']}.en.uptodown.com/android")
    if src.get("apkmirror_slug"):
        urls.append(f"https://www.apkmirror.com/apk/{src['apkmirror_slug']}/")
    return urls


def _fetch_versions(url: str) -> list[tuple[int, int, int]]:
    try:
        req = urllib.request.Request(url, headers=_HEADERS)
        with urllib.request.urlopen(req, timeout=25) as resp:  # noqa: S310 — fixed https hosts
            html = resp.read(600_000).decode("utf-8", "replace")
    except (urllib.error.URLError, OSError, ValueError):
        return []
    out = []
    for m in _VER_RE.findall(html):
        parts = tuple(int(x) for x in m.split("."))
        if len(parts) == 3:
            out.append(parts)  # type: ignore[arg-type]
    return out


def main() -> int:
    src = _cfg_sources()
    found: list[tuple[int, int, int]] = []
    for url in _urls(src):
        found.extend(_fetch_versions(url))
    if not found:
        print("FOUND none")
        print("NO-TRIGGER")
        return 0
    latest = max(found)
    print("FOUND " + ".".join(map(str, latest)))
    print("TRIGGER" if latest >= TRIGGER_VERSION else "NO-TRIGGER")
    return 0


if __name__ == "__main__":
    sys.exit(main())
