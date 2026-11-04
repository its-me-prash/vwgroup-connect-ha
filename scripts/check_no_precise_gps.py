#!/usr/bin/env python3
# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Refuse a commit that adds a coordinate pair which does not look synthetic.

CONTRIBUTING.md forbids "Exact GPS coordinates (more than 1 decimal place)" in
the repo, fixtures and commits, and binds maintainers as well as contributors.
Nothing enforced it. On 2026-11-04 a reporter's parked position was found in the
source and in a test, where it had sat since #1378 in September and shipped in
32 release tags — and it had been redacted out of the issue it arrived in two
months earlier, so the only thing missing was a check on our own tree. This is
that check, written in the shape of ``check_no_real_vins.py`` next door, for the
same reason: a written rule that nothing enforces is a rule that decays.

**What makes a pair a candidate.** Two coordinate-shaped numbers side by side,
each with two or more decimals, with the latitude's integer part capped at two
digits and the longitude's at three, inside real-world bounds. The pair is the
unit because a lone decimal is not a position and cannot be told apart from a
consumption figure or a timestamp's seconds.

**Why a context word is required.** The VIN check narrows on the eleven
world-manufacturer prefixes; a coordinate carries no such mark, and "two
two-decimal numbers side by side" is an ordinary shape in telemetry fixtures. So
a candidate only counts when the line, or one of the two above it, mentions
latitude, longitude, position, location, coordinates, GPS, geo, maps, a
destination, parking, a place or an ``@``. Measured over the tracked tree when
this was written: **all 16** coordinate pairs in the repo sat in such a context
and none outside it, so the narrowing costs no coverage and buys the strict
two-decimal threshold.

**When a pair is accepted.** Shape-based, not a list, for the reason the VIN
check gives: an allowlist goes stale the moment someone adds a legitimate new
placeholder. Both halves have to announce themselves as made up — both, not
either, because half a real pair is still half of someone's address:

  * a sequential digit run in the decimals, ascending or descending (``.123456``,
    ``.654321``)
  * four or more identical digits in a row (``.333300``, ``.1111``)
  * decimals that are all zero (``.000000``) — the rounded form CONTRIBUTING asks
    for, padded
  * a word marker on the line: TEST, SYNTHET, SYNTH, DUMMY, FAKE, EXAMPLE,
    PLACEHOLD, REDACT, ANON, SAMPLE

Anything else is treated as possibly real and refused, which is the right way
round: a false positive costs one commit a change of digits in a fixture whose
value is arbitrary, while a false negative publishes where a stranger parks.

**It gates what a change ADDS, not what the tree already holds.** That is the
first sentence of this docstring and it is also the only version that works.
Measured when this was written: the tracked tree holds **13** pairs that are not
visibly synthetic, and every one of them is a public landmark used as a test
input — Vienna Stephansplatz, Munich Marienplatz, central Zurich, and one
deliberately mis-signed Sydney longitude. Normalising them would have meant
**77** replacements across **18** files, including tests that assert rounded
outputs, which is a great deal of churn and regression risk for no privacy gain:
none of them is anybody's position. Exempting their files instead would put the
guard's blind spot exactly where coordinates collect. So the baseline stays, it
is named here rather than hidden, and the gate looks at added lines — which is
what would have caught #1378, because that value arrived in a commit.

Usage:
    python scripts/check_no_precise_gps.py --base origin/main   # the gate
    python scripts/check_no_precise_gps.py                      # audit, whole tree
    python scripts/check_no_precise_gps.py FILE...              # just these

With ``--base`` the exit code is 1 only for pairs on lines the diff adds;
pre-existing ones are listed as information. Without it every finding counts,
which is the audit view. The report masks the digits either way.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

#: Two coordinate-shaped numbers side by side. Deliberately the same shape as
#: ``_COORD_PAIR_RE`` in ``cariad/_unexpected_keys.py``, which blunts these at
#: runtime — one guards what we publish from a car, this guards what we commit.
_PAIR = re.compile(
    r"(?<![\d.])(-?\d{1,2}\.\d{2,})"
    r"\s*(?:([NnSs])\s*)?(?:[,;]|\s)\s*"
    r"(-?\d{1,3}\.\d{2,})"
    r"(?:\s*([EeWw]))?(?![\d.])"
)

#: A word that says the numbers on this line are a position. Looked for on the
#: line itself and the two above it, because a fixture often names the field one
#: or two lines before the value.
_CONTEXT = re.compile(
    r"(?i)lat|lon|lng|gps|geo|coord|location|position|maps|destination"
    r"|parking|place|@"
)

_MARKERS = ("TEST", "SYNTHET", "SYNTH", "DUMMY", "FAKE", "EXAMPLE",
            "PLACEHOLD", "REDACT", "ANON", "SAMPLE")

_SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv",
              ".mypy_cache", ".pytest_cache", ".ruff_cache", "htmlcov"}

#: This file alone, because the guidance above and in ``main()`` spells out
#: example coordinates to explain the rules. Measured, and the honest version is
#: weaker than it reads: every example here is judged synthetic by
#: ``looks_synthetic``, so the file would scan clean with no exemption at all.
#: The entry is a guard rail for a future example that is not, not something the
#: current text needs — said plainly, because an exemption justified by a reason
#: that does not hold is one nobody thinks to remove. Kept to one entry on
#: purpose: a guard that looks away from a file has its blind spot exactly where
#: the awkward cases collect, and its own test file is scanned too.
_SKIP_FILES = {"scripts/check_no_precise_gps.py"}


def _is_sequential(s: str) -> bool:
    """Ascending or descending by one, the whole way."""
    if len(s) < 4 or not s.isdigit():
        return False
    deltas = {int(s[i + 1]) - int(s[i]) for i in range(len(s) - 1)}
    return deltas in ({1}, {-1})


def _half_looks_synthetic(number: str) -> bool:
    """Does one half of the pair announce itself as made up?"""
    decimals = number.split(".", 1)[1]
    if set(decimals) == {"0"}:
        return True
    if re.search(r"(.)\1{3,}", decimals):        # four identical in a row
        return True
    # A sequential run anywhere in the decimals, as a sliding window rather than
    # a whole-match: the commonest filler is "123456789", whose 9->0 step would
    # fail a whole-match test for the one reason that does not matter.
    for start in range(max(1, len(decimals) - 3)):
        if _is_sequential(decimals[start:start + 6]):
            return True
    return False


def looks_synthetic(lat: str, lon: str, line: str) -> bool:
    """Accept only when BOTH halves are visibly invented, or the line says so.

    Both, not either: half a real pair is still half of someone's address, and a
    fixture that mixes an invented latitude with a captured longitude is the
    shape a careless redaction produces.
    """
    if any(m in line.upper() for m in _MARKERS):
        return True
    return _half_looks_synthetic(lat) and _half_looks_synthetic(lon)


def _in_bounds(lat: str, lon: str) -> bool:
    try:
        return abs(float(lat)) <= 90 and abs(float(lon)) <= 180
    except ValueError:  # pragma: no cover — the pattern only matches numbers
        return False


def _untracked_files() -> set[str]:
    """Files git does not know yet, minus the ignored ones.

    They matter twice over. ``git ls-files`` alone would not scan a brand-new
    test file at all, and ``git diff`` does not list one either — so in the
    gate's own diff mode an entirely new file would have no "added" lines and
    would pass as pre-existing. Every line of one of these counts as added.
    """
    out = subprocess.run(
        ["git", "ls-files", "--others", "--exclude-standard"],
        capture_output=True, text=True, stdin=subprocess.DEVNULL,
    )
    return {p for p in out.stdout.splitlines() if p} if out.returncode == 0 else set()


def _tracked_files() -> list[Path]:
    out = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
        capture_output=True, text=True, stdin=subprocess.DEVNULL, check=True,
    ).stdout.splitlines()
    return [Path(p) for p in out if p]


def scan(paths: list[Path]) -> list[tuple[Path, int, str, str]]:
    findings: list[tuple[Path, int, str, str]] = []
    for path in paths:
        posix = path.as_posix()
        if posix in _SKIP_FILES:
            continue
        if any(part in _SKIP_DIRS for part in path.parts):
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except (OSError, UnicodeDecodeError):
            continue
        lines = text.splitlines()
        for index, line in enumerate(lines):
            if not _PAIR.search(line):
                continue
            window = "\n".join(lines[max(0, index - 2):index + 1])
            if not _CONTEXT.search(window):
                continue
            for match in _PAIR.finditer(line):
                lat, lon = match.group(1), match.group(3)
                if not _in_bounds(lat, lon):
                    continue
                if looks_synthetic(lat, lon, line):
                    continue
                findings.append((path, index + 1, lat, lon))
    return findings


def _mask(number: str) -> str:
    whole, decimals = number.split(".", 1)
    return f"{whole}.{'X' * len(decimals)}"


def _added_lines(base: str) -> dict[str, set[int]] | None:
    """Line numbers each file gains relative to ``base``, or None if git fails.

    Returning None rather than an empty mapping matters: an empty mapping would
    read as "this change adds nothing", and the gate would pass everything. A
    broken baseline has to be loud, not permissive.
    """
    merge_base = subprocess.run(
        ["git", "merge-base", "HEAD", base], capture_output=True, text=True, stdin=subprocess.DEVNULL,
    )
    ref = merge_base.stdout.strip() if merge_base.returncode == 0 else base
    diff = subprocess.run(
        ["git", "diff", "--unified=0", "--no-color", ref, "--"],
        capture_output=True, text=True, stdin=subprocess.DEVNULL,
    )
    if diff.returncode != 0:
        return None
    added: dict[str, set[int]] = {}
    current: str | None = None
    for line in diff.stdout.splitlines():
        if line.startswith("+++ b/"):
            current = line[6:]
            added.setdefault(current, set())
        elif line.startswith("@@") and current is not None:
            match = re.search(r"\+(\d+)(?:,(\d+))?", line)
            if match:
                start = int(match.group(1))
                count = int(match.group(2) or 1)
                added[current].update(range(start, start + count))
    return added


def main(argv: list[str]) -> int:
    args = argv[1:]
    base: str | None = None
    if "--base" in args:
        index = args.index("--base")
        try:
            base = args[index + 1]
        except IndexError:
            print("--base needs a git ref, e.g. --base origin/main")
            return 2
        del args[index:index + 2]

    paths = [Path(a) for a in args] or _tracked_files()
    findings = scan(paths)

    vorhanden: list[tuple[Path, int, str, str]] = []
    if base is not None:
        added = _added_lines(base)
        if added is None:
            print(f"Cannot diff against {base!r}: no baseline, so nothing can be")
            print("judged new. Fix the ref rather than treating the gate as passed.")
            return 2
        ganz_neu = _untracked_files()
        neu = []
        for item in findings:
            path, lineno = item[0], item[1]
            posix = path.as_posix()
            if posix in ganz_neu or lineno in added.get(posix, set()):
                neu.append(item)
            else:
                vorhanden.append(item)
        findings = neu

    if vorhanden:
        print(f"Pre-existing, not judged (see this script's docstring): "
              f"{len(vorhanden)} pair(s).")
        for path, lineno, lat, lon in vorhanden:
            print(f"  {path.as_posix()}:{lineno}  {_mask(lat)}, {_mask(lon)}")
        print()

    if not findings:
        return 0

    print("Refusing: coordinate pairs that do not look synthetic.\n")
    print("CONTRIBUTING.md, 'What does NOT go in the repo':")
    print("  Exact GPS coordinates (more than 1 decimal place), even from your")
    print("  own car.\n")
    for path, lineno, lat, lon in findings:
        # Masked on purpose. The point is to locate it, not to copy a position
        # into a CI log that is itself public.
        print(f"  {path.as_posix()}:{lineno}  {_mask(lat)}, {_mask(lon)}")
    print("\nUse digits that are visibly made up. Keep the degrees so the shape")
    print("stays realistic and the region stays plausible, and make the decimals")
    print("announce themselves, for example:")
    print("  48.123456, 16.654321    50.333300, 4.444400    48.000000, 11.000000")
    print("\nIf the value really is a captured position, it does not belong in")
    print("the repo at all — round it to one decimal or leave it out.")
    print(f"\n{len(findings)} finding(s).")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
