#!/usr/bin/env python3
# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
"""Squeeze every possible sensor/entity out of the Golf 7 GTE.

We've been hitting capabilities surface-level. The capabilities list reveals
many operations we haven't called:
  - 13 different tripStatistics operations (we only used getTripdataShorttermLast)
  - getChargingMode, getChargingSettings, getChargingCareStatus
  - getDepartureProfiles (departure timer programming)
  - getEngineType (engine info)
  - getMaintenanceStatus (service info detail)
  - putClimatisationSettings (current settings)
  - getClimatisationSettings (current settings)
  - More detailed access status fields (window per door?)

Each successful endpoint = potential new HA entity.
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
_BASE = "https://emea.bff.cariad.digital"


def _read_vin() -> str:
    if _LOCAL.exists():
        for line in _LOCAL.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("vin:"):
                return line[4:].strip()
    return "WVWZZZAUZFW805377"


async def _try(session, name, url, headers):
    try:
        async with session.get(url, headers=headers) as resp:
            text = await resp.text()
            marker = "✓" if 200 <= resp.status < 300 else "✗"
            if 200 <= resp.status < 300 and text and text != "{}":
                print(f"\n  {marker} {resp.status:<4} {name}")
                try:
                    parsed = json.loads(text)
                    pretty = json.dumps(parsed, indent=2, ensure_ascii=False)[:1500]
                    for line in pretty.split("\n"):
                        print(f"        {line}")
                except Exception:
                    print(f"        {text[:600]}")
            else:
                print(f"  {marker} {resp.status:<4} {name}")
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
    print(f"\nDeep extraction of ALL sensor candidates for VIN ...{vin[-4:]}")
    print("=" * 100)

    async with aiohttp.ClientSession() as session:
        print("\n[Login] Cariad WeConnect-ID...", end=" ", flush=True)
        try:
            auth = _idk.IDKAuth(session, _models.BRAND_VW_EU)
            tokens = await auth.authenticate(email, password)
            print("✓")
        except Exception as exc:
            print(f"✗ {exc}")
            return 1

        headers = {
            "Authorization": f"Bearer {tokens.access_token}",
            "Accept": "application/json",
            "User-Agent": "Volkswagen/3.51.1-android/14",
            "Accept-Language": "de-de",
        }

        # ============================================================
        # 1. TRIP STATISTICS — 6 different endpoints we haven't fully tested
        # ============================================================
        print("\n--- 1. TRIP STATISTICS (6 endpoints) ---")
        await _try(session, "trips shortterm last", f"{_BASE}/vehicle/v1/trips/{vin}/shortterm/last", headers)
        await _try(session, "trips shortterm (list)", f"{_BASE}/vehicle/v1/trips/{vin}/shortterm", headers)
        await _try(session, "trips longterm last", f"{_BASE}/vehicle/v1/trips/{vin}/longterm/last", headers)
        await _try(session, "trips longterm (list)", f"{_BASE}/vehicle/v1/trips/{vin}/longterm", headers)
        await _try(session, "trips cyclic last", f"{_BASE}/vehicle/v1/trips/{vin}/cyclic/last", headers)
        await _try(session, "trips cyclic (list)", f"{_BASE}/vehicle/v1/trips/{vin}/cyclic", headers)

        # ============================================================
        # 2. CHARGING — multiple endpoints not tested
        # ============================================================
        print("\n--- 2. CHARGING DETAILS (4 endpoints) ---")
        await _try(session, "charging settings", f"{_BASE}/vehicle/v1/vehicles/{vin}/charging/settings", headers)
        await _try(session, "charging mode", f"{_BASE}/vehicle/v1/vehicles/{vin}/charging/mode", headers)
        await _try(session, "charging status", f"{_BASE}/vehicle/v1/vehicles/{vin}/charging/status", headers)
        await _try(session, "charging care status", f"{_BASE}/vehicle/v1/vehicles/{vin}/charging/careStatus", headers)
        await _try(session, "charging settings bidirectional", f"{_BASE}/vehicle/v1/vehicles/{vin}/charging/settings/bidirectional", headers)
        await _try(session, "selectivestatus charging full", f"{_BASE}/vehicle/v1/vehicles/{vin}/selectivestatus?jobs=charging,batteryChargingCare,chargingProfiles,chargingTimers", headers)

        # ============================================================
        # 3. CLIMATISATION — multiple endpoints
        # ============================================================
        print("\n--- 3. CLIMATISATION DETAILS (5 endpoints) ---")
        await _try(session, "climatisation settings", f"{_BASE}/vehicle/v1/vehicles/{vin}/climatisation/settings", headers)
        await _try(session, "climatisation status", f"{_BASE}/vehicle/v1/vehicles/{vin}/climatisation/status", headers)
        await _try(session, "climatisation temperature", f"{_BASE}/vehicle/v1/vehicles/{vin}/climatisation/temperature", headers)
        await _try(session, "windowheating", f"{_BASE}/vehicle/v1/vehicles/{vin}/windowheating", headers)
        await _try(session, "selectivestatus climate full", f"{_BASE}/vehicle/v1/vehicles/{vin}/selectivestatus?jobs=climatisation,climatisationTimers", headers)

        # ============================================================
        # 4. DEPARTURE PROFILES (Departure Timer)
        # ============================================================
        print("\n--- 4. DEPARTURE PROFILES (3 endpoints) ---")
        await _try(session, "departure profiles", f"{_BASE}/vehicle/v1/vehicles/{vin}/departure/profiles", headers)
        await _try(session, "departure timers settings", f"{_BASE}/vehicle/v1/vehicles/{vin}/departure/timers/settings", headers)
        await _try(session, "selectivestatus departure full", f"{_BASE}/vehicle/v1/vehicles/{vin}/selectivestatus?jobs=departureProfiles,departureTimers,chargingTimers", headers)

        # ============================================================
        # 5. ACCESS STATE — windows/sunroof/doors detail
        # ============================================================
        print("\n--- 5. ACCESS / WINDOWS / SUNROOF (full detail) ---")
        await _try(session, "access full", f"{_BASE}/vehicle/v1/vehicles/{vin}/access", headers)
        await _try(session, "selectivestatus access detail", f"{_BASE}/vehicle/v1/vehicles/{vin}/selectivestatus?jobs=access,vehicleHealthWarnings", headers)

        # ============================================================
        # 6. MAINTENANCE / HEALTH (full detail)
        # ============================================================
        print("\n--- 6. MAINTENANCE / HEALTH (full detail) ---")
        await _try(session, "maintenance status", f"{_BASE}/vehicle/v1/vehicles/{vin}/maintenance/status", headers)
        await _try(session, "selectivestatus health full", f"{_BASE}/vehicle/v1/vehicles/{vin}/selectivestatus?jobs=vehicleHealthInspection,vehicleHealthWarnings,vehicleLights,oilLevel,oilLevelStatus", headers)

        # ============================================================
        # 7. WAKE-UP REQUESTS HISTORY
        # ============================================================
        print("\n--- 7. WAKE-UP REQUESTS / TRIGGER STATUS ---")
        await _try(session, "wakeup requests", f"{_BASE}/vehicle/v1/vehicles/{vin}/vehicleWakeUp/requests", headers)
        await _try(session, "wakeup status", f"{_BASE}/vehicle/v1/vehicles/{vin}/vehicleWakeUp/status", headers)

        # ============================================================
        # 8. AUTOMATION (capability shows enabled but no operations listed)
        # ============================================================
        print("\n--- 8. AUTOMATION ENDPOINTS ---")
        await _try(session, "automation", f"{_BASE}/vehicle/v1/vehicles/{vin}/automation", headers)
        await _try(session, "selectivestatus automation", f"{_BASE}/vehicle/v1/vehicles/{vin}/selectivestatus?jobs=automation", headers)

        # ============================================================
        # 9. EVERYTHING IN ONE BIG QUERY (ultimate kitchen sink)
        # ============================================================
        print("\n--- 9. ULTIMATE KITCHEN SINK (every job we know) ---")
        all_jobs = (
            "access,activeVentilation,automation,auxiliaryHeating,batteryChargingCare,"
            "batterySupport,charging,chargingProfiles,chargingTimers,climatisation,"
            "climatisationTimers,departureProfiles,departureTimers,engineType,fuelStatus,"
            "honkAndFlash,hybridCarAuxiliaryHeating,lvBattery,measurements,oilLevel,"
            "oilLevelStatus,parkingPosition,readiness,state,tripStatistics,"
            "userCapabilities,vehicleHealthInspection,vehicleHealthWarnings,"
            "vehicleLights,vehicleStatus,vehicleWakeUp,windowHeating"
        )
        await _try(session, "ALL jobs", f"{_BASE}/vehicle/v1/vehicles/{vin}/selectivestatus?jobs={all_jobs}", headers)

        print("\n" + "=" * 100)
        print("Look at the 2xx responses above — each unique data point = potential HA entity!")


if __name__ == "__main__":
    asyncio.run(main())
