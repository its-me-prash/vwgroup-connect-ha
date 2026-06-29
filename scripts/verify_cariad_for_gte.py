#!/usr/bin/env python3
# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
"""Test Cariad-BFF endpoints for Golf 7 GTE.

The Volkswagen App shows live data → VIN must be in Cariad backend.
We've been testing the wrong endpoints (msg.volkswagen.de = MBB legacy).
The right ones are at emea.bff.cariad.digital.

This script does a fresh WeConnect-ID OAuth login (gets a Cariad access_token)
and tries the Cariad-BFF endpoints that vag-connect-ha already supports.
If they return 200 → the Golf 7 GTE works via the existing CARIAD code path
in vag-connect-ha and just needs to be enabled.
"""

from __future__ import annotations

import asyncio
import getpass
import importlib.util
import json
import sys
import types
from pathlib import Path

import aiohttp

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO))

_ha = types.ModuleType("homeassistant")
sys.modules.setdefault("homeassistant", _ha)
for sub in ("config_entries", "core", "helpers", "const", "exceptions", "util"):
    sys.modules.setdefault(f"homeassistant.{sub}", types.ModuleType(f"homeassistant.{sub}"))


def _load(pkg, file_path):
    spec = importlib.util.spec_from_file_location(pkg, file_path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[pkg] = mod
    spec.loader.exec_module(mod)
    return mod


_C = _REPO / "custom_components" / "vag_connect" / "cariad"
sys.modules["c"] = types.ModuleType("c"); sys.modules["c"].__path__ = [str(_C)]
sys.modules["c.auth"] = types.ModuleType("c.auth"); sys.modules["c.auth"].__path__ = [str(_C / "auth")]
_load("c.exceptions", _C / "exceptions.py")
_models = _load("c.models", _C / "models.py")
_idk = _load("c.auth.idk", _C / "auth" / "idk.py")


_LOCAL = _REPO / "tests" / "bruno" / "mbb_legacy" / "environments" / "mbb.local.bru"


def _read_vin() -> str:
    if _LOCAL.exists():
        for line in _LOCAL.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("vin:"):
                return line[4:].strip()
    return "WVWZZZAUZFW805377"


# Cariad-BFF endpoints that vag-connect-ha already uses for modern cars.
# If these work for the GTE, vag-connect-ha "just works" out of the box.
_CARIAD_BASE = "https://emea.bff.cariad.digital"


async def _try(session, name: str, method: str, url: str, headers: dict, json_body=None):
    try:
        if method == "GET":
            async with session.get(url, headers=headers) as resp:
                text = await resp.text()
                marker = "✓" if 200 <= resp.status < 300 else "✗"
                excerpt = text[:200].replace("\n", " ")
                print(f"  {marker} {resp.status:<4} {name:<35} {excerpt}")
                return resp.status, text
        else:
            async with session.post(url, headers=headers, json=json_body) as resp:
                text = await resp.text()
                marker = "✓" if 200 <= resp.status < 300 else "✗"
                excerpt = text[:200].replace("\n", " ")
                print(f"  {marker} {resp.status:<4} {name:<35} {excerpt}")
                return resp.status, text
    except Exception as exc:
        print(f"  EXC      {name:<35} {exc}")
        return 0, ""


async def main():
    email = input("VW account email: ").strip()
    password = getpass.getpass("VW account password: ")
    if not email or not password:
        sys.exit("ERROR: email + password required")

    vin = _read_vin()
    print(f"\nTesting CARIAD-BFF endpoints for VIN ...{vin[-4:]}")
    print("=" * 110)

    async with aiohttp.ClientSession() as session:
        # Login VW WeConnect-ID (no mbb scope — we want PURE Cariad token)
        print("\n[Login] WeConnect-ID OAuth (Cariad-side)...", end=" ", flush=True)
        try:
            auth = _idk.IDKAuth(session, _models.BRAND_VW_EU)
            tokens = await auth.authenticate(email, password)
            print(f"✓ ({len(tokens.access_token)} char access_token)")
        except Exception as exc:
            print(f"✗ {exc}")
            return 1

        headers = {
            "Authorization": f"Bearer {tokens.access_token}",
            "Accept": "application/json",
            "User-Agent": "Volkswagen/3.51.1-android/14",
            "Accept-Language": "de-de",
        }

        print()
        # Order matches Bruno cariad_bff/* numbering — same endpoints
        # vag-connect-ha already uses for VW EU in production.
        await _try(session, "vehicles list", "GET",
                   f"{_CARIAD_BASE}/vehicle/v1/vehicles", headers)
        await _try(session, "selectivestatus (all)", "GET",
                   f"{_CARIAD_BASE}/vehicle/v1/vehicles/{vin}/selectivestatus?jobs=all", headers)
        await _try(session, "selectivestatus (charging+climatisation)", "GET",
                   f"{_CARIAD_BASE}/vehicle/v1/vehicles/{vin}/selectivestatus?jobs=charging,climatisation", headers)
        await _try(session, "selectivestatus v2", "GET",
                   f"{_CARIAD_BASE}/vehicle/v2/vehicles/{vin}/selectivestatus?jobs=all", headers)
        await _try(session, "capabilities", "GET",
                   f"{_CARIAD_BASE}/vehicle/v1/vehicles/{vin}/capabilities", headers)
        await _try(session, "parkingposition", "GET",
                   f"{_CARIAD_BASE}/vehicle/v1/vehicles/{vin}/parkingposition", headers)
        await _try(session, "tripdata short", "GET",
                   f"{_CARIAD_BASE}/vehicle/v1/trips/{vin}/shortterm/last", headers)
        await _try(session, "homeRegion", "GET",
                   f"https://mal-1a.prd.ece.vwg-connect.com/api/cs/vds/v1/vehicles/{vin}/homeRegion", headers)

        print()
        print("=" * 110)
        print("LEGEND: ✓2xx = endpoint works | ✗401/403 = wrong auth/permission")
        print("        ✗404 = endpoint moved or VIN not in this backend")
        print()
        print("If ANY 2xx → Golf 7 GTE IS in Cariad backend → vag-connect-ha already supports it!")
        print("If all 404/403 → VIN really is MBB-only and we hit the wall again")


if __name__ == "__main__":
    asyncio.run(main())
