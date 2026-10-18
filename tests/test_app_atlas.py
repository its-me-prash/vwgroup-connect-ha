# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for the Cross-Brand App Atlas pipeline (Phase A.1).

Source-level pins for the scaffolding — no network calls (CI doesn't
need to actually read a Google Play listing to validate the structure).
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any

import pytest


_REPO_ROOT      = Path(__file__).resolve().parent.parent
_CONFIG_PATH    = _REPO_ROOT / "scripts" / "app_atlas" / "config.json"
_SCRIPT_PATH    = _REPO_ROOT / "scripts" / "app_atlas" / "build_atlas.py"
_EXTRACTOR_PATH = _REPO_ROOT / "scripts" / "app_atlas" / "apk_extractor.py"
_ATLAS_DIR      = _REPO_ROOT / "docs" / "research" / "app-atlas"
_NOTES_DIR      = _REPO_ROOT / "scripts" / "app_atlas" / "notes"


def _brand_keys() -> list[str]:
    """Brand keys straight from config.json.

    Parametrising off the config instead of a hand-copied literal is what makes
    adding a brand a one-line change: the per-brand page, package-id and
    deep-diff-choice tests all pick it up, so a half-added brand fails loudly
    instead of being silently untested.
    """
    data = json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
    return list(data["brands"].keys())


# ──────────────────────────────────────────────────────────────────────
# 1. config.json schema + coverage
# ──────────────────────────────────────────────────────────────────────


class TestConfig:
    def test_config_exists_and_parses(self) -> None:
        data = json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
        assert "_atlas_version" in data
        assert "brands" in data
        assert "search_patterns" in data

    def test_all_tracked_brands_present(self) -> None:
        data = json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
        expected = {
            "seat", "cupra", "volkswagen", "audi",
            "skoda", "volkswagen_na", "porsche",
            # Porsche ships two packages: com.porsche.one is the North-American
            # build, de.porsche.one is what everyone else — including every EU
            # reporter we hear from — actually installs. One row for both would
            # have meant quoting an NA version at EU owners.
            "porsche_row",
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
            ("porsche_row",   "de.porsche.one"),
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

    def test_package_id_is_the_whole_source_identity(self) -> None:
        """Google Play is the only source, keyed by package_id — so that one
        field is all a brand needs, and the old per-mirror `sources` block has
        no reason to exist. Pinned in both directions: the id must be there,
        and the block must not come back."""
        data = json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
        for brand, cfg in data["brands"].items():
            assert cfg.get("package_id"), f"Brand {brand} has no package_id to poll"
            assert "sources" not in cfg, (
                f"Brand {brand} carries a 'sources' block again — nothing reads it"
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

    def test_google_play_is_the_only_version_source(self) -> None:
        """The version scraper walks Google Play and nothing else. The mirror
        tiers are gone because a mirror answers from whatever it last ingested:
        a reading that lags the store is worse than none, since is_downgrade()
        then compares against a stale ceiling. A missing version is rendered as
        a gap instead."""
        src = _SCRIPT_PATH.read_text(encoding="utf-8")
        assert "def scrape_version(" in src
        assert "_try_google_play" in src
        for gone in ("_try_apkmirror", "_try_uptodown", "_try_apkcombo",
                     "apkmirror.com", "uptodown.com", "apkcombo.com"):
            assert gone not in src, f"{gone} is back in the version scraper"

    def test_an_extraction_crash_does_not_take_the_poll_down(self) -> None:
        """Measured, not hypothetical: the daily workflow failed five days
        running (2026-10-13 .. 2026-10-17) because an unresolvable mirror host
        raised URLError out of the extractor, aborting main() before anything
        was written — while Play was answering for six brands throughout. The
        extraction call has to be guarded."""
        # Anchored on the call's own neighbouring lines. An earlier version of
        # this test searched for a `try:` before the call and an `except` after
        # it, and passed on a mutant with both removed: the import block just
        # above has its own try/except, which is what the search found.
        lines = _SCRIPT_PATH.read_text(encoding="utf-8").splitlines()
        call = next(i for i, ln in enumerate(lines)
                    if "findings = extract_brand_apk(" in ln)
        above = lines[call - 1].strip()
        assert above == "try:", (
            "the extract_brand_apk call is not directly inside a try: — the "
            f"line above it is {above!r}"
        )
        arm = [ln.strip() for ln in lines[call:call + 20]]
        assert any(ln.startswith("except Exception") for ln in arm), (
            "no except arm on the extraction call — one brand's crash would "
            "abort the poll for every remaining brand"
        )
        assert "findings = None" in arm, (
            "the except arm must leave findings unset so the caller renders "
            "last-known findings instead of claiming a successful extraction"
        )

    def test_a_stale_brand_page_says_the_source_was_retained(
        self, tmp_path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Through emit_brand_atlas, because the call site is the part that was
        uncovered: reverting it alone — helper and summary left intact — kept
        the whole suite green, which is how the live pages came to credit a
        removed mirror without a test noticing."""
        mod = _load_builder()
        atlas = tmp_path / "atlas"
        atlas.mkdir()
        monkeypatch.setattr(mod, "_ATLAS_DIR", atlas)
        monkeypatch.setattr(mod, "_APK_CACHE_DIR", tmp_path / "no-cache")
        cfg = {"display_name": "Porsche", "package_id": "com.porsche.one",
               "expected_backend": "ppa"}

        mod.emit_brand_atlas("porsche", cfg, "21.26.39", "apkmirror",
                             {"last_version_name": "21.26.39"}, status="stale")
        row = next(ln for ln in (atlas / "porsche.md").read_text(encoding="utf-8").splitlines()
                   if "Source that responded" in ln)
        assert "retained" in row, f"a stale page still claims a source answered: {row!r}"
        assert "| `apkmirror` |" not in row
        assert row.split("|")[2].strip() != "apkmirror"

        # And the fresh case must keep reading as a plain source name.
        mod.emit_brand_atlas("porsche", cfg, "21.26.40", "google_play",
                             {"last_version_name": "21.26.39"})
        row = next(ln for ln in (atlas / "porsche.md").read_text(encoding="utf-8").splitlines()
                   if "Source that responded" in ln)
        assert "`google_play`" in row and "retained" not in row

    def test_an_unreadable_findings_file_is_no_findings_not_empty_findings(
        self,
    ) -> None:
        """The cache directory collects files from whatever tool last wrote it,
        and one shape in there is `{brand, versions, latest}`. Read through the
        lookups this renderer uses, every field came back None and five pages
        were rendered stating "Last extracted: (unknown)" followed by "none of
        the configured backend hosts found" — a negative result reported for
        brands whose cache had never been read. Unreadable has to mean unknown,
        not empty."""
        mod = _load_builder()
        foreign = mod._render_apk_section(
            {"brand": "skoda", "versions": ["8.17.0"], "latest": "8.17.0"}
        )
        assert foreign.startswith("_(Empty"), (
            f"a cache file of an unknown shape rendered as a result: {foreign[:120]!r}"
        )
        assert "(unknown)" not in foreign
        assert "none of the configured" not in foreign

        # A well-formed record must still render, or the guard would swallow
        # every real finding instead.
        good = mod._render_apk_section({
            "extracted_for_version": "5.8.1",
            "findings": {"extracted_at": "2026-06-25T04:38:28",
                         "headers": ["x-qmauth"], "endpoint_hosts": []},
        })
        assert "Last extracted: 2026-06-25T04:38:28" in good
        assert "x-qmauth" in good

    def test_the_summary_table_marks_a_retained_row_as_retained(
        self, tmp_path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Through emit_summary, not through the helper. The helper had a unit
        test while the table built its own label inline, so reverting the
        table's half left the suite green — the rendered-page test only catches
        it once someone re-runs the builder."""
        mod = _load_builder()
        out = tmp_path / "_summary.md"
        monkeypatch.setattr(mod, "_SUMMARY_PATH", out)
        cfg = {"brands": {
            "skoda": {"display_name": "Skoda", "package_id": "cz.skodaauto.myskoda",
                      "expected_backend": "mysmob"},
            "porsche": {"display_name": "Porsche", "package_id": "com.porsche.one",
                        "expected_backend": "ppa"},
        }}
        mod.emit_summary(
            cfg,
            {"skoda": "8.17.0", "porsche": "21.26.39"},
            {"skoda": "google_play", "porsche": "apkmirror"},
            {"skoda": "ok", "porsche": "stale"},
        )
        body = out.read_text(encoding="utf-8")
        skoda_row = next(ln for ln in body.splitlines() if "Skoda" in ln)
        porsche_row = next(ln for ln in body.splitlines() if "Porsche" in ln)
        assert "`google_play`" in skoda_row and "retained" not in skoda_row
        assert "8.17.0" in skoda_row and "not re-confirmed" not in skoda_row
        # The retained row must not read as though apkmirror answered today.
        assert "| `apkmirror` |" not in porsche_row
        assert "retained" in porsche_row
        assert "not re-confirmed" in porsche_row

    def test_a_single_brand_run_does_not_blank_the_other_rows(
        self, tmp_path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """emit_summary rewrites every row from the dicts main() built, so with
        `--brand X` only X was in them and the rest rendered as "(fetch
        failed)" — for brands that had not been asked anything. The README
        offers --brand for debugging, so this silently blanked the committed
        table."""
        mod = _load_builder()
        atlas = tmp_path / "atlas"
        atlas.mkdir()
        cache = tmp_path / "cache.json"
        cfg_path = tmp_path / "config.json"
        cfg_path.write_text(json.dumps({"brands": {
            "skoda": {"display_name": "Skoda", "package_id": "cz.skodaauto.myskoda",
                      "expected_backend": "mysmob"},
            "porsche": {"display_name": "Porsche", "package_id": "com.porsche.one",
                        "expected_backend": "ppa"},
        }, "search_patterns": {}}), encoding="utf-8")
        cache.write_text(json.dumps({"brands": {
            "skoda": {"last_version_name": "8.17.0", "last_source": "google_play",
                      "last_status": "ok"},
            "porsche": {"last_version_name": "21.26.39", "last_source": "apkmirror",
                        "last_status": "stale"},
        }}), encoding="utf-8")
        monkeypatch.setattr(mod, "_CONFIG_PATH", cfg_path)
        monkeypatch.setattr(mod, "_CACHE_PATH", cache)
        monkeypatch.setattr(mod, "_ATLAS_DIR", atlas)
        monkeypatch.setattr(mod, "_SUMMARY_PATH", atlas / "_summary.md")
        monkeypatch.setattr(mod, "_APK_CACHE_DIR", tmp_path / "no-cache")
        monkeypatch.setattr(mod, "scrape_version", lambda *a, **k: ("8.18.0", "google_play"))

        assert mod.main(["--brand", "skoda"]) == 0
        body = (atlas / "_summary.md").read_text(encoding="utf-8")
        assert "(fetch failed)" not in body, (
            "a brand this run never touched was rendered as a failed fetch"
        )
        porsche_row = next(ln for ln in body.splitlines() if "Porsche" in ln)
        assert "21.26.39" in porsche_row, "the untouched brand lost its known version"
        assert "8.18.0" in next(ln for ln in body.splitlines() if "Skoda" in ln)

    def test_a_retained_reading_is_not_labelled_as_having_responded(self) -> None:
        """The source cell is headed by what answered *this run*, so a stale
        brand must not print a bare source name there."""
        mod = _load_builder()
        fresh = mod._source_label("google_play", "ok")
        assert fresh == "`google_play`"
        stale = mod._source_label("apkcombo", "stale")
        assert "retained" in stale
        assert stale != "`apkcombo`"
        assert mod._source_label(None, "ok") == "(no source succeeded)"

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

    @pytest.mark.parametrize("brand", _brand_keys())
    def test_per_brand_page_exists(self, brand: str) -> None:
        """Initial atlas run populates a page per brand even when fetch fails."""
        assert (_ATLAS_DIR / f"{brand}.md").exists()

    def test_a_rerender_without_a_cache_keeps_the_extraction_record(
        self, tmp_path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """`.app-atlas-apk-cache/` is gitignored and only lives for the length
        of an extraction run — the page is the durable record. That was
        invisible while CI extracted and rendered in the same job. Once
        extraction moved to a maintainer's machine, a CI re-render had no cache
        and would have replaced a real extraction record with the "not yet run"
        placeholder, deleting findings inside a commit titled "refresh
        app-atlas"."""
        mod = _load_builder()
        atlas = tmp_path / "atlas"
        atlas.mkdir()
        real = (
            "_Last extracted: 2026-06-25T04:38:28 (for version `5.5.1`)_\n\n"
            "### HTTP header keys found in app bytecode\n\n- `x-qmauth`\n"
        )
        (atlas / "audi.md").write_text(
            "# App Atlas - Audi\n\n"
            "## Discovered via APK extraction (Phase A.2)\n\n"
            f"{real}\n"
            "## Cross-version diff\n\nnothing\n",
            encoding="utf-8",
        )
        monkeypatch.setattr(mod, "_ATLAS_DIR", atlas)
        monkeypatch.setattr(mod, "_APK_CACHE_DIR", tmp_path / "empty-cache")

        assert mod._load_apk_findings("audi") is None, "fixture must have no cache"

        # Go through the real renderer, not just the helper. An earlier version
        # of this test called _previous_apk_section() directly and passed on a
        # mutant with the call site reverted to the old
        # `_render_apk_section(_load_apk_findings(brand))` — it proved the
        # helper worked while the page was still being emptied.
        mod.emit_brand_atlas(
            "audi",
            {"display_name": "Audi", "package_id": "de.myaudi.mobile.assistant",
             "expected_backend": "cariad_bff"},
            "5.8.1", "google_play", {"last_version_name": "5.8.0"},
        )
        page = (atlas / "audi.md").read_text(encoding="utf-8")
        assert page.count("## Discovered via APK extraction") == 1, (
            "the carried body brought a second copy of the heading"
        )
        head = page.index("## Discovered via APK extraction")
        apk_part = page[head:page.index("\n## ", head + 10)]
        assert "Last extracted: 2026-06-25" in apk_part, (
            "the re-rendered page dropped the extraction record"
        )
        assert "x-qmauth" in apk_part
        # Scoped to this section on purpose: the Phase A.3 cross-version-diff
        # section below legitimately carries its own "(Empty ...)" placeholder.
        assert "_(Empty" not in apk_part

        carried = mod._previous_apk_section("audi")
        assert carried is not None
        assert "## Discovered via APK extraction" not in carried

        # Carrying a carried body must be idempotent, or every run would stack
        # another layer onto the page.
        (atlas / "audi.md").write_text(
            "# App Atlas - Audi\n\n"
            "## Discovered via APK extraction (Phase A.2)\n\n"
            f"{carried}\n\n"
            "## Cross-version diff\n\nnothing\n",
            encoding="utf-8",
        )
        assert mod._previous_apk_section("audi") == carried

        # A page that never had findings must not carry the placeholder forward
        # as though it were a record.
        (atlas / "seat.md").write_text(
            "## Discovered via APK extraction (Phase A.2)\n\n"
            "_(Empty — Phase A.2 APK extraction not yet run for this brand.)_\n\n"
            "## Cross-version diff\n",
            encoding="utf-8",
        )
        assert mod._previous_apk_section("seat") is None
        assert mod._previous_apk_section("brand-with-no-page") is None

    def test_the_client_id_watch_runs_where_the_cache_is(self) -> None:
        """The new-OAuth-client_id watch reads the extraction cache. It was a
        separate step in the daily workflow, which only worked because that job
        extracted too. With extraction local, that step has nothing to read, so
        the watch has to be invoked by the extraction run itself or it goes
        quiet with nothing saying so."""
        src = _SCRIPT_PATH.read_text(encoding="utf-8")
        assert "diff_known_client_ids" in src, (
            "build_atlas does not invoke the client_id watch at all"
        )
        tail = src[src.index("diff_known_client_ids"):]
        assert "_cid_main()" in tail
        # Advisory only: it must not be able to fail the atlas run.
        assert "except Exception" in tail

    def test_no_page_credits_a_source_that_was_not_asked(self) -> None:
        """A brand that keeps its last confirmed version also keeps the name of
        whatever delivered it, and both the per-brand page and the summary used
        to print that name under a column headed "Source that responded". Both
        Porsche rows therefore read `apkmirror` / `apkcombo` on runs where
        neither was in the code at all. Scanned over the rendered pages, so it
        catches the claim wherever it is rendered from."""
        # Match the NAME, not a backticked name. The first version of this
        # test asserted only on "| `apkmirror` |" and was run against a tree
        # where porsche.md read "| Source that responded | apkmirror |" with no
        # backticks at all — it passed, on a page publishing the exact claim
        # this test exists to catch. The label's markup is not the invariant;
        # the mirror name appearing in a row about this run is.
        for page in sorted(_ATLAS_DIR.glob("*.md")):
            for line in page.read_text(encoding="utf-8").splitlines():
                cells = [c.strip().strip("`") for c in line.split("|")]
                if "Source that responded" not in cells:
                    continue
                for mirror in ("apkmirror", "apkcombo", "uptodown"):
                    assert mirror not in cells, (
                        f"{page.name} credits {mirror} as the source that "
                        f"responded: {line.strip()!r}"
                    )
        # The summary's rows have no label cell, so check its Source column by
        # position instead of by heading.
        summary = _ATLAS_DIR / "_summary.md"
        if summary.exists():
            for line in summary.read_text(encoding="utf-8").splitlines():
                if not line.startswith("| **"):
                    continue
                cells = [c.strip().strip("`") for c in line.split("|")]
                for mirror in ("apkmirror", "apkcombo", "uptodown"):
                    assert mirror not in cells, (
                        f"_summary.md credits {mirror} as a source that "
                        f"responded: {line.strip()!r}"
                    )


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
        """Play serves XAPK split-bundles; unpacker must handle them."""
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


class TestPhaseA2Robustness:
    """Phase A.2 hardening: Windows apktool resolution, Play-only fetch,
    and the package-identity guard that rejects decoy downloads."""

    def _extractor(self):
        import importlib
        import sys
        sys.path.insert(0, str(_REPO_ROOT / "scripts" / "app_atlas"))
        return importlib.import_module("apk_extractor")

    def _fake_apk(self, tmp_path, package: str):
        import zipfile
        apk = tmp_path / "x.apk"
        with zipfile.ZipFile(apk, "w") as z:
            # Binary AXML stores strings as UTF-16LE; emulate the package string.
            z.writestr("AndroidManifest.xml", package.encode("utf-16-le"))
            z.writestr("classes.dex", b"dex\n035\x00")
        return apk

    def test_apktool_resolved_via_which(self) -> None:
        """Windows ships apktool as a .BAT wrapper that a bare subprocess call
        cannot resolve — it must go through shutil.which."""
        src = _EXTRACTOR_PATH.read_text(encoding="utf-8")
        assert 'shutil.which("apktool")' in src

    def test_google_play_is_the_only_apk_source(self) -> None:
        """The mirrors are gone on purpose. Two recorded reasons, both from
        this repository's own history rather than from memory: a mirror served
        CUPRA 2.18.1 while Play and the store had 2.19.1, and Volkswagen was
        never resolved by any of the three at all — its cache entry carried a
        null version while the watcher recorded daily that it had looked (see
        tests/test_v2180_atlas_google_play.py). One of them also gated
        downloads and handed back its own client app, which is why the package
        guard below had to exist. This pins that none of them comes back
        quietly — not even as a comment someone later writes a caller for."""
        src = _EXTRACTOR_PATH.read_text(encoding="utf-8")
        assert "def fetch_from_play(" in src
        assert "fetch_from_play(package_id, brand, tmp_dir)" in src
        assert "resolve_apkcombo_download" not in src
        assert "resolve_uptodown_download" not in src
        assert "apkcombo.com" not in src
        assert "uptodown" not in src.lower()

    def test_play_success_is_a_file_not_an_exit_code(self) -> None:
        """apkeep can print "Downloading" and exit 0 having written nothing when
        the disposable account it drew is cohort-limited. The fetch must judge on
        artifacts appearing on disk and rotate accounts, or the atlas records a
        successful extraction of nothing."""
        src = _EXTRACTOR_PATH.read_text(encoding="utf-8")
        assert "_apks_in(out_dir)" in src
        assert "_PLAY_ROTATIONS" in src
        assert "auroraoss.com/api/auth" in src

    def test_a_split_bundle_counts_as_an_artifact(self, tmp_path) -> None:
        """apkeep writes a split bundle as .xapk or .apks depending on how Play
        serves it, and the fetch judges success by artifacts appearing on disk.
        Counting only two of the three extensions made an .apks download read
        as "no artifact": the fetch would rotate accounts against a file it had
        already pulled and then report failure for a successful download. The
        reference script counts all three."""
        mod = self._extractor()
        for name in ("base.apk", "bundle.xapk", "split.apks", "notes.txt",
                     "UPPER.APKS"):
            (tmp_path / name).write_bytes(b"x")
        found = {p.name for p in mod._apks_in(tmp_path)}
        assert found == {"base.apk", "bundle.xapk", "split.apks", "UPPER.APKS"}, (
            f"artifact detection missed a bundle extension: {sorted(found)}"
        )

    def test_the_rotation_budget_covers_the_documented_worst_case(self) -> None:
        """The reference method rotates without a limit and records that one
        brand needed attempt 18. A cap below that fails exactly the brand the
        note was written about."""
        mod = self._extractor()
        assert mod._PLAY_ROTATIONS >= 18, (
            f"_PLAY_ROTATIONS={mod._PLAY_ROTATIONS} is under the documented "
            "worst case of 18 attempts"
        )

    def test_package_guard_wired(self) -> None:
        src = _EXTRACTOR_PATH.read_text(encoding="utf-8")
        assert "def _apk_declares_package(" in src
        assert "_apk_declares_package(base_apk, expected_pkg)" in src

    def test_guard_accepts_matching_package(self, tmp_path) -> None:
        mod = self._extractor()
        apk = self._fake_apk(tmp_path, "de.myaudi.mobile.assistant")
        assert mod._apk_declares_package(apk, "de.myaudi.mobile.assistant") is True

    def test_guard_rejects_decoy(self, tmp_path) -> None:
        """A file that declares a different package than the one requested is
        rejected. The name below is the real case that put the guard here: a
        mirror that gated downloads handed back its own client app."""
        mod = self._extractor()
        apk = self._fake_apk(tmp_path, "com.uptodown.activities")
        assert mod._apk_declares_package(apk, "cz.skodaauto.myskoda") is False

    def test_no_mirror_scraping_machinery_is_left_behind(self) -> None:
        """The HTML-scraping helpers went with the resolvers. Pinned because a
        leftover regex is how a mirror path quietly comes back: someone writes a
        new caller for a parser that is still sitting there."""
        mod = self._extractor()
        for gone in ("_UPTODOWN_TOKEN_RE", "_R2_LINK_RE",
                     "resolve_uptodown_download", "resolve_apkcombo_download"):
            assert not hasattr(mod, gone), f"{gone} is still importable"


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

    def test_force_extract_flag_bypasses_cache(self) -> None:
        """--force-extract overrides the version-change idempotency check."""
        src = _SCRIPT_PATH.read_text(encoding="utf-8")
        assert "--force-extract" in src
        assert "force_extract" in src
        # The override must actually short-circuit the cache check.
        assert "args.force_extract or current != prev_ver" in src

    def test_force_extract_implies_with_apk_extraction(self) -> None:
        """Setting --force-extract without --with-apk-extraction shouldn't
        require the user to also pass the flag — implied automatically."""
        src = _SCRIPT_PATH.read_text(encoding="utf-8")
        assert "args.with_apk_extraction = True" in src

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


class TestAllBrandsHaveAPlayPackageId:
    """Phase A.2 fetches from Google Play — every brand needs a package id, and
    that is now the single identifier, not one of three."""

    @pytest.mark.parametrize("brand", _brand_keys())
    def test_brand_has_package_id(self, brand: str) -> None:
        data = json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
        pkg = data["brands"][brand].get("package_id")
        assert pkg, f"Brand {brand} missing package_id — APK extraction can't run"
        assert "/" not in pkg, (
            f"Brand {brand}: {pkg!r} looks like a mirror slug, not a Play package id"
        )

    def test_no_mirror_keys_remain(self) -> None:
        """Scanned over the raw config text, not over a per-brand `sources`
        dict: that dict is gone, so a loop through it would be a loop over
        nothing and would pass whatever the file said. The text scan still
        fails if any mirror key is reintroduced, wherever it is put."""
        raw = _CONFIG_PATH.read_text(encoding="utf-8")
        for gone in ("apkmirror_slug", "uptodown_subdomain", "apkcombo_slug"):
            assert gone not in raw, f"config.json carries {gone} again"


# ──────────────────────────────────────────────────────────────────────
# 6. Phase A.3 — jadx decompile + cross-version semantic diff
# ──────────────────────────────────────────────────────────────────────


_JADX_PATH         = _REPO_ROOT / "scripts" / "app_atlas" / "jadx_decompiler.py"
_VERSION_DIFF_PATH = _REPO_ROOT / "scripts" / "app_atlas" / "version_diff.py"
_DEEP_DIFF_PATH    = _REPO_ROOT / "scripts" / "app_atlas" / "run_deep_diff.py"
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
        """Don't reinvent the APK download wheel — reuse A.2's Play path, so
        there is exactly one place where an APK enters this pipeline."""
        src = _JADX_PATH.read_text(encoding="utf-8")
        assert "from apk_extractor import" in src
        assert "fetch_from_play" in src and "unpack_xapk" in src

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


class TestPhaseA3Docs:
    """Documentation for locally generated deep-diff reports."""


    def test_diffs_directory_has_readme(self) -> None:
        """Empty diffs/ dir gets a README so new contributors find docs."""
        readme = _DIFFS_DIR / "README.md"
        assert readme.exists()
        body = readme.read_text(encoding="utf-8")
        assert "Phase A.3" in body
        assert "workflow_dispatch" in body or "manual" in body.lower()


# ──────────────────────────────────────────────────────────────────────
# 7. Version ordering guard
# ──────────────────────────────────────────────────────────────────────


class TestVersionOrdering:
    def test_a_flavoured_build_string_cannot_be_compared(self) -> None:
        """Porsche publishes the flavour in the build string itself
        (`20.26.36-row+186611`). Such a string does not parse, so
        is_downgrade() cannot fire on it — which is why a version is only ever
        recorded as its dotted numeric part. Keep both halves of this pinned:
        the unparseable form must stay unparseable (so it is never silently
        treated as comparable), and the stripped form must compare."""
        mod = _load_builder()
        assert mod.parse_version("20.26.36-row") is None
        assert mod.is_downgrade("20.26.36-row", "20.26.37") is False
        assert mod.is_downgrade("20.26.36", "20.26.37") is True


# ──────────────────────────────────────────────────────────────────────
# 8. Curated notes — hand-written findings folded into generated pages
# ──────────────────────────────────────────────────────────────────────


def _load_builder() -> Any:
    """Import build_atlas.py by path (scripts/ is not an installed package)."""
    spec = importlib.util.spec_from_file_location("_atlas_builder", _SCRIPT_PATH)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestCuratedNotes:
    """A brand page is regenerated from scratch every night, so analysis typed
    into the page itself lives exactly one day. These pin the mechanism that
    keeps it: notes live in scripts/app_atlas/notes/ and the emitter folds
    them in."""

    def test_emitter_reads_notes_dir(self) -> None:
        src = _SCRIPT_PATH.read_text(encoding="utf-8")
        assert "_NOTES_DIR" in src
        assert "def _load_note(" in src

    def test_note_sections_are_the_three_we_render(self) -> None:
        mod = _load_builder()
        assert set(mod._NOTE_SECTIONS) == {
            "flavors", "cross-version-diff", "action-items",
        }

    def test_missing_note_falls_back_to_placeholder(self) -> None:
        mod = _load_builder()
        assert mod._note_or("no-such-brand", "action-items", "PLACEHOLDER") == "PLACEHOLDER"
        # No note → no section header at all, not an empty one.
        assert mod._flavors_block("no-such-brand") == ""

    def test_blank_note_is_treated_as_absent(self, tmp_path: Path) -> None:
        """An emptied note must not punch a hole in the page."""
        mod = _load_builder()
        mod._NOTES_DIR = tmp_path
        (tmp_path / "ghost.action-items.md").write_text("   \n\n", encoding="utf-8")
        assert mod._note_or("ghost", "action-items", "PLACEHOLDER") == "PLACEHOLDER"

    def test_orphan_note_is_reported(self, tmp_path: Path) -> None:
        """A typo'd filename is silently ignored by the renderer — the builder
        has to say so, or the author never learns the note went nowhere."""
        mod = _load_builder()
        mod._NOTES_DIR = tmp_path
        (tmp_path / "porsche.action-items.md").write_text("x", encoding="utf-8")
        (tmp_path / "porshe.action-items.md").write_text("x", encoding="utf-8")
        (tmp_path / "porsche.actions.md").write_text("x", encoding="utf-8")
        orphans = mod.warn_orphan_notes(["porsche"])
        assert orphans == ["porsche.actions.md", "porshe.action-items.md"]

    def test_repo_notes_are_all_wired_up(self) -> None:
        """Every checked-in note must match a real brand + section."""
        mod = _load_builder()
        assert mod.warn_orphan_notes(_brand_keys()) == []

    @pytest.mark.parametrize(
        "brand,section",
        [
            ("porsche", "flavors"),
            ("porsche", "cross-version-diff"),
            ("porsche", "action-items"),
            ("porsche_row", "flavors"),
            ("skoda", "cross-version-diff"),
            ("skoda", "action-items"),
        ],
    )
    def test_note_present_and_rendered_on_page(self, brand: str, section: str) -> None:
        note = (_NOTES_DIR / f"{brand}.{section}.md").read_text(encoding="utf-8").strip()
        assert note
        page = (_ATLAS_DIR / f"{brand}.md").read_text(encoding="utf-8")
        # First line is enough: if the emitter dropped the note, it is missing.
        assert note.splitlines()[0] in page

    @pytest.mark.parametrize("brand", ["porsche", "skoda"])
    def test_placeholder_gone_from_filled_pages(self, brand: str) -> None:
        page = (_ATLAS_DIR / f"{brand}.md").read_text(encoding="utf-8")
        assert "Phase A.3 will populate this" not in page
        assert "Auto-flagged by the pipeline" not in page

    def test_porsche_pages_cross_link_the_two_flavors(self) -> None:
        """The whole point of the second brand row: neither page can be read as
        'the' Porsche version without the other being one click away."""
        na = (_ATLAS_DIR / "porsche.md").read_text(encoding="utf-8")
        row = (_ATLAS_DIR / "porsche_row.md").read_text(encoding="utf-8")
        assert "de.porsche.one" in na and "porsche_row.md" in na
        assert "com.porsche.one" in row and "porsche.md" in row


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
