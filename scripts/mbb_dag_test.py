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

Usage:  python scripts/mbb_dag_test.py <brand> [route] [vin]

        <brand>  volkswagen, audi, audi_na, seat, cupra. 'skoda' has no route
                 at all and exits with code 2.
        [route]  WHICH client+scope pair to use. Omit it: 'mbb' is chosen for
                 the Car-Net brands (volkswagen, audi), otherwise 'app'.
                   mbb         the e-Remote client + the 'mbb' scope -- the only
                               pair that puts MBB's own audience
                               (VWGMBB01DELIV1) in the id_token, which the
                               exchange requires. The default, and the one the
                               MBB probes need.
                   mbb-backup  the failover client for the same scope.
                   app         the brand's own app client. For Audi this is a
                               dead end: VW took that client's device grant
                               down with the Auth0 migration (#1364), so
                               /device_authorization answers 403.
                   portal      the EU-Data-Act portal client (read-only).
                 A raw client_id is still accepted for ad-hoc probing and is
                 then paired with the MBB scope.
        [vin]    optional, adds the host/VSR hunt.
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


def _mbb_aud(id_token: str) -> str | None:
    """The audience to pin the MBB register/exchange to.

    Delegates to the production selector rather than taking ``aud[0]``, which
    is what this harness used to do at three separate places. The mbb-scoped
    id_token is multi-audience, and #464 established that ``aud[0]`` is the
    OAuth client id on SEAT/CUPRA — pinning it there makes the MBB backend
    answer ``400 invalid_grant`` ("unknown audience"). ``jwt_aud`` picks the
    MBB *delivery* audience instead.

    Taking ``aud[0]`` meant the harness pinned something production never
    pins, so its "aud-as-clientid" line reported a rejection that said nothing
    about the shipped path — found on the 2026-10-04 Audi run, where that line
    printed 403 for the OAuth client id while production would have pinned
    ``VWGMBB01DELIV1``.
    """
    from custom_components.vag_connect.cariad.auth._mbboauth import (  # noqa: PLC0415
        jwt_aud,
    )

    return jwt_aud(id_token)


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

    aud_str = _mbb_aud(id_token)
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

    # ── 1. homeRegion — the per-VIN data base on the classic discovery host.
    #       (#306: the token's aud ``mal.prd.ece.vwg-connect.com`` is an audience
    #       identifier, not a host — NXDOMAIN at VW's own nameservers, so it is
    #       no longer probed; it only ever produced a false "unreachable".) ──
    print("\n[1] homeRegion discovery:")
    for hr_host in (
        "https://mal-1a.prd.ece.vwg-connect.com",
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


async def _vsr_probe(
    session: Any, bearer: str, client_id: str, vin: str, country: str,
) -> None:
    """Probe the legacy fs-car VSR (vehicle status report) read for one country.

    This is the data-plane read whose ``403 'no permission for systemId
    XID_APP_VW'`` signals the token has NO legacy MBB enrolment (vs a real
    Car-Net car, which answers 200). Reconstructs the fs-car status URL the same
    way ``_host_discovery``'s legacy fallback does (VW ``Vw`` segment on the
    classic mal-1a gateway). (#584 — this helper had gone missing, so
    ``_systemid_experiment`` NameError'd mid-run; reported by @JustAnotherDud.)
    """
    url = (
        f"https://mal-1a.prd.ece.vwg-connect.com/fs-car/bs/vsr/v1/Vw/{country}"
        f"/vehicles/{vin.upper()}/status"
    )
    await _probe_get(session, f"VSR status /{country}", url, bearer, client_id)


async def _systemid_experiment(session: Any, id_token: str, vin: str) -> None:
    """The decisive experiment: register under BOTH app identities (e-Remote
    vs We Connect), exchange each for a bearer, and do a real VSR read. Tells
    us whether the XID_APP_VW data-permission follows the register appId."""
    from custom_components.vag_connect.cariad.auth import _mbboauth  # noqa: PLC0415

    aud_str = _mbb_aud(id_token)
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


# ── #1313/Audi-Watch: der requestAuthCode/authorize-Schritt ──────────────────
# myAudi 5.8.1 (androguard, 2026-10-04) trägt den Pfad
# ``mobile/oauth2/v1/requestAuthCode/authorize`` auf GENAU dem Host, den
# ``_mbboauth.py`` schon nutzt, mit demselben Scope ``sc2:fal``. Unsere Probe
# von 2026-06 bekam auf direktem ``/mobile/oauth2/v1/token`` ein 403 —
# HYPOTHESE: weil wir diesen Code-Schritt überspringen. Die App fährt
# IdentityKit-Token -> loadMBBStatusData -> MBBConnectorExtensions.authorizationCode
# -> requestAuthCode/authorize -> erst DANN /token.
#
# Die exakte Request-Form steht nicht in der APK, nur das Parameter-Vokabular
# (response_type/client_id/redirect_uri/scope/state/nonce/code_challenge/
# grant_type/code/id_token/audience/brand/platform/appId/deviceId). Deshalb eine
# KLEINE, begründete Matrix statt Raten: vier Formen, die sich in genau einer
# Dimension unterscheiden, damit die Antwort interpretierbar bleibt.
_MBB_AUTHCODE_URL = (
    "https://mbboauth-1d.prd.ece.vwg-connect.com/mbbcoauth"
    "/mobile/oauth2/v1/requestAuthCode/authorize"
)


def _code_from(text: str) -> tuple[str, int]:
    """(Name des Code-Felds, Länge) aus einer Antwort — NIE der Wert selbst."""
    try:
        data = json.loads(text)
    except Exception:  # noqa: BLE001
        return ("", 0)
    if not isinstance(data, dict):
        return ("", 0)
    for key in ("code", "authorizationCode", "authCode", "auth_code"):
        val = data.get(key)
        if isinstance(val, str) and val:
            return (key, len(val))
    return ("", 0)


def _err_code_of(text: str) -> str:
    """Kurzer Fehlercode aus der Antwort, formgeprüft (nie Freitext/Secrets)."""
    try:
        data = json.loads(text)
    except Exception:  # noqa: BLE001
        return ""
    if not isinstance(data, dict):
        return ""
    for key in ("error", "errorCode"):
        val = data.get(key)
        if isinstance(val, str) and 0 < len(val) <= 40 and " " not in val.strip():
            return val
        if isinstance(val, dict):
            inner = val.get("errorCode") or val.get("code")
            if inner is not None:
                return str(inner)[:40]
    return ""


async def _request_auth_code_probe(
    session: Any, id_token: str, *, client_id: str, brand: str
) -> None:
    """Probe ``requestAuthCode/authorize`` — vier begründete Formen.

    Druckt NUR Status, Fehlercode und Code-LÄNGE. Niemals Token oder Code.
    Jede Form hat ihren eigenen Guard: eine Wand darf die anderen nicht kosten.
    """
    print("\n" + "=" * 64)
    print("  PROBE: requestAuthCode/authorize  (Audi-Watch 2026-10-04)")
    print("  Frage: liefert dieser Schritt einen Auth-Code, den /token nimmt?")
    print("=" * 64)

    # Vorbedingung, sonst ist das Ergebnis nicht interpretierbar: MBB bindet
    # an die Audience VWGMBB01DELIV1, die erst der Scope ``mbb`` in den
    # id_token legt. Ohne sie ist ein 401 ein Audience-Fehler und sagt NICHTS
    # ueber requestAuthCode. Lieber laut warnen als ein Ergebnis fehldeuten.
    _aud = _jwt_claims(id_token).get("aud")
    _aud_list = _aud if isinstance(_aud, list) else [_aud]
    if not any("VWGMBB" in str(a) for a in _aud_list if a):
        print("  [!] WARNUNG: id_token.aud enthaelt KEINE VWGMBB-Audience")
        print(f"      aud = {_aud}")
        print("      -> Ein 401 unten ist dann ein Audience-Problem, KEINE")
        print("         Aussage ueber requestAuthCode. Lauf auf der mbb-Route")
        print("         wiederholen: zweites Argument = mbb.")
    else:
        print(f"  [ok] id_token.aud traegt eine VWGMBB-Audience: {_aud_list}")

    base_hdr = {
        "Accept": "application/json",
        "User-Agent": _MBB_UA,
        "X-Client-Id": client_id,
    }
    variants: list[tuple[str, str, dict[str, str], dict[str, str] | None]] = [
        # 1) Wie der klassische Tausch, nur mit response_type=code: prüft, ob der
        #    Endpunkt dieselbe id_token-Grant-Form akzeptiert.
        ("POST form grant_type=id_token + response_type=code", "POST",
         dict(base_hdr),
         {"grant_type": "id_token", "token": id_token, "scope": "sc2:fal",
          "response_type": "code"}),
        # 2) Gleiche Form, aber das Token im Feld ``id_token`` — die APK kennt
        #    beide Feldnamen, und welcher gilt, entscheidet der Server.
        ("POST form id_token-Feld statt token", "POST",
         dict(base_hdr),
         {"grant_type": "id_token", "id_token": id_token, "scope": "sc2:fal",
          "response_type": "code"}),
        # 3) OIDC-artig als Query, wie ein /authorize es normalerweise erwartet.
        ("GET query response_type=code", "GET",
         dict(base_hdr),
         {"response_type": "code", "client_id": client_id, "scope": "sc2:fal",
          "token": id_token, "brand": brand, "platform": "Android"}),
        # 4) Ohne X-Client-Id: trennt "Client nicht berechtigt" von
        #    "Form falsch" — unser Client hat laut früheren Proben nur
        #    Directory-Rechte.
        ("POST form OHNE X-Client-Id", "POST",
         {k: v for k, v in base_hdr.items() if k != "X-Client-Id"},
         {"grant_type": "id_token", "token": id_token, "scope": "sc2:fal",
          "response_type": "code"}),
    ]

    got_code: tuple[str, int] | None = None
    # (status, body_was_json) per variant that actually answered — the verdict
    # is derived from these rather than left to the reader as a legend.
    seen: list[tuple[int, bool]] = []
    for label, method, headers, payload in variants:
        try:
            if method == "GET":
                ctx = session.get(_MBB_AUTHCODE_URL, headers=headers,
                                  params=payload)
            else:
                ctx = session.post(_MBB_AUTHCODE_URL, headers=headers,
                                   data=payload)
            async with ctx as resp:
                text = await resp.text()
                key, length = _code_from(text)
                err = _err_code_of(text)
                # Whether the body is JSON is load-bearing for the verdict: an
                # OAuth endpoint that refuses a client answers with a JSON
                # error object. A non-JSON body means nothing reached the OAuth
                # layer, so the status says little about our client.
                try:
                    parsed = json.loads(text)
                    body_is_json = isinstance(parsed, dict)
                    keys = sorted(parsed.keys())[:8] if body_is_json else []
                except (ValueError, TypeError):
                    body_is_json, keys = False, []
                extra = f"  code-Feld={key!r} len={length}" if key else ""
                if err:
                    extra += f"  error={err}"
                print(f"    [{label}] HTTP {resp.status}{extra}")
                if not key and not err:
                    shape = "JSON" if body_is_json else "kein JSON"
                    print(f"        body: {len(text)} B  {shape}  keys={keys}")
                seen.append((resp.status, body_is_json))
                if key and got_code is None:
                    got_code = (key, length)
        except Exception as exc:  # noqa: BLE001
            print(f"    [{label}] connect-error: {str(exc)[:120]}")

    print("\n  ── Verdikt ──")
    if got_code:
        print(f"  TREFFER: ein Auth-Code kam zurueck (Feld {got_code[0]!r}, "
              f"len={got_code[1]}).")
        print("  -> Das ist der fehlende Schritt. Naechstes: diesen Code mit")
        print("     grant_type=authorization_code an /mobile/oauth2/v1/token")
        print("     tauschen (hier NICHT automatisch, damit der Code nicht")
        print("     verbraucht wird, bevor Prash die Form festlegt).")
        print("=" * 64)
        return

    if not seen:
        print("  KEINE Antwort erhalten (alle Varianten Verbindungsfehler) —")
        print("  das ist KEIN Befund ueber den Endpunkt. Lauf wiederholen.")
        print("=" * 64)
        return

    statuses = {s for s, _ in seen}
    any_json = any(j for _, j in seen)
    only = next(iter(statuses)) if len(statuses) == 1 else None
    print(f"  KEIN Code. {len(seen)} Antworten, Status {sorted(statuses)}, "
          f"JSON-Body: {'ja' if any_json else 'nein'}")

    if only == 404:
        print("  -> Der Pfad existiert fuer UNSEREN Realm nicht. Hypothese")
        print("     widerlegt.")
    elif only == 401:
        print("  -> Audience-Problem, KEINE Aussage ueber requestAuthCode.")
        print("     Auf der mbb-Route wiederholen (siehe aud-Zeile oben).")
    elif only == 403 and not any_json:
        # The 2026-10-04 Audi run: four identical non-JSON 403s, including the
        # variant without X-Client-Id. Uniform refusal with no OAuth error
        # object is an edge/gateway rejection, not a client decision — so the
        # earlier wording "endpoint lives, our client may not" overclaimed.
        print("  -> Einheitlich 403 OHNE JSON-Fehlerobjekt, auch ohne")
        print("     X-Client-Id. Nichts hat die OAuth-Schicht erreicht, das")
        print("     sieht nach Abweisung am Gateway aus, NICHT nach einer")
        print("     Client-Entscheidung. Der Pfad ist fuer uns nicht")
        print("     bedienbar; WARUM bleibt offen. Hypothese NICHT bestaetigt.")
    elif only == 403 and any_json:
        print("  -> 403 MIT JSON-Fehlerobjekt: der Endpunkt hat geantwortet")
        print("     und lehnt ab. Fehlercode oben lesen; Variante 4 (ohne")
        print("     X-Client-Id) trennt Client-Recht von Form.")
    elif 400 in statuses:
        print("  -> Ein 400 kam zurueck: der Endpunkt lebt und liest die Form.")
        print("     Der Fehlercode oben sagt, welches Feld fehlt.")
    else:
        print("  -> Gemischte Antworten. Die Status-Zeilen oben einzeln lesen:")
        print("     404=Pfad fehlt, 400=Form falsch, 403=abgelehnt,")
        print("     401=Audience passt nicht.")
    print("=" * 64)


# The route names the 2nd CLI argument accepts. Anything else is treated as a
# raw client_id for ad-hoc probing.
_ROUTE_NAMES = ("mbb", "mbb-backup", "app", "portal")


def resolve_route(brand: str, arg2: str | None) -> tuple[str, str, str] | str:
    """Pick the ``(client_id, scope, route)`` to mint with, or return an error.

    The 2nd CLI arg names the ROUTE; it is NOT a client_id to paste. It used to
    be one, and that invited pasting the WRONG client: the Audi *app* client,
    whose device grant VW retired (#1364), answers
    ``403 unauthorized_client — client is not allowed to use the device_code
    grant``. That reads exactly like the probe refuting its own hypothesis,
    when in truth nothing was probed at all.

    The rejection is about the client, not the scope. A wire capture kept in
    our local research archive (2026-09-07) shows that client refused while
    sending ``openid mbb profile badge cars dealers vin`` — a scope carrying
    both ``mbb`` and ``cars`` — and our own 2026-09-04 probe found it refused
    across three scopes and six header shapes. So no scope rescues a retired
    client, and a run on the app route cannot answer anything about
    requestAuthCode.

    The named routes read the same single sources of truth the config flow
    reads, so each one is a client VW actually registered, together with the
    scope registered for it.

    Returns the triple on success, or an error message string to print.
    """
    from custom_components.vag_connect.cariad.auth._device_grant import (
        DAG_ENABLED_BRANDS,
        MBB_DAG_SCOPE,
        mbb_dag_backup_config,
        mbb_dag_config,
        portal_dag_config,
    )
    from custom_components.vag_connect.cariad.models import BRANDS

    # VW EU's *app* client is DAG-dead (unauthorized_client), but its
    # EU-Data-Act *portal* client works at the same
    # /oidc/v1/device_authorization endpoint (live-verified 2026-06-12) — so
    # "volkswagen" falls through to the portal client here.
    portal = portal_dag_config(brand)
    mbb = mbb_dag_config(brand)

    if arg2 is None:
        # Default to the MBB route where the brand has one: this harness exists
        # to test the MBB path, and for Audi the *app* route is a dead end —
        # VW took that client's device grant down with the Auth0 migration
        # (#1364, shipped as "Audi app login: attestation wall", and asserted
        # in tests/test_1364_device_grant_retired.py).
        route = ("mbb" if mbb is not None
                 else "app" if brand in DAG_ENABLED_BRANDS
                 else "portal")
    else:
        route = arg2 if arg2 in _ROUTE_NAMES else "override"

    if route in ("mbb", "mbb-backup"):
        # The e-Remote client + the load-bearing ``mbb`` scope: that scope is
        # what makes identity.vwgroup.io put the MBB backend audience
        # (VWGMBB01DELIV1) in the id_token instead of the OIDC client, which is
        # what the exchange demands. Live-validated on a real Audi account
        # 2026-08-30 (register 200 + durable refresh_token), so it covers Audi
        # and not only VW.
        cfg = mbb if route == "mbb" else mbb_dag_backup_config(brand)
        if cfg is None:
            return (f"[!] '{brand}' has no MBB device-grant route — the durable "
                    f"MBB login is Car-Net only (Volkswagen, Audi). Try 'app' "
                    f"or 'portal' as the 2nd argument.")
        return cfg[0], cfg[1], route
    if route == "app":
        if brand not in DAG_ENABLED_BRANDS:
            return (f"[!] '{brand}' has no app device-grant route. App-DAG: "
                    f"{sorted(DAG_ENABLED_BRANDS)}.")
        # Mirror the config flow exactly: the brand's OWN registered scope, not
        # a hardcoded "openid profile" that drops claims the client is entitled
        # to (Audi's registered scope already carries ``mbb``).
        return BRANDS[brand].client_id, BRANDS[brand].scope, route
    if route == "portal":
        if portal is None:
            return (f"[!] '{brand}' has no portal device-grant route "
                    f"(portal-DAG: volkswagen/seat/cupra).")
        return portal[0], portal[1], route
    # Ad-hoc probing of a client this script does not know about. It gets the
    # MBB scope, because that is the only reason to hand-probe here.
    assert arg2 is not None  # noqa: S101 — narrowing; route == "override"
    return arg2, MBB_DAG_SCOPE, route


async def main(brand: str) -> int:
    from aiohttp import ClientSession

    from custom_components.vag_connect.cariad.auth import _mbboauth
    from custom_components.vag_connect.cariad.auth._device_grant import (
        DeviceAuthorizationGrant,
    )

    resolved = resolve_route(brand, sys.argv[2] if len(sys.argv) > 2 else None)
    if isinstance(resolved, str):
        print(resolved)
        return 2
    client_id, scope, route = resolved
    print(f"[*] Brand: {brand}  route: {route}-device-grant  "
          f"client_id: {client_id[:8]}…  scope: {scope}")

    # Same strategy tags the config flow stamps, so the TokenSet this harness
    # mints is indistinguishable from a real one.
    _strategy = {"portal": "device_grant_portal",
                 "mbb": "mbb",
                 "mbb-backup": "mbb"}.get(route, "device_grant")
    async with ClientSession() as session:
        dag = DeviceAuthorizationGrant(
            session, client_id, scope=scope, strategy=_strategy,
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

        # ── #1313/Audi-Watch: laeuft AUTOMATISCH, damit ein Tester nichts
        #    Neues lernen muss. Vier begruendete Formen, fail-soft, druckt nur
        #    Status/Fehlercode/Laenge. Siehe _request_auth_code_probe. ──
        await _request_auth_code_probe(
            session, tokens.id_token, client_id=client_id, brand=brand)

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
        # Pin the register to the MBB audience the production selector picks,
        # so this harness exercises the shipped choice (see _mbb_aud).
        aud_str = _mbb_aud(tokens.id_token)
        print(f"\n[*] MBB register/v1 (pinned client_id = aud {str(aud_str)[:16]}…) …",
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
            # 16 chars, not 8: VWGMBB01DELIV1 and VWGMBB01CNAPP1 share their
            # first eight, so a shorter label cannot say which one was tried.
            candidates["aud-as-clientid " + str(aud_str)[:16]] = str(aud_str)
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
    # No brand = print the usage. It used to default to "skoda", which has no
    # device-grant route at all, so a bare run reported a dead brand the caller
    # never asked for instead of saying what to pass.
    if len(sys.argv) < 2:
        print(__doc__)
        raise SystemExit(2)
    raise SystemExit(asyncio.run(main(sys.argv[1].lower())))
