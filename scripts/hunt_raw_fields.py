#!/usr/bin/env python3
# Copyright 2026 Prash Balan (@its-me-prash) — Apache License 2.0
"""Hunt for raw MBB-style hex field IDs (0x030103000A = Fuel %, etc).

Cariad maps internal MBB field IDs to JSON properties, but it might
mis-map for migrated PHEV1 cars. We try:
  1. Dump FULL operationList — look for invocationUrl/serviceUri/servicePath
  2. Try Cariad "raw passthrough" endpoint variants
  3. Try mal-1a gateway VSR endpoints (mal-1a accepts our MBB token for
     operationList; maybe also for status)
  4. Try the bs/vsr URL pattern with MBB-exchanged token via mal-1a
     (NOT msg.volkswagen.de which we already proved 403)

Goal: find ANY endpoint that returns field ID 0x030103000A (FUEL %).
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

# Stub HA for clean import
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
_MBB = "https://mbboauth-1d.prd.ece.vwg-connect.com"


def _read_vin() -> str:
    if _LOCAL.exists():
        for line in _LOCAL.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("vin:"):
                return line[4:].strip()
    return "WVWZZZAUZFW805377"


_USER_AGENT = "Volkswagen/3.51.1-android/14"
_AUDI_UA = "Android/4.31.0 (Build 800341641.root project 'myaudi_android'.ext.buildTime) Android/13"


_BRAND_VW_VIA_AUDI = _models.BrandConfig(
    name="vw-via-audi",
    client_id="09b6cbec-cd19-4589-82fd-363dfa8c24da@apps_vw-dilab_com",
    redirect_uri="myaudi:///",
    user_agent=_AUDI_UA,
    api_base="https://msg.volkswagen.de",
    scope=(
        "address profile badge birthdate birthplace nationalIdentifier "
        "nationality profession email vin phone nickname name picture mbb "
        "gallery openid"
    ),
)


async def _get_fresh_tokens(session, email: str, password: str) -> tuple[str, str]:
    """Returns (cariad_access_token, mbb_vwToken_access)."""
    # 1. Cariad token via WeConnect-ID OAuth
    auth_cariad = _idk.IDKAuth(session, _models.BRAND_VW_EU)
    cariad_tokens = await auth_cariad.authenticate(email, password)
    cariad_access = cariad_tokens.access_token

    # 2. MBB vwToken via Audi-IDK + Audi register + exchange
    auth_audi = _idk.IDKAuth(session, _BRAND_VW_VIA_AUDI)
    audi_tokens = await auth_audi.authenticate(email, password)

    reg_body = {
        "client_name": "SM-A405FN", "platform": "google",
        "client_brand": "Audi", "appName": "myAudi",
        "appVersion": "4.31.0", "appId": "de.myaudi.mobile.assistant",
    }
    async with session.post(
        f"{_MBB}/mbbcoauth/mobile/register/v1",
        data=json.dumps(reg_body).encode(),
        headers={
            "Content-Type": "application/json; charset=utf-8",
            "Accept": "application/json",
            "User-Agent": _AUDI_UA,
        },
    ) as resp:
        if resp.status != 200:
            raise RuntimeError(f"MBB register failed: HTTP {resp.status}")
        x_client_id = json.loads(await resp.text())["client_id"]

    async with session.post(
        f"{_MBB}/mbbcoauth/mobile/oauth2/v1/token",
        data={"grant_type": "id_token", "token": audi_tokens.id_token, "scope": "sc2:fal"},
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
            "User-Agent": _AUDI_UA,
            "X-Client-Id": x_client_id,
        },
    ) as resp:
        if resp.status != 200:
            raise RuntimeError(f"MBB exchange failed: HTTP {resp.status}")
        mbb_vwToken = json.loads(await resp.text())["access_token"]

    return cariad_access, mbb_vwToken, x_client_id


async def _try(session, name, url, headers):
    try:
        async with session.get(url, headers=headers) as resp:
            text = await resp.text()
            marker = "✓" if 200 <= resp.status < 300 else "✗"
            # Look for hex field IDs in response
            has_hex = "0x" in text and any(
                f"0x{p}" in text for p in ["030103", "020404", "020401", "0203"]
            )
            highlight = "  HEX FIELDS!" if has_hex else ""
            print(f"  {marker} {resp.status:<4} {name}{highlight}")
            # Show body for any 2xx response (not just hex-flagged) — we want
            # to see what 207 partial responses actually contain
            if 200 <= resp.status < 300 and text and text != "{}":
                excerpt = text[:400].replace("\n", " ")
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
    print(f"\nHunt for hex field IDs for VIN ...{vin[-4:]}")
    print("=" * 100)

    async with aiohttp.ClientSession() as session:
        print("\n[Login] Fetching fresh tokens (Cariad + MBB)...", end=" ", flush=True)
        try:
            cariad_token, mbb_vwToken, x_client = await _get_fresh_tokens(session, email, password)
            print(f"✓ (Cariad: {len(cariad_token)} chars, MBB: {len(mbb_vwToken)} chars)")
        except Exception as exc:
            print(f"✗ {exc}")
            return 1

        # Cariad endpoints want CARIAD token + Volkswagen UA
        headers_cariad = {
            "Authorization": f"Bearer {cariad_token}",
            "Accept": "application/json",
            "User-Agent": _USER_AGENT,
            "Accept-Language": "de-de",
        }
        # MBB endpoints want MBB vwToken + Audi UA + X-Client-Id (Audi reg)
        headers_mbb = {
            "Authorization": f"Bearer {mbb_vwToken}",
            "Accept": "application/json",
            "User-Agent": _AUDI_UA,
            "X-Client-Id": x_client,
        }
        # For MBB endpoints we also need to test with Volkswagen UA (in case
        # gateway routes by UA)
        headers_mbb_vw = {
            "Authorization": f"Bearer {mbb_vwToken}",
            "Accept": "application/json",
            "User-Agent": _USER_AGENT,
            "X-Client-Id": x_client,
            "X-App-Name": "Volkswagen",
            "X-App-Version": "3.51.1",
        }

        # === A. Full operationList — look for invocationUrl ===
        print("\n--- A. Full operationList dump (look for invocationUrl/serviceUri) ---\n")
        url = f"https://mal-1a.prd.ece.vwg-connect.com/api/rolesrights/operationlist/v3/vehicles/{vin}"
        # Try with Audi-context first (matches token brand)
        async with session.get(url, headers=headers_mbb) as resp:
            text = await resp.text()
            if resp.status == 200:
                # Search for URL-like patterns in the response
                import re as _re
                urls_found = _re.findall(r'"(invocationUrl|serviceUri|servicePath|url)"\s*:\s*"([^"]+)"', text)
                if urls_found:
                    print(f"  ✓ Found {len(urls_found)} URL field(s) in operationList:")
                    for field, url_val in urls_found[:20]:
                        print(f"    {field}: {url_val}")
                else:
                    print(f"   No invocationUrl/serviceUri fields in operationList")
                    print(f"  (operationList only describes operations, not URLs — need to construct from id)")

                # Also look for hex field IDs
                hex_ids = _re.findall(r'0x[0-9A-Fa-f]{10,12}', text)
                if hex_ids:
                    print(f"\n   Found hex field IDs: {set(hex_ids)}")
            else:
                print(f"  ✗ {resp.status}")

        # === B. mal-1a VSR endpoint variants ===
        print("\n--- B. mal-1a gateway VSR endpoint variants ---\n")
        mal_base = "https://mal-1a.prd.ece.vwg-connect.com"
        candidates = [
            ("MAL bs vsr status", f"{mal_base}/api/bs/vsr/v1/VW/DE/vehicles/{vin}/status"),
            ("MAL bs vsr stored", f"{mal_base}/api/bs/vsr/v1/vehicles/{vin}/storedVehicleData"),
            ("MAL bs vsr current", f"{mal_base}/api/bs/vsr/v1/vehicles/{vin}/currentVehicleData"),
            ("MAL cs vds parameters", f"{mal_base}/api/cs/vds/v1/vehicles/{vin}/parameters"),
            ("MAL cs vds status", f"{mal_base}/api/cs/vds/v1/vehicles/{vin}/status"),
            ("MAL bs vsr v2 status", f"{mal_base}/api/bs/vsr/v2/VW/DE/vehicles/{vin}/status"),
            ("MAL fs-car vsr", f"{mal_base}/fs-car/bs/vsr/v1/VW/DE/vehicles/{vin}/status"),
            ("MAL bs vsr fields", f"{mal_base}/api/bs/vsr/v1/vehicles/{vin}/fields"),
        ]
        for name, url in candidates:
            await _try(session, name, url, headers_mbb)

        # === C. Cariad-BFF raw / parameters endpoint variants ===
        # IMPORTANT: Cariad endpoints want CARIAD token (not MBB token)
        print("\n--- C. Cariad-BFF raw / parameters / hex variants (with Cariad token) ---\n")
        cariad_base = "https://emea.bff.cariad.digital"
        candidates_c = [
            ("Cariad raw", f"{cariad_base}/vehicle/v1/vehicles/{vin}/raw"),
            ("Cariad parameters", f"{cariad_base}/vehicle/v1/vehicles/{vin}/parameters"),
            ("Cariad fields", f"{cariad_base}/vehicle/v1/vehicles/{vin}/fields"),
            ("Cariad measurements raw", f"{cariad_base}/vehicle/v1/vehicles/{vin}/measurements/raw"),
            ("Cariad fuel direct", f"{cariad_base}/vehicle/v1/vehicles/{vin}/fuel"),
            ("Cariad VSR", f"{cariad_base}/vehicle/v1/vehicles/{vin}/vsr"),
            ("Cariad storedVehicleData", f"{cariad_base}/vehicle/v1/vehicles/{vin}/storedVehicleData"),
            ("Cariad legacy passthrough", f"{cariad_base}/vehicle/v1/vehicles/{vin}/passthrough"),
            ("Cariad vehicleStatusData", f"{cariad_base}/vehicle/v1/vehicles/{vin}/vehicleStatusData"),
            ("Cariad fuel field 0x030103000A", f"{cariad_base}/vehicle/v1/vehicles/{vin}/parameters/0x030103000A"),
            ("Cariad selectivestatus jobs=fuelLevelStatus", f"{cariad_base}/vehicle/v1/vehicles/{vin}/selectivestatus?jobs=fuelLevelStatus"),
            ("Cariad selectivestatus jobs=rangeStatus", f"{cariad_base}/vehicle/v1/vehicles/{vin}/selectivestatus?jobs=rangeStatus"),
            ("Cariad selectivestatus jobs=fuel", f"{cariad_base}/vehicle/v1/vehicles/{vin}/selectivestatus?jobs=fuel"),
            ("Cariad selectivestatus jobs=tank", f"{cariad_base}/vehicle/v1/vehicles/{vin}/selectivestatus?jobs=tank"),
        ]
        for name, url in candidates_c:
            await _try(session, name, url, headers_cariad)

        # === D. WeConnect-Plus dashboard endpoint? ===
        print("\n--- D. Other vendor endpoint patterns ---\n")
        candidates_d = [
            # Sometimes there's an old-style core auth endpoint
            ("Core/auth status", f"https://msg.volkswagen.de/fs-car/core/auth/v1/VW/DE/status/{vin}"),
            # vehicle dashboard
            ("Cariad dashboard", f"{cariad_base}/dashboard/vehicle/v1/{vin}"),
            # myaudi data path (for cross-brand try)
            ("myaudi vehicle-management", f"{cariad_base}/myaudi/vehicle-management/v2/vehicles/{vin}"),
        ]
        for name, url in candidates_d:
            await _try(session, name, url, headers_mbb)

        print("\n" + "=" * 100)
        print("Look for  HEX FIELDS markers above — those endpoints expose raw field IDs.")
        print("Field IDs we want: 0x030103000A (fuel %), 0x0301030005 (total range), 0x0301030006 (gasoline range)")


if __name__ == "__main__":
    asyncio.run(main())
