#!/usr/bin/env python3
# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Watch the EU Data Act portal data-dictionary page for a new version.

The official SVK DataDictionary PDFs live behind the portal operator's page:
  https://eu-data-act.drivesomethinggreater.com/content/euda/de/de/service/data-dictionary

The actual PDF downloads are JS-triggered and login-gated, so they have no stable
public URL a CI runner can fetch — automated *download* is not possible. What we
CAN do: fetch the public page, look for any version/filename/change signal, and
compare it to a committed baseline (``docs/eu_data_act_source.lock``). When
anything changes, the workflow opens an issue so a human pulls the fresh PDFs and
re-runs ``scripts/build_eu_data_dict_doc.py``.

Signals checked (best-effort, in order of confidence):
  1. any ``SVK_DataDictionary_V<x>`` filename exposed in the HTML,
  2. any ``Version: <x>`` / date string,
  3. a sha256 of the normalised page HTML (catches structural/content changes).

Exit code is always 0; the ``changed`` verdict is written to ``$GITHUB_OUTPUT``
(and printed) so the workflow can decide whether to open an issue.

Usage:
  py scripts/check_eu_data_dict.py                # check, report changed=true/false
  py scripts/check_eu_data_dict.py --update-lock  # accept current state as baseline
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import urllib.request
from pathlib import Path

URL = "https://eu-data-act.drivesomethinggreater.com/content/euda/de/de/service/data-dictionary"
LOCK = Path(__file__).resolve().parents[1] / "docs" / "eu_data_act_source.lock"
_UA = "vwgroup-connect-ha eu-data-dict-watch (+https://github.com/its-me-prash/vwgroup-connect-ha)"


def _fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310 — fixed https URL
        return resp.read().decode("utf-8", errors="replace")


_DAM = "https://eu-data-act.drivesomethinggreater.com/content/dam/datahub/pdf/data-dictionary"


def _signals(html: str) -> dict[str, object]:
    # The AEM page embeds the DAM asset name (date-prefix + version), e.g.
    # ``251022_01_SVK_DataDictionary_V4.0_Continous_Data.pdf`` — and that DAM
    # asset is publicly downloadable (verified: HTTP 200, application/pdf, no
    # login). So a new dictionary is fully detectable AND fetchable here. Pull
    # the date-prefix + version, then build both direct download URLs (VW's own
    # inconsistent naming: ``_Continous_Data.pdf`` vs ``_Historical Data.pdf``).
    stems = sorted(set(re.findall(r"(\d{6}_\d+)_SVK_DataDictionary_V([\d.]+)", html)))
    urls: dict[str, str] = {}
    if stems:
        prefix, version = stems[0]  # newest exposed on the page
        base = f"{_DAM}/{prefix}_SVK_DataDictionary_V{version}"
        urls = {
            "continuous": f"{base}_Continous_Data.pdf",
            "historical": f"{base}_Historical%20Data.pdf",
            "version": version,
            "prefix": prefix,
        }
    # strip volatile bits (nonces, build hashes, csrf, cache-busters) before
    # hashing so a cosmetic redeploy doesn't false-trigger the content hash.
    norm = re.sub(r'(nonce|csrf|build|hash|_v=|\??v=)[^"\'\s]*', "", html, flags=re.I)
    norm = re.sub(r"\s+", " ", norm)
    return {
        "svk_versions": sorted({v for _, v in stems}),
        "download_urls": urls,
        "page_sha256": hashlib.sha256(norm.encode("utf-8")).hexdigest(),
    }


def _emit(changed: bool, summary: str) -> None:
    print(("CHANGED — " if changed else "unchanged — ") + summary)
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a", encoding="utf-8") as fh:
            fh.write(f"changed={'true' if changed else 'false'}\n")
            # multiline-safe summary output
            fh.write("summary<<EOF\n" + summary + "\nEOF\n")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--update-lock", action="store_true")
    args = ap.parse_args()

    try:
        html = _fetch(URL)
    except Exception as exc:  # noqa: BLE001
        _emit(False, f"could not fetch the source page ({type(exc).__name__}: {exc}); skipping this run")
        return 0

    now = _signals(html)
    base = json.loads(LOCK.read_text(encoding="utf-8")) if LOCK.exists() else {}

    if args.update_lock or not base:
        LOCK.parent.mkdir(parents=True, exist_ok=True)
        LOCK.write_text(json.dumps(now, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        _emit(False, f"baseline written: SVK version(s) {now['svk_versions'] or 'none exposed'}, sha {now['page_sha256'][:12]}")
        return 0

    urls = now.get("download_urls") or {}
    # expose the fresh download URLs to the workflow (so it can auto-fetch+regen)
    gh_out = os.environ.get("GITHUB_OUTPUT")
    if gh_out and urls:
        with open(gh_out, "a", encoding="utf-8") as fh:
            fh.write(f"version={urls.get('version','')}\n")
            fh.write(f"continuous_url={urls.get('continuous','')}\n")
            fh.write(f"historical_url={urls.get('historical','')}\n")

    diffs = []
    if now["svk_versions"] != base.get("svk_versions"):
        diffs.append(f"SVK version: {base.get('svk_versions')} -> {now['svk_versions']}  (NEW DICTIONARY VERSION)")
    if now["download_urls"] != base.get("download_urls"):
        diffs.append(f"download URLs changed -> {json.dumps(urls)}")
    if now["page_sha256"] != base.get("page_sha256"):
        diffs.append(f"page content hash changed ({base.get('page_sha256','?')[:12]} -> {now['page_sha256'][:12]})")

    if diffs:
        summary = ("The EU Data Act data-dictionary page changed — a new SVK DataDictionary "
                   "is likely published. The workflow will auto-download the fresh PDFs from the "
                   "public DAM URLs and regenerate `docs/EU_DATA_ACT_DATA_DICTIONARY.md` into a PR. "
                   "Source: " + URL + "\n\nDetected:\n- " + "\n- ".join(diffs))
        _emit(True, summary)
    else:
        _emit(False, f"no change (sha {now['page_sha256'][:12]})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
