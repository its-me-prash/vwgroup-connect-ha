#!/usr/bin/env python3
# Copyright 2026 Prash Balan (@its-me-prash) — Apache License 2.0
"""APK extraction module — Phase A.2.

Builds on Phase A.1's version polling. When a version changes, this
module:

1. Downloads the APK (or XAPK split-bundle) from APKCombo's R2 CDN
2. Unpacks XAPK → base APK if needed
3. Decodes the APK via ``apktool`` to extract AndroidManifest + smali
4. Greps the decoded output for HTTP-related patterns (header names,
   endpoint hosts, URL constants) per ``config.json:search_patterns``
5. Returns a discovery dict ready to be merged into the per-brand
   atlas markdown

The actual atlas markdown rendering happens in ``build_atlas.py`` —
this module just produces the data.

CI requirements:
- ``apktool`` on PATH (ubuntu-latest has it pre-installed via apt or
  the workflow can `apt-get install apktool` in ~10s)
- ``unzip``, ``find``, ``grep`` (pre-installed)
- Python stdlib only — no extra pip deps

Phase A.3 will add ``jadx`` decompile + semantic-diff between
consecutive versions; that lives in a separate module.
"""

from __future__ import annotations

import datetime
import logging
import re
import subprocess
import urllib.error
import urllib.request
import zipfile
from pathlib import Path
from typing import Any

_LOGGER = logging.getLogger("app_atlas.apk")

# v Phase A.2 fix 2026-05-25: APKCombo's `/download/apk` page is more
# strictly Cloudflare-protected than its plain version-name page. The
# desktop User-Agent that worked for version-name polling gets HTTP
# 403 on the download page from GitHub Actions IPs. Pivoting to a
# mobile UA + a fuller browser-headers set unblocks most CI runs —
# Cloudflare's bot-heuristics are friendlier to "user on mobile data
# without JS" requests because mobile clients are higher-noise.
_UA = (
    "Mozilla/5.0 (Linux; Android 14; Pixel 7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36"
)
_BROWSER_HEADERS: dict[str, str] = {
    "User-Agent": _UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.7,de;q=0.3",
    "Accept-Encoding": "gzip, deflate",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
}
_PAGE_TIMEOUT = 30
_DOWNLOAD_TIMEOUT = 300  # Big files; allow generous timeout for slow CDN.

# Regex to extract the APKCombo signed-CDN URL from a download page.
# Pattern matches links like /r2?u=https%3A%2F%2F... or direct
# https://apks.<hash>.r2.cloudflarestorage.com/... .
_R2_LINK_RE = re.compile(r'href="(/r2\?u=[^"]+)"')


def fetch(url: str, timeout: int = _PAGE_TIMEOUT) -> bytes:
    """GET a URL with browser-like headers; return raw bytes.

    v Phase A.2 fix: uses mobile UA + full browser-header set
    (`_BROWSER_HEADERS`) to maximize chance of bypassing Cloudflare's
    bot-heuristic on GitHub-Actions runner IPs. May still get 403 on
    persistent blocks — caller is expected to log and continue.
    """
    req = urllib.request.Request(url, headers=_BROWSER_HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        # Handle gzip-encoded responses (we requested Accept-Encoding: gzip).
        body = resp.read()
        if resp.headers.get("Content-Encoding") == "gzip":
            import gzip
            body = gzip.decompress(body)
        return body


def fetch_text(url: str) -> str:
    """GET a URL; return text body."""
    return fetch(url).decode("utf-8", errors="replace")


def resolve_apkcombo_download(slug: str) -> str | None:
    """Walk the APKCombo download page to find the R2-signed CDN URL.

    ``slug`` is e.g. ``"my-cupra-app/com.cupra.mycupra"``. Returns the
    fully-resolved download URL (XAPK or APK) or None on failure.
    """
    page_url = f"https://apkcombo.com/{slug}/download/apk"
    try:
        body = fetch_text(page_url)
    except urllib.error.HTTPError as exc:
        _LOGGER.warning("APKCombo %s → HTTP %s", page_url, exc.code)
        return None
    m = _R2_LINK_RE.search(body)
    if not m:
        _LOGGER.warning("APKCombo %s: no R2 link found", page_url)
        return None
    relative = m.group(1)
    # APKCombo's /r2 endpoint just redirects to the actual R2 URL.
    # urllib follows 301/302 automatically.
    return f"https://apkcombo.com{relative}"


# Uptodown embeds a per-download token in the download button's data-url;
# the file is served from dw.uptodown.net/dwn/<token>.
_UPTODOWN_TOKEN_RE = re.compile(
    r'id="detail-download-button"[^>]*data-url="([^"]+)"'
)


def resolve_uptodown_download(subdomain: str) -> str | None:
    """Resolve the direct APK/XAPK URL from an Uptodown app subdomain.

    Fallback for brands not served by APKCombo (e.g. Škoda). ``subdomain``
    is e.g. ``"cz-skodaauto-myskoda"``. The ``/android/download`` page carries
    a token in the ``#detail-download-button`` ``data-url``; the file lives at
    ``https://dw.uptodown.net/dwn/<token>``. Returns the URL or None.
    """
    page_url = f"https://{subdomain}.en.uptodown.com/android/download"
    try:
        body = fetch_text(page_url)
    except urllib.error.HTTPError as exc:
        _LOGGER.warning("Uptodown %s → HTTP %s", page_url, exc.code)
        return None
    except Exception as exc:  # noqa: BLE001
        _LOGGER.warning("Uptodown %s → %s", page_url, exc)
        return None
    m = _UPTODOWN_TOKEN_RE.search(body)
    if not m:
        _LOGGER.warning("Uptodown %s: no download token found", page_url)
        return None
    return f"https://dw.uptodown.net/dwn/{m.group(1)}"


def download_to(url: str, dest: Path) -> bool:
    """Download a URL to ``dest`` using browser-like headers.

    Returns True on success. For large files (APKs), streams to disk
    to avoid loading 100MB+ into memory.
    """
    try:
        req = urllib.request.Request(url, headers=_BROWSER_HEADERS)
        with urllib.request.urlopen(req, timeout=_DOWNLOAD_TIMEOUT) as resp:
            # Stream to disk in 1 MB chunks.
            with dest.open("wb") as f:
                while True:
                    chunk = resp.read(1024 * 1024)
                    if not chunk:
                        break
                    f.write(chunk)
        return True
    except Exception as exc:  # noqa: BLE001
        _LOGGER.error("Download failed (%s): %s", url[:80], exc)
        return False


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

    Guard against decoy downloads: some mirrors (Uptodown) gate the real file
    and serve their own client app instead. Binary AXML stores strings as
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
    import shutil
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


def extract_brand_apk(brand: str, brand_cfg: dict[str, Any],
                     search_patterns: dict[str, Any],
                     tmp_dir: Path) -> dict[str, Any] | None:
    """End-to-end pipeline for one brand: download → unpack → decode → grep.

    Returns the findings dict, or None if any step failed. Cleans up
    transient files (APK + decoded dir) on success or failure — only
    the findings dict is retained.
    """
    sources = brand_cfg.get("sources", {})
    apkcombo_slug = sources.get("apkcombo_slug")
    uptodown_sub = sources.get("uptodown_subdomain")
    if not apkcombo_slug and not uptodown_sub:
        _LOGGER.warning("Brand %s: no apkcombo_slug or uptodown_subdomain — "
                       "skipping APK extraction", brand)
        return None

    # 1. Resolve download URL — APKCombo first (XAPK, fast CDN), then fall
    #    back to Uptodown for brands APKCombo doesn't serve (e.g. Škoda).
    download_url = None
    if apkcombo_slug:
        download_url = resolve_apkcombo_download(apkcombo_slug)
    if not download_url and uptodown_sub:
        _LOGGER.info("Brand %s: APKCombo unavailable — trying Uptodown", brand)
        download_url = resolve_uptodown_download(uptodown_sub)
    if not download_url:
        _LOGGER.warning("Brand %s: no download URL via APKCombo or Uptodown", brand)
        return None
    _LOGGER.info("Brand %s: APK download URL resolved", brand)

    # 2. Download.
    apk_path = tmp_dir / f"{brand}.xapk"
    if not download_to(download_url, apk_path):
        return None
    _LOGGER.info("Brand %s: downloaded %d bytes", brand, apk_path.stat().st_size)

    # 3. Unpack XAPK (or copy if it's already a plain APK).
    unpack_dir = tmp_dir / f"{brand}_unpacked"
    base_apk = unpack_xapk(apk_path, unpack_dir)
    if not base_apk:
        return None

    # 3b. Identity guard — confirm the APK actually IS the brand app. Some
    #     mirrors (notably Uptodown) gate downloads and serve their OWN client
    #     app (com.uptodown.*) instead of the requested one. Without this check
    #     we'd silently analyse the wrong app and report bogus findings. Uses
    #     the canonical per-brand package_id from config.json so the guard also
    #     applies to brands fetched via a non-APKCombo source.
    expected_pkg = brand_cfg.get("package_id")
    if expected_pkg and not _apk_declares_package(base_apk, expected_pkg):
        _LOGGER.error("Brand %s: downloaded APK does not declare expected package "
                      "%r — likely a decoy/wrong download (e.g. Uptodown's own "
                      "app). Rejecting.", brand, expected_pkg)
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
    import shutil
    try:
        apk_path.unlink(missing_ok=True)
        shutil.rmtree(unpack_dir, ignore_errors=True)
        shutil.rmtree(decoded_dir, ignore_errors=True)
    except Exception:  # noqa: BLE001
        pass

    return findings
