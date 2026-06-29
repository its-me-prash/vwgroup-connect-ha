#!/usr/bin/env python3
# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
"""Verify all MBB read endpoints work for Golf 7 GTE PHEV.

Reads vw_access_token + x_client_id from mbb.local.bru and tries the
classic pre-Cariad endpoints. Prints status + headline data for each.

Run AFTER scripts/get_mbb_token.py to confirm MBB tokens are accepted
by the actual data endpoints (not just the OAuth one).
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import aiohttp

# Force UTF-8 output on Windows (default cp1252 chokes on ✓ ✗ box-drawing)
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if sys.stderr.encoding and sys.stderr.encoding.lower() != "utf-8":
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


_REPO = Path(__file__).resolve().parent.parent
_LOCAL = _REPO / "tests" / "bruno" / "mbb_legacy" / "environments" / "mbb.local.bru"

# VW headers — match the brand we registered MBB with (VW). Using Audi
# headers caused 'XID_APP_VW permission missing' because gateway routes
# requests by User-Agent + X-App-Name to the registered systemId.
_USER_AGENT = "Volkswagen/3.51.1-android/14"
_MAL = "https://mal-1a.prd.ece.vwg-connect.com"
_MSG = "https://msg.volkswagen.de"


def _read_env() -> dict[str, str]:
    """Parse mbb.local.bru → dict of var values."""
    if not _LOCAL.exists():
        sys.exit(f"ERROR: {_LOCAL} not found. Run get_mbb_token.py first.")
    out: dict[str, str] = {}
    for line in _LOCAL.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        for field in (
            "vw_access_token", "x_client_id", "vin", "brand", "country",
            "idk_id_token", "vw_refresh_token",
        ):
            prefix = f"{field}:"
            if line.startswith(prefix):
                value = line[len(prefix):].strip()
                if value and not value.startswith(("PASTE_", "WILL_BE_FILLED_")):
                    out[field] = value
    return out


def _bearer_headers(token: str, extra: dict[str, str] | None = None) -> dict[str, str]:
    h = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "User-Agent": _USER_AGENT,
    }
    if extra:
        h.update(extra)
    return h


async def _try(name: str, coro) -> tuple[str, int, str]:
    """Run a coroutine and capture (name, status, body_excerpt)."""
    try:
        status, body = await coro
        excerpt = body[:200].replace("\n", " ").replace("\r", " ")
        symbol = "✓" if 200 <= status < 300 else "✗"
        return name, status, f"{symbol} {status} — {excerpt}"
    except Exception as exc:  # noqa: BLE001
        return name, 0, f"✗ EXCEPTION: {exc}"


async def _get(session, url: str, headers: dict) -> tuple[int, str]:
    async with session.get(url, headers=headers) as resp:
        return resp.status, await resp.text()


async def _post(session, url: str, headers: dict, data=None) -> tuple[int, str]:
    async with session.post(url, headers=headers, data=data) as resp:
        return resp.status, await resp.text()


async def main() -> int:
    env = _read_env()
    token = env.get("vw_access_token", "")
    x_client = env.get("x_client_id", "")
    vin = env.get("vin", "")
    brand = env.get("brand", "VW")
    country = env.get("country", "DE")

    if not token or token.startswith("WILL_BE_FILLED"):
        sys.exit("ERROR: vw_access_token in mbb.local.bru is empty. Run get_mbb_token.py first.")
    if not vin:
        sys.exit("ERROR: vin in mbb.local.bru is empty.")

    print(f"\nVerifying MBB endpoints for VIN ...{vin[-4:]} (brand={brand} country={country})")
    print("=" * 76)

    # Per-VIN homeRegion may override readBase. We start with default.
    read_base = _MSG

    # CRITICAL: include X-Client-Id (registered xclientId) on every data
    # call AND match brand headers (X-App-Name=Volkswagen). Without these,
    # MBB gateway responds with "XID_APP_VW permission missing" because it
    # can't determine the systemId context.
    headers = _bearer_headers(
        token,
        {
            "X-App-Name": "Volkswagen",
            "X-App-Version": "3.51.1",
            "X-Client-Id": x_client,
        },
    )

    async with aiohttp.ClientSession() as session:
        results = await asyncio.gather(
            _try(
                "homeRegion",
                _get(session, f"{_MAL}/api/cs/vds/v1/vehicles/{vin}/homeRegion", headers),
            ),
            _try(
                "operationList",
                _get(session, f"{_MAL}/api/rolesrights/operationlist/v3/vehicles/{vin}", headers),
            ),
            _try(
                "vehicles_list",
                _get(session, f"{read_base}/fs-car/usermanagement/users/v1/{brand}/{country}/vehicles", headers),
            ),
            _try(
                "vehicle_status_VSR",
                _get(session, f"{read_base}/fs-car/bs/vsr/v1/{brand}/{country}/vehicles/{vin}/status", headers),
            ),
            _try(
                "charger",
                _get(session, f"{read_base}/fs-car/bs/batterycharge/v1/{brand}/{country}/vehicles/{vin}/charger", headers),
            ),
            _try(
                "climater",
                _get(session, f"{read_base}/fs-car/bs/climatisation/v1/{brand}/{country}/vehicles/{vin}/climater", headers),
            ),
            _try(
                "position",
                _get(session, f"{read_base}/fs-car/bs/cf/v1/{brand}/{country}/vehicles/{vin}/position", headers),
            ),
            _try(
                "tripdata_short",
                _get(session, f"{_MAL}/api/bs/tripstatistics/v1/{brand}/{country}/vehicles/{vin}/tripdata/shortTerm?type=list&newest", headers),
            ),
            _try(
                "departure_timer",
                _get(session, f"{read_base}/fs-car/bs/departuretimer/v1/{brand}/{country}/vehicles/{vin}/timer", headers),
            ),
        )

    # Report
    success = 0
    for name, status, msg in results:
        marker = "✓" if 200 <= status < 300 else " "
        print(f"  {marker} {name:25s} {msg}")
        if 200 <= status < 300:
            success += 1

    print("=" * 76)
    print(f"  {success}/{len(results)} endpoints returned 2xx")

    if success == 0:
        print("\n✗ ZERO endpoints accepted the MBB vwToken.")
        print("  This means MBB-OAuth gives us a token but the data endpoints")
        print("  reject it. Likely cause: brand mismatch (id_token=Audi but")
        print("  endpoint URL says VW), or VIN not bound to MBB account.")
        return 1

    if success < len(results):
        print(f"\n Partial success — {success}/{len(results)}.")
        print("  Some endpoints work for this account; others may need different")
        print("  brand/country combo or aren't enabled for this car.")

    if success == len(results):
        print("\n ALL endpoints work — MBB integration confirmed for Golf 7 GTE!")
        print("\nNext: I'll start v1.26.3 implementation in vag-connect-ha.")

    return 0 if success > 0 else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
