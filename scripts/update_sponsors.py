#!/usr/bin/env python3
"""Refresh the README "Sponsors" list from GitHub Sponsors.

PRIVACY IS THE POINT OF THIS SCRIPT. GitHub Sponsors lets a sponsor choose to be
PUBLIC or PRIVATE. We list **only** public sponsors, by name/avatar. Private
sponsors are never named — we only show an aggregate "and N private sponsors"
count, which reveals nothing about who they are. A sponsor who set themselves to
private stays private here, full stop.

Safety rails:
  * No token, an auth error, or an empty API result => the script makes NO change
    (it never wipes the existing list). A transient failure must not blank the
    README or drop a real sponsor.
  * Only ``privacyLevel == PUBLIC`` entities are written by name.

Env:
  SPONSORS_TOKEN  a token with the ``read:user`` scope (the default Actions
                  GITHUB_TOKEN cannot read sponsorships). Set it as a repo secret.
  SPONSORS_LOGIN  maintainer login (default: its-me-prash).

Usage:
  SPONSORS_TOKEN=... python scripts/update_sponsors.py            # update README
  SPONSORS_TOKEN=... python scripts/update_sponsors.py --check    # print, no write

Exit code is always 0 on a clean run (changed or not); non-zero only on a real
error the caller should notice. Prints "changed=true|false" for CI to branch on.
"""
from __future__ import annotations

import json
import os
import re
import sys
import urllib.request
from pathlib import Path

_README = Path(__file__).resolve().parent.parent / "README.md"
_START = "<!-- SPONSORS:START -->"
_END = "<!-- SPONSORS:END -->"
_API = "https://api.github.com/graphql"

_QUERY = """
query($login: String!) {
  user(login: $login) {
    sponsorshipsAsMaintainer(first: 100, activeOnly: true, includePrivate: true,
                             orderBy: {field: CREATED_AT, direction: ASC}) {
      totalCount
      nodes {
        privacyLevel
        tier { monthlyPriceInDollars }
        sponsorEntity {
          __typename
          ... on User { login url avatarUrl }
          ... on Organization { login url avatarUrl }
        }
      }
    }
  }
}
"""


def _fail(msg: str, code: int = 1) -> None:
    print(f"update_sponsors: {msg}", file=sys.stderr)
    sys.exit(code)


def _fetch(token: str, login: str) -> dict:
    body = json.dumps({"query": _QUERY, "variables": {"login": login}}).encode()
    req = urllib.request.Request(
        _API, data=body,
        headers={
            "Authorization": f"bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "vag-connect-sponsors-watch",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310 (fixed host)
        return json.loads(resp.read().decode())


def _render(public: list[dict], private_count: int) -> str:
    """Build the markdown block that goes between the markers."""
    lines: list[str] = []
    if public:
        lines.append("Huge thank you to the people funding this work:")
        lines.append("")
        avatars = []
        for e in public:
            login = e["login"]
            avatars.append(
                f'<a href="{e["url"]}" title="{login}">'
                f'<img src="{e["avatarUrl"]}&s=64" width="56" height="56" '
                f'alt="{login}" style="border-radius:50%"></a>'
            )
        lines.append("<p>" + " ".join(avatars) + "</p>")
    else:
        lines.append(
            "Be the first public sponsor to show up here — thank you either way!"
        )
    if private_count:
        who = "sponsor" if private_count == 1 else "sponsors"
        lines.append("")
        lines.append(
            f"_...and {private_count} private {who}, who we thank just as much "
            f"(kept private by their own choice)._"
        )
    return "\n".join(lines)


def main() -> int:
    check_only = "--check" in sys.argv
    token = os.environ.get("SPONSORS_TOKEN", "").strip()
    login = os.environ.get("SPONSORS_LOGIN", "its-me-prash").strip()

    if not token:
        # No token: do nothing. NEVER wipe the list on a missing secret.
        print("changed=false")
        print("update_sponsors: no SPONSORS_TOKEN, leaving README untouched.",
              file=sys.stderr)
        return 0

    try:
        data = _fetch(token, login)
    except Exception as exc:  # noqa: BLE001 - any failure = leave README as is
        print("changed=false")
        print(f"update_sponsors: API call failed ({exc}); README untouched.",
              file=sys.stderr)
        return 0

    if data.get("errors"):
        print("changed=false")
        print(f"update_sponsors: GraphQL errors {data['errors']}; README untouched.",
              file=sys.stderr)
        return 0

    node = (((data.get("data") or {}).get("user") or {})
            .get("sponsorshipsAsMaintainer") or {})
    nodes = node.get("nodes")
    if nodes is None:
        # Could not read the sponsor list at all (scope?) — do not touch anything.
        print("changed=false")
        print("update_sponsors: no sponsor data returned; README untouched.",
              file=sys.stderr)
        return 0

    public, private_count = [], 0
    for n in nodes:
        ent = n.get("sponsorEntity") or {}
        if n.get("privacyLevel") == "PUBLIC" and ent.get("login"):
            public.append(ent)
        else:
            private_count += 1

    block = _render(public, private_count)

    text = _README.read_text(encoding="utf-8")
    if _START not in text or _END not in text:
        _fail(f"markers {_START} / {_END} not found in README.md")
    new = re.sub(
        re.escape(_START) + r".*?" + re.escape(_END),
        f"{_START}\n{block}\n{_END}",
        text,
        count=1,
        flags=re.DOTALL,
    )

    changed = new != text
    print(f"changed={'true' if changed else 'false'}")
    print(f"update_sponsors: {len(public)} public, {private_count} private.",
          file=sys.stderr)
    if check_only:
        print(block, file=sys.stderr)
        return 0
    if changed:
        _README.write_text(new, encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
