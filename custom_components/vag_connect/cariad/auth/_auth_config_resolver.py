# Copyright 2026 Prash Balan (@its-me-prash) — Apache License 2.0
"""v2.5.6 — APK-primary, competitor-fallback auth config resolver.

v2.5.11 — added Audi market-config layer (between OIDC discovery and
APK cache) replicating audi_connect_ha's PR #736 dynamic-URL pattern.
See ``_audi_market_config.py`` for full rationale.

The 2026-05-28 VW Azure WAF migration ([#313](https://github.com/its-me-prash/vwgroup-connect-ha/issues/313))
exposed a fragility in our auth path: hardcoded constants for token URL,
OAuth client_id, and the qmauth HMAC secret meant a single VW backend
rotation broke 100% of Audi + VW EU users for ~6 h.

This module flips the priority: **values mined from the official APK take
precedence**; the hardcoded values from cross-source-verified competitor
ports (evcc, audi_connect_ha, volkswagencarnet, ioBroker.vw-connect)
become the resilience fallback.

Why APK-primary?
- The APK on APKMirror/APKCombo IS what the official app ships today.
- Competitors can drift — they update reactively when their users hit
  the next rotation. The APK is **proactive** truth.
- Our daily atlas already mines APK content; we just need to consume
  what we mine.

Why keep competitor-derived fallback?
- APK extraction can fail (Cloudflare, missing apktool, malformed JSON).
- A previously-working hardcoded value is strictly better than no value.
- Multi-source cross-verification (3+ projects agreeing on a value) is
  high-confidence even when APK is unavailable.

Architecture:
  ┌─ APK cache (.app-atlas-apk-cache/{brand}.json:auth_secrets) ───┐ ← PRIMARY
  ├─ Module-level hardcoded constants in idk.py ───────────────────┤ ← FALLBACK
  └─ Per-brand alternate UUID list (this module) ──────────────────┘ ← EXTRA candidates
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

_LOGGER = logging.getLogger(__name__)


# ── Per-brand alternate OAuth client_id candidates ──────────────────────────
# Captured from the 2026-05-27 APK retro-mining
# (see ``_private/auth-shield-retro-findings.md``). These are additional
# UUID@apps_vw-dilab_com values present in the official APK alongside our
# known-good client_id — could be region-specific, feature-specific, or
# fallback IDs that the app rotates through.
#
# v2.5.6 uses them as **fallback candidates** in the token-exchange chain:
# if our primary client_id returns 401/403, the integration retries with
# each of these in order before giving up. Reduces the failure surface
# when VW silently makes a UUID preferred over the legacy one.
_ALTERNATE_CLIENT_IDS: dict[str, tuple[str, ...]] = {
    "audi": (
        # Primary (hardcoded in BRAND_AUDI.client_id):
        #   09b6cbec-cd19-4589-82fd-363dfa8c24da@apps_vw-dilab_com
        # Discovered in classes9.dex + classes10.dex of myAudi 5.4.1.
        # Purpose unknown — possibly Audi internal-test or per-region fallback.
        "16dd7960-431d-4b88-b3a5-35724b2fce01@apps_vw-dilab_com",
        # v2.5.11 — evcc-derived alternate. Spotted in evcc's
        # ``vehicle/audi/`` and ``vehicle/vag/`` packages post-2026-05-28
        # (PR #30292 / commit history). NOT in audi_connect_ha's tree —
        # so this is a separately-discovered candidate from a different
        # competitor's reverse-engineering. Worth trying as fallback if
        # the canonical Audi UUID starts 401/403'ing.
        "f4d0934f-32bf-4ce4-b3c4-699a7049ad26@apps_vw-dilab_com",
    ),
    "volkswagen": (
        # Discovered in classes3.dex of WeConnect ID 3.61.0 (post-WAF prep version).
        # Both are NOT our current hardcoded client_id — worth trying as
        # candidates if the primary one starts 401/403'ing.
        "4edc53db-4b79-4e37-b614-19a95dea20dc@apps_vw-dilab_com",
        "a24fba63-34b3-4d43-b181-942111e6bda8@apps_vw-dilab_com",
    ),
}


# Cache root resolved relative to repo root. Daily atlas writes JSON here;
# this module reads from it. None when cache root is unavailable (e.g.
# unit-test contexts) — resolver gracefully degrades to fallback-only mode.
def _resolve_cache_root() -> Path | None:
    """Walk up from this file to find `.app-atlas-apk-cache/`."""
    here = Path(__file__).resolve()
    for parent in (here.parent, *here.parents):
        candidate = parent / ".app-atlas-apk-cache"
        if candidate.is_dir():
            return candidate
    return None


_APK_CACHE_ROOT: Path | None = _resolve_cache_root()


# ── OIDC Discovery cache (v2.5.7 R3) ────────────────────────────────────────
# Stores ``{brand: (token_endpoint, fetched_at_monotonic)}`` so we don't
# hammer the openid-configuration endpoint on every token exchange. TTL
# matches the typical 1-hour token lifetime — long enough that auth
# flows during the same session reuse the same discovered URL, short
# enough that a server-side URL change is picked up within an hour.
# Module-level so it survives across resolver instances within one HA
# process.
_OIDC_DISCOVERY_CACHE: dict[str, tuple[str, float]] = {}
_OIDC_DISCOVERY_TTL_S = 3600
_OIDC_DISCOVERY_TIMEOUT_S = 5


class _PriorPairDeprecation:
    """v2.5.11 — one-shot guard so the c95f4fd2 deprecation note is
    only logged the first time the chain is built. Class-with-attr
    pattern keeps the flag mutable while the module-level singleton
    semantics are obvious from the call site."""
    warned: bool = False


def _load_apk_auth_secrets(brand_name: str) -> dict[str, Any]:
    """Return the ``auth_secrets`` block from the latest APK extraction
    for ``brand_name``, or an empty dict if unavailable.

    Cache shape (per `_v3.0-artifact-mining-plan.md` and v2.5.5 patterns):
        {"versions": {"<version>": {"findings": {"auth_secrets": {...}}}}}

    The "latest" version is determined by max() over the version keys —
    works as long as version-name strings sort lexicographically (true
    for all 7 VAG brand apps as of 2026-05).
    """
    if _APK_CACHE_ROOT is None:
        return {}
    json_path = _APK_CACHE_ROOT / f"{brand_name}.json"
    if not json_path.is_file():
        return {}
    try:
        data = json.loads(json_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    versions = data.get("versions") or {}
    if not versions:
        return {}
    latest_v = max(versions.keys())
    findings = (versions[latest_v].get("findings") or {})
    return findings.get("auth_secrets") or {}


class AuthConfigResolver:
    """Resolves auth config values with APK-primary, hardcoded-fallback chain.

    Construct one per brand (cheap — caches the APK lookup in __init__).
    Read values via the typed getter methods; the resolver picks the
    highest-priority available source per call.

    Priority chain:
        1. APK extraction (`.app-atlas-apk-cache/{brand}.json`)
        2. Hardcoded competitor-derived constants (passed via the
           ``hardcoded_*`` kwargs at construction time)
        3. Alternates from ``_ALTERNATE_CLIENT_IDS`` for the OAuth
           client_id chain (extra fallback candidates)
    """

    def __init__(
        self,
        brand_name: str,
        *,
        hardcoded_client_id: str,
        hardcoded_qmauth_secret: str,
        hardcoded_qmauth_client_id: str,
        hardcoded_token_url: str,
        prior_qmauth_secret: str | None = None,
        prior_qmauth_client_id: str | None = None,
    ) -> None:
        self._brand = brand_name
        self._apk = _load_apk_auth_secrets(brand_name)
        self._hardcoded_client_id = hardcoded_client_id
        self._hardcoded_qmauth_secret = hardcoded_qmauth_secret
        self._hardcoded_qmauth_client_id = hardcoded_qmauth_client_id
        self._hardcoded_token_url = hardcoded_token_url
        # v2.5.7 R2 — optional prior qmauth pair as last-resort fallback.
        self._prior_qmauth_secret = prior_qmauth_secret
        self._prior_qmauth_client_id = prior_qmauth_client_id
        if self._apk:
            _LOGGER.debug(
                "AuthConfigResolver(%s): loaded auth_secrets from APK cache: keys=%s",
                brand_name, list(self._apk.keys()),
            )

    # ── Single-value getters ───────────────────────────────────────────────

    def qmauth_secret(self) -> str:
        """HMAC-SHA256 key for the x-qmauth header. APK-primary."""
        candidates = self._apk.get("qmauth_secret_candidates") or []
        for c in candidates:
            if isinstance(c, str) and len(c) == 64:
                return c.lower()
        return self._hardcoded_qmauth_secret

    def qmauth_client_id(self) -> str:
        """8-char hex client identifier embedded in the x-qmauth value."""
        # In the APK cache, the 8-hex variant lands under
        # ``client_id_candidates``. Prefer the first 8-char hex value.
        candidates = self._apk.get("client_id_candidates") or []
        for c in candidates:
            if isinstance(c, str) and len(c) == 8 and all(
                ch in "0123456789abcdef" for ch in c.lower()
            ):
                return c.lower()
        return self._hardcoded_qmauth_client_id

    def token_url(self) -> str:
        """Token-exchange URL for the brand's IDK.

        Resolution priority (v2.5.11 chain):
            1. OIDC discovery cache (`/auth/v1/idk/oidc/openid-configuration`
               ``token_endpoint`` field) — populated by
               ``refresh_via_discovery()`` once per TTL. Picks up
               server-side URL changes within ~1 h.
            2. Audi market-config CDN (v2.5.11 — content.app.my.audi.com,
               24h TTL). For Audi brand, derives token URL from the
               ``idkLoginServiceConfigurationURLProduction`` field that
               the official Audi app reads at startup. audi_connect_ha
               PR #736 noticed the 2026-05-28 migration via this layer.
            3. APK extraction (`token_path_markers_seen`) — daily atlas
               picks up app-bundled URL changes.
            4. Hardcoded constant — v2.5.4 baseline as safety net.
        """
        cached = _OIDC_DISCOVERY_CACHE.get(self._brand)
        if cached is not None:
            url, ts = cached
            if (time.monotonic() - ts) < _OIDC_DISCOVERY_TTL_S:
                return url
            # Stale — let the next refresh_via_discovery() update it.

        # v2.5.11 — Audi market-config (only meaningful for Audi brand).
        if self._brand == "audi":
            from ._audi_market_config import (  # noqa: PLC0415
                cached_audi_market_config,
                derive_token_url_from_market_config,
            )
            market_cfg = cached_audi_market_config()
            derived = derive_token_url_from_market_config(market_cfg)
            if derived:
                return derived

        paths = self._apk.get("token_path_markers_seen") or []
        for p in paths:
            if p == "/auth/v1/idk/oidc/token":
                return "https://emea.bff.cariad.digital/auth/v1/idk/oidc/token"
        return self._hardcoded_token_url

    async def refresh_via_discovery(self, session: Any) -> str | None:
        """v2.5.7 R3 — fetch ``token_endpoint`` via OIDC discovery.

        Populates the module-level ``_OIDC_DISCOVERY_CACHE`` so subsequent
        ``token_url()`` calls return the discovered value. Best-effort:
        a network failure / non-200 / malformed JSON silently keeps the
        previous cache (or falls through to APK + hardcoded fallback).

        The call is throttled by the TTL — within ``_OIDC_DISCOVERY_TTL_S``
        seconds of the last successful refresh, this is a no-op.

        Args:
            session: an aiohttp ``ClientSession``.

        Returns:
            The discovered ``token_endpoint`` URL, or ``None`` if the
            discovery call failed and there was no prior cached value.
        """
        # Discovery URL is shared across Audi + VW EU brands — both use
        # the same emea.bff.cariad.digital CARIAD-BFF cluster.
        discovery_url = (
            "https://emea.bff.cariad.digital"
            "/auth/v1/idk/oidc/openid-configuration"
        )
        # Throttle: skip if last refresh is still within TTL.
        cached = _OIDC_DISCOVERY_CACHE.get(self._brand)
        if cached is not None:
            _, ts = cached
            if (time.monotonic() - ts) < _OIDC_DISCOVERY_TTL_S:
                return cached[0]

        try:
            # Local import to avoid circular dependency at module load.
            from aiohttp import ClientTimeout  # noqa: PLC0415
            async with session.get(
                discovery_url,
                timeout=ClientTimeout(total=_OIDC_DISCOVERY_TIMEOUT_S),
                headers={"Accept": "application/json"},
            ) as resp:
                if resp.status != 200:
                    _LOGGER.debug(
                        "OIDC discovery (%s): HTTP %d — keeping fallback URL",
                        self._brand, resp.status,
                    )
                    return cached[0] if cached else None
                payload = await resp.json()
        except Exception as exc:  # noqa: BLE001 — best-effort discovery
            _LOGGER.debug(
                "OIDC discovery (%s): %s: %s — keeping fallback",
                self._brand, type(exc).__name__, exc,
            )
            return cached[0] if cached else None

        token_endpoint = payload.get("token_endpoint")
        if not isinstance(token_endpoint, str) or not token_endpoint.startswith("http"):
            _LOGGER.debug(
                "OIDC discovery (%s): no usable token_endpoint in response — "
                "keeping fallback URL",
                self._brand,
            )
            return cached[0] if cached else None

        _OIDC_DISCOVERY_CACHE[self._brand] = (token_endpoint, time.monotonic())
        # Log at INFO if we changed the URL since last cache — visible
        # signal that the VW IDP rotated something.
        prior_url = cached[0] if cached else None
        if prior_url is not None and prior_url != token_endpoint:
            _LOGGER.info(
                "OIDC discovery (%s): token_endpoint CHANGED — %s → %s",
                self._brand, prior_url, token_endpoint,
            )
        else:
            _LOGGER.debug(
                "OIDC discovery (%s): token_endpoint=%s",
                self._brand, token_endpoint,
            )
        return token_endpoint

    async def refresh_audi_market_config(
        self,
        session: Any,
        country: str = "DE",
        language: str = "de",
    ) -> dict[str, str]:
        """v2.5.11 — fetch the Audi market-config CDN entry.

        Best-effort wrapper around
        ``_audi_market_config.fetch_audi_market_config`` that always
        returns a dict (empty on failure). Populates the module-level
        cache so subsequent ``token_url()`` / ``oauth_client_id_chain()``
        calls can use the discovered values.

        Only meaningful for the ``"audi"`` brand. For other brands this
        is a no-op returning ``{}``.

        Args:
            session: an aiohttp ``ClientSession``.
            country: ISO 3166-1 alpha-2 country. Default ``"DE"``.
            language: ISO 639-1 language. Default ``"de"``.

        Returns:
            The cached market-config subset (3 keys max), or ``{}``.
        """
        if self._brand != "audi":
            return {}
        from ._audi_market_config import fetch_audi_market_config  # noqa: PLC0415
        return await fetch_audi_market_config(
            session, country=country, language=language,
        )

    # ── Multi-value chain ──────────────────────────────────────────────────

    def qmauth_chain(self) -> list[tuple[str, str]]:
        """Return ``(secret_hex, client_id)`` qmauth tuples in priority order.

        v2.5.7 R2 — when VW rotates the qmauth pair, we don't immediately
        know the new value (extraction from APK is blocked by runtime
        obfuscation; we wait for evcc/audi_connect_ha live captures).
        The fallback chain lets the integration try previously-working
        pairs before giving up — buys ~hours of "still works for most
        users" until the new pair lands.

        Order:
            1. APK-extracted pair (if v2.5.5 Phase A.5 shield captured it)
            2. Current hardcoded pair (the v2.5.4 evcc PR #30292 values)
            3. Prior hardcoded pair (the evcc PR #30277 baseline)

        v2.5.11 — the prior pair (``c95f4fd2`` / ``e47866378e...``) is
        CONFIRMED DEPRECATED. Cross-source verification 2026-05-29:
        evcc PR #30292 removed it; audi_connect_ha never had it. We
        keep it as last-resort only for the unlikely case VW rolls
        back the rotation. A warning is logged the first time this
        deprecated pair is reached in any process (via
        ``_warned_about_c95f4fd2``) so users see when their auth path
        hits a dead branch.

        Dedupes — if all three sources agree, we return one tuple.
        """
        ordered: list[tuple[str, str]] = []
        seen: set[tuple[str, str]] = set()

        def _add(secret: str | None, client_id: str | None) -> None:
            if not secret or not client_id:
                return
            key = (secret.lower(), client_id.lower())
            if key not in seen:
                ordered.append(key)
                seen.add(key)

        # 1. APK-extracted (will be empty until smali parser succeeds —
        # currently dead-end per Path 2.5, but ready when we get there).
        apk_secrets = self._apk.get("qmauth_secret_candidates") or []
        apk_client_ids = self._apk.get("client_id_candidates") or []
        # Pair-up if exactly one of each (most APKs would have just one).
        if apk_secrets and apk_client_ids:
            apk_8hex_ids = [c for c in apk_client_ids
                            if isinstance(c, str) and len(c) == 8]
            for s in apk_secrets:
                if isinstance(s, str) and len(s) == 64:
                    for cid in apk_8hex_ids:
                        _add(s, cid)

        # 2. Current hardcoded (the v2.5.4 baseline).
        _add(self._hardcoded_qmauth_secret, self._hardcoded_qmauth_client_id)

        # 3. Prior hardcoded (evcc PR #30277 baseline, rotated 2026-05-28).
        # v2.5.11 — log a one-shot warning when the deprecated pair is
        # included in the chain (it WILL be tried only if the primary
        # pair returns 4xx, which is itself unusual now).
        if (
            self._prior_qmauth_client_id == "c95f4fd2"
            and not _PriorPairDeprecation.warned
        ):
            _LOGGER.info(
                "qmauth fallback chain includes the c95f4fd2 prior pair "
                "(deprecated 2026-05-28 per evcc PR #30292). It will be "
                "tried only if the current 01da27b0 pair returns 4xx. "
                "If you see this followed by a 'fallback attempt succeeded' "
                "log line, file an issue — that means VW unexpectedly "
                "rolled back the qmauth rotation."
            )
            _PriorPairDeprecation.warned = True
        _add(self._prior_qmauth_secret, self._prior_qmauth_client_id)

        return ordered

    def oauth_client_id_chain(self) -> list[str]:
        """Return OAuth client_id candidates in try-first-success order.

        Order (v2.5.11):
            1. Audi market-config ``idkClientIDAndroidLive`` (Audi only,
               24h cache populated by ``refresh_audi_market_config()``)
            2. UUIDs found in the latest APK (excluding the hardcoded one
               if it's also present — it gets appended at the end)
            3. Per-brand alternates from ``_ALTERNATE_CLIENT_IDS``
            4. The hardcoded canonical client_id

        Dedupes while preserving order.
        """
        ordered: list[str] = []
        seen: set[str] = set()

        def _add(cid: str) -> None:
            if cid and cid not in seen:
                ordered.append(cid)
                seen.add(cid)

        # v2.5.11 — 1. Audi market-config (only for Audi brand).
        if self._brand == "audi":
            from ._audi_market_config import (  # noqa: PLC0415
                cached_audi_market_config,
            )
            market_cfg = cached_audi_market_config()
            market_cid = market_cfg.get("idkClientIDAndroidLive")
            if isinstance(market_cid, str) and "@apps_vw-dilab_com" in market_cid:
                _add(market_cid)

        # 2. From the APK cache. The `client_id_candidates` field contains
        # a mix of 8-hex strings AND full UUIDs — filter to UUIDs here.
        for c in (self._apk.get("client_id_candidates") or []):
            if isinstance(c, str) and "@apps_vw-dilab_com" in c:
                _add(c)

        # 3. Per-brand alternates discovered in the 2026-05-27 retro-mining.
        for alt in _ALTERNATE_CLIENT_IDS.get(self._brand, ()):
            _add(alt)

        # 4. The hardcoded canonical client_id — always last so it acts as
        # the safety-net the rest of the chain falls back to.
        _add(self._hardcoded_client_id)
        return ordered

    # ── Provenance for debug/diagnostic ────────────────────────────────────

    def provenance(self) -> dict[str, str]:
        """Return where each resolved value came from. For diagnostics."""
        return {
            "qmauth_secret": (
                "apk" if self._apk.get("qmauth_secret_candidates")
                else "hardcoded"
            ),
            "qmauth_client_id": (
                "apk" if self._apk.get("client_id_candidates")
                else "hardcoded"
            ),
            "token_url": (
                "apk" if any(
                    p == "/auth/v1/idk/oidc/token"
                    for p in (self._apk.get("token_path_markers_seen") or [])
                )
                else "hardcoded"
            ),
            "oauth_client_id_chain_size": str(len(self.oauth_client_id_chain())),
        }
