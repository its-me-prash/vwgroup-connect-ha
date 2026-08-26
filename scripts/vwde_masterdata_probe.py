#!/usr/bin/env python3
# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""volkswagen.de master-data + durable-MBB pre-flight tester probe (READ-ONLY).

WHY: For VW-EU cars we read supplementary data over the volkswagen.de authproxy.
Two things need confirming on a car whose owner is the PRIMARY / Car-Net-enrolled
user (not a guest on a family car):
  1. the durable-MBB pre-flight verdict from the relations read — does an enrolled
     Car-Net car report ``carnetIndicator=true`` → classify as ``eligible``?
  2. the market master-data — does the vehicle-file ``details`` endpoint return the
     model / engine / year / colour and the long ``specifications`` equipment list
     for a primary user (it 403s for a guest), and which extra portal endpoints
     serve data for an enrolled car?

SAFETY:
  * READ-ONLY. Every call is a GET. It never sends a command, never writes, never
    changes anything on the car or the account.
  * Your password is read with getpass (never shown, never stored). The one-time
    code volkswagen.de emails you is typed here only to finish the login.
  * The block it prints for pasting contains ONLY status codes, presence flags and
    field-name structure — NO password, NO VIN, NO number plate, NO field values,
    NO personal data. The VIN is shown to YOU (masked to the last 4) only so you
    can tell which car it read; that masked form is safe to paste.

RUN (from a checkout of this repo, with its dependencies installed):
    py scripts/vwde_masterdata_probe.py your.email@example.com

Then enter your volkswagen.de password when asked, and the code VW emails you.
Paste the marked block into the GitHub issue you were pointed at.
"""
from __future__ import annotations

import asyncio
import getpass
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

ISSUE = "#1165"  # the modern-MBB / VW-EU capability topic


def _mask(s: object) -> str:
    s = re.sub(r"[A-HJ-NPR-Z0-9]{11,17}", lambda m: "***" + m.group(0)[-4:], str(s))
    return re.sub(r"[\w.+-]+@[\w.-]+\.\w+", "***@***", s)


async def _raw_get(conn, session, url: str, accept: str = "application/json"):
    from aiohttp import ClientTimeout

    from custom_components.vag_connect.cariad.auth._website_authproxy import (
        _REDIRECT_URL,
    )
    headers = conn._headers({
        "Accept": accept, "user-id": "__userId__", "Referer": _REDIRECT_URL,
    })
    try:
        async with session.get(
            url, headers=headers, timeout=ClientTimeout(total=25),
        ) as resp:
            status = resp.status
            try:
                body = await resp.json(content_type=None)
            except Exception:  # noqa: BLE001
                body = None
            return status, body
    except Exception as exc:  # noqa: BLE001
        return 0, {"_err": type(exc).__name__}


async def main(email: str) -> int:
    import aiohttp

    from custom_components.vag_connect.cariad import _authproxy as ap
    from custom_components.vag_connect.cariad.auth._website_authproxy import (
        WebsiteAuthProxyConnector,
        _CHARGING_PATH,
        _MAINTENANCE_PATH,
        _SITE_BASE,
    )

    password = getpass.getpass("volkswagen.de password (hidden): ")

    lines: list[str] = []

    def rec(label: str, status: int, extra: str = "") -> None:
        tag = "OK " if status in (200, 201) else ("--" if status == 0 else "  ")
        lines.append(f"  {label:<26} HTTP {status:<4} {tag}{extra}")

    connector = aiohttp.TCPConnector(resolver=aiohttp.ThreadedResolver())
    async with aiohttp.ClientSession(connector=connector) as session:
        conn = WebsiteAuthProxyConnector(session, email, password, brand="volkswagen")
        print("[*] Signing in to volkswagen.de …", flush=True)
        try:
            step = await conn.begin_login()
        except Exception as exc:  # noqa: BLE001
            print(f"[!] login failed: {_mask(exc)}")
            return 1
        if step == "otp_required":
            code = input("Enter the code volkswagen.de just emailed you: ").strip()
            try:
                ok = await conn.submit_otp(code)
            except Exception as exc:  # noqa: BLE001
                print(f"[!] code rejected: {_mask(exc)}")
                return 1
            if not ok:
                print("[!] login did not complete")
                return 1
        elif step != "ok":
            print(f"[!] unexpected login step: {step}")
            return 1
        print("[*] Signed in.", flush=True)

        vins = await conn.list_vehicle_vins()
        if not vins:
            print("[!] no vehicles on this account")
            return 1
        vin = vins[0]

        # relations → pre-flight MBB eligibility (the inputs are not personal)
        rels = await conn.get_relations()
        gdc = conn._gdc(vin)
        verdict = conn.mbb_eligibility.get(vin, "unknown")
        rel = None
        if rels is not None:
            rel = next((v for v in rels.vehicles if v.vin == vin), None)
        elig_inputs = ""
        if rel is not None:
            elig_inputs = (
                f"backend={rel.mod_backend} carnet={rel.carnet_indicator} "
                f"role={rel.role} enrollment={rel.enrollment_status} "
                f"primaryCar={rel.primary_car}"
            )

        # master-data: details (primary-only) + data (guest-readable)
        st_d, body_d = await _raw_get(conn, session, ap.build_vehicle_details_url(vin))
        specs = ""
        if st_d == 200 and isinstance(body_d, dict):
            present = [k for k in ("modelName", "engine", "modelYear",
                                   "exteriorColorText") if body_d.get(k)]
            sp = body_d.get("specifications")
            if isinstance(sp, list) and sp:
                item_keys = sorted({k for it in sp[:5] if isinstance(it, dict)
                                    for k in it})
                specs = f"fields={'+'.join(present)} specs=[{len(sp)}x {{{','.join(item_keys)}}}]"
            else:
                specs = f"fields={'+'.join(present)} specs=none"
        rec("master-data: details", st_d, specs)

        st_x, body_x = await _raw_get(conn, session, ap.build_vehicle_data_url(vin))
        data_fields = ""
        if st_x == 200 and isinstance(body_x, dict):
            data_fields = "fields=" + "+".join(
                k for k in ("modelName", "exteriorColor") if body_x.get(k))
        rec("master-data: data", st_x, data_fields)

        # which extra portal endpoints serve data for an enrolled car
        def wc(path):
            return ap.build_authproxy_url(path, realm="vwag-weconnect",
                                          resource_host="myvw-vcf-prod", gdc=gdc)
        probes = [
            ("images", ap.build_vehicle_images_url(vin)),
            ("charging/status", f"{_SITE_BASE}{_CHARGING_PATH.format(vin=vin)}"),
            ("maintenance/status", f"{_SITE_BASE}{_MAINTENANCE_PATH.format(vin=vin)}"),
            ("warninglights/last", ap.build_warninglights_url(vin, gdc)),
            ("transactionhistory", ap.build_transactionhistory_url(vin, gdc)),
            ("usercapabilities", ap.build_usercapabilities_url(vin, gdc)),
            ("parkingposition", ap.build_parkingposition_url(vin, gdc)),
            ("tripdata/cyclic/last", wc(f"vehicles/{vin}/tripdata/cyclic/last")),
            ("tripdata/longterm/last", wc(f"vehicles/{vin}/tripdata/longterm/last")),
            ("selectivestatus(all)", wc(f"vehicles/{vin}/selectivestatus?jobs=all")),
            ("position", wc(f"vehicles/{vin}/position")),
            ("climater/status", wc(f"vehicles/{vin}/climater/status")),
            ("departuretimers", wc(f"vehicles/{vin}/departuretimers")),
            ("fuel/status", wc(f"vehicles/{vin}/fuel/status")),
            ("measurements/status", wc(f"vehicles/{vin}/measurements/status")),
        ]
        for name, url in probes:
            st, body = await _raw_get(conn, session, url, accept="*/*")
            has = "yes" if isinstance(body, (dict, list)) and body and not (
                isinstance(body, dict) and set(body) <= {"error", "code", "message", "_err"}
            ) else "no"
            rec(name, st, f"data={has}" if st == 200 else "")

    print("\n\n" + "=" * 64)
    print(f"  COPY EVERYTHING BETWEEN THE LINES INTO GITHUB ISSUE {ISSUE}")
    print("  (it contains NO password, NO VIN, NO number plate, NO field values)")
    print("=" * 64)
    print("----8<---- vag-connect vw.de master-data probe ----8<----")
    print(f"vehicle(masked) : {_mask(vin)}   (of {len(vins)} on the account)")
    print(f"mbb_pre-flight  : {verdict}")
    if elig_inputs:
        print(f"  inputs        : {elig_inputs}")
    print("results:")
    for ln in lines:
        print(ln)
    print("interpretation: 'eligible' + master-data details HTTP 200 with a specs")
    print("  list confirms the primary-user path; any endpoint showing data=yes is")
    print("  a live read we can wire.")
    print("----8<---- end — paste the block above ----8<----")
    print("=" * 64)
    return 0


if __name__ == "__main__":
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
        except Exception:  # noqa: BLE001
            pass
    if len(sys.argv) < 2:
        print("usage: py scripts/vwde_masterdata_probe.py <your.email@example.com>")
        raise SystemExit(2)
    raise SystemExit(asyncio.run(main(sys.argv[1])))
