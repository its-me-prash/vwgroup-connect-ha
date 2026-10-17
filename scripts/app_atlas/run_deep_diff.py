#!/usr/bin/env python3
# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
"""Phase A.3 orchestrator — run a deep diff for one brand × two versions.

Usage:
    python scripts/app_atlas/run_deep_diff.py \
        --brand cupra \
        --old-version 2.15.0 \
        --new-version 2.16.0

Run by hand. There was a ``workflow_dispatch`` workflow for this until
2026-10-17; it was removed because the APK comes from Google Play via
``apkeep``, which is deliberately absent from the runners (signing a
disposable store account in from a shared CI address gets it locked), so
a dispatch could never get past the fetch. It would not belong on a
schedule either — a jadx full decompile is far too heavy for one.

Output: writes
``docs/research/app-atlas/diffs/{brand}_{old}_vs_{new}.md`` and exits.
The workflow then commits + opens a PR.

Note: Google Play serves only the current build, so this orchestrator
resolves BOTH versions to that one build. For older versions it falls
back gracefully — the diff report just shows "(could not fetch old
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
    p.add_argument("--package-id",
                   help="Override the Play package id (default: read from config.json).")
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
    package_id = args.package_id or brand_cfg.get("package_id")
    if not package_id:
        _LOGGER.error("Brand %s has no package_id — cannot fetch APK",
                      args.brand)
        return 2

    _DIFFS_DIR.mkdir(parents=True, exist_ok=True)

    # NOTE: Google Play serves only the current build; there is no
    # version-pinned download on that channel at all. Fetching an older
    # build would mean a different source, which this pipeline no longer
    # has — so for now both decompiles run against the current build, and
    # the report says so rather than implying a real cross-version diff.
    _LOGGER.info("Starting deep-diff for %s: %s → %s",
                 args.brand, args.old_version, args.new_version)

    with tempfile.TemporaryDirectory(prefix="atlas_diff_") as td:
        tmp_dir = Path(td)
        old_decomp = tmp_dir / "old_decomp"
        new_decomp = tmp_dir / "new_decomp"

        # First decompile: the OLD version. (Currently this resolves to
        # the current build — see the note above.)
        _LOGGER.info("Decompiling 'old' version %s...", args.old_version)
        if not download_and_decompile(args.brand, package_id, tmp_dir, old_decomp):
            _LOGGER.error("Failed to fetch+decompile old version — aborting")
            return 1

        # Second decompile: NEW version. This is the same APK, since Play
        # serves one build. Realistically this section produces a real diff
        # only once a version-pinned fetch exists. For MVP, we still write a
        # report noting "both versions resolved to same APK" if old==new
        # findings.
        _LOGGER.info("Decompiling 'new' version %s...", args.new_version)
        if not download_and_decompile(args.brand, package_id, tmp_dir, new_decomp):
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
