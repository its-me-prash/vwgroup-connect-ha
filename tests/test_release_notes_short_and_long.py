# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""A release body that was 44 681 characters long.

Measured, not estimated: v5.1.0's published release body is **44 681
characters over 654 lines**, because ``release.yml`` pasted the version's whole
``CHANGELOG.md`` section into it verbatim. That body is what Home Assistant
shows in its update dialog and what HACS shows in the store listing, so on a
phone the part a reader needs first — what changed, and does it affect me —
sat under paragraphs of measurement and reasoning.

The reasoning is the point of the changelog and none of it is removed. It just
does not belong in a notification. So there are two documents for two
audiences:

* **the release body** — one line per change, each with its issue number and
  the people who reported or fixed it;
* **CHANGELOG.md** — unchanged, still the long form, linked from the body at
  the version's own tag so a reader (or a model summarising the release) is one
  click from the full account rather than from a shortened truth.

Nothing is maintained twice. Every entry already opens with a bold title, and
that title *is* the short form — these tests pin that the short body is derived
from it rather than written alongside it, because a second hand-kept list would
drift and no test would notice.
"""
from __future__ import annotations

import pathlib
import re
import sys

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import build_release_notes as brn  # noqa: E402


# ── fixtures ───────────────────────────────────────────────────────────────


def _changelog() -> str:
    return (REPO_ROOT / "CHANGELOG.md").read_text(encoding="utf-8")


def _workflow() -> str:
    return (REPO_ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")


_HEADINGS = re.compile(r"^## \[([^\]]+)\]", re.MULTILINE)


def _newest_section_with_entries() -> tuple[str, str]:
    """``(heading, section_text)`` for the newest section that has entries.

    Deliberately not hardcoded to ``[Unreleased]``. Right after a release that
    section is empty, and every assertion below that iterates over its entries
    would then pass by iterating over nothing — the vacuous-pass shape this
    file exists to prevent elsewhere. Walking to the newest non-empty section
    means these tests keep testing something on every day of the cycle.
    """
    changelog = _changelog()
    for heading in _HEADINGS.findall(changelog):
        section = brn.section_for(changelog, heading)
        if brn.split_entries(section):
            return heading, section
    pytest.fail("no CHANGELOG section has any '- **…**' entries")


#: An entry opener, counted straight out of the source for comparison against
#: the generated body. Counted independently of split_entries on purpose: if
#: the splitter silently dropped entries, a count taken from the splitter
#: itself would agree with it and prove nothing.
_ENTRY_OPENER = re.compile(r"^- \*\*", re.MULTILINE)


# ── the shape the user reads ────────────────────────────────────────────────


def test_every_entry_becomes_exactly_one_line() -> None:
    """No change is dropped, and none is split in two.

    This is the assertion that makes "shorter" safe. A body that is short
    because it lost half the entries would satisfy every size bound here.
    """
    heading, section = _newest_section_with_entries()
    expected = len(_ENTRY_OPENER.findall(section))
    assert expected >= 1

    body = brn.build(_changelog(), "9.9.9", heading)
    produced = [ln for ln in body.splitlines() if ln.startswith("- ")]
    assert len(produced) == expected, (
        f"{expected} entries in [{heading}] produced {len(produced)} lines"
    )


def test_no_line_is_empty() -> None:
    """The first version emitted a bare ``- `` per group.

    The prose that sits between a group heading and its first bullet was being
    buffered as an entry, so each group opened with an empty bullet and the
    change count was inflated — 17 reported for 15 real changes.
    """
    heading, _ = _newest_section_with_entries()
    body = brn.build(_changelog(), "9.9.9", heading)
    for line in body.splitlines():
        if line.startswith("- "):
            assert line.strip() not in ("-", "- "), "an empty bullet is back"
            assert len(line) > 12, f"suspiciously short line: {line!r}"


def test_each_line_names_its_issue() -> None:
    """What was asked for: the ticket number, on the line.

    Enforced against the real changelog rather than a fixture, so an entry
    written without a reference fails here instead of reaching a release body
    where a reader cannot look the change up.
    """
    heading, _ = _newest_section_with_entries()
    body = brn.build(_changelog(), "9.9.9", heading)
    unnumbered = [
        ln for ln in body.splitlines()
        if ln.startswith("- ") and not re.search(r"#\d{2,6}", ln)
    ]
    assert not unnumbered, (
        "these changes carry no issue or PR number, so a reader cannot look "
        f"them up: {unnumbered}"
    )


def test_a_number_in_the_title_moves_out_of_it() -> None:
    """Some entries write their own number into the bold title.

    This was first fixed the other way round — the title kept ``(#1902)`` and
    the duplicate was stripped from the reference list — and that was wrong in
    a way only a line-by-line audit of the real output caught: the entry also
    cites ``#1661`` as precedent, so suppressing its own number left
    ``… battery again (#1902) — #1661``, whose only trailing number belongs to
    a different change. The number is moved out of the title instead, so the
    references list is complete and starts with the right one.
    """
    entry = (
        "- **Something is fixed again (#1902).** The body cites #1661 as the "
        "precedent it follows."
    )
    line = brn.short_line(entry)
    assert line.count("#1902") == 1, f"the number is duplicated: {line}"
    assert "again (#1902)" not in line, "the number is still inside the title"
    assert "#1902 #1661" in line, (
        f"the entry's own number must come first, not the precedent: {line}"
    )


def test_the_subject_reference_comes_first() -> None:
    """Source order puts a cited precedent in front of the actual subject.

    The real case: ``The e-mail code step no longer tells you your password is
    wrong`` cites two older hardenings before closing with its own issue, so
    the line read ``#1313 #1679 #1843`` — the number a reader reads first was
    a different, closed change from months earlier.
    """
    entry = (
        "- **The e-mail code step no longer tells you your password is "
        "wrong.** It was hardened for exactly this in "
        "[#1313](https://github.com/x/y/issues/1313) and "
        "[#1679](https://github.com/x/y/issues/1679). "
        "([#1843](https://github.com/x/y/issues/1843))"
    )
    line = brn.short_line(entry)
    assert "#1843 #1313 #1679" in line, line


def test_source_order_is_kept_when_the_entry_gives_no_signal() -> None:
    """The limit of the rule above, and why it is safe.

    Only 3 of 16 entries in this release close with a parenthetical, so the
    trailing form is a habit and not a convention. Entries with neither signal
    already list their subject first — the Scout entry below is about all
    three of its issues — so nothing is reordered for them. Reordering on a
    guess would misfire on the majority.
    """
    entry = (
        "- **An unmappable field stops asking three different people.** It "
        "raised the repair on Volkswagen ([#1831](https://github.com/x/y/issues/1831)), "
        "on an ID.7 ([#1838](https://github.com/x/y/issues/1838)) and on a "
        "Tavascan ([#1861](https://github.com/x/y/issues/1861))."
    )
    assert brn.subject_ref(entry) is None, "an entry with no signal claimed one"
    assert "#1831 #1838 #1861" in brn.short_line(entry)


def test_a_discussion_is_linked_not_hash_numbered() -> None:
    """A bare ``#1415`` would send the reader to the wrong object.

    GitHub numbers Discussions separately from issues and pull requests, so
    ``#1415`` in a release body autolinks to *issue* 1415 — which exists, and
    is somebody else's. The one line in this release whose subject is a
    discussion pointed at an unrelated issue, which is a wrong destination
    rather than an untidy one.
    """
    entry = (
        "- **The Vehicle Status sensor was blank.** @someone reported it on a "
        "Tavascan ([discussion #1415](https://github.com/x/y/discussions/1415)), "
        "and #923 already guaranteed the opposite."
    )
    line = brn.short_line(entry)
    assert "[discussion #1415](https://github.com/x/y/discussions/1415)" in line, line
    assert " #1415" not in line.replace("[discussion #1415]", ""), (
        f"the discussion is still emitted as a bare issue reference: {line}"
    )
    assert "#923" in line, "the ordinary issue reference was lost"


def test_every_discussion_reference_in_the_real_section_is_linked() -> None:
    """Pinned against the shipping changelog, not only a fixture: an entry
    added later with a discussion link must not regress to a bare number."""
    heading, section = _newest_section_with_entries()
    body = brn.build(_changelog(), "9.9.9", heading)
    for num in re.findall(r"/discussions/(\d+)", section):
        assert f"discussion #{num}" in body or f"#{num}" not in body, (
            f"discussion {num} appears as a bare #{num}, which links to issue "
            f"{num} instead"
        )


def test_a_wrapped_title_is_read_whole() -> None:
    """Titles wrap across source lines. Reading only the first line would
    truncate most of them mid-sentence, which is how this was first written."""
    entry = (
        "- **The charge-timer sensors and the charging calendar are no\n"
        "  longer off by your UTC offset.** @someone measured it.\n"
    )
    title = brn.title_of(entry)
    assert title.endswith("off by your UTC offset"), title
    assert "\n" not in title


def test_contributors_are_credited_and_the_maintainer_is_not() -> None:
    """Also what was asked for. The maintainer's own handle is excluded —
    thanking yourself in your own release notes reads badly and it is on every
    entry, so it would crowd out the people who actually reported things."""
    entry = (
        "- **A thing.** @somebody reported it, @another confirmed it, and "
        "@its-me-prash fixed it. @somebody also sent diagnostics."
    )
    line = brn.short_line(entry)
    assert "thanks @somebody, @another" in line, line
    assert "its-me-prash" not in line
    assert line.count("@somebody") == 1, "a handle is credited twice"


def test_many_references_are_capped_not_dropped_silently() -> None:
    """A line with eight numbers on it is not scannable, which is the whole
    point of the short form. The overflow is counted rather than discarded, so
    the line never claims to list them all."""
    entry = "- **A thing.** See #11, #22, #33, #44, #55, #66."
    line = brn.short_line(entry)
    shown = re.findall(r"#\d+", line)
    assert len(shown) == brn._MAX_REFS, line
    assert "+2" in line, f"two references vanished without a trace: {line}"


# ── the long form stays reachable ──────────────────────────────────────────


def test_the_long_form_is_linked_at_the_version_tag() -> None:
    """``main`` would drift: a reader opening v5.2.0's notes in six months must
    land on what v5.2.0 actually said, not on the current file."""
    heading, _ = _newest_section_with_entries()
    body = brn.build(_changelog(), "5.2.0", heading)
    assert "/blob/v5.2.0/CHANGELOG.md" in body, (
        "the changelog link is missing or not pinned to the version's tag"
    )
    assert "CHANGELOG.md" in body


def test_the_body_says_how_many_changes_the_long_form_covers() -> None:
    """So a reader can tell the short body is a summary of a known quantity
    rather than a selection someone made."""
    heading, section = _newest_section_with_entries()
    expected = len(_ENTRY_OPENER.findall(section))
    body = brn.build(_changelog(), "9.9.9", heading)
    assert f"all {expected} change" in body, (
        f"the body does not state the real change count ({expected})"
    )


def test_the_short_body_is_actually_short() -> None:
    """The change list must not grow with the *detail* of the entries, only
    with their count.

    The first version of this compared the WHOLE body against the section and
    it was wrong in a way that only a small release exposes. The body carries a
    fixed header, changelog link and footer that do not shrink with the
    section — measured at 570, 602 and 641 characters against sections of
    2 350, 26 814 and 42 259. On a section with many entries that overhead
    disappears into the ratio; on a one-entry section it is most of the body,
    so the gate failed on the release that was *most* summarised. It had
    passed until then only because every section it had ever seen was large.

    What actually encodes "this is a summary" is the change list itself.
    """
    heading, section = _newest_section_with_entries()
    body = brn.build(_changelog(), "9.9.9", heading)
    changes = [ln for ln in body.splitlines() if ln.startswith("- ")]
    change_chars = sum(len(ln) for ln in changes)
    assert change_chars < len(section) / 4, (
        f"the change list is {change_chars} chars against a {len(section)}-char "
        f"section across {len(changes)} entries — the lines have started "
        "carrying the paragraphs instead of summarising them"
    )
    # and the fixed part stays fixed, so the footer cannot quietly balloon
    overhead = len(body) - change_chars
    assert overhead < 1200, (
        f"the body's non-change part is {overhead} chars; it has been ~600 "
        "and is meant to be a header, a link and a footer"
    )


def test_an_empty_or_missing_section_refuses_rather_than_guessing() -> None:
    """The workflow catches this and falls back to the link. What must not
    happen is a release published with a confidently empty change list."""
    with pytest.raises(SystemExit):
        brn.build("## [1.0.0]\n\nnothing here\n", "9.9.9")
    with pytest.raises(SystemExit):
        brn.build("## [1.0.0]\n\n### Fixed\n\nprose, no entries\n", "1.0.0")


# ── the workflow actually uses it ──────────────────────────────────────────


def _workflow_code() -> str:
    """The workflow's python with comment lines removed.

    Comments are stripped before any of the assertions below look at this,
    because three times in this batch a text gate was satisfied by the very
    comment explaining the fix. The prose below mentions "the entire CHANGELOG
    section verbatim"; that must not be able to pass for the code doing it.
    """
    return "\n".join(
        ln for ln in _workflow().splitlines() if not ln.strip().startswith("#")
    )


def test_the_workflow_builds_the_short_body() -> None:
    code = _workflow_code()
    assert "from build_release_notes import build" in code, (
        "release.yml no longer calls the short-notes builder"
    )
    assert "build_short_notes(changelog, version)" in code


def test_the_workflow_no_longer_pastes_the_section_verbatim() -> None:
    """The actual regression guard. Everything else here could pass while the
    workflow quietly went back to appending the whole section."""
    code = _workflow_code()
    assert "changelog_section" not in code, (
        "the verbatim CHANGELOG section is being assembled again; that is "
        "what produced the 44 681-character body"
    )


def test_the_workflow_survives_a_version_with_no_section() -> None:
    """A tag whose changelog section is missing must still publish a release,
    with the changelog linked in place of the list.

    Failing the notes step would leave a pushed, immutable tag with no release
    and no ``vag_connect.zip``. That the *run* now ends red afterwards is a
    separate thing, pinned by
    ``test_the_run_ends_red_when_the_change_list_is_missing``.

    The needle used to be the old fallback's ``for details._`` wording, which
    this change replaced with a body that states it is incomplete. The needle
    moved to the changelog link, which is the part that actually has to
    survive — the wording was never the point.
    """
    code = _workflow_code()
    assert "except SystemExit" in code, (
        "the builder's refusal is no longer caught; a missing section would "
        "now fail the release job after the tag already exists"
    )
    assert "/blob/v{version}/CHANGELOG.md" in code, (
        "the fallback no longer links the changelog, so a degraded release "
        "page would say what is missing without saying where to find it"
    )


# ── the degraded path cannot pass for a normal release ─────────────────────
#
# The failure this guards: pushing a tag before CHANGELOG.md's [Unreleased]
# heading has been renamed to the version. The builder then refuses, the
# workflow catches it, and the release publishes with no change list — on a
# green run, with a ::warning:: in the log as the only trace. That body is what
# Home Assistant shows in its update dialog and HACS in the store listing, so
# every user saw an empty-looking release and nothing said why. Tags are
# immutable, so it is found late or not at all.


def test_the_fallback_body_says_it_is_incomplete() -> None:
    """It must not read like a deliberately terse release.

    The first version appended ``_See the CHANGELOG.md for details._`` under a
    normal "What's new" heading, which is indistinguishable from a release that
    simply had little to say.
    """
    code = _workflow_code()
    assert "The change list could not be generated" in code, (
        "the fallback body no longer announces itself as incomplete"
    )
    assert "This release page is incomplete" in code
    # and in German too, since the body is bilingual everywhere else
    assert "unvollständig" in code


def test_the_degraded_path_records_a_flag() -> None:
    """The run has to be able to find out, not just the reader."""
    code = _workflow_code()
    assert 'degraded = "true"' in code, "the degraded path sets no flag"
    assert "GITHUB_OUTPUT" in code and "degraded=true" in code, (
        "the flag is never written where a later step can read it"
    )


def test_the_run_ends_red_when_the_change_list_is_missing() -> None:
    """A ``::warning::`` is not a signal — nothing reads the log of a green
    run. The job has to fail.

    Scoped to the verification step's own block, because the first version of
    this asserted ``"exit 1" in code`` over the whole file and the *tag/manifest
    mismatch* step already contains one. Turning this step's ``exit 1`` into
    ``exit 0`` left the test passing — a gate satisfied by unrelated code, which
    the mutation check is what caught.
    """
    yml = _workflow()
    step = yml[yml.index("- name: Release-Notes vollständig?"):]
    assert "steps.notes.outputs.degraded" in step, (
        "the verification step does not read the degraded flag, so the run "
        "still ends green"
    )
    assert "exit 1" in step, (
        "the verification step cannot fail the run any more"
    )
    assert "::error::" in step, "the step no longer reports an error"
    # and the degraded path itself must raise an error, not a warning
    code = _workflow_code()
    assert "::error::release body has no change list" in code, (
        "the degraded path is back to a warning nobody reads"
    )


def test_the_check_runs_after_the_release_exists() -> None:
    """The ordering is the whole design.

    Failing *before* the release is created would leave a pushed, immutable tag
    with no GitHub Release and no ``vag_connect.zip`` — worse than a thin body.
    So the release is published first and the run goes red afterwards: nothing
    is lost and nothing is silent.
    """
    yml = _workflow()
    create = yml.index("- name: GitHub Release erstellen")
    check = yml.index("- name: Release-Notes vollständig?")
    assert create < check, (
        "the completeness check now runs before the release is created; a "
        "failure there would leave a public tag with no release and no zip"
    )
    # and the release step must not be conditional on the flag
    release_block = yml[create:check]
    assert "degraded" not in release_block, (
        "publishing the release is now gated on the flag, which is exactly "
        "the trade this design avoids"
    )


def test_both_paths_behave_as_designed_when_actually_run() -> None:
    """The real workflow block, executed, rather than asserted about.

    Extracted from release.yml and run on a temporary tree, once for a version
    whose section exists and once for one that does not. Text assertions above
    can all pass while the assembled behaviour is wrong; this is the one that
    would notice.
    """
    import os
    import re
    import shutil
    import subprocess
    import tempfile

    yml = _workflow()
    match = re.search(r"python3 << 'PYTHON'\n(.*?)\n          PYTHON", yml, re.DOTALL)
    assert match, "could not find the python block in release.yml"
    block = "\n".join(
        ln[10:] if ln.startswith(" " * 10) else ln
        for ln in match.group(1).split("\n")
    )

    # The newest RELEASED section, not simply the newest one with entries.
    # Using the latter made this skip itself whenever anything was unreleased —
    # which is most of the time, and it is the strongest test in the file. The
    # happy path needs a heading the workflow would actually look up at tag
    # time, and a version heading is exactly that.
    changelog = _changelog()
    heading = next(
        (
            name
            for name in _HEADINGS.findall(changelog)
            if re.fullmatch(r"\d+\.\d+\.\d+", name)
            and brn.split_entries(brn.section_for(changelog, name))
        ),
        None,
    )
    assert heading is not None, "no released section with entries to drive"

    results = {}
    for label, version in (("happy", heading), ("degraded", "9.9.9")):
        work = pathlib.Path(tempfile.mkdtemp())
        (work / "CHANGELOG.md").write_text(changelog, encoding="utf-8")
        (work / "scripts").mkdir()
        shutil.copy(REPO_ROOT / "scripts/build_release_notes.py", work / "scripts")
        notes_path = str(work / "notes.md").replace("\\", "/")
        (work / "block.py").write_text(
            block.replace("/tmp/release_notes.md", notes_path), encoding="utf-8"
        )
        gh_output = work / "gh_output"
        gh_output.write_text("", encoding="utf-8")
        proc = subprocess.run(
            # -X utf8=1 emulates the ubuntu-latest runner, whose locale
            # encoding is UTF-8. Without it the block's bare open() uses
            # cp1252 on Windows and dies on the first non-ASCII byte, for a
            # reason that does not exist on the runner.
            [sys.executable, "-I", "-X", "utf8=1", "block.py"],
            cwd=work,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            # Windows raises WinError 6 without an explicit stdin here.
            stdin=subprocess.DEVNULL,
            env={**os.environ, "VERSION": version, "GITHUB_OUTPUT": str(gh_output)},
        )
        assert proc.returncode == 0, (
            f"[{label}] the notes step itself must not fail — the release and "
            f"the zip depend on it: {proc.stderr[-800:]}"
        )
        results[label] = (
            (work / "notes.md").read_text(encoding="utf-8"),
            gh_output.read_text(encoding="utf-8"),
            proc.stdout or "",
        )

    happy_body, happy_flag, happy_log = results["happy"]
    assert "## What changed" in happy_body
    assert "could not be generated" not in happy_body
    assert "degraded" not in happy_flag, (
        f"the happy path raised the degraded flag: {happy_flag!r}"
    )
    assert "::error::" not in happy_log

    bad_body, bad_flag, bad_log = results["degraded"]
    assert "could not be generated" in bad_body, (
        "the degraded body does not announce itself"
    )
    assert "## What changed" not in bad_body
    assert "degraded=true" in bad_flag, (
        f"the degraded path left no flag for the check step: {bad_flag!r}"
    )
    assert "::error::" in bad_log, "the degraded path still only warns"
    # the body is still written, so the release and the zip still publish
    assert len(bad_body) > 500, "the degraded path produced no body at all"


def test_the_builder_ships_with_the_repository() -> None:
    """The workflow imports it by path from the checkout, so it has to be a
    tracked file rather than something that exists only on one machine."""
    assert (REPO_ROOT / "scripts/build_release_notes.py").is_file()
    code = _workflow_code()
    assert 'sys.path.insert(0, "scripts")' in code


def test_a_prerelease_section_is_found_and_compared_against_the_last_stable() -> None:
    """A beta must not produce a degraded page — and v5.2.3b1 did.

    The version pattern in ``release.yml`` was plain semver only, so
    ``## [5.2.3b1]`` never matched, the version was absent from the list, and the
    body came out as "The change list could not be generated". Nothing had
    noticed because the "Release-Notes vollständig?" gate was added on
    2026-10-21 while the previous beta was tagged on 2026-10-04, and because the
    happy path above filters its driving heading down to plain semver — so the
    harness never ran a pre-release through the block it tests.

    This drives the real block with a pre-release heading and asserts three
    things: the section is found, the page is not degraded, and the comparison
    still points at the last STABLE version rather than at another beta.
    """
    import os
    import re
    import shutil
    import subprocess
    import tempfile

    yml = _workflow()
    match = re.search(r"python3 << 'PYTHON'\n(.*?)\n          PYTHON", yml, re.DOTALL)
    assert match, "could not find the python block in release.yml"
    block = "\n".join(
        ln[10:] if ln.startswith(" " * 10) else ln
        for ln in match.group(1).split("\n")
    )

    changelog = _changelog()
    # The NEWEST pre-release, not the first one that happens to have entries.
    # The original selection had "and brn.split_entries(...)" in it, and that
    # silently chose a healthy 4.10.0b5 while the section this test was written
    # for — 5.2.3b1, five entries and no "### " category heading — parsed to
    # zero and stayed unexamined. Choosing the input by the property under test
    # is how a test passes on a case it was meant to catch.
    beta = next(
        (
            name
            for name in _HEADINGS.findall(changelog)
            if re.fullmatch(r"\d+\.\d+\.\d+(?:a|b|rc|pre)\d*", name)
        ),
        None,
    )
    assert beta is not None, (
        "no pre-release section in the changelog to drive — this test must not "
        "quietly skip itself"
    )
    assert brn.split_entries(brn.section_for(changelog, beta)), (
        f"the newest pre-release section ({beta}) parses to zero entries, which "
        "is exactly the degraded-page defect. check_changelog_structure refuses "
        "that state, so reaching here means that gate regressed too"
    )
    last_stable = next(
        (n for n in _HEADINGS.findall(changelog) if re.fullmatch(r"\d+\.\d+\.\d+", n)),
        None,
    )
    assert last_stable is not None, "no stable section to compare against"

    work = pathlib.Path(tempfile.mkdtemp())
    (work / "CHANGELOG.md").write_text(changelog, encoding="utf-8")
    (work / "scripts").mkdir()
    shutil.copy(REPO_ROOT / "scripts/build_release_notes.py", work / "scripts")
    notes_path = str(work / "notes.md").replace("\\", "/")
    (work / "block.py").write_text(
        block.replace("/tmp/release_notes.md", notes_path), encoding="utf-8"
    )
    gh_output = work / "gh_output"
    gh_output.write_text("", encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, "-I", "-X", "utf8=1", "block.py"],
        cwd=work, capture_output=True, text=True, encoding="utf-8",
        errors="replace", stdin=subprocess.DEVNULL,
        env={**os.environ, "VERSION": beta, "GITHUB_OUTPUT": str(gh_output)},
    )
    assert proc.returncode == 0, proc.stderr[-800:]

    notes = (work / "notes.md").read_text(encoding="utf-8")
    assert "could not be generated" not in notes, (
        f"the {beta} section was not found — the page is degraded"
    )
    assert "incomplete" not in notes.lower(), "the page still reports itself degraded"
    assert gh_output.read_text(encoding="utf-8").strip() != "degraded=true", (
        "the gate flag is still set"
    )
    assert f"v{beta}" in notes, "the notes must name the version they are for"
    assert last_stable in notes, (
        f"a beta page should compare against the last stable ({last_stable}); "
        "pointing at another beta is what the position rule avoids"
    )
