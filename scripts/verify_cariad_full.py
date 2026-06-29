#!/usr/bin/env python3
# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
"""Full Cariad-BFF data probe — tests ALL selectivestatus job types
to find tank/fuel data + everything else for the Golf 7 GTE PHEV.

The Cariad selectivestatus endpoint accepts comma-separated 'jobs' query
param. Different jobs return different data sections. We try the canonical
list to map out which jobs work for this VIN and what data they return.
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


_BASE = "https://emea.bff.cariad.digital"

# Cariad selectivestatus job types — each returns a different data section.
# Source: vag-connect-ha cariad/api/vw_eu.py + observed responses.
_JOB_TYPES = [
    # PHEV / EV core
    "charging",
    "climatisation",
    "fuelStatus",            # ← tank %!
    "measurements",          # odometer, range, total km
    # Status
    "vehicleHealthInspection",
    "vehicleHealthWarnings",
    "vehicleLights",
    # Access
    "access",                # doors, windows, locks
    # Comfort
    "auxiliaryHeating",      # Standheizung
    "windowHeating",
    # Trip / driving
    "userCapabilities",
    "vehicleStatus",
]


async def _try(session, name: str, url: str, headers: dict):
    try:
        async with session.get(url, headers=headers) as resp:
            text = await resp.text()
            marker = "✓" if 200 <= resp.status < 300 else "✗"
            print(f"  {marker} {resp.status:<4} {name}")
            if 200 <= resp.status < 300 and text and text != "{}":
                # Pretty print first 600 chars
                try:
                    parsed = json.loads(text)
                    pretty = json.dumps(parsed, indent=2, ensure_ascii=False)[:800]
                    for line in pretty.split("\n"):
                        print(f"        {line}")
                except Exception:
                    print(f"        {text[:300]}")
            return resp.status, text
    except Exception as exc:
        print(f"  EXC      {name}: {exc}")
        return 0, ""


async def main():
    email = input("VW account email: ").strip()
    password = getpass.getpass("VW account password: ")
    if not email or not password:
        sys.exit("ERROR: email + password required")

    vin = _read_vin()
    print(f"\nFull Cariad probe for Golf 7 GTE (VIN ...{vin[-4:]})")
    print("=" * 110)

    async with aiohttp.ClientSession() as session:
        print("\n[Login] WeConnect-ID OAuth...", end=" ", flush=True)
        try:
            auth = _idk.IDKAuth(session, _models.BRAND_VW_EU)
            tokens = await auth.authenticate(email, password)
            print(f"✓ ({len(tokens.access_token)} char token)")
        except Exception as exc:
            print(f"✗ {exc}")
            return 1

        headers = {
            "Authorization": f"Bearer {tokens.access_token}",
            "Accept": "application/json",
            "User-Agent": "Volkswagen/3.51.1-android/14",
            "Accept-Language": "de-de",
        }

        print("\n--- Test each job type individually ---\n")
        winners = []
        for job in _JOB_TYPES:
            status, body = await _try(
                session,
                f"selectivestatus jobs={job}",
                f"{_BASE}/vehicle/v1/vehicles/{vin}/selectivestatus?jobs={job}",
                headers,
            )
            if 200 <= status < 300 and body and body != "{}":
                winners.append(job)
            print()

        # Try the BIG combined query with ALL working jobs
        if winners:
            print("=" * 110)
            print(f"\n--- Combined query with {len(winners)} working jobs ---\n")
            combined = ",".join(winners)
            await _try(
                session,
                f"selectivestatus jobs={combined}",
                f"{_BASE}/vehicle/v1/vehicles/{vin}/selectivestatus?jobs={combined}",
                headers,
            )

        print("\n" + "=" * 110)
        print(f"SUMMARY: {len(winners)}/{len(_JOB_TYPES)} job types returned data")
        print(f"Working: {', '.join(winners) if winners else '(none)'}")


if __name__ == "__main__":
    asyncio.run(main())
