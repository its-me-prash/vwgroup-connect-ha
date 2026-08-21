#!/usr/bin/env python3
# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""SEAT / CUPRA attestation-bypass tester probe — the "MBB mix".

WHY: SEAT/CUPRA online-services (OLA) reads and commands are blocked server-side
(HTTP 403) behind Google device attestation (Firebase App Check / Play Integrity)
plus an AWS-WAF token. Reverse-engineering the CUPRA 2.21.1 app confirms EVERY OLA
data endpoint carries those headers — there is no bearer-only path IN THE APP.

BUT: the app also stores a ``carnetEnrollmentCountry`` — i.e. the car is enrolled
in VW Group's legacy Car-Net / MBB plane. The app doesn't USE that plane (it went
all-in on attested OLA), but the durable MBB device-grant (the same brand-agnostic
`9496332b` flow that works for Volkswagen) mints a bearer WITHOUT any attestation.
This probe checks, on YOUR SEAT/CUPRA car, whether that attestation-free MBB bearer
is ACCEPTED by the legacy MBB gateway — which would be a way in that sidesteps the
OLA wall entirely (reads and/or commands).

This is EXPLORATORY. We report HTTP status codes for the MBB discovery, the
operation list (what commands the car offers) and the vehicle-status read. Even a
"401 vs 403 vs 200" difference is the datapoint. Your paste-back is the data.

SAFETY:
  * Your SEAT/CUPRA password NEVER touches this script — you confirm the login in
    YOUR browser. The script only sees the resulting tokens.
  * READ-ONLY. It sends NO commands, changes nothing on the car (it only lists
    which commands the backend *offers*; it never invokes one).
  * Every VIN / token / user-id / email in the output is masked. The block it
    tells you to paste contains only host names, HTTP status codes and flags.

RUN:
    py scripts/seat_cupra_mbb_probe.py <YOUR_VIN>

Then open the verification link, confirm in your browser, and paste the marked
block into the GitHub thread.
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

ISSUE = "#464"  # CUPRA/SEAT OLA-403 tracker
# legacy MBB discovery/setter host (same EU plane VW uses)
DISCOVERY_BASE = "https://mal-1a.prd.ece.vwg-connect.com"


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


async def _hit(session: Any, bearer: str, cid: str, uid: str, url: str,
               app_name: str) -> int:
    headers = {
        "Authorization": f"Bearer {bearer}",
        "Accept": "application/json",
        "X-App-Name": app_name,
        "X-App-Version": "5.17.6",
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
    # SEAT/CUPRA never shipped a modern MBB app-name; the legacy Car-Net eRemote
    # value is the closest, and the backend keys acceptance on the bearer + VIN
    # enrollment more than the exact app-name. Probe a couple of variants.
    app_names = ["SEATCarNetEU", "CupraCarNetEU", "cz.skodaauto.connect"]

    def rec(host_label: str, status: int, note: str = "") -> None:
        verdict = {
            0: "conn-error (host unreachable from you)",
            200: "ACCEPTED + data",
            401: "token REJECTED (invalid_token)",
            403: "token accepted, no permission / not enrolled (403)",
            404: "token accepted, path/car not found (404)",
        }.get(status, "see status")
        lines.append(f"  {host_label:<48} HTTP {status:<4} {verdict} {note}")

    async with ClientSession() as session:
        # SEAT and CUPRA accounts authenticate on the cupraid.vwgroup.io realm
        # ("cupraid.vwgroup.io — CUPRA portal-redirect for SEAT/Cupra"), NOT the VW
        # realm. Pointing the device grant at identity.vwgroup.io (the default) sent
        # a CUPRA tester to a VW login that didn't know his account and forced a new
        # VW signup (@TinusNL, #464). Target the SEAT/CUPRA realm so you sign in with
        # your real SEAT ID / CUPRA ID.
        realm = "https://cupraid.vwgroup.io"
        dag = DeviceAuthorizationGrant(
            session, MBB_DAG_CLIENT_ID, scope=MBB_DAG_SCOPE, strategy="mbb",
            device_auth_url=f"{realm}/oidc/v1/device_authorization",
            token_url=f"{realm}/oidc/v1/token",
        )
        print(f"[*] Requesting MBB device code from {realm} …", flush=True)
        try:
            dc = await dag.request_device_code()
        except Exception as exc:  # noqa: BLE001
            print(f"[!] device_code request failed: {_mask(exc)}")
            print(f"    (This itself is a useful result — please paste it into {ISSUE}:")
            print("     a failure here tells us the MBB device grant won't issue for")
            print("     a SEAT/CUPRA account at all.)")
            return 1
        print("\n" + "=" * 64)
        print("  OPEN THIS LINK IN YOUR BROWSER AND CONFIRM THE LOGIN:")
        print("   ", dc.verification_uri_complete or dc.verification_uri)
        if not dc.verification_uri_complete:
            print("  (enter this code if asked:", dc.user_code, ")")
        print("  Sign in with your SEAT ID / CUPRA ID email + password.")
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
            _e = str(exc).lower()
            if "certificate_verify_failed" in _e or "self-signed" in _e or "self signed" in _e:
                print("    NOTE: that's a TLS-interception error from YOUR network —")
                print("    a corporate proxy or antivirus is re-signing HTTPS traffic to")
                print("    mbboauth-1d.prd.ece.vwg-connect.com. It's not a backend reject.")
                print("    Please re-run from a network without SSL inspection (e.g. a")
                print("    phone hotspot) so we get the real answer.")
            else:
                print(f"    (Please still paste THIS message into {ISSUE} — a mint")
                print("     failure means the MBB plane rejects SEAT/CUPRA accounts.)")
            return 1
        bc = _claims(mbb.access_token)
        uid = str(bc.get("sub", ""))
        durable = "yes" if mbb.refresh_token else "no"

        # 1) homeRegion discovery — does the MBB plane KNOW this SEAT/CUPRA VIN?
        for app in app_names:
            st = await _hit(session, mbb.access_token, cid, uid,
                            f"{DISCOVERY_BASE}/api/cs/vds/v1/vehicles/{V}/homeRegion",
                            app)
            rec(f"mal-1a /homeRegion  (X-App-Name={app})", st)

        # 2) operation list — which commands the car OFFERS on MBB (no command sent)
        st = await _hit(session, mbb.access_token, cid, uid,
                        f"{DISCOVERY_BASE}/api/rolesrights/operationlist/v3/vehicles/{V}",
                        app_names[0])
        rec("mal-1a /operationlist", st)

        # 3) vehicle-status read (VSR) — the actual live-data prize, attestation-free
        st = await _hit(session, mbb.access_token, cid, uid,
                        f"{DISCOVERY_BASE}/fs-car/bs/vsr/v1/Seat/CN/vehicles/{V}/status",
                        app_names[0])
        rec("mal-1a /fs-car/bs/vsr/v1/.../status", st)

    print("\n\n" + "=" * 64)
    print(f"  COPY EVERYTHING BETWEEN THE LINES INTO THE GITHUB THREAD ({ISSUE})")
    print("  (it contains NO password, NO VIN, NO personal data)")
    print("=" * 64)
    print("----8<---- vag-connect SEAT/CUPRA MBB-mix probe ----8<----")
    print(f"mbb_bearer_minted : yes   durable_refresh={durable}")
    print("results:")
    for ln in lines:
        print(ln)
    print("interpretation: any line that is NOT 401/conn-error means the")
    print("  attestation-free MBB bearer is ACCEPTED by the legacy plane for a")
    print("  SEAT/CUPRA car — a read/command route that sidesteps the OLA wall.")
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
        print("usage: py scripts/seat_cupra_mbb_probe.py <YOUR_VIN>")
        raise SystemExit(2)
    raise SystemExit(asyncio.run(main(sys.argv[1])))
