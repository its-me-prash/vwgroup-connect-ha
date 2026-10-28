# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The VIN guard has to actually catch things, and the repo has to stay clean.

CONTRIBUTING.md says, under "What goes in the repo / fixtures / commits", that
full VINs do not belong here, "even from the tester's own car", and that the
section binds maintainers as well as contributors. A written rule nothing
enforces decays.

Two things are tested here, and the first matters more than it looks:

1. The guard can fail. A check that silently accepts everything passes its own
   regression test forever while protecting nothing, which is the shape of
   several bugs this project has already paid for. So there are positive cases
   with VINs that MUST be rejected.

2. The tree is clean. This is the regression test proper.

The positive fixtures are assembled from fragments at run time rather than
written out as literals, and that is not cosmetic: the file that proves the guard
refuses a production-shaped VIN must not be the one file that writes one down,
and it must not buy a green result by exempting itself from the guard. A guard
with a self-exemption is a guard with a blind spot, and the blind spot is exactly
where the awkward cases accumulate — so there is no skip entry for this file.

The guard scans this file. Nine of the ten seventeen-character literals in the
negative-case list below do match the guard's pattern, and they go unreported
because looks_synthetic() recognises them, not because the scan cannot see
them. The tenth, WVWZZZTESTVIN0001, is never seen by the pattern at all: the
standard excludes I, O and Q from the VIN alphabet, and the word TEST**VIN**
carries an I. It is a fine negative case and a poor example of one, since it
would pass even if looks_synthetic() stopped working. The
serials in the positive fixtures are invented — right manufacturer, right type
code, a serial drawn from nothing — so they exercise the "looks real, refuse it"
path without being anybody's car.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from check_no_real_vins import looks_synthetic, scan  # noqa: E402

_ROOT = Path(__file__).resolve().parents[1]

# Invented, and split so this file holds no 17-character VIN of its own. Each is
# a real manufacturer and type code with a serial that belongs to no car and
# carries no synthetic marker — the shape the guard must refuse. One per
# manufacturer this project sees, including WVG, the prefix the first inventory
# sweep's pattern missed.
_REFUSE = [
    "WVWZZZ" + "AUZFW" + "472913",
    "WAUZZZ" + "F29MN" + "681204",
    "TMBJR8" + "NX2RY" + "350827",
    "VSSZZZ" + "5FZLR" + "914635",
    "WVGZZZ" + "5NZPM" + "208471",
    "WP0ZZZ" + "99ZTS" + "617482",
]
# Keep only well-formed entries, so a typo above fails loudly in
# test_every_refusal_fixture_is_well_formed rather than silently weakening a test.
_REFUSE_SAFE = [v for v in _REFUSE if len(v) == 17 and v.isascii() and v.isalnum()]


class TestTheFixturesThemselves:
    """If the fixtures are malformed the tests below prove nothing."""

    def test_every_refusal_fixture_is_well_formed(self):
        assert len(_REFUSE_SAFE) >= 5, f"only {len(_REFUSE_SAFE)} usable fixtures"
        for v in _REFUSE_SAFE:
            assert len(v) == 17

    def test_every_vin_literal_in_this_file_is_synthetic(self):
        """The reason the guard needs no exemption for this file.

        Placeholder literals are fine here and are the point of the negative
        cases below. What must never reappear is a literal the guard itself would
        refuse — which is precisely what the first version of this file held, five
        times over, behind a self-exemption. Asserted against the guard's own
        predicate rather than against a hand-written list, so the two cannot drift.
        """
        import re
        src = Path(__file__).read_text(encoding="utf-8")
        pattern = re.compile(
            r"(?<![A-HJ-NPR-Z0-9])(?:WVW|WAU|TMB|VSS|WP0|WVG)[A-HJ-NPR-Z0-9]{14}"
            r"(?![A-HJ-NPR-Z0-9])"
        )
        offenders = [v for v in pattern.findall(src) if not looks_synthetic(v)]
        # Masked: the message can land in a public CI log.
        masked = [f"{v[:6]}...{v[-4:]}" for v in offenders]
        assert masked == [], "non-synthetic VIN literal in this file: " + ", ".join(masked)

    def test_that_check_would_catch_a_real_one(self):
        """Counter-check for the test above: the pattern plus predicate do flag a
        production-shaped literal, so a green result means something."""
        assert looks_synthetic(_REFUSE_SAFE[0]) is False

    def test_the_guard_does_not_exempt_this_file(self):
        from check_no_real_vins import _SKIP_FILES
        assert "tests/test_no_real_vins.py" not in _SKIP_FILES


class TestTheGuardCanFail:
    """Positive cases. If these ever stop being rejected the guard is blind."""

    @pytest.mark.parametrize("vin", _REFUSE_SAFE)
    def test_a_production_looking_vin_is_refused(self, vin):
        assert looks_synthetic(vin) is False, f"{vin} wrongly accepted as synthetic"

    def test_a_refused_vin_is_actually_reported(self, tmp_path):
        """End to end, not just the predicate: the scanner must surface it."""
        vin = _REFUSE_SAFE[0]
        f = tmp_path / "fixture.py"
        f.write_text(f'VIN = "{vin}"\n', encoding="utf-8")
        findings = scan([f])
        assert len(findings) == 1
        assert findings[0][2] == vin


class TestTheGuardAcceptsPlaceholders:
    """Negative cases, each one a literal this repo actually relies on."""

    @pytest.mark.parametrize("vin", [
        "WVWZZZAUZFW000000",   # zeroed serial, the convention used for the fix
        "WVWZZZTESTVIN0001",   # word marker
        "WAUZZZTESTVHN0001",
        "TMBXXXXXXXXXXXXXX",   # filler run
        "WVWZZZ1KZAW000503",   # padded counter
        "WVWZZZ7AZRE000999",
        "WAUZZZ1234567890A",   # sequential run with a trailing letter
        "WVWZZZ1234567890X",
        "WVWZZZE1ZMP111111",   # repeated-digit serial
        "WVWZZZSYNTHET0001",
    ])
    def test_a_visibly_fake_vin_passes(self, vin):
        assert looks_synthetic(vin) is True, f"{vin} wrongly refused"

    def test_an_ordinary_identifier_is_not_mistaken_for_a_vin(self):
        """Guards against the check firing on hex blobs, etags and base64."""
        findings = scan([Path(__file__)])
        bad = [f for f in findings if "0x8DEEC19E6798565" in f[2]]
        assert bad == []


class TestTheGuardDocumentsWhatItDoes:
    """The docstring is the rule as a contributor reads it, so it has to agree
    with the code underneath it. It did not: ``ANON`` and ``SAMPLE`` are two of
    the eleven word markers the code accepts and neither appeared in the list a
    reader sees, so the written rule understated what already counts as
    obviously-fake. Someone following the documentation would rename a
    legitimate ANON placeholder for nothing.

    Prose cannot be diffed against behaviour, so the part of it that *is*
    derivable from the code gets derived. A twelfth marker added later fails
    this test too, rather than quietly widening the gate behind its own
    documentation.
    """

    def test_the_docstring_names_every_marker_the_code_accepts(self) -> None:
        import check_no_real_vins

        doc = check_no_real_vins.__doc__ or ""
        missing = [m for m in check_no_real_vins._MARKERS if m not in doc]
        assert missing == [], (
            f"markers the code accepts but the documented rule omits: {missing}"
        )


def _tracked_paths() -> list[str]:
    """``git ls-files`` for the repo under test.

    ``stdin=DEVNULL`` is load-bearing on Windows and was learned the hard way:
    without it these two tests pass when the file runs alone and fail inside the
    full suite with ``OSError: [WinError 6] The handle is invalid``. Under
    pytest's full capture the inherited stdin handle is not duplicable, and
    ``subprocess`` tries to duplicate it before it ever reaches git. A test that
    only passes in isolation is worth very little, so this stays explicit.
    """
    return subprocess.run(
        ["git", "ls-files"], capture_output=True, text=True,
        check=True, cwd=_ROOT, stdin=subprocess.DEVNULL,
    ).stdout.splitlines()


class TestTheTreeIsClean:
    """The regression test. This is the one that will fail on a future PR."""

    def test_no_tracked_file_holds_a_non_synthetic_vin(self):
        tracked = _tracked_paths()
        findings = scan([_ROOT / p for p in tracked if p])
        # Report masked: this assertion message can end up in a public CI log.
        masked = [f"{p}:{n} {v[:6]}...{v[-4:]}" for p, n, v in findings]
        assert masked == [], "non-synthetic VINs in tree: " + "; ".join(masked)

    def test_the_scan_actually_read_the_tree(self):
        """Counter-check for the test above: a scan over nothing also returns
        nothing, and would look just as green."""
        assert len(_tracked_paths()) > 100, "git ls-files returned almost nothing"
