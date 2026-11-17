# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#2158 — every error the vw.de sign-in can show has a text in its dialog.

@ChristophCaina added the Volkswagen.de read channel through the options and
got ``authproxy_refused`` at the e-mail code step. The setup dialog has a text
for that key, the options dialog did not, and neither did the repair that
carries the same login (``issues.supplementary_reauth``). A key without a text
in the dialog it lands in shows no explanation there.

Pinned for ``strings.json`` and every translation:

* every key ``_map_error`` lets through (plus ``cannot_connect`` and
  ``invalid_otp``) has a text in ``config.error`` AND ``options.error`` — the
  options dialog maps errors through the same function at its vw.de steps;
* every key the shared vw.de login (``_vwde_reauth.py``) raises, plus
  ``invalid_otp``, has a text in the repair's ``fix_flow.error``.

The repair's own verdict for an unfinished code step is in
``test_1717_reauth_repair_fix_button.py``.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent / "custom_components" / "vag_connect"
_FILES = [_ROOT / "strings.json", *sorted((_ROOT / "translations").glob("*.json"))]


def _raised_by_vwde_login() -> set[str]:
    src = (_ROOT / "_vwde_reauth.py").read_text(encoding="utf-8")
    return set(re.findall(r'raise ValueError\("([a-z_]+)"\)', src))


def test_the_instruments_find_what_they_check() -> None:
    """Positive control: an empty key set would pass every check below."""
    from custom_components.vag_connect.config_flow import _MAPPED_ERROR_KEYS

    assert {"authproxy_refused", "invalid_otp", "upstream_unavailable"} <= _MAPPED_ERROR_KEYS
    assert {"authproxy_refused", "invalid_otp", "upstream_unavailable", "invalid_credentials"} <= (
        _raised_by_vwde_login())
    assert len(_FILES) == 13


@pytest.mark.parametrize("path", _FILES, ids=lambda p: p.name)
def test_mapped_errors_have_a_text_in_setup_and_options(path: Path) -> None:
    from custom_components.vag_connect.config_flow import _MAPPED_ERROR_KEYS

    data = json.loads(path.read_text(encoding="utf-8"))
    need = set(_MAPPED_ERROR_KEYS) | {"cannot_connect", "invalid_otp"}
    for block in ("config", "options"):
        have = data[block]["error"]
        missing = sorted(k for k in need if not (isinstance(have.get(k), str) and have[k].strip()))
        assert not missing, f"{path.name} {block}.error has no text for {missing}"


@pytest.mark.parametrize("path", _FILES, ids=lambda p: p.name)
def test_the_vwde_repair_has_a_text_for_every_login_error(path: Path) -> None:
    data = json.loads(path.read_text(encoding="utf-8"))
    have = data["issues"]["supplementary_reauth"]["fix_flow"]["error"]
    need = _raised_by_vwde_login() | {"invalid_otp"}
    missing = sorted(k for k in need if not (isinstance(have.get(k), str) and have[k].strip()))
    assert not missing, f"{path.name} supplementary_reauth error has no text for {missing}"


@pytest.mark.parametrize("path", _FILES, ids=lambda p: p.name)
def test_the_copied_texts_match_the_setup_dialog(path: Path) -> None:
    """The texts were taken from the same language's setup dialog, so a reader
    sees the same explanation wherever the error lands."""
    data = json.loads(path.read_text(encoding="utf-8"))
    setup = data["config"]["error"]
    for block in (data["options"]["error"], data["issues"]["supplementary_reauth"]["fix_flow"]["error"]):
        for key in ("authproxy_refused", "invalid_otp", "upstream_unavailable"):
            assert block[key] == setup[key], f"{path.name}: {key} differs from config.error"
