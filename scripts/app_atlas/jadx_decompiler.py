#!/usr/bin/env python3
# Copyright 2026 Prash Balan (@its-me-prash) — Apache License 2.0
"""jadx full decompile wrapper — Phase A.3.

Phase A.2 used ``apktool`` for fast smali-level extraction. This
module wraps ``jadx`` for full Java-source decompile — much heavier
(5-15min per APK, 100-500MB output) but produces readable Java code.
That's the basis for the cross-version semantic diff in
``version_diff.py``.

This module is NOT called by the daily atlas builder. It's only
invoked from the manual ``app-atlas-deep-diff.yml`` workflow when a
maintainer wants to investigate what semantically changed between
two specific versions of a brand's app.

Hard requirements:
- ``jadx`` on PATH (workflow installs from GitHub release)
- ~2GB free disk (for decompile output across both versions)
- ~15min CI runtime budget per APK
"""

from __future__ import annotations

import logging
import re
import subprocess
from pathlib import Path
from typing import Any

# Reuse the lighter pipeline from Phase A.2 for the download +
# unpack-XAPK steps. The only difference at runtime is the decoder.
from apk_extractor import (
    download_to,
    resolve_apkcombo_download,
    unpack_xapk,
)

_LOGGER = logging.getLogger("app_atlas.jadx")

_JADX_TIMEOUT = 900  # 15 minutes max per decompile.


def jadx_decompile(apk_path: Path, dest_dir: Path) -> bool:
    """Run ``jadx -d <dest> --no-res <apk>``. Returns True on success.

    ``--no-res`` skips resource decoding (faster, we don't need PNGs).
    Errors during decompile are common (jadx can't always handle
    obfuscated code) — those produce partial output which is still
    useful, so we accept non-zero exit codes when output exists.
    """
    if dest_dir.exists():
        import shutil
        shutil.rmtree(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    try:
        result = subprocess.run(
            ["jadx", "-d", str(dest_dir), "--no-res", str(apk_path)],
            check=False,
            capture_output=True,
            text=True,
            timeout=_JADX_TIMEOUT,
        )
        # jadx often exits non-zero on partial failures but still
        # produces useful output. Accept any result where the dest dir
        # has at least one .java file.
        java_files = list(dest_dir.rglob("*.java"))
        if not java_files:
            _LOGGER.error("jadx produced no .java files (rc=%d):\n%s\n%s",
                          result.returncode, result.stdout[-500:], result.stderr[-500:])
            return False
        _LOGGER.info("jadx decompile: %d .java files produced (rc=%d)",
                     len(java_files), result.returncode)
        return True
    except FileNotFoundError:
        _LOGGER.error("jadx not on PATH — workflow needs to install it")
        return False
    except subprocess.TimeoutExpired:
        _LOGGER.error("jadx timed out after %ds for %s", _JADX_TIMEOUT, apk_path)
        # Even on timeout, partial output may exist + be useful.
        return len(list(dest_dir.rglob("*.java"))) > 0


def download_and_decompile(
    brand: str,
    apkcombo_slug: str,
    tmp_dir: Path,
    decomp_dir: Path,
) -> bool:
    """End-to-end: APKCombo download → XAPK unpack → jadx decompile.

    Returns True on success (decomp_dir populated). The downloaded
    APK is cleaned up after decompile; only the decompiled tree
    remains for the caller to analyze.
    """
    download_url = resolve_apkcombo_download(apkcombo_slug)
    if not download_url:
        _LOGGER.error("Brand %s: could not resolve APKCombo URL", brand)
        return False

    apk_path = tmp_dir / f"{brand}.xapk"
    if not download_to(download_url, apk_path):
        return False

    unpack_dir = tmp_dir / f"{brand}_unpacked"
    base_apk = unpack_xapk(apk_path, unpack_dir)
    if not base_apk:
        return False

    if not jadx_decompile(base_apk, decomp_dir):
        return False

    # Cleanup the APK + unpack dir; keep the decomp_dir.
    import shutil
    try:
        apk_path.unlink(missing_ok=True)
        shutil.rmtree(unpack_dir, ignore_errors=True)
    except Exception:  # noqa: BLE001
        pass
    return True
