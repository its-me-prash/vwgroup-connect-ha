#!/usr/bin/env python3
# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
"""VW US/Canada read-shape capture — grounds APK-audit items N5 + N6.

For a US/CA VW tester (e.g. issue #659). Logs in with YOUR myVW account,
then GETs the candidate read endpoints and prints only their SHAPE — field
names, value types, and ENUM_LIKE values — with your VIN, name, and every
free-text value MASKED. The output is safe to paste in a GitHub issue: it
reveals the API structure we need, not your personal data.

What it settles:
  N5 — does /ev/v1/vehicle/{uuid}/climate/summary still return a
       ClimateStatusReport, or 404? And which of charge/summary or the
       user-summary route embeds climateStatusInd?
  N6 — does /rrs/v1/privileges... still return coverage, and what shape does
       /account/v1/coverages expose for subscription.active / expiresAt?

Read-only. No commands are sent. Password read via a hidden getpass prompt —
never echoed, never stored.

Usage (PowerShell):
    py scripts/vwna_capture.py --vin 3VW... --email you@example.com --country us
    py scripts/vwna_capture.py --country ca --mfa 123456
"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import json
import re
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO))

# Home Assistant is a real dependency here (same as the test suite) — import
# the client directly; the package's __init__ pulls the installed HA classes.
import aiohttp  # noqa: E402
from custom_components.vag_connect.cariad.api.vw_na import VWNAClient  # noqa: E402

_ENUM = re.compile(r"^[A-Z][A-Z0-9_.:+-]{1,34}$")
_VINISH = re.compile(r"^[A-HJ-NPR-Z0-9]{11,17}$")


def _shape(o, depth: int = 0):
    """Structure + types + enum values only — free text / VIN / PII masked."""
    if depth > 8:
        return "…"
    if isinstance(o, dict):
        return {k: _shape(v, depth + 1) for k, v in list(o.items())[:60]}
    if isinstance(o, list):
        if not o:
            return []
        head = _shape(o[0], depth + 1)
        return [head, f"…(+{len(o) - 1})"] if len(o) > 1 else [head]
    if isinstance(o, bool):
        return o
    if isinstance(o, (int, float)):
        return "<num>"
    if o is None:
        return None
    if isinstance(o, str):
        if _VINISH.match(o):
            return "<VIN>"
        if _ENUM.match(o):
            return o                       # enum value — safe + the useful bit
        if len(o) <= 3:
            return o
        return f"<str:{len(o)}>"           # free text masked
    return f"<{type(o).__name__}>"


async def _probe(client: VWNAClient, label: str, url: str,
                 carnet_token: str | None, use_read: bool) -> None:
    try:
        if use_read:
            data = await client._read(url, carnet_token)
        else:
            data = await client._get(url)
        print(f"\n  === {label} → OK ===")
        print("  " + json.dumps(_shape(data), indent=2, ensure_ascii=False)[:2400].replace("\n", "\n  "))
    except Exception as exc:  # noqa: BLE001
        # An APIError carries .status; show it so a 404 (dead) vs 403/200 is clear.
        status = getattr(exc, "status", None)
        body = str(getattr(exc, "body", "") or "")[:120]
        print(f"\n  === {label} → {type(exc).__name__} "
              f"status={status} {body} ===")


async def _run(email: str, password: str, mfa: str | None, vin: str,
               country: str) -> int:
    vin = vin.strip().upper()
    print("\n" + "=" * 68)
    print(f"  VW-NA read-shape capture — VIN ...{vin[-6:]}  country={country}")
    print("=" * 68)
    async with aiohttp.ClientSession() as session:
        client = VWNAClient(session, email, password, country=country)
        print("\n[1/4] login …")
        try:
            await client.authenticate(mfa_code=mfa)
        except Exception as exc:  # noqa: BLE001
            print(f"  ✗ login failed: {type(exc).__name__}: {str(exc)[:180]}")
            return 6
        print("  ✓ authenticated")

        print("[2/4] garage discovery (VIN → uuid, user_id) …")
        try:
            vins = await client.get_vehicles()
        except Exception as exc:  # noqa: BLE001
            print(f"  ✗ garage failed: {type(exc).__name__}: {str(exc)[:150]}")
            return 7
        uuid = client._vin_to_uuid.get(vin, vin)
        uid = client._user_id or ""
        print(f"  ✓ {len(vins)} vehicle(s); uuid resolved={uuid != vin}; user_id set={bool(uid)}")

        print("[3/4] read-session token …")
        try:
            carnet = await client._get_read_session_token(vin)
        except Exception as exc:  # noqa: BLE001
            carnet = None
            print(f"  (session-token step: {type(exc).__name__} — continuing)")
        print(f"  carnet_token acquired={bool(carnet)}")

        print("[4/4] candidate read shapes (masked):")
        B = client._base
        # N5 candidates (ev/rvs data — use the carnet-authorised read path)
        await _probe(client, "N5 climate/summary",
                     f"{B}/ev/v1/vehicle/{uuid}/climate/summary", carnet, True)
        await _probe(client, "N5 charge/summary",
                     f"{B}/ev/v1/vehicle/{uuid}/charge/summary", carnet, True)
        await _probe(client, "N5 user/.../summary",
                     f"{B}/ev/v1/user/{uid}/vehicle/{uuid}/summary", carnet, True)
        await _probe(client, "rvs status",
                     f"{B}/rvs/v1/vehicle/{uuid}", carnet, True)
        # N6 candidates (subscription/coverage — plain account auth)
        await _probe(client, "N6 rrs privileges",
                     f"{B}/rrs/v1/privileges/user/{uid}/vehicle/{uuid}", None, False)
        await _probe(client, "N6 account/coverages",
                     f"{B}/account/v1/coverages", None, False)
        await _probe(client, "N6 account/VWCare",
                     f"{B}/account/v1/VWCare", None, False)

    print("\n" + "-" * 68)
    print("Paste the whole [4/4] block. It's masked (VIN/text hidden, only field")
    print("names + types + enum values shown). We ground N5/N6 from it.")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description="VW US/CA read-shape capture (N5/N6).")
    p.add_argument("--vin", help="Vehicle VIN (prompted if omitted).")
    p.add_argument("--email", help="myVW account email (prompted if omitted).")
    p.add_argument("--country", default="us", choices=["us", "ca"], help="us or ca.")
    p.add_argument("--mfa", help="2FA code, if your account has it.")
    args = p.parse_args()
    email = args.email or input("myVW email: ").strip()
    vin = args.vin or input("VIN: ").strip()
    if not email or not vin:
        print("ERROR: email and VIN required", file=sys.stderr)
        return 1
    password = (getpass.getpass("myVW password (hidden): ")
                if sys.stdin.isatty() else sys.stdin.readline().rstrip("\n"))
    if not password:
        print("ERROR: password required", file=sys.stderr)
        return 1
    return asyncio.run(_run(email, password, args.mfa, vin, args.country))


if __name__ == "__main__":
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
        except Exception:  # noqa: BLE001
            pass
    raise SystemExit(main())
