#!/usr/bin/env python3
# Copyright 2026 Prash Balan (@its-me-prash) — Apache License 2.0
"""Test: VW WeConnect-ID client BUT requesting mbb scope.

The previous try_vw_direct.py revealed MBB's exact expectation:
  "Audiences (...) don't match issuer (VWGMBB01DELIV1)."

So MBB wants id_token.aud to contain VWGMBB01DELIV1. Audi-IDK adds those
automatically because Audi clients have mbb scope by default. But maybe
the WeConnect-ID client (a24fba63) also supports mbb scope when explicitly
requested? Hasn't been tested yet — Auth0 might just silently strip it,
might error, or might actually grant it.

If it grants it: VW-namespace id_token + MBB audience = MBB-acceptable
token, AND it carries VW-side PPID → data endpoints might work too.
"""

from __future__ import annotations

import asyncio
import getpass
import importlib.util
import json
import sys
import types
from pathlib import Path

import aiohttp

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if sys.stderr.encoding and sys.stderr.encoding.lower() != "utf-8":
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO))

_ha = types.ModuleType("homeassistant")
sys.modules.setdefault("homeassistant", _ha)
for sub in ("config_entries", "core", "helpers", "const", "exceptions", "util"):
    sys.modules.setdefault(f"homeassistant.{sub}", types.ModuleType(f"homeassistant.{sub}"))


def _load(pkg: str, file_path: Path):
    spec = importlib.util.spec_from_file_location(pkg, file_path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[pkg] = mod
    spec.loader.exec_module(mod)
    return mod


_C = _REPO / "custom_components" / "vag_connect" / "cariad"
sys.modules["c"] = types.ModuleType("c"); sys.modules["c"].__path__ = [str(_C)]
sys.modules["c.auth"] = types.ModuleType("c.auth"); sys.modules["c.auth"].__path__ = [str(_C / "auth")]
_load("c.exceptions", _C / "exceptions.py")
_models = _load("c.models", _C / "models.py")
_idk = _load("c.auth.idk", _C / "auth" / "idk.py")


# WeConnect-ID client BUT scope explicitly includes mbb.
# Three scope variants to try (Auth0 may accept some, reject others).
_SCOPES_TO_TRY = [
    "openid profile mbb cars vin",
    "openid profile mbb cars vin offline_access",
    "openid profile mbb cars dealers vin badge",
    "openid profile badge cars dealers vin mbb",  # original + mbb appended
]


_MBB = "https://mbboauth-1d.prd.ece.vwg-connect.com"
_MBB_REG = f"{_MBB}/mbbcoauth/mobile/register/v1"
_MBB_TOKEN = f"{_MBB}/mbbcoauth/mobile/oauth2/v1/token"
_VW_UA = "Volkswagen/3.51.1-android/14"


def _decode_jwt_aud(jwt: str) -> str:
    """Decode aud claim from JWT (no signature verify)."""
    import base64 as _b64
    payload = jwt.split(".")[1]
    payload += "=" * (-len(payload) % 4)
    claims = json.loads(_b64.urlsafe_b64decode(payload))
    aud = claims.get("aud", "")
    return str(aud)[:200]


async def _try_login_with_scope(session, email: str, password: str, scope: str):
    """Login with WeConnect-ID client but custom scope. Returns (id_token, aud) or (None, error)."""
    brand = _models.BrandConfig(
        name="vw-mbb-test",
        client_id="a24fba63-34b3-4d43-b181-942111e6bda8@apps_vw-dilab_com",
        redirect_uri="weconnect://authenticated",
        user_agent=_VW_UA,
        api_base="https://msg.volkswagen.de",
        scope=scope,
    )
    auth = _idk.IDKAuth(session, brand)
    try:
        tokens = await auth.authenticate(email, password)
        aud = _decode_jwt_aud(tokens.id_token)
        return tokens.id_token, aud
    except Exception as exc:
        return None, str(exc)[:150]


async def _mbb_register_vw(session) -> str | None:
    body = {
        "client_name": "SM-A405FN", "platform": "google",
        "client_brand": "VW", "appName": "Volkswagen",
        "appVersion": "3.51.1", "appId": "de.volkswagen.car-net.eu.eremote",
    }
    async with session.post(
        _MBB_REG,
        data=json.dumps(body).encode(),
        headers={
            "Content-Type": "application/json; charset=utf-8",
            "Accept": "application/json", "User-Agent": _VW_UA,
        },
    ) as resp:
        if resp.status != 200:
            return None
        return json.loads(await resp.text())["client_id"]


async def _mbb_exchange(session, id_token: str, x_client: str):
    async with session.post(
        _MBB_TOKEN,
        data={
            "grant_type": "id_token",
            "token": id_token,
            "scope": "sc2:fal",
        },
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
            "User-Agent": _VW_UA,
            "X-Client-Id": x_client,
        },
    ) as resp:
        return resp.status, (await resp.text())[:250]


async def main() -> int:
    email = input("VW account email: ").strip()
    password = getpass.getpass("VW account password: ")
    if not email or not password:
        sys.exit("ERROR: email + password required")

    print("\n" + "=" * 90)
    print("TEST: WeConnect-ID Client with mbb scope variants")
    print("=" * 90)

    async with aiohttp.ClientSession() as session:
        x_vw = await _mbb_register_vw(session)
        if not x_vw:
            sys.exit("MBB register VW failed — abort")
        print(f"\nMBB X-Client-Id (VW brand): ...{x_vw[-12:]}")

        for i, scope in enumerate(_SCOPES_TO_TRY, 1):
            print(f"\n[{i}/{len(_SCOPES_TO_TRY)}] Login with scope: '{scope}'")
            id_token, info = await _try_login_with_scope(session, email, password, scope)

            if id_token is None:
                print(f"      ✗ Login FAILED: {info}")
                continue

            print(f"      ✓ Login OK ({len(id_token)} chars)")
            print(f"        id_token aud: {info}")

            has_mbb_aud = "VWGMBB01" in info
            if has_mbb_aud:
                print("         aud contains VWGMBB01* — MBB might accept!")
            else:
                print("         aud does NOT contain VWGMBB01* — IDK silently dropped mbb scope")

            status, body = await _mbb_exchange(session, id_token, x_vw)
            marker = "✓" if status == 200 else "✗"
            print(f"        {marker} MBB exchange: HTTP {status}")
            print(f"        Body: {body}")

            if status == 200:
                print("\n BREAKTHROUGH — WeConnect-ID + this scope WORKS!")
                print(f"   Save this scope for vag-connect-ha v1.26.3:")
                print(f"   scope = \"{scope}\"")
                return 0

        print("\n" + "=" * 90)
        print("✗ Keine WeConnect-ID + scope-Variante hat MBB überzeugt.")
        print("  WeConnect-ID Client kann keine VWGMBB01* audiences ausstellen.")
        print("  Das bestätigt endgültig: für VW VINs gibt es 2026 keinen")
        print("  öffentlich nutzbaren Pfad zu MBB legacy backend.")
        print("=" * 90)

    return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
