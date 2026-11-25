# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""scripts/build_contributors.py: pagination ends, nothing is dropped.

Until 2026-11-25 the script paged issues, pull requests and discussions in one
query and reset a finished connection's cursor to None, so the next request
fetched its first page again and the loop never ended. These tests drive
``collect`` with fake GitHub answers, no network.
"""
from __future__ import annotations

import importlib.util
import pathlib
import sys
from typing import Any

import pytest

_SCRIPT = pathlib.Path(__file__).resolve().parent.parent / "scripts" / "build_contributors.py"


def _load() -> Any:
    spec = importlib.util.spec_from_file_location("_build_contributors", _SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["_build_contributors"] = mod
    spec.loader.exec_module(mod)
    return mod


bc = _load()


def _page(logins: list[str], nxt: str | None) -> dict:
    return {
        "pageInfo": {"hasNextPage": nxt is not None, "endCursor": nxt},
        "nodes": [{"author": {"login": name}} for name in logins],
    }


# issues: three pages, pull requests: one, discussions: two. With the old
# reset, pull requests would have been fetched from the start again after
# their single page, and the loop would not have ended.
_PAGES = {
    ("issues", None): _page(["alice", "its-me-prash"], "i1"),
    ("issues", "i1"): _page(["bob"], "i2"),
    ("issues", "i2"): _page(["carol", "dependabot[bot]"], None),
    ("pullRequests", None): _page(["dave", "github-actions[bot]"], None),
    ("discussions", None): _page(["erin"], "d1"),
    ("discussions", "d1"): _page(["frank"], None),
}


def test_every_page_is_fetched_exactly_once_and_the_loop_ends() -> None:
    calls: list[tuple[str, str | None]] = []

    def graphql(field: str, after: str | None) -> dict:
        calls.append((field, after))
        return _PAGES[(field, after)]

    found = bc.collect(graphql=graphql, rest=lambda endpoint: [])
    assert calls == [
        ("issues", None), ("issues", "i1"), ("issues", "i2"),
        ("pullRequests", None),
        ("discussions", None), ("discussions", "d1"),
    ]
    assert found == {"alice", "bob", "carol", "dave", "erin", "frank"}


def test_rest_comment_lists_add_names_and_bots_stay_out() -> None:
    seen: list[str] = []

    def rest(endpoint: str) -> list[str]:
        seen.append(endpoint)
        return {"issues/comments": ["grace", "renovate[bot]"],
                "pulls/comments": ["heidi", "its-me-prash"]}[endpoint]

    found = bc.collect(graphql=lambda field, after: _PAGES[(field, after)], rest=rest)
    assert seen == ["issues/comments", "pulls/comments"]
    assert {"grace", "heidi"} <= found
    assert not {"renovate[bot]", "its-me-prash"} & found


def test_a_cursor_that_does_not_move_stops_the_run() -> None:
    calls: list[str | None] = []

    def stuck(field: str, after: str | None) -> dict:
        calls.append(after)
        return _page(["x"], "same")

    with pytest.raises(SystemExit) as exc:
        bc.collect(graphql=stuck, rest=lambda endpoint: [])
    assert exc.value.code == 2
    # Stops at the second answer, not only when the page budget runs out.
    assert calls == [None, "same"]


def test_the_page_budget_stops_an_endless_connection(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(bc, "MAX_PAGES", 5)
    calls: list[str | None] = []

    def endless(field: str, after: str | None) -> dict:
        calls.append(after)
        return _page(["x"], f"c{len(calls)}")

    with pytest.raises(SystemExit) as exc:
        bc.collect(graphql=endless, rest=lambda endpoint: [])
    assert exc.value.code == 2
    assert len(calls) == 5


def test_a_thread_with_more_than_100_comments_is_named(capsys: pytest.CaptureFixture[str]) -> None:
    pages = dict(_PAGES)
    pages[("discussions", "d1")] = {
        "pageInfo": {"hasNextPage": False, "endCursor": None},
        "nodes": [{"number": 7, "author": {"login": "frank"},
                   "comments": {"totalCount": 140, "nodes": []}}],
    }
    bc.collect(graphql=lambda field, after: pages[(field, after)], rest=lambda endpoint: [])
    assert "discussions #7 hat 140 Kommentare" in capsys.readouterr().err


def test_merge_is_additive_and_ignores_case() -> None:
    added, unseen, result = bc.merge(found={"foo", "Baz"}, was={"Foo", "bar"})
    assert added == ["Baz"]
    assert unseen == ["bar"]
    assert result == {"Foo", "bar", "Baz"}


def test_render_keeps_the_existing_order() -> None:
    text = bc.render({"b", "A", "a", "C"})
    names = [line[3:] for line in text.splitlines() if line.startswith("- @")]
    assert names == ["A", "a", "b", "C"]
    assert text.startswith(bc.HEADER)


def test_check_fails_on_a_missing_name_and_writes_nothing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path,
) -> None:
    out = tmp_path / "CONTRIBUTORS.md"
    out.write_text(bc.render({"alice"}), encoding="utf-8")
    before = out.read_bytes()
    monkeypatch.setattr(bc, "OUT", out)
    monkeypatch.setattr(bc, "collect", lambda: {"alice", "bob"})
    monkeypatch.setattr(sys, "argv", ["build_contributors.py", "--check"])
    assert bc.main() == 1
    assert out.read_bytes() == before

    monkeypatch.setattr(sys, "argv", ["build_contributors.py", "--write"])
    assert bc.main() == 0
    assert "- @bob" in out.read_text(encoding="utf-8")

    monkeypatch.setattr(sys, "argv", ["build_contributors.py", "--check"])
    assert bc.main() == 0
