#!/usr/bin/env python3
# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Refuse a commit that adds a VIN which does not look synthetic.

CONTRIBUTING.md forbids full VINs in the repo, fixtures and commits, and it binds
maintainers as well as contributors. A written rule that nothing enforces is a
rule that decays. This is the enforcement.

The check is deliberately shape-based rather than a list. An allowlist of
individual VINs would need over a hundred entries and would go stale the moment
someone adds a legitimate new placeholder. Instead a literal is accepted when it
carries a visible marker of being made up:

  * a word marker anywhere in it: TEST, SYNTHET, SYNTH, KEEP, DUMMY, FAKE,
    EXAMPLE, PLACEHOLD, REDACT, ANON, SAMPLE
  * a filler run: four or more identical characters in a row (XXXX, AAAA, 0000)
  * an all-zero serial, the last six characters
  * a sequential serial, ascending or descending by one (012345, 123456, 987654)
  * a serial of one repeated digit (111111, 999999)

Anything else is treated as possibly real and refused. That is the right way
round: a false positive costs one commit a rename to an obviously-fake value,
while a false negative publishes a stranger's vehicle identity.

Usage:
    python scripts/check_no_real_vins.py            # whole tree (tracked files)
    python scripts/check_no_real_vins.py FILE...    # just these

Exit code 1 and a per-finding report when something is refused.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

# A VIN is 17 characters; I, O and Q are excluded from the alphabet by the
# standard, which is what keeps this from matching ordinary hex or base64 runs.
#
# TWO leading letters, not three. Position 3 of a world-manufacturer identifier
# may be a digit (ISO 3779), and four of the eleven prefixes below are exactly
# that shape: WP0, WF0, WV1, WV2. With {3} the pattern could not produce a
# candidate under any of them, so the check was structurally blind to a third of
# its own prefix list - Porsche included - while its documentation said it
# refuses any VIN-shaped literal that carries no mark of being made up.
#
# Widening is safe because the narrowing happens in scan(), which filters every
# match through startswith(_WMI) immediately after finditer. A 17-character
# token that is not one of these prefixes is discarded whether this matched it
# or not, so the pattern may be the looser of the two.
_VIN = re.compile(r"(?<![A-HJ-NPR-Z0-9])([A-HJ-NPR-Z]{2}[A-HJ-NPR-Z0-9]{15})(?![A-HJ-NPR-Z0-9])")

# Only these world-manufacturer prefixes concern this project. Narrowing to them
# keeps the check from firing on unrelated 17-character identifiers.
_WMI = ("WVW", "WAU", "TMB", "VSS", "WP0", "WF0", "WME", "TMP", "WVG", "WV1", "WV2")

_MARKERS = ("TEST", "SYNTHET", "SYNTH", "KEEP", "DUMMY", "FAKE", "EXAMPLE",
            "PLACEHOLD", "REDACT", "ANON", "SAMPLE")

_SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", ".mypy_cache",
              ".pytest_cache", ".ruff_cache", "htmlcov"}
# This file alone, because the guidance it prints spells out example VINs to
# explain the rules.
#
# Measured, and the honest version is weaker than it reads: all three examples
# main() prints are judged synthetic by looks_synthetic() — a zeroed serial, a
# TEST marker, a padded counter — so this file would scan clean with no
# exemption at all. The entry is a guard rail for a future example that is not
# synthetic, not something the current text needs. Said plainly because the
# exemption is the guard's only blind spot, and a blind spot justified by a
# reason that does not hold is one nobody will think to remove.
#
# Nothing else is exempt, and the exemption list is kept to one
# entry on purpose: a guard that looks away from a file is a guard whose blind spot
# is exactly where the awkward cases collect. The guard's own test file is scanned
# too, and it asserts that this set does not mention it.
_SKIP_FILES = {"scripts/check_no_real_vins.py"}


def _is_sequential(s: str) -> bool:
    """Ascending or descending by one, the whole way."""
    if len(s) < 4 or not s.isdigit():
        return False
    deltas = {int(s[i + 1]) - int(s[i]) for i in range(len(s) - 1)}
    return deltas in ({1}, {-1})


def looks_synthetic(vin: str) -> bool:
    """Does this literal visibly announce itself as made up?

    Every rule here was derived from literals already in this repo, not guessed:
    running the check without one of them produced a false positive on a value a
    human can see at a glance is invented.
    """
    up = vin.upper()
    if any(m in up for m in _MARKERS):
        return True
    if re.search(r"(.)\1{3,}", up):          # four identical in a row
        return True
    # A sequential digit run anywhere. Checked as a sliding window rather than
    # whole-match, because the commonest filler in this repo is "1234567890",
    # whose final 9->0 step is not +1 and would otherwise fail a whole-match
    # test for the one reason that does not matter.
    for match in re.finditer(r"\d{6,}", up):
        digits = match.group()
        if any(_is_sequential(digits[i:i + 6]) for i in range(len(digits) - 5)):
            return True
    serial = up[-6:]
    if serial.isdigit() and len(set(serial)) == 1:
        return True
    if _is_sequential(serial):
        return True
    # A padded counter: two or more leading zeros then a small number. Real
    # production serials do not start 00xxxx, and this is the shape every
    # hand-written placeholder in this repo reaches for (000001, 000503, 001234).
    return bool(re.fullmatch(r"0{2,}\d+", serial))


def _tracked_files() -> list[Path]:
    out = subprocess.run(
        ["git", "ls-files"], capture_output=True, text=True, check=True,
    ).stdout.splitlines()
    return [Path(p) for p in out if p]


def scan(paths: list[Path]) -> list[tuple[Path, int, str]]:
    findings: list[tuple[Path, int, str]] = []
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
        for lineno, line in enumerate(text.splitlines(), 1):
            for match in _VIN.finditer(line):
                vin = match.group(1)
                if not vin.startswith(_WMI):
                    continue
                if looks_synthetic(vin):
                    continue
                findings.append((path, lineno, vin))
    return findings


def main(argv: list[str]) -> int:
    paths = [Path(a) for a in argv[1:]] or _tracked_files()
    findings = scan(paths)
    if not findings:
        return 0

    print("Refusing: VIN-shaped literals that do not look synthetic.\n")
    print("CONTRIBUTING.md, 'What goes in the repo / fixtures / commits':")
    print("  Full VINs (17 chars), even from the tester's own car, do not go in.\n")
    for path, lineno, vin in findings:
        # Print the VIN masked. The point is to locate it, not to copy it into
        # a CI log that is itself public.
        print(f"  {path.as_posix()}:{lineno}  {vin[:6]}...{vin[-4:]}")
    print("\nUse a placeholder that is visibly made up. Keep the manufacturer,")
    print("type code, model-year letter and plant letter so the shape stays")
    print("realistic, and zero the six-digit serial, for example:")
    print("  WVWZZZAUZFW000000    WAUZZZTESTVHN0001    TMBJR0NX4SY000001")
    print(f"\n{len(findings)} finding(s).")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
