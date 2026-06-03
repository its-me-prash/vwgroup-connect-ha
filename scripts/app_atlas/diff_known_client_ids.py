# Copyright 2026 Prash Balan (@its-me-prash) - Apache License 2.0
# SPDX-License-Identifier: Apache-2.0
"""Diff client_ids found in the latest APK extraction against the
client_ids we already know about in source.

Output:
- Exit 0 always (advisory; never fails the workflow).
- When a brand-new client_id is detected, writes a markdown summary
  to `.app-atlas-apk-cache/new-client-ids-found.md` and prints it to
  stdout. The app-atlas-builder workflow reads that file and creates
  a GitHub issue tagged `apk-watcher` so we can react quickly when
  VW (or any other brand) ships a fresh OAuth client.
- When no new ids are found, the marker file is removed (so the
  follow-up workflow step can `if: hashFiles(marker) != ''` reliably).

This is intentionally a small, dependency-free script. It runs
inside the existing `app-atlas-builder.yml` workflow as a step
after `build_atlas.py`.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_APK_CACHE = _REPO_ROOT / ".app-atlas-apk-cache"
_MODELS_PY = _REPO_ROOT / "custom_components" / "vag_connect" / "cariad" / "models.py"
_RESOLVER_PY = (
    _REPO_ROOT
    / "custom_components"
    / "vag_connect"
    / "cariad"
    / "auth"
    / "_auth_config_resolver.py"
)
_MARKER_FILE = _APK_CACHE / "new-client-ids-found.md"

# Matches the canonical VAG OAuth client_id shape (UUID@apps_vw-dilab_com).
_CID_RE = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
    r"@apps_vw-dilab_com",
    re.IGNORECASE,
)


def _known_from_source() -> set[str]:
    """Collect every client_id string already wired into source.

    Walks models.py + _auth_config_resolver.py. Cheap regex grep,
    deliberately not importing the modules so this can run during
    CI without setting up the HA path.
    """
    known: set[str] = set()
    for path in (_MODELS_PY, _RESOLVER_PY):
        if not path.is_file():
            continue
        for match in _CID_RE.findall(path.read_text(encoding="utf-8")):
            known.add(match.lower())
    return known


def _candidates_from_cache() -> dict[str, set[str]]:
    """Return brand -> set of client_ids found in the latest APK
    extraction for that brand.
    """
    out: dict[str, set[str]] = {}
    if not _APK_CACHE.is_dir():
        return out
    for json_path in sorted(_APK_CACHE.glob("*.json")):
        try:
            data = json.loads(json_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        brand = data.get("brand") or json_path.stem
        # Cache shape varies across atlas builder iterations. Handle
        # both single-version and multi-version layouts.
        candidates: list[str] = []
        if isinstance(data.get("findings"), dict):
            auth = (data["findings"].get("auth_secrets") or {})
            candidates = list(auth.get("client_id_candidates") or [])
        elif isinstance(data.get("versions"), dict):
            versions = data["versions"]
            if versions:
                latest = max(versions.keys())
                auth = (
                    (versions[latest].get("findings") or {})
                    .get("auth_secrets") or {}
                )
                candidates = list(auth.get("client_id_candidates") or [])
        for cand in candidates:
            if isinstance(cand, str) and _CID_RE.fullmatch(cand):
                out.setdefault(brand, set()).add(cand.lower())
    return out


def main() -> int:
    """Run the diff. Always exit 0 - this is advisory only."""
    known = _known_from_source()
    per_brand = _candidates_from_cache()

    new_per_brand: dict[str, list[str]] = {}
    for brand, cids in per_brand.items():
        new = sorted(cids - known)
        if new:
            new_per_brand[brand] = new

    # Clean up any stale marker from a previous run.
    if _MARKER_FILE.exists():
        try:
            _MARKER_FILE.unlink()
        except OSError:
            pass

    if not new_per_brand:
        print(
            f"No new client_ids found. ({sum(len(v) for v in per_brand.values())} "
            f"candidates checked across {len(per_brand)} brand(s), "
            f"all already wired into source.)"
        )
        return 0

    lines = [
        "## New OAuth client_id(s) detected in latest APK extraction",
        "",
        "The daily app-atlas builder found one or more OAuth client_ids "
        "in a fresh APK that are not yet wired into our source.",
        "",
        "When a brand rotates or adds a client_id, the WAF may pass it "
        "while the old ones get blocked. Worth promoting these into "
        "`_ALTERNATE_CLIENT_IDS` in `_auth_config_resolver.py` so the "
        "chain can fall back to them.",
        "",
        "### Findings",
        "",
    ]
    for brand in sorted(new_per_brand):
        lines.append(f"**{brand}**")
        for cid in new_per_brand[brand]:
            lines.append(f"- `{cid}`")
        lines.append("")
    lines.append("### Next steps")
    lines.append("")
    lines.append(
        "1. Manually verify the candidate is genuinely a new auth "
        "client_id and not a different kind of UUID that happens to "
        "match the pattern."
    )
    lines.append(
        "2. Add it to `_ALTERNATE_CLIENT_IDS[<brand>]` in "
        "`custom_components/vag_connect/cariad/auth/_auth_config_resolver.py`."
    )
    lines.append(
        "3. Bump the manifest version + add a CHANGELOG entry under Fixed."
    )

    marker_body = "\n".join(lines) + "\n"
    _MARKER_FILE.parent.mkdir(parents=True, exist_ok=True)
    _MARKER_FILE.write_text(marker_body, encoding="utf-8")
    print(marker_body)
    return 0


if __name__ == "__main__":
    sys.exit(main())
