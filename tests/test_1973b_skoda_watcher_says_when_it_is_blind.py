# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The Škoda official-API watcher had no tests, and it went blind unnoticed.

Measured on 2026-11-01. The watcher printed ``FOUND 8.17.0`` as late as
2026-10-25 and ``FOUND none`` on every run from 2026-10-29 onward — eight
consecutive runs at the time of measurement, each concluding **success**. It
never saw 8.18.0, which was on the device that day. The last tracking issue it
ever filed stops at 8.17.0 (#1438, 2026-09-23).

Two separate defects, and the second is the one that mattered:

1. ``_VER_RE`` had the major version hardcoded to ``8``, so a 9.x release would
   have been invisible — the same failure a second time, in a different place.
2. Fail-soft printed a negative and exited 0, which is indistinguishable from
   "nothing new" unless somebody reads the log of a green scheduled run. Nobody
   does.

Deliberately NOT done, because measuring refuted it: widening the pattern onto
the Play page body. The listing carries no parseable version slot any more
(neither of the atlas scraper's patterns matches a 1.17 MB body), while the page
*does* contain 8.16.0, 8.15.0 and 8.14.0 as review metadata. A pattern over
those reports a version several releases behind reality as current — worse than
none, because it is confident.
"""
from __future__ import annotations

import importlib.util
import re
from pathlib import Path
from typing import Any

import pytest

_ROOT = Path(__file__).resolve().parent.parent
_SCRIPT = _ROOT / "scripts" / "skoda_official_watch.py"
_WF = _ROOT / ".github" / "workflows" / "skoda-official-api-watch.yml"


def _load() -> Any:
    spec = importlib.util.spec_from_file_location("_skoda_watch", _SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


watch = _load()


class TestTheVersionPatternIsNotPinnedToMajorEight:
    """Defect 1. The regression this class exists for is a 9.x release."""

    @pytest.mark.parametrize("raw", ["9.0.0", "9.18.3", "10.0.1", "12.34.56"])
    def test_a_later_major_is_read(self, raw: str) -> None:
        m = watch._VER_RE.match(raw)
        assert m, f"{raw} was not read — a major past 8 is invisible again"

    def test_the_old_hardcoded_pattern_would_have_missed_it(self) -> None:
        """Positive control for the claim above, so it is not just an assertion."""
        old = re.compile(r"\b(8\.\d{1,2}\.\d{1,2})\b")
        assert old.search("9.0.0") is None
        assert watch._VER_RE.match("9.0.0") is not None

    def test_eight_point_x_still_reads(self) -> None:
        assert watch._VER_RE.match("8.18.0").group(1) == "8.18.0"

    def test_a_suffixed_version_parses_to_its_three_numbers(self) -> None:
        """Porsche's listing answers "21.26.44-row+193583". Anchored at the
        start, so the suffix is ignored rather than rejecting the whole value."""
        assert watch._VER_RE.match("21.26.44-row+193583").group(1) == "21.26.44"

    def test_rubbish_is_still_rejected(self) -> None:
        for raw in ("", "none", "Varies with device", "8.18"):
            assert watch._VER_RE.match(raw) is None, raw


class TestBlindIsNotTheSameClaimAsNoTrigger:
    """Defect 2, the one that let a week pass unnoticed."""

    @staticmethod
    def _run(monkeypatch: pytest.MonkeyPatch, version: Any) -> list[str]:
        monkeypatch.setattr(watch, "_package_id", lambda: "cz.skodaauto.myskoda")
        monkeypatch.setattr(watch, "_play_version", lambda _pkg: version)
        monkeypatch.setattr(watch.time, "sleep", lambda _s: None)
        import io
        import contextlib

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = watch.main()
        assert rc == 0, "the watcher must never take the workflow down"
        return buf.getvalue().strip().splitlines()

    def test_an_unreadable_source_says_blind(self, monkeypatch: pytest.MonkeyPatch) -> None:
        lines = self._run(monkeypatch, None)
        assert lines == ["FOUND none", "NO-TRIGGER", "BLIND"]

    def test_a_version_below_the_trigger_says_seeing_not_blind(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The distinction the whole change is about: "read it, too old" must
        not look like "could not read it"."""
        lines = self._run(monkeypatch, (8, 15, 0))
        assert lines == ["FOUND 8.15.0", "NO-TRIGGER", "SEEING"]

    def test_a_version_at_or_above_the_trigger_triggers(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        assert self._run(monkeypatch, (8, 16, 0)) == ["FOUND 8.16.0", "TRIGGER", "SEEING"]
        assert self._run(monkeypatch, (8, 18, 0)) == ["FOUND 8.18.0", "TRIGGER", "SEEING"]

    def test_a_later_major_triggers_too(self, monkeypatch: pytest.MonkeyPatch) -> None:
        assert self._run(monkeypatch, (9, 0, 0))[1] == "TRIGGER"

    def test_main_goes_through_the_retry_rather_than_round_it(self) -> None:
        """Structural, and deliberately not a live run.

        This repo has no network tests — measured, there is no marker and no
        skip convention for one — so adding the first would make every suite
        run fetch a 1.17 MB page from Google. The live behaviour was checked by
        hand instead (2026-11-01: FOUND none / NO-TRIGGER / BLIND, exit 0).

        What is worth pinning without the network is that ``main`` cannot
        bypass the retry: calling ``_play_version`` directly would make a
        single blip file an issue again.
        """
        src = _SCRIPT.read_text(encoding="utf-8")
        body = src[src.index("def main()"):]
        assert body.count("_read_with_retry(") == 1
        assert "_play_version(" not in body, (
            "main must not call _play_version directly — that skips the retry"
        )


class TestABlipDoesNotFileAnIssue:
    def test_a_single_failure_is_retried(self, monkeypatch: pytest.MonkeyPatch) -> None:
        calls: list[int] = []

        def _flaky(_pkg: str) -> tuple[int, int, int] | None:
            calls.append(1)
            return None if len(calls) == 1 else (8, 18, 0)

        monkeypatch.setattr(watch, "_play_version", _flaky)
        got = watch._read_with_retry("pkg", sleep=0)
        assert got == (8, 18, 0)
        assert len(calls) == 2

    def test_a_persistent_failure_is_reported(self, monkeypatch: pytest.MonkeyPatch) -> None:
        calls: list[int] = []

        def _dead(_pkg: str) -> None:
            calls.append(1)
            return None

        monkeypatch.setattr(watch, "_play_version", _dead)
        assert watch._read_with_retry("pkg", sleep=0) is None
        assert len(calls) == watch._ATTEMPTS, (
            "every attempt must be spent before declaring blindness"
        )

    def test_a_first_time_success_costs_one_request(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The retry must not double the load on a healthy source."""
        calls: list[int] = []
        monkeypatch.setattr(
            watch, "_play_version",
            lambda _pkg: (calls.append(1), (8, 18, 0))[1],
        )
        assert watch._read_with_retry("pkg", sleep=0) == (8, 18, 0)
        assert len(calls) == 1


class TestTheWorkflowWiring:
    """The script can only say BLIND; the workflow is what makes it visible."""

    @staticmethod
    def _wf() -> str:
        return _WF.read_text(encoding="utf-8")

    def test_the_sight_token_is_captured(self) -> None:
        wf = self._wf()
        assert wf.count("sight=$sight") == 1
        assert "grep -E '^(SEEING|BLIND)$'" in wf

    def test_a_step_is_gated_on_blind(self) -> None:
        wf = self._wf()
        assert wf.count("steps.check.outputs.sight == 'BLIND'") == 1, (
            "exactly one step may fire on blindness"
        )

    def test_the_blind_step_dedups_on_open_issues_only(self) -> None:
        """The deliberate asymmetry, and the reason it is a test.

        The version-trigger step de-dups across ALL states, because a closed
        issue there means "this version was evaluated". The blind step must
        de-dup on OPEN only, because a closed issue there means "the watcher
        was repaired" — so a later blindness is a NEW fault and has to re-file.
        Getting these the same way round silently disables one of them.
        """
        wf = self._wf()
        blind_at = wf.index("steps.check.outputs.sight == 'BLIND'")
        trigger_at = wf.index("steps.check.outputs.state == 'TRIGGER'")
        assert blind_at < trigger_at, "the blind step is expected first"
        blind_block = wf[blind_at:trigger_at]
        trigger_block = wf[trigger_at:]
        assert "--state open" in blind_block
        assert "--state all" in trigger_block
        assert "--state all" not in blind_block
        assert "--state open" not in trigger_block

    def test_the_blind_step_does_not_fail_the_job(self) -> None:
        """Every 4 hours means a red run would be six a day and then muted."""
        wf = self._wf()
        blind_at = wf.index("steps.check.outputs.sight == 'BLIND'")
        trigger_at = wf.index("steps.check.outputs.state == 'TRIGGER'")
        assert "exit 1" not in wf[blind_at:trigger_at]

    def test_the_issue_body_says_blind_is_not_no_new_version(self) -> None:
        """The whole point has to reach the person who reads the issue."""
        wf = self._wf()
        assert 'not "no new version"' in wf or "not \"no new version\"" in wf
