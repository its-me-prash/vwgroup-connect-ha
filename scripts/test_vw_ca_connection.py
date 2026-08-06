#!/usr/bin/env python3
# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
"""Manual VW Canada connection test — diagnoses the #915 HTTP 500 reports.

Runs the SAME auth + garage-discovery code path as the HA integration
(``VWNAClient``, country="ca"), with DEBUG logging on the auth/API modules
turned on, so a live 500 shows exactly WHICH request produced it (email
step, password step, token exchange, garage fetch, ...) instead of a
generic "login failed".

Background (see custom_components/vag_connect/cariad/auth/idk.py, #915):
VW's signin-service occasionally answers a step in the login chain with a
bare HTTP 5xx that has nothing to do with the password being wrong — it's
an upstream outage. The integration already classifies that as
UpstreamUnavailableError rather than "invalid credentials", but which
concrete call is 500-ing is easiest to pin down outside of HA, on demand.

USAGE
    python scripts/test_vw_ca_connection.py --email you@example.com
    python scripts/test_vw_ca_connection.py --email you@example.com --pin 1234
    python scripts/test_vw_ca_connection.py --email you@example.com --country us

Password is always prompted via getpass — never echoed, never stored.
The S-PIN (--pin) is optional; omit it if you only want to test login +
vehicle listing (no SPIN read-session / lock-status exchange).
"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import json
import logging
import re
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO))

import aiohttp  # noqa: E402

from custom_components.vag_connect.cariad.api.vw_na import VWNAClient  # noqa: E402
from custom_components.vag_connect.cariad.exceptions import (  # noqa: E402
    AuthenticationError,
    CariadError,
    RateLimitError,
    TwoFactorRequiredError,
    UpstreamUnavailableError,
)


import dataclasses  # noqa: E402

_ENUM = re.compile(r"^[A-Z][A-Z0-9_.:+-]{1,34}$")
_VINISH = re.compile(r"^[A-HJ-NPR-Z0-9]{11,17}$")


def _shape(o: object, depth: int = 0) -> object:
    """Structure + types + enum values only — free text / VIN / PII masked.

    Same masking rules as scripts/vwna_capture.py's `_shape`, duplicated
    here so this script stays self-contained: field names and value TYPES
    are safe to paste into an issue, free-text values are not.
    """
    if depth > 8:
        return "…"
    if isinstance(o, dict):
        return {k: _shape(v, depth + 1) for k, v in list(o.items())[:60]}
    if isinstance(o, list):
        if not o:
            return []
        head = _shape(o[0], depth + 1)
        return [head, f"…(+{len(o) - 1})"] if len(o) > 1 else [head]
    if isinstance(o, bool):
        return o
    if isinstance(o, (int, float)):
        return "<num>"
    if o is None:
        return None
    if isinstance(o, str):
        if _VINISH.match(o):
            return "<VIN>"
        if _ENUM.match(o):
            return o
        if len(o) <= 3:
            return o
        return f"<str:{len(o)}>"
    return f"<{type(o).__name__}>"


def _setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    # Quiet the noisy transport logger; keep our auth/API modules verbose.
    logging.getLogger("aiohttp").setLevel(logging.WARNING)
    logging.getLogger("custom_components.vag_connect.cariad.auth.idk").setLevel(level)
    logging.getLogger("custom_components.vag_connect.cariad.api.vw_na").setLevel(level)
    logging.getLogger("custom_components.vag_connect.cariad.api.base").setLevel(level)


def _display_vehicle_data(d: object) -> None:
    """Pretty-print all non-None fields from a VehicleData dataclass.

    Groups fields into logical sections for readability. VIN is masked;
    all other telemetry values (SoC, GPS, range, etc.) are shown as-is
    since that's the point of this diagnostic script.
    """
    fields = dataclasses.fields(d)
    # Group definitions: (section_title, field_name_prefixes_or_names)
    sections = [
        ("Identity", ["vin", "model", "model_year", "manufacturer",
                      "vehicle_nickname", "firmware_version", "license_plate"]),
        ("Battery & Range", ["battery_soc", "battery_available_kwh", "battery_cap_kwh",
                             "battery_temp", "fuel_level", "range_km", "electric_range_km",
                             "combustion_range_km", "total_range_km", "odometer_km"]),
        ("Charging", ["charging_state", "is_charging", "plug_state", "plug_connected",
                      "charging_power_kw", "charging_rate_kmh", "charge_complete_eta",
                      "charging_type", "target_soc", "max_charge_current",
                      "connector_locked", "charge_mode"]),
        ("Location", ["latitude", "longitude"]),
        ("Climate", ["climatisation_state", "climatisation_active",
                     "target_temperature", "climate_remaining_time_min"]),
        ("Doors & Windows", ["doors_locked", "doors_open", "trunk_open",
                             "hood_open", "windows_open"]),
        ("Connection", ["is_online", "last_seen_at"]),
        ("Drivetrain", ["is_electric", "is_hybrid", "has_battery", "has_combustion"]),
    ]

    # Collect fields already shown in sections
    shown = set()
    for _, names in sections:
        shown.update(names)

    for title, names in sections:
        values = []
        for name in names:
            val = getattr(d, name, None)
            if val is None:
                continue
            # Mask VIN for privacy
            if name == "vin" and isinstance(val, str) and len(val) >= 6:
                val = f"***{val[-6:]}"
            values.append((name, val))
        if values:
            print(f"\n    ── {title} ──")
            for name, val in values:
                print(f"      {name}: {val}")

    # Catch-all: any non-None fields not in the sections above
    extras = []
    for f in fields:
        if f.name in shown:
            continue
        val = getattr(d, f.name, None)
        if val is None or val == {} or val == []:
            continue
        # Skip False booleans (default state, not interesting)
        if val is False:
            continue
        extras.append((f.name, val))

    if extras:
        print("\n    ── Other ──")
        for name, val in extras:
            display = str(val)
            if len(display) > 120:
                display = display[:120] + "…"
            print(f"      {name}: {display}")


async def _run(email: str, password: str, pin: str, country: str, args_verbose: bool = False) -> int:
    print("\n" + "=" * 68)
    print(f"  VW {country.upper()} connection test — account {email}")
    print("=" * 68)

    # Force the plain glibc-based resolver instead of aiohttp's default
    # aiodns/c-ares one. If the `aiodns` package happens to be installed
    # (a transitive dep of some `homeassistant` installs), aiohttp silently
    # switches to it, and c-ares can fail to resolve VW's hosts on some
    # systems (observed on WSL2) even though plain getaddrinfo works fine.
    # That failure looks like a connection problem but has nothing to do
    # with VW's backend — avoid it entirely for this diagnostic script.
    connector = aiohttp.TCPConnector(resolver=aiohttp.ThreadedResolver())
    async with aiohttp.ClientSession(connector=connector) as session:
        client = VWNAClient(session, email, password, spin=pin, country=country)

        print(f"\n[1/4] Authenticating against {client._base} …")
        try:
            await client.authenticate()
        except UpstreamUnavailableError as exc:
            print(f"\n  ✗ UPSTREAM 5xx — {exc}")
            print(
                "\n  This is VW's own backend answering with a server error, not a"
                "\n  wrong password (see idk.py issue #915). Re-run with --verbose"
                "\n  to see which exact HTTP call (email POST / password POST /"
                "\n  token exchange) returned the 5xx. Wait a while and retry."
            )
            interesting_headers = {
                k: v for k, v in exc.headers.items()
                if k.lower() in (
                    "server", "via", "x-request-id", "x-amzn-requestid",
                    "x-amzn-trace-id", "x-amz-cf-id", "cf-ray", "retry-after",
                    "x-correlation-id", "date", "content-type",
                )
            }
            if interesting_headers:
                print("\n  Response headers:")
                for k, v in interesting_headers.items():
                    print(f"    {k}: {v}")
            if exc.body:
                print(f"\n  Response body ({len(exc.body)} chars):")
                print("  " + exc.body.replace("\n", "\n  "))
            return 2
        except TwoFactorRequiredError as exc:
            print(f"\n  ✗ Two-factor auth required: {type(exc).__name__}: {exc}")
            print("  This script does not implement an MFA prompt yet.")
            return 3
        except RateLimitError as exc:
            print(f"\n  ✗ Rate limited: {exc}")
            return 4
        except AuthenticationError as exc:
            print(f"\n  ✗ Authentication failed: {exc}")
            return 5
        except CariadError as exc:
            print(f"\n  ✗ {type(exc).__name__}: {exc}")
            return 6
        print("  ✓ authenticated")

        print("\n[2/4] Fetching garage (vehicle list) …")
        try:
            vins = await client.get_vehicles()
        except CariadError as exc:
            print(f"  ✗ {type(exc).__name__}: {exc}")
            return 7
        if not vins:
            print("  (no vehicles returned)")
            print("  Fetching raw garage payload (masked) to see why …")
            try:
                raw = await client._get(f"{client._base}/account/v1/garage")
            except CariadError as exc:
                print(f"  ✗ raw garage fetch failed too: {type(exc).__name__}: {exc}")
            else:
                print("  " + json.dumps(_shape(raw), indent=2,
                                         ensure_ascii=False)[:3000].replace("\n", "\n  "))
                print(
                    "\n  Paste the shape above. It's masked (VIN/text hidden, only"
                    "\n  field names + types shown) — if 'vehicles' is a non-empty"
                    "\n  list, the field names inside it tell us what the parser"
                    "\n  in vw_na.py's get_vehicles() needs to look for instead of"
                    "\n  'vin'/'vehicleIdentificationNumber'."
                )
        for vin in vins:
            uuid = client._vin_to_uuid.get(vin, "?")
            nick = client._vin_to_nickname.get(vin, "")
            model = client._vin_to_model.get(vin, "")
            print(f"  ✓ VIN ...{vin[-6:]}  uuid={uuid != vin!s:<5} "
                  f"model={model!r} nickname={nick!r}")

        if pin:
            print("\n[3/4] S-PIN read-session exchange …")
            if not vins:
                print("  (skipped — no vehicle to test against)")
            else:
                try:
                    token = await client._get_read_session_token(vins[0])
                except CariadError as exc:
                    print(f"  ✗ {type(exc).__name__}: {exc}")
                    return 8
                print(f"  {'✓ session token acquired' if token else '(no token — see warning above, if any)'}")
        else:
            print("\n[3/4] S-PIN not provided — skipping read-session exchange.")

        # ── Step 4: Fetch full vehicle data (SoC, GPS, range, doors, …) ──
        print("\n[4/4] Fetching vehicle status data …")
        if not vins:
            print("  (skipped — no vehicles)")
        else:
            for vin in vins:
                print(f"\n  Vehicle ...{vin[-6:]}:")
                try:
                    vehicle_data = await client.get_status(vin)
                except CariadError as exc:
                    print(f"    ✗ {type(exc).__name__}: {exc}")
                    continue
                _display_vehicle_data(vehicle_data)
                print(f"    ✓ data retrieved")

    print("\n" + "-" * 68)
    print("Connection test finished OK.")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description="Manual VW Canada/US connection test (#915).")
    p.add_argument("--email", help="myVW account email (prompted if omitted).")
    p.add_argument("--pin", default="", help="S-PIN (optional; enables step 3).")
    p.add_argument("--country", default="ca", choices=["us", "ca"], help="us or ca (default: ca).")
    p.add_argument("--verbose", action="store_true", help="DEBUG-level logging of every HTTP step.")
    args = p.parse_args()

    _setup_logging(args.verbose)

    email = args.email or input("myVW email: ").strip()
    if not email:
        print("ERROR: email required", file=sys.stderr)
        return 1
    password = (getpass.getpass("myVW password (hidden): ")
                if sys.stdin.isatty() else sys.stdin.readline().rstrip("\n"))
    if not password:
        print("ERROR: password required", file=sys.stderr)
        return 1

    return asyncio.run(_run(email, password, args.pin, args.country, args.verbose))


if __name__ == "__main__":
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
        except Exception:  # noqa: BLE001
            pass
    raise SystemExit(main())
