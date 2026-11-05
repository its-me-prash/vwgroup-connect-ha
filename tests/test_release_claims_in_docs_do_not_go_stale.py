# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""A sentence about release status has an expiry date, so a test has to hold it.

**The defect this exists for, measured 2026-11-05.** `PRIVACY.md` told readers a
GPS-precision defect was "fixed in the repository but is **not yet in a released
version**", citing #1378, in two places. By then v5.2.3 was tagged and both fixes
were in it. So the project's own privacy document was withholding an all-clear
that already applied, and advising caution about a version that no longer had the
defect.

**Why a guard rather than care.** The wording was not sloppy — it was the careful
wording, chosen the previous evening precisely *because* naming an unreleased
version would have been wrong. The note that prescribes it also says to follow it
up at release time. That follow-up step was missed within twenty-four hours of
being written, by its author. A rule whose enforcement is a person remembering at
the right moment is not a gate; this file is the gate.

**Two directions, because they fail differently.**

* *Stale caution* (what happened): the doc says something is **not** released
  while the changelog puts its newest work in a shipped version. Harmless-looking
  and therefore long-lived.
* *False all-clear* (the expensive one): the doc says something **is** fixed as of
  a version, and it is not — in a privacy or redaction promise that tells a reader
  it is safe to share a file when it is not. The repo already has
  `test_923_redaction_promise_is_version_scoped.py` because that exact class put
  live session cookies into public issues for four months.

**Why the changelog and not git.** The obvious implementation is
``git tag --contains``. It cannot work where it has to: `ci.yml` checks out with
`actions/checkout@v7` and no `fetch-depth`/`fetch-tags`, i.e. a shallow clone with
no tags and no history, so the call would find neither the commit nor any tag and
would answer "unreleased" for everything — a gate that silently passes in the only
place it runs. `CHANGELOG.md` is in the checkout, is newest-first, is the file the
release process already rewrites at release time (`[Unreleased]` becomes the
version heading), and is parsed by three other readers in this repo. No subprocess,
no network, no clone depth.

**What this asserts, and what it does not.** It compares two documents and reports
a *contradiction*; it does not know whether a fix is real. An issue number under a
released heading can be a mere mention rather than a fix — the "cited is not fixed"
trap, and #1378 is a live example, appearing under 4.7.11 and 4.7.6 for unrelated
reasons. The first draft tried to dodge that by counting only the *newest* heading
citing a reference, and that inverted on its own first use: see `shipped_refs`. The
rule now is "has this reference ever appeared in a shipped version", which no later
mention can undo, at the price of a possible false alarm. When this test goes red it
names both documents and leaves the judgement to a person — the message says so, and
the fix is to reword the sentence, never to delete the check.

**Completeness, not only consistency.** A consistency check between two documents is
vacuously satisfied by a claim that cites nothing, and the silent-rot case is exactly
a sentence with no reference to re-check. So an "not yet released" claim must cite a
resolvable reference; without one it is unverifiable, and that is itself the finding.

Deliberately out of scope: ordering two version numbers. "Fixed as of 5.2.3" for
something that actually shipped in 5.2.0 is conservative, not wrong, and comparing
`5.2.3b1` against `5.2.3` is its own trap. The two checks below catch the two
measured classes without it.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]

#: Markdown documents that are *about* release bookkeeping rather than making
#: claims, and so are not in scope. ``CHANGELOG.md`` is the reference being
#: compared against and is historical by nature — a 2026-04 entry saying
#: something was unreleased was true in 2026-04. ``CLAUDE.md`` is excluded from
#: the repository itself (``.git/info/exclude``) and only exists locally.
_NOT_A_CLAIMANT = {"CHANGELOG.md", "CLAUDE.md"}

# ── the two claim shapes, derived from measured text, not imagined ───────────
#
# `_STALE_CAUTION` is proven below against the two verbatim sentences that
# carried the real defect. It matches the *claim*, never the bare word
# "Unreleased": `## [Unreleased]` is a legitimate changelog heading and
# RELEASE_PROCESS.md discusses that block at length, so a pattern keyed on the
# word alone would cry wolf on the documentation of the very convention that
# makes this check possible.
_STALE_CAUTION = re.compile(
    r"not\s+yet\s+(?:in\s+a\s+)?releas"          # "not yet in a released version"
    r"|not\s+yet\s+in\s+(?:a|any)\s+release"
    r"|not\s+releas\w*\s+yet"
    r"|noch\s+(?:in\s+)?keiner\s+\w*version"      # DE: "noch in keiner Version"
    r"|noch\s+nicht\s+ver(?:ö|oe)ffentlicht"
    r"|noch\s+nicht\s+in\s+einem\s+release",
    re.IGNORECASE,
)

#: "fixed as of 5.2.3", "behoben ab 5.2.3", "gilt seit 1.2.3". The version is
#: captured because its heading has to exist.
_ALL_CLEAR = re.compile(
    r"(?:fixed|corrected|behoben|korrigiert|gilt|holds|applies|stripped|redacted)"
    r"[^.]{0,60}?"
    r"\b(?:as\s+of|from|since|ab|seit)\b"
    r"[\s*_]{0,4}"
    r"(\d+\.\d+\.\d+[A-Za-z0-9]*)",
    re.IGNORECASE,
)

#: `#1234` or `.../issues/1234`. Two digits minimum so a `#1` anchor or a
#: markdown heading does not read as an issue.
_REF = re.compile(r"(?:#|issues/)(\d{2,6})")

#: `## [Unreleased]` or `## [5.2.3] - 2026-11-04 — title`
_HEADING = re.compile(r"^##\s+\[([^\]]+)\]")

_UNRELEASED_LABEL = "Unreleased"


# ── scope: keyed on a property a copy shares, so it is testable on one ───────

def collect_docs(root: Path) -> list[Path]:
    """Documents in scope under ``root``.

    The scope deliberately takes ``root`` as an argument instead of reading the
    repository directly. A check whose reach is pinned to one real path can only
    ever fire on that path and cannot be shown to work on a copy — the failure
    mode this repo tracks as "a gate must gate".
    """
    docs = [
        p
        for p in sorted(root.glob("*.md"))
        if p.name not in _NOT_A_CLAIMANT
    ]
    docs += sorted((root / ".github" / "ISSUE_TEMPLATE").glob("*.yml"))
    return docs


# ── reading claims out of hard-wrapped markdown ──────────────────────────────

def _units(text: str) -> list[tuple[str, str]]:
    """``(sentence, enclosing block)`` pairs.

    Markdown here is hard-wrapped, so a line is not a thought: in the real
    PRIVACY.md sentence the reference `#1378` sat on one line and "fixed as of
    5.2.3" on the next. Splitting on newlines would have separated a claim from
    its own reference and reported it as unverifiable — the measurement would
    have accused the text of the opposite defect. So soft line breaks are joined
    first, and only blank lines and table-cell pipes end a block.
    """
    out: list[tuple[str, str]] = []
    for block in re.split(r"\n\s*\n|\|", text):
        flat = re.sub(r"\s+", " ", block).strip()
        if not flat:
            continue
        # Do not split inside a version number: a period between digits is not
        # the end of a sentence.
        for sentence in re.split(r"(?<![0-9])\.(?=\s|$)", flat):
            s = sentence.strip()
            if s:
                out.append((s, flat))
    return out


def _refs(sentence: str, block: str) -> tuple[set[str], str]:
    """References for a claim, and where they were found.

    The sentence is asked first; only if it names none does the enclosing block
    answer. Widening always would let a reference from a neighbouring sentence
    stand in for a missing one and quietly weaken the completeness check.
    """
    own = set(_REF.findall(sentence))
    if own:
        return own, "sentence"
    return set(_REF.findall(block)), "block"


# ── the changelog side ───────────────────────────────────────────────────────

def changelog_headings(text: str) -> list[str]:
    """Heading labels, in file order (newest first)."""
    return [m.group(1) for line in text.splitlines() if (m := _HEADING.match(line))]


def shipped_refs(text: str) -> dict[str, str]:
    """Every referenced issue that appears under a released heading, and one
    such heading per issue (the newest, for the failure message).

    **Why "has it ever shipped" and not "its newest entry".** The first draft of
    this module asked which heading *most recently* cites a reference, so an old
    unrelated mention could not make a current caution look stale. It inverted on
    its own first use: the changelog entry describing *this* guard cites #1378,
    under ``[Unreleased]``, which made #1378's newest heading unreleased and
    silently switched both checks off for the one issue they were built for.

    Whether a reference has ever appeared in a shipped version cannot be undone
    by writing about it again, so both checks below rest on that instead. The
    cost is the opposite error: an issue mentioned in a release for an unrelated
    reason will flag a legitimate caution. That is a false alarm with a message
    asking a person to tell a fix from a mention — the direction a guard is
    allowed to be wrong in.
    """
    shipped: dict[str, str] = {}
    heading = ""
    for line in text.splitlines():
        m = _HEADING.match(line)
        if m:
            heading = m.group(1)
            continue
        if not heading or heading == _UNRELEASED_LABEL:
            continue
        for ref in _REF.findall(line):
            shipped.setdefault(ref, heading)  # first seen == newest release
    return shipped


def referenced_refs(text: str) -> set[str]:
    """Every issue referenced anywhere under a heading, shipped or not."""
    out: set[str] = set()
    heading = ""
    for line in text.splitlines():
        m = _HEADING.match(line)
        if m:
            heading = m.group(1)
            continue
        if heading:
            out.update(_REF.findall(line))
    return out


# ── the audit itself, as a pure function so it can be driven by fixtures ─────

def audit(
    text: str,
    shipped: dict[str, str],
    headings: list[str],
    known: set[str] | None = None,
) -> list[str]:
    """Problems in ``text``. Empty list means nothing to report."""
    released = {h for h in headings if h != _UNRELEASED_LABEL}
    problems: list[str] = []

    for sentence, block in _units(text):
        if _STALE_CAUTION.search(sentence):
            refs, where = _refs(sentence, block)
            if not refs:
                problems.append(
                    "says something is not yet released but cites no issue or "
                    "commit, so nothing can ever tell you it shipped: "
                    f"{sentence[:160]!r}"
                )
                continue
            in_a_release = {r: shipped[r] for r in refs if r in shipped}
            if in_a_release:
                problems.append(
                    "says something is not yet released, but CHANGELOG.md "
                    f"already carries {in_a_release} in a shipped version "
                    f"(references read from the {where}). Either the caution is "
                    "stale and the sentence should name the version, or that "
                    "changelog entry is a mention rather than a fix — decide "
                    f"which and reword; do not delete this check: {sentence[:160]!r}"
                )

        for claimed in _ALL_CLEAR.findall(sentence):
            if claimed not in released:
                problems.append(
                    f"claims something holds as of {claimed}, but CHANGELOG.md "
                    "has no released section with that version — a typo here is "
                    "an all-clear for a version that does not exist: "
                    f"{sentence[:160]!r}"
                )
                continue
            refs, where = _refs(sentence, block)
            # Only judge references the changelog knows at all. One it has never
            # heard of says nothing about release status, and reading that
            # silence as "unreleased" would redden every document that cites an
            # issue the changelog never discussed.
            judgeable = refs & known if known is not None else refs
            if judgeable and not (judgeable & set(shipped)):
                problems.append(
                    f"claims something holds as of {claimed}, but no released "
                    f"section of CHANGELOG.md carries {sorted(judgeable)} — its "
                    "entries sit under [Unreleased], so no shipped version has "
                    "it. This is a false all-clear in a document people act on "
                    f"(references read from the {where}): {sentence[:160]!r}"
                )

    return problems


# ── fixtures from the real repository ────────────────────────────────────────

@pytest.fixture(scope="module")
def changelog() -> tuple[dict[str, str], list[str], set[str]]:
    text = (_ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    return shipped_refs(text), changelog_headings(text), referenced_refs(text)


_DOCS = collect_docs(_ROOT)


# ── the guard ────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("doc", _DOCS, ids=[p.name for p in _DOCS])
def test_no_document_makes_a_stale_or_false_release_claim(
    doc: Path, changelog: tuple[dict[str, str], list[str], set[str]]
) -> None:
    shipped, headings, known = changelog
    problems = audit(doc.read_text(encoding="utf-8"), shipped, headings, known)
    assert not problems, f"{doc.name}:\n  - " + "\n  - ".join(problems)


# ── positive controls: the verbatim text of the real defect ──────────────────
#
# Both sentences are quoted exactly as they stood in PRIVACY.md at commit
# 32392abb, before the correction on 2026-11-05. They are the reason this file
# exists, so they are what the pattern has to catch — an invented example would
# only prove the pattern matches what its author had in mind while writing it.

_HISTORICAL_TABLE_CELL = (
    "The vehicle coordinate rounded to 3 decimals (~110 m), plus a `User-Agent` "
    "naming the integration. Results are cached per cell, so the same parking "
    "spot is not re-queried. **Up to and including 5.2.3b1 this was not true:** "
    "the rounding reached only the cache key and the request carried the "
    "full-precision coordinate. That is fixed in the repository but is not yet "
    "in a released version."
)

_HISTORICAL_PARAGRAPH = (
    "Always read an export before sharing it. A GPS-precision defect on two "
    "report surfaces is fixed in\nthe repository but is **not yet in a released "
    "version**\n([#1378](https://github.com/its-me-prash/vwgroup-connect-ha/issues/1378)), "
    "so\nan export made with 5.2.3b1 or earlier can still contain a precise\n"
    "coordinate."
)


def test_the_real_paragraph_that_went_stale_is_caught(
    changelog: tuple[dict[str, str], list[str], set[str]]
) -> None:
    shipped, headings, known = changelog
    problems = audit(_HISTORICAL_PARAGRAPH, shipped, headings, known)
    assert any("not yet released" in p and "1378" in p for p in problems), (
        "the sentence that actually went stale is no longer detected, so this "
        f"whole file now guards nothing. Problems reported: {problems}"
    )


def test_a_caution_without_a_reference_is_itself_the_finding(
    changelog: tuple[dict[str, str], list[str], set[str]]
) -> None:
    """The table cell carried no issue number at all.

    A consistency check cannot see this one: with nothing to compare, two
    documents never disagree. It needs the completeness half.
    """
    shipped, headings, known = changelog
    problems = audit(_HISTORICAL_TABLE_CELL, shipped, headings, known)
    assert any("cites no issue" in p for p in problems), (
        f"an unverifiable caution passed unreported. Problems: {problems}"
    )


def test_a_false_all_clear_is_caught(
    changelog: tuple[dict[str, str], list[str], set[str]]
) -> None:
    """The dangerous direction, driven by real data.

    The fixture needs a reference the changelog knows but no release carries —
    #1990 is one as this is written, being brand new in the `[Unreleased]` block.
    The reference is looked up rather than hard-coded, so when it eventually
    ships the control picks another pending one; and if nothing is pending at all
    it says so instead of passing on an empty set.
    """
    shipped, headings, known = changelog
    pending_only = sorted(known - set(shipped))
    assert pending_only, (
        "every issue CHANGELOG.md references now appears in some release, so "
        "this control cannot be exercised. Point it at a pending reference or "
        "remove it — do not leave it passing on an empty set."
    )
    ref = pending_only[0]
    released = [h for h in headings if h != _UNRELEASED_LABEL]
    text = f"The leak is fixed as of {released[0]} ([#{ref}](x))."
    problems = audit(text, shipped, headings, known)
    assert any("false all-clear" in p for p in problems), (
        f"claiming #{ref} shipped in {released[0]} was not reported. "
        f"Problems: {problems}"
    )


def test_a_version_that_was_never_released_is_caught(
    changelog: tuple[dict[str, str], list[str], set[str]]
) -> None:
    shipped, headings, known = changelog
    problems = audit("This is fixed as of 99.98.97.", shipped, headings, known)
    assert any("no released section" in p for p in problems), (
        f"a version that does not exist passed as an all-clear. {problems}"
    )


# ── negative controls: the things that must stay quiet ───────────────────────

@pytest.mark.parametrize(
    "innocent",
    [
        "## [Unreleased]",
        "An open release pull request renames `[Unreleased]` to the new version "
        "and adds a fresh empty `[Unreleased]` above it.",
        "A feature branch that appends to `[Unreleased]` does not textually "
        "overlap that rename.",
        "Bundles the unreleased a11-a13 work plus the EU Data Act read-path "
        "expansion. Install via the HACS beta channel to test.",
        "See #1378 for the discussion.",
        "Requires Home Assistant 2026.1.0 or newer.",
    ],
)
def test_release_bookkeeping_prose_is_not_a_claim(
    innocent: str, changelog: tuple[dict[str, str], list[str], set[str]]
) -> None:
    """A pattern keyed on the word "unreleased" would fire on all of these.

    The last two matter especially: the changelog convention is *documented* in
    RELEASE_PROCESS.md and in the changelog's own preamble, and a guard that
    reddens on the documentation of the convention it depends on gets deleted
    rather than fixed.
    """
    shipped, headings, known = changelog
    assert not audit(innocent, shipped, headings, known), innocent


# ── controls on the instrument itself ────────────────────────────────────────

def test_scope_is_provable_on_a_copy(tmp_path: Path) -> None:
    """The reach of the check, exercised somewhere other than the real repo.

    A completeness check keyed on the real path cannot be falsified. This plants
    documents in a throwaway tree and asserts which ones are picked up.
    """
    (tmp_path / "PRIVACY.md").write_text("x", encoding="utf-8")
    (tmp_path / "README.md").write_text("x", encoding="utf-8")
    (tmp_path / "CHANGELOG.md").write_text("x", encoding="utf-8")
    (tmp_path / "CLAUDE.md").write_text("x", encoding="utf-8")
    (tmp_path / "notes.txt").write_text("x", encoding="utf-8")
    templates = tmp_path / ".github" / "ISSUE_TEMPLATE"
    templates.mkdir(parents=True)
    (templates / "bug_report.yml").write_text("x", encoding="utf-8")

    found = {p.name for p in collect_docs(tmp_path)}
    assert found == {"PRIVACY.md", "README.md", "bug_report.yml"}, found


def test_a_planted_stale_claim_in_a_real_file_is_found(
    tmp_path: Path, changelog: tuple[dict[str, str], list[str], set[str]]
) -> None:
    """End to end on disk: collector plus audit, not just the audit.

    Proving only ``audit`` would leave the file-discovery layer untested, and a
    scope that never matches is the quietest way for this guard to stop working.
    """
    shipped, headings, known = changelog
    (tmp_path / "PRIVACY.md").write_text(_HISTORICAL_PARAGRAPH, encoding="utf-8")
    docs = collect_docs(tmp_path)
    assert [p.name for p in docs] == ["PRIVACY.md"]
    assert audit(docs[0].read_text(encoding="utf-8"), shipped, headings, known)


def test_the_changelog_is_newest_first(
    changelog: tuple[dict[str, str], list[str], set[str]]
) -> None:
    """``shipped_refs`` reports the newest shipping release, which this assumes."""
    _, headings, _known = changelog
    assert headings, "no `## [...]` headings parsed — the anchor is broken"
    assert headings[0] == _UNRELEASED_LABEL, (
        f"the first heading is {headings[0]!r}, not [Unreleased]. If the "
        "changelog is no longer newest-first, 'the newest heading citing a "
        "reference' in this module means the oldest one."
    )
    dated = [h for h in headings[1:] if " - " in h]
    dates = [h.split(" - ", 1)[1][:10] for h in dated]
    assert dates == sorted(dates, reverse=True), (
        "release headings are not in descending date order; the first heading "
        "citing a reference is therefore not its newest entry"
    )


def test_the_real_documents_actually_contain_a_claim() -> None:
    """Instrument control: without this, a pattern that stopped matching
    anything would make the parametrized guard above pass on every document.
    """
    hits = 0
    for doc in _DOCS:
        for sentence, _ in _units(doc.read_text(encoding="utf-8")):
            if _STALE_CAUTION.search(sentence) or _ALL_CLEAR.search(sentence):
                hits += 1
    assert hits, (
        "no document makes any release claim at all. Measured on 2026-11-05 "
        "there were two, both in PRIVACY.md. Either they were removed — then "
        "say so here — or the pattern no longer matches and this file is "
        "checking nothing."
    )
