#!/usr/bin/env python3
# Copyright 2026 Prash Balan (@its-me-prash) — Apache License 2.0
"""Interactive IDK token helper for Bruno testing.

Runs the SAME IDK OAuth flow that the vag_connect HA integration uses.
Prints the id_token (plus access/refresh) so you can paste it into the
mbb_legacy Bruno collection's mbb.local.bru environment.

USAGE
    python scripts/get_idk_token.py
    python scripts/get_idk_token.py --brand audi
    python scripts/get_idk_token.py --brand vw --email me@example.com
    python scripts/get_idk_token.py --silent          # only id_token to stdout

PASSWORD
    Always prompted via getpass — never echoed, never stored on disk.
    Pipe-safe: "echo 'pw' | python scripts/get_idk_token.py" works for CI.

WHY NOT JUST USE BRUNO?
    The IDK flow does PKCE + Auth0 Universal Login + 15 redirect hops +
    optional MFA + HTML state parsing. That's 200 LOC of battle-tested
    Python in cariad/auth/idk.py. Replicating it in Bruno pre-request
    scripts would be fragile and break on every Auth0 template change.
    This helper IS the integration code — kein Drift möglich.
"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import importlib.util
import sys
import types
from pathlib import Path

# Make sibling 'custom_components' importable
_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO))

# Stub homeassistant so HA-dependent siblings don't break our auth-only import.
# We load idk.py / models.py / exceptions.py via spec_from_file_location below
# WITHOUT triggering custom_components.vag_connect.__init__ (which imports HA).
_ha_stub = types.ModuleType("homeassistant")
sys.modules.setdefault("homeassistant", _ha_stub)
for sub in ("config_entries", "core", "helpers", "const", "exceptions", "util"):
    sys.modules.setdefault(f"homeassistant.{sub}", types.ModuleType(f"homeassistant.{sub}"))


def _load_pkg_module(pkg_path: str, file_path: Path) -> types.ModuleType:
    """Load a module file under a virtual package path so relative imports work."""
    spec = importlib.util.spec_from_file_location(pkg_path, file_path)
    if not spec or not spec.loader:
        raise RuntimeError(f"Cannot load {pkg_path} from {file_path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[pkg_path] = mod
    spec.loader.exec_module(mod)
    return mod


# Build the minimal package tree: cariad → cariad.exceptions, cariad.models, cariad.auth.idk
_CARIAD_DIR = _REPO / "custom_components" / "vag_connect" / "cariad"

# Empty parent packages so relative imports resolve
sys.modules["cariad_auth_only"] = types.ModuleType("cariad_auth_only")
sys.modules["cariad_auth_only"].__path__ = [str(_CARIAD_DIR)]
sys.modules["cariad_auth_only.auth"] = types.ModuleType("cariad_auth_only.auth")
sys.modules["cariad_auth_only.auth"].__path__ = [str(_CARIAD_DIR / "auth")]

# Load in dependency order: exceptions → models → idk
_exc = _load_pkg_module("cariad_auth_only.exceptions", _CARIAD_DIR / "exceptions.py")
_models = _load_pkg_module("cariad_auth_only.models", _CARIAD_DIR / "models.py")
_idk = _load_pkg_module("cariad_auth_only.auth.idk", _CARIAD_DIR / "auth" / "idk.py")

import aiohttp  # noqa: E402

IDKAuth = _idk.IDKAuth
AuthenticationError = _exc.AuthenticationError
MarketingConsentError = _exc.MarketingConsentError
RateLimitError = _exc.RateLimitError
TermsAndConditionsError = _exc.TermsAndConditionsError
TwoFactorRequiredError = _exc.TwoFactorRequiredError
BRAND_VW_EU = _models.BRAND_VW_EU
BRAND_AUDI = _models.BRAND_AUDI
BRAND_SKODA = _models.BRAND_SKODA
BRAND_SEAT = _models.BRAND_SEAT
BRAND_CUPRA = _models.BRAND_CUPRA


# MBB-compatible VW config — uses AUDI's IDK OAuth client. Why:
#   - Modern VW WeConnect ID client (a24fba63-...) does NOT support `mbb`
#     scope; resulting id_token lacks MBB audience claims → MBB rejects.
#   - Legacy VW Car-Net client (9496332b-...) was deprecated from IDK Auth0
#     in 2025/early 2026; HTTP 400 on /authorize.
#   - Audi's IDK client (09b6cbec-...) IS configured for `mbb` scope and
#     remains active — confirmed via upstream v1.19.1 (2026-03-01).
#   - Same VW Group account works in both apps; the resulting id_token has
#     Audi audience but the user.subject is the same. MBB should accept.
#   - We register MBB client with `client_brand: "VW"` and `appName: "Volkswagen"`
#     so the X-Client-Id is bound to VW-side authorization at MBB, regardless
#     of which IDK app issued the id_token. (upstream proves audience-
#     vs-X-Client-Id mismatch is fine: their id_token is Audi-audience but
#     they register with brand=Audi → all good. Untested for VW-via-Audi but
#     this is the only known working combination given available clients.)
BRAND_VW_MBB_LEGACY = _models.BrandConfig(
    name="vw-mbb",
    client_id="09b6cbec-cd19-4589-82fd-363dfa8c24da@apps_vw-dilab_com",
    redirect_uri="myaudi:///",
    user_agent="Android/4.31.0 (Build 800341641.root project 'myaudi_android'.ext.buildTime) Android/13",
    api_base="https://msg.volkswagen.de",
    # Audi-style scope INCLUDING mbb — that's the magic. Without `mbb` in
    # scope the issued id_token doesn't carry MBB authorization claims.
    scope=(
        "address profile badge birthdate birthplace nationalIdentifier "
        "nationality profession email vin phone nickname name picture mbb "
        "gallery openid"
    ),
)

_BRANDS = {
    "vw": BRAND_VW_EU,
    "volkswagen": BRAND_VW_EU,
    "vw-mbb": BRAND_VW_MBB_LEGACY,
    "vw-legacy": BRAND_VW_MBB_LEGACY,
    "audi": BRAND_AUDI,
    "skoda": BRAND_SKODA,
    "seat": BRAND_SEAT,
    "cupra": BRAND_CUPRA,
}


async def _run(brand_key: str, email: str, password: str, mfa: str | None) -> int:
    brand = _BRANDS[brand_key]
    # mbb_mode (hybrid flow) was tried first but produced id_tokens that MBB
    # also rejected — turns out the issue is SCOPE: the id_token must be
    # issued with `mbb` scope claim, which only Audi's IDK client supports
    # in 2026 (VW's WeConnect ID client and legacy Car-Net don't).
    # vw-mbb now uses Audi's IDK client + Audi's mbb-including scope =
    # standard code-flow yields an MBB-acceptable id_token.
    mbb_mode = False  # Hybrid flow not needed; code flow with mbb scope works.
    async with aiohttp.ClientSession() as session:
        auth = IDKAuth(session, brand)
        try:
            tokens = await auth.authenticate(
                email, password, mfa_code=mfa, mbb_mode=mbb_mode
            )
        except TwoFactorRequiredError:
            print("\nERROR: 2FA required. Re-run with --mfa <code>", file=sys.stderr)
            return 2
        except TermsAndConditionsError:
            print(
                "\nERROR: VW account hat unakzeptierte Terms&Conditions. "
                "Erst in der offiziellen App akzeptieren, dann nochmal.",
                file=sys.stderr,
            )
            return 3
        except MarketingConsentError:
            print(
                "\nERROR: VW account braucht Marketing-Consent-Entscheidung. "
                "Erst in der offiziellen App entscheiden, dann nochmal.",
                file=sys.stderr,
            )
            return 4
        except RateLimitError:
            print(
                "\nERROR: Rate-limit getroffen (429). 15 Min warten, "
                "nicht hochfrequent retry'n — sonst Account-Lockout.",
                file=sys.stderr,
            )
            return 5
        except AuthenticationError as exc:
            print(f"\nERROR: Auth fehlgeschlagen: {exc}", file=sys.stderr)
            return 6

    # In MBB-mode, IDKAuth already returns the hybrid-flow id_token (from the
    # authorize-redirect fragment) in tokens.id_token, with empty access/refresh
    # — those come from the MBB exchange (Bruno Stufe 1) which uses this token.
    if mbb_mode and tokens.id_token:
        print(
            f"→ MBB hybrid id_token captured ({len(tokens.id_token)} chars). "
            f"access/refresh are MBB-side and come from Bruno 01_token_exchange.",
            file=sys.stderr,
        )

    return tokens.id_token, tokens.access_token, tokens.refresh_token


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Interactive IDK token helper for Bruno testing.",
    )
    parser.add_argument(
        "--brand",
        default="vw",
        choices=list(_BRANDS.keys()),
        help="Brand (default: vw). Use 'audi' for Audi, 'skoda' for Skoda, etc.",
    )
    parser.add_argument(
        "--email",
        help="VW account email. If omitted, prompted interactively.",
    )
    parser.add_argument(
        "--mfa",
        default=None,
        help="2FA code (only if account has 2FA enabled).",
    )
    parser.add_argument(
        "--silent",
        action="store_true",
        help="Only print id_token to stdout (for piping into other tools).",
    )
    parser.add_argument(
        "--bruno",
        action="store_true",
        help="Print copy-paste-ready Bruno mbb.local.bru env block.",
    )
    parser.add_argument(
        "--write-bruno",
        action="store_true",
        help=(
            "Write tokens directly into tests/bruno/mbb_legacy/environments/"
            "mbb.local.bru (creates from template if missing). Skips terminal "
            "output to keep tokens off your screen."
        ),
    )
    args = parser.parse_args()

    email = args.email or input("VW account email: ").strip()
    if not email:
        print("ERROR: email required", file=sys.stderr)
        return 1

    # getpass — niemals echoen, niemals stored
    if sys.stdin.isatty():
        password = getpass.getpass("VW account password: ")
    else:
        # Pipe-mode (echo 'pw' | python ...)
        password = sys.stdin.readline().rstrip("\n")

    if not password:
        print("ERROR: password required", file=sys.stderr)
        return 1

    if not args.silent:
        print(
            f"\n→ Authenticating against IDK as {email[:3]}***@*** "
            f"(brand={args.brand}) ...",
            file=sys.stderr,
        )

    result = asyncio.run(_run(args.brand, email, password, args.mfa))
    if isinstance(result, int):
        return result
    id_tok, access_tok, refresh_tok = result

    if args.silent:
        # Pipe-friendly: just the id_token, nothing else
        print(id_tok)
        return 0

    if args.write_bruno:
        # Write directly into mbb.local.bru — token never appears on screen
        local_path = (
            _REPO / "tests" / "bruno" / "mbb_legacy" / "environments" / "mbb.local.bru"
        )
        template_path = local_path.with_name("mbb.template.bru")
        if not local_path.exists():
            if not template_path.exists():
                print(
                    f"ERROR: neither {local_path} nor template found.",
                    file=sys.stderr,
                )
                return 7
            local_path.write_text(template_path.read_text(encoding="utf-8"), encoding="utf-8")
            print(f"→ Created {local_path.name} from template.", file=sys.stderr)

        content = local_path.read_text(encoding="utf-8")
        # Replace each token line; supports both the placeholder values
        # ("PASTE_..._HERE", "WILL_BE_FILLED_AFTER_...") and any prior real value.
        import re as _re  # noqa: PLC0415

        def _sub(field: str, value: str, text: str) -> str:
            pattern = rf"^(\s*{_re.escape(field)}:\s*).*$"
            return _re.sub(pattern, lambda m: f"{m.group(1)}{value}", text, flags=_re.MULTILINE)

        content = _sub("idk_id_token", id_tok, content)
        # Only update access/refresh if non-empty. In MBB hybrid-flow mode they
        # are empty and come later from Bruno Stufe 1 (MBB token exchange).
        if access_tok:
            content = _sub("vw_access_token", access_tok, content)
        if refresh_tok:
            content = _sub("vw_refresh_token", refresh_tok, content)
        local_path.write_text(content, encoding="utf-8")

        n_written = 1 + bool(access_tok) + bool(refresh_tok)
        print(
            f"\n✓ Wrote {n_written} token{'s' if n_written != 1 else ''} into {local_path.name}",
            file=sys.stderr,
        )
        if not access_tok:
            print(
                "  → idk_id_token only (MBB hybrid mode — vw_access_token "
                "/ vw_refresh_token come from Bruno 01_POST_token_exchange)",
                file=sys.stderr,
            )
        else:
            print(
                "  → idk_id_token, vw_access_token, vw_refresh_token updated",
                file=sys.stderr,
            )
        print(
            f"\n→ Next: open Bruno, select environment 'mbb.local', run "
            f"'01_POST_token_exchange.bru'",
            file=sys.stderr,
        )
        print(
            "\nReminder: id_token expires in ~1h. Re-run this command for fresh tokens.",
            file=sys.stderr,
        )
        return 0

    if args.bruno:
        # Copy-paste block for mbb.local.bru
        print("\n" + "=" * 60, file=sys.stderr)
        print("BRUNO mbb.local.bru — copy/paste these lines:", file=sys.stderr)
        print("=" * 60, file=sys.stderr)
        print(f"  idk_id_token: {id_tok}")
        print(f"  vw_access_token: {access_tok}")
        print(f"  vw_refresh_token: {refresh_tok}")
        return 0

    # Default: human-readable output
    print("\n" + "=" * 60)
    print("SUCCESS — Tokens received")
    print("=" * 60)
    print(f"\nid_token (für mbb.local.bru → idk_id_token):")
    print(f"\n{id_tok}\n")
    print(f"access_token (CARIAD-side, NICHT MBB):")
    print(f"\n{access_tok[:60]}...{access_tok[-20:]}\n")
    print(f"refresh_token (CARIAD-side, gilt 90 Tage):")
    print(f"\n{refresh_tok[:60]}...{refresh_tok[-20:]}\n")
    print("=" * 60)
    print("\nNext: paste id_token into Bruno mbb.local.bru → idk_id_token,")
    print("dann Stufe 1 (01_POST_token_exchange) ausführen.")
    print("\nid_token läuft nach ~1h ab — wenn 401 in Bruno: Helper neu laufen lassen.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
