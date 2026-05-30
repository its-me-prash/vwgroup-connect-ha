#!/usr/bin/env python3
# Copyright 2026 Prash Balan (@its-me-prash) — Apache License 2.0
"""verify_my_vin.py — User-facing pre-flight diagnostic for VAG Connect.

What this script does
=====================

Given your VAG account credentials (Audi / VW EU / Skoda / SEAT / CUPRA /
Porsche / VW NA), it logs into the manufacturer API exactly the same way
the VAG Connect HA integration would, then prints — for each VIN on
your account — a privacy-anonymised report of:

- Which sensors WILL populate ()
- Which sensors WILL stay "Unknown" today (️)
- Which sensors WILL spawn but are unreliable for your firmware (⚡)

This lets you decide BEFORE installing the integration:
- Does your car/firmware support the features you care about?
- Will you see all the entities other users report?

Privacy
=======

- Your password is read from stdin (never echoed) or ``VAG_PASSWORD`` env
- VINs are masked to last 6 chars in all output (``***ABC123``)
- GPS coordinates rounded to 1 decimal (~10 km precision)
- All tokens / cookies stripped before display
- NO data is sent anywhere except your manufacturer's own servers
- Output goes to stdout — copy/paste only what you want to share

Usage
=====

    python scripts/verify_my_vin.py
    # Then enter brand + email + password interactively

Or non-interactively (e.g. CI / scripted):

    VAG_BRAND=skoda VAG_EMAIL=you@example.com VAG_PASSWORD='...' \\
        python scripts/verify_my_vin.py

Exit codes
==========

    0 — success, vehicles found + report printed
    1 — auth failure (invalid credentials / 2FA / T&C not accepted)
    2 — no vehicles in account
    3 — script invocation error (missing dep, etc.)

Reference
=========

Built per the EXTERNAL_BLOCKED_ROADMAP / pre-cariad-mbb-and-golf-7-gte
audit §6.2 recommendation. v2.1.0+.
"""

from __future__ import annotations

import asyncio
import getpass
import importlib.util
import os
import sys
import types
from dataclasses import asdict
from pathlib import Path

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    except (AttributeError, OSError):
        pass

_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO))

# Load the integration's brand clients without booting Home Assistant.
# Stub the `homeassistant` package because brand client modules import
# from it for typing only (we never instantiate a HA-backed entity here).
_ha = types.ModuleType("homeassistant")
sys.modules.setdefault("homeassistant", _ha)
for sub in (
    "config_entries", "core", "helpers", "const",
    "exceptions", "util", "components",
):
    sys.modules.setdefault(
        f"homeassistant.{sub}", types.ModuleType(f"homeassistant.{sub}"),
    )


def _load(pkg: str, file_path: Path) -> types.ModuleType:
    spec = importlib.util.spec_from_file_location(pkg, file_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load {pkg} from {file_path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[pkg] = mod
    spec.loader.exec_module(mod)
    return mod


_C = _REPO / "custom_components" / "vag_connect" / "cariad"
sys.modules["c"] = types.ModuleType("c")
sys.modules["c"].__path__ = [str(_C)]
sys.modules["c.auth"] = types.ModuleType("c.auth")
sys.modules["c.auth"].__path__ = [str(_C / "auth")]
sys.modules["c.api"] = types.ModuleType("c.api")
sys.modules["c.api"].__path__ = [str(_C / "api")]
sys.modules["c.push"] = types.ModuleType("c.push")
sys.modules["c.push"].__path__ = [str(_C / "push")]


_BRAND_TO_MODULE: dict[str, tuple[str, str]] = {
    "audi": ("c.api.audi", "AudiClient"),
    "volkswagen": ("c.api.vw_eu", "VWEUClient"),
    "skoda": ("c.api.skoda", "SkodaClient"),
    "seat": ("c.api.seat_cupra", "SeatCupraClient"),
    "cupra": ("c.api.seat_cupra", "SeatCupraClient"),
    "porsche": ("c.api.porsche", "PorscheClient"),
    "volkswagen_na": ("c.api.vw_na", "VwNaClient"),
}


def _mask_vin(vin: str) -> str:
    return f"***{vin[-6:]}" if vin and len(vin) >= 6 else "***??????"


def _round_gps(value: object) -> object:
    if isinstance(value, (int, float)):
        return round(float(value), 1)
    return value


def _classify_field(name: str, value: object) -> tuple[str, str]:
    """Return (status_emoji, label) for a VehicleData field.

     populated cleanly
    ️ None / empty (entity will be "Unknown" or won't spawn)
    ⚡ surfaced but value looks suspicious (zero/empty for safety field)
    """
    if value is None:
        return ("️", "Unknown / not published by your firmware")
    if isinstance(value, (str, int, float, bool)):
        return ("", repr(value))
    if isinstance(value, dict):
        return ("", f"{{{len(value)} keys}}")
    if isinstance(value, list):
        return ("", f"[{len(value)} items]")
    return ("", str(value)[:60])


async def _run() -> int:
    print("=" * 70)
    print("  VAG Connect — verify_my_vin.py — pre-flight diagnostic")
    print("=" * 70)
    print()

    brand = (os.environ.get("VAG_BRAND") or "").strip().lower()
    if not brand:
        print("Available brands:", ", ".join(sorted(_BRAND_TO_MODULE)))
        brand = input("Brand: ").strip().lower()
    if brand not in _BRAND_TO_MODULE:
        print(f"ERROR: unknown brand {brand!r}. Pick one from the list above.")
        return 3

    email = (os.environ.get("VAG_EMAIL") or "").strip()
    if not email:
        email = input("Email: ").strip()

    password = os.environ.get("VAG_PASSWORD") or ""
    if not password:
        password = getpass.getpass("Password (hidden): ")

    if not email or not password:
        print("ERROR: email + password required")
        return 3

    # Load the brand client module.
    mod_name, cls_name = _BRAND_TO_MODULE[brand]
    py_path_map = {
        "c.api.audi": _C / "api" / "audi.py",
        "c.api.vw_eu": _C / "api" / "vw_eu.py",
        "c.api.skoda": _C / "api" / "skoda.py",
        "c.api.seat_cupra": _C / "api" / "seat_cupra.py",
        "c.api.porsche": _C / "api" / "porsche.py",
        "c.api.vw_na": _C / "api" / "vw_na.py",
    }
    # Brand modules import siblings from c.api / c.auth — preload them.
    for sib in ("c.exceptions", "c.models", "c._util"):
        path = _C / (sib.split(".", 1)[1] + ".py")
        if path.exists() and sib not in sys.modules:
            _load(sib, path)
    if mod_name not in sys.modules:
        try:
            _load(mod_name, py_path_map[mod_name])
        except Exception as err:  # noqa: BLE001
            print(f"ERROR: cannot import {mod_name}: {err}")
            return 3

    try:
        import aiohttp  # noqa: PLC0415
    except ImportError:
        print(
            "ERROR: aiohttp not installed. Run: pip install aiohttp"
        )
        return 3

    print()
    print(f"Brand: {brand}")
    print(f"Account: {email}")
    print(f"Authenticating against the manufacturer API...")
    print()

    async with aiohttp.ClientSession() as session:
        cls = getattr(sys.modules[mod_name], cls_name)
        client = cls(session=session, email=email, password=password)
        try:
            await client.authenticate()
        except Exception as err:  # noqa: BLE001
            print(f"ERROR: auth failed — {type(err).__name__}: {err}")
            print()
            print("Common causes:")
            print("- Wrong email or password")
            print("- 2FA prompt active in your manufacturer app — sign in there once")
            print("- T&C / privacy consent prompt active in the app")
            print("- Account temporarily blocked (rate-limit) — wait 15 min")
            return 1

        try:
            vins = await client.get_vehicles()
        except Exception as err:  # noqa: BLE001
            print(f"ERROR: garage discovery failed — {type(err).__name__}: {err}")
            return 1

        if not vins:
            print("No vehicles found on this account.")
            return 2

        print(f"Found {len(vins)} vehicle(s) on this account.")
        print()

        for vin in vins:
            print(f"--- VIN {_mask_vin(vin)} ---")
            try:
                data = await client.get_status(vin)
            except Exception as err:  # noqa: BLE001
                print(f"  ERROR: get_status failed — {type(err).__name__}: {err}")
                print()
                continue

            d = asdict(data) if hasattr(data, "__dataclass_fields__") else dict(data)

            # Anonymise GPS before display
            if "latitude" in d:
                d["latitude"] = _round_gps(d["latitude"])
            if "longitude" in d:
                d["longitude"] = _round_gps(d["longitude"])
            if "vin" in d:
                d["vin"] = _mask_vin(d["vin"])

            populated: list[str] = []
            unknown: list[str] = []
            for key, value in sorted(d.items()):
                status, label = _classify_field(key, value)
                if status == "":
                    populated.append(f"   {key:40s} = {label}")
                else:
                    unknown.append(f"  ️  {key:40s} = {label}")

            print(f"\n  Populated fields ({len(populated)}):")
            for line in populated:
                print(line)
            print(f"\n  Unknown / not-published fields ({len(unknown)}):")
            for line in unknown:
                print(line)
            print()

    print("=" * 70)
    print("Done. Copy/paste the relevant sections when filing a GitHub issue.")
    print("Privacy: VINs masked, GPS rounded to 1 decimal, tokens stripped.")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(_run()))
    except KeyboardInterrupt:
        print("\nAborted by user.")
        sys.exit(130)
