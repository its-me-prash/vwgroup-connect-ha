#!/usr/bin/env python3
# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""VW North America attestation-bypass tester probe — for issue #1215.

WHY: Since ~2026-08-13 VW's North-America plane requires Play-Integrity
attestation that Home Assistant cannot produce, so US vehicles stopped working.
BUT the legacy MBB device-grant path mints a durable bearer WITHOUT any
attestation, and that bearer's audience includes VW's NA cloud host
(ha-5a.prd.nar.vwg.vwautocloud.net). This probe checks, on YOUR US/CA car,
whether that attestation-free bearer is actually ACCEPTED by the NA plane —
which would be a way back in.

This is EXPLORATORY: we do not yet know the exact NA endpoint paths, so the
probe reports HTTP status codes for a range of candidates. Even a "401 vs 403"
difference tells us whether the token is accepted. Your paste-back is the data.

SAFETY:
  * Your VW ID password NEVER touches this script — you confirm the login in
    YOUR browser. The script only sees the resulting tokens.
  * READ-ONLY. It sends no commands, changes nothing on the car.
  * Every VIN / token / user-id / email in the output is masked. The block it
    tells you to paste contains only host names, HTTP status codes and flags.

RUN:
    py scripts/vw_na_mbb_probe.py <YOUR_VIN>

Then open the verification link, confirm in your browser, and paste the marked
block into GitHub issue #1215.
"""
from __future__ import annotations

import asyncio
import base64
import json
import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

ISSUE = "#1215"
# classic Car-Net NA data hosts (from our vw_na.py) — for comparison
CONVEH = ["https://b-h-s.spr.us00.p.con-veh.net", "https://b-h-s.spr.ca00.p.con-veh.net"]


def _mask(s: Any) -> str:
    s = re.sub(r"[A-HJ-NPR-Z0-9]{11,17}", lambda m: "***" + m.group(0)[-4:], str(s))
    return re.sub(r"[\w.+-]+@[\w.-]+\.\w+", "***@***", s)


def _claims(tok: str) -> dict[str, Any]:
    try:
        p = tok.split(".")[1]
        p += "=" * (-len(p) % 4)
        return json.loads(base64.urlsafe_b64decode(p))
    except Exception:  # noqa: BLE001
        return {}


async def _hit(session: Any, bearer: str, cid: str, uid: str, url: str) -> int:
    headers = {
        "Authorization": f"Bearer {bearer}",
        "Accept": "application/json",
        "X-App-Name": "Volkswagen",
        "X-App-Version": "3.51.1",
        "User-Agent": "okhttp/3.14.9",
        "X-Client-Id": cid,
        "X-MbbUserId": uid,
    }
    try:
        async with session.get(url, headers=headers) as r:
            return r.status
    except Exception:  # noqa: BLE001
        return 0


async def main(vin: str) -> int:
    from aiohttp import ClientSession

    from custom_components.vag_connect.cariad.auth import _mbboauth
    from custom_components.vag_connect.cariad.auth._device_grant import (
        DeviceAuthorizationGrant,
        MBB_DAG_CLIENT_ID,
        MBB_DAG_SCOPE,
    )

    V = vin.strip().upper()
    lines: list[str] = []

    def rec(host_label: str, status: int, note: str = "") -> None:
        verdict = {
            0: "conn-error (host unreachable from you)",
            200: "ACCEPTED + data",
            401: "token REJECTED (invalid_token)",
            403: "token accepted, no permission (403)",
            404: "token accepted, path/car not found (404)",
        }.get(status, "see status")
        lines.append(f"  {host_label:<46} HTTP {status:<4} {verdict} {note}")

    async with ClientSession() as session:
        dag = DeviceAuthorizationGrant(
            session, MBB_DAG_CLIENT_ID, scope=MBB_DAG_SCOPE, strategy="mbb"
        )
        print("[*] Requesting device code from identity.vwgroup.io …", flush=True)
        try:
            dc = await dag.request_device_code()
        except Exception as exc:  # noqa: BLE001
            print(f"[!] device_code request failed: {_mask(exc)}")
            print(f"    (This itself is a useful result — please paste it into {ISSUE}:")
            print("     it may mean US accounts must use identity.na.vwgroup.io.)")
            return 1
        print("\n" + "=" * 64)
        print("  OPEN THIS LINK IN YOUR BROWSER AND CONFIRM THE LOGIN:")
        print("   ", dc.verification_uri_complete or dc.verification_uri)
        if not dc.verification_uri_complete:
            print("  (enter this code if asked:", dc.user_code, ")")
        print("  Your password stays in the browser — never in this script.")
        print("=" * 64 + "\n", flush=True)

        try:
            tokens = await dag.poll_for_tokens(
                dc.device_code, interval=dc.interval, expires_in=dc.expires_in
            )
        except Exception as exc:  # noqa: BLE001
            print(f"[!] login not confirmed / failed: {_mask(exc)}")
            return 1

        # which hosts does YOUR token's audience actually name?
        aud = _claims(tokens.id_token).get("aud", [])
        aud = aud if isinstance(aud, list) else [aud]
        na_hosts = [a for a in aud if isinstance(a, str) and a.startswith("http")
                    and ("nar" in a or "vwautocloud" in a or "na." in a)]

        try:
            mbb, cid = await _mbboauth.mint_mbb_bearer(session, tokens.id_token)
        except Exception as exc:  # noqa: BLE001
            print(f"[!] MBB bearer mint failed: {_mask(exc)}")
            print(f"    (Please still paste THIS message into issue {ISSUE}.)")
            return 1
        bc = _claims(mbb.access_token)
        uid = str(bc.get("sub", ""))

        # 1. the modern NA plane host(s) named in the token's own audience
        for host in na_hosts or ["https://ha-5a.prd.nar.vwg.vwautocloud.net"]:
            base = host.rstrip("/")
            for path in (f"/vehicle/v1/vehicles/{V}/selectivestatus?jobs=access,charging",
                         "/vehicle/v1/vehicles", f"/vehicles/{V}/status"):
                st = await _hit(session, mbb.access_token, cid, uid, base + path)
                rec(f"{base.split('//')[1][:24]}{path.split('?')[0][:20]}", st)

        # 2. classic con-veh NA (comparison — different audience, likely rejected)
        for host in CONVEH:
            st = await _hit(session, mbb.access_token, cid, uid,
                           f"{host}/api/cs/vds/v1/vehicles/{V}/homeRegion")
            rec(f"{host.split('//')[1][:24]}/homeRegion", st)

    print("\n\n" + "=" * 64)
    print(f"  COPY EVERYTHING BETWEEN THE LINES INTO GITHUB ISSUE {ISSUE}")
    print("  (it contains NO password, NO VIN, NO personal data)")
    print("=" * 64)
    print("----8<---- vag-connect VW-NA MBB bypass probe ----8<----")
    print(f"bearer_minted : yes   durable_refresh={'yes' if mbb.refresh_token else 'no'}")
    print(f"NA hosts in your token audience: {na_hosts or '(none — token had no NA host!)'}")
    print("results:")
    for ln in lines:
        print(ln)
    print("interpretation: any line that is NOT 401/conn-error means the")
    print("  attestation-free bearer is ACCEPTED by that NA host — the way back in.")
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
        print("usage: py scripts/vw_na_mbb_probe.py <YOUR_VIN>")
        raise SystemExit(2)
    raise SystemExit(asyncio.run(main(sys.argv[1])))
