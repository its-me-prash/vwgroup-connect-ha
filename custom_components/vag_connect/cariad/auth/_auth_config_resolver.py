# Copyright 2026 Prash Balan (@its-me-prash) — Apache License 2.0
"""v2.5.6 — APK-primary, competitor-fallback auth config resolver.

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
    ) -> None:
        self._brand = brand_name
        self._apk = _load_apk_auth_secrets(brand_name)
        self._hardcoded_client_id = hardcoded_client_id
        self._hardcoded_qmauth_secret = hardcoded_qmauth_secret
        self._hardcoded_qmauth_client_id = hardcoded_qmauth_client_id
        self._hardcoded_token_url = hardcoded_token_url
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
        """Token-exchange URL for the brand's IDK."""
        paths = self._apk.get("token_path_markers_seen") or []
        # Prefer the new `/auth/v1/idk/oidc/token` if the APK confirms it.
        for p in paths:
            if p == "/auth/v1/idk/oidc/token":
                # APK confirmed the new URL — assemble against the BFF host.
                return "https://emea.bff.cariad.digital/auth/v1/idk/oidc/token"
        return self._hardcoded_token_url

    # ── Multi-value chain ──────────────────────────────────────────────────

    def oauth_client_id_chain(self) -> list[str]:
        """Return OAuth client_id candidates in try-first-success order.

        Order:
            1. UUIDs found in the latest APK (excluding the hardcoded one
               if it's also present — it gets appended at the end)
            2. Per-brand alternates from ``_ALTERNATE_CLIENT_IDS``
            3. The hardcoded canonical client_id

        Dedupes while preserving order.
        """
        ordered: list[str] = []
        seen: set[str] = set()

        def _add(cid: str) -> None:
            if cid and cid not in seen:
                ordered.append(cid)
                seen.add(cid)

        # 1. From the APK cache. The `client_id_candidates` field contains
        # a mix of 8-hex strings AND full UUIDs — filter to UUIDs here.
        for c in (self._apk.get("client_id_candidates") or []):
            if isinstance(c, str) and "@apps_vw-dilab_com" in c:
                _add(c)

        # 2. Per-brand alternates discovered in the 2026-05-27 retro-mining.
        for alt in _ALTERNATE_CLIENT_IDS.get(self._brand, ()):
            _add(alt)

        # 3. The hardcoded canonical client_id — always last so it acts as
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
