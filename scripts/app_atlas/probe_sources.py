#!/usr/bin/env python3
# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
"""Diagnostic probe — test which APK distribution sources are reachable
from the current network (typically GitHub Actions runners).

Phase A.2 ran into 403 from APKCombo when invoked from CI (Cloudflare's
bot-heuristic blocks GH-Actions IP ranges regardless of User-Agent).
This probe checks whether alternative sources (APKPure, Aptoide,
APKMirror direct) are similarly blocked — informs Option A (pivot to
different CDN) vs Option B (lokal-authoritative + CI-best-effort).

Run via workflow_dispatch (.github/workflows/probe-apk-sources.yml).
Output: HTTP status + first 200 bytes per URL. Not committed anywhere
— results are read from the action log.
"""

from __future__ import annotations

import sys
import urllib.error
import urllib.request

# One representative URL per source, using CUPRA as the example brand
# (consistently small download page across all sources).
_PROBES: list[tuple[str, str]] = [
    # (label, url)
    ("APKCombo download page (current source, known 403 from CI)",
     "https://apkcombo.com/my-cupra-app/com.cupra.mycupra/download/apk"),
    ("APKPure app page (Option A candidate)",
     "https://apkpure.com/cupra-mycupra/com.cupra.mycupra"),
    ("APKPure download page (Option A candidate)",
     "https://apkpure.com/cupra-mycupra/com.cupra.mycupra/download"),
    ("Aptoide app page (Option A alt candidate)",
     "https://en.aptoide.com/app/com.cupra.mycupra"),
    ("APKMirror app page (current source for version-name, known works)",
     "https://www.apkmirror.com/apk/cupra/my-cupra/"),
    ("Uptodown app page (current source, known works)",
     "https://my-cupra-app.de.uptodown.com/android"),
    # Volkswagen test case (all 3 currently failed — slug research separate)
    ("APKPure VW We Connect ID (verify if app exists there)",
     "https://apkpure.com/we-connect-id/com.volkswagenag.passat.cnap"),
]

# Mobile UA + full browser-headers set (matches apk_extractor.py).
_UA = (
    "Mozilla/5.0 (Linux; Android 14; Pixel 7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36"
)
_HEADERS: dict[str, str] = {
    "User-Agent": _UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.7,de;q=0.3",
    "Accept-Encoding": "gzip, deflate",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
}


def probe(label: str, url: str) -> dict[str, str | int]:
    """GET one URL with full browser-like headers; return status + preview."""
    req = urllib.request.Request(url, headers=_HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read(2048)  # First 2KB only — enough to confirm shape
            if resp.headers.get("Content-Encoding") == "gzip":
                import gzip
                try:
                    body = gzip.decompress(body)
                except Exception:  # noqa: BLE001
                    # gzip needs full frame; truncated body may fail.
                    body = body[:200]
            preview = body[:200].decode("utf-8", errors="replace").replace("\n", " ")
            return {"label": label, "url": url, "status": resp.status,
                    "preview": preview}
    except urllib.error.HTTPError as exc:
        body = b""
        try:
            body = exc.read()[:200]
        except Exception:  # noqa: BLE001
            pass
        return {"label": label, "url": url, "status": exc.code,
                "preview": body.decode("utf-8", errors="replace").replace("\n", " ")}
    except Exception as exc:  # noqa: BLE001
        return {"label": label, "url": url, "status": -1,
                "preview": f"EXCEPTION: {type(exc).__name__}: {exc}"[:200]}


def main() -> int:
    print(f"Probing {len(_PROBES)} APK-distribution sources from this network…")
    print("=" * 78)
    success_count = 0
    for label, url in _PROBES:
        r = probe(label, url)
        status = r["status"]
        marker = "✓" if status == 200 else ("✗" if status >= 400 or status == -1 else "·")
        print(f"\n{marker} [{status}] {label}")
        print(f"    URL: {url}")
        print(f"    Preview: {r['preview'][:150]}")
        if status == 200:
            success_count += 1
    print("\n" + "=" * 78)
    print(f"Summary: {success_count}/{len(_PROBES)} sources returned 200 OK from this network.")
    print("If APKPure returned 200 from CI: viable Option A fallback.")
    print("If all CDN sources returned 403: confirms IP-reputation blocking; "
          "Option B (lokal-authoritative) is correct path.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
