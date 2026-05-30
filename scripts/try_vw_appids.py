#!/usr/bin/env python3
# Copyright 2026 Prash Balan (@its-me-prash) — Apache License 2.0
"""Try different appId values in MBB register to find which grants XID_APP_VW.

WeConnect-ID id_token + VW register + various appIds → see which combo lets
data endpoints accept the resulting vwToken.
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


_BRAND_VW_NATIVE_MBB = _models.BrandConfig(
    name="vw-mbb",
    client_id="a24fba63-34b3-4d43-b181-942111e6bda8@apps_vw-dilab_com",
    redirect_uri="weconnect://authenticated",
    user_agent="Volkswagen/3.51.1-android/14",
    api_base="https://msg.volkswagen.de",
    scope="openid profile mbb cars vin",
)

_MBB = "https://mbboauth-1d.prd.ece.vwg-connect.com"
_MBB_REG = f"{_MBB}/mbbcoauth/mobile/register/v1"
_MBB_TOKEN = f"{_MBB}/mbbcoauth/mobile/oauth2/v1/token"
_MAL = "https://mal-1a.prd.ece.vwg-connect.com"
_MSG = "https://msg.volkswagen.de"

# Different appId/appName/version combos to try
_APP_VARIANTS = [
    {"name": "Volkswagen App (current)", "appId": "de.volkswagen.car-net.eu.eremote", "appName": "Volkswagen", "appVersion": "3.51.1"},
    {"name": "WeConnect modern", "appId": "de.volkswagen.weconnect", "appName": "WeConnect", "appVersion": "1.0.0"},
    {"name": "Car-Net legacy", "appId": "de.volkswagen.carnet.eu.eremote", "appName": "Car-Net", "appVersion": "5.3.2"},
    {"name": "VW Connect Plus", "appId": "de.volkswagen.connect", "appName": "Connect", "appVersion": "1.0.0"},
    {"name": "We Connect Go", "appId": "de.volkswagen.weconnect-id", "appName": "We Connect ID", "appVersion": "2.0.0"},
    {"name": "MyVolkswagen DE", "appId": "de.volkswagen.myvolkswagen", "appName": "myVolkswagen", "appVersion": "3.0.0"},
]


async def _read_vin():
    local = _REPO / "tests" / "bruno" / "mbb_legacy" / "environments" / "mbb.local.bru"
    for line in local.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("vin:"):
            return line[4:].strip()
    return "WVWZZZAUZFW805377"


async def main():
    email = input("VW account email: ").strip()
    password = getpass.getpass("VW account password: ")
    if not email or not password:
        sys.exit("ERROR: email + password required")

    vin = await _read_vin()
    print(f"\nVIN: ...{vin[-4:]}")
    print("=" * 100)

    async with aiohttp.ClientSession() as session:
        # Login once
        print("\nLogin VW WeConnect-ID with mbb scope...", end=" ", flush=True)
        auth = _idk.IDKAuth(session, _BRAND_VW_NATIVE_MBB)
        try:
            tokens = await auth.authenticate(email, password)
            print(f"✓ ({len(tokens.id_token)} chars)")
        except Exception as exc:
            print(f"✗ {exc}")
            return 1

        # Try each app variant
        print(f"\n{'#':<3} {'App Variant':<32} {'Reg':<10} {'Exch':<10} {'charger':<8}")
        print("-" * 100)
        for i, app in enumerate(_APP_VARIANTS, 1):
            reg_body = {
                "client_name": "SM-A405FN", "platform": "google",
                "client_brand": "VW",
                "appName": app["appName"],
                "appVersion": app["appVersion"],
                "appId": app["appId"],
            }
            # Register
            try:
                async with session.post(
                    _MBB_REG,
                    data=json.dumps(reg_body).encode(),
                    headers={
                        "Content-Type": "application/json; charset=utf-8",
                        "Accept": "application/json",
                        "User-Agent": f"{app['appName']}/{app['appVersion']}-android/14",
                    },
                ) as resp:
                    if resp.status != 200:
                        print(f"{i:<3} {app['name']:<32} ✗{resp.status:<8} - skipped")
                        continue
                    x_client = json.loads(await resp.text())["client_id"]
            except Exception as exc:
                print(f"{i:<3} {app['name']:<32} EXC - skipped")
                continue
            reg_marker = f"✓...{x_client[-6:]}"

            # Exchange
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
                        "User-Agent": f"{app['appName']}/{app['appVersion']}-android/14",
                        "X-Client-Id": x_client,
                    },
                ) as resp:
                    body = await resp.text()
                    if resp.status != 200:
                        print(f"{i:<3} {app['name']:<32} {reg_marker:<10} ✗{resp.status:<8} -")
                        continue
                    vw_token = json.loads(body)["access_token"]
            except Exception:
                print(f"{i:<3} {app['name']:<32} {reg_marker:<10} EXC -")
                continue

            # Try charger endpoint
            try:
                async with session.get(
                    f"{_MSG}/fs-car/bs/batterycharge/v1/VW/DE/vehicles/{vin}/charger",
                    headers={
                        "Authorization": f"Bearer {vw_token}",
                        "Accept": "application/json",
                        "User-Agent": f"{app['appName']}/{app['appVersion']}-android/14",
                        "X-Client-Id": x_client,
                        "X-App-Name": app["appName"],
                        "X-App-Version": app["appVersion"],
                    },
                ) as resp:
                    text = await resp.text()
                    marker = "✓2xx" if 200 <= resp.status < 300 else f"✗{resp.status}"
                    print(f"{i:<3} {app['name']:<32} {reg_marker:<10} ✓200      {marker:<8}")
                    if 200 <= resp.status < 300:
                        print(f"\n WINNER: {app['name']}")
                        print(f"   appId={app['appId']}")
                        print(f"   First 300 chars of charger response:")
                        print(f"   {text[:300]}")
                        return 0
            except Exception as exc:
                print(f"{i:<3} {app['name']:<32} {reg_marker:<10} ✓200      EXC")

    print("\nAlle App-Varianten getestet — keine grant XID_APP_VW Permission.")
    return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
