# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""A warning you cannot act on is a warning that gets dismissed.

@starwarsfan (#1896) runs an Audi Q4 e-tron and a Škoda on one setup and got:

    ***022149: Fahrzeugdaten seit 216 h nicht mehr aktualisiert

Two separate faults in one card.

**It does not say which car.** The title carried the masked VIN alone, which is
recognisable only to someone who has gone and looked it up. He has two cars; the
warning told him something was wrong without telling him what. The card now
names the vehicle the way the device page does — through the *same* helper, so
the two cannot drift apart — and falls back to the masked VIN when there is no
label, which is exactly what it did before.

**And it told him to open volkswagen.de.** He has an Audi and a Škoda. That
instruction was wrong twice over: wrong site for a non-Volkswagen owner, and
wrong place even for a Volkswagen, because a lapsed EU Data Act feed is fixed in
the portal and not on volkswagen.de. His own words are the reason this matters
more than a typo would: *"I don't want to touch the setup for that car, which is
already working!"* — a card that misdirects is a card that gets people to break
something that works.

The description also asserted the EU Data Act as one of exactly two causes. This
repair fires for **any** car whose capture stamp has aged past the threshold,
including one read over a brand channel, where that cause cannot apply at all.
The opener is source-neutral now and two conditional paragraphs say what to do
in each case.
"""
from __future__ import annotations

import json
import pathlib
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from custom_components.vag_connect.repairs import raise_issue_stale_data

# Synthetic, per CONTRIBUTING: real shape, zeroed serial. The reporter's
# own masked tail went in here first and the VIN guard refused it -- the
# second time today, and the guard was right both times. His tail stays in
# the docstring, where it is prose rather than a literal.
_VIN = "WVWZZZAUZFW000000"
_IR = "custom_components.vag_connect.repairs.ir"


def _raise(**kw: Any) -> dict:
    """Call the repair and return the kwargs it handed the issue registry."""
    with patch(_IR) as ir:
        raise_issue_stale_data(
            MagicMock(), "entry1", _VIN,
            masked_vin="***000000", age_hours=216, **kw,
        )
    return ir.async_create_issue.call_args.kwargs


# ── the card names the car ─────────────────────────────────────────────────


def test_the_card_carries_the_car_label() -> None:
    got = _raise(car="Audi Q4 e-tron")
    assert got["translation_placeholders"]["car"] == "Audi Q4 e-tron"


def test_without_a_label_it_falls_back_to_the_masked_vin() -> None:
    """Strictly what it did before, so a car we cannot name is no worse off."""
    assert _raise()["translation_placeholders"]["car"] == "***000000"
    assert _raise(car=None)["translation_placeholders"]["car"] == "***000000"
    assert _raise(car="")["translation_placeholders"]["car"] == "***000000"


def test_the_masked_vin_is_still_passed_and_still_masked() -> None:
    """#1626 — the full VIN must never reach the issue registry, which is
    dumped verbatim into config-entry diagnostics."""
    got = _raise(car="Audi Q4 e-tron")
    assert got["translation_placeholders"]["vin"] == "***000000"
    assert _VIN not in str(got)


def test_a_label_that_leaked_a_full_vin_would_be_caught() -> None:
    """The label comes from the vehicle dict, and that dict has a ``vin`` key.
    If the naming helper ever started falling back to the raw VIN, it would
    reach the registry through this new placeholder."""
    got = _raise(car=f"Audi {_VIN}")
    assert _VIN in str(got), (
        "this test documents the hazard; if it ever fails the helper changed "
        "and the guard below is what matters"
    )
    # The real guard: the coordinator builds the label with _device_name, which
    # uses only the last 6 characters when no model is known.
    from custom_components.vag_connect.entity_base import _device_name

    label = _device_name({"vin": _VIN}, "audi")
    assert _VIN not in label
    assert label.endswith("000000")


# ── it names it the same way the device page does ──────────────────────────


def test_the_label_matches_the_device_page() -> None:
    """Same helper, not a second implementation — otherwise the card and the
    device list drift and the user is back to matching VINs by eye."""
    from custom_components.vag_connect.entity_base import _device_name

    veh = {"vin": _VIN, "model": "Q4 e-tron"}
    assert _device_name(veh, "audi") == "Audi Q4 e-tron"


def test_the_coordinator_passes_a_label_built_from_that_helper() -> None:
    """Checked against the source: the call site must not grow its own naming.

    This asserted ``"car=_device_name(data" in src`` until @starwarsfan
    checked the shipped result and found it still wrong — so the assertion was
    pinning the defect rather than the fix. Two things were wrong with routing
    the card straight through ``_device_name``: it never consults the device
    registry, so a car the owner renamed was called something else; and it
    read the VIN out of the snapshot, which on a thin one is missing, leaving
    the bare brand label. Both are why ``_car_label`` exists.

    The assertion is kept, aimed at the helper that is now correct, because
    the original intent still holds: the call site must not grow its own
    naming logic.
    """
    import inspect

    from custom_components.vag_connect import coordinator as _coord

    src = inspect.getsource(_coord)
    assert "car=self._car_label(" in src, (
        "the stale-data repair stopped naming the car through _car_label"
    )
    assert "car=_device_name(data" not in src, (
        "the card is naming the car from the snapshot again, which ignores a "
        "rename and degrades to the brand label when the snapshot is thin"
    )


# ── the text, in every language ────────────────────────────────────────────


def _cards() -> list[tuple[str, dict]]:
    from custom_components.vag_connect import const

    root = pathlib.Path(const.__file__).parent
    files = [root / "strings.json", *sorted((root / "translations").glob("*.json"))]
    assert len(files) == 13, "the language set changed; check this test"
    return [
        (p.name, json.loads(p.read_text(encoding="utf-8"))["issues"]["stale_data"])
        for p in files
    ]


@pytest.mark.parametrize("name,card", _cards())
def test_every_title_names_the_car(name: str, card: dict) -> None:
    assert "{car}" in card["title"], name
    assert "{vin}" not in card["title"], f"{name} still titles by VIN"
    assert "{age}" in card["title"], name


@pytest.mark.parametrize("name,card", _cards())
def test_no_language_still_sends_people_to_volkswagen_de(name: str, card: dict) -> None:
    """The half that was wrong for every non-Volkswagen owner, and wrong about
    the destination even for a Volkswagen one."""
    assert "volkswagen.de" not in card["description"], name


@pytest.mark.parametrize("name,card", _cards())
def test_no_opener_asserts_the_eu_data_act_as_the_cause(name: str, card: dict) -> None:
    """This card also fires for brand-channel cars, where that cause cannot
    apply. The conditional paragraphs below the opener carry it instead."""
    opener = card["description"].split("\n\n")[0]
    assert "EU Data Act" not in opener, name
    assert "EU-Data-Act" not in opener, name


@pytest.mark.parametrize("name,card", _cards())
def test_every_language_points_at_the_portal_for_the_portal_case(
    name: str, card: dict
) -> None:
    assert "vwgroup-datahub" in card["description"], name


@pytest.mark.parametrize("name,card", _cards())
def test_the_placeholders_the_card_uses_are_the_ones_it_is_given(
    name: str, card: dict
) -> None:
    """A placeholder the raise site does not pass renders literally as
    ``{foo}`` in front of the user."""
    import re

    supplied = {"car", "vin", "age"}
    used = set(re.findall(r"\{(\w+)\}", card["title"] + card["description"]))
    assert used <= supplied, f"{name} uses {used - supplied}"
