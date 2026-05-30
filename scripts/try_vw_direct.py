#!/usr/bin/env python3
# Copyright 2026 Prash Balan (@its-me-prash) — Apache License 2.0
"""Test: VW WeConnect-ID id_token → MBB exchange, ALL via Python (no Bruno).

Eliminates Bruno from the trust chain. Login with VW WeConnect-ID client
(a24fba63) directly, register MBB with VW brand, attempt exchange. Shows
raw HTTP response so we know definitively whether MBB rejects via Python
the same way it does via Bruno.
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

# UTF-8 safe stdout
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if sys.stderr.encoding and sys.stderr.encoding.lower() != "utf-8":
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO))

# HA stub for clean import
_ha_stub = types.ModuleType("homeassistant")
sys.modules.setdefault("homeassistant", _ha_stub)
for sub in ("config_entries", "core", "helpers", "const", "exceptions", "util"):
    sys.modules.setdefault(f"homeassistant.{sub}", types.ModuleType(f"homeassistant.{sub}"))


def _load(pkg_path: str, file_path: Path):
    spec = importlib.util.spec_from_file_location(pkg_path, file_path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[pkg_path] = mod
    spec.loader.exec_module(mod)
    return mod


_CARIAD_DIR = _REPO / "custom_components" / "vag_connect" / "cariad"
sys.modules["cariad_auth_only"] = types.ModuleType("cariad_auth_only")
sys.modules["cariad_auth_only"].__path__ = [str(_CARIAD_DIR)]
sys.modules["cariad_auth_only.auth"] = types.ModuleType("cariad_auth_only.auth")
sys.modules["cariad_auth_only.auth"].__path__ = [str(_CARIAD_DIR / "auth")]
_load("cariad_auth_only.exceptions", _CARIAD_DIR / "exceptions.py")
_models = _load("cariad_auth_only.models", _CARIAD_DIR / "models.py")
_idk = _load("cariad_auth_only.auth.idk", _CARIAD_DIR / "auth" / "idk.py")


_MBB_BASE = "https://mbboauth-1d.prd.ece.vwg-connect.com"
_MBB_REG = f"{_MBB_BASE}/mbbcoauth/mobile/register/v1"
_MBB_TOKEN = f"{_MBB_BASE}/mbbcoauth/mobile/oauth2/v1/token"


async def main() -> int:
    email = input("VW account email: ").strip()
    password = getpass.getpass("VW account password: ")
    if not email or not password:
        sys.exit("ERROR: email + password required")

    print("\n" + "=" * 76)
    print("TEST: VW WeConnect-ID id_token → MBB exchange (Python direct)")
    print("=" * 76)

    async with aiohttp.ClientSession() as session:
        # Step 1: VW IDK login (WeConnect ID, a24fba63)
        print("\n[1/3] VW IDK login (WeConnect-ID client a24fba63)...")
        auth = _idk.IDKAuth(session, _models.BRAND_VW_EU)
        try:
            tokens = await auth.authenticate(email, password)
            print(f"      ✓ id_token obtained ({len(tokens.id_token)} chars)")
        except Exception as exc:  # noqa: BLE001
            print(f"      ✗ {exc}")
            return 1

        # Step 2: MBB register as VW
        print("\n[2/3] MBB register (brand=VW, appId=de.volkswagen.car-net.eu.eremote)...")
        reg_body = {
            "client_name": "SM-A405FN",
            "platform": "google",
            "client_brand": "VW",
            "appName": "Volkswagen",
            "appVersion": "3.51.1",
            "appId": "de.volkswagen.car-net.eu.eremote",
        }
        try:
            async with session.post(
                _MBB_REG,
                data=json.dumps(reg_body).encode(),
                headers={
                    "Content-Type": "application/json; charset=utf-8",
                    "Accept": "application/json",
                    "User-Agent": "Volkswagen/3.51.1-android/14",
                },
            ) as resp:
                body = await resp.text()
                if resp.status != 200:
                    print(f"      ✗ HTTP {resp.status}: {body[:300]}")
                    return 2
                client_id = json.loads(body)["client_id"]
                print(f"      ✓ X-Client-Id: ...{client_id[-12:]}")
        except Exception as exc:  # noqa: BLE001
            print(f"      ✗ {exc}")
            return 2

        # Step 3: MBB exchange — VW WeConnect-ID id_token + VW xclientId
        print("\n[3/3] MBB exchange (id_token + X-Client-Id, scope=sc2:fal)...")
        try:
            async with session.post(
                _MBB_TOKEN,
                data={
                    "grant_type": "id_token",
                    "token": tokens.id_token,
                    "scope": "sc2:fal",
                },
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Accept": "application/json",
                    "User-Agent": "Volkswagen/3.51.1-android/14",
                    "X-Client-Id": client_id,
                },
            ) as resp:
                body = await resp.text()
                print(f"      → HTTP {resp.status}")
                print(f"      → Body: {body[:500]}")
                if resp.status == 200:
                    print("\n UNERWARTET: MBB akzeptiert VW WeConnect-ID id_token!")
                    print("   → Bruno hatte recht uns zu misstrauen")
                    return 0
                else:
                    print(f"\n✗ MBB lehnt VW WeConnect-ID id_token ab — bestätigt was Bruno zeigte.")
                    print(f"  Das bestätigt: WeConnect-ID Client gibt KEINE mbb-fähigen id_tokens.")
                    return 3
        except Exception as exc:  # noqa: BLE001
            print(f"      ✗ {exc}")
            return 3


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
