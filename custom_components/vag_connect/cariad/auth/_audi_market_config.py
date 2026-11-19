# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""v2.5.11 — Audi Market-Config dynamic discovery.

Backstory: when VW migrated the CARIAD token endpoint on 2026-05-28
(``/login/v1/idk/token`` → ``/auth/v1/idk/oidc/token``), the
``upstream`` integration noticed the change WITHIN HOURS — not
because their devs found it on GitHub, but because the official myAudi
Android app already advertised the new URL in its **market-config CDN**.
The integration just had to read what the app was already telling it.

This module replicates that capability for vag-connect-ha. The Audi
app fetches::

    GET https://content.app.my.audi.com/service/mobileapp/configurations/market/{country}/{language}?v=<app version>

at startup. ``v`` is the app's own versionName (myAudi 5.10.1:
``MarketResourceDownloadAction.l()`` appends ``VersionInformation.e()``),
and the CDN answers with a key set for that version: measured 2026-11-18,
DE returned 68 keys for ``v=4.23.1`` and 122 for ``v=5.10.1``. We send the
version from the one myAudi identity in ``models.py``.

We read three keys that survive backend rotations:

* ``idkLoginServiceConfigurationURLProduction`` — the OIDC discovery
  URL (typically ``https://emea.bff.cariad.digital/auth/v1/idk/oidc/
  openid-configuration``). When VW flips the path again, the market
  config flips first.
* ``idkClientIDAndroidLive`` — the OAuth ``client_id``. Pre-rotation
  this matches our hardcoded ``09b6cbec-cd19-...``; post-rotation
  this is the new id.
* ``mbbOAuthBaseURLLive`` — the legacy MBB token base
  (``https://mbboauth-1d.prd.ece.vwg-connect.com``). Used by our
  legacy fs-car data path; if VW rotates that too the CDN value
  follows.

**Measured 2026-11-18 (DE and CH, both ``v`` values): only the
discovery URL is served.** ``idkClientIDAndroidLive`` and
``mbbOAuthBaseURLLive`` are absent, so today the app uses its built-in
defaults for both and so do we. They stay on the read list because their
consumers (``_auth0.resolve_client_id``, ``_auth_config_resolver``) are
the rotation path if a market starts serving them again; absent is the
harmless case.

It also carries four watch keys, read as strings and logged when they
change, because they decide how the app signs in (myAudi 5.10.1):

* ``marketSupportsAuth0`` — chooses Auth0 instead of IdentityKit for new
  sign-ins (``UserModuleKt`` client configuration). App default false;
  absent in DE and CH on 2026-11-18. Logged once at INFO when a market
  turns it on.
* ``marketSupportsAndroidClientValidation`` — Play Integrity on the token
  call. ``true`` in DE and CH on 2026-11-18.
* ``auth0MigrationNotice`` (``None``/``Inform``/``ForcedLogout``) and
  ``webViewAuthenticationProvider`` (default ``idk``).

The fetch is **best-effort with hard fallback**: a failed/timeout/
malformed response leaves the existing chain (OIDC discovery → APK
cache → hardcoded constants) intact. No new failure mode for users
who don't need this layer.

## Architecture: where this slots into the priority chain

::

    1. OIDC discovery cache  (v2.5.7 R3 — token_endpoint from
       /auth/v1/idk/oidc/openid-configuration, 1h TTL)
    2. Audi market-config    (v2.5.11 — idkLoginServiceConfigurationURLProduction
       + idkClientIDAndroidLive + mbbOAuthBaseURLLive, 24h TTL)
    3. APK cache             (Phase A.5+ — daily extraction, 24h+ TTL)
    4. Hardcoded constants   (v2.5.4 baseline — safety net)

The 24h cache TTL matches the Audi app's startup-once pattern. The
data rarely changes in a single day; when it does (rotation event),
the next HA restart picks it up.

## Why Audi-only

The myAudi app exposes this market-config endpoint and the keys above.
VW WeConnect uses a different config CDN that does NOT expose the
same key set — and crucially VW's token URL is the same one Audi
uses (same CARIAD-BFF, same OIDC discovery doc), so the Audi market
config indirectly helps both brands.

## Coverage

The function is callable per-region. Default ``country=DE language=de``
matches our existing user base. Future enhancement: read country from
HA config (``hass.config.country``) and pass through.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

from ..models import MYAUDI_APP_VERSION, MYAUDI_USER_AGENT

_LOGGER = logging.getLogger(__name__)


# Module-level cache keyed by (country, language). Each entry holds the
# fetched dict + the monotonic clock time of fetch.
_AUDI_MARKET_CACHE: dict[tuple[str, str], tuple[dict[str, Any], float]] = {}
_AUDI_MARKET_TTL_S = 86400  # 24 h
_AUDI_MARKET_TIMEOUT_S = 5


_MARKET_CONFIG_URL_TEMPLATE = (
    "https://content.app.my.audi.com"
    "/service/mobileapp/configurations/market/{country}/{language}"
    "?v={version}"
)


# Keys we care about — subset of the full response. The Audi market-
# config response is large (~30 KB) but we only extract these three
# resilience-critical fields. Any other keys are ignored.
_KEYS_OF_INTEREST = frozenset({
    "idkLoginServiceConfigurationURLProduction",
    "idkClientIDAndroidLive",
    "mbbOAuthBaseURLLive",
})

# Sign-in watch keys (see module docstring). Booleans are stored as
# ``"true"``/``"false"`` so the returned dict keeps its ``str`` values.
_WATCH_KEYS = frozenset({
    "marketSupportsAuth0",
    "marketSupportsAndroidClientValidation",
    "auth0MigrationNotice",
    "webViewAuthenticationProvider",
})

# Markets already reported as Auth0 sign-in markets in this process, so the
# INFO line appears once per market and not on every 24 h refresh.
_AUTH0_MARKETS_NOTED: set[tuple[str, str]] = set()


async def fetch_audi_market_config(
    session: Any,
    *,
    country: str = "DE",
    language: str = "de",
    force_refresh: bool = False,
) -> dict[str, str]:
    """Fetch (or read from cache) the Audi market-config subset.

    Args:
        session: an ``aiohttp.ClientSession``.
        country: ISO 3166-1 alpha-2 country code. Default ``"DE"``.
        language: ISO 639-1 language code. Default ``"de"``.
        force_refresh: if True, bypasses the cache and re-fetches.

    Returns:
        A dict with a subset of ``_KEYS_OF_INTEREST`` and ``_WATCH_KEYS``.
        Values are strings (URLs, client IDs, or ``"true"``/``"false"`` for
        the boolean watch keys). Missing keys mean
        the field was absent from the response or fetch failed.
        Always safe to ``.get()`` against; never raises.

    Cache behaviour:
        Within 24 h of a successful fetch this is a no-op. After 24 h
        the next call refreshes the cache. Cache TTL matches the
        official Audi app's startup-once pattern.
    """
    cache_key = (country.upper(), language.lower())
    cached = _AUDI_MARKET_CACHE.get(cache_key)
    if cached is not None and not force_refresh:
        cfg, fetched_at = cached
        if (time.monotonic() - fetched_at) < _AUDI_MARKET_TTL_S:
            return cfg

    url = _MARKET_CONFIG_URL_TEMPLATE.format(
        country=country.upper(), language=language.lower(),
        version=MYAUDI_APP_VERSION,
    )
    try:
        # Local import to avoid a hard aiohttp dependency at module load.
        from aiohttp import ClientTimeout  # noqa: PLC0415
        async with session.get(
            url,
            timeout=ClientTimeout(total=_AUDI_MARKET_TIMEOUT_S),
            headers={
                "Accept": "application/json",
                # UA mirrors the official Audi app — content CDN does
                # not require it but it makes the fetch indistinguishable
                # from a real client which is friendlier to ops.
                "User-Agent": MYAUDI_USER_AGENT,
            },
        ) as resp:
            if resp.status != 200:
                _LOGGER.debug(
                    "Audi market-config (%s/%s): HTTP %d — keeping cache",
                    country, language, resp.status,
                )
                return cached[0] if cached else {}
            try:
                payload = await resp.json()
            except (ValueError, json.JSONDecodeError) as exc:
                _LOGGER.debug(
                    "Audi market-config (%s/%s): non-JSON body: %s — keeping cache",
                    country, language, exc,
                )
                return cached[0] if cached else {}
    except Exception as exc:  # noqa: BLE001 — best-effort discovery
        _LOGGER.debug(
            "Audi market-config (%s/%s): %s: %s — keeping cache",
            country, language, type(exc).__name__, exc,
        )
        return cached[0] if cached else {}

    if not isinstance(payload, dict):
        _LOGGER.debug(
            "Audi market-config (%s/%s): payload is %s, not dict — keeping cache",
            country, language, type(payload).__name__,
        )
        return cached[0] if cached else {}

    extracted: dict[str, str] = {}
    for k in _KEYS_OF_INTEREST:
        v = payload.get(k)
        if isinstance(v, str) and v:
            extracted[k] = v
    for k in _WATCH_KEYS:
        v = payload.get(k)
        if isinstance(v, bool):  # before str: JSON true/false
            extracted[k] = "true" if v else "false"
        elif isinstance(v, str) and v:
            extracted[k] = v

    if extracted.get("marketSupportsAuth0") == "true" and (
        cache_key not in _AUTH0_MARKETS_NOTED
    ):
        _AUTH0_MARKETS_NOTED.add(cache_key)
        _LOGGER.info(
            "Audi market-config (%s/%s): marketSupportsAuth0 is set — the "
            "myAudi app signs new logins in this market in through Auth0 "
            "instead of IdentityKit",
            country, language,
        )

    # Log changes when refreshed (info-level — visible in HA logs at
    # default verbosity if cache key changed) — useful detection of
    # an Audi-side rotation or a sign-in switch.
    if cached is not None:
        prior_cfg = cached[0]
        for k in _KEYS_OF_INTEREST | _WATCH_KEYS:
            if extracted.get(k) and prior_cfg.get(k) != extracted.get(k):
                _LOGGER.info(
                    "Audi market-config (%s/%s): %s CHANGED — %s → %s",
                    country, language, k,
                    prior_cfg.get(k), extracted.get(k),
                )

    _AUDI_MARKET_CACHE[cache_key] = (extracted, time.monotonic())
    _LOGGER.debug(
        "Audi market-config (%s/%s): cached keys=%s",
        country, language, list(extracted.keys()),
    )
    return extracted


def cached_audi_market_config(
    country: str = "DE",
    language: str = "de",
) -> dict[str, str]:
    """Read-only sync accessor for the cached market-config subset.

    Returns an empty dict if no fetch has succeeded yet (caller should
    arrange for an async ``fetch_audi_market_config()`` call elsewhere
    in the lifecycle to populate it).

    Args:
        country: ISO 3166-1 alpha-2 country code. Default ``"DE"``.
        language: ISO 639-1 language code. Default ``"de"``.

    Returns:
        The cached dict, or ``{}`` if unavailable / cache expired.
    """
    cache_key = (country.upper(), language.lower())
    cached = _AUDI_MARKET_CACHE.get(cache_key)
    if cached is None:
        return {}
    cfg, fetched_at = cached
    if (time.monotonic() - fetched_at) >= _AUDI_MARKET_TTL_S:
        return {}
    return dict(cfg)  # copy to prevent mutation


def derive_token_url_from_market_config(market_cfg: dict[str, str]) -> str | None:
    """Convert the OIDC discovery URL from market-config into our token URL.

    The market-config exposes the ``openid-configuration`` URL — we
    derive the token-endpoint URL by string-replacing the discovery
    suffix. This pattern matches what upstream's audi_services.py
    does (fall back to known URL shape if OIDC fetch itself isn't
    available).

    Args:
        market_cfg: dict from ``fetch_audi_market_config()``.

    Returns:
        The likely token endpoint URL, or ``None`` if the discovery URL
        is absent or doesn't follow the expected shape.
    """
    discovery_url = market_cfg.get("idkLoginServiceConfigurationURLProduction")
    if not isinstance(discovery_url, str):
        return None
    # Two known shapes — MUST check longest-suffix first so the
    # `.well-known/` case isn't shadowed by the bare `openid-configuration`
    # suffix (which is a substring of the longer one).
    #   {host}/auth/v1/idk/oidc/openid-configuration → {host}/auth/v1/idk/oidc/token
    #   {host}/login/v1/idk/openid-configuration → {host}/login/v1/idk/token  (legacy)
    #   {host}/.well-known/openid-configuration → {host}/token  (rare)
    for suffix, replacement in (
        ("/.well-known/openid-configuration", "/token"),
        ("/openid-configuration", "/token"),
    ):
        if discovery_url.endswith(suffix):
            return discovery_url[: -len(suffix)] + replacement
    return None
