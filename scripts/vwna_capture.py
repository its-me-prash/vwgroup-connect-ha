#!/usr/bin/env python3
# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
"""VW US/Canada read-shape capture — grounds APK-audit items N5 + N6.

For a US/CA VW tester (e.g. issue #659). Logs in with YOUR myVW account,
then GETs the candidate read endpoints and prints only their SHAPE — field
names, value types, and ENUM_LIKE values — with your VIN, name, and every
free-text value MASKED. The output is safe to paste in a GitHub issue: it
reveals the API structure we need, not your personal data.

What it settles:
  N5 — does /ev/v1/vehicle/{uuid}/climate/summary still return a
       ClimateStatusReport, or 404? And which of charge/summary or the
       user-summary route embeds climateStatusInd?
  N6 — does /rrs/v1/privileges... still return coverage, and what shape does
       /account/v1/coverages expose for subscription.active / expiresAt?
  v2.29.x hidden surface — vehicle health, the dedicated location read, the
       remote-operation activity feed, message center, public charging
       sessions, trips, send-to-car, ToS status, in-car wifi, phone-key
       summary and the capability check. These are endpoints the official app
       calls and we have never seen a response from; each is a candidate for
       data we cannot offer today.

Read-only. Every request is a GET and nothing changes state: no commands, no
purchases, no pairing changes, no accepting terms, no starting a charging
session (see the safety block next to the probes). Password read via a hidden
getpass prompt — never echoed, never stored.

Usage (PowerShell):
    py scripts/vwna_capture.py --vin 3VW... --email you@example.com --country us
    py scripts/vwna_capture.py --country ca --mfa 123456
"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import json
import re
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO))

# Home Assistant is a real dependency here (same as the test suite) — import
# the client directly; the package's __init__ pulls the installed HA classes.
import aiohttp  # noqa: E402
from custom_components.vag_connect.cariad.api.vw_na import VWNAClient  # noqa: E402

_ENUM = re.compile(r"^[A-Z][A-Z0-9_.:+-]{1,34}$")
_VINISH = re.compile(r"^[A-HJ-NPR-Z0-9]{11,17}$")
_JWTISH = re.compile(r"^[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]+$")
_ISO = re.compile(r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}")
_ERRCODE = re.compile(r"\b[A-Z][A-Z0-9_]{2,39}\b")

# v2.29.x — key-name-driven masking. The value-shape rules below (_ENUM, the
# <=3-char passthrough) decide on what a value LOOKS like, and a short all-caps
# personal value looks exactly like an enum: a plate, a city, a first name and a
# dealer code would all print verbatim. That was harmless while this script only
# read ev/rvs telemetry; it is NOT harmless for the message-center, charging
# session, trip and address payloads the hidden-surface pass added. So these key
# families are masked regardless of what their value looks like.
_KEY_ID = (
    "userid", "user_id", "vehicleid", "vehicle_id", "uuid", "customerid",
    "accountid", "deviceid", "pairingid", "sessionid", "tripid",
    "notificationid", "cpoid", "locationid", "walletid", "cartid", "ptpref",
    "correlationid", "requestid", "vin",
)
# Long, unambiguous GPS key fragments (substring match is safe).
_KEY_GPS = (
    "latitude", "longitude", "heading", "altitude", "accuracy", "position",
    "coordinates",
)
# Short GPS keys are matched EXACTLY: "lat" as a substring also hits
# "licensePlate" and "translate", which are not coordinates.
_KEY_GPS_EXACT = ("lat", "lon", "lng", "geo", "coord")
_KEY_SECRET = (
    "token", "auth", "bearer", "secret", "pin", "hash", "signature",
    "password", "credential", "challenge", "roken", "payload",
)
_KEY_PERSONAL = (
    "address", "street", "city", "postalcode", "zip", "name", "firstname",
    "lastname", "nickname", "email", "phone", "licenseplate", "plate",
    "dealername", "operatorname", "subject", "body", "message", "title",
    "description", "text",
)
# Two-letter country codes are a genuinely useful enum and carry no PII.
_KEY_ALLOW = ("country", "countrycode", "locale", "unit", "units")


def _mask_for_key(key: str) -> str | None:
    """Return a fixed placeholder when a KEY name alone makes its value unsafe."""
    k = key.lower().replace("-", "").replace("_", "")
    if any(a in k for a in _KEY_ALLOW):
        return None
    if any(s in k for s in _KEY_SECRET):
        return "<redacted>"
    if any(i == k or k.endswith(i) for i in _KEY_ID):
        return "<id>"
    # Personal before GPS: a plate/address key must not be mislabelled by a
    # short coordinate fragment (both are masked either way, but the label
    # should be honest).
    if any(p in k for p in _KEY_PERSONAL):
        return "<personal>"
    if any(g in k for g in _KEY_GPS) or k in _KEY_GPS_EXACT:
        return "<gps>"
    return None


def _shape(o, depth: int = 0, strict: bool = False):
    """Structure + types + enum values only — free text / VIN / PII masked.

    ``strict=True`` additionally drops the enum and short-string passthroughs, so
    every leaf becomes a type placeholder. Used for payloads that can carry
    arbitrary personal prose (message center, POI/charging locations).
    """
    if depth > 8:
        return "…"
    if isinstance(o, dict):
        out = {}
        for k, v in list(o.items())[:60]:
            forced = _mask_for_key(str(k))
            out[k] = forced if forced is not None else _shape(v, depth + 1, strict)
        return out
    if isinstance(o, list):
        if not o:
            return []
        head = _shape(o[0], depth + 1, strict)
        return [head, f"…(+{len(o) - 1})"] if len(o) > 1 else [head]
    if isinstance(o, bool):
        return o
    if isinstance(o, (int, float)):
        return "<num>"
    if o is None:
        return None
    if isinstance(o, str):
        if _JWTISH.match(o):
            return "<redacted>"
        if _VINISH.match(o):
            return "<VIN>"
        if _ISO.match(o):
            return "<iso8601>"             # "it is a timestamp", not when
        if strict:
            return f"<str:{len(o)}>"
        if _ENUM.match(o):
            return o                       # enum value — safe + the useful bit
        if len(o) <= 3:
            return o
        return f"<str:{len(o)}>"           # free text masked
    return f"<{type(o).__name__}>"


def _safe_error_line(exc: Exception) -> str:
    """Status plus error CODES only — never free-form body text.

    v2.29.x: this used to print ``str(exc.body)[:120]`` raw, and a con-veh error
    body can carry the VIN, the vehicle UUID or the userId. The status code is
    the diagnostic value; the body prose is pure risk. We shape a JSON body
    through the same masker and, for a non-JSON body, emit only its length plus
    any SCREAMING_CASE error codes (USER_NOT_AUTHORIZED, METHOD_NOT_ALLOWED …).
    """
    status = getattr(exc, "status", None)
    raw = str(getattr(exc, "body", "") or "")
    if not raw:
        return f"status={status}"
    try:
        shaped = _shape(json.loads(raw))
        return f"status={status} body={json.dumps(shaped, ensure_ascii=False)[:300]}"
    except Exception:  # noqa: BLE001
        # A VIN is all-caps alphanumeric and matches an error-code pattern, so
        # require an underscore (USER_NOT_AUTHORIZED, METHOD_NOT_ALLOWED …) and
        # reject anything VIN-shaped outright.
        codes = sorted({
            c for c in _ERRCODE.findall(raw)
            if "_" in c and not _VINISH.match(c)
        })[:6]
        return f"status={status} len={len(raw)} codes={codes}"


async def _probe(client: VWNAClient, label: str, url: str,
                 carnet_token: str | None, use_read: bool,
                 strict: bool = False) -> None:
    try:
        if use_read:
            data = await client._read(url, carnet_token)
        else:
            data = await client._get(url)
        print(f"\n  === {label} → OK ===")
        shaped = json.dumps(_shape(data, strict=strict), indent=2, ensure_ascii=False)
        print("  " + shaped[:2400].replace("\n", "\n  "))
    except Exception as exc:  # noqa: BLE001
        # An APIError carries .status; show it so a 404 (dead) vs 403/200 is clear.
        print(f"\n  === {label} → {type(exc).__name__} "
              f"{_safe_error_line(exc)} ===")


async def _run(email: str, password: str, mfa: str | None, vin: str,
               country: str, probe_health: bool = False) -> int:
    vin = vin.strip().upper()
    print("\n" + "=" * 68)
    print(f"  VW-NA read-shape capture — VIN ...{vin[-6:]}  country={country}")
    print("=" * 68)
    async with aiohttp.ClientSession() as session:
        client = VWNAClient(session, email, password, country=country)
        print("\n[1/4] login …")
        try:
            await client.authenticate(mfa_code=mfa)
        except Exception as exc:  # noqa: BLE001
            print(f"  ✗ login failed: {type(exc).__name__}: {str(exc)[:180]}")
            return 6
        print("  ✓ authenticated")

        print("[2/4] garage discovery (VIN → uuid, user_id) …")
        try:
            vins = await client.get_vehicles()
        except Exception as exc:  # noqa: BLE001
            print(f"  ✗ garage failed: {type(exc).__name__}: {str(exc)[:150]}")
            return 7
        uuid = client._vin_to_uuid.get(vin, vin)
        uid = client._user_id or ""
        print(f"  ✓ {len(vins)} vehicle(s); uuid resolved={uuid != vin}; user_id set={bool(uid)}")

        print("[3/4] read-session token …")
        try:
            carnet = await client._get_read_session_token(vin)
        except Exception as exc:  # noqa: BLE001
            carnet = None
            print(f"  (session-token step: {type(exc).__name__} — continuing)")
        print(f"  carnet_token acquired={bool(carnet)}")

        print("[4/4] candidate read shapes (masked):")
        B = client._base
        # N5 candidates (ev/rvs data — use the carnet-authorised read path)
        await _probe(client, "N5 climate/summary",
                     f"{B}/ev/v1/vehicle/{uuid}/climate/summary", carnet, True)
        await _probe(client, "N5 charge/summary",
                     f"{B}/ev/v1/vehicle/{uuid}/charge/summary", carnet, True)
        await _probe(client, "N5 user/.../summary",
                     f"{B}/ev/v1/user/{uid}/vehicle/{uuid}/summary", carnet, True)
        await _probe(client, "rvs status",
                     f"{B}/rvs/v1/vehicle/{uuid}", carnet, True)
        # N6 candidates (subscription/coverage — plain account auth)
        # v2.29.x — the coverages/VWCare URLs were TRUNCATED (bare
        # /account/v1/coverages and /account/v1/VWCare), so they could only ever
        # 404 and the N6 question this script exists to answer stayed
        # unanswerable. The path templates below are verbatim from the current
        # myVW app (androguard sweep of com.vw.carnet.release 2026.7.28-9380).
        await _probe(client, "N6 rrs privileges",
                     f"{B}/rrs/v1/privileges/user/{uid}/vehicle/{uuid}", None, False)
        await _probe(client, "N6 account/coverages",
                     f"{B}/account/v1/coverages/vehicle/{uuid}", None, False)
        await _probe(client, "N6 account/VWCare",
                     f"{B}/account/v1/VWCare/user/{uid}/vehicle/{uuid}/summary",
                     None, False)

        # ── v2.29.x — hidden-surface probes ──────────────────────────────────
        # Path templates verbatim from the current myVW app (androguard sweep of
        # com.vw.carnet.release 2026.7.28-9380). These are endpoints the official
        # app calls that we have NEVER seen a response from; each one is a
        # candidate for data we cannot offer today (vehicle health, charging
        # sessions, notifications, trips).
        #
        # SAFETY — every probe below is a plain GET and nothing here changes
        # state. Deliberately NOT probed, and they must never be added:
        #   * /account/v2/enrollment/toses (POST)  — POSTing would accept a legal
        #     agreement on the owner's behalf. The GET status read below is fine.
        #   * /estore/*                            — carts, payment, wallets.
        #   * /pair/*, /mdk/*/pairing/password|reset — revokes the owner's phone
        #     key / vehicle pairing.
        #   * /cds/wifi/*/reset                    — rotates the hotspot creds.
        #   * /device/v1/*/analytic, /devicestatistics/* — sends telemetry TO VW.
        #   * /poi/*/session/start|stop            — starts/stops a PAID public
        #     charging session on the owner's account.
        # A 405 here is a useful answer too: it tells us the verb, exactly how
        # the flash 405 told us honkflash wants PUT.
        print("\n[5/5] hidden-surface probes (masked, read-only):")

        # Vehicle health. NOTE: the app inventory only exposes a /refresh
        # TRIGGER for this service and no health READ path, so we probe the
        # trigger (expect 405/404 if it is POST-only) and diff the normal status
        # read around it rather than assuming a read exists.
        # OPT-IN: a refresh trigger wakes the car and spends modem budget. It is
        # not destructive (changes no setting, sends VW nothing about us), but it
        # is a mutation, so it stays behind --probe-health and runs at most once.
        if probe_health:
            await _probe(client, "health listener (trigger; verb probe)",
                         f"{B}/vehiclehealthlistener/v2/vehicle/{uuid}/refresh",
                         carnet, True)
            await _probe(client, "rvs status (post-health diff)",
                         f"{B}/rvs/v1/vehicle/{uuid}", carnet, True)
        else:
            print("\n  === health listener → SKIPPED (pass --probe-health to "
                  "wake the car once and diff the status read) ===")

        # Dedicated location read (we only parse GPS out of the rvs aggregate).
        await _probe(client, "location (dedicated)",
                     f"{B}/rvs/v1/location/vehicle/{uuid}", carnet, True, strict=True)

        # Remote-operation activity feed (sibling of the correlationId history
        # we already use for command confirmation).
        await _probe(client, "activity feed",
                     f"{B}/history/activity/v1/vehicle/{uuid}", carnet, True, strict=True)

        # Message center. Bodies may contain personal text — _shape() masks all
        # free-text values, only field names/types/enums are printed.
        await _probe(client, "messagecenter unread count",
                     f"{B}/messagecenter/v2/user/{uid}/vehicle/{uuid}/unRead/count",
                     carnet, True)
        await _probe(client, "messagecenter inbox",
                     f"{B}/messagecenter/v2/user/{uid}/vehicle/{uuid}", carnet, True, strict=True)
        await _probe(client, "messagecenter categories",
                     f"{B}/messagecenter/v2/user/{uid}/vehicle/{uuid}/categories",
                     carnet, True)

        # Public charging sessions (history + any session in flight).
        await _probe(client, "charging sessions (history)",
                     f"{B}/poi/v1/history/vehicle/{uuid}/user/{uid}/sessions",
                     carnet, True, strict=True)
        await _probe(client, "charging session (active)",
                     f"{B}/poi/v1/vehicle/{uuid}/user/{uid}/session/active",
                     carnet, True, strict=True)

        # Trips. Likely planned NAV routes rather than driven trips — the probe
        # settles which, so we don't promise a trip sensor we cannot build.
        await _probe(client, "trip v1", f"{B}/poi/v1/vehicle/{uuid}/trip",
                     carnet, True, strict=True)
        await _probe(client, "trip v2", f"{B}/poi/v2/vehicle/{uuid}/trip",
                     carnet, True, strict=True)

        # Send-to-car destination resource (GET only; we never POST a
        # destination from a capture run).
        await _probe(client, "destination (send-to-car resource)",
                     f"{B}/poi/v1/vehicle/{uuid}/destination", carnet, True, strict=True)

        # Terms-of-service enrolment STATUS. GET ONLY — see the safety note.
        await _probe(client, "enrollment toses (STATUS GET only)",
                     f"{B}/account/v2/enrollment/toses/user/{uid}/vehicle/{uuid}",
                     None, False)

        # In-car wifi hotspot state (status only, never /reset).
        await _probe(client, "wifi connection status",
                     f"{B}/cds/wifi/v1/wifiConnection/vehicle/{uuid}/status",
                     carnet, True)

        # Mobile-device-key summary (read only, never pairing/password|reset).
        # Also tells us whether this account has a paired phone key at all.
        await _probe(client, "mdk summary",
                     f"{B}/mdk/v1/vehicle/{uuid}/summary", carnet, True, strict=True)

        # Capability check. Its siblings (resolveAmbiguity / searchDatastore /
        # provideFeedback) suggest a VOICE-assistant service rather than an
        # entitlement source; this probe settles it before we would ever gate a
        # button on it.
        await _probe(client, "vas checkCapability",
                     f"{B}/vas/v1/checkCapability/vehicle/{uuid}", carnet, True)

    print("\n" + "-" * 68)
    print("Paste the whole [4/4] AND [5/5] blocks. They're masked (VIN/text hidden, only field")
    print("names + types + enum values shown). We ground N5/N6 from it.")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description="VW US/CA read-shape capture (N5/N6).")
    p.add_argument("--vin", help="Vehicle VIN (prompted if omitted).")
    p.add_argument("--email", help="myVW account email (prompted if omitted).")
    p.add_argument("--country", default="us", choices=["us", "ca"], help="us or ca.")
    p.add_argument("--mfa", help="2FA code, if your account has it.")
    p.add_argument(
        "--probe-health", action="store_true",
        help="Also trigger the vehicle-health refresh once and diff the status "
             "read around it. This WAKES the car and spends a little modem "
             "budget; it changes no setting and sends VW nothing about you. "
             "Off by default.",
    )
    args = p.parse_args()
    email = args.email or input("myVW email: ").strip()
    vin = args.vin or input("VIN: ").strip()
    if not email or not vin:
        print("ERROR: email and VIN required", file=sys.stderr)
        return 1
    password = (getpass.getpass("myVW password (hidden): ")
                if sys.stdin.isatty() else sys.stdin.readline().rstrip("\n"))
    if not password:
        print("ERROR: password required", file=sys.stderr)
        return 1
    return asyncio.run(_run(email, password, args.mfa, vin, args.country,
                            args.probe_health))


if __name__ == "__main__":
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
        except Exception:  # noqa: BLE001
            pass
    raise SystemExit(main())
