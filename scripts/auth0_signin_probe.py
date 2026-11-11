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

WHAT IT DOES NOT
  - no password field, no sign-in on your behalf
  - no token, VIN or e-mail in clear text (VINs are masked)
  - nothing written, nothing commanded on the vehicle

Usage (in YOUR terminal, so the browser callback reaches your localhost):
  python scripts/auth0_signin_probe.py [brand]
      brand: audi (default), volkswagen, seat, cupra

Please share the output on the #1712 issue when you test an unproven brand.
"""
from __future__ import annotations

import base64
import http.server
import json
import sys
import threading
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from pathlib import Path

# Repo root on sys.path so the custom_components package imports.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from custom_components.vag_connect.cariad.auth import _auth0  # noqa: E402


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

    print("\n  (The token values themselves were deliberately not printed. "
          "What you see above — audience, scopes, validity — says which "
          "permissions the sign-in carries.)")


if __name__ == "__main__":
    main()
