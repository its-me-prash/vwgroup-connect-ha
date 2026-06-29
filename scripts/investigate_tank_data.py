#!/usr/bin/env python3
# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
"""Hunt for the missing gasoline tank data.

Cariad selectivestatus returns carType: "electric" + only secondaryEngine
data for the Golf 7 GTE PHEV — but MBB operationList confirms the car is
PHEV1. The gasoline tank info MUST be exposed somewhere; we just need to
find which endpoint/job/parameter returns it.

Tests:
  1. Extra job types upstream uses (lvBattery, oilLevel, etc.)
  2. selectivestatus v2 with various actionIds
  3. Alternative fuel-related endpoints
  4. MBB charger endpoint with Cariad token (worth retrying)
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


# Extra jobs from upstream (not yet tested)
_NEW_JOBS = [
    "activeVentilation",
    "batteryChargingCare",
    "batterySupport",
    "chargingProfiles",
    "chargingTimers",
    "climatisationTimers",
    "departureProfiles",
    "departureTimers",
    "honkAndFlash",
    "hybridCarAuxiliaryHeating",   # ← PHEV-specific!
    "lvBattery",                   # 12V battery
    "oilLevel",                    # Oil level (might include fuel?)
    "readiness",
]

# Possible v2 actionIds (guessed from common patterns)
_V2_ACTION_IDS = [
    "vehicle-status",
    "fuel-status",
    "fuelstatus",
    "battery-status",
    "range",
    "tank",
    "all",
]


async def _try(session, name: str, url: str, headers: dict):
    try:
        async with session.get(url, headers=headers) as resp:
            text = await resp.text()
            marker = "✓" if 200 <= resp.status < 300 else "✗"
            print(f"  {marker} {resp.status:<4} {name}")
            if 200 <= resp.status < 300 and text and text != "{}":
                # Look for fuel/tank/gasoline keywords
                lower = text.lower()
                fuel_indicators = ["gasoline", "fuel", "tank", "primaryengine", "carbontype"]
                hits = [w for w in fuel_indicators if w in lower]
                if hits:
                    print(f"         FUEL KEYWORDS FOUND: {', '.join(hits)}")
                    pretty = json.dumps(json.loads(text), indent=2, ensure_ascii=False)[:1000]
                    for line in pretty.split("\n"):
                        print(f"        {line}")
                else:
                    excerpt = text[:200].replace("\n", " ")
                    print(f"        {excerpt}")
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
    print(f"\nHunting tank data for VIN ...{vin[-4:]}")
    print("=" * 110)

    async with aiohttp.ClientSession() as session:
        print("\n[Login] WeConnect-ID OAuth (Cariad)...", end=" ", flush=True)
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

        # === A. Extra upstream jobs ===
        print("\n--- A. Extra job types from upstream ---\n")
        for job in _NEW_JOBS:
            await _try(
                session,
                f"selectivestatus jobs={job}",
                f"{_BASE}/vehicle/v1/vehicles/{vin}/selectivestatus?jobs={job}",
                headers,
            )

        # === B. v2 selectivestatus with various actionIds ===
        print("\n--- B. selectivestatus v2 with actionIds ---\n")
        for action_id in _V2_ACTION_IDS:
            await _try(
                session,
                f"v2 actionIds={action_id}",
                f"{_BASE}/vehicle/v2/vehicles/{vin}/selectivestatus?actionIds={action_id}",
                headers,
            )

        # === C. Alternative endpoint paths ===
        print("\n--- C. Alternative endpoints ---\n")
        await _try(session, "v1 fuel direct", f"{_BASE}/vehicle/v1/vehicles/{vin}/fuel", headers)
        await _try(session, "v1 status all", f"{_BASE}/vehicle/v1/vehicles/{vin}/status", headers)
        await _try(session, "v1 health", f"{_BASE}/vehicle/v1/vehicles/{vin}/health", headers)
        await _try(session, "v1 range", f"{_BASE}/vehicle/v1/vehicles/{vin}/range", headers)
        await _try(session, "v1 measurements", f"{_BASE}/vehicle/v1/vehicles/{vin}/measurements", headers)
        await _try(session, "garage", f"{_BASE}/vehicle/v1/garage", headers)

        # === D. Combined ALL jobs (kitchen sink) ===
        print("\n--- D. KITCHEN SINK: combined query with EVERYTHING ---\n")
        all_jobs = "charging,climatisation,fuelStatus,measurements,vehicleHealthInspection,"
        all_jobs += "vehicleHealthWarnings,vehicleLights,access,auxiliaryHeating,windowHeating,"
        all_jobs += "userCapabilities,vehicleStatus,activeVentilation,batteryChargingCare,"
        all_jobs += "batterySupport,chargingProfiles,chargingTimers,climatisationTimers,"
        all_jobs += "departureProfiles,departureTimers,honkAndFlash,hybridCarAuxiliaryHeating,"
        all_jobs += "lvBattery,oilLevel,readiness"
        await _try(
            session,
            "ALL jobs combined",
            f"{_BASE}/vehicle/v1/vehicles/{vin}/selectivestatus?jobs={all_jobs}",
            headers,
        )

        print("\n" + "=" * 110)
        print("If any endpoint shows 'gasoline', 'fuel', 'tank', or 'primaryEngine' with type='gasoline'")
        print("→ that's our path to tank data. Look at the highlighted FUEL KEYWORDS sections above.")


if __name__ == "__main__":
    asyncio.run(main())
