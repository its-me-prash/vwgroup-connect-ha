# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#1809 — a backend refusal is not a statement about the car's platform.

An Audi e-tron 55 quattro of model year 2019, a GE-platform car, was told by
the integration that it is "an MEB / ID-family car (ID.3/4/5/7, Enyaq, Born,
Q4)". It is not one, and the reporter said so plainly.

Where that came from: ``CONF_MEB_COMMANDS_UNAVAILABLE`` is set at two places in
the config flow, and neither looks at the platform or the model. One fires when
the durable Car-Net login answers ``Unknown user``, the other when the MBB
bearer never minted. Both are backend refusals. The refusal is real on this car,
because Audi migrated the e-tron off Car-Net, so the outcome (a read-only entry)
was right; only the explanation was wrong, and a wrong explanation sends someone
looking for an answer that does not exist.

The texts now say what the refusal actually tells us: the car is not enrolled in
the legacy Car-Net system, which is expected for ID and MEB models and equally
what an older car answers once the brand has moved it off that system.

The config key keeps its name on purpose. It is persisted in ``entry.data``, so
renaming it would silently drop the flag for every entry already set up.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1] / "custom_components" / "vag_connect"
_CORRECTED = ("strings.json", "translations/en.json", "translations/de.json")


def _load(rel: str) -> dict:
    return json.loads((_ROOT / rel).read_text(encoding="utf-8"))


@pytest.mark.parametrize("rel", _CORRECTED)
def test_the_repair_no_longer_asserts_the_model_class(rel: str) -> None:
    text = _load(rel)["issues"]["meb_commands_unavailable"]["description"]
    for claim in (
        "this is an MEB / ID-family car",
        "MEB / ID-family car",
        "known limitation of VW's MEB platform",
        "ist dies ein MEB",
    ):
        assert claim not in text, claim


@pytest.mark.parametrize("rel", _CORRECTED)
def test_the_repair_names_the_answer_it_is_based_on(rel: str) -> None:
    """The user can act on the backend's own words, not on our inference."""
    text = _load(rel)["issues"]["meb_commands_unavailable"]["description"]
    assert "Unknown user" in text


# Per-language expectations, so a German file cannot pass on an English phrase.
_SECOND_CAUSE = {
    "strings.json": "older car",
    "translations/en.json": "older car",
    "translations/de.json": "älteres Auto",
}
_READ_ONLY = {
    "strings.json": "read-only",
    "translations/en.json": "read-only",
    "translations/de.json": "nur lesend",
}


@pytest.mark.parametrize("rel", _CORRECTED)
def test_the_repair_says_both_causes_are_possible(rel: str) -> None:
    text = _load(rel)["issues"]["meb_commands_unavailable"]["description"]
    assert "MEB" in text                      # still named as the expected case
    assert _SECOND_CAUSE[rel] in text         # and the one that was missing


@pytest.mark.parametrize("rel", _CORRECTED)
def test_the_repair_keeps_what_it_always_said(rel: str) -> None:
    """Correcting the cause must not drop the outcome or the placeholder."""
    text = _load(rel)["issues"]["meb_commands_unavailable"]["description"]
    assert "{brand}" in text
    assert _READ_ONLY[rel] in text
    assert text.count("\n\n") == 2


@pytest.mark.parametrize("rel", _CORRECTED)
def test_the_setup_abort_no_longer_asserts_it_either(rel: str) -> None:
    text = _load(rel)["config"]["abort"]["mbb_not_eligible"]
    assert "This means it's a newer ID / MEB model" not in text
    assert "Unknown user" in text


def test_the_persisted_key_name_is_unchanged() -> None:
    """Renaming it would drop the flag for entries already set up."""
    from custom_components.vag_connect.const import CONF_MEB_COMMANDS_UNAVAILABLE

    assert CONF_MEB_COMMANDS_UNAVAILABLE == "meb_commands_unavailable"


def test_neither_flag_site_checks_the_platform() -> None:
    """Pin the actual cause, so a future reader does not re-add the claim.

    If someone ever makes the flag depend on a real platform check, this test
    fails and the texts can be made specific again. Until then they must not
    pretend to know the model class.
    """
    src = (_ROOT / "config_flow.py").read_text(encoding="utf-8")
    assert src.count("CONF_MEB_COMMANDS_UNAVAILABLE: True") == 1
    assert src.count("entry_data[CONF_MEB_COMMANDS_UNAVAILABLE] = True") == 1
    # and both sites carry the note explaining what the flag does NOT mean
    assert src.count("#1809") >= 2
