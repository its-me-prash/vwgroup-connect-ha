#!/usr/bin/env python3
# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
"""Decode the id_token currently in mbb.local.bru and print SAFE claims only.

Usage:
    python scripts/decode_id_token.py

Prints aud / iss / iat / exp / scp / scope / lee / aat / jtt — the structural
JWT claims that show what kind of token IDK issued. Skips: sub, email, name,
nickname, sid, jti, brandid (anything personally identifiable).

Use this to debug why MBB rejects the id_token: if `aud` matches the legacy
We Connect client_id (9496332b-...) AND scopes include `mbb` → token is
correctly shaped, MBB rejection has another root cause. If aud is still
a24fba63-... (Cariad WeConnect ID) → the script didn't actually swap brands,
re-run with --brand vw-mbb explicitly.
"""

from __future__ import annotations

import base64
import json
import sys
from pathlib import Path


_REPO = Path(__file__).resolve().parent.parent
_LOCAL = _REPO / "tests" / "bruno" / "mbb_legacy" / "environments" / "mbb.local.bru"

# Whitelist would miss new/unknown claims that might be diagnostic.
# Use a sensitive denylist instead — print everything else.
_SENSITIVE_CLAIMS = {
    "sub", "email", "name", "nickname", "sid", "brandid", "jti",
    "picture", "groupid", "legacy_ids", "phone_number",
    "given_name", "family_name", "address", "birthdate", "preferred_username",
    "email_verified", "phone_verified",
}


def _decode_jwt_payload(jwt: str) -> dict:
    """Decode JWT payload (claim section) — header + signature ignored."""
    parts = jwt.split(".")
    if len(parts) != 3:
        raise ValueError(f"Not a valid JWT (expected 3 parts, got {len(parts)})")
    payload = parts[1]
    # JWT base64url, padding removed
    payload += "=" * (-len(payload) % 4)
    raw = base64.urlsafe_b64decode(payload)
    return json.loads(raw)


def main() -> int:
    if not _LOCAL.exists():
        print(f"ERROR: {_LOCAL} does not exist.", file=sys.stderr)
        print("Run: python scripts/get_idk_token.py --brand vw-mbb --write-bruno",
              file=sys.stderr)
        return 1

    content = _LOCAL.read_text(encoding="utf-8")

    tokens: dict[str, str] = {}
    for line in content.splitlines():
        line = line.strip()
        for field in ("idk_id_token", "vw_access_token", "vw_refresh_token"):
            prefix = f"{field}:"
            if line.startswith(prefix):
                value = line[len(prefix):].strip()
                if value and not value.startswith(("PASTE_", "WILL_BE_FILLED_")):
                    tokens[field] = value

    if not tokens:
        print("No tokens found in mbb.local.bru — did you run get_idk_token.py?",
              file=sys.stderr)
        return 1

    for field, jwt in tokens.items():
        print(f"\n── {field} ──")
        try:
            claims = _decode_jwt_payload(jwt)
        except Exception as exc:
            print(f"  (not a JWT or decode failed: {exc})")
            continue

        # Print all non-sensitive claims (denylist instead of whitelist
        # so we don't miss new diagnostic claims like `nonce` or `acr`).
        for key in sorted(claims.keys()):
            if key in _SENSITIVE_CLAIMS:
                continue
            value = claims[key]
            if isinstance(value, (int, float)):
                if key in ("iat", "exp", "auth_time"):
                    from datetime import datetime, timezone
                    dt = datetime.fromtimestamp(int(value), tz=timezone.utc)
                    print(f"  {key:14s}: {value} ({dt.isoformat()})")
                    continue
            # Truncate long string values to avoid spamming
            if isinstance(value, str) and len(value) > 100:
                value = value[:80] + "..." + value[-10:]
            print(f"  {key:14s}: {value}")

        # Quick sanity flags
        aud = claims.get("aud", "")
        scopes = (claims.get("scp") or claims.get("scope") or "").split()
        print()
        if "9496332b" in str(aud):
            print("  ✓ aud = LEGACY We Connect client (correct for MBB)")
        elif "a24fba63" in str(aud):
            print("  ✗ aud = MODERN WeConnect ID client (WRONG for MBB)")
        elif aud:
            print(f"  ? aud unknown: {aud}")
        if scopes:
            if "mbb" in scopes:
                print("  ✓ scope contains 'mbb' (correct for MBB)")
            else:
                print(f"  ✗ scope MISSING 'mbb' — got: {' '.join(scopes)}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
