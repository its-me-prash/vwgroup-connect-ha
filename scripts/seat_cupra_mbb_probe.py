#!/usr/bin/env python3
# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""SEAT / CUPRA attestation-bypass tester probe — the "MBB mix" + BFF check.

WHY: SEAT/CUPRA online-services (OLA) reads and commands are blocked server-side
(HTTP 403) behind Google device attestation (Firebase App Check / Play Integrity)
plus an AWS-WAF token. Reverse-engineering the CUPRA/SEAT apps confirms EVERY OLA
data endpoint carries those headers — there is no bearer-only path IN THE APP.

BUT the SEAT/CUPRA cars are enrolled in VW Group's legacy Car-Net / MBB plane, and
there IS a browser sign-in client that is NOT shipped in either mobile app — the
SEAT/CUPRA web-SSO client (id supplied at runtime, see _load_client_id below).
Because it is a browser client it carries NO
Play-Integrity attestation. Live probing (2026-08-22) confirmed it is device-code
capable on the SEAT realm of ``identity.vwgroup.io`` and is a public client (no
secret): the full RFC-8628 device grant works end-to-end up to the browser-approve.

What we do NOT yet know — and what THIS probe answers with your one approval — is
which backend the resulting token actually reaches:
  * "old" / MBB durable path: does the id_token exchange at the legacy MBB OAuth
    backend (aud VWGMBB01DELIV1) into a durable, refreshable bearer that the
    mal-1a Car-Net plane accepts?  → a durable two-way (command) channel for
    SEAT/CUPRA, the same shape that already works for Volkswagen.
  * modern BFF path: is the raw device-grant access token accepted by
    ``emea.bff.cariad.digital`` (the CARIAD BFF) at all?

Even a "401 vs 403 vs 200" difference on any line is the datapoint. Your paste-back
is the data.

SAFETY:
  * Your SEAT/CUPRA password NEVER touches this script — you confirm the login in
    YOUR browser. The script only sees the resulting tokens.
  * READ-ONLY. It sends NO commands, changes nothing on the car (it only lists
    which commands the backend *offers*; it never invokes one).
  * Every VIN / token / user-id / email in the output is masked. The block it
    tells you to paste contains only host names, HTTP status codes and flags.

RUN (with a car on the account):
    py scripts/seat_cupra_mbb_probe.py <YOUR_VIN>
RUN (login-only, no car — tests sign-in + token mint + backend acceptance):
    py scripts/seat_cupra_mbb_probe.py

Then open the verification link, confirm in your browser, and paste the marked
block back. Your password is entered ONLY in your browser at the VW Group login
page — it never reaches this script.
"""
from __future__ import annotations

import asyncio
import base64
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

ISSUE = "#464"  # CUPRA/SEAT OLA-403 tracker

# ── The lever ────────────────────────────────────────────────────────────────
# The SEAT/CUPRA *web* SSO client (the one cupraid.vwgroup.io redirects to in a
# browser). It is NOT present in either mobile APK (com.cupra.mycupra /
# com.seat.myseat.ola ship different app clients) → being a browser client it
# carries no Play-Integrity attestation. Live-probed 2026-08-22: device-code
# capable, SEAT realm, public client (token endpoint returns
# authorization_pending).
#
# The client id itself is kept OUT of this tracked file (competitive / anti-scrape
# — see memory vag_connect_seatcupra_764_lever). It is read at runtime from
# ``VAGC_SEATCUPRA_CLIENT`` or a local, gitignored private file. It graduates into
# the integration only once a tester confirms the minted token reaches a backend.
def _normalize_client_id(raw: str) -> str:
    """Tolerate the common paste mistakes when supplying the client id.

    A tester who drops the whole ``VAGC_SEATCUPRA_CLIENT=<id>`` line into the
    local file (instead of just the bare id) would otherwise send that entire
    string as the client id — VW then answers ``400 invalid_request: The legal
    entity is missing or invalid`` (a confusing message for a malformed client;
    reproduced live, #464). A real client id never contains ``=``, so if we see
    one we keep only the part after it. Also strips wrapping quotes/whitespace.
    """
    s = raw.strip().strip('"').strip("'").strip()
    if "=" in s:
        s = s.split("=", 1)[1].strip().strip('"').strip("'").strip()
    return s


def _load_client_id() -> str:
    v = _normalize_client_id(os.environ.get("VAGC_SEATCUPRA_CLIENT", ""))
    if v:
        return v
    for _p in (
        os.path.expanduser("~/.claude/private/seatcupra_client.txt"),
        os.path.join(os.path.dirname(os.path.abspath(__file__)), ".seatcupra_client.local"),
    ):
        try:
            with open(_p, encoding="utf-8") as _fh:
                _s = _normalize_client_id(_fh.read())
                if _s:
                    return _s
        except OSError:
            pass
    raise SystemExit(
        "[!] SEAT/CUPRA web client id not found. Put JUST the id (one line, no\n"
        "    'VAGC_SEATCUPRA_CLIENT=' prefix and no quotes) in\n"
        "    ~/.claude/private/seatcupra_client.txt or scripts/.seatcupra_client.local,\n"
        "    or set the VAGC_SEATCUPRA_CLIENT environment variable.")


# Same load-bearing ``mbb`` scope that mints the VWGMBB01DELIV1-aud id_token on
# Volkswagen — the key to the legacy MBB exchange.
SEATCUPRA_MBB_SCOPE = "openid profile mbb cars"

# The shared VW Group IDP. The *client* — not the host — selects the SEAT realm;
# the branded cupraid.vwgroup.io URL is only a login skin and is NOT an OIDC
# issuer (pointing the device grant at it returns a non-JSON page, which is why
# the previous revision failed before the login screen even appeared).
IDP = "https://identity.vwgroup.io"

# legacy MBB discovery/setter host (same EU plane VW uses)
DISCOVERY_BASE = "https://mal-1a.prd.ece.vwg-connect.com"
# #464 — the MBB exchange bearer's aud is actually ``mal.prd.ece`` (NOT ``-1a``,
# which is only the VW setter) + ``ha-5a…vwautocloud.net``. bbr111's mal-1a reads
# came back 403/404; those may be a wrong-host artifact, so we also hit the host
# the bearer is genuinely audienced for.
DISCOVERY_BASE_ALT = "https://mal.prd.ece.vwg-connect.com"
# modern CARIAD BFF — the attestation-walled plane; we probe it only to record
# whether the device-grant bearer is accepted (200) or walled (401/403).
BFF_BASE = "https://emea.bff.cariad.digital"
# OLA — the SEAT/CUPRA online-services plane the mobile app actually drives for
# reads AND commands (grounded in com.cupra.mycupra / com.seat.myseat.ola: the
# apps reference ola.prod.code.seat.cloud.vwgroup.com as primary, emea.bff.cariad
# as secondary). OLA sits behind Firebase App Check + an AWS-WAF token, so a
# bearer-only hit is EXPECTED to 403 (the wall, not the token). The datapoint:
# 200 = the web-client bearer somehow bypasses the wall (jackpot); 401 = the
# token itself is rejected; 403 = walled as expected.
OLA_BASE = "https://ola.prod.code.seat.cloud.vwgroup.com"


def _mask(s: Any) -> str:
    s = str(s)
    # UUIDs (user ids, device ids) — redact before the VIN pass so the paste
    # block never carries a personal identifier.
    s = re.sub(
        r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}",
        "***-uuid-***", s)
    s = re.sub(r"[A-HJ-NPR-Z0-9]{11,17}", lambda m: "***" + m.group(0)[-4:], s)
    return re.sub(r"[\w.+-]+@[\w.-]+\.\w+", "***@***", s)


def _claims(tok: str) -> dict[str, Any]:
    try:
        p = tok.split(".")[1]
        p += "=" * (-len(p) % 4)
        return json.loads(base64.urlsafe_b64decode(p))
    except Exception:  # noqa: BLE001
        return {}


def _aud_str(claims: dict[str, Any]) -> str:
    """A masked, human-readable view of the token audience — the single most
    telling field (it names the backend the token is FOR)."""
    aud = claims.get("aud")
    if isinstance(aud, list):
        aud = ",".join(str(a) for a in aud)
    return _mask(aud) if aud else "(none)"


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


async def _hit_bff(session: Any, bearer: str, url: str) -> tuple[int, str]:
    """Minimal CARIAD-BFF GET → (status, short body). No attestation headers are
    sent on purpose: we want to know whether a bearer ALONE is enough. The body
    on a non-200 tells the reasons apart (clientId-not-whitelisted vs no-vehicle
    vs a transient 5xx)."""
    headers = {
        "Authorization": f"Bearer {bearer}",
        "Accept": "application/json",
        "User-Agent": "okhttp/4.12.0",
    }
    try:
        async with session.get(url, headers=headers) as r:
            body = ""
            try:
                body = (await r.text())[:600]
            except Exception:  # noqa: BLE001
                pass
            return r.status, body
    except Exception:  # noqa: BLE001
        return 0, ""


async def _hit_ola(session: Any, bearer: str, url: str) -> tuple[int, str]:
    """Minimal OLA GET → (status, short body). No App-Check / WAF token is sent
    (we do not have one without the attested app), so a 403 is expected; a 200 or
    a 401 is the informative outcome."""
    headers = {
        "Authorization": f"Bearer {bearer}",
        "Accept": "application/json",
        "User-Agent": "okhttp/4.12.0",
    }
    try:
        async with session.get(url, headers=headers) as r:
            body = ""
            try:
                body = (await r.text())[:600]
            except Exception:  # noqa: BLE001
                pass
            return r.status, body
    except Exception:  # noqa: BLE001
        return 0, ""


async def main(vin: str) -> int:
    from aiohttp import ClientSession

    from custom_components.vag_connect.cariad.auth import _mbboauth
    from custom_components.vag_connect.cariad.auth._device_grant import (
        DeviceAuthorizationGrant,
    )

    V = vin.strip().upper()
    has_vin = bool(V)
    lines: list[str] = []
    # SEAT/CUPRA never shipped a modern MBB app-name; the legacy Car-Net eRemote
    # value is the closest, and the backend keys acceptance on the bearer + VIN
    # enrollment more than the exact app-name. Probe a couple of variants.
    app_names = ["SEATCarNetEU", "CupraCarNetEU", "cz.skodaauto.connect"]

    def rec(host_label: str, status: int, note: str = "", body: str = "") -> None:
        verdict = {
            0: "conn-error (host unreachable from you)",
            200: "ACCEPTED + data",
            401: "token REJECTED (invalid_token)",
            403: "token accepted, no permission / not enrolled (403)",
            404: "token accepted, path/car not found (404)",
        }.get(status, "see status")
        line = f"  {host_label:<48} HTTP {status:<4} {verdict} {note}".rstrip()
        if status != 200 and body:
            line += f"  body={_mask(body).strip()[:450]}"
        lines.append(line)

    client_id = _load_client_id()
    # #464 — client AND scope are overridable so we can test the device-code-
    # capable SEAT/CUPRA *app* clients (3c756d46 / 99a5b77d), not just the web
    # client. Their tokens are audienced for the CARIAD BFF / OLA (unlike the web
    # client's VAS/MBB aud), so a BFF-style scope may mint a BFF-whitelisted
    # bearer — the VW-EU 650d46ca precedent. Set VAGC_SCOPE to experiment, e.g.
    # "openid profile badge cars dealers vin offline_access".
    scope = os.environ.get("VAGC_SCOPE", "").strip() or SEATCUPRA_MBB_SCOPE
    async with ClientSession() as session:
        # Device grant on the SEAT realm. The verification page is branded SEAT
        # (identity.vwgroup.io/oidc/device/seat) but a CUPRA ID signs in there
        # just the same — the web + app clients share the SEAT realm.
        dag = DeviceAuthorizationGrant(
            session, client_id, scope=scope,
            strategy="mbb",
            device_auth_url=f"{IDP}/oidc/v1/device_authorization",
            token_url=f"{IDP}/oidc/v1/token",
        )
        print(f"[*] Requesting device code from {IDP} (SEAT/CUPRA web client) …",
              flush=True)
        try:
            dc = await dag.request_device_code()
        except Exception as exc:  # noqa: BLE001
            print(f"[!] device_code request failed: {_mask(exc)}")
            print(f"    (Please paste this into {ISSUE} — a failure here would mean")
            print("     the web client stopped issuing a device code.)")
            return 1
        print("\n" + "=" * 64)
        print("  OPEN THIS LINK IN YOUR BROWSER AND CONFIRM THE LOGIN:")
        print("   ", dc.verification_uri_complete or dc.verification_uri)
        if not dc.verification_uri_complete:
            print("  (enter this code if asked:", dc.user_code, ")")
        print("  Sign in with your SEAT ID / CUPRA ID email + password.")
        print("  (The page is SEAT-branded — a CUPRA ID works there too.)")
        print("  Your password stays in the browser — never in this script.")
        print("=" * 64 + "\n", flush=True)

        try:
            tokens = await dag.poll_for_tokens(
                dc.device_code, interval=dc.interval, expires_in=dc.expires_in
            )
        except Exception as exc:  # noqa: BLE001
            print(f"[!] login not confirmed / failed: {_mask(exc)}")
            return 1

        # The single most telling fact: what the SEAT realm actually granted.
        id_claims = _claims(tokens.id_token) if tokens.id_token else {}
        acc_claims = _claims(tokens.access_token) if tokens.access_token else {}
        id_aud = _aud_str(id_claims)
        granted_scope = _mask(id_claims.get("scope") or acc_claims.get("scope") or "")
        has_refresh = "yes" if getattr(tokens, "refresh_token", None) else "no"

        # ── "old" / MBB durable path ──────────────────────────────────────────
        # The register→exchange is ACCOUNT-level (no car needed): success here
        # alone proves a durable, refreshable MBB bearer is mintable for a
        # SEAT/CUPRA account — the core of the durable two-way.
        mbb = None
        cid = ""
        mbb_minted = "no"
        try:
            mbb, cid = await _mbboauth.mint_mbb_bearer(session, tokens.id_token)
            mbb_minted = "yes"
        except Exception as exc:  # noqa: BLE001
            mbb_minted = f"FAILED ({_mask(exc)[:300]})"
            _e = str(exc).lower()
            if "certificate_verify_failed" in _e or "self-signed" in _e or "self signed" in _e:
                print("    NOTE: TLS-interception error from YOUR network (corporate")
                print("    proxy / antivirus re-signing HTTPS). Not a backend reject —")
                print("    please re-run from a network without SSL inspection.")

        if mbb is not None:
            bc = _claims(mbb.access_token)
            uid = str(bc.get("sub", ""))
            durable = "yes" if mbb.refresh_token else "no"
            mbb_aud = _aud_str(bc)
            lines.append(
                f"  MBB exchange (old/durable)  minted=yes  durable_refresh={durable}  aud={mbb_aud}")

            # #464 client-MIX — the MBB/VWAC exchange bearer (aud includes
            # ha-5a…vwautocloud.net) tested against the MODERN planes, not just
            # mal-1a. If the CARIAD BFF or OLA accept this exchanged bearer, the
            # VW-style "MBB mix" opens a read/command path for SEAT/CUPRA.
            _st, _b = await _hit_bff(session, mbb.access_token,
                                     f"{BFF_BASE}/vehicle/v2/vehicles")
            rec("MIX bff /vehicle/v2/vehicles (MBB bearer)", _st, body=_b)
            _st, _b = await _hit_ola(session, mbb.access_token,
                                     f"{OLA_BASE}/v1/vehicles")
            rec("MIX ola /v1/vehicles (MBB bearer)", _st, "(403=wall)", _b)

            # account-level plane acceptance (no VIN needed): the usermanagement
            # vehicles list. 200 (even empty) = the durable MBB bearer is accepted
            # by the SEAT/CUPRA Car-Net plane; 401 = the bearer is rejected there.
            for brand in ("Seat", "Cupra"):
                st = await _hit(session, mbb.access_token, cid, uid,
                                f"{DISCOVERY_BASE}/fs-car/usermanagement/users/v1/{brand}/DE/vehicles",
                                app_names[0])
                rec(f"mal-1a /usermanagement/{brand}/DE/vehicles", st)
            # #464 — same reads against mal.prd.ece (the bearer's ACTUAL aud host,
            # not the -1a setter). A 200/404 here where mal-1a gave 403 would mean
            # we were just hitting the wrong host all along.
            for brand in ("Seat", "Cupra"):
                st = await _hit(session, mbb.access_token, cid, uid,
                                f"{DISCOVERY_BASE_ALT}/fs-car/usermanagement/users/v1/{brand}/DE/vehicles",
                                app_names[0])
                rec(f"mal.prd.ece /usermanagement/{brand}/DE/vehicles", st)

            if has_vin:
                # homeRegion — does the MBB plane KNOW this SEAT/CUPRA VIN?
                # Try BOTH the setter host and the bearer's aud host.
                for base_label, base in (("mal-1a", DISCOVERY_BASE),
                                         ("mal.prd.ece", DISCOVERY_BASE_ALT)):
                    for app in app_names:
                        st = await _hit(session, mbb.access_token, cid, uid,
                                        f"{base}/api/cs/vds/v1/vehicles/{V}/homeRegion",
                                        app)
                        rec(f"{base_label} /homeRegion  (X-App-Name={app})", st)
                # operation list — which commands the car OFFERS (no command sent)
                st = await _hit(session, mbb.access_token, cid, uid,
                                f"{DISCOVERY_BASE}/api/rolesrights/operationlist/v3/vehicles/{V}",
                                app_names[0])
                rec("mal-1a /operationlist", st)
                # vehicle-status read (VSR) — the actual live-data prize
                st = await _hit(session, mbb.access_token, cid, uid,
                                f"{DISCOVERY_BASE}/fs-car/bs/vsr/v1/Seat/CN/vehicles/{V}/status",
                                app_names[0])
                rec("mal-1a /fs-car/bs/vsr/v1/.../status", st)
            else:
                lines.append("  mal-1a per-VIN reads             SKIPPED (no car on account)")
        else:
            lines.append(f"  MBB exchange (old/durable)  minted={mbb_minted}")

        # ── modern BFF path ───────────────────────────────────────────────────
        # /vehicle/v2/vehicles is a LIST endpoint (no VIN needed): 200 + (possibly
        # empty) list = the web-client bearer is BFF-whitelisted; 403 = valid but
        # not whitelisted; 401 = token rejected. Ideal for a no-car account.
        if tokens.access_token:
            st, body = await _hit_bff(session, tokens.access_token,
                                      f"{BFF_BASE}/vehicle/v2/vehicles")
            rec("bff /vehicle/v2/vehicles (list, no car needed)", st, body=body)
            if has_vin:
                st, body = await _hit_bff(session, tokens.access_token,
                                          f"{BFF_BASE}/vehicle/v1/vehicles/{V}/selectivestatus?jobs=userCapabilities")
                rec("bff /vehicle/v1/.../selectivestatus", st, body=body)

        # ── OLA path (what the app actually drives) ──────────────────────────
        # /v1/vehicles is the list endpoint. OLA is attestation-walled, so a 403
        # is the expected wall response; a 200 would mean the web-client bearer
        # sails past the App-Check/WAF wall; a 401 means the token is rejected.
        if tokens.access_token:
            st, body = await _hit_ola(session, tokens.access_token,
                                      f"{OLA_BASE}/v1/vehicles")
            rec("ola /v1/vehicles (list, no car needed)", st, "(403=wall expected)", body)
            if has_vin:
                st, body = await _hit_ola(session, tokens.access_token,
                                          f"{OLA_BASE}/v2/vehicles/{V}/status")
                rec("ola /v2/vehicles/{vin}/status", st, "(403=wall expected)", body)
                st, body = await _hit_ola(session, tokens.access_token,
                                          f"{OLA_BASE}/v1/vehicles/{V}/permissions")
                rec("ola /v1/vehicles/{vin}/permissions", st, "(403=wall expected)", body)

    print("\n\n" + "=" * 64)
    print(f"  COPY EVERYTHING BETWEEN THE LINES INTO THE GITHUB THREAD ({ISSUE})")
    print("  (it contains NO password, NO VIN, NO personal data)")
    print("=" * 64)
    print("----8<---- vag-connect SEAT/CUPRA MBB-mix + BFF probe ----8<----")
    print(f"client            : {client_id[:8]}… (SEAT/CUPRA, attestation-free device grant)")
    print(f"scope             : {scope}")
    print(f"mode              : {'full (with car)' if has_vin else 'login-only (no car on account)'}")
    print(f"id_token_aud      : {id_aud}")
    print(f"access_token_aud  : {_aud_str(acc_claims)}")
    print(f"access_token_scope: {_mask(acc_claims.get('scope') or '') or '(opaque / not a JWT)'}")
    print(f"granted_scope     : {granted_scope or '(not present in token)'}")
    print(f"device_refresh    : {has_refresh}")
    print("results:")
    for ln in lines:
        print(ln)
    print("interpretation:")
    print("  * a 200 on any mal-1a line = attestation-free MBB (old/durable)")
    print("    read/command route works for SEAT/CUPRA — the durable two-way.")
    print("  * a 200 on a bff line = the modern CARIAD BFF accepts the web")
    print("    client's bearer directly (an even better two-way).")
    print("  * a 200 on an ola line = the bearer sails past the App-Check/WAF")
    print("    wall on the plane the app actually uses (the biggest prize);")
    print("    403 there is the expected wall, 401 means the token is rejected.")
    print("  * 401/403 everywhere = the token mints but no backend accepts it;")
    print("    the id_token_aud line above tells us which backend to target next.")
    print("----8<---- end — paste the block above ----8<----")
    print("=" * 64)
    return 0


if __name__ == "__main__":
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
        except Exception:  # noqa: BLE001
            pass
    vin_arg = sys.argv[1] if len(sys.argv) >= 2 else ""
    if not vin_arg:
        print("[i] no VIN given -> LOGIN-ONLY mode (device login + token mint +")
        print("    MBB exchange + BFF/OLA list). Pass a VIN to add per-car reads:")
        print("    py scripts/seat_cupra_mbb_probe.py <YOUR_VIN>\n")
    raise SystemExit(asyncio.run(main(vin_arg)))
