#!/usr/bin/env python3
"""Build the SHORT release body for a version, and link the long one.

Why this exists
---------------
``release.yml`` used to paste the version's whole ``CHANGELOG.md`` section into
the GitHub Release body verbatim. For v5.1.0 that was **44 681 characters over
653 lines**. Home Assistant shows that body in its update dialog, and HACS
shows it in the store listing, so on a phone the useful part — what changed and
whether it affects me — was buried under paragraphs of measurement and
reasoning.

The reasoning is worth keeping. It just does not belong in a notification.

So there are two audiences and now two documents:

* **the release body** — one line per change, with its issue number and the
  people who reported or fixed it. Scannable on a phone, and enough to decide
  whether to read further.
* **CHANGELOG.md** — unchanged, and still the long form: what broke, why, how
  it was measured, what was deliberately not done. The release body links
  straight to the version's anchor there, so a reader (or a model summarising
  the release) is one click from the full account rather than being handed a
  shorter version of the truth.

Nothing is written twice. Every changelog entry already opens with a bold
title, and that title *is* the short form — the long body is the paragraphs
after it. This reads the titles out rather than asking anyone to maintain a
second list that would drift.

Usage
-----
    python scripts/build_release_notes.py --version 5.2.0
    python scripts/build_release_notes.py --version 5.2.0 --section Unreleased
    python scripts/build_release_notes.py --version 5.2.0 --out /tmp/notes.md
"""
from __future__ import annotations

import argparse
import pathlib
import re
import sys

REPO = "its-me-prash/vwgroup-connect-ha"

#: Keep-a-Changelog groups, in the order a reader cares about them.
_GROUP_ORDER = ("Removed", "Added", "Changed", "Fixed", "Security", "Notes")

#: ``### Behoben / Fixed`` → ``Fixed``. The file's headings are bilingual and
#: the English half is the stable one (RELEASE_PROCESS.md, EN-primary since
#: v2.4.1), so the group name is taken from the last ``/``-separated part.
_HEADING_RE = re.compile(r"^###\s+(.+?)\s*$")
_ENTRY_RE = re.compile(r"^- \*\*")
#: An issue or pull request reference, in a link or bare.
_REF_RE = re.compile(r"#(\d{2,6})\b")
#: A GitHub handle. Not ``@`` inside an e-mail address or a code span.
_HANDLE_RE = re.compile(r"(?<![\w.@/])@([A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?)\b")
#: A reference an entry writes into its own bold title, e.g. ``(#1902)``.
#: One OR MORE comma-separated numbers. The single-number form was all this
#: matched until 5.2.3, so a title ending ``(#709, #1950)`` kept its numbers and
#: the line then carried them twice — once in the title, once in the reference
#: list the builder appends.
_TITLE_REF_RE = re.compile(r"\s*\(#\d{2,6}(?:,\s*#\d{2,6})*\)\s*$")
#: A reference whose link target is a **Discussion**. GitHub numbers
#: Discussions separately from issues and pull requests, so a bare ``#1415`` in
#: a release body autolinks to *issue* 1415 — a different object, and in this
#: repository someone else's. The one entry here whose subject is a discussion
#: sent the reader to an unrelated issue, which is a wrong destination rather
#: than a cosmetic flaw, so these are rendered as explicit links instead.
_DISCUSSION_REF_RE = re.compile(
    r"\[(?:discussion )?#(\d{2,6})\]\(([^)]*?/discussions/\d+)\)"
)
#: A reference the entry closes with, e.g. ``([#1843](…))`` as its last token.
_TRAILING_REF_RE = re.compile(r"\(\[(?:discussion )?#(\d{2,6})\]\([^)]*\)\)\s*$")


def section_for(changelog: str, heading: str) -> str:
    """The body of one ``## [...]`` section, without its heading line."""
    pattern = rf"^## \[{re.escape(heading)}\][^\n]*\n(.*?)(?=^## \[|\Z)"
    match = re.search(pattern, changelog, re.DOTALL | re.MULTILINE)
    return match.group(1).strip() if match else ""


def split_entries(section: str) -> list[tuple[str, list[str]]]:
    """``[(group, [entry_text, ...]), ...]`` in the order they appear.

    An entry runs from its ``- **`` line to the next entry or group heading,
    so its continuation lines and following paragraphs come with it. That
    matters because the issue numbers and the handles are usually *in* those
    paragraphs, not in the title.
    """
    groups: list[tuple[str, list[str]]] = []
    current: str | None = None
    buf: list[str] = []
    entries: list[str] = []

    def flush_entry() -> None:
        text = "\n".join(buf).strip()
        buf.clear()
        # Only a real entry. The prose that sits between a group heading and
        # its first bullet was being buffered as one too, which produced an
        # empty "- " line per group and inflated the change count.
        if text.startswith("- **"):
            entries.append(text)

    def flush_group() -> None:
        flush_entry()
        if current is not None and entries:
            groups.append((current, list(entries)))
        entries.clear()

    for line in section.splitlines():
        head = _HEADING_RE.match(line)
        if head:
            flush_group()
            current = head.group(1).split("/")[-1].strip()
            continue
        if _ENTRY_RE.match(line):
            flush_entry()
        buf.append(line)
    flush_group()
    return groups


def title_of(entry: str) -> str:
    """The entry's bold title, as one line.

    The title wraps across source lines, so the entry is joined before the
    ``**…**`` is taken — reading only the first line would truncate most of
    them mid-sentence.
    """
    joined = " ".join(entry.splitlines())
    joined = re.sub(r"\s+", " ", joined)
    match = re.search(r"\*\*(.+?)\*\*", joined)
    text = match.group(1) if match else joined.lstrip("- ").strip()
    text = text.strip().rstrip(".").strip()
    # A number written into the title is moved out of it, because the
    # references are appended separately. Suppressing the duplicate the other
    # way round was the first attempt and it is wrong: with "(#1902)" left in
    # the title and stripped from the tail, the line read "… battery again
    # (#1902) — #1661", whose only trailing number belongs to the precedent
    # the entry cites rather than to the change itself.
    text = _TITLE_REF_RE.sub("", text).strip().rstrip(".").strip()
    return text


def refs_of(entry: str) -> list[str]:
    """Issue/PR numbers, de-duplicated, in first-appearance order."""
    seen: list[str] = []
    for num in _REF_RE.findall(entry):
        if num not in seen:
            seen.append(num)
    return seen


def handles_of(entry: str) -> list[str]:
    """GitHub handles, de-duplicated, excluding the maintainer's own."""
    seen: list[str] = []
    for handle in _HANDLE_RE.findall(entry):
        low = handle.lower()
        if low in ("its-me-prash",) or handle in seen:
            continue
        seen.append(handle)
    return seen


#: How many references one line may carry before it stops being scannable.
_MAX_REFS = 4


def subject_ref(entry: str) -> str | None:
    """The number this entry is *about*, when the entry itself says which.

    Two signals, and the measurement that decides how far to trust them: of
    the 16 entries in this release, one carries its number in the bold title
    and three close with ``([#N](…))`` — and those four are **exactly** the
    entries where source order puts a cited precedent in front of the subject.
    The other twelve carry neither signal and already list their subject
    first. So a signal, where present, identifies the subject; where absent,
    nothing is reordered and the behaviour is unchanged.

    This is deliberately not a general rule about reference position. Only 3
    of 16 entries end with a parenthetical, so the trailing form is a habit
    rather than a convention, and treating it as one would misfire on the
    majority.
    """
    title_nums = _REF_RE.findall(title_of(entry))
    if title_nums:
        return title_nums[0]
    trailing = _TRAILING_REF_RE.search(entry.rstrip())
    return trailing.group(1) if trailing else None


def short_line(entry: str) -> str:
    title = title_of(entry)
    parts: list[str] = []
    discussions = dict(_DISCUSSION_REF_RE.findall(entry))
    refs = refs_of(entry)

    # The subject first. Left in source order, the e-mail-code entry read
    # "#1313 #1679 #1843" — two issues closed months earlier in front of the
    # one the line is actually about, which is the number a reader reads first.
    subject = subject_ref(entry)
    if subject is not None and subject in refs:
        refs = [subject] + [n for n in refs if n != subject]

    if refs:
        # Capped, not chosen: beyond the subject, an entry's remaining
        # references are all genuinely related and there is no signal saying
        # which matters more, so they are kept in source order and bounded.
        shown = refs[:_MAX_REFS]
        more = len(refs) - len(shown)
        rendered = [
            f"[discussion #{n}]({discussions[n]})" if n in discussions else f"#{n}"
            for n in shown
        ]
        parts.append(" ".join(rendered) + (f" +{more}" if more else ""))
    people = handles_of(entry)
    if people:
        parts.append("thanks " + ", ".join(f"@{h}" for h in people))
    tail = f" — {' · '.join(parts)}" if parts else ""
    return f"- {title}{tail}"


def build(changelog: str, version: str, heading: str | None = None) -> str:
    heading = heading or version
    section = section_for(changelog, heading)
    if not section:
        raise SystemExit(
            f"no '## [{heading}]' section in CHANGELOG.md — nothing to build"
        )
    groups = split_entries(section)
    if not groups:
        raise SystemExit(
            f"'## [{heading}]' has no '- **…**' entries; refusing to publish an "
            "empty release body rather than guessing"
        )

    anchor = f"https://github.com/{REPO}/blob/v{version}/CHANGELOG.md"
    out: list[str] = []
    out.append("## What changed / Was hat sich geändert")
    out.append("")

    ordered = sorted(
        groups,
        key=lambda g: _GROUP_ORDER.index(g[0]) if g[0] in _GROUP_ORDER else 99,
    )
    total = 0
    for name, entries in ordered:
        out.append(f"**{name}**")
        out.append("")
        for entry in entries:
            out.append(short_line(entry))
            total += 1
        out.append("")

    out.append("---")
    out.append("")
    out.append(
        f"📖 **The full account of all {total} change"
        f"{'s' if total != 1 else ''} is in the changelog:** "
        f"[CHANGELOG.md → v{version}]({anchor})"
    )
    out.append("")
    out.append(
        "Each line above is one paragraph there: what broke, how it was "
        "measured, and what was deliberately left alone. Written out in full "
        "on purpose — for anyone debugging the same thing, and so a summary of "
        "this release can be made from the reasoning rather than from the "
        "headline."
    )
    out.append("")
    out.append(
        "Die vollständige Fassung jedes Punkts steht im Changelog, verlinkt "
        "oben."
    )
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--version", required=True, help="e.g. 5.2.0")
    ap.add_argument(
        "--section",
        help="CHANGELOG heading to read if it is not the version itself "
             "(e.g. Unreleased, for a dry run before the rename)",
    )
    ap.add_argument("--file", default="CHANGELOG.md")
    ap.add_argument("--out", help="write here instead of stdout")
    args = ap.parse_args(argv)

    changelog = pathlib.Path(args.file).read_text(encoding="utf-8")
    notes = build(changelog, args.version, args.section)

    if args.out:
        pathlib.Path(args.out).write_text(notes + "\n", encoding="utf-8")
        print(
            f"wrote {len(notes)} characters / {notes.count(chr(10)) + 1} lines "
            f"to {args.out}"
        )
    else:
        # The output is markdown for GitHub, not for a console. On Windows the
        # default stdout codec is cp1252 and the emoji in the footer raised
        # UnicodeEncodeError, so the encoding is pinned rather than inherited.
        try:
            sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
        except (AttributeError, OSError):  # pragma: no cover - exotic stdout
            pass
        sys.stdout.write(notes + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
