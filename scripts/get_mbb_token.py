#!/usr/bin/env python3
# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
"""End-to-end MBB token helper for Golf 7 GTE PHEV (pre-Cariad).

Runs the FULL flow:
  1. IDK login via Audi-IDK client (gets id_token with mbb scope + VWGMBB01* aud)
  2. Register MBB client (POST /mbbcoauth/mobile/register/v1) with Audi brand
  3. Exchange id_token for MBB vwToken (POST /mbbcoauth/mobile/oauth2/v1/token)
  4. Write all 4 tokens to tests/bruno/mbb_legacy/environments/mbb.local.bru:
       idk_id_token  → fresh Audi-IDK id_token
       x_client_id   → freshly-registered MBB client_id
       vw_access_token  → MBB vwToken (NOT Cariad-side)
       vw_refresh_token → MBB refresh_token

After this succeeds, Bruno stages 03-18 use the MBB vwToken to call
msg.volkswagen.de/fs-car/... endpoints for the actual GTE data.

Usage:
    python scripts/get_mbb_token.py
    python scripts/get_mbb_token.py --email me@example.com
    python scripts/get_mbb_token.py --mfa 123456

Reports SUCCESS or FAILURE clearly so we know if MBB still works for our
account/region/vehicle without needing to round-trip through Bruno.
"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import importlib.util
import json
import sys
import types
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO))

# Stub homeassistant before any imports of vag_connect.cariad
_ha_stub = types.ModuleType("homeassistant")
sys.modules.setdefault("homeassistant", _ha_stub)
for sub in ("config_entries", "core", "helpers", "const", "exceptions", "util"):
    sys.modules.setdefault(f"homeassistant.{sub}", types.ModuleType(f"homeassistant.{sub}"))


def _load_pkg_module(pkg_path: str, file_path: Path) -> types.ModuleType:
    spec = importlib.util.spec_from_file_location(pkg_path, file_path)
    if not spec or not spec.loader:
        raise RuntimeError(f"Cannot load {pkg_path} from {file_path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[pkg_path] = mod
    spec.loader.exec_module(mod)
    return mod


_CARIAD_DIR = _REPO / "custom_components" / "vag_connect" / "cariad"
sys.modules["cariad_auth_only"] = types.ModuleType("cariad_auth_only")
sys.modules["cariad_auth_only"].__path__ = [str(_CARIAD_DIR)]
sys.modules["cariad_auth_only.auth"] = types.ModuleType("cariad_auth_only.auth")
sys.modules["cariad_auth_only.auth"].__path__ = [str(_CARIAD_DIR / "auth")]

_exc = _load_pkg_module("cariad_auth_only.exceptions", _CARIAD_DIR / "exceptions.py")
_models = _load_pkg_module("cariad_auth_only.models", _CARIAD_DIR / "models.py")
_idk = _load_pkg_module("cariad_auth_only.auth.idk", _CARIAD_DIR / "auth" / "idk.py")

import aiohttp  # noqa: E402

IDKAuth = _idk.IDKAuth
AuthenticationError = _exc.AuthenticationError
RateLimitError = _exc.RateLimitError
TermsAndConditionsError = _exc.TermsAndConditionsError
TwoFactorRequiredError = _exc.TwoFactorRequiredError
MarketingConsentError = _exc.MarketingConsentError


#  WINNER (verified 2026-05-10 via try_vw_with_mbb.py):
# WeConnect-ID client (a24fba63) + scope including 'mbb' produces an
# id_token with VWGMBB01DELIV1 + VWGMBB01CNAPP1 in aud[], AND the user_id
# inside is the VW-side PPID (matches VW MBB user database). Combined with
# VW-brand MBB register, gives a vwToken in VW namespace that should pass
# CLS check for VW VINs (Golf 7 GTE etc.).
_BRAND_VW_NATIVE_MBB = _models.BrandConfig(
    name="vw-mbb",
    client_id="a24fba63-34b3-4d43-b181-942111e6bda8@apps_vw-dilab_com",
    redirect_uri="weconnect://authenticated",
    user_agent="Volkswagen/3.51.1-android/14",
    api_base="https://msg.volkswagen.de",
    # CRITICAL: 'mbb' must be in scope — that's what makes IDK add VWGMBB01*
    # audiences to the resulting id_token. Tested scope variants in
    # try_vw_with_mbb.py — 'openid profile mbb cars vin' is minimal working set.
    scope="openid profile mbb cars vin",
)

# Audi-IDK fallback — used to work for OAuth exchange but token ends up in
# Audi namespace, fails CLS check for VW VINs. Kept for diagnostic purposes.
_BRAND_VW_VIA_AUDI = _models.BrandConfig(
    name="vw-via-audi",
    client_id="09b6cbec-cd19-4589-82fd-363dfa8c24da@apps_vw-dilab_com",
    redirect_uri="myaudi:///",
    user_agent="Android/4.31.0 (Build 800341641.root project 'myaudi_android'.ext.buildTime) Android/13",
    api_base="https://msg.volkswagen.de",
    scope=(
        "address profile badge birthdate birthplace nationalIdentifier "
        "nationality profession email vin phone nickname name picture mbb "
        "gallery openid"
    ),
)

# VW NA "MyVW" client — VW-namespace AND has mbb in scope. Worth trying for
# EU users even though region-restricted; might be IDK's only remaining
# VW-side mbb-scoped client after the legacy Car-Net deprecation.
_BRAND_VW_NA = _models.BrandConfig(
    name="vw-na",
    client_id="59992128-69a9-42c3-8621-7942041ba824_MYVW_ANDROID",
    redirect_uri="kombi:///login",
    user_agent="MyVW/1.0 Android",
    api_base="https://msg.volkswagen.de",
    scope="openid profile email offline_access mbb vin cars dealers",
)


_MBB_OAUTH_BASE = "https://mbboauth-1d.prd.ece.vwg-connect.com"
_MBB_REGISTER_URL = f"{_MBB_OAUTH_BASE}/mbbcoauth/mobile/register/v1"
_MBB_TOKEN_URL = f"{_MBB_OAUTH_BASE}/mbbcoauth/mobile/oauth2/v1/token"
_BRUNO_LOCAL = (
    _REPO / "tests" / "bruno" / "mbb_legacy" / "environments" / "mbb.local.bru"
)
_BRUNO_TEMPLATE = _BRUNO_LOCAL.with_name("mbb.template.bru")

# Two registration variants — the script tries Audi first (matches id_token
# brand) then falls back to VW (matches VIN brand). We DON'T know yet which
# combination MBB accepts for cross-brand VW-via-Audi-IDK access.
_REG_BODY_AUDI = {
    "client_name": "SM-A405FN",
    "platform": "google",
    "client_brand": "Audi",
    "appName": "myAudi",
    "appVersion": "4.31.0",
    "appId": "de.myaudi.mobile.assistant",
}
_REG_BODY_VW = {
    "client_name": "SM-A405FN",
    "platform": "google",
    "client_brand": "VW",
    "appName": "Volkswagen",
    "appVersion": "3.51.1",
    "appId": "de.volkswagen.car-net.eu.eremote",
}

_AUDI_USER_AGENT = (
    "Android/4.31.0 (Build 800341641.root project 'myaudi_android'.ext.buildTime) "
    "Android/13"
)
_VW_USER_AGENT = "Volkswagen/3.51.1-android/14"


async def _idk_login(
    session: aiohttp.ClientSession,
    brand: object,
    email: str,
    password: str,
    mfa: str | None,
):
    auth = IDKAuth(session, brand)
    return await auth.authenticate(email, password, mfa_code=mfa)


async def _mbb_register(
    session: aiohttp.ClientSession, brand: str = "VW"
) -> str:
    """POST /mbbcoauth/mobile/register/v1 → returns the registered client_id.

    brand: "VW" or "Audi" — controls the registration body. The resulting
    xclientId is bound to the brand's namespace at MBB. To access VW-VIN
    data, register with brand="VW" so the vwToken carries XID_APP_VW.
    """
    body_data = _REG_BODY_VW if brand == "VW" else _REG_BODY_AUDI
    user_agent = _VW_USER_AGENT if brand == "VW" else _AUDI_USER_AGENT
    headers = {
        "Content-Type": "application/json; charset=utf-8",
        "Accept": "application/json",
        "User-Agent": user_agent,
    }
    async with session.post(
        _MBB_REGISTER_URL,
        data=json.dumps(body_data).encode(),
        headers=headers,
    ) as resp:
        body = await resp.text()
        if resp.status != 200:
            raise RuntimeError(
                f"MBB register ({brand}) failed: HTTP {resp.status}\n{body[:300]}"
            )
        data = json.loads(body)
        client_id = data.get("client_id")
        if not client_id:
            raise RuntimeError(f"MBB register response has no client_id: {body[:200]}")
        return client_id


async def _mbb_exchange(
    session: aiohttp.ClientSession, id_token: str, x_client_id: str
) -> dict:
    """POST id_token → MBB vwToken pair."""
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept": "application/json",
        "User-Agent": _AUDI_USER_AGENT,
        "X-Client-Id": x_client_id,
    }
    data = {
        "grant_type": "id_token",
        "token": id_token,
        "scope": "sc2:fal",
    }
    async with session.post(_MBB_TOKEN_URL, data=data, headers=headers) as resp:
        body = await resp.text()
        if resp.status != 200:
            raise RuntimeError(
                f"MBB token exchange failed: HTTP {resp.status}\n{body[:400]}"
            )
        return json.loads(body)


def _write_bruno(
    id_token: str, x_client_id: str, access_token: str, refresh_token: str
) -> Path:
    """Write all 4 values to mbb.local.bru (creates from template if needed)."""
    if not _BRUNO_LOCAL.exists():
        if not _BRUNO_TEMPLATE.exists():
            raise RuntimeError(f"Neither {_BRUNO_LOCAL} nor template found.")
        _BRUNO_LOCAL.write_text(
            _BRUNO_TEMPLATE.read_text(encoding="utf-8"), encoding="utf-8"
        )
        print(f"→ Created {_BRUNO_LOCAL.name} from template.", file=sys.stderr)

    content = _BRUNO_LOCAL.read_text(encoding="utf-8")

    import re as _re  # noqa: PLC0415

    def _sub(field: str, value: str, text: str) -> str:
        pattern = rf"^(\s*{_re.escape(field)}:\s*).*$"
        return _re.sub(
            pattern, lambda m: f"{m.group(1)}{value}", text, flags=_re.MULTILINE
        )

    content = _sub("idk_id_token", id_token, content)
    content = _sub("x_client_id", x_client_id, content)
    content = _sub("vw_access_token", access_token, content)
    content = _sub("vw_refresh_token", refresh_token, content)
    _BRUNO_LOCAL.write_text(content, encoding="utf-8")
    return _BRUNO_LOCAL


async def _run(email: str, password: str, mfa: str | None, brand_choice: str = "vw-mbb") -> int:
    brand = {
        "vw-mbb": _BRAND_VW_NATIVE_MBB,
        "vw-via-audi": _BRAND_VW_VIA_AUDI,
        "vw-na": _BRAND_VW_NA,
    }.get(brand_choice, _BRAND_VW_NATIVE_MBB)
    print(f"\n┌─ STEP 1 — IDK login (brand={brand_choice}) ─────────────────────────",
          file=sys.stderr)
    try:
        async with aiohttp.ClientSession() as session:
            tokens = await _idk_login(session, brand, email, password, mfa)
            print(
                f"│  ✓ id_token obtained ({len(tokens.id_token)} chars)",
                file=sys.stderr,
            )

            # Pick MBB-register brand based on which IDK client was used.
            # vw-mbb (WeConnect-ID native) → register as VW (matches id_token's VW PPID)
            # vw-via-audi → register as Audi (matches id_token's Audi PPID, same-namespace constraint)
            register_brand = "Audi" if brand_choice == "vw-via-audi" else "VW"
            print(
                f"│\n│ STEP 2 — Register MBB client (brand={register_brand}) ─────────────",
                file=sys.stderr,
            )
            x_client_id = await _mbb_register(session, brand=register_brand)
            print(f"│  ✓ X-Client-Id: ...{x_client_id[-12:]} (brand={register_brand})", file=sys.stderr)

            print(
                "│\n│ STEP 3 — Exchange id_token → MBB vwToken ──────────────────",
                file=sys.stderr,
            )
            mbb = await _mbb_exchange(session, tokens.id_token, x_client_id)
            access = mbb.get("access_token", "")
            refresh = mbb.get("refresh_token", "")
            expires = mbb.get("expires_in", 0)
            if not access or not refresh:
                raise RuntimeError(f"MBB response missing tokens: {mbb}")
            print(
                f"│  ✓ MBB vwToken obtained ({len(access)} chars, "
                f"expires_in={expires}s)",
                file=sys.stderr,
            )

            print(
                "│\n│ STEP 4 — Write to mbb.local.bru ───────────────────────────",
                file=sys.stderr,
            )
            path = _write_bruno(tokens.id_token, x_client_id, access, refresh)
            print(f"│  ✓ Updated {path.name}", file=sys.stderr)

            print(
                "└─ SUCCESS ──────────────────────────────────────────────────────"
                "\n\n MBB-Auth komplett. mbb.local.bru hat jetzt:"
                "\n   - idk_id_token (Audi-IDK, 1h gültig)"
                "\n   - x_client_id  (frisch registriert, 1y gültig)"
                "\n   - vw_access_token  (MBB vwToken, 1h gültig)"
                "\n   - vw_refresh_token (MBB refresh, 90d gültig)"
                "\n\nNext: open Bruno → run Stufen 03-18 (use MBB vwToken)."
                "\n01_POST_token_exchange wird auch funktionieren (200) — wir haben"
                "\nes hier programmatisch schon gemacht.",
                file=sys.stderr,
            )
            return 0

    except TwoFactorRequiredError:
        print("✗ 2FA required. Re-run with --mfa <code>", file=sys.stderr)
        return 2
    except TermsAndConditionsError:
        print(
            "✗ VW-Konto hat unakzeptierte Terms&Conditions. "
            "Erst in offizieller App akzeptieren.",
            file=sys.stderr,
        )
        return 3
    except MarketingConsentError:
        print(
            "✗ Marketing-Consent in offizieller App entscheiden, dann nochmal.",
            file=sys.stderr,
        )
        return 4
    except RateLimitError:
        print("✗ Rate-limit (429). 15 Min warten.", file=sys.stderr)
        return 5
    except AuthenticationError as exc:
        print(f"✗ IDK-Auth fehlgeschlagen: {exc}", file=sys.stderr)
        return 6
    except RuntimeError as exc:
        print(f"\n└─ FAILURE ──────────────────────────────────────────────────────",
              file=sys.stderr)
        print(f"\n✗ {exc}\n", file=sys.stderr)
        if "MBB token exchange" in str(exc):
            print(
                "DIAGNOSE: id_token ist OK (IDK akzeptiert), Registration ist OK,"
                "\naber MBB lehnt den Exchange ab. Mögliche Gründe:"
                "\n  - Account hat keine Audi-Subscription (id_token-Audience-Filter)"
                "\n  - VIN nicht mit Konto verknüpft auf MBB-Side"
                "\n  - MBB-Backend hat unsere appId/Brand-Combo geblockt"
                "\nNext: paste den HTTP-Body oben hier rein — wir gehen weiter.",
                file=sys.stderr,
            )
        return 7


def main() -> int:
    parser = argparse.ArgumentParser(
        description="End-to-end MBB token helper for pre-Cariad VW (Golf 7 GTE)."
    )
    parser.add_argument("--email", help="VW account email (prompted if omitted).")
    parser.add_argument("--mfa", help="2FA code (only if account has 2FA).")
    parser.add_argument(
        "--brand",
        default="vw-mbb",
        choices=["vw-mbb", "vw-via-audi", "vw-na"],
        help="Which IDK client to use. vw-mbb (DEFAULT, WINNER) = WeConnect-ID + mbb scope = VW namespace token. vw-via-audi = Audi client (Audi namespace, fails CLS). vw-na = NA MyVW (returns Unknown client).",
    )
    args = parser.parse_args()

    email = args.email or input("VW account email: ").strip()
    if not email:
        print("ERROR: email required", file=sys.stderr)
        return 1

    password = (
        getpass.getpass("VW account password: ")
        if sys.stdin.isatty()
        else sys.stdin.readline().rstrip("\n")
    )
    if not password:
        print("ERROR: password required", file=sys.stderr)
        return 1

    return asyncio.run(_run(email, password, args.mfa, brand_choice=args.brand))


if __name__ == "__main__":
    sys.exit(main())
