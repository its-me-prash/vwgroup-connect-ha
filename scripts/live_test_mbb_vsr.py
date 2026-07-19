#!/usr/bin/env python3
# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
"""One-shot MBB VSR read live-test — Golf 7 GTE (legacy Car-Net / pre-Cariad).

Answers ONE question end-to-end: does the durable MBB vehicle-status read
(``/fs-car/bs/vsr/v1/{Brand}/{country}/vehicles/{vin}/status``) still return
DATA or a 403 for a real account + VIN, on the exact host our shipped
``_get_status_via_mbb_vsr`` uses?

It runs the full chain in one process, nothing touches disk:
  1. IDK login  (WeConnect-ID native client + ``mbb`` scope → VW-namespace id_token)
  2. MBB register + exchange  → durable MBB vwToken (sc2:fal)
  3. homeRegion lookup  → per-VIN read base (region host, else msg.volkswagen.de)
  4. operationList  → is the vehicle-status service licensed? (expired sub == 403s)
  5. VSR status GET  → the actual read; decodes tank %, total range, AdBlue,
     SoC and dumps every field id returned so nothing is missed
  6. charger / climater / position  → the sibling reads, for a fuller picture

The MBB access token lives only in memory for this run and is never printed,
logged, or written to a file.

Usage (PowerShell):
    py scripts/live_test_mbb_vsr.py --vin WVWZZZ... --email you@example.com
    py scripts/live_test_mbb_vsr.py            # prompts for VIN + email
    py scripts/live_test_mbb_vsr.py --mfa 123456      # if the account has 2FA
    py scripts/live_test_mbb_vsr.py --country CH      # non-DE market segment

The VW account password is read via a hidden getpass prompt — paste it when
asked; it is not echoed and not stored.
"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_REPO = _HERE.parent
sys.path.insert(0, str(_HERE))   # so we can import get_mbb_token as a module
sys.path.insert(0, str(_REPO))

# get_mbb_token's import-time code stubs Home Assistant and loads the real
# IDKAuth + BrandConfig, then exposes the proven IDK→register→exchange helpers.
# Reusing it means this live-test authenticates through the SAME code the
# integration ships — no parallel auth to drift out of sync.
import get_mbb_token as gmt  # noqa: E402
import aiohttp  # noqa: E402

_MAL = "https://mal-1a.prd.ece.vwg-connect.com"
_MSG_DEFAULT = "https://msg.volkswagen.de"

# VSR field IDs (mirror custom_components/vag_connect/cariad/_mbb.py). Labelled
# so a successful read prints human values, not just hex ids.
_VSR_FIELDS = {
    "0x030103000A": ("Tank level", "%"),
    "0x0301030005": ("Total range", "km"),
    "0x02040C0001": ("AdBlue range", "km"),
    "0x0301030006": ("Primary range", "km"),
    "0x0301030002": ("State of charge", "%"),
    "0x0101010001": ("Odometer", "km"),
    "0x0301030008": ("Fuel range", "km"),
}


def _bearer(token: str, x_client: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "User-Agent": gmt._VW_USER_AGENT,
        "X-App-Name": "Volkswagen",
        "X-App-Version": "3.51.1",
        "X-Client-Id": x_client,
    }


async def _get(session, url, headers):
    async with session.get(url, headers=headers) as resp:
        return resp.status, await resp.text()


async def _resolve_read_base(session, vin, headers) -> tuple[str, int]:
    """homeRegion → per-VIN read base. Mirrors _mbb_resolve_read_base."""
    url = f"{_MAL}/api/cs/vds/v1/vehicles/{vin}/homeRegion"
    try:
        status, body = await _get(session, url, headers)
    except Exception as exc:  # noqa: BLE001
        print(f"   homeRegion lookup errored ({exc}); using default base")
        return _MSG_DEFAULT, 0
    if status != 200:
        return _MSG_DEFAULT, status
    try:
        import json  # noqa: PLC0415

        data = json.loads(body)
        content = (
            data.get("homeRegion", {}).get("baseUri", {}).get("content")
        )
    except Exception:  # noqa: BLE001
        content = None
    if not content:
        return _MSG_DEFAULT, status
    # Strip any trailing path; Cariad hosts fall back to the MBB default.
    base = content.rstrip("/")
    if "cariad.digital" in base or "bff.cariad" in base:
        return _MSG_DEFAULT, status
    return base, status


def _decode_vsr(body: str) -> list[tuple[str, str]]:
    """Pull (label, value+unit) pairs out of a VSR StoredVehicleDataResponse."""
    import json  # noqa: PLC0415

    out: list[tuple[str, str]] = []
    try:
        data = json.loads(body)
    except Exception:  # noqa: BLE001
        return out
    try:
        groups = (
            data["StoredVehicleDataResponse"]["vehicleData"]["data"]
        )
    except Exception:  # noqa: BLE001
        return out
    for grp in groups if isinstance(groups, list) else []:
        for fld in grp.get("field", []) if isinstance(grp, dict) else []:
            if not isinstance(fld, dict):
                continue
            fid = str(fld.get("id", ""))
            val = fld.get("value")
            unit = fld.get("unit", "") or ""
            label = _VSR_FIELDS.get(fid, (fid, ""))[0]
            out.append((label, f"{val}{(' ' + unit) if unit else ''} [{fid}]"))
    return out


def _verdict(status: int) -> str:
    if 200 <= status < 300:
        return "✓ DATA"
    if status == 403:
        return "✗ 403 FORBIDDEN"
    if status == 0:
        return "✗ network error"
    return f"✗ HTTP {status}"


async def _run(email: str, password: str, mfa: str | None, vin: str,
               brand: str, country: str) -> int:
    vin = vin.strip().upper()
    print("\n" + "=" * 72)
    print(f"  MBB VSR live-test — VIN ...{vin[-6:]}  brand={brand}  country={country}")
    print("=" * 72)

    async with aiohttp.ClientSession() as session:
        # ── 1-3: auth (reuses the integration's IDK→register→exchange) ──
        print("\n[1/6] IDK login (WeConnect-ID native, mbb scope) …")
        try:
            tokens = await gmt._idk_login(
                session, gmt._BRAND_VW_NATIVE_MBB, email, password, mfa
            )
        except gmt.TwoFactorRequiredError:
            print("  ✗ 2FA required — re-run with --mfa <code>")
            return 2
        except gmt.TermsAndConditionsError:
            print("  ✗ Account has unaccepted Terms — accept in the We Connect app first.")
            return 3
        except gmt.MarketingConsentError:
            print("  ✗ Marketing-consent decision pending — resolve it in the We Connect app first.")
            return 4
        except gmt.RateLimitError:
            print("  ✗ Rate-limited (429). Wait ~15 min.")
            return 5
        except gmt.AuthenticationError as exc:
            print(f"  ✗ IDK auth failed: {exc}")
            return 6
        print(f"  ✓ id_token ({len(tokens.id_token)} chars)")

        print("[2/6] Register MBB client (brand=VW) …")
        try:
            x_client = await gmt._mbb_register(session, brand="VW")
        except RuntimeError as exc:
            print(f"  ✗ register failed: {exc}")
            return 7
        print(f"  ✓ X-Client-Id …{x_client[-10:]}")

        print("[3/6] Exchange id_token → durable MBB vwToken …")
        try:
            mbb = await gmt._mbb_exchange(session, tokens.id_token, x_client)
        except RuntimeError as exc:
            print(f"  ✗ exchange failed: {exc}")
            print("     (id_token OK + register OK, but MBB rejected the exchange —")
            print("      account may lack the sub, or the VIN isn't MBB-linked.)")
            return 8
        access = mbb.get("access_token", "")
        if not access:
            print(f"  ✗ exchange returned no access_token: {mbb}")
            return 8
        print(f"  ✓ MBB vwToken ({len(access)} chars, expires_in={mbb.get('expires_in')}s)")

        headers = _bearer(access, x_client)

        # ── 4: homeRegion → read base ──
        print("[4/6] homeRegion → read base …")
        read_base, hr_status = await _resolve_read_base(session, vin, headers)
        note = "default" if read_base == _MSG_DEFAULT else "region host"
        print(f"  → read_base = {read_base}  ({note}, homeRegion HTTP {hr_status})")

        # ── 5: operationList (licensing) ──
        print("[5/6] operationList (is vehicle-status licensed?) …")
        op_url = f"{_MAL}/api/rolesrights/operationlist/v3/vehicles/{vin}"
        op_status, op_body = await _get(session, op_url, headers)
        if 200 <= op_status < 300:
            en = op_body.count('"Enabled"') + op_body.count(">Enabled<")
            dis = op_body.count('"Disabled"') + op_body.count(">Disabled<")
            print(f"  {_verdict(op_status)} — services Enabled≈{en} Disabled≈{dis}")
            if en == 0 and dis > 0:
                print("     ⚠ every service Disabled → We Connect subscription looks"
                      " expired; the VSR read below will likely 403.")
        else:
            print(f"  {_verdict(op_status)}")

        # ── 6: the VSR read + siblings ──
        print("[6/6] VSR status read (the target) + siblings …\n")
        seg = brand  # brand segment; VW/Audi passed verbatim like the integration
        targets = {
            "vehicle_status_VSR":
                f"{read_base}/fs-car/bs/vsr/v1/{seg}/{country}/vehicles/{vin}/status",
            "charger":
                f"{read_base}/fs-car/bs/batterycharge/v1/{seg}/{country}/vehicles/{vin}/charger",
            "climater":
                f"{read_base}/fs-car/bs/climatisation/v1/{seg}/{country}/vehicles/{vin}/climater",
            "position":
                f"{read_base}/fs-car/bs/cf/v1/{seg}/{country}/vehicles/{vin}/position",
        }
        vsr_status = None
        vsr_body = ""
        for name, url in targets.items():
            status, body = await _get(session, url, headers)
            print(f"  {name:22s} {_verdict(status)}")
            if name == "vehicle_status_VSR":
                vsr_status, vsr_body = status, body

    # ── verdict ──
    print("\n" + "-" * 72)
    if vsr_status is not None and 200 <= vsr_status < 300:
        print("RESULT: ✓ MBB VSR read is ALIVE for this car — decoded fields:")
        fields = _decode_vsr(vsr_body)
        if fields:
            for label, val in fields:
                print(f"   • {label:16s} {val}")
        else:
            print("   (200 but no parseable fields — raw first 400 chars:)")
            print("   " + vsr_body[:400].replace("\n", " "))
        print("\n→ Ship confidence: _get_status_via_mbb_vsr will return real data")
        print("  for legacy Car-Net cars. Confirm the decoded values match the car.")
        return 0
    if vsr_status == 403:
        print("RESULT: ✗ VSR read 403s. Either the We Connect sub is expired/inactive")
        print("  (see operationList above) or MBB no longer serves /bs/vsr for this")
        print("  account/region. The read path stays EU-Data-Act-portal only.")
        return 20
    print(f"RESULT: ✗ VSR read returned {_verdict(vsr_status or 0)} — inconclusive; "
          "capture the body and dig in.")
    return 21


def main() -> int:
    p = argparse.ArgumentParser(description="One-shot MBB VSR read live-test (Golf 7 GTE).")
    p.add_argument("--vin", help="Vehicle VIN (prompted if omitted).")
    p.add_argument("--email", help="VW account email (prompted if omitted).")
    p.add_argument("--mfa", help="2FA code (only if the account has 2FA).")
    p.add_argument("--brand", default="VW", help="MBB brand segment (default VW).")
    p.add_argument("--country", default="DE", help="Market segment (default DE; e.g. CH/AT).")
    args = p.parse_args()

    email = args.email or input("VW account email: ").strip()
    if not email:
        print("ERROR: email required", file=sys.stderr)
        return 1
    vin = args.vin or input("Golf 7 GTE VIN: ").strip()
    if not vin:
        print("ERROR: VIN required", file=sys.stderr)
        return 1
    password = (
        getpass.getpass("VW account password (hidden): ")
        if sys.stdin.isatty()
        else sys.stdin.readline().rstrip("\n")
    )
    if not password:
        print("ERROR: password required", file=sys.stderr)
        return 1

    return asyncio.run(
        _run(email, password, args.mfa, vin, args.brand, args.country)
    )


if __name__ == "__main__":
    sys.exit(main())
