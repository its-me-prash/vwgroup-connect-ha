# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The EU-Data-Act dictionary watcher must not open a PR for a cosmetic page
redeploy.

On 2026-08-10 the watch workflow opened PR #1124 ("regenerate EU Data Act data
dictionary (SVK V4.0)") whose only real diff was the extraction date and the
tracked ``page_sha256``. The regenerated dictionary was byte-identical — same SVK
V4.0, same 1141 + 5139 keys. The portal had merely re-published the AEM landing
page (its HTML hash moved); the versioned PDFs were untouched.

Root cause: ``check_eu_data_dict.py`` treated a bare ``page_sha256`` change as a
new-dictionary signal. But the PDFs are versioned in their own filename
(``…_V4.0_…``), so real content can only arrive with a version/URL bump — the page
hash is the wrong trigger. ``_classify`` now splits *trigger* signals (version /
download URLs) from *informational* ones (page hash), and a hash-only change no
longer opens a PR.

The states below are lifted verbatim from ``docs/eu_data_act_source.lock`` before
and after PR #1124, so this test reproduces the exact false-positive.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "check_eu_data_dict.py"
_spec = importlib.util.spec_from_file_location("check_eu_data_dict", _SCRIPT)
assert _spec and _spec.loader
check_eu_data_dict = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(check_eu_data_dict)
_classify = check_eu_data_dict._classify


# ── the real #1124 states ────────────────────────────────────────────────────

_V40_URLS = {
    "continuous": (
        "https://eu-data-act.drivesomethinggreater.com/content/dam/datahub/pdf/"
        "data-dictionary/251022_01_SVK_DataDictionary_V4.0_Continous_Data.pdf"
    ),
    "historical": (
        "https://eu-data-act.drivesomethinggreater.com/content/dam/datahub/pdf/"
        "data-dictionary/251022_01_SVK_DataDictionary_V4.0_Historical%20Data.pdf"
    ),
    "version": "4.0",
    "prefix": "251022_01",
}
_BASE_1124 = {
    "svk_versions": ["4.0"],
    "download_urls": _V40_URLS,
    "page_sha256": "26bfa2517beb4ab453a1ab3ddf6165869f33758b7c2ed20be783dd8b4a456d5f",
}
_NOW_1124 = {
    "svk_versions": ["4.0"],
    "download_urls": _V40_URLS,
    # only this moved — the AEM page was cosmetically re-published
    "page_sha256": "1753253b6702b06a142abd5fb10a7a3636453a85f8a449fa581ff212493c9b5b",
}


def test_1124_cosmetic_page_redeploy_does_not_open_a_pr() -> None:
    """The exact #1124 state: page hash moved, version + URLs identical."""
    should_pr, trigger, info = _classify(_NOW_1124, _BASE_1124)
    assert should_pr is False       # was True before the fix → no-op PR #1124
    assert trigger == []            # nothing warranting a regenerate
    assert len(info) == 1           # the hash change is recorded, not suppressed
    assert "cosmetic" in info[0].lower()


def test_a_new_svk_version_triggers_a_pr() -> None:
    """A real new dictionary bumps the version in the DAM filename."""
    now = {
        "svk_versions": ["4.1"],
        "download_urls": {**_V40_URLS, "version": "4.1"},
        "page_sha256": "ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff",
    }
    should_pr, trigger, info = _classify(now, _BASE_1124)
    assert should_pr is True
    assert any("NEW DICTIONARY VERSION" in t for t in trigger)


def test_a_changed_download_url_triggers_a_pr() -> None:
    """Same version string but a new date-prefix (new asset) must still PR."""
    now = {
        "svk_versions": ["4.0"],
        "download_urls": {**_V40_URLS, "prefix": "260101_02"},
        "page_sha256": _BASE_1124["page_sha256"],
    }
    should_pr, trigger, info = _classify(now, _BASE_1124)
    assert should_pr is True
    assert any("download URLs changed" in t for t in trigger)


def test_identical_signals_are_no_change() -> None:
    should_pr, trigger, info = _classify(_BASE_1124, _BASE_1124)
    assert should_pr is False
    assert trigger == []
    assert info == []


def test_a_real_version_bump_still_reports_the_hash_as_info() -> None:
    """When both change, the PR fires (version) and the hash rides along as info —
    never suppressed, matching the no-suppression spirit of the watcher."""
    now = {
        "svk_versions": ["5.0"],
        "download_urls": {**_V40_URLS, "version": "5.0"},
        "page_sha256": _NOW_1124["page_sha256"],
    }
    should_pr, trigger, info = _classify(now, _BASE_1124)
    assert should_pr is True
    assert trigger and info
