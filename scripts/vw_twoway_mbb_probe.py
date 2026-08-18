#!/usr/bin/env python3
# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""VW EU Two-Way (MBB) live tester probe — for issue #1217 / #923.

WHY: On 2026-08-18 VW disabled the device_code grant for the CARIAD-BFF
two-way client 650d46ca, so the modern BFF two-way channel is dead. We found
a DURABLE alternative: the legacy MBB (Car-Net) client 9496332b still mints a
refreshable bearer with the We-Connect identity (sys=XID_APP_VW). This probe
checks, on YOUR car, whether that durable MBB bearer can (a) READ live data and
(b) open the command authorization (lock/unlock) — WITHOUT taking any action.

SAFETY:
  * Your VW ID password NEVER touches this script — you confirm the login in
    YOUR browser (device-authorization flow). The script only ever sees the
    resulting tokens.
  * The command test is auth-only: it requests the security-pin challenge and
    STOPS. It never sends your S-PIN, never locks/unlocks, never changes
    anything on the car.
  * Every VIN / token / user-id / email in the output is masked. The block it
    tells you to paste contains only HTTP status codes and yes/no flags.

RUN:
    py scripts/vw_twoway_mbb_probe.py <YOUR_VIN>

Then open the verification link it prints, confirm in your browser, and paste
the marked block into GitHub issue #1217.
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

MAL = "https://mal-1a.prd.ece.vwg-connect.com"
ISSUE = "#584"  # the VW-EU MBB two-way topic


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


def _has_data(body: str) -> bool:
    """Heuristic: a real MBB status body carries value fields, not just an
    error envelope. True only when it parses and is not a pure error."""
    try:
        j = json.loads(body)
    except ValueError:
        return False
    if not isinstance(j, dict):
        return False
    if set(j.keys()) <= {"error"}:
        return False
    return len(body) > 40


async def _get(session: Any, bearer: str, cid: str, uid: str, url: str) -> tuple[int, str]:
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
            return r.status, await r.text()
    except Exception as exc:  # noqa: BLE001
        return 0, f"conn-error: {type(exc).__name__}"


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

    def rec(label: str, status: int, extra: str = "") -> None:
        tag = "OK " if status in (200, 201) else ("--" if status == 0 else "  ")
        lines.append(f"  {label:<30} HTTP {status:<4} {tag}{extra}")

    async with ClientSession() as session:
        dag = DeviceAuthorizationGrant(
            session, MBB_DAG_CLIENT_ID, scope=MBB_DAG_SCOPE, strategy="mbb"
        )
        print("[*] Requesting device code from identity.vwgroup.io …", flush=True)
        dc = await dag.request_device_code()
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

        try:
            mbb, cid = await _mbboauth.mint_mbb_bearer(session, tokens.id_token)
        except Exception as exc:  # noqa: BLE001
            print(f"[!] MBB bearer mint failed: {_mask(exc)}")
            print("    (Please still paste THIS message into issue " + ISSUE + ".)")
            return 1

        bc = _claims(mbb.access_token)
        uid = str(bc.get("sub", ""))
        sysid = bc.get("sys", "?")
        durable = bool(mbb.refresh_token)
        bearer = mbb.access_token

        # ── reads ────────────────────────────────────────────────────────────
        st, body = await _get(session, bearer, cid, uid,
                              f"{MAL}/api/rolesrights/operationlist/v3/vehicles/{V}")
        svc_n, sub = "?", "?"
        try:
            ops = json.loads(body).get("operationList", {})
            svc_n = len(ops.get("serviceInfo", []) or [])
        except Exception:  # noqa: BLE001
            pass
        rec("reads: operationlist v3", st, f"(services={svc_n})")

        st, _ = await _get(session, bearer, cid, uid,
                          f"{MAL}/api/cs/vds/v1/vehicles/{V}/homeRegion")
        rec("reads: homeRegion", st)

        st, body = await _get(session, bearer, cid, uid,
                             f"{MAL}/api/bs/vsr/v1/vehicles/{V}/status")
        rec("reads: VSR status", st, f"has_data={'yes' if _has_data(body) else 'no'}")

        st, body = await _get(session, bearer, cid, uid,
                             f"{MAL}/api/bs/batterycharge/v1/vehicles/{V}/charger")
        rec("reads: charger", st, f"has_data={'yes' if _has_data(body) else 'no'}")

        st, body = await _get(session, bearer, cid, uid,
                             f"{MAL}/api/bs/climatisation/v1/vehicles/{V}/climater")
        rec("reads: climater", st, f"has_data={'yes' if _has_data(body) else 'no'}")

        # ── command AUTH only (safe: returns a challenge, no S-PIN, no action) ─
        for op in ("LOCK", "UNLOCK"):
            st, _ = await _get(
                session, bearer, cid, uid,
                f"{MAL}/api/rolesrights/authorization/v2/vehicles/{V}"
                f"/services/rlu_v1/operations/{op}/security-pin-auth-requested",
            )
            rec(f"command-auth: {op}", st, "(no action taken)")

    # ── the paste-safe feedback block ────────────────────────────────────────
    print("\n\n")
    print("=" * 64)
    print(f"  COPY EVERYTHING BETWEEN THE LINES INTO GITHUB ISSUE {ISSUE}")
    print("  (it contains NO password, NO VIN, NO personal data)")
    print("=" * 64)
    print("----8<---- vag-connect VW-EU MBB two-way probe ----8<----")
    print(f"bearer_minted : yes   sys={sysid}   durable_refresh={'yes' if durable else 'no'}")
    print("results:")
    for ln in lines:
        print(ln)
    print("interpretation: reads work if the VSR/charger/climater lines show")
    print("  HTTP 200 + has_data=yes; commands are available if the LOCK/UNLOCK")
    print("  command-auth lines show HTTP 200.")
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
        print("usage: py scripts/vw_twoway_mbb_probe.py <YOUR_VIN>")
        raise SystemExit(2)
    raise SystemExit(asyncio.run(main(sys.argv[1])))
