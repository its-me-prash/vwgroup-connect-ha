# Copyright 2026 Prash Balan (@its-me-prash) — Apache License 2.0
"""Tests for the Cross-Brand App Atlas pipeline (Phase A.1).

Source-level pins for the scaffolding — no network calls (CI doesn't
need to actually scrape APKMirror/Uptodown to validate the structure).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest


_REPO_ROOT      = Path(__file__).resolve().parent.parent
_CONFIG_PATH    = _REPO_ROOT / "scripts" / "app_atlas" / "config.json"
_SCRIPT_PATH    = _REPO_ROOT / "scripts" / "app_atlas" / "build_atlas.py"
_EXTRACTOR_PATH = _REPO_ROOT / "scripts" / "app_atlas" / "apk_extractor.py"
_WORKFLOW_PATH  = _REPO_ROOT / ".github" / "workflows" / "app-atlas-builder.yml"
_ATLAS_DIR      = _REPO_ROOT / "docs" / "research" / "app-atlas"


# ──────────────────────────────────────────────────────────────────────
# 1. config.json schema + coverage
# ──────────────────────────────────────────────────────────────────────


class TestConfig:
    def test_config_exists_and_parses(self) -> None:
        data = json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
        assert "_atlas_version" in data
        assert "brands" in data
        assert "search_patterns" in data

    def test_all_7_brands_present(self) -> None:
        data = json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
        expected = {
            "seat", "cupra", "volkswagen", "audi",
            "skoda", "volkswagen_na", "porsche",
        }
        assert set(data["brands"].keys()) == expected

    @pytest.mark.parametrize(
        "brand,expected_package",
        [
            ("seat",          "com.seat.myseat.ola"),
            ("cupra",         "com.cupra.mycupra"),
            ("volkswagen",    "com.volkswagen.weconnect"),
            ("audi",          "de.myaudi.mobile.assistant"),
            ("skoda",         "cz.skodaauto.myskoda"),
            ("volkswagen_na", "com.vw.carnet.release"),
            ("porsche",       "com.porsche.one"),
        ],
    )
    def test_package_ids(self, brand: str, expected_package: str) -> None:
        data = json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
        assert data["brands"][brand]["package_id"] == expected_package

    def test_ola_enforcement_flagged_for_seat_cupra_only(self) -> None:
        """Only SEAT + CUPRA have OLA enforcement known as of v2.4.1."""
        data = json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
        known = {b for b, cfg in data["brands"].items()
                 if cfg.get("ola_enforcement_known")}
        assert known == {"seat", "cupra"}

    def test_each_brand_has_sources_dict(self) -> None:
        """Multi-source fallback chain — every brand needs a sources block."""
        data = json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
        for brand, cfg in data["brands"].items():
            assert "sources" in cfg, f"Brand {brand} missing 'sources' dict"
            # At least one source must be configured (apkmirror OR uptodown).
            sources = cfg["sources"]
            assert sources.get("apkmirror_slug") or sources.get("uptodown_subdomain"), (
                f"Brand {brand} has no usable source — neither apkmirror_slug "
                f"nor uptodown_subdomain configured"
            )

    def test_search_patterns_include_ola_headers(self) -> None:
        data = json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
        ola = data["search_patterns"]["ola_headers"]
        assert set(ola) >= {"app-market", "app-brand", "app-version", "origin"}

    def test_search_patterns_include_known_backends(self) -> None:
        data = json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
        hosts = data["search_patterns"]["known_backend_hosts"]
        # Critical hosts that must be searched for in every APK extraction.
        for h in (
            "ola.prod.code.seat.cloud.vwgroup.com",
            "emea.bff.cariad.digital",
            "mysmob.api.connect.skoda-auto.cz",
            "identity.vwgroup.io",
            "identity.na.vwgroup.io",
        ):
            assert h in hosts, f"Missing critical host in search_patterns: {h}"


# ──────────────────────────────────────────────────────────────────────
# 2. build_atlas.py structure
# ──────────────────────────────────────────────────────────────────────


class TestBuildScript:
    def test_script_exists_and_is_executable(self) -> None:
        assert _SCRIPT_PATH.exists()
        # The shebang + main() block must be present for CI to run it.
        src = _SCRIPT_PATH.read_text(encoding="utf-8")
        assert src.startswith("#!/usr/bin/env python3") or "if __name__ == " in src

    def test_multi_source_scraper_present(self) -> None:
        """Phase A.1: scrape_version walks apkmirror → uptodown → apkcombo fallback."""
        src = _SCRIPT_PATH.read_text(encoding="utf-8")
        assert "def scrape_version(" in src
        assert "_try_apkmirror" in src
        assert "_try_uptodown" in src
        # v2.4.2+ — APKCombo as 3rd-tier fallback (added for VW EU coverage).
        assert "_try_apkcombo" in src

    def test_emits_per_brand_atlas(self) -> None:
        src = _SCRIPT_PATH.read_text(encoding="utf-8")
        assert "def emit_brand_atlas(" in src

    def test_emits_summary(self) -> None:
        src = _SCRIPT_PATH.read_text(encoding="utf-8")
        assert "def emit_summary(" in src

    def test_supports_dry_run(self) -> None:
        """Local debugging convenience — --dry-run should not write files."""
        src = _SCRIPT_PATH.read_text(encoding="utf-8")
        assert "--dry-run" in src
        assert "dry_run" in src

    def test_supports_single_brand_filter(self) -> None:
        src = _SCRIPT_PATH.read_text(encoding="utf-8")
        assert "--brand" in src


# ──────────────────────────────────────────────────────────────────────
# 3. Workflow file
# ──────────────────────────────────────────────────────────────────────


class TestWorkflow:
    def test_workflow_exists(self) -> None:
        assert _WORKFLOW_PATH.exists()

    def test_runs_daily(self) -> None:
        src = _WORKFLOW_PATH.read_text(encoding="utf-8")
        # Daily cron, 04:00 UTC (different from upstream-ola-watcher to
        # avoid runner contention).
        assert '"0 4 * * *"' in src

    def test_has_write_permissions(self) -> None:
        src = _WORKFLOW_PATH.read_text(encoding="utf-8")
        assert "contents: write" in src
        assert "pull-requests: write" in src

    def test_opens_pr_on_changes(self) -> None:
        src = _WORKFLOW_PATH.read_text(encoding="utf-8")
        assert "gh pr create" in src
        assert "auto-atlas" in src  # label

    def test_idempotent_pr_dedup(self) -> None:
        src = _WORKFLOW_PATH.read_text(encoding="utf-8")
        assert "gh pr list" in src

    def test_no_auto_merge(self) -> None:
        """Safety: APKMirror/Uptodown could return junk data; human reviews."""
        src = _WORKFLOW_PATH.read_text(encoding="utf-8")
        assert "gh pr merge" not in src

    def test_runs_atlas_builder_script(self) -> None:
        src = _WORKFLOW_PATH.read_text(encoding="utf-8")
        assert "scripts/app_atlas/build_atlas.py" in src


# ──────────────────────────────────────────────────────────────────────
# 4. Docs scaffolding
# ──────────────────────────────────────────────────────────────────────


class TestAtlasDocs:
    def test_atlas_directory_exists(self) -> None:
        assert _ATLAS_DIR.is_dir()

    def test_readme_present(self) -> None:
        assert (_ATLAS_DIR / "README.md").exists()

    def test_legal_disclosure_present(self) -> None:
        """Reverse-engineering legal basis must be documented."""
        legal = _ATLAS_DIR / "LEGAL.md"
        assert legal.exists()
        body = legal.read_text(encoding="utf-8")
        # Cites the actual legal exceptions.
        assert "DMCA" in body
        assert "Software Directive" in body or "2009/24/EC" in body

    def test_summary_present(self) -> None:
        assert (_ATLAS_DIR / "_summary.md").exists()

    @pytest.mark.parametrize(
        "brand",
        ["seat", "cupra", "volkswagen", "audi", "skoda", "volkswagen_na", "porsche"],
    )
    def test_per_brand_page_exists(self, brand: str) -> None:
        """Initial atlas run populates a page per brand even when fetch fails."""
        assert (_ATLAS_DIR / f"{brand}.md").exists()


# ──────────────────────────────────────────────────────────────────────
# 5. Phase A.2 — APK extraction module
# ──────────────────────────────────────────────────────────────────────


class TestApkExtractorModule:
    """Source-level pins for the Phase A.2 APK extraction module."""

    def test_module_exists(self) -> None:
        assert _EXTRACTOR_PATH.exists()

    def test_public_pipeline_function(self) -> None:
        """The end-to-end pipeline entry-point is named extract_brand_apk."""
        src = _EXTRACTOR_PATH.read_text(encoding="utf-8")
        assert "def extract_brand_apk(" in src

    def test_uses_apktool(self) -> None:
        """APK decode uses apktool (not androguard / not pyaxmlparser)."""
        src = _EXTRACTOR_PATH.read_text(encoding="utf-8")
        assert '"apktool"' in src
        assert "subprocess.run" in src

    def test_handles_xapk_bundles(self) -> None:
        """APKCombo serves XAPK split-bundles; unpacker must handle them."""
        src = _EXTRACTOR_PATH.read_text(encoding="utf-8")
        assert "def unpack_xapk(" in src
        assert "zipfile" in src

    def test_grep_uses_config_patterns(self) -> None:
        """search_patterns dict from config.json drives the grep step."""
        src = _EXTRACTOR_PATH.read_text(encoding="utf-8")
        assert "def grep_patterns(" in src
        assert "ola_headers" in src
        assert "known_backend_hosts" in src

    def test_cleanup_transient_files(self) -> None:
        """APKs are 50-200MB — must NOT be retained after extraction."""
        src = _EXTRACTOR_PATH.read_text(encoding="utf-8")
        assert "rmtree" in src or "unlink" in src
        # Either both or at minimum: the comment notes cleanup is intentional.
        assert "Cleanup" in src or "cleanup" in src


class TestPhaseA2Integration:
    """build_atlas.py wires the apk_extractor in when --with-apk-extraction."""

    def test_cli_flag_present(self) -> None:
        src = _SCRIPT_PATH.read_text(encoding="utf-8")
        assert "--with-apk-extraction" in src

    def test_only_extracts_on_version_change(self) -> None:
        """Idempotency: same version on re-runs should NOT re-extract."""
        src = _SCRIPT_PATH.read_text(encoding="utf-8")
        # The guard condition `current != prev_ver` must gate extraction.
        assert "current != prev_ver" in src

    def test_apk_findings_cache_used(self) -> None:
        """APK findings persist to .app-atlas-apk-cache/{brand}.json."""
        src = _SCRIPT_PATH.read_text(encoding="utf-8")
        assert "_APK_CACHE_DIR" in src
        assert "_save_apk_findings" in src
        assert "_load_apk_findings" in src

    def test_atlas_page_renders_apk_section(self) -> None:
        """Atlas markdown includes the 'Discovered via APK extraction' section."""
        src = _SCRIPT_PATH.read_text(encoding="utf-8")
        assert "Discovered via APK extraction" in src

    def test_workflow_installs_apktool(self) -> None:
        src = _WORKFLOW_PATH.read_text(encoding="utf-8")
        assert "apt-get install" in src and "apktool" in src

    def test_workflow_passes_with_apk_extraction_flag(self) -> None:
        src = _WORKFLOW_PATH.read_text(encoding="utf-8")
        assert "--with-apk-extraction" in src


class TestAllBrandsHaveApkcomboSlug:
    """Phase A.2 currently uses APKCombo CDN — every brand needs a slug."""

    @pytest.mark.parametrize(
        "brand",
        ["seat", "cupra", "volkswagen", "audi", "skoda", "volkswagen_na", "porsche"],
    )
    def test_brand_has_apkcombo_slug(self, brand: str) -> None:
        data = json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
        slug = data["brands"][brand]["sources"].get("apkcombo_slug")
        assert slug, f"Brand {brand} missing apkcombo_slug — APK extraction can't run"


# ──────────────────────────────────────────────────────────────────────
# 6. Phase A.3 — jadx decompile + cross-version semantic diff
# ──────────────────────────────────────────────────────────────────────


_JADX_PATH         = _REPO_ROOT / "scripts" / "app_atlas" / "jadx_decompiler.py"
_VERSION_DIFF_PATH = _REPO_ROOT / "scripts" / "app_atlas" / "version_diff.py"
_DEEP_DIFF_PATH    = _REPO_ROOT / "scripts" / "app_atlas" / "run_deep_diff.py"
_DEEP_DIFF_WF_PATH = _REPO_ROOT / ".github" / "workflows" / "app-atlas-deep-diff.yml"
_DIFFS_DIR         = _ATLAS_DIR / "diffs"


class TestPhaseA3Modules:
    """Source-level pins for the Phase A.3 jadx + diff modules."""

    def test_jadx_decompiler_module_exists(self) -> None:
        assert _JADX_PATH.exists()

    def test_jadx_wraps_jadx_cli(self) -> None:
        src = _JADX_PATH.read_text(encoding="utf-8")
        assert "def jadx_decompile(" in src
        assert '"jadx"' in src
        assert "--no-res" in src  # skip resource decoding for speed

    def test_jadx_reuses_apkextractor_download(self) -> None:
        """Don't reinvent the APK download wheel — reuse A.2's path."""
        src = _JADX_PATH.read_text(encoding="utf-8")
        assert "from apk_extractor import" in src
        assert "download_to" in src and "unpack_xapk" in src

    def test_version_diff_module_exists(self) -> None:
        assert _VERSION_DIFF_PATH.exists()

    def test_version_diff_extracts_constants(self) -> None:
        src = _VERSION_DIFF_PATH.read_text(encoding="utf-8")
        assert "def extract_url_constants(" in src
        assert "def extract_header_keys(" in src
        assert "def extract_oauth_scopes(" in src

    def test_version_diff_renders_report(self) -> None:
        src = _VERSION_DIFF_PATH.read_text(encoding="utf-8")
        assert "def render_diff_report(" in src
        # Report sections we promise to maintainers in the README.
        assert "URLs added" in src
        assert "URLs removed" in src or "Removed URLs" in src

    def test_version_diff_filters_noise(self) -> None:
        """Filter out stable noise (XML schemas, Google APIs)."""
        src = _VERSION_DIFF_PATH.read_text(encoding="utf-8")
        assert "schemas.android.com" in src or "android.googleapis.com" in src

    def test_deep_diff_orchestrator_exists(self) -> None:
        assert _DEEP_DIFF_PATH.exists()

    def test_deep_diff_takes_brand_old_new(self) -> None:
        src = _DEEP_DIFF_PATH.read_text(encoding="utf-8")
        assert "--brand" in src
        assert "--old-version" in src
        assert "--new-version" in src


class TestPhaseA3Workflow:
    """Manual-trigger workflow for deep-diff generation."""

    def test_workflow_exists(self) -> None:
        assert _DEEP_DIFF_WF_PATH.exists()

    def test_workflow_is_manual_only(self) -> None:
        """Deep diff is too heavy for scheduled runs — manual only."""
        src = _DEEP_DIFF_WF_PATH.read_text(encoding="utf-8")
        assert "workflow_dispatch:" in src
        # Critical: NO schedule trigger — would burn through CI budget.
        assert "schedule:" not in src

    def test_workflow_inputs_present(self) -> None:
        src = _DEEP_DIFF_WF_PATH.read_text(encoding="utf-8")
        assert "brand:" in src
        assert "old_version:" in src
        assert "new_version:" in src

    def test_workflow_brand_choice_constrained(self) -> None:
        """Brand input restricted to the 7 brands we know."""
        src = _DEEP_DIFF_WF_PATH.read_text(encoding="utf-8")
        # All 7 brand keys must appear as choice options.
        for brand in ("seat", "cupra", "volkswagen", "audi",
                      "skoda", "volkswagen_na", "porsche"):
            assert f"          - {brand}" in src, (
                f"workflow_dispatch brand input missing choice for {brand}"
            )

    def test_workflow_installs_jadx_and_rg(self) -> None:
        src = _DEEP_DIFF_WF_PATH.read_text(encoding="utf-8")
        assert "jadx" in src
        assert "ripgrep" in src

    def test_workflow_opens_pr_with_report(self) -> None:
        src = _DEEP_DIFF_WF_PATH.read_text(encoding="utf-8")
        assert "gh pr create" in src
        assert "diffs/" in src
        assert "auto-atlas-diff" in src  # label

    def test_workflow_does_not_auto_merge(self) -> None:
        """Safety: maintainer reviews + merges the diff report."""
        src = _DEEP_DIFF_WF_PATH.read_text(encoding="utf-8")
        assert "gh pr merge" not in src

    def test_diffs_directory_has_readme(self) -> None:
        """Empty diffs/ dir gets a README so new contributors find docs."""
        readme = _DIFFS_DIR / "README.md"
        assert readme.exists()
        body = readme.read_text(encoding="utf-8")
        assert "Phase A.3" in body
        assert "workflow_dispatch" in body or "manual" in body.lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
