#!/usr/bin/env python3
# Copyright 2026 Prash Balan (@its-me-prash) — Apache License 2.0
"""Test which active control actions work for the Golf 7 GTE.

vag-connect-ha already implements lock/unlock, charging start/stop,
climate start/stop, honk/flash, wake. We test whether these endpoints
ACCEPT requests for our VIN (without actually mutating state where avoidable)
to know which functions will work in the integration.

Strategy:
  - GET capabilities/operations endpoints (read-only safe)
  - POST vehicleWakeup (safe — just triggers a status refresh)
  - For lock/unlock + charging + climate: send a "noop" or query-only call
    where possible, otherwise document what would happen
  - DO NOT actually lock/unlock without explicit user confirmation
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


async def _get(session, name, url, headers):
    """Read-only test."""
    try:
        async with session.get(url, headers=headers) as resp:
            text = await resp.text()
            marker = "✓" if 200 <= resp.status < 300 else "✗"
            excerpt = text[:300].replace("\n", " ")
            print(f"  {marker} {resp.status:<4} GET  {name}")
            if 200 <= resp.status < 300 and text and text != "{}":
                print(f"        {excerpt}")
            return resp.status, text
    except Exception as exc:
        print(f"  EXC      GET  {name}: {exc}")
        return 0, ""


async def _probe_post(session, name, url, headers, body):
    """Probe POST endpoint (will MUTATE — only safe ones tested below)."""
    try:
        async with session.post(url, headers=headers, json=body) as resp:
            text = await resp.text()
            marker = "✓" if 200 <= resp.status < 300 else "✗"
            excerpt = text[:300].replace("\n", " ")
            print(f"  {marker} {resp.status:<4} POST {name}")
            if text:
                print(f"        {excerpt}")
            return resp.status, text
    except Exception as exc:
        print(f"  EXC      POST {name}: {exc}")
        return 0, ""


async def main():
    email = input("VW account email: ").strip()
    password = getpass.getpass("VW account password: ")
    if not email or not password:
        sys.exit("ERROR: email + password required")

    vin = _read_vin()
    print(f"\nActive Action Capability Test for VIN ...{vin[-4:]}")
    print("=" * 100)
    print("  Most tests are READ-ONLY. Wake POST will be executed (safe).")
    print("  Lock/Unlock/Charge/Climate POST will be SKIPPED unless --execute is passed.")
    print()

    execute_mutating = "--execute" in sys.argv
    if execute_mutating:
        print("  --execute flag set: WILL execute mutating POST calls!")
        print("  This will trigger LOCK on your car. Press Ctrl+C in 5s to abort...")
        await asyncio.sleep(5)
    else:
        print("ℹ  Run with --execute to also test lock/unlock/charging/climate POSTs.")
    print()

    async with aiohttp.ClientSession() as session:
        print("[Login] Cariad WeConnect-ID...", end=" ", flush=True)
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
            "Content-Type": "application/json",
            "User-Agent": "Volkswagen/3.51.1-android/14",
            "Accept-Language": "de-de",
        }

        # === A. CAPABILITIES (read-only, tells us what's allowed) ===
        print("\n--- A. Capabilities (what does the car expose?) ---\n")
        status, body = await _get(
            session, "capabilities (full)",
            f"{_BASE}/vehicle/v1/vehicles/{vin}/capabilities", headers
        )

        if 200 <= status < 300 and body:
            try:
                data = json.loads(body)
                caps = data.get("capabilities", {})
                print(f"\n  → Capabilities exposed: {list(caps.keys())}")
                for cap_id, cap_info in caps.items():
                    enabled = cap_info.get("isEnabled", False)
                    operations = cap_info.get("operations", {})
                    op_list = list(operations.keys()) if isinstance(operations, dict) else []
                    print(f"    • {cap_id}: enabled={enabled}, operations={op_list}")
            except Exception:
                pass

        # === B. WAKE (POST, safe — just refresh) ===
        print("\n--- B. Wake test (safe POST — only triggers status refresh) ---\n")
        for version in ["v1", "v2"]:
            status, body = await _probe_post(
                session, f"vehicleWakeup ({version})",
                f"{_BASE}/vehicle/{version}/vehicles/{vin}/vehicleWakeup",
                headers, {}
            )
            if 200 <= status < 300:
                break

        # === C. ACTION DISCOVERY (read-only — what URLs are documented?) ===
        print("\n--- C. Action endpoint discovery (HEAD/OPTIONS to probe existence) ---\n")
        action_endpoints = [
            ("Lock door", f"/vehicle/v1/vehicles/{vin}/access/lock"),
            ("Unlock door", f"/vehicle/v1/vehicles/{vin}/access/unlock"),
            ("Start charging", f"/vehicle/v1/vehicles/{vin}/charging/start"),
            ("Stop charging", f"/vehicle/v1/vehicles/{vin}/charging/stop"),
            ("Start climate", f"/vehicle/v1/vehicles/{vin}/climatisation/start"),
            ("Stop climate", f"/vehicle/v1/vehicles/{vin}/climatisation/stop"),
            ("Honk + flash", f"/vehicle/v1/vehicles/{vin}/honkAndFlash"),
            ("Window heat start", f"/vehicle/v1/vehicles/{vin}/windowHeating/start"),
            ("Window heat stop", f"/vehicle/v1/vehicles/{vin}/windowHeating/stop"),
            ("Aux heater start", f"/vehicle/v1/vehicles/{vin}/auxiliaryHeating/start"),
            ("Aux heater stop", f"/vehicle/v1/vehicles/{vin}/auxiliaryHeating/stop"),
        ]

        # Use OPTIONS to probe without mutating
        for name, path in action_endpoints:
            url = f"{_BASE}{path}"
            try:
                async with session.options(url, headers=headers) as resp:
                    text = await resp.text()
                    allow = resp.headers.get("Allow", resp.headers.get("Access-Control-Allow-Methods", ""))
                    marker = "✓" if 200 <= resp.status < 300 else "?"
                    print(f"  {marker} {resp.status:<4} OPTIONS {name:<22} Allow={allow}")
            except Exception as exc:
                print(f"  EXC      OPTIONS {name}: {exc}")

        # === D. EXECUTE actual mutating actions (only if --execute) ===
        if execute_mutating:
            print("\n--- D. EXECUTING mutating POST actions (--execute given) ---\n")
            print("  Sending actual control commands to your car!")

            # Lock first (assume car is unlocked? safer to start with charging stop)
            await _probe_post(
                session, "Stop climatisation (safe — already off)",
                f"{_BASE}/vehicle/v1/vehicles/{vin}/climatisation/stop",
                headers, {}
            )
            # Lock the car
            await _probe_post(
                session, "Lock door",
                f"{_BASE}/vehicle/v1/vehicles/{vin}/access/lock",
                headers, {"spin": ""}  # Empty SPIN to test if needed
            )

        print("\n" + "=" * 100)
        print("RESULTS GUIDE:")
        print("- Capabilities section shows EVERY operation Cariad exposes for your VIN")
        print("- Wake POST result tells us if vag-connect-ha's wake button will work")
        print("- OPTIONS responses reveal which action endpoints exist server-side")
        print("- Run with --execute to actually try lock/unlock/charge/climate (RISK!)")


if __name__ == "__main__":
    asyncio.run(main())
