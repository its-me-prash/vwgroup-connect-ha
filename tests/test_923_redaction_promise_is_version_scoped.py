"""#923 — the two strings that ask for a diagnostics file may not promise more
than the redaction delivers.

Both said "everything is redacted automatically" and named *tokens* among what
is stripped. That was false from mid-June 2026 until 5.2.1: the volkswagen.de
session cookies, the MBB command tokens and the Tibber tokens were never in the
redaction list. Those two strings are what put roughly seventy files with a
live session into public issues, because the product told people it was safe.

The guard is language-independent on purpose. It does not read vocabulary — it
anchors on the colon that introduces the list of redacted items, recognised by
the identifiers spelled the same in every language (VIN, GPS, token), and
demands that the clause in front of that colon names a version rather than
making an unconditional claim.

A positive control asserts the anchor really found both sentences in every
file; without it a broken anchor would make the whole module pass while
checking nothing, which is the failure mode that let the original defect
through review.
"""
from __future__ import annotations

import io
import json
import re
from pathlib import Path

import pytest

_PKG = Path(__file__).resolve().parents[1] / "custom_components" / "vag_connect"
_FILES = [_PKG / "strings.json"] + sorted((_PKG / "translations").glob("*.json"))

# where the two assurances live
_SCOUT = ("issues", "vehicle_data_scout_findings", "description")
_COHORT = ("options", "step", "init", "data_description", "test_cohort")
_KEYS = {"scout": _SCOUT, "cohort": _COHORT}

# the clause before the colon must name a version, e.g. "5.2.1+"
_VERSIONED = re.compile(r"\d+\.\d+\.\d+")

# the languages whose copy can be written and reviewed in this project
_AUTHORED = {"strings", "en", "de"}


def _dig(data: object, path: tuple[str, ...]) -> str | None:
    cur: object = data
    for key in path:
        if not isinstance(cur, dict) or key not in cur:
            return None
        cur = cur[key]
    return cur if isinstance(cur, str) else None


def _list_clause(text: str) -> str | None:
    """The clause introducing the redaction list, or None if not found.

    Mirrors the anchor the fix used: the first colon whose following window
    mentions VIN plus token or GPS.
    """
    for colon in (i for i, ch in enumerate(text) if ch == ":"):
        window = text[colon + 1 : colon + 200].lower()
        if "vin" not in window:
            continue
        if "token" not in window and "gps" not in window:
            continue
        start = 0
        for sep in (". ", ".\n", "\n\n", "! "):
            hit = text.rfind(sep, 0, colon)
            if hit >= 0:
                start = max(start, hit + len(sep))
        if text[start : start + 1] == "_":
            start += 1
        return text[start : colon + 1]
    return None


def _cases() -> list[tuple[Path, str, str]]:
    out = []
    for path in _FILES:
        data = json.loads(io.open(path, encoding="utf-8").read())
        for label, where in _KEYS.items():
            text = _dig(data, where)
            if text is not None:
                out.append((path, label, text))
    return out


_CASES = _cases()


@pytest.mark.parametrize(
    ("path", "label", "text"),
    _CASES,
    ids=[f"{p.stem}-{lab}" for p, lab, _ in _CASES],
)
def test_the_promise_names_a_version(path: Path, label: str, text: str) -> None:
    clause = _list_clause(text)
    assert clause is not None, (
        f"{path.name}/{label}: the anchor no longer finds the redaction list. "
        "Either the sentence was restructured (then update this guard) or the "
        "list is gone (then say so) — do not leave it unchecked."
    )
    assert _VERSIONED.search(clause), (
        f"{path.name}/{label}: the redaction list is introduced by "
        f"{clause!r}, which makes an unconditional promise. It must name the "
        "version from which it holds — this exact wording is what put live "
        "session cookies into public issues for four months."
    )


def test_positive_control_both_sentences_were_found_everywhere() -> None:
    """Without this, a broken anchor would make the module vacuous."""
    assert len(_FILES) >= 13, f"only {len(_FILES)} language file(s) found"
    found = {(p.stem, lab) for p, lab, _ in _CASES}
    missing = [
        (p.stem, lab)
        for p in _FILES
        for lab in _KEYS
        if (p.stem, lab) not in found
    ]
    assert not missing, (
        f"these files no longer carry the string at all: {missing}. A missing "
        "key falls back to English, which is acceptable — but confirm that is "
        "what was intended rather than letting it pass silently."
    )
    assert len(_CASES) == 2 * len(_FILES)


# "what an older version did not do" - matched on the idea, not on one wording,
# so rephrasing the sentence does not turn this guard red for the wrong reason.
_OLDER = re.compile(r"older versions?|ältere[nr]? versionen?", re.IGNORECASE)


@pytest.mark.parametrize("stem", sorted(_AUTHORED - {"strings"}))
def test_authored_languages_say_what_older_versions_did(stem: str) -> None:
    """EN and DE carry the explicit warning, not only the version label."""
    path = next(p for p in _FILES if p.stem == stem)
    data = json.loads(io.open(path, encoding="utf-8").read())
    for label, where in _KEYS.items():
        text = _dig(data, where)
        assert text is not None, f"{path.name}: {label} is missing"
        assert _OLDER.search(text), (
            f"{path.name}/{label}: says it is redacted from 5.2.1 but never "
            "says what an older version did not redact — a reader on 5.1.3 "
            "needs the second half to act on the first"
        )
        assert "volkswagen.de" in text


def test_no_ascii_umlaut_substitutes_in_german() -> None:
    """House rule: real umlauts in user-facing German, never ae/oe/ue."""
    path = next(p for p in _FILES if p.stem == "de")
    body = io.open(path, encoding="utf-8").read()
    bad = [w for w in ("aelter", "Anhaeng", "ueber ", "oeffne") if w in body]
    assert not bad, f"ASCII umlaut substitutes in de.json: {bad}"
