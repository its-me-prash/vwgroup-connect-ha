#!/usr/bin/env python3
# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
"""APK extraction module — Phase A.2.

Builds on Phase A.1's version polling. When a version changes, this
module:

1. Downloads the APK (or XAPK split-bundle) from Google Play, the only
   source (see ``fetch_from_play``)
2. Unpacks XAPK → base APK if needed
3. Decodes the APK via ``apktool`` to extract AndroidManifest + smali
4. Greps the decoded output for HTTP-related patterns (header names,
   endpoint hosts, URL constants) per ``config.json:search_patterns``
5. Returns a discovery dict ready to be merged into the per-brand
   atlas markdown

The actual atlas markdown rendering happens in ``build_atlas.py`` —
this module just produces the data.

Where this runs: on a maintainer's machine, not in the daily workflow.
The Play download signs in with a disposable store account, and repeating
that from a shared CI runner address gets the account locked, so the
scheduled job polls versions only and the findings from a local run are
what gets committed.

Requirements:
- ``apkeep`` on PATH for the Play download; without it this module logs
  and returns None, and the atlas page keeps its last-known findings
- ``apktool`` on PATH for the decode
- ``unzip``, ``find``, ``grep``
- Python stdlib only — no extra pip deps

Phase A.3 adds ``jadx`` decompile + constant diff; that lives in a
separate module and is likewise local.
"""

from __future__ import annotations

import datetime
import json
import logging
import re
import shutil
import subprocess
import time
import urllib.request
import zipfile
from pathlib import Path
from typing import Any

_LOGGER = logging.getLogger("app_atlas.apk")

def unpack_xapk(xapk_path: Path, dest_dir: Path) -> Path | None:
    """Extract a XAPK file (zip-of-APKs) and return the path to the
    base APK inside. Returns None if no base APK found.

    XAPK structure: ``{package}.apk`` is the base; other entries like
    ``config.arm64_v8a.apk`` are split-apks for architecture-specific
    libraries (ignored — we only need the universal base).

    If the input is already a plain APK (not a XAPK), this just copies
    it to ``dest_dir / "base.apk"`` and returns that path.
    """
    if not zipfile.is_zipfile(xapk_path):
        _LOGGER.warning("%s is not a valid zip", xapk_path)
        return None

    dest_dir.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(xapk_path, "r") as zf:
        names = zf.namelist()
        # Heuristic: the base APK is the one named after the package
        # OR the largest .apk file in the bundle (architecture-agnostic).
        apks = [n for n in names if n.endswith(".apk")]
        if not apks:
            # Maybe it's a plain APK — check for AndroidManifest.xml.
            if "AndroidManifest.xml" in names:
                # It IS a plain APK. Copy it.
                target = dest_dir / "base.apk"
                target.write_bytes(xapk_path.read_bytes())
                return target
            _LOGGER.warning("%s has no .apk entries and no AndroidManifest.xml", xapk_path)
            return None

        # Prefer the entry whose name doesn't contain "config." (split-apks)
        base_candidates = [n for n in apks if "config." not in n.lower()]
        if base_candidates:
            base_name = base_candidates[0]
        else:
            # All entries are splits → pick the largest one (most universal).
            base_name = max(apks, key=lambda n: zf.getinfo(n).file_size)

        target = dest_dir / "base.apk"
        with zf.open(base_name) as src:
            target.write_bytes(src.read())
        _LOGGER.info("XAPK %s: extracted base apk %s (%d bytes)",
                     xapk_path.name, base_name, target.stat().st_size)
        return target


def _apk_declares_package(base_apk: Path, expected_pkg: str) -> bool:
    """True if the APK's AndroidManifest contains the expected package name.

    This is what makes an analysed artifact attributable to a brand: every
    finding downstream is reported under this brand's name, so the file has to
    declare the package the config asked for. Binary AXML stores strings as
    UTF-16LE, so a substring scan of AndroidManifest.xml reliably confirms the
    declared package is present.
    """
    try:
        with zipfile.ZipFile(base_apk) as z:
            manifest = z.read("AndroidManifest.xml")
    except (KeyError, zipfile.BadZipFile, OSError) as exc:
        _LOGGER.warning("Could not read AndroidManifest from %s: %s", base_apk, exc)
        return False
    return expected_pkg in manifest.decode("utf-16-le", errors="ignore")


def apktool_decode(apk_path: Path, dest_dir: Path) -> bool:
    """Run ``apktool d <apk> -o <dest>``. Returns True on success."""
    if dest_dir.exists():
        # apktool refuses to overwrite by default.
        shutil.rmtree(dest_dir)
    # Windows: apktool ships as a .BAT/.cmd wrapper — a bare ["apktool", ...] is NOT
    # resolved by CreateProcess (which only finds .exe, not PATHEXT scripts), so it raised
    # FileNotFoundError on local Windows runs. shutil.which() honours PATHEXT and returns the
    # full path to apktool.BAT, which subprocess can execute. On Linux it returns the binary.
    apktool_bin = shutil.which("apktool") or "apktool"
    try:
        result = subprocess.run(
            [apktool_bin, "d", "--force-manifest", "-o", str(dest_dir), str(apk_path)],
            check=False,
            capture_output=True,
            text=True,
            timeout=600,
        )
        if result.returncode != 0:
            _LOGGER.error("apktool failed (rc=%d):\n%s\n%s",
                          result.returncode, result.stdout[-500:], result.stderr[-500:])
            return False
        return True
    except FileNotFoundError:
        _LOGGER.error("apktool not on PATH — workflow needs `apt-get install apktool`")
        return False
    except subprocess.TimeoutExpired:
        _LOGGER.error("apktool timed out after 600s for %s", apk_path)
        return False


def grep_patterns(decoded_dir: Path, search_patterns: dict[str, Any]) -> dict[str, Any]:
    """Search the decoded APK for HTTP-related patterns.

    Returns a discovery dict shaped like:

        {
            "headers": ["app-market", "app-brand", ...],
            "endpoint_hosts": ["ola.prod.code.seat.cloud.vwgroup.com", ...],
            "ola_header_values": {"app-version": "2.16.0", ...},
        }

    Implementation uses ``ripgrep`` if available (10× faster), falls
    back to plain ``grep -r``.
    """
    findings: dict[str, Any] = {
        "headers": [],
        "endpoint_hosts": [],
        "ola_header_values": {},
    }

    if not decoded_dir.is_dir():
        return findings

    # Use ripgrep when available; fall back to grep.
    rg_available = subprocess.run(
        ["which", "rg"], check=False, capture_output=True
    ).returncode == 0
    grep_cmd = ["rg", "-N", "--no-heading", "-i"] if rg_available else ["grep", "-rNih"]

    def _search(pattern: str, limit: int = 30) -> list[str]:
        try:
            result = subprocess.run(
                grep_cmd + ["-e", pattern, str(decoded_dir)],
                check=False, capture_output=True, text=True, timeout=30,
            )
            lines = result.stdout.splitlines()[:limit]
            return [ln.strip() for ln in lines if ln.strip()]
        except Exception:  # noqa: BLE001
            return []

    # 1. OLA-style header keys.
    for key in search_patterns.get("ola_headers", []):
        hits = _search(rf'"{key}"', limit=5)
        if hits:
            findings["headers"].append(key)
            # Try to extract a value-pattern for ``app-version`` specifically:
            # "app-version": "2.16.0" or 'app-version', '2.16.0'
            if key == "app-version":
                for ln in hits:
                    m = re.search(r'"app-version"[\s,:]+"([^"]+)"', ln)
                    if m:
                        findings["ola_header_values"]["app-version"] = m.group(1)
                        break

    # 2. Known backend hosts (substring match).
    for host in search_patterns.get("known_backend_hosts", []):
        hits = _search(re.escape(host), limit=1)
        if hits:
            findings["endpoint_hosts"].append(host)

    # 3. Phase A.5 (v2.5.5) — auth-config secrets discovery.
    # The 2026-05-28 VW Azure WAF migration would have been caught
    # proactively if these patterns had been mined. The bucket finds
    # rotated qmauth values, new token URLs, and rotated header names
    # BEFORE the user-facing 403 cascade hits production.
    auth_secrets_cfg = search_patterns.get("auth_secrets") or {}
    if auth_secrets_cfg:
        auth_findings: dict[str, Any] = {
            "header_names_seen": [],
            "token_path_markers_seen": [],
            "qmauth_constants_seen": [],
            "qmauth_secret_candidates": [],
            "client_id_candidates": [],
        }

        for hdr in auth_secrets_cfg.get("header_names", []):
            if _search(re.escape(hdr), limit=1):
                auth_findings["header_names_seen"].append(hdr)

        for path in auth_secrets_cfg.get("token_path_markers", []):
            if _search(re.escape(path), limit=1):
                auth_findings["token_path_markers_seen"].append(path)

        for name in auth_secrets_cfg.get("qmauth_constants", []):
            hits = _search(re.escape(name), limit=3)
            if hits:
                auth_findings["qmauth_constants_seen"].append(name)
                # Try to extract a quoted value from the same line — the
                # smali decompiler typically emits ``const-string vN, "0x..."``
                # near the constant assignment. Patterns documented in
                # evcc PR #30292: qmSecret = 64-char hex, qmClientId = 8-char hex.
                for ln in hits:
                    # 64-char hex (HMAC secret rotation)
                    m_secret = re.search(
                        r'"([0-9a-fA-F]{64})"', ln,
                    )
                    if m_secret:
                        val = m_secret.group(1).lower()
                        if val not in auth_findings["qmauth_secret_candidates"]:
                            auth_findings["qmauth_secret_candidates"].append(val)
                    # 8-char hex (client id), excluding obvious non-id strings
                    m_clientid = re.search(
                        r'"([0-9a-fA-F]{8})"', ln,
                    )
                    if m_clientid:
                        val = m_clientid.group(1).lower()
                        # Avoid common 8-hex matches like RGBA colours.
                        if (
                            val not in auth_findings["client_id_candidates"]
                            and not val.startswith(("ff", "00", "aa"))
                        ):
                            auth_findings["client_id_candidates"].append(val)

        # Free-form client_id pattern — the @apps_vw-dilab_com suffix is
        # the canonical VAG OAuth client_id marker. Captures the FULL
        # UUID@suffix string for cross-checking against models.py.
        for marker in auth_secrets_cfg.get("client_id_patterns", []):
            hits = _search(re.escape(marker), limit=3)
            for ln in hits:
                m = re.search(
                    r'"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}@apps_vw-dilab_com)"',
                    ln, re.IGNORECASE,
                )
                if m and m.group(1) not in auth_findings["client_id_candidates"]:
                    auth_findings["client_id_candidates"].append(m.group(1))

        findings["auth_secrets"] = auth_findings

    return findings



_AURORA_DISPENSER = "https://auroraoss.com/api/auth"
# The reference script rotates without a limit by default, and records that
# MyŠkoda 8.16.0 needed attempt 18 — a budget of 8 would simply have failed on
# that brand. A cap exists here only so an unattended run cannot spin forever;
# it is set above the worst case that method documents, not below it.
_PLAY_ROTATIONS = 24
_PLAY_SLEEP_S = 4.0

# Three extensions, matching the reference script. apkeep writes a split
# bundle as .xapk or .apks depending on how Play serves it, and counting only
# two of the three made such a download read as "no artifact": the fetch would
# then rotate accounts against a file that was already on disk, and finally
# report failure for a package it had successfully pulled.
_PLAY_ARTIFACT_SUFFIXES = (".apk", ".xapk", ".apks")


def _apks_in(d: Path) -> set[Path]:
    return {p for p in d.iterdir()
            if p.is_file() and p.suffix.lower() in _PLAY_ARTIFACT_SUFFIXES}


def fetch_from_play(package_id: str, brand: str, out_dir: Path) -> Path | None:
    """Pull one package from Google Play via apkeep. Returns the artifact, or None.

    Follows C:/tools/apkget.sh, the standing method in this project, and
    deliberately keeps its two awkward properties rather than tidying them away.
    One thing it does NOT yet carry over: that script takes a minimum version
    and version-code (``APKGET_MIN_VERSION`` / ``APKGET_MIN_CODE``) and rotates
    until the artifact meets them, because a disposable account can land in an
    older rollout cohort. Without that floor, the version a finding is filed
    under comes from the Play listing rather than from the artifact, so it can
    name a build one cohort newer than the file that was actually read.

    1. SUCCESS IS A FILE ON DISK, never an exit code. apkeep can print
       "Downloading ..." and exit 0 having written nothing, when the disposable
       account it was handed is cohort-limited for that package. Trusting the
       exit code is how a build reports a successful extraction of nothing.
    2. FAILURE MEANS ROTATE, not give up. Each attempt takes a fresh throwaway
       account from the Aurora dispenser; the same package often lands on the
       second or third one. That is why there is a loop here and not a single call.

    No account is created and no password is entered: the dispenser hands out a
    disposable {email, auth} pair, which apkeep consumes via --auth-token. The
    token is never logged.

    Returns None when apkeep is not installed, which is the state of the CI
    runner today. The caller treats None as "render last-known findings", so an
    environment without apkeep degrades instead of failing.
    """
    if shutil.which("apkeep") is None:
        _LOGGER.warning(
            "Brand %s: apkeep is not installed — no Play fetch, the atlas page "
            "will render last-known findings", brand,
        )
        return None

    for attempt in range(1, _PLAY_ROTATIONS + 1):
        try:
            req = urllib.request.Request(
                _AURORA_DISPENSER, headers={"User-Agent": "com.aurora.store"},
            )
            with urllib.request.urlopen(req, timeout=25) as resp:
                creds = json.loads(resp.read().decode("utf-8", errors="replace"))
        except Exception as exc:  # noqa: BLE001
            _LOGGER.warning("Brand %s: attempt %d — Aurora dispenser: %s",
                            brand, attempt, exc)
            time.sleep(_PLAY_SLEEP_S)
            continue
        email, auth = creds.get("email", ""), creds.get("auth", "")
        if not email or not auth:
            _LOGGER.warning("Brand %s: attempt %d — dispenser gave no credentials",
                            brand, attempt)
            time.sleep(_PLAY_SLEEP_S)
            continue

        before = _apks_in(out_dir)
        try:
            subprocess.run(
                ["apkeep", "-a", package_id, "-d", "google-play",
                 "--email", email, "--auth-token", auth, "--accept-tos",
                 str(out_dir)],
                capture_output=True, timeout=600, check=False,
            )
        except Exception as exc:  # noqa: BLE001
            _LOGGER.warning("Brand %s: attempt %d — apkeep did not run: %s",
                            brand, attempt, type(exc).__name__)
            time.sleep(_PLAY_SLEEP_S)
            continue
        new = _apks_in(out_dir) - before
        if not new:
            # Not an error and not rate limiting against us: this throwaway
            # account is cohort-limited for this package. Take another one.
            _LOGGER.info("Brand %s: attempt %d — Play returned no artifact for "
                         "this account, rotating", brand, attempt)
            time.sleep(_PLAY_SLEEP_S)
            continue
        got = sorted(new, key=lambda p: p.stat().st_size)[-1]
        _LOGGER.info("Brand %s: Play served %s on attempt %d",
                     brand, got.name, attempt)
        return got

    _LOGGER.warning("Brand %s: %d account rotations exhausted, no artifact",
                    brand, _PLAY_ROTATIONS)
    return None


def extract_brand_apk(brand: str, brand_cfg: dict[str, Any],
                     search_patterns: dict[str, Any],
                     tmp_dir: Path) -> dict[str, Any] | None:
    """End-to-end pipeline for one brand: download → unpack → decode → grep.

    Returns the findings dict, or None if any step failed. Cleans up
    transient files (APK + decoded dir) on success or failure — only
    the findings dict is retained.
    """
    package_id = brand_cfg.get("package_id")
    if not package_id:
        _LOGGER.warning("Brand %s: no package_id — skipping APK extraction", brand)
        return None

    # 1+2. Fetch from Google Play, the only source. The mirrors this used to
    # walk are gone on purpose: they serve whatever they last ingested, which
    # the repository's own history shows lagging by a full minor version, and
    # one of them had also started gating downloads and handing back a
    # different app than the one requested — which is why step 3b exists. An
    # atlas built from a stale or substituted APK is worse than one that
    # renders last-known findings, which is what the caller does when this
    # returns None.
    apk_path = fetch_from_play(package_id, brand, tmp_dir)
    if apk_path is None:
        return None
    _LOGGER.info("Brand %s: fetched %d bytes from Play", brand, apk_path.stat().st_size)

    # 3. Unpack XAPK (or copy if it's already a plain APK).
    unpack_dir = tmp_dir / f"{brand}_unpacked"
    base_apk = unpack_xapk(apk_path, unpack_dir)
    if not base_apk:
        return None

    # 3b. Identity guard — confirm the APK actually IS the brand app. Without
    #     it we would analyse whatever arrived and report the findings under
    #     this brand's name: a substituted app, the wrong split out of an XAPK,
    #     or a mistyped package id all look identical from here. Checked
    #     against the canonical per-brand package_id from config.json, so it
    #     holds whatever the fetch path is.
    expected_pkg = brand_cfg.get("package_id")
    if expected_pkg and not _apk_declares_package(base_apk, expected_pkg):
        _LOGGER.error("Brand %s: downloaded APK does not declare expected "
                      "package %r — wrong or substituted download. Rejecting.",
                      brand, expected_pkg)
        return None

    # 4. apktool decode.
    decoded_dir = tmp_dir / f"{brand}_decoded"
    if not apktool_decode(base_apk, decoded_dir):
        return None
    _LOGGER.info("Brand %s: apktool decode done", brand)

    # 5. Grep patterns.
    findings = grep_patterns(decoded_dir, search_patterns)
    findings["extracted_at"] = datetime.datetime.now(
        tz=datetime.timezone.utc
    ).isoformat()
    findings["xapk_size_bytes"] = apk_path.stat().st_size

    # 6. Cleanup transient files.
    try:
        apk_path.unlink(missing_ok=True)
        shutil.rmtree(unpack_dir, ignore_errors=True)
        shutil.rmtree(decoded_dir, ignore_errors=True)
    except Exception:  # noqa: BLE001
        pass

    return findings
