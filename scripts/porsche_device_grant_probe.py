#!/usr/bin/env python3
# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Probe whether a Porsche account can do an RFC-8628 device-authorization grant.

WHY

Porsche is migrating My-Porsche (Auth0 email+password) accounts to Porsche One
(an approve-in-your-browser / device-code login). The integration's password
flow now provably dies on a captcha/consent page at identity.porsche.com (#1337),
so the realistic way in is the device grant. But the Porsche One path has never
been verified live, and its first step — fetching the Porsche One client_id from
``api.ppa.porsche.com/v1/mobile/clientId`` — currently returns HTTP 502, so we
can't even start it that way.

This probe SKIPS the 502 client-id fetch and instead tries the device grant with
the legacy My-Porsche Auth0 client we already hold. Both apps share the same
Porsche ID, and the browser device-approval happens at identity.porsche.com
regardless of which app is installed — so this answers the one open question:

    does /oauth/device/code work at all on an existing Porsche account with a
    client_id we already have?

A 200 with a user_code (and, after you approve in the browser, a minted token)
means the device grant is viable and worth wiring into the integration. A
``400 unauthorized_client`` means this client is not allowed the grant and we
need a different one.

WHAT IT TOUCHES

Only ``identity.porsche.com`` (OIDC discovery + device/token endpoints). It does
NOT enter your e-mail or password anywhere — the only sign-in is the browser
approval you do yourself. It does NOT touch Home Assistant, the integration, or
any account data. Tokens it might mint are printed truncated and never stored.

USAGE

  python scripts/porsche_device_grant_probe.py
  python scripts/porsche_device_grant_probe.py --client-id <other> --no-poll

Then open the printed URL, sign in + approve, and let it poll (or Ctrl-C).
"""

from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.parse
import urllib.request

# The legacy My-Porsche Auth0 client we already hold (custom_components/vag_connect/
# cariad/auth/porsche.py:_CLIENT_ID). We inject it to skip the 502 client-id fetch.
_DEFAULT_CLIENT_ID = "XhygisuebbrqQ80byOuU5VncxLIm8E6H"
_DISCOVERY_URL = "https://identity.porsche.com/.well-known/openid-configuration"
_DEVICE_SCOPE = "openid profile email ssodb mbb offline_access"
_DEVICE_GRANT = "urn:ietf:params:oauth:grant-type:device_code"
_UA = "PorscheOne/12.24.27 (Android)"
_TIMEOUT = 30


def _get_json(url: str) -> tuple[int, dict]:
    req = urllib.request.Request(
        url, headers={"User-Agent": _UA, "Accept": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")
        try:
            return exc.code, json.loads(body)
        except json.JSONDecodeError:
            return exc.code, {"_raw": body[:300]}


def _post_form(url: str, form: dict) -> tuple[int, dict]:
    data = urllib.parse.urlencode(form).encode()
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "User-Agent": _UA,
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")
        try:
            return exc.code, json.loads(body)
        except json.JSONDecodeError:
            return exc.code, {"_raw": body[:300]}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--client-id", default=_DEFAULT_CLIENT_ID,
                    help="OAuth client_id to try (default: legacy My-Porsche).")
    ap.add_argument("--scope", default=_DEVICE_SCOPE, help="device-code scope")
    ap.add_argument("--no-poll", action="store_true",
                    help="only request the device code; don't wait for approval")
    args = ap.parse_args()

    print("== Porsche device-grant probe ==")
    print(f"client_id : {args.client_id}")

    # 1) OIDC discovery — resolves the device/token endpoints; check the grant.
    status, doc = _get_json(_DISCOVERY_URL)
    if status != 200:
        print(f"FAIL discovery HTTP {status}: {doc}")
        return 2
    device_ep = doc.get("device_authorization_endpoint", "")
    token_ep = doc.get("token_endpoint", "")
    grants = doc.get("grant_types_supported", [])
    print(f"device_authorization_endpoint: {device_ep or '(none advertised)'}")
    print(f"token_endpoint               : {token_ep or '(none)'}")
    print(f"device_code advertised       : {_DEVICE_GRANT in grants}")
    if not device_ep or not token_ep:
        print("FAIL — tenant does not advertise a device endpoint. Verdict: NO.")
        return 3

    # 2) device_authorization — the decisive call.
    status, data = _post_form(device_ep, {
        "client_id": args.client_id, "scope": args.scope,
    })
    print(f"\ndevice_authorization → HTTP {status}")
    if status != 200:
        err = data.get("error", "")
        print(f"body: {data}")
        if err == "unauthorized_client":
            print("Verdict: NO — this client is not allowed the device grant. "
                  "A different client_id is needed.")
        else:
            print(f"Verdict: NO / needs investigation (error={err!r}).")
        return 4

    user_code = data.get("user_code", "")
    uri = data.get("verification_uri_complete") or data.get("verification_uri", "")
    device_code = data.get("device_code", "")
    interval = int(data.get("interval", 5))
    expires_in = int(data.get("expires_in", 600))
    print("SUCCESS — the device grant STARTED (this client is allowed).")
    print(f"\n  Open: {uri}")
    print(f"  Code: {user_code}")
    print("  Sign in + approve in the browser.\n")
    if args.no_poll:
        print("(--no-poll) Not waiting. The 200 above already proves the grant "
              "is allowed for this client. Verdict: YES (start).")
        return 0

    # 3) poll the token endpoint until approval / denial / expiry.
    deadline = time.monotonic() + min(expires_in, 600)
    while time.monotonic() < deadline:
        time.sleep(interval)
        status, data = _post_form(token_ep, {
            "grant_type": _DEVICE_GRANT,
            "client_id": args.client_id,
            "device_code": device_code,
        })
        if status == 200:
            at = str(data.get("access_token", ""))
            print("APPROVED — a token was minted. Verdict: YES (full device "
                  "grant works end-to-end on this account).")
            print(f"  access_token: {at[:12]}… (len {len(at)}), "
                  f"refresh_token present: {bool(data.get('refresh_token'))}")
            return 0
        err = str(data.get("error", ""))
        if err in ("authorization_pending", "slow_down"):
            if err == "slow_down":
                interval += 5
            print("  …pending")
            continue
        print(f"token poll → HTTP {status} error={err!r}: {data}")
        print("Verdict: the code was issued but the token exchange was rejected "
              f"(error={err!r}).")
        return 5
    print("Timed out waiting for approval. The device_authorization 200 above "
          "still proves the grant is ALLOWED for this client. Verdict: YES (start).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
