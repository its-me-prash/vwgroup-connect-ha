#!/usr/bin/env python3
# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Refuse a CHANGELOG that kept a conflict marker or duplicated a heading.

The existing CI job checks that CHANGELOG.md was *touched*. That is a different
question from whether the result is intact, and twice in one day the difference
cost an entry:

(a) A contributor's branch opened its own ``### Behoben / Fixed`` while main
    already had one. Merging produced the heading twice, and nothing failed.
(b) Two branches each rewrote the whole ``## [Unreleased]`` block, so git's
    hunks overlapped and resolving the conflict by taking one side dropped
    main's entire ``### Hinzugefügt / Added`` section — one entry gone. The file
    *was* modified, so the existing check passed it.

WHAT GATES, AND WHAT DOES NOT

Two checks run in CI, and they are the two that can be made to fire only on
real damage:

1. No conflict markers, anywhere in the file.
2. No duplicate section heading inside ``## [Unreleased]`` — which is incident
   (a), and not a hypothetical: of the last 80 revisions of this file on main,
   **three** really carried a duplicated heading in that block.

A third check — "no entry that exists in the baseline has vanished" — is
available through ``--base`` / ``--baseline-file`` but is deliberately NOT part
of the CI job, and that decision is the most important thing in this file.

Replayed over the last 80 revisions of this file on main, each commit against
its real parent, it would have refused **five** of them — and **none** of those
five had lost anything. Every one was an entry whose bold title had been
rewritten, confirmed by reading each diff: a title reordered, one shortened,
two expanded, and one where an issue number was inserted into the title, which
is precisely what RELEASE_PROCESS.md asks an author to do. Over the same 80
revisions it caught **zero** real losses, while the duplicate-heading check
caught three with no false alarm.

The reason is structural rather than fixable: an entry's identity has to be
read out of its own text, 516 of the 819 identified entries cite no issue
number at all and are therefore keyed by their title, so ordinary rewording is
indistinguishable from deletion. Tightening it the other way is no better —
keying by issue number alone collapses entries that share one, and then a
deletion leaves no trace.

A required check that refuses legitimate work and has never caught damage is
worse than no check at all, because what happens next is that someone adds a
``--skip`` and it protects nothing for ever. So it is a diagnostic you run when
you have a reason to, not a gate. Run it after resolving a changelog conflict,
which is when incident (b) happened:

    python scripts/check_changelog_structure.py --base origin/main

Its blind spot, stated plainly rather than discovered later: an entry whose
issue number is also cited by another entry can be deleted without this
reporting it — 322 of 985 entries today, and 6 of the 12 in the Unreleased
block. Incident (b) itself IS caught, because that entry's number was unique.

The other half of the same coin, for reading its output rather than its code:
it will accuse you of deleting an entry you only reworded. In the Unreleased
block that is currently one entry of thirteen, because the other twelve cite an
issue; across the whole file it is 516 of 819. So a report naming a title you
recognise as something you edited is the expected false alarm, not a finding.

Incident (b) is prevented at the cause instead, by
``scripts/add_changelog_entry.py``: it inserts one entry at the end of its
section and never rewrites the block, so two branches adding to two different
sections merge cleanly rather than overlapping. That script is the fix for (b);
this one is the net under (a).

Deliberately NOT checked: section order and section vocabulary. The first draft
of this script enforced Keep a Changelog's order and its six section names, and
produced 55 kB of complaints about nine months of released history — this
project has used 31 distinct section headings, among them "Docs", "Thanks" and
"What is new vs v2.7.4", and the file states that past entries are preserved as
written. Imposing a vocabulary the project does not follow is inventing a rule,
not mechanising one.

Check 2 is scoped to ``## [Unreleased]`` because that is where edits land and
where the duplicate came from. Released blocks are history.

Usage:
    python scripts/check_changelog_structure.py
    python scripts/check_changelog_structure.py --base origin/main
    python scripts/check_changelog_structure.py --file CHANGELOG.md --base HEAD~1
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

_MARKERS = ("<<<<<<<", "=======", ">>>>>>>")
_RELEASE = re.compile(r"^## +\[.+?\]", re.M)
#: Up to three leading spaces and a tab after the hashes, because CommonMark
#: renders all of those as headings and GitHub shows them as headings — so a
#: merge that leaves "  ### Behoben / Fixed" leaves a visible duplicate that a
#: column-0-and-space-only pattern cannot see.
#:
#: NOT widened to four hashes. This file uses "#### " for sub-headings INSIDE an
#: entry (four entries do today), so counting those as sections would both
#: inflate the section count and risk refusing a legitimate entry that happens
#: to repeat a sub-heading. Conflating the two conventions would be inventing a
#: rule; the writer refuses a heading inside an entry instead.
_SECTION = re.compile(r"^ {0,3}###[ \t]+(.+?)\s*$", re.M)
#: The bilingual section names, each mapped to one slot, so check 2 compares
#: what a heading MEANS rather than how it is spelled. Without this, a branch
#: writing "### Fixed" and a branch writing "### Behoben / Fixed" merge into one
#: block holding two headings for one section, and the duplicate check counts
#: two unique names and passes. Both spellings are real: this file's history has
#: 176 of the English-only form and 5 of the bilingual one, and its own header
#: switched the convention to English-primary at v2.4.1 — so the order varies
#: too, and both orders map to the same slot.
#:
#: A heading outside this table — "Docs", "Thanks", "What is new vs v2.7.4" —
#: compares literally, which is the right default: this script does not police
#: section vocabulary, so it must not guess that two unknown names mean one
#: thing.
_SLOT_WORDS = {
    "added": "added", "hinzugefügt": "added",
    "changed": "changed", "geändert": "changed",
    "deprecated": "deprecated", "veraltet": "deprecated",
    "removed": "removed", "entfernt": "removed",
    "fixed": "fixed", "behoben": "fixed",
    "security": "security", "sicherheit": "security",
}
#: An entry opens with "- **" and its bold title may wrap over several lines —
#: hence re.S. But the dot is tempered so a title cannot run PAST the next entry
#: or heading: with a plain ``.+?`` an entry whose bold marker is never closed
#: matches lazily across newlines to the next ``**`` it finds, which is the
#: OPENING marker of the following entry. finditer is non-overlapping, so that
#: next entry is then never matched, its issue key is absent from entry_keys(),
#: and check 3 reports it as lost while it is demonstrably still in the file.
#: A false failure on a required check is the exact failure mode this script's
#: own docstring is written against. Measured over the whole file before and
#: after: 985 matches and 817 keys either way, no key gained, none lost, no key
#: with a different title, all 48 wrapped titles still matched.
_ENTRY = re.compile(r"^- \*\*((?:(?!^- \*\*|^#).)+?)\*\*", re.M | re.S)
_ISSUE = re.compile(r"#(\d{3,6})")
_UNRELEASED = "## [Unreleased]"
#: Anchored to column 0, because the plain substring is not a heading test. A
#: sentence in the file that merely NAMES the Unreleased heading — this project
#: documents the block's own shape in prose, and its release process quotes the
#: template — would otherwise become the block's start, and the block would then
#: "end" at the real heading a few lines later. Check 2 would inspect that
#: fragment and find no duplicate in it: switched off by a sentence, silently.
_UNRELEASED_RE = re.compile(r"^## +\[Unreleased\]", re.M)


def _p(text: object) -> str:
    """ASCII-safe for stdout.

    Windows consoles encode stdout as cp1252, and this script prints changelog
    text back at the reader — section headings carry umlauts and the file's own
    sponsor line carries an emoji. Printing either raised UnicodeEncodeError and
    took the run down, which on a checker is the worst failure mode: it would
    have passed in CI on Linux and been unusable on the machine where the
    changelog is actually edited.
    """
    return str(text).encode("ascii", "replace").decode("ascii")


def heading_slot(name: str) -> str:
    """What a section heading means, for comparing two spellings of one section.

    Returns a slot token when every slash-separated part of the heading is a
    known section word in either language, and the heading's own casefolded
    text otherwise. Requiring EVERY part to be known is what keeps
    "Fixed / Behoben" and "Behoben / Fixed" together while leaving
    "What is new vs v2.7.4" alone.
    """
    parts = [p.strip().casefold() for p in name.split("/") if p.strip()]
    slots = {_SLOT_WORDS[p] for p in parts if p in _SLOT_WORDS}
    if parts and len(slots) == 1 and all(p in _SLOT_WORDS for p in parts):
        return next(iter(slots))
    return name.strip().casefold()


def unreleased_block(text: str) -> str:
    """The ``## [Unreleased]`` block, or "" when the file has none.

    Searching from the END of the heading rather than from a fixed offset
    matters as much as anchoring it: ``_RELEASE`` also matches
    ``## [Unreleased]`` itself, so a search that starts one character early
    finds the heading again and returns an empty block.
    """
    m = _UNRELEASED_RE.search(text)
    if not m:
        return ""
    nxt = _RELEASE.search(text, m.end())
    return text[m.start():nxt.start()] if nxt else text[m.start():]


def entry_keys(text: str) -> dict[str, str]:
    """Identity -> the title it came from, for every entry in the text.

    An entry is keyed by each issue it cites, so one entry covering two issues
    is tracked under both: losing it should name both.
    """
    keys: dict[str, str] = {}
    for m in _ENTRY.finditer(text):
        tail = text[m.start():]
        nxt = re.search(r"^(?:- \*\*|### |## )", tail[3:], re.M)
        body = tail[: nxt.start() + 3] if nxt else tail
        title = re.sub(r"\s+", " ", m.group(1)).strip()
        issues = sorted(set(_ISSUE.findall(body)))
        if issues:
            for num in issues:
                keys[f"#{num}"] = title
        else:
            # Two entries with the same title must occupy two slots, or losing
            # one of them is invisible: a dict assignment would overwrite, the
            # key would still be present afterwards, and check 3 would pass a
            # real deletion. This file already contains two colliding pairs —
            # four entries — because some titles are deliberately reused from
            # release to release ("Repo hygiene."), so this is not a
            # hypothetical. Numbering the later ones keeps the first slot's
            # identity stable, which is what makes a genuine reorder of two
            # colliding entries pass while a deletion of either fails.
            #
            # Note what is NOT done here: the same multiplicity treatment for
            # ISSUE keys. Replayed over the file's own history it fires on
            # legitimate work — two entries about one issue being folded into
            # one, which happened twice recently — so on a required check it
            # would be worse than the defect it closes. That leg needs its own
            # answer, not this one widened.
            key = f"title:{title}"
            n = 2
            while key in keys:
                key = f"title:{title} [{n}]"
                n += 1
            keys[key] = title
    return keys


#: A third limit, recorded because the obvious fix makes things worse.
#:
#: An entry's body runs to the next entry or heading, so a paragraph sitting
#: between two entries is absorbed into the one above it and donates its issue
#: number to that entry — after which the entry which really owns the number can
#: be deleted unnoticed.
#:
#: Narrowing the body to the entry's FIRST paragraph is the tempting fix, and it
#: is wrong here. Measured on the file: 20 of 986 entries span more than one
#: paragraph (up to eleven), and for five of them the issue number appears only
#: in a later paragraph. Narrowing would strip those five of their issue key and
#: leave them identified by their title, which is the fragile kind — so the fix
#: would make five real entries easier to lose in order to close a case that
#: needs a stray paragraph belonging to no entry, something this file does not
#: contain. Left as it is, on purpose.


def _git_show(ref: str, path: str) -> str | None:
    try:
        r = subprocess.run(
            ["git", "show", f"{ref}:{path}"],
            capture_output=True, encoding="utf-8", errors="replace", check=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None
    return r.stdout


def sections_without_a_category(text: str) -> list[str]:
    """Section names that hold ``- **`` entries but no ``### `` heading.

    ``build_release_notes.split_entries`` only yields a group once it has seen
    a category heading, so such a section parses as ZERO entries and the
    release page comes out as "The change list could not be generated".

    v5.2.3b1 shipped exactly that way on 2026-11-01: five entries, no category
    heading, a degraded page. It was the only one of 386 sections with the
    defect, and nothing caught it — the version-pattern fix made for it was
    verified by a test that drives the first pre-release *with entries*, which
    silently selected a different, healthy section.
    """
    offenders: list[str] = []
    heads = list(re.finditer(r"^## \[([^\]]+)\][^\n]*$", text, re.MULTILINE))
    for idx, head in enumerate(heads):
        end = heads[idx + 1].start() if idx + 1 < len(heads) else len(text)
        body = text[head.end():end]
        has_entries = re.search(r"^- \*\*", body, re.MULTILINE) is not None
        has_category = re.search(r"^### ", body, re.MULTILINE) is not None
        if has_entries and not has_category:
            offenders.append(head.group(1))
    return offenders


def check(text: str, baseline: str | None) -> list[str]:
    problems: list[str] = []

    for num, line in enumerate(text.splitlines(), 1):
        for marker in _MARKERS:
            if line.startswith(marker):
                problems.append(
                    f"line {num}: an unresolved conflict marker ({marker}) is "
                    "still in the file"
                )

    for name in sections_without_a_category(text):
        problems.append(
            f'section "{name}" has entries but no "### " category heading, so '
            "build_release_notes parses it as zero entries and the release "
            "page says the change list could not be generated. Add the "
            "category headings its neighbours use (### Behoben / Fixed, "
            "### Hinzugefügt / Added, ### Geändert / Changed)."
        )

    # Only the FIRST Unreleased heading is examined, so a second one hides
    # everything under it from check 2. That is what a merge resolved by
    # keeping both sides leaves behind — the same operation that produced the
    # duplicate heading this script exists to catch. Reporting it costs seven
    # lines; 130 historical revisions of this file all have exactly one
    # heading, so the rule would never have fired on the project's own history.
    heads = len(_UNRELEASED_RE.findall(text))
    if heads > 1:
        problems.append(
            f'the file has {heads} "{_UNRELEASED}" headings. Only the first is '
            "examined, so everything under the others is unchecked; a merge "
            "resolved by keeping both sides leaves this. Fold them into one."
        )

    block = unreleased_block(text)
    if not block:
        # The message used to say a release in progress "is fine", while the
        # function put it in `problems` and returned 1. A check whose text
        # contradicts its own exit code teaches the reader to ignore the text.
        # The behaviour is right and stays: this project's release step adds a
        # fresh empty block above the new version (RELEASE_PROCESS.md), so a
        # file with no such heading at column 0 is a mistake and not a stage of
        # the process.
        problems.append(
            f'there is no "{_UNRELEASED}" heading at the start of a line. The '
            "release step adds a fresh empty one above the new version, so a "
            "file without it has lost it — restore the heading, keeping any "
            "entries that were under it."
        )
    else:
        found = [m.group(1) for m in _SECTION.finditer(block)]
        by_slot: dict[str, list[str]] = {}
        for name in found:
            by_slot.setdefault(heading_slot(name), []).append(name)
        for spellings in by_slot.values():
            if len(spellings) > 1:
                shown = (
                    f'"{spellings[0]}"' if len(set(spellings)) == 1
                    else " and ".join(f'"{s}"' for s in dict.fromkeys(spellings))
                )
                problems.append(
                    f"Unreleased has the section {shown} {len(spellings)} "
                    "times. Two headings for one section in one release is what "
                    "a merge leaves behind; fold the entries into one section."
                )

    if baseline is not None:
        was, now = entry_keys(baseline), entry_keys(text)
        for key in sorted(set(was) - set(now)):
            problems.append(
                f"the entry for {key} is in the baseline and gone from this "
                f"file ({was[key][:70]!r}). An entry is the record that the "
                "work happened; it may move between release blocks, but it may "
                "not disappear."
            )

    return problems


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--file", default="CHANGELOG.md")
    ap.add_argument(
        "--base", default=None,
        help="a git ref to compare entries against, e.g. origin/main",
    )
    ap.add_argument(
        "--baseline-file", default=None,
        help="a file to compare entries against, instead of a git ref. For "
             "testing this checker, and for comparing two files directly.",
    )
    args = ap.parse_args(argv)

    path = Path(args.file)
    if not path.exists():
        print(_p(f"not found: {path}"))
        return 2
    text = path.read_text(encoding="utf-8")

    baseline = None
    if args.baseline_file:
        bp = Path(args.baseline_file)
        if not bp.exists():
            print(_p(f"baseline file not found: {bp}"))
            return 2
        baseline = bp.read_text(encoding="utf-8")
    elif args.base:
        baseline = _git_show(args.base, args.file)
        if baseline is None:
            # NOT a warning-and-continue. A mistyped ref, a shallow clone or a
            # path outside the repository would otherwise switch off the one
            # check that catches a lost entry, and switch it off silently - in
            # CI, where nobody is reading the log of a job that passed.
            print(_p(
                f"Refusing: --base {args.base} was asked for, but {args.file} "
                f"could not be read at that ref. The lost-entry check cannot "
                "run, and skipping it quietly is how it would stop protecting "
                "anything. Fix the ref, or drop --base to run the structure "
                "checks alone."
            ))
            return 2

    problems = check(text, baseline)
    if not problems:
        sections = len(_SECTION.findall(unreleased_block(text)))
        entries = len(entry_keys(text))
        # Not "skipped": the lost-entry comparison is opt-in by design, because
        # as a gate it refused 18 of 79 real commits. Saying "skipped" would
        # invite someone to wire it into CI to make the message go away.
        extra = "" if baseline else " (no baseline given, so entries were not compared)"
        print(_p(
            f"CHANGELOG.md intact: {entries} identified entries, "
            f"{sections} unique section(s) in Unreleased{extra}."
        ))
        return 0

    print("Refusing: CHANGELOG.md is not intact.\n")
    for problem in problems:
        print(_p(f"  - {problem}"))
    print(f"\n{len(problems)} problem(s).")
    return 1


if __name__ == "__main__":
    sys.exit(main())
