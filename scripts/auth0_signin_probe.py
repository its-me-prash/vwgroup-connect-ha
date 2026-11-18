#!/usr/bin/env python3
# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
"""Local EU browser (Auth0/PKCE) sign-in probe — you sign in, it measures.

#1712. The config flow's browser sign-in is proven on Audi; for the other EU
brands (Volkswagen, SEAT, CUPRA) the route is reachable but the code exchange
is unverified. This is the tool a tester runs to find out, and to produce a
log that is safe to share: it uses the integration's own
``cariad/auth/_auth0.py`` builders, so it exercises exactly what the config
flow would.

WHAT IT DOES
  1. builds the ``/authorize`` URL for the chosen brand from ``_auth0`` (no
     credentials)
  2. you open it in your browser and sign in — your password never touches
     this script
  3. it catches the ``code`` from the localhost callback (Audi) or you paste
     the callback URL / code (the other brands use an app-scheme callback the
     browser will not show)
  4. it exchanges the code for a token with the 5-header set, no attestation —
     the documented door
  5. it decodes the token and shows ONLY the metadata: audience, scopes,
     validity. The token itself is never printed.
  6. a read-only look at what the token unlocks on the CARIAD API
  7. GET /user/v1/mbbuser — whether the MBB user id comes back for this token
     (myAudi 5.10.1 fetches it here for Auth0 too) and whether it equals the sub
  8. an MQTT CONNECT to the mobile-push broker (eu.mqtt.mobilepush…:8883, user
     IDK, password = the token) — connect, read the return code, disconnect;
     no subscribe, no publish

WHAT IT DOES NOT
  - no password field, no sign-in on your behalf
  - no token, VIN or e-mail in clear text (VINs are masked)
  - nothing written, nothing commanded on the vehicle; the MQTT leg only
    connects and disconnects

Usage (in YOUR terminal, so the browser callback reaches your localhost):
  python scripts/auth0_signin_probe.py [brand]
      brand: audi (default), volkswagen, seat, cupra

Please share the output on the #1712 issue when you test an unproven brand.
"""
from __future__ import annotations

import base64
import http.server
import json
import ssl
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import socket
import uuid
import webbrowser
from pathlib import Path

# Repo root on sys.path so the custom_components package imports.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from custom_components.vag_connect.cariad.auth import _auth0  # noqa: E402
from custom_components.vag_connect.cariad.models import (  # noqa: E402
    MYAUDI_APP_VERSION,
)


# Hosts this probe talks to from Python (the authorize step runs in the browser,
# not here). Some machines run a DNS blocker/VPN that sinkholes the VW/CARIAD
# names to a private IPv6 (``fd44:…``), which the token exchange then cannot
# reach — while the browser, on its own resolver, signs in fine. The override
# below resolves these names over DoH and pins the IPv4, scoped to this
# process (like ``curl --resolve``); it changes no system setting.
_RESOLVE_HOSTS = (
    "group.identity.vwgroup.io",
    "emea.bff.cariad.digital",
    # The MQTT broker: its name carries the same sinkhole IPv6, but DoH follows
    # the Event Grid CNAME chain to a public Azure gateway IP, so pinning it
    # lets the CONNECT reach the real broker instead of the dead-end address.
    "eu.mqtt.mobilepush.cariad.digital",
)
_real_getaddrinfo = socket.getaddrinfo
_PINNED: dict[str, str] = {}


def _doh_a(host: str) -> str | None:
    """One A record for *host* from Cloudflare DoH, or None. Two attempts, so a
    single transient blip does not leave a host unpinned."""
    url = (f"https://1.1.1.1/dns-query?name={urllib.parse.quote(host)}&type=A")
    req = urllib.request.Request(url, headers={"accept": "application/dns-json"})
    for attempt in range(2):
        try:
            with urllib.request.urlopen(req, timeout=12) as resp:
                data = json.loads(resp.read().decode("utf-8", "replace"))
        except Exception:  # noqa: BLE001
            if attempt == 0:
                time.sleep(1)
                continue
            return None
        for ans in data.get("Answer", []):
            if ans.get("type") == 1 and isinstance(ans.get("data"), str):
                return ans["data"]
        return None
    return None


def _install_doh_resolver() -> None:
    """Force the VW/CARIAD hosts to IPv4 for this process only.

    These names carry a bogus private IPv6 (``fd44:…``) on a machine with a DNS
    blocker/VPN; Python prefers that AAAA and the connection is reset, while the
    host answers fine over IPv4. For each host we take the real IPv4 — from DoH,
    else the system's own A record — and return only that, so no AAAA is tried.
    A host with no IPv4 at all (e.g. the Event Grid privatelink broker) is left
    to normal resolution. Scoped to this process; changes no system setting."""
    def _gai(host, port, *args, **kwargs):  # type: ignore[no-untyped-def]
        ip = _PINNED.get(host)
        if ip:
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, port))]
        return _real_getaddrinfo(host, port, *args, **kwargs)

    for host in _RESOLVE_HOSTS:
        ip = _doh_a(host)
        if not ip:
            try:
                ip = str(_real_getaddrinfo(host, 443, socket.AF_INET)[0][4][0])
            except Exception:  # noqa: BLE001
                ip = None
        if ip:
            _PINNED[host] = ip
            print(f"  DNS: {host} → {ip} (IPv4 forced; the private-IPv6 "
                  "answer on this machine is a dead end)")
    if _PINNED:
        socket.getaddrinfo = _gai  # type: ignore[assignment]


def _mask(value: str, keep: int = 4) -> str:
    if not value:
        return value
    return value[:keep] + f"…[{len(value)} chars]"


def _decode_jwt_claims(token: str) -> dict:
    """The claims of a JWT, no signature check (we read, we do not trust)."""
    parts = token.split(".")
    if len(parts) < 2:
        return {"_note": "not a JWT (opaque token)"}
    pad = parts[1] + "=" * (-len(parts[1]) % 4)
    try:
        return json.loads(base64.urlsafe_b64decode(pad))
    except Exception as exc:  # noqa: BLE001
        return {"_error": f"claims unreadable: {type(exc).__name__}"}


def _show_claims(name: str, token: str) -> None:
    claims = _decode_jwt_claims(token)
    print(f"\n  === {name} — metadata (the token itself is NOT shown) ===")
    for key in ("iss", "aud", "scope", "scp", "exp", "iat", "azp",
                "client_id", "token_type"):
        if key in claims:
            print(f"      {key}: {claims[key]}")
    for sensitive in ("sub", "email", "preferred_username", "vin", "name"):
        if sensitive in claims:
            print(f"      {sensitive}: {_mask(str(claims[sensitive]))}  (masked)")


#: Read-only CARIAD endpoints. Only GET; no commands, no writes. It prints
#: status and field names/counts — never VINs, values, tokens or e-mail.
_PROBES = [
    ("BFF garage (vehicle list)",
     "https://emea.bff.cariad.digital/vehicle/v1/vehicles"),
]


def _exchange(route: _auth0.Route, code: str, verifier: str) -> dict:
    # Route-aware: the same redirect_uri as at /authorize (RFC 6749 §4.1.3).
    body = _auth0.token_body_for(route, code=code, code_verifier=verifier)
    data = urllib.parse.urlencode(body, quote_via=urllib.parse.quote).encode()
    # The 5-header set WITHOUT x-assertion — the door that does not ask for the
    # attestation.
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept": "application/json",
        "User-Agent": "vag-connect-local-probe",
    }
    req = urllib.request.Request(route.token_url, data=data, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", "replace")
        try:
            payload = json.loads(raw)
        except Exception:  # noqa: BLE001
            payload = {"error": f"HTTP {exc.code}", "error_description": raw[:300]}
        print(f"\n  Token exchange refused: HTTP {exc.code}")
        print(f"  Classification: {_auth0.classify_refusal(payload)}")
        print(f"  error={payload.get('error')} "
              f"desc={str(payload.get('error_description'))[:200]}")
        return {}


def _probe_cariad(access_token: str) -> None:
    """Ask read-only what the token unlocks. Prints structure only."""
    print("\n  ====== WHAT THE TOKEN UNLOCKS (read-only) ======")
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json",
        "User-Agent": "vag-connect-local-probe",
    }
    first_vin = None
    for name, url in _PROBES:
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=25) as resp:
                status, raw = resp.status, resp.read(20000)
        except urllib.error.HTTPError as exc:
            status, raw = exc.code, b""
        except Exception as exc:  # noqa: BLE001
            print(f"    {name}: error {type(exc).__name__}")
            continue
        verdict = ("OPEN" if status == 200 else
                   "403 not entitled" if status == 403 else
                   "401 token refused" if status == 401 else f"HTTP {status}")
        print(f"    {name}: {verdict}")
        if status != 200:
            continue
        try:
            data = json.loads(raw)
        except Exception:  # noqa: BLE001
            print(f"      (response not JSON, {len(raw)} B)")
            continue
        vehicles = data.get("data") if isinstance(data, dict) else None
        if isinstance(vehicles, list):
            print(f"      vehicles: {len(vehicles)}")
            if vehicles and isinstance(vehicles[0], dict):
                print(f"      fields per vehicle: {sorted(vehicles[0])[:12]}")
                for vehicle in vehicles:
                    vin = vehicle.get("vin")
                    if isinstance(vin, str) and len(vin) == 17 and first_vin is None:
                        first_vin = vin  # kept internally, never printed

    if first_vin:
        base = "https://emea.bff.cariad.digital/vehicle/v1/vehicles"
        url = f"{base}/{first_vin}/capabilities"
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=25) as resp:
                status = resp.status
        except urllib.error.HTTPError as exc:
            status = exc.code
        except Exception as exc:  # noqa: BLE001
            status = -1
            print(f"    capabilities (masked VIN): error {type(exc).__name__}")
        if status != -1:
            print(f"    capabilities (one masked VIN): "
                  f"{'OPEN' if status == 200 else f'HTTP {status}'}")

    print("\n  Reading: OPEN = the Auth0 token reads this CARIAD channel. "
          "403 = a silo the token is not entitled to. Two-way commands "
          "(lock/climate) do NOT run over this — they stay on the MBB path.")


def _probe_mbbuser(access_token: str, token_sub: str | None) -> str | None:
    """GET {bff}/user/v1/mbbuser — read-only. myAudi 5.10.1 fetches the MBB user
    id here (``Authentication.MbbUserInfo``), for Auth0 and IdentityKit alike.
    Prints only whether an id came back and whether it equals the token ``sub``
    (both are masked); the id itself is never printed."""
    url = "https://emea.bff.cariad.digital/user/v1/mbbuser"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json",
        "User-Agent": "vag-connect-local-probe",
    }
    print("\n  ====== /user/v1/mbbuser (read-only) ======")
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=25) as resp:
            status, raw = resp.status, resp.read(8000)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")[:200]
        print(f"    HTTP {exc.code}  {body}")
        if "scope" in body.lower():
            print("    → the message names a scope: the token's scope set is "
                  "too narrow for this endpoint")
        return None
    except Exception as exc:  # noqa: BLE001
        print(f"    error {type(exc).__name__}")
        return None
    print(f"    HTTP {status}")
    if status != 200:
        return None
    try:
        mbb_id = (json.loads(raw).get("data") or {}).get("mbbUserId")
    except Exception:  # noqa: BLE001
        print(f"    (response not JSON, {len(raw)} B)")
        return None
    print(f"    mbbUserId returned: {bool(mbb_id)}"
          + (f"  ({_mask(str(mbb_id))})" if mbb_id else ""))
    if mbb_id and token_sub:
        print(f"    mbbUserId == token sub: {mbb_id == token_sub}  "
              "(equal ⇒ the two candidate ids are the same value)")
    return mbb_id if isinstance(mbb_id, str) and mbb_id else None


def _mqtt_connect_once(access_token: str, label: str, client_id: str) -> str:
    """One read-only MQTT v5 CONNECT to the mobile-push broker with the given
    client id, then DISCONNECT. No SUBSCRIBE, no PUBLISH. Returns the CONNACK
    reason code as text (or an error tag). Username ``IDK``, password = the
    access token (``MqttConnectionManagerImpl``). The client id may contain the
    sub or the mbbUserId; it is never printed, only its ``label``."""
    import paho.mqtt.client as mqtt  # noqa: PLC0415
    host, port = "eu.mqtt.mobilepush.cariad.digital", 8883
    box: dict[str, object] = {}
    try:
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,
                             client_id=client_id, protocol=mqtt.MQTTv5)
    except Exception:  # noqa: BLE001 — paho < 2.0
        client = mqtt.Client(client_id=client_id, protocol=mqtt.MQTTv5)
    client.username_pw_set("IDK", access_token)
    client.tls_set(cert_reqs=ssl.CERT_REQUIRED)

    def _on_connect(client: object, userdata: object, flags: object,
                    reason_code: object, properties: object = None) -> None:
        box["rc"] = reason_code

    client.on_connect = _on_connect
    try:
        client.connect(host, port, clean_start=True, keepalive=10)
        client.loop_start()
        for _ in range(80):
            if "rc" in box:
                break
            time.sleep(0.1)
        client.disconnect()
        client.loop_stop()
    except Exception as exc:  # noqa: BLE001
        return f"error {type(exc).__name__}: {str(exc)[:80]}"
    rc = box.get("rc")
    return "timeout (no CONNACK)" if rc is None else str(rc)


def _probe_mqtt(access_token: str, attempts: list[tuple[str, str]]) -> None:
    """Try each candidate client-id form at the broker — read-only, CONNECT only,
    one at a time, reporting the CONNACK reason code per form. The MQTT v5 codes
    are specific (Success=0, 0x85 client-id invalid, 0x87 not authorized, …), so
    they separate "this client id is wrong" from "the token is refused". No
    SUBSCRIBE and no PUBLISH are issued (a user-scoped SUBSCRIBE is a later step
    with its own go)."""
    print("\n  ====== MQTT CONNECT per client-id form (read-only, no subscribe) ======")
    try:
        import paho.mqtt.client  # noqa: F401, PLC0415
    except Exception:  # noqa: BLE001
        print("    paho-mqtt not installed — skipped")
        return
    for label, client_id in attempts:
        rc = _mqtt_connect_once(access_token, label, client_id)
        accepted = rc in ("Success", "0")
        print(f"    clientId={label}: CONNACK {rc}"
              f"{'  ← ACCEPTED' if accepted else ''}")
    print("    (no subscribe, no publish were issued; username IDK, token as "
          "password; MQTT v5)")


def _catch_code(redirect_uri: str, timeout_s: int = 300) -> str | None:
    """A tiny server on the callback's localhost port; catches ?code=."""
    parsed = urllib.parse.urlparse(redirect_uri)
    if parsed.scheme not in ("http", "https") or "localhost" not in (parsed.hostname or ""):
        return None  # app-scheme callback → paste mode
    port = parsed.port or 8080
    caught: dict = {}

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            query = urllib.parse.urlparse(self.path).query
            caught.update(urllib.parse.parse_qs(query))
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(
                b"<h2>Signed in. You can close this window and return to the "
                b"terminal.</h2>")

        def log_message(self, *args: object) -> None:
            return

    try:
        server = http.server.HTTPServer(("127.0.0.1", port), Handler)
    except OSError as exc:
        print(f"  Port {port} is busy ({exc}); switching to paste mode.")
        return None
    thread = threading.Thread(target=server.handle_request, daemon=True)
    thread.start()
    print(f"  (local mini-server on 127.0.0.1:{port}, waiting for the browser "
          f"callback …)")
    thread.join(timeout_s)
    server.server_close()
    codes = caught.get("code")
    return codes[0] if codes else None


def main() -> None:
    _install_doh_resolver()
    brand = (sys.argv[1] if len(sys.argv) > 1 else "audi").lower()
    routes = _auth0.routes_for(brand)
    if not routes:
        sys.exit(f"'{brand}' has no browser sign-in on this tenant. "
                 f"Try one of: {', '.join(sorted(_auth0.AUTH0_BRANDS))}.")
    if not _auth0.is_offered(brand):
        print(f"NOTE: {brand} is reachable but UNVERIFIED — this probe is how "
              f"we find out whether its code exchange works. Please share the "
              f"result on the #1712 issue.\n")

    route = next((r for r in routes if r.catchable), routes[0])
    verifier, challenge = _auth0.new_pkce_pair()
    state = _auth0.new_state()
    url = _auth0.authorization_url_for(
        route, code_challenge=challenge, state=state, nonce=_auth0.new_state())

    print(f"Brand: {brand}  ·  route: {route.key}  "
          f"({'catchable localhost' if route.catchable else 'app-scheme callback'})")
    print("\n1) Open this URL in your browser and sign in with your own "
          "account:\n")
    print(url)
    print()
    try:
        webbrowser.open(url)
    except Exception:  # noqa: BLE001
        pass

    code = _catch_code(route.redirect_uri)
    if not code:
        pasted = input(
            "\n2) If it was not caught automatically, paste the whole "
            "callback URL (or just the code) here:\n> ").strip()
        try:
            code = _auth0.parse_redirect(
                pasted, expected_redirect_uri=route.redirect_uri,
                expected_state=state)
        except _auth0.Auth0RedirectInvalid as exc:
            sys.exit(f"  Refused: {exc}")

    print("\n3) Exchanging the code for a token (your password was never "
          "involved) …")
    result = _exchange(route, code, verifier)
    if not result:
        sys.exit("  No token — see the classification above.")

    try:
        tokens = _auth0.read_token_response(result)
    except _auth0.Auth0ExchangeFailed as exc:
        sys.exit(f"  {exc}")

    print("\n  ====== WE ARE THROUGH ======")
    print(f"  response fields: {sorted(tokens)}")
    print(f"  token_type: {tokens.get('token_type')}")
    print(f"  expires_in: {tokens.get('expires_in')} s")
    if "scope" in tokens:
        print(f"  scopes: {tokens['scope']}")
    if tokens.get("access_token"):
        _show_claims("access_token", tokens["access_token"])
    if tokens.get("id_token"):
        _show_claims("id_token", tokens["id_token"])
    print(f"\n  refresh_token present: {'yes' if tokens.get('refresh_token') else 'no'}")

    if tokens.get("access_token"):
        _probe_cariad(tokens["access_token"])
        id_claims = _decode_jwt_claims(tokens.get("id_token") or "")
        token_sub = id_claims.get("sub") if isinstance(id_claims, dict) else None
        token_sub = token_sub if isinstance(token_sub, str) else None
        mbb_id = _probe_mbbuser(tokens["access_token"], token_sub)
        # Candidate client-id forms (the ids themselves are never printed). The
        # app connects with clientId myAudi-android-<ver>-<stored id>; Event Grid
        # usually ties the client id to the token identity, so sub and mbbUserId
        # are the likely accepted forms. The CONNACK per form tells us which.
        attempts: list[tuple[str, str]] = [
            (f"myAudi-android-{MYAUDI_APP_VERSION}-<random>",
             f"myAudi-android-{MYAUDI_APP_VERSION}-{uuid.uuid4()}"),
        ]
        if token_sub:
            attempts.append(("<token-sub>", token_sub))
        if mbb_id:
            attempts.append(("<mbbUserId>", mbb_id))
        attempts.append(("vag-connect-probe-<random> (control)",
                         f"vag-connect-probe-{uuid.uuid4().hex[:8]}"))
        _probe_mqtt(tokens["access_token"], attempts)

    print("\n  (The token values themselves were deliberately not printed. "
          "What you see above — audience, scopes, validity — says which "
          "permissions the sign-in carries.)")


if __name__ == "__main__":
    main()
