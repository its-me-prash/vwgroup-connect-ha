#!/usr/bin/env python3
# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
"""E3 capture — the REAL departure-timer request the We Connect / myAudi app
sends to the CARIAD BFF. A mitmproxy addon: it watches the app's traffic and
pretty-prints the departure-timer POST/PUT (method + path + body), with the
VIN and any long free-text MASKED, so it's safe to paste.

Why: our command_set_departure_timer currently sends a flat body with the wrong
top-level keys; the app uses a nested `{"timers":[{id,enabled,singleTimer|
recurringTimer}]}` shape (weconnect 4.1.1 DEX). We need the exact HTTP VERB +
path template + body to fix it without guessing — this grabs it live.

────────────────────────────────────────────────────────────────────────────
SETUP (10 min, on the same WiFi as your phone):

  1. Install mitmproxy:            pip install mitmproxy
  2. Start it with this addon:     mitmproxy -s scripts/e3_timer_capture.py
     (or `mitmweb -s scripts/e3_timer_capture.py` for a browser UI)
  3. On your phone → WiFi → set an HTTP proxy to  <this-computer-IP>:8080
  4. In the phone browser open  http://mitm.it  → install the mitmproxy CA
     cert (Android: Settings → Security → install as a *user* CA).
  5. Open We Connect / myAudi, go to a departure/charging timer, change it and
     hit save. Watch this console — the addon prints the captured request.
  6. Paste the printed block back. Done.

⚠ HONEST CAVEAT — certificate pinning. The current We Connect / myAudi builds
   may pin their TLS cert, so mitmproxy could see the connection but not decrypt
   it (you'll see the host but no body, or a handshake error). If so, capturing
   needs a de-pinned app (Frida/objection with a pinning-bypass) or an older
   app build — tell me and I'll write that path. Try this first; it works on
   many builds.
────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import re

try:
    from mitmproxy import http
except Exception:  # noqa: BLE001
    http = None  # allows `python scripts/e3_timer_capture.py` to print help

# Path fragments that identify a timer / departure request.
_TIMER_HINTS = (
    "departuretimer", "departure-timer", "departuretimers",
    "climatisation/timers", "/timers", "climatimer", "chargingtimer",
    "climatisation/settings", "pretripclimate",
)
_METHODS = ("POST", "PUT", "PATCH")

_VIN = re.compile(r"[A-HJ-NPR-Z0-9]{17}")


def _mask_vin(s: str) -> str:
    return _VIN.sub(lambda m: m.group(0)[:3] + "…" + m.group(0)[-2:], s or "")


def _mask_body(text: str) -> str:
    # Body is timer config (times, weekdays, enabled) — not PII — but mask any
    # 17-char VIN that might appear, and truncate very long blobs.
    return _mask_vin(text)[:3000]


if http is not None:
    def request(flow: "http.HTTPFlow") -> None:  # noqa: F821  (mitmproxy hook)
        req = flow.request
        url = req.pretty_url
        low = url.lower()
        if req.method not in _METHODS:
            return
        if not any(h in low for h in _TIMER_HINTS):
            return
        try:
            body = req.get_text(strict=False) or ""
        except Exception:  # noqa: BLE001
            body = "<binary/undecodable>"
        ct = req.headers.get("content-type", "")
        print("\n" + "=" * 70)
        print("  E3 CAPTURE — a timer/climate request from the app")
        print("=" * 70)
        print(f"  {req.method}  {_mask_vin(req.path)}")
        print(f"  host: {req.host}")
        print(f"  content-type: {ct}")
        print("  body:")
        print("    " + _mask_body(body).replace("\n", "\n    "))
        print("=" * 70)
        print("  ^ paste this block. (VIN masked; timer config is not PII.)\n")


if __name__ == "__main__":
    import sys
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
        except Exception:  # noqa: BLE001
            pass
    print(__doc__)
    if http is None:
        print("\n[note] mitmproxy isn't installed in this interpreter — that's")
        print("fine: run it under mitmproxy, `mitmproxy -s scripts/e3_timer_capture.py`.")
