# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Every shipped language must carry every string, or the dialog breaks.

Home Assistant does not fall back to English for a custom integration. A key
that exists in ``en.json`` and is missing from ``fr.json`` does not quietly
render in English for a French user, it renders as the raw key or as nothing at
all. So a translation file that lags behind is not a cosmetic debt, it is a
broken settings dialog for everyone using that language, and it fails silently:
the tests pass, the integration loads, and only a user in that language ever
sees it.

That is exactly how twelve keys added with the companion channel reached ten of
the eleven shipped translations as blanks. Nothing in the suite noticed, because
nothing was looking.

Placeholders are pinned for the same reason. ``{path}`` is not a word, it is a
substitution the code performs, and a translation that drops it or renames it
produces either a literal brace in the dialog or a KeyError at render time.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

_TRANSLATIONS = (
    Path(__file__).resolve().parents[1]
    / "custom_components" / "vag_connect" / "translations"
)
_STRINGS = (
    Path(__file__).resolve().parents[1]
    / "custom_components" / "vag_connect" / "strings.json"
)


def _flatten(obj: object, prefix: str = "") -> dict[str, str]:
    """Nested translation dict → {dotted.key: text}."""
    out: dict[str, str] = {}
    if isinstance(obj, dict):
        for key, value in obj.items():
            out.update(_flatten(value, f"{prefix}.{key}" if prefix else key))
    elif isinstance(obj, str):
        out[prefix] = obj
    return out


def _load(path: Path) -> dict[str, str]:
    return _flatten(json.loads(path.read_text(encoding="utf-8")))


def _placeholders(text: str) -> set[str]:
    import re

    return set(re.findall(r"\{(\w+)\}", text))


_ENGLISH = _load(_TRANSLATIONS / "en.json")
_LANGS = sorted(
    p.stem for p in _TRANSLATIONS.glob("*.json") if p.stem != "en"
)


def test_there_are_translations_to_check() -> None:
    """Guard against the whole file passing because a glob found nothing."""
    assert len(_LANGS) >= 10, _LANGS
    assert len(_ENGLISH) > 500, len(_ENGLISH)


@pytest.mark.parametrize("lang", _LANGS)
def test_no_string_is_missing(lang: str) -> None:
    translated = _load(_TRANSLATIONS / f"{lang}.json")
    missing = sorted(set(_ENGLISH) - set(translated))
    assert not missing, (
        f"{lang}.json is missing {len(missing)} string(s); a user running Home "
        f"Assistant in this language sees the raw key instead:\n  "
        + "\n  ".join(missing[:20])
    )


@pytest.mark.parametrize("lang", _LANGS)
def test_no_string_is_orphaned(lang: str) -> None:
    """A key no longer in English is dead weight, and usually a typo in a key
    name, which reads as a missing translation from the other side."""
    translated = _load(_TRANSLATIONS / f"{lang}.json")
    extra = sorted(set(translated) - set(_ENGLISH))
    assert not extra, f"{lang}.json has {len(extra)} key(s) English does not: {extra[:20]}"


@pytest.mark.parametrize("lang", _LANGS)
def test_placeholders_survive_translation(lang: str) -> None:
    translated = _load(_TRANSLATIONS / f"{lang}.json")
    drifted = {
        key: (sorted(_placeholders(_ENGLISH[key])), sorted(_placeholders(translated[key])))
        for key in set(_ENGLISH) & set(translated)
        if _placeholders(_ENGLISH[key]) != _placeholders(translated[key])
    }
    assert not drifted, (
        f"{lang}.json changes the substitutions the code performs: {drifted}"
    )


def test_strings_json_matches_the_english_translation() -> None:
    """``strings.json`` is what Home Assistant validates the integration
    against; letting it drift from the shipped English is how a key ends up
    translated everywhere and rendered nowhere."""
    strings = _load(_STRINGS)
    only_en = sorted(set(_ENGLISH) - set(strings))
    only_strings = sorted(set(strings) - set(_ENGLISH))
    assert not only_en and not only_strings, (
        f"only in en.json: {only_en[:10]}\nonly in strings.json: {only_strings[:10]}"
    )
