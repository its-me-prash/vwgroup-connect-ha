# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""A failed or backwards scrape must not overwrite what the atlas already knew.

The daily watcher opened a PR that replaced a known-good Skoda version with
null because every download mirror failed that morning, and walked CUPRA from
2.20.2 back to 2.20.1 because one listing served an older number. Both came
from the same place: the run wrote whatever the scrape returned, and the only
guard on a version move tested inequality, never ordering.

Neither failure could have been caught before, because nothing in the suite ran
``main()`` — every atlas test asserted on the source text of the file rather
than on its behaviour. These execute the real loop against a stubbed scraper.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any

import pytest

_SCRIPT = (Path(__file__).resolve().parents[1]
           / "scripts" / "app_atlas" / "build_atlas.py")


def _module():
    spec = importlib.util.spec_from_file_location("_atlas_under_test", _SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def atlas(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """The builder, pointed at a throwaway cache + docs dir, with one brand."""
    mod = _module()
    cache_path = tmp_path / "cache.json"
    docs = tmp_path / "docs"
    docs.mkdir()
    monkeypatch.setattr(mod, "_CACHE_PATH", cache_path)
    monkeypatch.setattr(mod, "_ATLAS_DIR", docs)
    monkeypatch.setattr(mod, "_SUMMARY_PATH", docs / "_summary.md")
    monkeypatch.setattr(mod, "_CONFIG_PATH", tmp_path / "config.json")
    (tmp_path / "config.json").write_text(json.dumps({
        "brands": {"skoda": {
            "display_name": "Skoda",
            "package_id": "cz.skodaauto.myskoda",
            "sources": {"uptodown_subdomain": "x"},
            "expected_backend": "mysmob",
        }},
        "search_patterns": {},
    }), encoding="utf-8")

    def run(scrape_result: tuple[str | None, str | None]) -> dict[str, Any]:
        monkeypatch.setattr(mod, "scrape_version", lambda *a, **k: scrape_result)
        assert mod.main([]) == 0
        return json.loads(cache_path.read_text(encoding="utf-8"))["brands"]["skoda"]

    run.page = lambda: (docs / "skoda.md").read_text(encoding="utf-8")  # type: ignore[attr-defined]
    run.summary = lambda: (docs / "_summary.md").read_text(encoding="utf-8")  # type: ignore[attr-defined]
    run.mod = mod  # type: ignore[attr-defined]
    return run


class TestAFailedScrapeKeepsWhatWeKnew:
    def test_the_reported_case(self, atlas) -> None:
        """Skoda: known-good 8.14.0, then every source fails."""
        assert atlas(("8.14.0", "uptodown"))["last_version_name"] == "8.14.0"
        entry = atlas((None, None))
        assert entry["last_version_name"] == "8.14.0"
        assert entry["last_source"] == "uptodown"
        assert entry["last_status"] == "stale"

    def test_the_page_says_it_is_not_fresh(self, atlas) -> None:
        """Carrying the value silently would be its own kind of wrong: the
        number has to keep saying how old it is."""
        atlas(("8.14.0", "uptodown"))
        atlas((None, None))
        assert "(fetch failed)" not in atlas.page()
        assert "Not re-confirmed today" in atlas.page()
        assert "not re-confirmed" in atlas.summary()

    def test_confirmation_time_stops_moving_while_stale(self, atlas) -> None:
        confirmed = atlas(("8.14.0", "uptodown"))["last_confirmed_at"]
        assert atlas((None, None))["last_confirmed_at"] == confirmed

    def test_a_first_ever_failure_still_reports_failure(self, atlas) -> None:
        """With nothing cached there is nothing to protect, and pretending
        otherwise would invent a version."""
        entry = atlas((None, None))
        assert entry["last_version_name"] is None
        assert entry["last_status"] == "ok"
        assert "(fetch failed)" in atlas.page()

    def test_recovery_clears_the_mark(self, atlas) -> None:
        atlas(("8.14.0", "uptodown"))
        atlas((None, None))
        entry = atlas(("8.15.0", "google_play"))
        assert entry["last_version_name"] == "8.15.0"
        assert entry["last_status"] == "ok"
        assert "Not re-confirmed" not in atlas.page()


class TestAVersionDoesNotWalkBackwards:
    def test_the_reported_case(self, atlas) -> None:
        """CUPRA: cached 2.20.2, a listing serves 2.20.1."""
        atlas(("2.20.2", "google_play"))
        entry = atlas(("2.20.1", "google_play"))
        assert entry["last_version_name"] == "2.20.2"
        assert entry["last_status"] == "rejected"
        assert entry["last_rejected_reading"] == "2.20.1"

    def test_the_rejection_is_visible_not_swallowed(self, atlas) -> None:
        """Silently discarding a reading is how the opposite bug would ship."""
        atlas(("2.20.2", "google_play"))
        atlas(("2.20.1", "google_play"))
        assert "2.20.1" in atlas.page()
        assert "rejected" in atlas.summary()

    def test_going_forward_is_untouched(self, atlas) -> None:
        atlas(("2.20.2", "google_play"))
        assert atlas(("2.20.3", "google_play"))["last_version_name"] == "2.20.3"

    def test_a_date_scheme_moves_forward_normally(self, atlas) -> None:
        """myVW numbers by date; the comparator must not misread that."""
        atlas(("2026.5.27-9076", "apkmirror"))
        entry = atlas(("2026.7.28-9380", "google_play"))
        assert entry["last_version_name"] == "2026.7.28-9380"
        assert entry["last_status"] == "ok"

    def test_a_scheme_change_is_not_a_downgrade(self, atlas) -> None:
        """Comparing 5.0.0 against 2026.7.28-9380 is meaningless. An
        over-eager comparator would pin the brand on the old value forever."""
        atlas(("2026.7.28-9380", "google_play"))
        assert atlas(("5.0.0", "google_play"))["last_version_name"] == "5.0.0"


class TestTheComparatorRefusesRatherThanGuesses:
    @pytest.mark.parametrize("value", ["3.61.0-beta", "1.2.3.rc1", "varies", ""])
    def test_unparseable_values_have_no_ordering(self, atlas, value: str) -> None:
        assert atlas.mod.parse_version(value) is None

    @pytest.mark.parametrize(("new", "old", "expected"), [
        ("2.20.1", "2.20.2", True),
        ("2.20.3", "2.20.2", False),
        ("2.20.2", "2.20.2", False),
        ("2026.5.27-9076", "2026.7.28-9380", True),
        ("8.15", "8.14.0", False),          # different shape → no opinion
        ("3.61.0-beta", "3.61.0", False),   # unparseable → no opinion
    ])
    def test_ordering(self, atlas, new: str, old: str, expected: bool) -> None:
        assert atlas.mod.is_downgrade(new, old) is expected
