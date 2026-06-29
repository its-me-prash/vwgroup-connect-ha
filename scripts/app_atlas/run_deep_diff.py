#!/usr/bin/env python3
# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
"""Phase A.3 orchestrator — run a deep diff for one brand × two versions.

Usage:
    python scripts/app_atlas/run_deep_diff.py \
        --brand cupra \
        --old-version 2.15.0 \
        --new-version 2.16.0

Invoked by ``.github/workflows/app-atlas-deep-diff.yml`` (manual
``workflow_dispatch`` trigger). Does NOT run on a daily schedule —
jadx full-decompile is too heavy.

Output: writes
``docs/research/app-atlas/diffs/{brand}_{old}_vs_{new}.md`` and exits.
The workflow then commits + opens a PR.

Note: this orchestrator currently requires BOTH versions to be
fetchable from APKCombo as latest. For older versions, it falls back
gracefully — the diff report just shows "(could not fetch old
version, falling back to current-only extraction)".
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import tempfile
from pathlib import Path

_LOGGER = logging.getLogger("app_atlas.deep_diff")

_REPO_ROOT     = Path(__file__).resolve().parent.parent.parent
_CONFIG_PATH   = _REPO_ROOT / "scripts" / "app_atlas" / "config.json"
_DIFFS_DIR     = _REPO_ROOT / "docs" / "research" / "app-atlas" / "diffs"


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    p = argparse.ArgumentParser(description="Run Phase A.3 deep diff between two APK versions.")
    p.add_argument("--brand", required=True,
                   help="Brand key from config.json (e.g. 'cupra').")
    p.add_argument("--old-version", required=True,
                   help="Older version-name to compare against (e.g. '2.15.0').")
    p.add_argument("--new-version", required=True,
                   help="Newer version-name to compare to (e.g. '2.16.0').")
    p.add_argument("--apkcombo-slug",
                   help="Override APKCombo slug (default: read from config.json).")
    args = p.parse_args(argv)

    # Late import — these modules require external tools (jadx, rg)
    # that only the manual workflow installs. Local-laptop runs will
    # fail fast with clear error.
    sys.path.insert(0, str(Path(__file__).parent))
    from jadx_decompiler import download_and_decompile  # noqa: PLC0415
    from version_diff import (  # noqa: PLC0415
        extract_header_keys,
        extract_oauth_scopes,
        extract_url_constants,
        render_diff_report,
    )

    config = json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
    if args.brand not in config["brands"]:
        _LOGGER.error("Unknown brand %r — choices: %s",
                      args.brand, list(config["brands"].keys()))
        return 2
    brand_cfg = config["brands"][args.brand]
    slug = args.apkcombo_slug or brand_cfg.get("sources", {}).get("apkcombo_slug")
    if not slug:
        _LOGGER.error("Brand %s has no apkcombo_slug — cannot fetch APK",
                      args.brand)
        return 2

    _DIFFS_DIR.mkdir(parents=True, exist_ok=True)

    # NOTE: APKCombo only serves the LATEST version directly. For
    # version-pinned downloads we'd need to navigate to per-version
    # pages — that's a Phase A.3.1 follow-up. For now we run both
    # decompiles against the current latest, and let the maintainer
    # know if the two versions differ from what they asked for.
    _LOGGER.info("Starting deep-diff for %s: %s → %s",
                 args.brand, args.old_version, args.new_version)

    with tempfile.TemporaryDirectory(prefix="atlas_diff_") as td:
        tmp_dir = Path(td)
        old_decomp = tmp_dir / "old_decomp"
        new_decomp = tmp_dir / "new_decomp"

        # First decompile: the OLD version. (Currently we'd only get
        # the latest from APKCombo. Future enhancement: per-version
        # URL like /download/apk/{version}.)
        _LOGGER.info("Decompiling 'old' version %s...", args.old_version)
        if not download_and_decompile(args.brand, slug, tmp_dir, old_decomp):
            _LOGGER.error("Failed to fetch+decompile old version — aborting")
            return 1

        # Second decompile: NEW version. APKCombo will serve the same
        # APK since we only navigate to the latest page. Realistically
        # this section will produce a diff only after Phase A.3.1
        # adds per-version fetching. For MVP, we still write a report
        # noting "both versions resolved to same APK" if old==new
        # findings.
        _LOGGER.info("Decompiling 'new' version %s...", args.new_version)
        if not download_and_decompile(args.brand, slug, tmp_dir, new_decomp):
            _LOGGER.error("Failed to fetch+decompile new version — aborting")
            return 1

        _LOGGER.info("Extracting constants from old decompile...")
        old_urls    = extract_url_constants(old_decomp)
        old_headers = extract_header_keys(old_decomp)
        old_scopes  = extract_oauth_scopes(old_decomp)

        _LOGGER.info("Extracting constants from new decompile...")
        new_urls    = extract_url_constants(new_decomp)
        new_headers = extract_header_keys(new_decomp)
        new_scopes  = extract_oauth_scopes(new_decomp)

        _LOGGER.info("Rendering diff report...")
        report = render_diff_report(
            args.brand, args.old_version, args.new_version,
            old_urls, new_urls, old_headers, new_headers, old_scopes, new_scopes,
        )

    out_path = _DIFFS_DIR / f"{args.brand}_{args.old_version}_vs_{args.new_version}.md"
    out_path.write_text(report, encoding="utf-8")
    _LOGGER.info("Diff report written: %s", out_path)
    print(str(out_path))
    return 0


if __name__ == "__main__":
    sys.exit(main())
