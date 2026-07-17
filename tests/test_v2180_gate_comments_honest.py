# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Comments claiming ``_DATA_PRESENT_REQUIRED`` gating must be telling the truth.

A comment above ``requests_remaining_today`` said the sensor was "gated via
``_DATA_PRESENT_REQUIRED``". It never was, and the other 20 gate comments in
the tree were fine — so the odd one out was invisible: the described behaviour
was real, just produced by a different mechanism (``hide_empty``). Nobody
noticed because nothing checks a comment.

The cost of that kind of drift isn't the comment. It's that the next person
reasoning about whether a sensor can phantom-spawn reads the comment, believes
the wrong gate is in play, and draws a conclusion the code doesn't support.
That's how the CHANGELOG ended up claiming a Touareg fix that could never fire.

So: parse the frozensets, map every gate comment to the description it sits
above, and fail when a claim doesn't hold. Cheap to run, and it turns a class
of silent rot into a red test.
"""
from __future__ import annotations

import ast
import io
import pathlib
import tokenize

import pytest

_ROOT = pathlib.Path(__file__).resolve().parents[1] / "custom_components/vag_connect"
_GATE = "_DATA_PRESENT_REQUIRED"
_DESC_CALL_SUFFIX = "Description"


def _members(path: pathlib.Path) -> tuple[set[str], int]:
    """Parse the frozenset literal. Never grep this — the members are data."""
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        target = None
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            target = node.target.id
        elif (
            isinstance(node, ast.Assign)
            and node.targets
            and isinstance(node.targets[0], ast.Name)
        ):
            target = node.targets[0].id
        if target != _GATE:
            continue
        value = node.value
        if isinstance(value, ast.Call) and getattr(value.func, "id", None) == "frozenset":
            return set(ast.literal_eval(value.args[0])), node.lineno
        return set(ast.literal_eval(value)), node.lineno
    raise AssertionError(f"{_GATE} not found in {path.name}")


def _literal_span(path: pathlib.Path, lineno: int) -> tuple[int, int]:
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if getattr(node, "lineno", None) == lineno:
            return lineno, node.end_lineno or lineno
    return lineno, lineno


def _descriptions(path: pathlib.Path) -> list[tuple[int, str]]:
    out: list[tuple[int, str]] = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if not isinstance(node, ast.Call):
            continue
        name = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
        if not name or not name.endswith(_DESC_CALL_SUFFIX):
            continue
        for kw in node.keywords:
            if kw.arg == "key" and isinstance(kw.value, ast.Constant):
                out.append((node.lineno, kw.value.value))
    return sorted(out)


# A claim has to be read as a block, not a line. Comments wrap, so the verb and
# its negation routinely land on different lines than the gate name — the very
# comment this test was written for says "deliberately NOT in" one line above
# the mention. Judging line-by-line reads that as a claim of the opposite.
_NEGATIONS = ("not in", "isn't in", "is not in", "deliberately not", "never in")


def _gate_comment_blocks(path: pathlib.Path) -> list[tuple[int, str]]:
    """[(last_lineno, block_text)] for each contiguous comment block naming the gate."""
    src = path.read_text(encoding="utf-8")
    blocks: list[tuple[int, str]] = []
    cur: list[str] = []
    last = 0
    for tok in tokenize.generate_tokens(io.StringIO(src).readline):
        if tok.type == tokenize.COMMENT:
            if cur and tok.start[0] == last + 1:
                cur.append(tok.string)
            else:
                if cur:
                    blocks.append((last, " ".join(cur)))
                cur = [tok.string]
            last = tok.start[0]
    if cur:
        blocks.append((last, " ".join(cur)))
    return [(ln, text) for ln, text in blocks if _GATE in text]


def _is_a_claim_of_gating(block: str) -> bool:
    lowered = block.lower()
    return not any(neg in lowered for neg in _NEGATIONS)


@pytest.mark.parametrize("fname", ["sensor.py", "binary_sensor.py"])
def test_every_gate_claim_holds(fname: str) -> None:
    path = _ROOT / fname
    members, gate_ln = _members(path)
    lo, hi = _literal_span(path, gate_ln)
    descs = _descriptions(path)

    liars = []
    for ln, text in _gate_comment_blocks(path):
        if lo <= ln <= hi:
            continue  # inside the set literal: annotating a member, not claiming
        if not _is_a_claim_of_gating(text):
            continue  # a comment saying it is NOT gated is not a claim that it is
        nxt = next(((dln, key) for dln, key in descs if dln > ln), None)
        if nxt is None:
            continue
        dln, key = nxt
        if dln - ln > 25:
            continue  # too far to be describing this description
        if key not in members:
            liars.append(f"{fname}:{ln} claims {key!r} is gated — it is not. {text[:70]}")

    assert liars == [], "\n".join(liars)


def test_the_quota_trio_stays_out_of_the_gate() -> None:
    """A decision, pinned deliberately.

    These three are fed by the X-RateLimit-* response headers. They are NOT in
    the set and should not be: the set's own docstring says it is for fields
    that "simply doesn't publish", and warns that "most existing sensors
    legitimately start as None and populate later, so they should NOT be gated
    this way". A rate-limit header is transport metadata that can appear on the
    first response carrying it — the populate-later case exactly.

    Phantom entities are already prevented by ``hide_empty`` (default on). The
    only users this would change are those who turned hide_empty off, i.e. who
    explicitly asked to see everything.

    If someone adds them anyway, this fails and they have to say why here.
    """
    members, _ = _members(_ROOT / "sensor.py")
    for key in ("requests_remaining_today", "requests_limit_today", "requests_reset_at"):
        assert key not in members, (
            f"{key} was added to {_GATE}. That overrides hide_empty=False for "
            f"users who asked to see everything — say why, and fix the comment "
            f"above the description, which documents the opposite decision."
        )


def test_hide_empty_is_the_gate_that_actually_hides_them() -> None:
    """The mechanism the comment now names must still be there and default on."""
    src = (_ROOT / "sensor.py").read_text(encoding="utf-8")
    assert "if hide_empty and desc.key not in _REPORTER_KEYS and desc.data_key:" in src
    # Default-on, read options-then-data (entry.options is blanked by the
    # update listener, so an options-only read would silently default).
    assert "entry.data.get(CONF_HIDE_EMPTY_ENTITIES, True)" in src
