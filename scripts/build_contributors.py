# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Rebuild CONTRIBUTORS.md from the tracker.

The file has always described itself as "auto-compiled", but nothing in the
repository compiled it — so it drifted. On 2026-10-10 eleven of the twelve
people whose reports had been used that week were missing from it, which is the
opposite of what a credit list is for.

It drifted a second time. From 2026-10-10 to 2026-11-25 nothing ran this script:
no workflow called it, and it no longer finished (see ``collect``). The list was
topped up by hand at releases, and on 2026-11-25 it was missing 204 people. The
weekly ``Contributors check`` workflow now runs ``--check``, so a gap turns a
run red instead of growing unseen.

Collects everyone who authored or commented on an issue, a pull request or a
discussion, or left a review, excluding bots and the maintainer, and merges them
into the list. ADDITIVE: it never removes a name, because a gap in the query is
not evidence that somebody did not contribute. Idempotent otherwise.

Usage:
    python scripts/build_contributors.py --check
    python scripts/build_contributors.py --write

``--check`` prints who would be added and exits 1 if the file is out of date;
``--write`` updates it. Needs the ``gh`` CLI authenticated against this
repository (in a workflow, ``GH_TOKEN`` is enough).
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import subprocess
import sys
from collections.abc import Callable

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

# One connection per request, each paged to its own end.
#
# The first version asked for issues, pull requests and discussions in ONE
# query and, when one of them ran out of pages, set its cursor back to None.
# The next request then fetched that connection's FIRST page again, which has a
# next page, so once the three needed different page counts the loop never
# ended. On 2026-11-25 it was still running at request 81 with the name count
# flat since request 15; 15 + 8 + 2 requests are enough.
#
# Page sizes: 20 discussions per page, because 100 x 100 comments x 100 replies
# exceeds GitHub's ceiling of 500,000 nodes for one query.
CONNECTIONS: dict[str, tuple[int, str]] = {
    "issues": (
        100,
        "nodes { author { login } comments(first:100) { nodes { author { login } } } }",
    ),
    "pullRequests": (
        100,
        "nodes { author { login } comments(first:100) { nodes { author { login } } }"
        " reviews(first:100) { nodes { author { login } } } }",
    ),
    "discussions": (
        20,
        "nodes { number author { login } comments(first:100) { totalCount"
        " nodes { author { login } replies(first:100) { nodes { author { login } } } } } }",
    ),
}

# Issue and pull-request comments past the first 100 of a thread are not in the
# GraphQL answer above (#465 alone has more than 140). These two REST lists
# carry every comment of the repository, so nobody is lost to that cut.
REST_COMMENT_LISTS = ("issues/comments", "pulls/comments")

# A request budget per connection, far above what the tracker needs (15 pages
# of issues on 2026-11-25), so a pagination fault ends in a loud exit instead
# of a job that runs until it is killed.
MAX_PAGES = 500

GraphQL = Callable[[str, str | None], dict]
Rest = Callable[[str], list[str]]


def _query(field: str) -> str:
    size, nodes = CONNECTIONS[field]
    return (
        "query($owner:String!, $name:String!, $after:String) {"
        " repository(owner:$owner, name:$name) {"
        f" {field}(first:{size}, after:$after) {{"
        " pageInfo { hasNextPage endCursor } " + nodes + " } } }"
    )


def _gh_graphql(field: str, after: str | None) -> dict:
    args = ["gh", "api", "graphql", "-f", f"query={_query(field)}",
            "-f", f"owner={REPO_OWNER}", "-f", f"name={REPO_NAME}"]
    if after is not None:
        args += ["-f", f"after={after}"]
    run = subprocess.run(args, capture_output=True, text=True,
                         encoding="utf-8", check=False)
    if run.returncode != 0:
        print(f"gh api failed: {run.stderr.strip()[:400]}")
        sys.exit(2)
    connection: dict = json.loads(run.stdout)["data"]["repository"][field]
    return connection


def _gh_rest_logins(endpoint: str) -> list[str]:
    run = subprocess.run(
        ["gh", "api", f"repos/{REPO_OWNER}/{REPO_NAME}/{endpoint}?per_page=100",
         "--paginate", "--jq", ".[] | .user.login // empty"],
        capture_output=True, text=True, encoding="utf-8", check=False)
    if run.returncode != 0:
        print(f"gh api failed: {run.stderr.strip()[:400]}")
        sys.exit(2)
    return [line for line in run.stdout.splitlines() if line.strip()]


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


def collect(graphql: GraphQL = _gh_graphql, rest: Rest = _gh_rest_logins) -> set[str]:
    found: set[str] = set()
    for field in CONNECTIONS:
        after: str | None = None
        for page in range(1, MAX_PAGES + 1):
            connection = graphql(field, after)
            nodes = connection.get("nodes") or []
            _logins(nodes, found)
            for node in nodes:
                comments = (node or {}).get("comments") or {}
                if (comments.get("totalCount") or 0) > 100:
                    # No silent cut: say which thread was read only in part.
                    print(f"  Warnung: {field} #{node.get('number')} hat "
                          f"{comments['totalCount']} Kommentare, gelesen 100",
                          file=sys.stderr)
            info = connection["pageInfo"]
            if not info["hasNextPage"]:
                print(f"  {field}: {page} Seite(n)", file=sys.stderr)
                break
            if not info.get("endCursor") or info["endCursor"] == after:
                print(f"{field}: Cursor bewegt sich nicht ({info.get('endCursor')!r})")
                sys.exit(2)
            after = info["endCursor"]
        else:
            print(f"{field}: mehr als {MAX_PAGES} Seiten, Paginierung defekt?")
            sys.exit(2)
    for endpoint in REST_COMMENT_LISTS:
        found.update(rest(endpoint))
    print(f"  {len(found)} Namen gesamt", file=sys.stderr)
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


def merge(found: set[str], was: set[str]) -> tuple[list[str], list[str], set[str]]:
    """Return (added, unseen, result). GitHub logins ignore case, so a name
    already listed in another spelling is not added a second time."""
    was_lower = {name.lower() for name in was}
    found_lower = {name.lower() for name in found}
    added = sorted(name for name in found if name.lower() not in was_lower)
    unseen = sorted(name for name in was if name.lower() not in found_lower)
    return added, unseen, was | set(added)


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
    # ADDITIVE ONLY. A credit list must never drop someone because a query did
    # not re-find them: a contribution can arrive through a surface this query
    # does not cover (a review thread, a renamed account, a transferred issue),
    # and @naked-head — whose field correction is quoted in the parser to this
    # day — was one of four names the first run would have deleted.
    added, unseen, people = merge(found, was)
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
