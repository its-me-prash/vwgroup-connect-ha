# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""v2.18.0 — the app-atlas polls Google Play first, not the third-party mirrors.

Two things drove this:

* **Volkswagen was never polled at all.** Its three mirror slugs all failed, so
  the cache carried `last_version_name: null, last_source: null` while the
  watcher faithfully recorded that it had checked, every single day. VW is the
  largest brand we serve. Google Play answers 4.1.1 for it.
* **Mirrors lag.** CUPRA sat at 2.18.1 on Uptodown while Play (and the actual
  store) had 2.19.1.

Play needs no account for this — the store page serves the version to an
anonymous request — so nothing lands in CI secrets.

The mirrors stay wired as a fallback: VW-NA and Porsche publish no version on
their listings, and Play reshuffles its markup from time to time.

Fixtures below are trimmed from real page bodies fetched on 2026-07-17.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "app_atlas"))

import build_atlas  # noqa: E402


# The real version field, as it appears on the VW listing.
_PLAY_WITH_VERSION = 'x"]],1],null,null,null,[[["4.1.1"]],[[[37]],[[[29,"1'

# The trap. Play records which app version each reviewer was running, in a
# shape that looks exactly like a version field and appears ~20x per page.
# Matching it would report a random reviewer's version as current.
_PLAY_REVIEW_METADATA = (
    'aEQ"]]],"2.7.0",null,null,x'
    'aEQ"]]],"3.60.2",null,null,x'
    'aEQ"]]],"2.12.2",null,null,x'
)


def _stub_fetch(monkeypatch: pytest.MonkeyPatch, body: str | Exception) -> None:
    def _fake(url: str, *a: object, **k: object) -> str:
        if isinstance(body, Exception):
            raise body
        return body

    monkeypatch.setattr(build_atlas, "_fetch", _fake)


class TestGooglePlayScrape:
    def test_reads_the_version_field(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _stub_fetch(monkeypatch, _PLAY_WITH_VERSION)
        assert build_atlas._try_google_play("com.volkswagen.weconnect") == "4.1.1"

    def test_review_metadata_is_not_mistaken_for_the_version(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # A page carrying ONLY review metadata must yield nothing, not "2.7.0".
        _stub_fetch(monkeypatch, _PLAY_REVIEW_METADATA)
        assert build_atlas._try_google_play("com.seat.connectedcar") is None

    def test_varies_with_device_is_not_a_version(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _stub_fetch(monkeypatch, 'Varies with device [[["9.9.9"]]')
        assert build_atlas._try_google_play("com.example.app") is None

    def test_network_failure_is_swallowed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Must degrade to the mirrors, never take the workflow down.
        _stub_fetch(monkeypatch, RuntimeError("boom"))
        assert build_atlas._try_google_play("com.example.app") is None


class TestSourceOrder:
    def test_play_wins_and_the_mirrors_are_not_called(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        called: list[str] = []
        monkeypatch.setattr(build_atlas, "_try_google_play", lambda p: "4.1.1")
        for name in ("_try_apkmirror", "_try_uptodown", "_try_apkcombo"):
            monkeypatch.setattr(
                build_atlas, name, lambda s, _n=name: called.append(_n) or "0.0.1"
            )

        version, source = build_atlas.scrape_version(
            "volkswagen",
            {"package_id": "com.volkswagen.weconnect", "apkmirror_slug": "vw/x"},
        )
        assert (version, source) == ("4.1.1", "google_play")
        assert called == []

    def test_falls_back_to_mirrors_when_play_has_no_version(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # This is Porsche and VW-NA: no version on the listing at all.
        monkeypatch.setattr(build_atlas, "_try_google_play", lambda p: None)
        monkeypatch.setattr(build_atlas, "_try_apkmirror", lambda s: "12.24.27")

        version, source = build_atlas.scrape_version(
            "porsche", {"package_id": "com.porsche.one", "apkmirror_slug": "p/one"}
        )
        assert (version, source) == ("12.24.27", "apkmirror")

    def test_brand_without_package_id_still_uses_mirrors(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            build_atlas,
            "_try_google_play",
            lambda p: pytest.fail("Play must not be called without a package_id"),
        )
        monkeypatch.setattr(build_atlas, "_try_apkmirror", lambda s: "1.2.3")

        assert build_atlas.scrape_version("x", {"apkmirror_slug": "a/b"}) == (
            "1.2.3",
            "apkmirror",
        )


def test_every_brand_carries_a_package_id() -> None:
    # Play is keyed by package_id. A brand missing one silently drops to the
    # mirrors — which is exactly how VW went unpolled for months.
    import json

    cfg = json.loads(
        (Path(__file__).resolve().parents[1] / "scripts/app_atlas/config.json").read_text(
            encoding="utf-8"
        )
    )
    missing = [b for b, c in cfg["brands"].items() if not c.get("package_id")]
    assert missing == [], f"brands with no package_id: {missing}"
