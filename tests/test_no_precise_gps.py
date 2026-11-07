# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The coordinate guard has to actually catch things, and stay narrow.

CONTRIBUTING.md forbids "Exact GPS coordinates (more than 1 decimal place)" in
the repo, "even from your own car", and it binds maintainers too. Nothing
enforced it until #1378 turned up a reporter's parked position in the source and
in a test, two months after the same value had been redacted out of the issue it
arrived in. `scripts/check_no_precise_gps.py` is the enforcement; this is the
test that it works.

Three things are tested, and the first matters more than it looks:

1. **The guard can fail.** A check that silently accepts everything passes its
   own regression test forever while protecting nothing — the shape of several
   bugs this project has already paid for. So there are positive cases that MUST
   be refused.

2. **The guard stays narrow.** Two decimals side by side is an ordinary shape in
   telemetry fixtures, so the guard requires a coordinate word nearby. If that
   narrowing ever stops working the guard starts refusing temperature pairs, gets
   switched off, and protects nothing again. Both directions are pinned.

3. **Nothing new creeps into the tree.** As a file-set ratchet rather than a
   count: an exact number taken from the tree goes red on every healthy edit.
   A ratchet alone is not enough either — if the pattern broke, the finding set
   would shrink to nothing and a subset check would pass. So the instrument has
   to still see the known baseline as well.

The positive fixtures are assembled from fragments at run time, like the VIN
guard's test next door, so the file that proves the guard refuses a
precise-looking pair is not itself the file that writes one down. There is no
skip entry for this file: a guard with a self-exemption has its blind spot
exactly where the awkward cases accumulate.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from check_no_precise_gps import (  # noqa: E402
    _SKIP_FILES,
    looks_synthetic,
    scan,
)

_ROOT = Path(__file__).resolve().parents[1]

# Assembled, so no contiguous precise pair is written in this file. Each half is
# a plausible-looking decimal that announces nothing.
_LAT_REAL = "51." + "50" + "7351"
_LON_REAL = "0." + "12" + "7758"
_LAT_REAL_2 = "40." + "71" + "2776"
_LON_REAL_2 = "-74." + "00" + "5974"


def _write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "fixture.py"
    path.write_text(text, encoding="utf-8")
    return path


# ── 1. the guard can fail ───────────────────────────────────────────────────
def test_a_precise_pair_in_coordinate_context_is_refused(tmp_path: Path) -> None:
    path = _write(tmp_path, f'LOCATION = "{_LAT_REAL},{_LON_REAL}"\n')
    findings = scan([path])
    assert len(findings) == 1, findings
    assert findings[0][2] == _LAT_REAL
    assert findings[0][3] == _LON_REAL


def test_looks_synthetic_says_no_to_an_ordinary_looking_pair() -> None:
    assert not looks_synthetic(_LAT_REAL, _LON_REAL, "position")
    assert not looks_synthetic(_LAT_REAL_2, _LON_REAL_2, "gps location")


def test_both_halves_have_to_be_invented() -> None:
    """Half a real pair is still half of somebody's address."""
    assert not looks_synthetic("48." + "123456", _LON_REAL, "lat/lon")
    assert not looks_synthetic(_LAT_REAL, "16." + "654321", "lat/lon")
    assert looks_synthetic("48." + "123456", "16." + "654321", "lat/lon")


# ── 2. the guard stays narrow ──────────────────────────────────────────────
def test_without_a_coordinate_word_nothing_is_reported(tmp_path: Path) -> None:
    """A temperature or voltage pair must not be mistaken for a position."""
    path = _write(tmp_path, 'READINGS = ["21.5075", "0.1278"]\n')
    assert scan([path]) == []


def test_with_a_coordinate_word_the_same_numbers_are_reported(tmp_path: Path) -> None:
    """Positive control for the test above: the numbers are findable, the word
    is what decides. Without this pair of tests the narrowing could be broken
    in either direction and one of them would still pass."""
    path = _write(tmp_path, f'READINGS = ["{_LAT_REAL}", "{_LON_REAL}"]\n')
    assert scan([path]) == []          # not adjacent -> not a pair
    path2 = _write(tmp_path, f'GPS = "{_LAT_REAL}, {_LON_REAL}"\n')
    assert len(scan([path2])) == 1


def test_the_word_may_sit_up_to_two_lines_above(tmp_path: Path) -> None:
    path = _write(tmp_path, f'# parking position\n#\nVALUE = "{_LAT_REAL},{_LON_REAL}"\n')
    assert len(scan([path])) == 1
    far = _write(tmp_path, f'# parking position\n#\n#\nVALUE = "{_LAT_REAL},{_LON_REAL}"\n')
    assert scan([far]) == []


def test_one_decimal_is_what_the_rule_asks_for(tmp_path: Path) -> None:
    path = _write(tmp_path, 'GPS = "48.1, 11.6"\n')
    assert scan([path]) == []


def test_out_of_bounds_numbers_are_not_a_position(tmp_path: Path) -> None:
    path = _write(tmp_path, 'location = "95.507351, 191.127758"\n')
    assert scan([path]) == []


def test_visibly_invented_decimals_pass() -> None:
    for lat, lon in (
        ("48." + "123456", "16." + "654321"),   # sequential runs
        ("50." + "333300", "4." + "444400"),    # four identical
        ("48." + "000000", "11." + "000000"),   # rounded, padded
    ):
        assert looks_synthetic(lat, lon, "gps"), (lat, lon)


def test_a_marker_word_on_the_line_is_enough() -> None:
    assert looks_synthetic(_LAT_REAL, _LON_REAL, "SAMPLE position")
    assert looks_synthetic(_LAT_REAL, _LON_REAL, "# synthetic coordinates")


# ── 3. the tree ─────────────────────────────────────────────────────────────
#: Files that already held a non-synthetic pair when the guard was written. All
#: of them are public landmarks used as test input — see the script's docstring
#: for why they were left alone rather than normalised or exempted.
#: Counted per file, not just listed, and compared with ``<=``. A set of file
#: names would let a new pair into a file that already has one, which is the
#: likeliest way the next one arrives — somebody extends an existing fixture.
#: A ratchet on the count blocks that and still allows cleaning up.
_BASELINE = {
    "custom_components/vag_connect/companion/presets.py": 3,
    "tests/test_923_authproxy_parkingposition_prep.py": 1,
    "tests/test_968_companion_id3_nav.py": 5,
    "tests/test_porsche_command_protocol.py": 1,
    "tests/test_porsche_measurement_keys.py": 1,
    "tests/test_skoda_send_destination.py": 1,
    "tests/test_v1242_porsche_vw_na_parity.py": 1,
}


def _tree_counts() -> dict[str, int]:
    counts: dict[str, int] = {}
    for path in _tree_findings_raw():
        counts[path] = counts.get(path, 0) + 1
    return counts


def _tree_findings_raw() -> list[str]:
    # stdin=DEVNULL is not decoration: under pytest on Windows a subprocess
    # without it dies with "WinError 6, the handle is invalid", because pytest
    # has replaced the inherited stdin. The VIN guard's test next door carries
    # the same line for the same reason.
    out = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
        cwd=_ROOT, capture_output=True, text=True, check=True,
        stdin=subprocess.DEVNULL,
    ).stdout.splitlines()
    paths = [_ROOT / p for p in out if p]
    return [f[0].relative_to(_ROOT).as_posix() for f in scan(paths)]


def test_nothing_adds_a_precise_pair_anywhere() -> None:
    counts = _tree_counts()
    neue_dateien = sorted(set(counts) - set(_BASELINE))
    assert not neue_dateien, (
        "new file(s) with a coordinate pair that does not look invented: "
        f"{neue_dateien} — use visibly made-up digits, or round to one decimal"
    )
    gewachsen = {
        datei: (anzahl, _BASELINE[datei])
        for datei, anzahl in counts.items()
        if anzahl > _BASELINE[datei]
    }
    assert not gewachsen, (
        f"more coordinate pairs than before: {gewachsen} (found, allowed). "
        "A fixture gained one — make its digits visibly made up."
    )


def test_the_instrument_still_sees_the_baseline() -> None:
    """Without this the ratchet above would pass on a broken pattern: nothing
    found is trivially 'not more than before'."""
    counts = _tree_counts()
    assert counts, "the guard found nothing at all — check the pattern"
    # The two biggest holders are the ones to notice disappearing silently.
    assert counts.get("tests/test_968_companion_id3_nav.py", 0) >= 1
    assert counts.get("custom_components/vag_connect/companion/presets.py", 0) >= 1
    assert sum(counts.values()) >= 10, counts


def test_the_guard_does_not_exempt_its_own_test() -> None:
    assert "tests/test_no_precise_gps.py" not in _SKIP_FILES
    assert _SKIP_FILES == {"scripts/check_no_precise_gps.py"}


class TestTheGateIsActuallyWired:
    """The script existed and ran clean; nothing invoked it.

    Until 2026-11-05 ``check_no_precise_gps.py`` was referenced by no workflow
    and no hook — a guard whose only reader was its own unit test. Its sibling
    ``check_no_real_vins.py`` has sat in ``ci.yml`` since it was written, and
    the difference was not a decision: the VIN tree scans clean, so the audit
    form works there, while this tree holds 13 deliberate pairs and an audit
    run would fail on every commit. A required check that always fails gets
    deleted, so the gate needed the ``--base`` form before it could be required.

    This class holds the three properties that form actually depends on. Each
    one, removed, turns the gate into something that cannot refuse anything —
    and the comment in the workflow would not stop it, which is why the test
    exists instead of only the comment.
    """

    WF = _ROOT / ".github" / "workflows" / "ci.yml"

    def _text(self) -> str:
        return self.WF.read_text(encoding="utf-8")

    def _invocations(self) -> list[str]:
        return [
            ln for ln in self._text().splitlines()
            if "check_no_precise_gps.py" in ln and not ln.lstrip().startswith("#")
        ]

    def test_the_workflow_invokes_the_gate(self) -> None:
        assert self._invocations(), (
            "ci.yml no longer runs scripts/check_no_precise_gps.py. The script "
            "then guards nothing but itself, which is the state this class was "
            "written to end."
        )

    def test_every_invocation_passes_a_baseline(self) -> None:
        """Without ``--base`` the run is an audit and fails on the 13 known
        pairs, every time, on every branch. That is the shape that gets a step
        commented out a week later."""
        for ln in self._invocations():
            assert "--base" in ln, (
                f"invoked without a baseline: {ln.strip()!r}. The tracked tree "
                "holds 13 deliberate pairs (public landmarks, named in the "
                "script's docstring), so an audit run cannot pass."
            )

    def test_the_checkout_is_not_shallow(self) -> None:
        """``--base`` needs history. The default checkout has depth 1 and no
        origin/main, and the gate is deliberately loud about a missing baseline
        rather than permissive — so a shallow checkout breaks every run.

        **Comment lines are excluded, and that is the whole point of this
        method.** The first version asserted the string anywhere in the job
        head and passed with the setting deleted, because the explanatory
        comment above the checkout names ``fetch-depth: 0`` itself. The test was
        satisfied by its own documentation — proven by removing the setting and
        watching it stay green.
        """
        head = self._text().split("- name: Python 3.14 einrichten", 1)[0]
        wirksam = [
            ln for ln in head.splitlines()
            if "fetch-depth" in ln and not ln.lstrip().startswith("#")
        ]
        assert wirksam, (
            "the lint-and-validate checkout lost fetch-depth: 0 on an effective "
            "line, so the GPS gate has no baseline to diff against. A mention "
            "in a comment does not configure anything."
        )
        assert any("0" in ln.split(":", 1)[1] for ln in wirksam), (
            f"fetch-depth is set but not to 0: {wirksam!r}"
        )

    def test_a_direct_push_does_not_compare_against_itself(self) -> None:
        """On a push to main, origin/main is the new HEAD: merge-base returns
        HEAD, the diff is empty and the gate passes on anything. The commit the
        branch pointed at before the push is the only honest baseline there, so
        the step has to distinguish the two event kinds."""
        step = self._text().split("Keine präzisen GPS-Koordinaten", 1)
        assert len(step) == 2, "the GPS step was renamed or removed"
        body = step[1]
        assert "github.event.before" in body, (
            "the step no longer uses the pushed-from commit as the baseline on "
            "a push, so a direct push to main would compare main against "
            "itself and the gate would accept any coordinate"
        )
        assert "github.event_name" in body, (
            "the step no longer distinguishes push from pull_request"
        )
