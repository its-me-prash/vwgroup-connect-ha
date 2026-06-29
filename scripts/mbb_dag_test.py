#!/usr/bin/env python3
# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
"""Local DAG + MBB live test harness.

Drives the RFC-8628 Device Authorization Grant for a chosen brand: prints a
verification LINK you open in your browser and confirm (your credentials stay
in YOUR browser — never in this script). Once you confirm, it obtains a real
``identity.vwgroup.io`` id_token and uses it to test the MBB token exchange
(``cariad/auth/_mbboauth.py``) against the LIVE server — proving whether the
legacy MBB path mints a durable refreshable token past the Play-Integrity wall.

NEVER prints tokens — only lengths, booleans and HTTP status codes.

Usage:  py scripts/mbb_dag_test.py [skoda|audi|seat|cupra]   (default: skoda)
"""

from __future__ import annotations

import asyncio
import base64
import json
import sys
from pathlib import Path
from typing import Any

# Repo root on sys.path so the custom_components package imports.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# MBB register endpoint (classic Car-Net flow) — grounded in the e-Remote DEX.
_MBB_REGISTER_URL = (
    "https://mbboauth-1d.prd.ece.vwg-connect.com/mbbcoauth/mobile/register/v1"
)
_MBB_UA = "WeConnect/5.17.6 (Android 14; okhttp/3.14.9)"


def _jwt_claims(token: str) -> dict[str, Any]:
    """Decode a JWT's PUBLIC payload claims (aud/iss/exp/azp). Never returns or
    logs the signature/raw token — just the metadata claims used to reason
    about compatibility."""
    try:
        payload_b64 = token.split(".")[1]
        payload_b64 += "=" * (-len(payload_b64) % 4)  # pad
        data = json.loads(base64.urlsafe_b64decode(payload_b64))
        return {k: data.get(k) for k in ("iss", "aud", "azp", "exp", "scope")}
    except Exception:  # noqa: BLE001
        return {}


# App-identity candidates for register/v1. The DATA endpoints (VSR /status,
# usermanagement) gate on the SERVER-side systemId 'XID_APP_VW', which is
# (hypothesis) derived from the registered app identity — so the e-Remote
# appId may mint a token the data endpoints reject (403 *.security.9007
# "no permission for systemId XID_APP_VW"). The We Connect app uses the SAME
# mbboauth register/v1 + sc2:fal (DEX-confirmed), so registering as We Connect
# may be what flips the systemId to XID_APP_VW.
_APP_EREMOTE = ("de.volkswagen.carnet.eu.eremote", "WeConnect", "5.17.6")
_APP_WECONNECT = ("com.volkswagen.weconnect", "WeConnect", "5.17.6")
_APP_MYAUDI = ("de.myaudi.mobile.assistant", "myAudi", "4.31.0")


async def _mbb_register(
    session: Any,
    id_token: str,
    desired_client_id: str | None = None,
    app: tuple[str, str, str] = _APP_EREMOTE,
    client_brand: str = "VW",
) -> tuple[str | None, str | None]:
    """POST the classic Car-Net MBB register/v1 step. Returns the registered
    client_id on success, else None. ``desired_client_id`` pins the client_id
    in the body so the registered client == the id_token's aud (MBB requires
    id_token.aud == X-Client-Id at the token exchange). ``app`` = (appId,
    appName, appVersion) — the lever for the XID_APP_VW systemId."""
    app_id, app_name, app_version = app
    body = {
        "client_name": "vag-connect-mbb-probe",
        "platform": "google",
        "client_brand": client_brand,
        "appId": app_id,
        "appName": app_name,
        "appVersion": app_version,
        "id_token": id_token,
    }
    if desired_client_id:
        body["client_id"] = desired_client_id
        body["scope"] = "sc2:fal"
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": _MBB_UA,
        "Authorization": f"Bearer {id_token}",
    }
    try:
        async with session.post(_MBB_REGISTER_URL, json=body, headers=headers) as resp:
            text = await resp.text()
            if resp.status in (200, 201):
                try:
                    payload = json.loads(text)
                except ValueError:
                    payload = {}
                # Show the FULL shape (keys) — does it carry a client_secret
                # (→ confidential exchange) or extra fields we must echo back?
                print(f"    [register OK] HTTP {resp.status}  keys={list(payload.keys())}  "
                      f"client_id={'yes' if payload.get('client_id') else 'no'}  "
                      f"client_secret={'PRESENT' if payload.get('client_secret') else 'absent'}")
                return payload.get("client_id"), payload.get("client_secret")
            print(f"    [register rejected] HTTP {resp.status}: {text[:300]}")
            return None, None
    except Exception as exc:  # noqa: BLE001
        print(f"    [register error] {exc}")
        return None, None


def _bearer_claims(token: str) -> dict[str, Any]:
    """Decode ALL public claims of the MBB bearer JWT (no signature). The
    systemId/identity lives here — comparing the e-Remote vs We Connect
    bearers tells us whether the register appId changes the token identity
    WITHOUT needing the (sandbox-unreachable) data host."""
    try:
        payload_b64 = token.split(".")[1]
        payload_b64 += "=" * (-len(payload_b64) % 4)
        return json.loads(base64.urlsafe_b64decode(payload_b64))
    except Exception:  # noqa: BLE001
        return {}


async def _probe_get(
    session: Any, label: str, url: str, bearer: str, client_id: str,
    mbb_user_id: str = "", full: bool = False,
    send_client_id: bool = True, send_user_id: bool = True,
) -> str:
    """GET any MBB endpoint with the bearer + headers; print status + body
    head. ``send_client_id`` / ``send_user_id`` let us omit the X-Client-Id /
    X-MbbUserId headers — the upstream libs send NEITHER on reads, so omitting
    them tests whether OUR registered client (directory-only rights) is what
    trips the rolesandrights check."""
    headers = {
        "Authorization": f"Bearer {bearer}",
        "Accept": "application/json",
        "X-App-Name": "Volkswagen",
        "X-App-Version": "3.51.1",
        "User-Agent": "okhttp/3.14.9",
    }
    if send_client_id and client_id:
        headers["X-Client-Id"] = client_id
    if send_user_id and mbb_user_id:
        headers["X-MbbUserId"] = mbb_user_id
    try:
        async with session.get(url, headers=headers) as resp:
            text = await resp.text()
            ok = resp.status == 200
            shown = text if full else text[:260]
            print(f"    [{label}] HTTP {resp.status} {'OK' if ok else ''}: {shown}")
            return text
    except Exception as exc:  # noqa: BLE001
        print(f"    [{label}] connect-error: {str(exc)[:120]}")
        return ""


async def _host_discovery(
    session: Any, id_token: str, idk_access_token: str, vin: str,
    brand: str = "volkswagen",
) -> None:
    """The decisive host hunt: resolve the operationList service directory (per
    service: host + license status + commands) + try VSR on the brand's data
    hosts. Brand-aware: Audi data lives on msg.audi.de with the /Audi/ segment;
    VW on msg.volkswagen.de with /VW/."""
    from custom_components.vag_connect.cariad.auth import _mbboauth  # noqa: PLC0415

    is_audi = brand.lower() == "audi"
    seg = "Audi" if is_audi else "VW"
    reg_app = _APP_MYAUDI if is_audi else _APP_EREMOTE
    reg_brand = "Audi" if is_audi else "VW"
    data_hosts = (
        ["https://msg.audi.de", "https://fal-3a.prd.eu.dp.vwg-connect.com"]
        if is_audi else
        ["https://msg.volkswagen.de", "https://fal-3a.prd.eu.dp.vwg-connect.com"]
    )

    aud = _jwt_claims(id_token).get("aud")
    aud_str = aud[0] if isinstance(aud, list) else aud
    # Mint with retries — this sandbox has flaky DNS to the vwg-connect hosts;
    # a transient timeout must not abort the whole (browser-confirmed) run.
    mbb = None
    cid = aud_str
    for attempt in range(4):
        try:
            reg_cid, _sec = await _mbb_register(
                session, id_token, desired_client_id=aud_str, app=reg_app,
                client_brand=reg_brand)
            cid = reg_cid or aud_str
            mbb = await _mbboauth.exchange_id_token(
                session, id_token, client_id=cid)
            break
        except Exception as exc:  # noqa: BLE001
            print(f"    [mint attempt {attempt + 1}/4 failed] {str(exc)[:110]}")
            await asyncio.sleep(2)
    if mbb is None:
        print("    [!] could not mint the MBB bearer (transient DNS/timeout in "
              "this environment). Just re-run — the auth itself works.")
        return
    bc = _bearer_claims(mbb.access_token)
    uid = bc.get("sub", "")
    print(f"\n[*] bearer minted. sys={bc.get('sys')} sub={uid} cor={bc.get('cor')} "
          f"aud={bc.get('aud')}")
    print(f"    X-Client-Id={cid[:8]}…  X-MbbUserId={uid}")

    # ── 0. Garage enumeration — can we AUTO-READ the VIN(s) now (esp. with an
    #       active subscription)? Try the account-level vehicle-list endpoints. ──
    print("\n[0] garage enumeration (auto-VIN):")
    for g_url in (
        f"https://msg.volkswagen.de/fs-car/usermanagement/users/v1/{seg}/CH/vehicles",
        f"https://msg.volkswagen.de/fs-car/usermanagement/users/v1/{seg}/DE/vehicles",
        "https://mal-1a.prd.ece.vwg-connect.com/api/usermanagement/users/v1/vehicles",
        "https://mal-1a.prd.ece.vwg-connect.com/api/cs/vds/v1/vehicles",
        f"https://mal-1a.prd.ece.vwg-connect.com/api/usermanagement/users/{uid}/vehicles",
    ):
        await _probe_get(
            session, f"garage {g_url.split('//')[1].split('/')[0]}{g_url.split('vehicles')[0][-22:]}",
            g_url, mbb.access_token, cid, uid, full=True)

    # ── 1. homeRegion — the per-VIN data base. Try the classic discovery host
    #       AND the mal host from the token aud. ──
    print("\n[1] homeRegion discovery:")
    for hr_host in (
        "https://mal-1a.prd.ece.vwg-connect.com",
        "https://mal.prd.ece.vwg-connect.com",
    ):
        await _probe_get(
            session, f"homeRegion @ {hr_host.split('//')[1]}",
            f"{hr_host}/api/cs/vds/v1/vehicles/{vin.upper()}/homeRegion",
            mbb.access_token, cid, uid)

    # ── 2. operationlist (rolesrights) — the SERVICE DIRECTORY. 200 here =
    #       token reads data + vehicle enrolled. Its serviceInfo[] carries the
    #       per-service host+path (invocationUrl/baseUri) — the real VSR host. ──
    print("\n[2] rolesrights operationlist (service directory) — FULL:")
    op_text = await _probe_get(
        session, "operationlist @ mal-1a",
        "https://mal-1a.prd.ece.vwg-connect.com"
        f"/api/rolesrights/operationlist/v3/vehicles/{vin.upper()}",
        mbb.access_token, cid, uid, full=True)

    # Parse serviceInfo → print every service's id + status + its base URLs,
    # and collect candidate base URLs for the status/VSR service + ALL
    # per-service bases (for the section-7 per-service data probes).
    status_bases: list[str] = []
    all_bases: dict[str, str] = {}
    try:
        ops = json.loads(op_text).get("operationList", {})
        services = ops.get("serviceInfo", []) or []
        print(f"\n    serviceInfo: {len(services)} services")
        for svc in services:
            sid = svc.get("serviceId", "?")
            sstatus = (svc.get("serviceStatus") or {}).get("status") or svc.get("status")
            base = ((svc.get("serviceConfiguration") or {}).get("baseUri")
                    or svc.get("invocationUrl") or {})
            base_c = base.get("content") if isinstance(base, dict) else base
            ops_list = [o.get("id") for o in (svc.get("operation") or []) if isinstance(o, dict)]
            print(f"      - {sid}  status={sstatus}  base={base_c}  ops={ops_list[:6]}")
            if base_c:
                all_bases[str(sid)] = base_c
            if base_c and any(k in str(sid).lower() for k in (
                    "statusreport", "vsr", "carfinder", "rbatterycharge", "rclima")):
                status_bases.append(base_c)
    except Exception as exc:  # noqa: BLE001
        print(f"    [operationlist parse error] {exc}")

    # ── 3. Status read. The operationList shows the working services on the
    #       MODERN pattern ``mal-1a.../api/bs/{service}/v1/vehicles/{vin}/`` (NO
    #       /fs-car, NO brand/country) — e.g. rclima→climatisation, trip→
    #       tripstatistics. statusreport_v1 carries no invocationUrl, so derive
    #       its host by analogy (mal-1a /api/bs/vsr or /statusreport) and ALSO
    #       try the legacy /fs-car hosts. ──
    mv = "https://mal-1a.prd.ece.vwg-connect.com"
    V = vin.upper()
    candidates = [
        # modern /api/bs pattern on mal-1a (most likely — matches rclima/trip)
        (f"{mv}/api/bs/vsr/v1/vehicles/{V}/status", "api/bs/vsr status"),
        (f"{mv}/api/bs/vsr/v1/vehicles/{V}/requests", "api/bs/vsr requests"),
        (f"{mv}/api/bs/statusreport/v1/vehicles/{V}/status", "api/bs/statusreport"),
        (f"{mv}/api/bs/cf/v1/vehicles/{V}/position", "api/bs/cf position"),
    ]
    # any operationList-derived base for a status-ish service, + its /status
    for b in status_bases:
        base = b.replace("{vin}", V).rstrip("/")
        candidates.append((f"{base}/status", f"derived {base.split('//')[-1][:34]}"))
    # legacy /fs-car fallbacks
    for host in data_hosts:
        for country in ("CH", "DE"):
            candidates.append((
                f"{host}/fs-car/bs/vsr/v1/{seg}/{country}/vehicles/{V}/status",
                f"legacy {host.split('//')[-1]} /{country}"))
    print(f"\n[3] status read — modern /api/bs pattern first (seg={seg}):")
    seen2: set[str] = set()
    for url, label in candidates:
        if url in seen2:
            continue
        seen2.add(url)
        await _probe_get(session, label, url, mbb.access_token, cid, uid, full=True)

    # ── 4. Prash's idea: does the CARIAD BFF accept the MBB token? The BFF is
    #       NOT in the token aud (vwautocloud/mal) and expects a CARIAD/IDK
    #       issuer, so likely 401 — but if it works we get the full modern
    #       selectivestatus. Probe the garage + selectivestatus. ──
    print("\n[4] CARIAD BFF with the MBB token (audience mismatch — long shot):")
    bff = "https://emea.bff.cariad.digital"
    await _probe_get(
        session, "BFF /vehicle/v1/vehicles (garage)",
        f"{bff}/vehicle/v1/vehicles", mbb.access_token, cid, uid)
    await _probe_get(
        session, "BFF selectivestatus (MBB bearer)",
        f"{bff}/vehicle/v1/vehicles/{vin.upper()}/selectivestatus"
        "?jobs=access,fuelStatus,measurements,charging",
        mbb.access_token, cid, uid)
    # Also try the device-grant IDK access_token (the OIDC token, NOT the MBB
    # bearer) against the BFF — the BFF may want the OIDC token. This is the
    # 'hybrid' path the integration normally uses; it's attestation-gated, but
    # this device-grant token is fresh so it's worth a direct check.
    if idk_access_token:
        await _probe_get(
            session, "BFF /vehicles (IDK access_token)",
            f"{bff}/vehicle/v1/vehicles", idk_access_token, cid, uid)
        await _probe_get(
            session, "BFF selectivestatus (IDK access_token)",
            f"{bff}/vehicle/v1/vehicles/{vin.upper()}/selectivestatus"
            "?jobs=access,fuelStatus,measurements,charging",
            idk_access_token, cid, uid)

    # ── 5. THE HEADER MATRIX (Prash). Upstream (audi_connect_ha /
    #       volkswagencarnet) sends NO X-Client-Id on reads — ours sends a
    #       freshly-registered client that may only carry DIRECTORY rights, not
    #       DATA rights → maybe that's what trips ``rolesandrights.unauthorized``.
    #       Retry the key reads with the header variations + the legacy bs/rs
    #       path (audi_services uses /fs-car/bs/rs/v1) and the shared client. ──
    print("\n[5] header matrix — drop X-Client-Id / X-MbbUserId, try bs/rs:")
    V = vin.upper()
    shared = "9523ee15-f6e0-4eb9-9907-59d058d7e16e"  # MBB_SHARED_CLIENT_ID
    msg = "https://msg.volkswagen.de" if not is_audi else "https://msg.audi.de"
    targets = [
        ("homeRegion", f"{mv}/api/cs/vds/v1/vehicles/{V}/homeRegion"),
        ("api/bs/vsr/status", f"{mv}/api/bs/vsr/v1/vehicles/{V}/status"),
        ("legacy bs/rs DE", f"{msg}/fs-car/bs/rs/v1/{seg}/DE/vehicles/{V}/status"),
        ("legacy bs/vsr DE", f"{msg}/fs-car/bs/vsr/v1/{seg}/DE/vehicles/{V}/status"),
    ]
    for name, url in targets:
        # (a) no X-Client-Id (keep X-MbbUserId)
        await _probe_get(session, f"{name} | no-cid", url, mbb.access_token,
                         cid, uid, full=True, send_client_id=False)
        # (b) no X-Client-Id AND no X-MbbUserId (full upstream-minimal)
        await _probe_get(session, f"{name} | bare", url, mbb.access_token,
                         cid, uid, full=True, send_client_id=False,
                         send_user_id=False)
        # (c) shared app client_id instead of our registered one
        await _probe_get(session, f"{name} | shared-cid", url, mbb.access_token,
                         shared, uid, full=True)

    # ── 6. SecToken leg-1 (SAFE — GET only, returns a challenge, consumes NO
    #       SPIN try). Commands do the rolesrights AUTHORIZATION that reads
    #       skip; the rolesrights family works for us (operationList=200), so
    #       this may 200 where data reads 403 → durable COMMANDS viable. ──
    print("\n[6] SecToken leg-1 (safe, no SPIN) — does the command-auth open?")
    for op in ("LOCK", "UNLOCK"):
        await _probe_get(
            session, f"security-pin-auth-requested {op}",
            f"{mv}/api/rolesrights/authorization/v2/vehicles/{V}/services/"
            f"rlu_v1/operations/{op}/security-pin-auth-requested",
            mbb.access_token, cid, uid, full=True)
    # also the climatisation + charge operation-auth (no SPIN on those reads)
    for svc, op in (("rclima_v1", "P_START_CLIMA_NOSET"),
                    ("rbatterycharge_v1", "P_START")):
        await _probe_get(
            session, f"op-auth {svc}/{op}",
            f"{mv}/api/rolesrights/authorization/v2/vehicles/{V}/services/"
            f"{svc}/operations/{op}/security-pin-auth-requested",
            mbb.access_token, cid, uid, full=True)

    # ── 7. PER-SERVICE DATA GETs (the bit we missed). The operationList handed
    #       us per-service hosts for the now-Enabled services (rclima, charge,
    #       trip). We only ever hammered the generic VSR/status — never these.
    #       A G_DATA/G_STATUS read on a service's OWN host may return real data
    #       even where the generic VSR 403s. Also probe the FREE Enabled
    #       services (vehicletelemetry_v1, vehicles_v1_cai) by convention. ──
    print("\n[7] per-service DATA reads on operationList hosts (the missed bit):")
    def _sub(base: str) -> str:
        return base.replace("{vin}", V).replace("{brand}", seg).replace(
            "{country}", "DE").rstrip("/")
    # known service → likely GET sub-paths (classic Car-Net resource names)
    subpaths = {
        "rclima_v1": ["climater", "status", ""],
        "rbatterycharge_v1": ["charger", "status", ""],
        "trip_statistic_v1": ["tripdata/shortTerm/newest", "tripdata", ""],
        "carfinder_v1": ["position", ""],
        "timerprogramming_v1": ["timer", "status", ""],
    }
    for sid, base in all_bases.items():
        b = _sub(base)
        for sp in subpaths.get(sid, ["status", ""]):
            url = f"{b}/{sp}" if sp else b
            await _probe_get(session, f"{sid} GET /{sp or '(base)'}", url,
                             mbb.access_token, cid, uid, full=True)
    # FREE Enabled services with no invocationUrl — convention guesses on mal-1a
    for sid, guesses in (
        ("vehicletelemetry_v1", [f"{mv}/api/bs/vehicletelemetry/v1/vehicles/{V}/status",
                                 f"{mv}/api/bs/vehicletelemetry/v1/vehicles/{V}"]),
        ("vehicles_v1_cai", [f"{mv}/api/cai/v1/vehicles", f"{mv}/api/bs/vehicles/v1/vehicles",
                             f"{mv}/api/cs/vds/v1/vehicles"]),
        ("fod_v1", [f"{mv}/api/bs/fod/v1/vehicles/{V}/status"]),
    ):
        for url in guesses:
            await _probe_get(session, f"{sid} GET {url.split('/api/')[-1][:30]}",
                             url, mbb.access_token, cid, uid, full=True)


async def _systemid_experiment(session: Any, id_token: str, vin: str) -> None:
    """The decisive experiment: register under BOTH app identities (e-Remote
    vs We Connect), exchange each for a bearer, and do a real VSR read. Tells
    us whether the XID_APP_VW data-permission follows the register appId."""
    from custom_components.vag_connect.cariad.auth import _mbboauth  # noqa: PLC0415

    aud = _jwt_claims(id_token).get("aud")
    aud_str = aud[0] if isinstance(aud, list) else aud
    for label, app in (("e-Remote", _APP_EREMOTE), ("We Connect", _APP_WECONNECT)):
        print(f"\n[EXPERIMENT] register as {label} (appId={app[0]}) -> exchange -> VSR read")
        reg_cid, _sec = await _mbb_register(
            session, id_token, desired_client_id=aud_str, app=app)
        cid = reg_cid or aud_str
        if not cid:
            print("    [skip] no client_id to exchange with")
            continue
        try:
            mbb = await _mbboauth.exchange_id_token(session, id_token, client_id=cid)
        except Exception as exc:  # noqa: BLE001
            print(f"    [exchange rejected] {str(exc)[:200]}")
            continue
        print(f"    [exchange OK] bearer len={len(mbb.access_token)}, "
              f"refresh={'yes' if mbb.refresh_token else 'no'}")
        # Decode the bearer's identity claims — the decisive comparison that
        # works WITHOUT the data host. Show every claim that could carry the
        # systemId / app identity.
        bc = _bearer_claims(mbb.access_token)
        wanted = ("azp", "aud", "scope", "sub", "cor", "typ", "systemId",
                  "client_id", "vwACId", "act", "iss")
        shown = {k: bc.get(k) for k in wanted if k in bc}
        extra = {k: v for k, v in bc.items() if k not in wanted
                 and not isinstance(v, (dict, list)) and k not in ("exp", "iat", "nbf", "jti")}
        print(f"    [bearer claims] {shown}")
        if extra:
            print(f"    [bearer extra]  {extra}")
        for country in ("CH", "DE"):
            await _vsr_probe(session, mbb.access_token, cid, vin, country)


async def main(brand: str) -> int:
    from aiohttp import ClientSession

    from custom_components.vag_connect.cariad.auth import _mbboauth
    from custom_components.vag_connect.cariad.auth._device_grant import (
        DAG_ENABLED_BRANDS,
        DeviceAuthorizationGrant,
        portal_dag_config,
    )
    from custom_components.vag_connect.cariad.models import BRANDS

    # Optional 2nd CLI arg = an explicit client_id override (to test whether a
    # specific client — e.g. the e-Remote 9496332b — is device-grant-able, so
    # its id_token's aud matches what MBB wants).
    override = sys.argv[2] if len(sys.argv) > 2 else None

    # Resolve the device-grant client. VW EU's *app* client is DAG-dead
    # (unauthorized_client), but its EU-Data-Act *portal* client works at the
    # same /oidc/v1/device_authorization endpoint (live-verified 2026-06-12) —
    # so "volkswagen" routes through the portal client here.
    portal = portal_dag_config(brand)
    if override:
        # ``mbb`` scope is the key: it makes identity.vwgroup.io issue an
        # id_token targeted at the MBB backend audience (VWGMBB01DELIV1) rather
        # than the OIDC client — exactly what the e-Remote app requests and
        # what the MBB token exchange demands (id_token.aud == VWGMBB01DELIV1).
        # Audi's client doesn't allow the "cars" scope (myAudi scope set);
        # "mbb" is the load-bearing one (adds VWGMBB01DELIV1 to the aud).
        _ov_scope = ("openid profile mbb" if brand.lower() == "audi"
                     else "openid profile mbb cars")
        client_id, scope, route = override, _ov_scope, "override"
    elif brand in DAG_ENABLED_BRANDS:
        client_id, scope, route = BRANDS[brand].client_id, "openid profile", "app"
    elif portal is not None:
        client_id, scope, route = portal[0], portal[1], "portal"
    else:
        print(f"[!] '{brand}' has no device-grant route. App-DAG: "
              f"{sorted(DAG_ENABLED_BRANDS)}; portal-DAG: volkswagen/seat/cupra.")
        return 2
    print(f"[*] Brand: {brand}  route: {route}-device-grant  "
          f"client_id: {client_id[:8]}…  scope: {scope}")

    async with ClientSession() as session:
        dag = DeviceAuthorizationGrant(
            session, client_id, scope=scope,
            strategy="device_grant_portal" if route == "portal" else "device_grant",
        )
        print("[*] Requesting device code …", flush=True)
        dc = await dag.request_device_code()

        print("\n" + "=" * 64)
        print("  OPEN THIS LINK IN YOUR BROWSER AND CONFIRM THE LOGIN:")
        print("   ", dc.verification_uri_complete or dc.verification_uri)
        print("  (if the code isn't pre-filled, enter:", dc.user_code, ")")
        print("  Waiting up to", dc.expires_in, "s for you to confirm …")
        print("=" * 64 + "\n", flush=True)

        try:
            tokens = await dag.poll_for_tokens(
                dc.device_code, interval=dc.interval, expires_in=dc.expires_in)
        except Exception as exc:  # noqa: BLE001
            print(f"[!] device-grant did not complete: {exc}")
            return 1

        print(f"[ok] got id_token (len={len(tokens.id_token)}), "
              f"access_token (len={len(tokens.access_token)}). NOT printing them.")

        # ── Decode the id_token's PUBLIC claims (aud/iss/exp only — never the
        #    signature/token). aud tells us immediately whether this token is
        #    even MBB-compatible (MBB binds to a recognised app aud). ──
        claims = _jwt_claims(tokens.id_token)
        print(f"[*] id_token claims:  iss={claims.get('iss')}  "
              f"aud={claims.get('aud')}  azp={claims.get('azp')}")

        # ── DECISIVE EXPERIMENT (when a VIN is passed as argv[3]): does the
        #    durable token actually READ data, and does the XID_APP_VW
        #    permission follow the register appId (e-Remote vs We Connect)? ──
        probe_vin = sys.argv[3] if len(sys.argv) > 3 else None
        if probe_vin:
            await _host_discovery(
                session, tokens.id_token, tokens.access_token, probe_vin,
                brand=brand)
            print("\n" + "=" * 64)
            print("  HOST HUNT DONE. Any 'HTTP 200 OK' above = the working host.")
            print("  If homeRegion 200s it gives the real data base; if EVERY")
            print("  VSR/operationlist 403s with XID_APP_VW, it's a vehicle-")
            print("  enrollment wall, not a host issue.")
            print("=" * 64)
            return 0

        # ── Step 1: MBB register (the missing step). Classic Car-Net flow
        #    POSTs the id_token + app metadata to /mobile/register/v1 and gets
        #    back the X-Client-Id to use for the token exchange. ──
        # Pin the register to the id_token's own aud so registered == aud.
        aud = claims.get("aud")
        aud_str = aud[0] if isinstance(aud, list) else aud
        print(f"\n[*] MBB register/v1 (pinned client_id = aud {str(aud_str)[:8]}…) …",
              flush=True)
        reg_client_id, reg_secret = await _mbb_register(
            session, tokens.id_token, desired_client_id=aud_str)

        any_ok = False

        # ── ADOPT TEST (Prash's idea): take the freshly-registered MBB client
        #    and RE-AUTHORIZE with it at identity.vwgroup.io, so the new
        #    id_token's aud == the registered client → the exchange should
        #    finally match. Only works if the registered client is an OIDC
        #    client (request_device_code fails fast otherwise — no wait). ──
        if reg_client_id:
            print(f"\n[*] ADOPT test: re-authorize with registered client "
                  f"{reg_client_id[:8]}… …", flush=True)
            try:
                dag2 = DeviceAuthorizationGrant(
                    session, reg_client_id, scope="openid profile cars")
                dc2 = await dag2.request_device_code()
                print("    [YES] registered client IS OIDC-usable — confirm a 2nd link:")
                print("     ", dc2.verification_uri_complete or dc2.verification_uri)
                print("      waiting for 2nd confirm …", flush=True)
                tok2 = await dag2.poll_for_tokens(
                    dc2.device_code, interval=dc2.interval, expires_in=dc2.expires_in)
                c2 = _jwt_claims(tok2.id_token)
                print(f"    2nd id_token aud={c2.get('aud')}")
                try:
                    mbb = await _mbboauth.exchange_id_token(
                        session, tok2.id_token, client_id=reg_client_id)
                    print(f"    [BREAKTHROUGH] MBB exchange OK — durable "
                          f"refresh_token present: {bool(mbb.refresh_token)}")
                    any_ok = True
                except Exception as exc:  # noqa: BLE001
                    print(f"    [adopt exchange rejected] {str(exc)[:300]}")
            except Exception as exc:  # noqa: BLE001
                print(f"    [NO] registered client not OIDC-usable: {str(exc)[:160]}")

        # ── Fallback diagnostics: try the static candidates + capture the FULL
        #    'Audiences' error (now untruncated). ──
        candidates: dict[str, str] = {}
        if aud_str:
            candidates["aud-as-clientid " + str(aud_str)[:8]] = str(aud_str)
        if reg_client_id and reg_client_id != aud_str:
            candidates["REGISTERED " + reg_client_id[:8]] = reg_client_id
        candidates["shared mod2/eRemote 9523ee15"] = _mbboauth.MBB_SHARED_CLIENT_ID
        for label, cid in candidates.items():
            print(f"\n[*] MBB exchange with X-Client-Id = {label} …", flush=True)
            try:
                mbb = await _mbboauth.exchange_id_token(session, tokens.id_token, client_id=cid)
                print(f"    [OK] HTTP 200 — access_token len={len(mbb.access_token)}, "
                      f"durable refresh_token present: {bool(mbb.refresh_token)}")
                any_ok = True
            except Exception as exc:  # noqa: BLE001
                print(f"    [rejected] {str(exc)[:380]}")

        print("\n" + ("=" * 64))
        if any_ok:
            print("  RESULT: the MBB path MINTED a token past the App-Check wall. ")
            print("  The MBB adapter approach is viable — durable two-way is on.")
        else:
            print("  RESULT: no candidate client was accepted by the MBB endpoint.")
            print("  (id_token aud may need to match the X-Client-Id, or the flow ")
            print("   needs the mbbcoauth/mobile/register/v1 step first.)")
        print("=" * 64)
    return 0


if __name__ == "__main__":
    # Windows consoles default to cp1252 and choke on non-ASCII (→ … ←) when
    # stdout is redirected; force utf-8 so prints never crash the run.
    for _stream in (sys.stdout, sys.stderr):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
        except Exception:  # noqa: BLE001
            pass
    brand_arg = sys.argv[1].lower() if len(sys.argv) > 1 else "skoda"
    raise SystemExit(asyncio.run(main(brand_arg)))
