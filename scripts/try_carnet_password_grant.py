#!/usr/bin/env python3
# Copyright 2026 Prash Balan (@its-me-prash) — Apache License 2.0
"""LEGACY Car-Net password-grant flow — bypasses IDK OAuth entirely.

Per research finding: pre-Cariad MBB endpoints (msg.volkswagen.de/fs-car)
gate access by underlying client_id, NOT just audience. WeConnect-ID OAuth
gives the WRONG underlying client. The OFFICIAL VW Connect app uses a
password-grant flow against msg.volkswagen.de/fs-car/core/auth/v1/VW/DE/token
which produces a token whose client identity DOES have XID_APP_VW system
permission.

References:
- wez3/volkswagen-carnet-client
- camueller/SmartApplianceEnabler/doc/soc/VW_DE.md
- upstream/ioBroker.vw-connect/main.js
"""

from __future__ import annotations

import asyncio
import getpass
import sys
from pathlib import Path

import aiohttp

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

_REPO = Path(__file__).resolve().parent.parent
_LOCAL = _REPO / "tests" / "bruno" / "mbb_legacy" / "environments" / "mbb.local.bru"


def _read_vin() -> str:
    if not _LOCAL.exists():
        return "WVWZZZAUZFW805377"
    for line in _LOCAL.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("vin:"):
            return line[4:].strip()
    return "WVWZZZAUZFW805377"


# Legacy password-grant endpoint — DIRECT against MBB, not IDK
_TOKEN_URL = "https://msg.volkswagen.de/fs-car/core/auth/v1/VW/DE/token"

# Multiple body shape candidates (research is sparse on exact format)
_BODY_VARIANTS = [
    # MINIMAL — exactly what wez3/volkswagen-carnet-client sends
    {
        "name": "v1 — wez3 exact (minimal)",
        "body": {
            "grant_type": "password",
            "username": "{email}",
            "password": "{password}",
        },
    },
    # With scope mbb explicitly
    {
        "name": "v2 — with scope mbb",
        "body": {
            "grant_type": "password",
            "username": "{email}",
            "password": "{password}",
            "scope": "openid profile mbb cars",
        },
    },
    # With X-App as openid scope only
    {
        "name": "v3 — scope openid only",
        "body": {
            "grant_type": "password",
            "username": "{email}",
            "password": "{password}",
            "scope": "openid",
        },
    },
]


_HEADER_VARIANTS = [
    # EXACT wez3 headers — vintage 2017 era app version + okhttp client
    {
        "name": "A — wez3 EXACT (eRemote 1.0.0 / okhttp 2.3.0)",
        "headers": {
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
            "X-App-Name": "eRemote",
            "X-App-Version": "1.0.0",
            "User-Agent": "okhttp/2.3.0",
        },
    },
    # Slightly newer eRemote version that the official app shipped
    {
        "name": "B — eRemote 5.1.2 / okhttp 3.7.0",
        "headers": {
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
            "X-App-Name": "eRemote",
            "X-App-Version": "5.1.2",
            "User-Agent": "okhttp/3.7.0",
        },
    },
    # We Connect modern (post-rebrand)
    {
        "name": "C — We Connect 5.3.2 / okhttp 3.7.0",
        "headers": {
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
            "X-App-Name": "We Connect",
            "X-App-Version": "5.3.2",
            "User-Agent": "okhttp/3.7.0",
        },
    },
]


async def _try(session, body_def, header_def, email, password):
    body = {k: v.replace("{email}", email).replace("{password}", password) for k, v in body_def["body"].items()}
    try:
        async with session.post(
            _TOKEN_URL,
            data=body,
            headers=header_def["headers"],
        ) as resp:
            text = await resp.text()
            return resp.status, text[:300]
    except Exception as exc:
        return 0, f"EXCEPTION: {exc}"


async def main():
    print("\n" + "=" * 100)
    print("LEGACY CAR-NET PASSWORD-GRANT — direct against msg.volkswagen.de")
    print("=" * 100)
    print(f"Endpoint: {_TOKEN_URL}")
    print()

    email = input("VW account email: ").strip()
    password = getpass.getpass("VW account password: ")
    if not email or not password:
        sys.exit("ERROR: email + password required")

    print()
    async with aiohttp.ClientSession() as session:
        winners = []
        for body_def in _BODY_VARIANTS:
            for header_def in _HEADER_VARIANTS:
                status, body_excerpt = await _try(session, body_def, header_def, email, password)
                marker = "✓" if 200 <= status < 300 else "✗"
                print(f"\n[{body_def['name']} | {header_def['name']}]")
                print(f"  Status: {marker} {status}")
                print(f"  Body:   {body_excerpt[:250]}")
                if 200 <= status < 300:
                    winners.append((body_def["name"], header_def["name"], body_excerpt))

    print()
    print("=" * 100)
    if winners:
        print(f"\n {len(winners)} WINNING combination(s) found!\n")
        for body_name, header_name, body in winners:
            print(f"  Winner: {body_name} + {header_name}")
            print(f"  Response: {body[:300]}")
            print()
        print("→ This token may have XID_APP_VW! Try it on data endpoints next.")
    else:
        print("\n✗ No password-grant variant succeeded.")
        print("  The legacy Car-Net password endpoint may have been disabled,")
        print("  OR the body/header format we tried is wrong.")
        print()
        print("Common error patterns:")
        print("  401 / invalid_grant: credentials wrong, OR client_id required")
        print("  404: endpoint moved or never existed")
        print("  410 Gone: endpoint deprecated")


if __name__ == "__main__":
    asyncio.run(main())
