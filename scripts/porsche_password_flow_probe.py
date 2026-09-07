#!/usr/bin/env python3
# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Probe how far the My-Porsche Auth0 password flow gets, past passkey-enrollment.

WHY

#1337 confirmed the password flow (custom_components/vag_connect/cariad/auth/
porsche.py:PorscheAuth) dies at a rendered HTTP-200 page instead of a redirect,
right after the password POST. We assumed that's a captcha/consent wall, and
separately assumed (by analogy with the Audi/VW BFF wall) that even a completed
browser login would fail at the token exchange behind Play-Integrity attestation.
Neither assumption has been tested against Porsche's own token endpoint with a
real account.

A manual browser walkthrough on 2026-09-07 showed the HTTP-200 page is often the
Auth0 ACUL **passkey-enrollment** screen (/u/passkey-enrollment), not a captcha —
and declining it ("continue without passkeys") does yield a real authorization
code at my.porsche.com?code=... So the wall porsche.py hits may just be an
unhandled screen, not a hard captcha/attestation dead end.

This probe adds the one missing step (decline passkey-enrollment, the same way
CJNE/pyporscheconnectapi's _skip_passkey_enrollment does) and then, critically,
actually calls POST /oauth/token with the resulting code. That answers the real
open question: does Porsche's Auth0 token endpoint hand back an access_token, or
does it reject the exchange (attestation / assertion error) the way the VW-Group
BFF does for Audi? Either answer is useful and gets printed verbatim (redacted).

WHAT IT TOUCHES

Only identity.porsche.com. Your e-mail/password are entered at the terminal
prompt (password via getpass, never echoed) and used only in the two Auth0 POSTs
below — they are never printed, logged, or written to disk. Any code/token in
the output is truncated. Run this only against a login you control (a
vehicle-less test account is ideal, exactly so a real car is never touched).

USAGE

  python scripts/porsche_password_flow_probe.py
"""

from __future__ import annotations

import base64
import getpass
import hashlib
import http.cookiejar
import json
import re
import secrets
import urllib.error
import urllib.parse
import urllib.request

_AUTH_SERVER = "identity.porsche.com"
_AUTH_URL = f"https://{_AUTH_SERVER}/authorize"
_TOKEN_URL = f"https://{_AUTH_SERVER}/oauth/token"
_CLIENT_ID = "XhygisuebbrqQ80byOuU5VncxLIm8E6H"
_REDIRECT_URI = "my-porsche-app://auth0/callback"
_AUDIENCE = "https://api.porsche.com"
_SCOPE = (
    "openid profile email offline_access mbb ssodb badge vin dealers cars "
    "charging manageCharging plugAndCharge climatisation manageClimatisation "
    "pid:user_profile.porscheid:read pid:user_profile.vehicles:read"
)
_UA = "My Porsche/2.1.0 (iPhone; iOS 17.0; Scale/3.00)"
_TIMEOUT = 30
_MAX_HOPS = 10


class _NoRedirect(urllib.request.HTTPErrorProcessor):
    """Surface 3xx as a normal response instead of urllib auto-following it.

    Needed because one hop in this chain redirects to the app custom-scheme
    ``my-porsche-app://...``, which urllib cannot open at all.
    """

    def http_response(self, request, response):
        return response

    https_response = http_response


def _opener() -> urllib.request.OpenerDirector:
    jar = http.cookiejar.CookieJar()
    return urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(jar), _NoRedirect()
    )


def _pkce() -> tuple[str, str]:
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).rstrip(b"=").decode()
    digest = hashlib.sha256(verifier.encode()).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    return verifier, challenge


def _extract_code(url: str) -> str | None:
    if not url.startswith(_REDIRECT_URI):
        return None
    query = url.split("?", 1)[-1] if "?" in url else ""
    codes = urllib.parse.parse_qs(query).get("code")
    return codes[0] if codes else None


def _request(opener, method: str, url: str, data: dict | None = None) -> tuple[int, str, str]:
    body = urllib.parse.urlencode(data).encode() if data is not None else None
    req = urllib.request.Request(
        url,
        data=body,
        method=method,
        headers={
            "User-Agent": _UA,
            "Content-Type": "application/x-www-form-urlencoded",
        },
    )
    with opener.open(req, timeout=_TIMEOUT) as resp:
        location = resp.headers.get("Location", "")
        text = resp.read().decode("utf-8", "replace")
        return resp.status, location, text


def _skip_passkey_enrollment(opener, url: str, html: str) -> str | None:
    """POST the decline action for the Auth0 ACUL passkey-enrollment screen.

    Mirrors CJNE/pyporscheconnectapi's ``_skip_passkey_enrollment``: the page
    embeds a base64 JSON context via ``atob("...")``; we need its
    ``transaction.state`` to post ``action=abort-passkey-enrollment`` back.
    """
    match = re.search(r'atob\("([A-Za-z0-9+/=]+)"', html)
    if not match:
        return None
    try:
        context = json.loads(base64.b64decode(match.group(1)).decode("utf-8"))
    except (ValueError, json.JSONDecodeError) as exc:
        print(f"  (could not parse passkey-enrollment context: {exc})")
        return None
    state = context.get("transaction", {}).get("state")
    if not state:
        return None
    status, location, _ = _request(opener, "POST", url, {
        "state": state,
        "action": "abort-passkey-enrollment",
        "acul-sdk": "@auth0/auth0-acul-js@1.2.0",
    })
    print(f"  passkey-enrollment decline → HTTP {status}")
    return location or None


def main() -> int:
    print("== Porsche password-flow probe (past passkey-enrollment) ==")
    email = input("Porsche ID e-mail: ").strip()
    password = getpass.getpass("Password (not echoed): ")

    opener = _opener()
    verifier, challenge = _pkce()
    state_hint = base64.urlsafe_b64encode(secrets.token_bytes(12)).rstrip(b"=").decode()

    # 1) /authorize
    params = urllib.parse.urlencode({
        "client_id": _CLIENT_ID,
        "redirect_uri": _REDIRECT_URI,
        "response_type": "code",
        "scope": _SCOPE,
        "audience": _AUDIENCE,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "state": state_hint,
    })
    status, location, _ = _request(opener, "GET", f"{_AUTH_URL}?{params}")
    print(f"authorize → HTTP {status}")
    m = re.search(r"[?&]state=([^&]+)", location)
    if not m:
        print("FAIL — no Auth0 state in the redirect. Can't continue.")
        return 2
    auth0_state = urllib.parse.unquote(m.group(1))

    # 2) /u/login/identifier
    status, location, text = _request(
        opener,
        "POST",
        f"https://{_AUTH_SERVER}/u/login/identifier?state={auth0_state}",
        {
            "state": auth0_state, "username": email, "js-available": "true",
            "webauthn-available": "true", "is-brave": "false",
            "webauthn-platform-authenticator-available": "false", "action": "default",
        },
    )
    print(f"login/identifier → HTTP {status}")
    if status == 400:
        print("STOP — Porsche wants a captcha at the identifier step. This probe "
              "doesn't solve captchas. Body (first 300 chars):")
        print(f"  {text[:300]!r}")
        return 3

    # 3) /u/login/password
    status, location, text = _request(
        opener,
        "POST",
        f"https://{_AUTH_SERVER}/u/login/password?state={auth0_state}",
        {"state": auth0_state, "username": email, "password": password, "action": "default"},
    )
    print(f"login/password → HTTP {status}")
    if status == 400:
        print("STOP — wrong credentials (Porsche returns 400, not 401, here).")
        return 4

    # 4) follow redirects, transparently declining passkey-enrollment if it shows up.
    current = urllib.parse.urljoin(f"https://{_AUTH_SERVER}/u/login/password", location)
    code: str | None = None
    for hop in range(_MAX_HOPS):
        code = _extract_code(current)
        if code:
            break
        if not current.startswith("https://"):
            print(f"  hop {hop}: non-https target ({current[:40]}...), stopping.")
            break
        status, location, text = _request(opener, "GET", current)
        host = urllib.parse.urlsplit(current).hostname
        print(f"  hop {hop}: {host} → HTTP {status}")
        if status in (301, 302, 303, 307, 308):
            current = urllib.parse.urljoin(current, location)
            continue
        if "/u/passkey-enrollment" in current:
            resumed = _skip_passkey_enrollment(opener, current, text)
            if resumed:
                current = urllib.parse.urljoin(current, resumed)
                continue
        print("  → rendered a page, not a redirect, and it wasn't a passkey "
              "screen we could clear. This is the real wall (captcha/consent).")
        break

    if not code:
        print("\nVerdict: NO authorization code obtained. Stops before we can "
              "even test the token exchange.")
        return 5

    print(f"\nGot authorization code (len {len(code)}, not printed in full).")

    # 5) the actual open question: does the token exchange succeed?
    status, _, text = _request(opener, "POST", _TOKEN_URL, {
        "grant_type": "authorization_code",
        "client_id": _CLIENT_ID,
        "code": code,
        "redirect_uri": _REDIRECT_URI,
        "code_verifier": verifier,
    })
    print(f"\noauth/token → HTTP {status}")
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        data = {"_raw": text[:500]}
    if status == 200:
        at = str(data.get("access_token", ""))
        print("SUCCESS — token exchange worked. Verdict: the password flow is "
              "viable end-to-end on this account (no attestation wall here).")
        print(f"  access_token: {at[:12]}... (len {len(at)}), "
              f"refresh_token present: {bool(data.get('refresh_token'))}")
        return 0
    print(f"body: {json.dumps({k: v for k, v in data.items() if k != 'access_token'})[:500]}")
    print("Verdict: authorization code was issued, but the token endpoint "
          "rejected the exchange (see error above) — that IS the real wall, "
          "and now we have Porsche's literal error for it instead of a guess.")
    return 6


if __name__ == "__main__":
    raise SystemExit(main())
