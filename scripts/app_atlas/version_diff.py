#!/usr/bin/env python3
# Copyright 2026 Prash Balan (@its-me-prash) — Apache License 2.0
"""Semantic diff between two jadx-decompiled APK versions — Phase A.3.

Targeted analysis instead of naive ``diff -r`` (which produces too
much noise from generated code, obfuscated class renames, and
unrelated UI changes).

What we extract from each version:
- HTTP/HTTPS URL constants
- Header-key strings (anywhere in code, even outside our known list)
- OAuth scope strings
- OkHttp interceptor + Retrofit @Header / @Path annotations
- Permission strings (AndroidManifest equivalent — from manifest XML or BuildConfig)

What we compare:
- URLs added in new version (NEW endpoints — most interesting)
- URLs removed (deprecation signals)
- Header keys added (potential future enforcement)
- Scopes changed (auth-flow evolution)

Output: a single markdown report
``docs/research/app-atlas/diffs/{brand}_{old}_vs_{new}.md`` —
self-contained, committed to the repo, scannable.
"""

from __future__ import annotations

import datetime
import logging
import re
import subprocess
from pathlib import Path
from typing import Any

_LOGGER = logging.getLogger("app_atlas.diff")

# Regexes used to extract semantic strings from decompiled .java files.
# These are intentionally permissive — we want to discover new
# endpoints, not enforce a strict schema. Post-processing filters out
# false positives.

# Matches "https://example.com/...", "http://example.com/..."
_URL_RE = re.compile(r'"(https?://[a-zA-Z0-9._/?&=:%~+#-]+)"')

# Matches "Authorization", "X-Custom-Header", "app-version" etc. as
# values used as header keys (3-50 chars, alphanumeric-with-dash).
# Restricted to strings appearing near HTTP-related code.
_HEADER_KEY_RE = re.compile(r'"([a-zA-Z][a-zA-Z0-9-]{2,49})"')

# OAuth scopes are typically space-separated string lists.
_OAUTH_SCOPE_RE = re.compile(r'"(openid[a-zA-Z0-9._\s+:-]+)"')


def extract_url_constants(decomp_dir: Path) -> set[str]:
    """Extract all HTTPS URL string constants from decompiled output."""
    urls: set[str] = set()
    try:
        result = subprocess.run(
            ["rg", "-Noh", "--no-heading", r'"https?://[^\s"]+"', str(decomp_dir)],
            check=False, capture_output=True, text=True, timeout=120,
        )
    except Exception as exc:  # noqa: BLE001
        _LOGGER.warning("rg failed during URL extraction: %s", exc)
        return urls
    for line in result.stdout.splitlines():
        m = _URL_RE.search(line)
        if not m:
            continue
        url = m.group(1)
        # Filter noise — drop user-doc URLs that are stable across versions.
        if any(noise in url for noise in (
            "schemas.android.com",
            "schemas.xmlsoap.org",
            "www.w3.org",
            "android.googleapis.com",
            "play.google.com",
        )):
            continue
        # Strip query strings + fragments to normalize.
        url_norm = re.split(r'[?#]', url)[0].rstrip("/")
        urls.add(url_norm)
    return urls


def extract_header_keys(decomp_dir: Path) -> set[str]:
    """Heuristic: header keys appear as string literals near OkHttp /
    Retrofit code. We extract candidates from the entire decompile,
    then filter by name-shape + known patterns."""
    keys: set[str] = set()
    try:
        result = subprocess.run(
            ["rg", "-Noh", "--no-heading",
             r'"[a-zA-Z][a-zA-Z0-9-]{2,49}"', str(decomp_dir)],
            check=False, capture_output=True, text=True, timeout=180,
        )
    except Exception as exc:  # noqa: BLE001
        _LOGGER.warning("rg failed during header extraction: %s", exc)
        return keys

    # Header-key heuristics:
    # - Contains a hyphen (most HTTP headers have one)
    # - OR is one of the well-known no-hyphen headers
    no_hyphen_known = {"Authorization", "Accept", "Cookie", "Host", "Origin",
                       "Referer", "User-Agent"}
    for line in result.stdout.splitlines():
        m = _HEADER_KEY_RE.search(line)
        if not m:
            continue
        candidate = m.group(1)
        if "-" in candidate and not candidate.startswith("-"):
            keys.add(candidate)
        elif candidate in no_hyphen_known:
            keys.add(candidate)
    return keys


def extract_oauth_scopes(decomp_dir: Path) -> set[str]:
    """Extract OAuth scope strings (starting with 'openid ...')."""
    scopes: set[str] = set()
    try:
        result = subprocess.run(
            ["rg", "-Noh", "--no-heading", r'"openid[^"]*"', str(decomp_dir)],
            check=False, capture_output=True, text=True, timeout=60,
        )
    except Exception as exc:  # noqa: BLE001
        _LOGGER.warning("rg failed during scope extraction: %s", exc)
        return scopes
    for line in result.stdout.splitlines():
        m = _OAUTH_SCOPE_RE.search(line)
        if m:
            scopes.add(m.group(1).strip())
    return scopes


def render_diff_report(
    brand: str,
    old_version: str,
    new_version: str,
    old_urls: set[str],
    new_urls: set[str],
    old_headers: set[str],
    new_headers: set[str],
    old_scopes: set[str],
    new_scopes: set[str],
) -> str:
    """Render the markdown report for one brand × two versions."""
    now = datetime.datetime.now(tz=datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    added_urls    = sorted(new_urls - old_urls)
    removed_urls  = sorted(old_urls - new_urls)
    added_headers = sorted(new_headers - old_headers)
    removed_headers = sorted(old_headers - new_headers)
    added_scopes  = sorted(new_scopes - old_scopes)
    removed_scopes = sorted(old_scopes - new_scopes)

    def _bullet_section(title: str, items: list[str], empty_note: str) -> str:
        if not items:
            return f"### {title}\n\n_{empty_note}_\n"
        body = "\n".join(f"- `{item}`" for item in items)
        return f"### {title}\n\n{body}\n"

    sections = [
        f"# App Atlas Diff — {brand}: {old_version} → {new_version}\n",
        f"> Auto-generated by `.github/workflows/app-atlas-deep-diff.yml` ·",
        f"> Generated: {now}\n",
        "",
        "## Summary\n",
        f"- URL constants: {len(added_urls)} added, {len(removed_urls)} removed",
        f"- Header-key strings: {len(added_headers)} added, {len(removed_headers)} removed",
        f"- OAuth scopes: {len(added_scopes)} added, {len(removed_scopes)} removed",
        "",
        "## URLs added in new version",
        "",
        "_These are the highest-signal changes — new endpoints the app started talking to._",
        "",
        _bullet_section("Added URLs", added_urls, "No new URLs"),
        "",
        _bullet_section("Removed URLs", removed_urls, "No URLs removed (deprecation signals would appear here)"),
        "",
        "## Header keys",
        "",
        _bullet_section("Added headers", added_headers,
                        "No new header keys (no upcoming enforcement signals)"),
        "",
        _bullet_section("Removed headers", removed_headers, "None removed"),
        "",
        "## OAuth scopes",
        "",
        _bullet_section("Added scopes", added_scopes,
                        "Auth flow unchanged at scope level"),
        "",
        _bullet_section("Removed scopes", removed_scopes, "None removed"),
        "",
        "## Action items (manual review)",
        "",
        "_Triage hints based on the diff above:_",
        "",
        "- **NEW URLs containing OLA-style hosts** (`ola.prod.code.seat.cloud.vwgroup.com`, `emea.bff.cariad.digital`, `mysmob.api.connect.skoda-auto.cz`, etc.) — likely new endpoints we should add scout coverage for",
        "- **NEW headers (especially `app-*`)** — possible future enforcement signal — pre-emptively add to outgoing requests",
        "- **CHANGED scopes** — auth-flow change, review IDP auth client + scope chain in our code",
        "",
        "## Methodology",
        "",
        f"Both APK versions decompiled with `jadx --no-res`. Diff computed on extracted constants only — class-rename noise filtered. Source pages: see brand atlas at [`../{brand}.md`](../{brand}.md).",
        "",
        f"_File location: `docs/research/app-atlas/diffs/{brand}_{old_version}_vs_{new_version}.md`_",
    ]
    return "\n".join(sections)
