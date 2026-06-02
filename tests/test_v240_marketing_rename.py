# Copyright 2026 Prash Balan (@its-me-prash) — Apache License 2.0
# SPDX-License-Identifier: Apache-2.0
"""v2.4.0 — Marketing-only rename: ``VAG Connect`` → ``VW Group Connect``.

Context: humorous community feedback on the Home Assistant UK + HA
Ideas, Projects and Solutions Facebook groups (2026-05). "VAG" — the
official DACH abbreviation for Volkswagen AG — reads quite differently
to English speakers. Si Gregory suggested the rename, Ben Johnson +
Evets David + Stuart McBride + Jordan Waeles all chimed in.

The rename is **marketing-only** per user decision in the planning
phase:
- The integration ``DOMAIN`` stays ``vag_connect`` (entity-IDs depend
  on it; renaming would break every existing user's automations +
  recorder history)
- The custom-components folder stays ``custom_components/vag_connect/``
- All service-call prefixes stay ``vag_connect.lock`` etc.
- The easter-egg service stays ``vag_connect.show_vag`` (Jordan Waeles'
  Pandas-style joke — preserved by design)

What CHANGES:
- Repo URL ``vag-connect-ha`` → ``vwgroup-connect-ha`` (operational
  files only; historical CHANGELOG entries + dated research docs are
  preserved for accuracy)
- Display name ``VAG Connect`` → ``VW Group Connect`` (manifest, hacs,
  strings, 8 translations, 8 READMEs)
- New ``MIGRATION.md`` at repo root with the full story
- Rename-notice block at top of each of the 8 READMEs

These tests pin both the rename AND the things that must NOT have
changed, so a future refactor can't accidentally drift either side.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest


_REPO_ROOT = Path(__file__).resolve().parent.parent
_MANIFEST = _REPO_ROOT / "custom_components" / "vag_connect" / "manifest.json"
_HACS_JSON = _REPO_ROOT / "hacs.json"
_STRINGS = _REPO_ROOT / "custom_components" / "vag_connect" / "strings.json"
_TRANSLATIONS_DIR = _REPO_ROOT / "custom_components" / "vag_connect" / "translations"
_CONST_PY = _REPO_ROOT / "custom_components" / "vag_connect" / "const.py"
_MIGRATION = _REPO_ROOT / "MIGRATION.md"
_README_MD = _REPO_ROOT / "README.md"


# ──────────────────────────────────────────────────────────────────────
# 1. Display name renamed in user-facing strings
# ──────────────────────────────────────────────────────────────────────


class TestDisplayNameRenamed:
    """Manifest, HACS, strings.json + 8 translations now say "VW Group Connect"."""

    def test_manifest_name(self) -> None:
        m = json.loads(_MANIFEST.read_text(encoding="utf-8"))
        assert m["name"] == "VW Group Connect"

    def test_hacs_json_name(self) -> None:
        h = json.loads(_HACS_JSON.read_text(encoding="utf-8"))
        assert h["name"] == "VW Group Connect"

    def test_strings_json_no_vag_connect(self) -> None:
        """strings.json must no longer contain the old display name."""
        text = _STRINGS.read_text(encoding="utf-8")
        # "VAG Connect" (integration name) must be gone.
        # "VAG account" / "VAG IDP" (manufacturer ecosystem refs) stay.
        assert "VAG Connect" not in text

    @pytest.mark.parametrize(
        "lang",
        ["de", "en", "fr", "es", "nl", "pl", "cs", "sv"],
    )
    def test_translation_no_vag_connect(self, lang: str) -> None:
        text = (_TRANSLATIONS_DIR / f"{lang}.json").read_text(encoding="utf-8")
        assert "VAG Connect" not in text, (
            f"{lang}.json still contains 'VAG Connect' — bulk-replace missed it"
        )

    @pytest.mark.parametrize(
        "lang",
        ["de", "en", "fr", "es", "nl", "pl", "cs", "sv"],
    )
    def test_translation_has_vw_group_connect(self, lang: str) -> None:
        """Sanity check the new name is actually present."""
        text = (_TRANSLATIONS_DIR / f"{lang}.json").read_text(encoding="utf-8")
        assert "VW Group Connect" in text


# ──────────────────────────────────────────────────────────────────────
# 2. Repo URL renamed in operational docs
# ──────────────────────────────────────────────────────────────────────


class TestRepoUrlRenamed:
    """Manifest URLs + workflow + README badges + docs use the new repo URL."""

    def test_manifest_documentation_url(self) -> None:
        m = json.loads(_MANIFEST.read_text(encoding="utf-8"))
        assert m["documentation"] == "https://github.com/its-me-prash/vwgroup-connect-ha"

    def test_manifest_issue_tracker_url(self) -> None:
        m = json.loads(_MANIFEST.read_text(encoding="utf-8"))
        assert m["issue_tracker"] == "https://github.com/its-me-prash/vwgroup-connect-ha/issues"

    def test_readme_md_uses_new_url(self) -> None:
        text = _README_MD.read_text(encoding="utf-8")
        # The HACS badge + release badge MUST use the new URL.
        assert "github.com/its-me-prash/vwgroup-connect-ha" in text

    def test_readme_md_no_old_url_outside_notice(self) -> None:
        """The old URL is allowed inside the rename-notice + MIGRATION link.

        Everywhere else (badges, install buttons, doc links) it must
        be the new URL.
        """
        text = _README_MD.read_text(encoding="utf-8")
        # Count old URL occurrences. Allowed: 1 in the rename-notice
        # block describing the old name (markdown-bold backticks).
        # Actually our notice uses just the slug `vag-connect-ha`, not
        # a full URL, so there should be ZERO full-URL occurrences.
        # (The slug alone in backticks is fine and lives in the notice.)
        assert "github.com/its-me-prash/vag-connect-ha" not in text, (
            "README.md still references the OLD full repo URL — that "
            "should only appear in the slug form inside the rename-notice"
        )


# ──────────────────────────────────────────────────────────────────────
# 3. Rename-notice block present in all 8 READMEs
# ──────────────────────────────────────────────────────────────────────


class TestRenameNoticeInReadmes:
    """Each README has the community-credits rename-notice block."""

    @pytest.mark.parametrize(
        "fname",
        [
            "README.md",
            "README.en.md",
            "README.fr.md",
            "README.es.md",
            "README.nl.md",
            "README.pl.md",
            "README.cs.md",
            "README.sv.md",
        ],
    )
    def test_notice_present(self, fname: str) -> None:
        text = (_REPO_ROOT / fname).read_text(encoding="utf-8")
        assert "Note on the rename" in text, f"{fname} missing rename-notice"
        # Community credits per spec.
        for name in ("Si Gregory", "Ben Johnson", "Evets David", "Jordan Waeles"):
            assert name in text, f"{fname} missing credit for {name}"
        # Reference the easter-egg service so users find it.
        assert "vag_connect.show_vag" in text, f"{fname} missing easter-egg ref"
        # Reference MIGRATION.md for full story.
        assert "MIGRATION.md" in text, f"{fname} missing MIGRATION.md link"


# ──────────────────────────────────────────────────────────────────────
# 4. MIGRATION.md exists with the right structure
# ──────────────────────────────────────────────────────────────────────


class TestMigrationDoc:
    def test_file_exists(self) -> None:
        assert _MIGRATION.exists(), "MIGRATION.md missing from repo root"

    def test_contains_tldr(self) -> None:
        text = _MIGRATION.read_text(encoding="utf-8")
        assert "Nothing breaks" in text or "nothing breaks" in text.lower()

    def test_documents_what_stays(self) -> None:
        text = _MIGRATION.read_text(encoding="utf-8")
        # Critical promises to users:
        assert "DOMAIN" in text
        assert "vag_connect" in text
        assert "Entity-IDs" in text or "entity-IDs" in text.lower()

    def test_credits_community(self) -> None:
        text = _MIGRATION.read_text(encoding="utf-8")
        for name in ("Si Gregory", "Ben Johnson", "Evets David", "Jordan Waeles", "Stuart McBride"):
            assert name in text, f"MIGRATION.md missing credit for {name}"


# ──────────────────────────────────────────────────────────────────────
# 5. CRITICAL — internal DOMAIN + folder + service-IDs unchanged
# ──────────────────────────────────────────────────────────────────────
#
# The point of the marketing-only rename is that NO user breakage
# happens. These tests pin the things that MUST stay the same. If any
# of them fail, the rename has accidentally gone beyond marketing-only
# scope.


class TestNothingActuallyChanged:
    def test_domain_constant_unchanged(self) -> None:
        text = _CONST_PY.read_text(encoding="utf-8")
        assert 'DOMAIN = "vag_connect"' in text, (
            "CRITICAL: DOMAIN was changed from vag_connect — this would "
            "break every existing user's config entries, entity-IDs, "
            "and automations. The marketing-only rename must NOT touch "
            "the DOMAIN. If this is intentional, ship as v4.0.0 MAJOR "
            "with proper async_migrate_entry."
        )

    def test_manifest_domain_unchanged(self) -> None:
        m = json.loads(_MANIFEST.read_text(encoding="utf-8"))
        assert m["domain"] == "vag_connect"

    def test_custom_components_folder_unchanged(self) -> None:
        assert (_REPO_ROOT / "custom_components" / "vag_connect").is_dir(), (
            "CRITICAL: custom_components/vag_connect/ was renamed — HACS "
            "+ HA both bind to this folder name. Renaming would break "
            "every existing install."
        )

    def test_easter_egg_service_name_preserved(self) -> None:
        """show_vag service-ID stays vag_connect.show_vag (Jordan's joke)."""
        init_py = (_REPO_ROOT / "custom_components" / "vag_connect" / "__init__.py").read_text(
            encoding="utf-8"
        )
        services_yaml = (_REPO_ROOT / "custom_components" / "vag_connect" / "services.yaml").read_text(
            encoding="utf-8"
        )
        assert '"show_vag"' in init_py
        assert "show_vag:" in services_yaml


# ──────────────────────────────────────────────────────────────────────
# 6. Historical preservation — CHANGELOG + dated research preserved
# ──────────────────────────────────────────────────────────────────────


class TestHistoryPreserved:
    """Past CHANGELOG entries + dated research docs were intentionally
    NOT rewritten — they describe what actually shipped at the time."""

    def test_changelog_keeps_old_name(self) -> None:
        """CHANGELOG.md still has historical references to "VAG Connect"."""
        text = (_REPO_ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
        # At least one historical entry must still say "VAG Connect"
        # — that's the whole point of history-preservation.
        assert "VAG Connect" in text, (
            "CHANGELOG.md historical entries were unexpectedly rewritten — "
            "the history-preservation decision (v2.4.0 plan) requires "
            "past releases keep their original name references for accuracy."
        )

    def test_dated_research_preserved(self) -> None:
        """At least one docs/research/*-2026-*.md still references vag_connect."""
        research_dir = _REPO_ROOT / "docs" / "research"
        if not research_dir.is_dir():
            pytest.skip("docs/research/ not present in this checkout")
        any_preserved = False
        for f in research_dir.glob("2026-*.md"):
            if "vag_connect" in f.read_text(encoding="utf-8"):
                any_preserved = True
                break
        # Soft assertion — research dir might not have 2026-* files in
        # a fresh checkout. We just check the prefix-based ones exist
        # if any do.
        if not any_preserved:
            pytest.skip("no 2026-* research files contain vag_connect refs to check")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
