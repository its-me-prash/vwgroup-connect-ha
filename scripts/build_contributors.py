# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Rebuild CONTRIBUTORS.md from the tracker.

The file has always described itself as "auto-compiled", but nothing in the
repository compiled it — so it drifted. On 2026-10-10 eleven of the twelve
people whose reports had been used that week were missing from it, which is the
opposite of what a credit list is for.

Collects everyone who authored or commented on an issue, a pull request or a
discussion, or left a review, excluding bots and the maintainer, and merges them
into the list. ADDITIVE: it never removes a name, because a gap in the query is
not evidence that somebody did not contribute. Idempotent otherwise.

Usage (PowerShell):
    & "$env:LOCALAPPDATA\\Python\\bin\\python.exe" scripts/build_contributors.py --check
    & "$env:LOCALAPPDATA\\Python\\bin\\python.exe" scripts/build_contributors.py --write

``--check`` prints who would be added or removed and exits 1 if the file is out
of date, so CI can hold the line; ``--write`` updates it. Needs the ``gh`` CLI
authenticated against this repository.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import subprocess
import sys

REPO_OWNER = "its-me-prash"
REPO_NAME = "vwgroup-connect-ha"
OUT = pathlib.Path(__file__).resolve().parent.parent / "CONTRIBUTORS.md"

# The maintainer is the author of the project, not a reporter of it; bots are
# not people. Everything else that ever spoke on the tracker belongs in.
EXCLUDE_EXACT = {"its-me-prash"}
BOT_RE = re.compile(r"(\[bot\]$|^dependabot|^github-actions|^renovate|^codecov)", re.I)

HEADER = """# Contributors & Reporters

VW Group Connect is made better by the people who take the time to file \
field-Scout reports, open issues, send diagnostics and logs, request features, \
join the discussions, and test on real cars. This integration would be far \
poorer without them. **Thank you** 🙏

Everyone below has reported an issue or a Vehicle Data Scout finding, requested \
a feature, or taken part in a discussion on this repository (rebuilt by \
`scripts/build_contributors.py`; alphabetical, bots excluded). If you've \
contributed and aren't listed, that's an oversight — please open an issue and \
we'll fix it.

"""

_QUERY = """
query($owner:String!, $name:String!, $ic:String, $pc:String, $dc:String) {
  repository(owner:$owner, name:$name) {
    issues(first:100, after:$ic) {
      pageInfo { hasNextPage endCursor }
      nodes { author { login } comments(first:100) { nodes { author { login } } } }
    }
    pullRequests(first:100, after:$pc) {
      pageInfo { hasNextPage endCursor }
      nodes { author { login } comments(first:100) { nodes { author { login } } }
              reviews(first:50) { nodes { author { login } } } }
    }
    discussions(first:100, after:$dc) {
      pageInfo { hasNextPage endCursor }
      nodes { author { login } comments(first:50) {
        nodes { author { login } replies(first:50) { nodes { author { login } } } } } }
    }
  }
}
"""


def _gh_graphql(**variables: object) -> dict:
    args = ["gh", "api", "graphql", "-f", f"query={_QUERY}"]
    for key, value in variables.items():
        if value is None:
            continue
        args += ["-f", f"{key}={value}"]
    run = subprocess.run(args, capture_output=True, text=True,
                         encoding="utf-8", check=False)
    if run.returncode != 0:
        print(f"gh api failed: {run.stderr.strip()[:400]}")
        sys.exit(2)
    return json.loads(run.stdout)


def _logins(node: object, into: set[str]) -> None:
    """Walk any nested author/login structure and collect every login."""
    if isinstance(node, dict):
        if "login" in node and isinstance(node["login"], str):
            into.add(node["login"])
        for value in node.values():
            _logins(value, into)
    elif isinstance(node, list):
        for value in node:
            _logins(value, into)


def collect() -> set[str]:
    found: set[str] = set()
    cursors: dict[str, str | None] = {"ic": None, "pc": None, "dc": None}
    more = True
    pages = 0
    while more:
        data = _gh_graphql(owner=REPO_OWNER, name=REPO_NAME, **cursors)
        repo = data["data"]["repository"]
        _logins(repo, found)
        more = False
        for key, field in (("ic", "issues"), ("pc", "pullRequests"),
                           ("dc", "discussions")):
            info = repo[field]["pageInfo"]
            if info["hasNextPage"]:
                cursors[key] = info["endCursor"]
                more = True
            else:
                cursors[key] = None
        pages += 1
        print(f"  Seite {pages}: {len(found)} Namen bisher", file=sys.stderr)
    return {
        name for name in found
        if name not in EXCLUDE_EXACT and not BOT_RE.search(name)
    }


def render(people: set[str]) -> str:
    ordered = sorted(people, key=lambda s: (s.lower(), s))
    return HEADER + "\n".join(f"- @{name}" for name in ordered) + "\n"


def existing() -> set[str]:
    if not OUT.exists():
        return set()
    return set(re.findall(r"^- @(\S+)", OUT.read_text(encoding="utf-8"), re.M))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true", help="update CONTRIBUTORS.md")
    ap.add_argument("--check", action="store_true",
                    help="report drift and exit 1 if out of date")
    args = ap.parse_args()
    if not (args.write or args.check):
        ap.error("pass --check or --write")

    found = collect()
    was = existing()
    added = sorted(found - was)
    unseen = sorted(was - found)
    # ADDITIVE ONLY. A credit list must never drop someone because a query did
    # not re-find them: a contribution can arrive through a surface this query
    # does not cover (a review thread, a renamed account, a transferred issue),
    # and @naked-head — whose field correction is quoted in the parser to this
    # day — was one of four names the first run would have deleted.
    people = found | was
    print(f"\nGefunden: {len(found)} · in der Datei: {len(was)} "
          f"· Ergebnis: {len(people)}")
    if added:
        print(f"NEU ({len(added)}): {', '.join(added)}")
    if unseen:
        print(f"BEHALTEN, von der Abfrage nicht gefunden ({len(unseen)}): "
              f"{', '.join(unseen)}")
    if not added:
        print("Datei ist aktuell.")
        return 0

    if args.write:
        OUT.write_text(render(people), encoding="utf-8")
        print(f"geschrieben: {OUT.name}")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
