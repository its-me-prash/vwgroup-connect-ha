#!/usr/bin/env python3
# Copyright 2026 Prash Balan (@its-me-prash) — Apache License 2.0
"""App Atlas builder — Phase A.1 (lightweight version-polling).

Usage:
    python scripts/app_atlas/build_atlas.py [--brand BRAND] [--dry-run]

What this does (Phase A.1):
1. Reads scripts/app_atlas/config.json
2. For each brand: scrapes APKMirror for current latest version-name +
   version-code
3. Compares to .app-atlas-cache.json (committed state)
4. Updates docs/research/app-atlas/{brand}.md with current version
5. Updates docs/research/app-atlas/_summary.md (cross-brand matrix)
6. Updates .app-atlas-cache.json with the new state

Phase A.2 will add: APK download via APKMirror direct CDN + apktool
extraction + grep for OLA headers + endpoint discovery.

Phase A.3 will add: jadx full decompile + semantic diff between
consecutive versions.

CI-friendliness:
- Pure stdlib (no external deps for Phase A.1)
- Idempotent: re-runs without version changes are no-ops
- Graceful per-brand failure: one unreachable APKMirror page doesn't
  fail the whole run
"""

from __future__ import annotations

import argparse
import datetime
import json
import logging
import re
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

_LOGGER = logging.getLogger("app_atlas")

# ── Paths ───────────────────────────────────────────────────────────
_REPO_ROOT      = Path(__file__).resolve().parent.parent.parent
_CONFIG_PATH    = _REPO_ROOT / "scripts" / "app_atlas" / "config.json"
_ATLAS_DIR      = _REPO_ROOT / "docs" / "research" / "app-atlas"
_CACHE_PATH     = _REPO_ROOT / ".app-atlas-cache.json"
_APK_CACHE_DIR  = _REPO_ROOT / ".app-atlas-apk-cache"   # NEW v Phase A.2
_SUMMARY_PATH   = _ATLAS_DIR / "_summary.md"

# ── HTTP ────────────────────────────────────────────────────────────
_UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
_TIMEOUT = 20


def _fetch(url: str) -> str:
    """GET a URL with a polite User-Agent, returning the body as text."""
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
        return resp.read().decode("utf-8", errors="replace")


# ── Source scrapers (multi-source fallback chain) ───────────────────
# Strategy: try APKMirror first (most authoritative). If it 404/403s,
# fall back to Uptodown (more scraper-friendly, broader coverage of
# European OEM apps). Adding a 3rd source (e.g. Aptoide) is a 1-block
# extension in scrape_version().

_APKMIRROR_BASE = "https://www.apkmirror.com/apk/"
_UPTODOWN_BASE  = "https://{sub}.en.uptodown.com/android"
_APKCOMBO_BASE  = "https://apkcombo.com/{slug}/"

# APKMirror page regexes — multiple layouts seen in the wild.
_APKMIRROR_VERSION_REGEXES = [
    re.compile(r'class="appRowVersionName"[^>]*>\s*<a[^>]*>[^<]*?\s+(\d+(?:\.\d+){1,3}(?:-\d+)?)', re.IGNORECASE),
    re.compile(r'class="appRowTitle[^"]*"[^>]*>\s*<a[^>]*>[^<]*?\s+(\d+(?:\.\d+){1,3}(?:-\d+)?)', re.IGNORECASE),
    re.compile(r'/[a-z0-9-]+-(\d+(?:\.\d+){1,3}(?:-\d+)?)-release', re.IGNORECASE),
]

# Uptodown pattern: <div itemprop="softwareVersion">5.4.1</div>
_UPTODOWN_VERSION_REGEXES = [
    re.compile(r'itemprop="softwareVersion"[^>]*>\s*([\d.]+(?:-\w+)?)', re.IGNORECASE),
    re.compile(r'"latestVersion"\s*:\s*"([^"]+)"', re.IGNORECASE),
    re.compile(r'class="version"[^>]*>\s*([\d.]+(?:-\w+)?)', re.IGNORECASE),
]

# APKCombo pattern: title includes "Volkswagen ... 3.61.0 - Updated: 2026 - com.x.y"
_APKCOMBO_VERSION_REGEXES = [
    # The meta-title pattern: " 3.61.0 - Updated:" — anchored by ` - Updated:` for safety.
    re.compile(r'\b(\d+\.\d+\.\d+(?:[-.]\w+)?)\s*-\s*Updated:', re.IGNORECASE),
    # Fallback: any `<a>...3.61.0</a>` style link.
    re.compile(r'>(\d+\.\d+\.\d+(?:[-.]\w+)?)<\s*/\s*a\s*>', re.IGNORECASE),
]


def _try_apkmirror(slug: str) -> str | None:
    url = f"{_APKMIRROR_BASE}{slug}/"
    try:
        body = _fetch(url)
    except urllib.error.HTTPError as exc:
        _LOGGER.debug("APKMirror %s → HTTP %s", url, exc.code)
        return None
    except Exception as exc:  # noqa: BLE001
        _LOGGER.debug("APKMirror %s → %s", url, exc)
        return None
    for regex in _APKMIRROR_VERSION_REGEXES:
        m = regex.search(body)
        if m:
            return m.group(1)
    return None


def _try_uptodown(subdomain: str) -> str | None:
    url = _UPTODOWN_BASE.format(sub=subdomain)
    try:
        body = _fetch(url)
    except urllib.error.HTTPError as exc:
        _LOGGER.debug("Uptodown %s → HTTP %s", url, exc.code)
        return None
    except Exception as exc:  # noqa: BLE001
        _LOGGER.debug("Uptodown %s → %s", url, exc)
        return None
    for regex in _UPTODOWN_VERSION_REGEXES:
        m = regex.search(body)
        if m:
            return m.group(1)
    return None


def _try_apkcombo(slug: str) -> str | None:
    url = _APKCOMBO_BASE.format(slug=slug)
    try:
        body = _fetch(url)
    except urllib.error.HTTPError as exc:
        _LOGGER.debug("APKCombo %s → HTTP %s", url, exc.code)
        return None
    except Exception as exc:  # noqa: BLE001
        _LOGGER.debug("APKCombo %s → %s", url, exc)
        return None
    for regex in _APKCOMBO_VERSION_REGEXES:
        m = regex.search(body)
        if m:
            return m.group(1)
    return None


def scrape_version(brand: str, sources: dict[str, str | None]) -> tuple[str | None, str | None]:
    """Multi-source fallback scrape.

    Returns (version, source_name) — source_name is one of
    ``"apkmirror"``, ``"uptodown"``, ``"apkcombo"``, or ``None``.
    Tries each configured source in order; returns on first success.

    Adding a 4th source: implement ``_try_<name>(slug) -> str | None``
    + add an ``if <name>_slug := sources.get("<name>_slug")`` branch
    below.
    """
    apkmirror_slug = sources.get("apkmirror_slug")
    if apkmirror_slug:
        v = _try_apkmirror(apkmirror_slug)
        if v:
            return v, "apkmirror"

    uptodown_sub = sources.get("uptodown_subdomain")
    if uptodown_sub:
        v = _try_uptodown(uptodown_sub)
        if v:
            return v, "uptodown"

    # v2.4.2+ — APKCombo as 3rd-tier fallback. Less reliable than
    # APKMirror but covers some apps that APKMirror + Uptodown don't.
    apkcombo_slug = sources.get("apkcombo_slug")
    if apkcombo_slug:
        v = _try_apkcombo(apkcombo_slug)
        if v:
            return v, "apkcombo"

    _LOGGER.warning(
        "Brand %s: all sources failed (apkmirror_slug=%r, "
        "uptodown_subdomain=%r, apkcombo_slug=%r)",
        brand, apkmirror_slug, uptodown_sub, apkcombo_slug,
    )
    return None, None


# ── Cache I/O ───────────────────────────────────────────────────────


def load_cache() -> dict[str, Any]:
    if not _CACHE_PATH.exists():
        return {"_atlas_version": 1, "brands": {}}
    return json.loads(_CACHE_PATH.read_text(encoding="utf-8"))


def save_cache(cache: dict[str, Any]) -> None:
    cache["_last_updated"] = datetime.datetime.now(tz=datetime.timezone.utc).isoformat()
    _CACHE_PATH.write_text(
        json.dumps(cache, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


# ── Atlas markdown emitter (Phase A.1 — version-only) ──────────────


def _load_apk_findings(brand: str) -> dict[str, Any] | None:
    """Load the cached APK-extraction findings for ``brand`` (if any).

    Phase A.2: ``.app-atlas-apk-cache/{brand}.json`` is written by
    the apk_extractor when extraction succeeds. None means we've
    never run extraction for this brand OR the last attempt failed.
    """
    p = _APK_CACHE_DIR / f"{brand}.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None


def _save_apk_findings(brand: str, findings: dict[str, Any], version: str) -> None:
    """Persist apk-extraction findings to disk for diff + atlas rendering."""
    _APK_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "brand": brand,
        "extracted_for_version": version,
        "findings": findings,
    }
    (_APK_CACHE_DIR / f"{brand}.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _render_apk_section(findings: dict[str, Any] | None) -> str:
    """Render the 'Discovered endpoints / headers' atlas sections.

    Returns markdown lines (no leading/trailing whitespace) ready for
    string-concat into the per-brand atlas template.
    """
    if findings is None:
        return (
            "_(Empty — Phase A.2 APK extraction not yet run for this "
            "brand, or last attempt failed. See `app_atlas/apk_extractor.py`.)_"
        )
    inner_findings = findings.get("findings", findings)
    extracted_at = inner_findings.get("extracted_at", "(unknown)")
    extracted_for = findings.get("extracted_for_version", "(unknown)")
    headers = inner_findings.get("headers", [])
    endpoints = inner_findings.get("endpoint_hosts", [])
    ola_values = inner_findings.get("ola_header_values", {})

    parts = [
        f"_Last extracted: {extracted_at[:19]} (for version `{extracted_for}`)_\n",
        "",
        "### HTTP header keys found in app bytecode",
        "",
    ]
    if headers:
        parts.extend(f"- `{h}`" for h in headers)
    else:
        parts.append("_(none of the configured OLA-style header keys found)_")
    if ola_values:
        parts.append("")
        parts.append("**Extracted header values:**")
        for key, val in sorted(ola_values.items()):
            parts.append(f"- `{key}` = `{val}`")

    parts.extend([
        "",
        "### Backend hosts found in app bytecode",
        "",
    ])
    if endpoints:
        parts.extend(f"- `{h}`" for h in endpoints)
    else:
        parts.append("_(none of the configured backend hosts found)_")

    return "\n".join(parts)


def emit_brand_atlas(brand: str, brand_cfg: dict[str, Any], current_version: str | None,
                    source_name: str | None, cache_entry: dict[str, Any]) -> None:
    """Write/update docs/research/app-atlas/{brand}.md."""
    display    = brand_cfg["display_name"]
    package    = brand_cfg["package_id"]
    backend    = brand_cfg["expected_backend"]
    ola_known  = brand_cfg.get("ola_enforcement_known", False)
    ola_since  = brand_cfg.get("ola_enforcement_since", "")
    prev_ver   = cache_entry.get("last_version_name", "")
    sources    = brand_cfg.get("sources", {})
    now        = datetime.datetime.now(tz=datetime.timezone.utc).strftime("%Y-%m-%d")
    apk_section = _render_apk_section(_load_apk_findings(brand))

    src_label = source_name or "(no source succeeded)"
    md = f"""# App Atlas — {display}

> **Auto-generated** by `.github/workflows/app-atlas-builder.yml` ·
> Last refreshed: {now}

## Identity

| Field | Value |
|---|---|
| Android package ID | `{package}` |
| Expected backend | `{backend}` |
| OLA enforcement known? | {'**YES** (since ' + ola_since + ')' if ola_known else 'No (not observed yet)'} |

## Configured sources (fallback chain)

| Source | Configured value |
|---|---|
| APKMirror | `{sources.get('apkmirror_slug') or '(none)'}` |
| Uptodown | `{sources.get('uptodown_subdomain') or '(none)'}` |

## Current version

| | |
|---|---|
| Latest version-name | `{current_version or '(fetch failed)'}` |
| Source that responded | `{src_label}` |
| Previously cached version | `{prev_ver or '(first run)'}` |
| Changed since last run? | {'**YES**' if current_version and current_version != prev_ver else 'No'} |

## Discovered via APK extraction (Phase A.2)

{apk_section}

## Cross-version diff

_(Empty — Phase A.3 will populate this from full decompile + diff.)_

## Action items

_(Auto-flagged by the pipeline when new endpoints / headers / version-bumps suggest follow-up work.)_

---

_See [`README.md`](README.md) for atlas methodology and
[`LEGAL.md`](LEGAL.md) for reverse-engineering disclosure._
"""
    (_ATLAS_DIR / f"{brand}.md").write_text(md, encoding="utf-8")


def emit_summary(config: dict[str, Any], results: dict[str, str | None],
                 sources_used: dict[str, str | None]) -> None:
    """Write docs/research/app-atlas/_summary.md — cross-brand matrix."""
    now = datetime.datetime.now(tz=datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    rows: list[str] = []
    for brand, cfg in config["brands"].items():
        version = results.get(brand) or "(fetch failed)"
        src = sources_used.get(brand) or "—"
        ola_flag = "✅" if cfg.get("ola_enforcement_known") else "❌"
        rows.append(
            f"| **{cfg['display_name']}** | `{cfg['package_id']}` | "
            f"`{version}` | `{src}` | `{cfg['expected_backend']}` | {ola_flag} |"
        )
    body = (
        "# App Atlas — Cross-Brand Summary\n\n"
        f"> Auto-generated · Last refreshed: {now}\n\n"
        "| Brand | Android package | Latest version | Source | Expected backend | OLA enforced? |\n"
        "|---|---|---|---|---|---|\n"
        + "\n".join(rows)
        + "\n\n"
        "## Methodology\n\n"
        "Daily CI workflow ([`.github/workflows/app-atlas-builder.yml`](\n"
        "../../../.github/workflows/app-atlas-builder.yml)) scrapes\n"
        "APKMirror for the latest version of each VAG-brand Android app.\n"
        "When a version changes (Phase A.2+), the workflow downloads the\n"
        "APK, extracts it with apktool, and greps for known HTTP\n"
        "patterns (OLA headers, backend URLs, etc).\n\n"
        "**Phase progression**:\n\n"
        "- **A.1 (current)**: version-polling only. Confirms which apps\n"
        "  exist and tracks their version cadence.\n"
        "- **A.2 (next)**: APK download + string-pattern grep.\n"
        "- **A.3 (later)**: full decompile via jadx + cross-version\n"
        "  semantic diff.\n\n"
        "See per-brand pages in this directory for details.\n"
    )
    _SUMMARY_PATH.write_text(body, encoding="utf-8")


# ── Main loop ───────────────────────────────────────────────────────


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    p = argparse.ArgumentParser(description="Build the cross-brand App Atlas.")
    p.add_argument("--brand", help="Only process this single brand (for debugging).")
    p.add_argument("--dry-run", action="store_true",
                   help="Show what would change; don't write files.")
    p.add_argument("--with-apk-extraction", action="store_true",
                   help="Phase A.2: also download + decode APKs for brands where "
                        "the version-name changed since last cache. Requires apktool "
                        "on PATH. Adds significant CI runtime (~30s-2min per changed "
                        "brand) — only enable in the scheduled workflow, not for "
                        "local debugging.")
    p.add_argument("--force-extract", action="store_true",
                   help="Phase A.2 override: extract APKs for ALL brands "
                        "regardless of version-change cache state. Use this to "
                        "(re)build the apk-cache from scratch — e.g. after adding "
                        "a new brand, or for the initial population. Implies "
                        "--with-apk-extraction. CI-only; locally it requires "
                        "apktool on PATH for every brand.")
    args = p.parse_args(argv)
    # --force-extract implies --with-apk-extraction.
    if args.force_extract:
        args.with_apk_extraction = True

    config = json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
    cache = load_cache()
    cache.setdefault("brands", {})

    results: dict[str, str | None] = {}
    sources_used: dict[str, str | None] = {}
    changed_brands: list[str] = []

    target_brands = [args.brand] if args.brand else list(config["brands"].keys())
    for brand in target_brands:
        if brand not in config["brands"]:
            _LOGGER.error("Unknown brand %r — check config.json", brand)
            continue
        brand_cfg = config["brands"][brand]
        sources = brand_cfg.get("sources", {})
        if not sources:
            _LOGGER.warning("Brand %s has no sources configured — skipping", brand)
            results[brand] = None
            sources_used[brand] = None
            continue

        current, src = scrape_version(brand, sources)
        results[brand] = current
        sources_used[brand] = src
        prev_entry = cache["brands"].get(brand, {})
        prev_ver = prev_entry.get("last_version_name", "")

        if current and current != prev_ver:
            changed_brands.append(brand)
            _LOGGER.info("CHANGED %s: %s → %s (via %s)", brand, prev_ver or "(none)", current, src)
        elif current:
            _LOGGER.info("unchanged %s: %s (via %s)", brand, current, src)
        else:
            _LOGGER.warning("Could not determine current version for %s — all sources failed", brand)

        # Phase A.2 — APK extraction when version changed (or when
        # --force-extract is set, regardless of cache state).
        should_extract = (
            args.with_apk_extraction
            and current
            and not args.dry_run
            and (args.force_extract or current != prev_ver)
        )
        if should_extract:
            try:
                from .apk_extractor import extract_brand_apk  # noqa: PLC0415
            except ImportError:
                # Direct-execution path (not as a package); fall back to sys.path.
                import sys as _sys  # noqa: PLC0415
                _sys.path.insert(0, str(Path(__file__).parent))
                from apk_extractor import extract_brand_apk  # type: ignore[no-redef]
            with tempfile.TemporaryDirectory(prefix=f"atlas_apk_{brand}_") as td:
                tmp_dir = Path(td)
                _LOGGER.info("Brand %s: starting APK extraction (version %s)", brand, current)
                findings = extract_brand_apk(
                    brand, brand_cfg, config["search_patterns"], tmp_dir,
                )
                if findings:
                    _save_apk_findings(brand, findings, current)
                    _LOGGER.info("Brand %s: APK extraction OK — %d headers, %d hosts found",
                                 brand, len(findings.get("headers", [])),
                                 len(findings.get("endpoint_hosts", [])))
                else:
                    _LOGGER.warning("Brand %s: APK extraction failed — atlas page will "
                                    "render last-known findings only", brand)

        if not args.dry_run:
            emit_brand_atlas(brand, brand_cfg, current, src, prev_entry)
            cache["brands"][brand] = {
                "last_version_name": current,
                "last_source": src,
                "last_checked_at": datetime.datetime.now(
                    tz=datetime.timezone.utc
                ).isoformat(),
            }

    if not args.dry_run:
        emit_summary(config, results, sources_used)
        save_cache(cache)

    print(f"\nSummary: {len(changed_brands)} brand(s) changed: {changed_brands}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
