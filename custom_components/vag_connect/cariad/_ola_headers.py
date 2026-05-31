# Copyright 2026 Prash Balan (@its-me-prash) — Apache License 2.0
"""OLA (Online Living Application) authentication header constants.

VW Group's OLA backend (``ola.prod.code.seat.cloud.vwgroup.com``) —
which serves both SEAT and CUPRA — started enforcing app-identifying
headers on **2026-05-20**. Without these headers, every request returns
HTTP 403 Forbidden regardless of token validity, blocking all SEAT +
CUPRA setup and operation entirely (see issues #281 goncal, #282
matthias0304/smartmatic, and parallel discoveries in PyCupra #89 and
CarConnectivity-connector-seatcupra #112 / PR #113).

This module is the **single source of truth** for the OLA-specific
HTTP headers. Bumping versions is a 1-line change here.

## Defense-in-depth architecture (v2.4.1+)

1. **This module** — centralized constants per brand.
2. **OptionsFlow override** — power-users can patch
   ``app_version_override`` + ``user_agent_override`` live without
   waiting for releases (see ``const.py`` + ``config_flow.py`` for
   the config keys).
3. **Multi-version fallback chain** — if a request returns 403, the
   client retries with the N-1 version (the previous-major value
   stored in ``_OLA_HEADERS_BY_BRAND_FALLBACK``), then N-2, then
   surfaces the failure.
4. **Repair-issue on persistent 403** — after all fallbacks exhaust,
   ``cariad/api/seat_cupra.py`` raises an HA Repair issue prompting
   the user to check for an integration update.

Plus: ``.github/workflows/upstream-ola-watcher.yml`` runs weekly and
opens a GitHub Issue on this repo whenever the upstream
CarConnectivity-connector-seatcupra constants diverge from these.

## Sustainability note

The community has flagged that VW may eventually require **signed app-
attestation tokens** (Play Integrity / App Attest) instead of mere
header values. If/when that happens, this header-based workaround
breaks regardless of version. At that point the integration would
need to support some form of token-relay or pivot to a different
backend (mitch-dc / volkswagencarnet patterns). For now (2026-05),
header-based identification is sufficient.

## Why per-brand

CarConnectivity's ``my_cupra_session.py`` uses different ``app-brand``
+ ``app-version`` + ``user-agent`` values for SEAT vs. CUPRA. We
mirror that — the OLA backend appears to enforce **brand-app
consistency** (i.e. don't claim to be the CUPRA app while requesting
a SEAT vehicle).
"""

from __future__ import annotations

# v2.4.1 (2026-05-25) — latest known-good values mirroring CarConnectivity
# v0.6.3's ``my_cupra_session.py``. Source of truth for upstream-watcher
# CI diff: https://github.com/upstream/cc-connector-
# seatcupra/blob/main/src/carconnectivity_connectors/seatcupra/auth/
# my_cupra_session.py
_OLA_HEADERS_BY_BRAND: dict[str, dict[str, str]] = {
    "seat": {
        "app-market": "android",
        "app-brand": "seat",
        "app-version": "2.17.0",
        "origin": "app",
    },
    "cupra": {
        "app-market": "android",
        "app-brand": "cupra",
        "app-version": "2.15.0",
        "origin": "app",
    },
}

# v2.4.1 — fallback chain for the multi-version retry layer. Ordered
# newest-first. When a request 403s with the primary version, the
# client retries with the next entry. Stop at empty list = surface 403
# as fatal + raise HA Repair issue.
#
# Bump strategy: when we update _OLA_HEADERS_BY_BRAND with a new
# version (say, SEAT 2.18.0 ships from upstream watcher), MOVE the
# current value (2.17.0) into position [0] of the fallback chain.
# Keep last 2-3 fallbacks; older than that is dead weight.
_OLA_HEADERS_BY_BRAND_FALLBACK: dict[str, list[dict[str, str]]] = {
    "seat": [
        # Older app-version known to have worked before 2026-05-20
        # enforcement (we never had to specify these before).
        # No fallbacks yet — primary is the first known-good.
    ],
    "cupra": [
        # Same — pre-2026-05-20 no fallbacks existed; primary is
        # first known-good after enforcement started.
    ],
}

# v2.4.1 — user-agent override per brand. CarConnectivity's session
# also sets brand-specific User-Agent strings. The base client
# defaults to BrandConfig.user_agent; OLA-specific override below
# wins for ola.prod.code.seat.cloud.vwgroup.com requests.
_OLA_USER_AGENT_BY_BRAND: dict[str, str] = {
    "seat":  "SEATApp/2.5.0 (com.seat.myseat.ola; build:202410171614; iOS 15.8.3) Alamofire/5.7.0 Mobile",
    "cupra": "CUPRAApp%20-%20Store/20220503 CFNetwork/1333.0.4 Darwin/21.5.0",
}


def get_ola_headers(
    brand: str,
    fallback_index: int = -1,
    app_version_override: str | None = None,
    user_agent_override: str | None = None,
) -> dict[str, str]:
    """Return the OLA HTTP headers for the given brand.

    Args:
        brand: ``"seat"`` or ``"cupra"`` (case-insensitive). Other
            values return an empty dict (no-op).
        fallback_index: ``-1`` = primary (default); ``0`` = first
            fallback; ``1`` = second; etc. Index out of range returns
            an empty dict (caller should surface failure).
        app_version_override: if non-empty, replaces ``app-version``
            in the result. Used by the OptionsFlow advanced setting.
        user_agent_override: if non-empty, included as ``User-Agent``
            in the result. Used by the OptionsFlow advanced setting.

    Returns:
        A new dict (safe to mutate by caller). Empty dict if the brand
        is unknown or fallback_index is out of range.
    """
    brand_norm = brand.lower().strip() if isinstance(brand, str) else ""
    if brand_norm not in _OLA_HEADERS_BY_BRAND:
        return {}

    if fallback_index < 0:
        headers = dict(_OLA_HEADERS_BY_BRAND[brand_norm])
    else:
        chain = _OLA_HEADERS_BY_BRAND_FALLBACK.get(brand_norm, [])
        if fallback_index >= len(chain):
            return {}
        headers = dict(chain[fallback_index])

    if app_version_override:
        headers["app-version"] = app_version_override

    ua = user_agent_override or _OLA_USER_AGENT_BY_BRAND.get(brand_norm)
    if ua:
        headers["User-Agent"] = ua

    return headers


def get_fallback_count(brand: str) -> int:
    """Return the number of fallback header-sets available for ``brand``.

    Used by the retry loop to know when to stop iterating and surface
    a fatal 403.
    """
    brand_norm = brand.lower().strip() if isinstance(brand, str) else ""
    return len(_OLA_HEADERS_BY_BRAND_FALLBACK.get(brand_norm, []))
