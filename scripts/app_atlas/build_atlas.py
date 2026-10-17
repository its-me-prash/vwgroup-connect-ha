#!/usr/bin/env python3
# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
"""App Atlas builder — Phase A.1 (lightweight version-polling).

Usage:
    python scripts/app_atlas/build_atlas.py [--brand BRAND] [--dry-run]

What this does (Phase A.1):
1. Reads scripts/app_atlas/config.json
2. For each brand: reads its Google Play listing for the current latest
   version-name
3. Compares to .app-atlas-cache.json (committed state)
4. Updates docs/research/app-atlas/{brand}.md with current version
5. Updates docs/research/app-atlas/_summary.md (cross-brand matrix)
6. Updates .app-atlas-cache.json with the new state

Hand-written findings go in scripts/app_atlas/notes/{brand}.{section}.md
(section = flavors | cross-version-diff | action-items) and are folded into
the generated page — writing them into the page itself would be erased by
the next daily run.

Phase A.2 adds: APK download from Google Play (apkeep) + apktool
extraction + grep for OLA headers + endpoint discovery.

Phase A.3: jadx full decompile + constant diff, also run locally. Note
that Google Play serves only the current build, so a diff between two
consecutive versions needs builds already fetched earlier — the channel
cannot fetch an older one on demand.

CI-friendliness:
- Pure stdlib (no external deps for Phase A.1)
- Idempotent: re-runs without version changes are no-ops
- Graceful per-brand failure: one unreadable Play listing doesn't fail
  the whole run
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
_NOTES_DIR      = _REPO_ROOT / "scripts" / "app_atlas" / "notes"
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


# ── Source scraper (Google Play only) ───────────────────────────────
# Google Play is the publisher's own listing and the single source here, for
# versions as for the APK itself (see apk_extractor). The store page exposes
# the version to an anonymous request, so this needs NO account and no token
# in CI.
#
# The mirrors that used to sit behind this (APKMirror, Uptodown, APKCombo) are
# gone deliberately. They are not a current source: a mirror publishes
# whatever it last happened to ingest, so its answer can lag the store by
# weeks or name a build Play no longer serves — and a version that is wrong in
# that direction is worse than no version, because is_downgrade() then has a
# stale ceiling to compare against. Play had also made them redundant on every
# brand that publishes a version at all: it resolved Volkswagen, which the
# mirrors never once did (the cache carried last_version_name=null while the
# watcher dutifully recorded that it had looked, every day).
_PLAY_BASE = "https://play.google.com/store/apps/details?id={pkg}&hl=en&gl=US"

# The version sits in the page's embedded JSON callback data.
#
# TRAP — do not "fix" a missing brand by matching `]]],"<version>",null`. That
# shape is all over the page and looks like the jackpot, but it's review
# metadata: Play records which app version each reviewer was running. Matching
# it yields ~20 hits per page, mostly ancient, and would have the atlas report
# some random reviewer's version as current. The bracket form below is the
# actual version field. Measured 2026-10-17 across the full brand list: six of
# the eight answer (seat 2.23.0, cupra 2.23.0, vw 4.6.4, audi 5.8.1, skoda
# 8.17.0, vw_na 2026.9.29-9674).
#
# The two Porsche packages publish no version on their store listing at all —
# not "Varies with device", just absent. They now report no version and the
# atlas renders the gap, where the mirrors used to supply a number nobody had
# checked against the store. (VW-NA was in that group when the mirrors were
# removed from the APK path; it answers now, so do not take the Porsche gap as
# permanent either — re-measure before building anything on it.)
_PLAY_VERSION_REGEXES = [
    re.compile(r'\[\[\["(\d+\.\d+(?:\.\d+)?(?:[-.]\w+)?)"\]\]'),
    re.compile(r'"softwareVersion"\s*:\s*"(\d+\.\d+(?:\.\d+)?(?:[-.]\w+)?)"'),
]


def _try_google_play(package_id: str) -> str | None:
    url = _PLAY_BASE.format(pkg=package_id)
    try:
        body = _fetch(url)
    except urllib.error.HTTPError as exc:
        _LOGGER.debug("Google Play %s → HTTP %s", url, exc.code)
        return None
    except Exception as exc:  # noqa: BLE001
        _LOGGER.debug("Google Play %s → %s", url, exc)
        return None
    # "Varies with device" is Play's answer for staged/dynamic rollouts. It is
    # not a version — report none rather than record it.
    if "Varies with device" in body:
        _LOGGER.debug("Google Play %s → 'Varies with device'", package_id)
        return None
    for regex in _PLAY_VERSION_REGEXES:
        m = regex.search(body)
        if m:
            return m.group(1)
    return None


def scrape_version(brand: str, package_id: str | None) -> tuple[str | None, str | None]:
    """Read the current version from the brand's Google Play listing.

    Returns ``(version, "google_play")`` on success and ``(None, None)`` when
    Play has no version to give — either because the listing doesn't publish
    one (VW-NA, Porsche) or because the markup moved. ``None`` is the honest
    answer in both cases: the atlas renders the gap, and ``is_downgrade()``
    keeps whatever ceiling the cache already holds instead of being handed a
    mirror's guess.

    This is deliberately single-source. See the comment above ``_PLAY_BASE``
    for why the mirrors were removed rather than kept as a fallback.
    """
    if not package_id:
        _LOGGER.warning("Brand %s: no package_id configured", brand)
        return None, None

    v = _try_google_play(package_id)
    if v:
        return v, "google_play"

    _LOGGER.warning(
        "Brand %s: Google Play published no version for %s", brand, package_id
    )
    return None, None


# ── Version ordering ────────────────────────────────────────────────


def parse_version(value: str) -> tuple[int, ...] | None:
    """``"2026.7.28-9380"`` → ``(2026, 7, 28, 9380)``; ``None`` when the string
    is not purely numeric segments.

    Deliberately refuses rather than guesses. A qualifier like ``3.61.0-beta``
    has no defensible ordering against a plain release, and a comparator that
    invents one is worse than no comparator: it would silently freeze a brand
    on a value it decided was newer.
    """
    tokens = re.split(r"[.\-]", value.strip())
    if not tokens or not all(t.isdigit() for t in tokens):
        return None
    return tuple(int(t) for t in tokens)


def is_downgrade(new: str, old: str) -> bool:
    """True only when both strings parse, share a shape, and ``new`` sorts below.

    The same-length requirement is what keeps this honest across brands: myVW
    numbers releases by date (``2026.7.28-9380``) while the SEAT app uses plain
    semver (``2.20.2``). Comparing across those schemes is meaningless, so a
    brand that changes its numbering is passed through untouched rather than
    being read as a catastrophic downgrade and pinned forever.
    """
    a, b = parse_version(new), parse_version(old)
    if a is None or b is None or len(a) != len(b):
        return False
    return a < b


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


_APK_HEADING = "## Discovered via APK extraction (Phase A.2)"


def _previous_apk_section(brand: str) -> str | None:
    """The APK-findings body already on the brand's page, if any.

The findings cache under ``.app-atlas-apk-cache/`` is gitignored, so it
    never travels with the repository: it persists on whichever machine wrote
    it (entries here go back months) and is simply absent anywhere else. The
    committed page is the only record that travels.

    That did not matter while CI both extracted and rendered in one job. With
    extraction moved to a maintainer's machine, a CI render has no cache at
    all, and handing ``_render_apk_section`` a None would put the "not yet
    run" placeholder where a real extraction record had been — removing
    findings inside a commit titled "refresh app-atlas". No committed page has
    lost anything that way yet, because at the time of writing they all still
    carry the placeholder; this closes the door before the first local run
    fills them.

    So an absent cache means "nothing new to say", not "nothing is known",
    which is the rule the version cache already follows. The carried body
    dates itself (``Last extracted: … for version …``), and nothing is
    appended on the way through, so repeated carries cannot stack up a trail
    of notes.
    """
    page = _ATLAS_DIR / f"{brand}.md"
    if not page.is_file():
        return None
    try:
        body = page.read_text(encoding="utf-8")
    except OSError:
        return None
    start = body.find(_APK_HEADING)
    if start == -1:
        return None
    start += len(_APK_HEADING)
    end = body.find("\n## ", start)
    section = (body[start:] if end == -1 else body[start:end]).strip()
    if not section or section.startswith("_(Empty"):
        return None
    return section


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
    # A cache file this renderer cannot read must count as no findings, not as
    # an empty result. The cache directory accumulates files from whatever tool
    # last wrote it, and some carry a different shape entirely (one held
    # ``{brand, versions, latest}``). Rendered through the lookups below, every
    # field came back None and the page stated "Last extracted: (unknown)"
    # followed by "none of the configured backend hosts found" — a negative
    # finding, printed on a brand whose cache had in fact never been read.
    if not any(k in inner_findings for k in ("extracted_at", "headers", "endpoint_hosts")):
        _LOGGER.warning(
            "APK findings cache has an unrecognised shape (keys: %s) — treating "
            "it as no findings rather than as an empty result",
            sorted(inner_findings)[:6],
        )
        return (
            "_(Empty — Phase A.2 APK extraction not yet run for this "
            "brand, or last attempt failed. See `app_atlas/apk_extractor.py`.)_"
        )
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


# ── Curated notes ───────────────────────────────────────────────────
# Every brand page is rewritten from scratch on each run, so anything
# typed straight into docs/research/app-atlas/{brand}.md survives exactly
# until the next daily poll and is then gone without a trace. Hand-written
# analysis therefore lives beside the config, in
# scripts/app_atlas/notes/{brand}.{section}.md, and the emitter folds it
# back in — the generated page stays generated, and the findings stay.

_NOTE_SECTIONS = ("flavors", "cross-version-diff", "action-items")


def _load_note(brand: str, section: str) -> str | None:
    """Curated markdown for one section of one brand's page, or None.

    ``section`` is one of ``_NOTE_SECTIONS``. A whitespace-only file counts
    as absent, so emptying a note falls back to the generated placeholder
    rather than punching a blank hole into the page.
    """
    p = _NOTES_DIR / f"{brand}.{section}.md"
    if not p.exists():
        return None
    try:
        body = p.read_text(encoding="utf-8").strip()
    except OSError as exc:
        _LOGGER.warning("Brand %s: could not read note %s — %s", brand, p.name, exc)
        return None
    return body or None


def warn_orphan_notes(brand_keys: list[str]) -> list[str]:
    """Return the note files this build will ignore, and log each one.

    A note is picked up by filename alone, so ``porshe.action-items.md`` or
    ``porsche.actions.md`` is not an error anywhere — it is simply never read,
    and the page keeps rendering the placeholder as if nobody had written
    anything. Naming the orphans out loud is what turns that into a typo the
    author can see.
    """
    if not _NOTES_DIR.is_dir():
        return []
    orphans: list[str] = []
    for p in sorted(_NOTES_DIR.glob("*.md")):
        brand, _, section = p.stem.partition(".")
        if brand in brand_keys and section in _NOTE_SECTIONS:
            continue
        orphans.append(p.name)
        _LOGGER.warning(
            "Note %s matches no brand+section — expected {brand}.{%s}.md",
            p.name, "|".join(_NOTE_SECTIONS),
        )
    return orphans


def _note_or(brand: str, section: str, placeholder: str) -> str:
    note = _load_note(brand, section)
    return note if note is not None else placeholder


def _flavors_block(brand: str) -> str:
    """Optional '## Flavors' section — only brands that ship more than one
    package carry one, so it is absent (not empty) for everyone else."""
    note = _load_note(brand, "flavors")
    if note is None:
        return ""
    return f"## Flavors\n\n{note}\n\n"


def _source_label(source_name: str | None, status: str) -> str:
    """How the page names the source behind the version above it.

    A stale brand keeps its last confirmed version *and* the name of whatever
    delivered it. Under a cell headed "responded" that reads as a claim about
    this run, which it is not: the two Porsche rows said "apkcombo" and
    "apkmirror" while carrying a value last confirmed days earlier, and once
    those sources were removed from the code the same cell would have credited
    something this pipeline can no longer even ask. So the retained case now
    says it was retained and keeps the old name as provenance.
    """
    if not source_name:
        return "(no source succeeded)"
    if status == "stale":
        return f"(none responded — value retained from an earlier `{source_name}` reading)"
    return f"`{source_name}`"


def _reading_note(status: str, current_version: str | None, observed: str | None) -> str:
    """The one line on the page that says how much to trust the number above it."""
    if status == "stale":
        return ("| Reading | **Not re-confirmed today** — every source failed, "
                "so this is the last confirmed value, not a fresh one. |")
    if status == "rejected":
        return (f"| Reading | **A source offered `{observed}`**, which sorts below the "
                f"confirmed `{current_version}`. Kept the confirmed one. If the app "
                f"really was rolled back, clear this brand's cache entry to accept it. |")
    return ""


def emit_brand_atlas(brand: str, brand_cfg: dict[str, Any], current_version: str | None,
                    source_name: str | None, cache_entry: dict[str, Any],
                    status: str = "ok", observed: str | None = None) -> None:
    """Write/update docs/research/app-atlas/{brand}.md."""
    display    = brand_cfg["display_name"]
    package    = brand_cfg["package_id"]
    backend    = brand_cfg["expected_backend"]
    ola_known  = brand_cfg.get("ola_enforcement_known", False)
    ola_since  = brand_cfg.get("ola_enforcement_since", "")
    prev_ver   = cache_entry.get("last_version_name", "")
    now        = datetime.datetime.now(tz=datetime.timezone.utc).strftime("%Y-%m-%d")
    fresh_findings = _load_apk_findings(brand)
    apk_section = (
        _render_apk_section(fresh_findings) if fresh_findings
        else _previous_apk_section(brand) or _render_apk_section(None)
    )
    flavors     = _flavors_block(brand)
    diff_section = _note_or(
        brand, "cross-version-diff",
        "_(Empty — Phase A.3 will populate this from full decompile + diff.)_",
    )
    actions_section = _note_or(
        brand, "action-items",
        "_(Auto-flagged by the pipeline when new endpoints / headers / "
        "version-bumps suggest follow-up work.)_",
    )

    src_label = _source_label(source_name, status)
    md = f"""# App Atlas — {display}

> **Auto-generated** by `.github/workflows/app-atlas-builder.yml` ·
> Last refreshed: {now}

## Identity

| Field | Value |
|---|---|
| Android package ID | `{package}` |
| Expected backend | `{backend}` |
| OLA enforcement known? | {'**YES** (since ' + ola_since + ')' if ola_known else 'No (not observed yet)'} |

{flavors}## Source

| Source | Configured value |
|---|---|
| Google Play (only source) | `{package}` |

## Current version

| | |
|---|---|
| Latest version-name | `{current_version or '(fetch failed)'}` |
| Source that responded | {src_label} |
| Previously cached version | `{prev_ver or '(first run)'}` |
| Changed since last run? | {'**YES**' if current_version and current_version != prev_ver else 'No'} |
{_reading_note(status, current_version, observed)}

## Discovered via APK extraction (Phase A.2)

{apk_section}

## Cross-version diff

{diff_section}

## Action items

{actions_section}

---

_See [`README.md`](README.md) for atlas methodology and
[`LEGAL.md`](LEGAL.md) for reverse-engineering disclosure._
"""
    (_ATLAS_DIR / f"{brand}.md").write_text(md, encoding="utf-8")


def emit_summary(config: dict[str, Any], results: dict[str, str | None],
                 sources_used: dict[str, str | None],
                 statuses: dict[str, str] | None = None) -> None:
    """Write docs/research/app-atlas/_summary.md — cross-brand matrix."""
    now = datetime.datetime.now(tz=datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    statuses = statuses or {}
    rows: list[str] = []
    for brand, cfg in config["brands"].items():
        version = results.get(brand) or "(fetch failed)"
        # A version carried over from an earlier run reads exactly like a fresh
        # one in a table, which is how a stale number gets quoted as current.
        # The same goes for the Source column: it is headed by what answered,
        # so a retained row must not print the name of a source that was never
        # asked. The two Porsche rows read `apkmirror` / `apkcombo` here while
        # carrying a value last confirmed days earlier, and once those sources
        # were removed the same cell would have named something this pipeline
        # can no longer ask at all.
        status = statuses.get(brand, "ok")
        if status == "stale":
            version += " (not re-confirmed)"
        elif status == "rejected":
            version += " (kept; an older reading was rejected)"
        name = sources_used.get(brand)
        if not name:
            src = "—"
        elif status == "stale":
            src = f"(retained from `{name}`)"
        else:
            src = f"`{name}`"
        ola_flag = "" if cfg.get("ola_enforcement_known") else ""
        rows.append(
            f"| **{cfg['display_name']}** | `{cfg['package_id']}` | "
            f"`{version}` | {src} | `{cfg['expected_backend']}` | {ola_flag} |"
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
        "../../../.github/workflows/app-atlas-builder.yml)) reads the Google\n"
        "Play listing of each VAG-brand Android app for its latest\n"
        "version-name. Play is the only source: a mirror serves whatever it\n"
        "last ingested, which can lag the store by weeks, so a brand Play\n"
        "does not publish a version for is reported as a gap rather than\n"
        "filled in from elsewhere.\n\n"
        "That job polls versions and nothing else. The APK download and the\n"
        "extraction on top of it (phases A.2 and A.3 below) are run by a\n"
        "maintainer locally and only their findings are committed, because\n"
        "the Play download needs a disposable store account and signing one\n"
        "in repeatedly from a shared runner address gets it locked. So a\n"
        "green daily run means the versions were checked, not that the APKs\n"
        "were re-extracted; each page dates its own extraction record.\n\n"
        "**Phase progression**:\n\n"
        "- **A.1**: version-polling. Confirms which apps exist and tracks\n"
        "  their version cadence. Runs daily in CI.\n"
        "- **A.2**: APK download + string-pattern grep. Run locally.\n"
        "- **A.3**: full decompile via jadx + constant diff. Run locally.\n\n"
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
                        "the version-name changed since last cache. Needs apkeep "
                        "and apktool on PATH, and takes ~30s-2min per changed "
                        "brand. This is a LOCAL step — the scheduled workflow "
                        "polls versions only, because the Play fetch signs in "
                        "with a disposable account and doing that from a shared "
                        "runner IP gets the account locked.")
    p.add_argument("--force-extract", action="store_true",
                   help="Phase A.2 override: extract APKs for ALL brands "
                        "regardless of version-change cache state. Use this to "
                        "(re)build the apk-cache from scratch — e.g. after adding "
                        "a new brand, or for the initial population. Implies "
                        "--with-apk-extraction, so the same local-only note "
                        "applies, for every brand rather than the changed ones.")
    args = p.parse_args(argv)
    # --force-extract implies --with-apk-extraction.
    if args.force_extract:
        args.with_apk_extraction = True

    config = json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
    warn_orphan_notes(list(config["brands"].keys()))
    cache = load_cache()
    cache.setdefault("brands", {})

    # Seeded from the cache, not empty. emit_summary() rewrites the whole
    # cross-brand table from these three dicts, so with a `--brand X` run only
    # X ever landed in them and the other seven rows were rendered from a
    # missing key — printing "(fetch failed)" and an em dash for brands that
    # had not been asked anything. The README offers `--brand audi` as the way
    # to debug one brand, so that quietly blanked seven rows of the committed
    # summary. A brand this run does not touch now keeps what was last known
    # about it.
    results: dict[str, str | None] = {}
    sources_used: dict[str, str | None] = {}
    statuses: dict[str, str] = {}
    for _brand, _entry in cache["brands"].items():
        if _brand not in config["brands"]:
            continue
        results[_brand] = _entry.get("last_version_name")
        sources_used[_brand] = _entry.get("last_source")
        # Not "ok": nothing was confirmed for this brand in this run. "stale"
        # is exactly what the table should say about a carried-over row.
        statuses[_brand] = "stale" if _entry.get("last_version_name") else "ok"
    changed_brands: list[str] = []

    target_brands = [args.brand] if args.brand else list(config["brands"].keys())
    for brand in target_brands:
        if brand not in config["brands"]:
            _LOGGER.error("Unknown brand %r — check config.json", brand)
            continue
        brand_cfg = config["brands"][brand]
        # The package ID is the whole identity of a brand here: Play is keyed by
        # it, and so is the APK fetch. A brand without one cannot be polled.
        package_id = brand_cfg.get("package_id")
        if not package_id:
            _LOGGER.warning("Brand %s has no package_id configured — skipping", brand)
            results[brand] = None
            sources_used[brand] = None
            continue

        observed, observed_src = scrape_version(brand, package_id)
        prev_entry = cache["brands"].get(brand, {})
        # `or ""` rather than a .get default: a cache entry written by an older
        # build carries an explicit null, and `.get(key, "")` returns that null
        # rather than the default, which used to render the brand as a
        # first-ever run and report a spurious version change.
        prev_ver = prev_entry.get("last_version_name") or ""
        prev_src = prev_entry.get("last_source")

        # A scrape reports one of three things, and only one of them is new
        # knowledge about the app. Treating all three as "the current version"
        # is how a failed fetch erased a known-good version-name, and how a
        # mirror serving an older listing walked a brand backwards.
        current, src, status = observed, observed_src, "ok"
        if observed is None and prev_ver:
            # Every source failed. That says something about the sources, not
            # about the app — so keep what we last confirmed and mark it as
            # not re-confirmed rather than forgetting it.
            current, src, status = prev_ver, prev_src, "stale"
        elif observed and prev_ver and is_downgrade(observed, prev_ver):
            # Apps do get pulled and re-released, so this is not impossible —
            # but a single scrape is not enough to conclude it, and the page
            # carries several version-shaped strings that are NOT the current
            # one. Keep the confirmed value and make the rejected reading
            # visible so a human can override it.
            current, src, status = prev_ver, prev_src, "rejected"

        results[brand] = current
        sources_used[brand] = src
        statuses[brand] = status

        if status == "stale":
            _LOGGER.warning("STALE %s: every source failed — keeping %s", brand, prev_ver)
            # print(), not the logger: a workflow command is only recognised
            # when it starts the line, and the log format prefixes it.
            print(f"::warning title=App Atlas::{brand}: every source failed; "
                  f"keeping the last confirmed version {prev_ver}", flush=True)
        elif status == "rejected":
            _LOGGER.warning("REJECTED %s: %s sorts below confirmed %s — keeping %s",
                            brand, observed, prev_ver, prev_ver)
            print(f"::warning title=App Atlas::{brand}: a source offered {observed}, "
                  f"which is older than the confirmed {prev_ver}; kept {prev_ver}",
                  flush=True)
        elif current and current != prev_ver:
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
                # Extraction is best-effort and must never take the poll with
                # it. It reaches the network and shells out to apkeep/apktool,
                # so it can raise for reasons that have nothing to do with this
                # brand — and an exception here used to abort main() for every
                # brand still in the loop, leaving the run with nothing written
                # at all. That is not theoretical: between 2026-10-13 and
                # 2026-10-17 the daily workflow failed five times in a row on
                # an unresolvable mirror host (URLError from a DNS lookup),
                # while Play was answering for six brands the whole time.
                try:
                    findings = extract_brand_apk(
                        brand, brand_cfg, config["search_patterns"], tmp_dir,
                    )
                except Exception:  # noqa: BLE001
                    _LOGGER.exception(
                        "Brand %s: APK extraction raised — continuing with "
                        "version polling for the remaining brands", brand,
                    )
                    findings = None
                if findings:
                    _save_apk_findings(brand, findings, current)
                    _LOGGER.info("Brand %s: APK extraction OK — %d headers, %d hosts found",
                                 brand, len(findings.get("headers", [])),
                                 len(findings.get("endpoint_hosts", [])))
                else:
                    _LOGGER.warning("Brand %s: APK extraction failed — atlas page will "
                                    "render last-known findings only", brand)

        if not args.dry_run:
            emit_brand_atlas(brand, brand_cfg, current, src, prev_entry,
                             status=status, observed=observed)
            now_iso = datetime.datetime.now(tz=datetime.timezone.utc).isoformat()
            entry: dict[str, Any] = {
                "last_version_name": current,
                "last_source": src,
                "last_checked_at": now_iso,
                # Separate from last_checked_at on purpose: "we looked" and "we
                # got an answer" stopped being the same thing the moment a
                # failed look was allowed to keep the old value.
                "last_confirmed_at": (
                    now_iso if status == "ok"
                    else prev_entry.get("last_confirmed_at")
                ),
                "last_status": status,
            }
            if status == "rejected":
                entry["last_rejected_reading"] = observed
            cache["brands"][brand] = entry

    if not args.dry_run:
        emit_summary(config, results, sources_used, statuses)
        save_cache(cache)

    # The new-OAuth-client_id watch reads the extraction cache, so it has to run
    # wherever extraction runs. It used to be a separate step in the daily
    # workflow, which worked only because that job extracted too; once
    # extraction moved to a maintainer's machine, that step had nothing to read
    # and the watch would have gone quiet without anything saying so. Advisory
    # only — it never fails the run.
    if args.with_apk_extraction and not args.dry_run:
        try:
            try:
                from .diff_known_client_ids import main as _cid_main  # noqa: PLC0415
            except ImportError:
                import sys as _sys  # noqa: PLC0415
                _sys.path.insert(0, str(Path(__file__).parent))
                from diff_known_client_ids import main as _cid_main  # type: ignore[no-redef]
            _cid_main()
            # Delivery is the half that did NOT come along. The workflow step
            # that files the GitHub issue reads a marker inside the gitignored
            # cache, so it can only ever see one written by a run in that same
            # job — never one written here. Until that is wired up, a hit
            # reaches a human only through this terminal, so say so loudly
            # rather than let it scroll past among the per-brand lines.
            marker = _APK_CACHE_DIR / "new-client-ids-found.md"
            if marker.exists():
                _LOGGER.warning(
                    "NEW OAuth client_id(s) found. No issue is filed "
                    "automatically from a local run — the details are above and "
                    "in %s; open the tracker entry by hand.", marker,
                )
        except Exception:  # noqa: BLE001
            _LOGGER.exception("client_id watch failed — the atlas run itself is unaffected")

    print(f"\nSummary: {len(changed_brands)} brand(s) changed: {changed_brands}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
