# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""v2.18.0 — the app-atlas polls Google Play, not the third-party mirrors.

Two things drove this:

* **Volkswagen was never polled at all.** Its three mirror slugs all failed, so
  the cache carried `last_version_name: null, last_source: null` while the
  watcher faithfully recorded that it had checked, every single day. VW is the
  largest brand we serve. Google Play answers 4.1.1 for it.
* **Mirrors lag.** CUPRA sat at 2.18.1 on Uptodown while Play (and the actual
  store) had 2.19.1.

Play needs no account for this — the store page serves the version to an
anonymous request — so nothing lands in CI secrets.

2026-10-17: the mirrors are gone entirely, so Play is the only source for the
version as well as for the APK. They were not pulled because one of them broke
— they were pulled because a mirror answers from whatever it last ingested, and
a reading that lags the store is worse than none: ``is_downgrade()`` then has a
stale ceiling to compare against. Measured on the day they were removed, six of
the eight builds answer from Play; both Porsche packages publish no version at
all and are now reported as such instead of being filled in from elsewhere.

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

    # ── semver build metadata ───────────────────────────────────────────────
    #
    # This family cost three weeks of silent staleness on both Porsche entries,
    # and the pattern was only ever tested against a plain ``4.1.1``. The real
    # listings publish ``21.26.44-pcna+193583`` and ``21.26.44-row+193583``:
    # the old pattern consumed ``-pcna`` and then demanded the closing quote, so
    # the ``+193583`` broke the match. The watcher reported "Google Play
    # published no version", and somebody wrote that down as a fact about the
    # STORE rather than about our parser.
    #
    # Measured against the live listings on 2026-10-28, so these are real
    # strings rather than invented ones.
    @pytest.mark.parametrize(
        ("version", "package"),
        [
            ("21.26.44-pcna+193583", "com.porsche.one"),
            ("21.26.44-row+193583", "de.porsche.one"),
            ("20.26.37-pcna+188460", "com.porsche.one"),   # an older real reading
            ("1.2.3+build.7", "com.example.dotted"),       # dotted build metadata
            ("1.2.3+build-7", "com.example.hyphen"),       # hyphenated
        ],
        ids=["porsche-na", "porsche-row", "porsche-older", "dotted", "hyphenated"],
    )
    def test_build_metadata_does_not_break_the_version(
        self, monkeypatch: pytest.MonkeyPatch, version: str, package: str
    ) -> None:
        _stub_fetch(monkeypatch, f'x"]],1],null,null,null,[[["{version}"]],[[[37]]')
        assert build_atlas._try_google_play(package) == version

    @pytest.mark.parametrize(
        "version",
        ["2.23.1", "4.1.1", "2026.9.29-9674"],
        ids=["plain", "plain-short", "prerelease-no-build"],
    )
    def test_the_shapes_that_already_worked_still_do(
        self, monkeypatch: pytest.MonkeyPatch, version: str
    ) -> None:
        """Widening a pattern is where a regression hides. ``2026.9.29-9674`` is
        the real VW-NA shape and has no build metadata at all."""
        _stub_fetch(monkeypatch, f'x"]],1],null,null,null,[[["{version}"]],[[[37]]')
        assert build_atlas._try_google_play("com.example.app") == version

    def test_a_plus_outside_the_version_slot_is_not_picked_up(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The widened pattern must not start matching things that merely
        contain a ``+``. Only the bracket slot counts."""
        _stub_fetch(monkeypatch, 'some+thing "1.2.3+9" null,null,x')
        assert build_atlas._try_google_play("com.example.app") is None

    def test_the_build_metadata_group_does_not_run_past_the_version(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A greedy build-metadata group would swallow everything up to the LAST
        closing bracket on the page and return it as the version. A short clean
        fixture cannot show that, so this one carries a second ``"]]`` after the
        version slot, exactly as a real listing does.
        """
        _stub_fetch(
            monkeypatch,
            'x"]],1],[[["21.26.44-pcna+193583"]],[[[37]],[[[29,"1.2.3"]],x',
        )
        assert build_atlas._try_google_play("com.porsche.one") == "21.26.44-pcna+193583"

    def test_the_software_version_fallback_also_takes_build_metadata(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The second pattern is the documented escape hatch for when the bracket
        markup moves. It needs the same build-metadata tolerance, or the fallback
        would fail on exactly the listings the primary pattern just learned to
        read. Fixture carries no bracket slot, so only the fallback can answer.
        """
        _stub_fetch(monkeypatch, 'null,"softwareVersion": "21.26.44-row+193583",null')
        assert build_atlas._try_google_play("de.porsche.one") == "21.26.44-row+193583"

    def test_the_absent_slot_is_still_reported_as_no_version(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Skoda's listing answers 200 with no version in that slot at all, which
        is a DIFFERENT cause from the Porsche one and must stay distinguishable:
        no version, rather than a wrong one."""
        _stub_fetch(monkeypatch, 'x"]],1],null,null,null,[[[37]],[[[29,"1')
        assert build_atlas._try_google_play("cz.skodaauto.myskoda") is None

    def test_network_failure_is_swallowed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Must report no version, never take the workflow down.
        _stub_fetch(monkeypatch, RuntimeError("boom"))
        assert build_atlas._try_google_play("com.example.app") is None


class TestSourceOrder:
    """There is no order left to test — Play is the only source. What these
    pin instead is that the removed tiers did not leave a stub behind, and
    that the two states the mirrors used to paper over are now reported as
    what they are."""

    def test_play_is_the_only_source(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(build_atlas, "_try_google_play", lambda p: "4.1.1")
        version, source = build_atlas.scrape_version(
            "volkswagen", "com.volkswagen.weconnect"
        )
        assert (version, source) == ("4.1.1", "google_play")
        for gone in ("_try_apkmirror", "_try_uptodown", "_try_apkcombo"):
            assert not hasattr(build_atlas, gone), f"{gone} is importable again"

    def test_no_version_on_the_listing_is_reported_as_none(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Both Porsche packages, measured 2026-10-17: Play publishes no
        version for them. That now yields None, which the caller renders as a
        retained reading. A mirror's answer here would have been a number
        nobody had checked against the store."""
        monkeypatch.setattr(build_atlas, "_try_google_play", lambda p: None)
        assert build_atlas.scrape_version("porsche", "com.porsche.one") == (None, None)

    def test_a_brand_without_a_package_id_is_not_polled(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            build_atlas,
            "_try_google_play",
            lambda p: pytest.fail("Play must not be called without a package_id"),
        )
        assert build_atlas.scrape_version("x", None) == (None, None)


def test_every_brand_carries_a_package_id() -> None:
    # Play is keyed by package_id, and it is the only source. A brand missing
    # one cannot be polled at all — it is the whole source identity now.
    import json

    cfg = json.loads(
        (Path(__file__).resolve().parents[1] / "scripts/app_atlas/config.json").read_text(
            encoding="utf-8"
        )
    )
    missing = [b for b, c in cfg["brands"].items() if not c.get("package_id")]
    assert missing == [], f"brands with no package_id: {missing}"
