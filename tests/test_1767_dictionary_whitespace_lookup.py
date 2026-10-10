# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#1767 (@zdimic1) / #1769 (@derschneewolf) — both Audis reported the four
tyre-pressure-sensor service-life fields with an EMPTY "Spec field (official)"
column, even though the catalogue describes all four. The cause is on our side
and it is a spelling mismatch three ways.

The catalogue was extracted from VW's PDF and the extraction left line-wrap
spaces inside the field name, so the family is listed twice:

    LL_TirePressMonit1UDS_ ReadDataByIdentMeasu Value_Left front tire …_0x4E94
    LL_TirePressMonit1UDS_ReadDataByIdentMeasuValue_Leftfronttirepressure…_0x4E94

Cars send a third spelling — unbroken prefix, real spaces in the description —
and both of our indices are exact dict lookups, so none of the three ever
matched another. Collapsing whitespace on both sides bridges them.

The fifth test is the one that matters most: a name whose whitespace-stripped
form is shared by entries with DIFFERENT units must stay unresolved here rather
than be answered with a coin-flip unit, because ``describe()`` feeds
auto-created diagnostic sensors.
"""
from __future__ import annotations

import pytest

from custom_components.vag_connect.cariad.auth import eu_data_dictionary as dd

# What @zdimic1's and @derschneewolf's cars actually send.
AS_SENT = (
    "LL_TirePressMonit1UDS_ReadDataByIdentMeasuValue_"
    "Left front tire pressure sensor remaining operation time_0x4E94"
)


def test_catalogue_really_holds_both_broken_spellings() -> None:
    """Control. If the catalogue stops shipping these, the rest proves nothing."""
    names = [
        e["name"] for e in dd._load().values()
        if isinstance(e.get("name"), str) and "4E94" in e["name"]
    ]
    assert len(names) == 2, names
    assert any(" ReadDataByIdentMeasu " in n for n in names), names
    assert any("Leftfronttirepressuresensor" in n for n in names), names
    # And neither is what the car sends — that is the whole bug.
    assert AS_SENT not in names


@pytest.mark.parametrize("wheel,did", [
    ("Left front", "0x4E94"),
    ("Right front", "0x4E95"),
    ("Left rear", "0x4E96"),
    ("Right rear", "0x4E97"),
])
def test_all_four_wheels_resolve_from_the_spelling_cars_send(
    wheel: str, did: str
) -> None:
    key = (
        "LL_TirePressMonit1UDS_ReadDataByIdentMeasuValue_"
        f"{wheel} tire pressure sensor remaining operation time_{did}"
    )
    entry = dd.lookup(key)
    assert entry is not None, f"{did} still unresolved"
    assert wheel.lower() in str(entry.get("description", "")).lower()
    assert "remaining operation time" in str(entry.get("description", "")).lower()


def test_resolves_through_the_scouts_dotted_prefix() -> None:
    """The Scout passes ``eu_data_act.<field>``, not the bare name."""
    assert dd.lookup(f"eu_data_act.{AS_SENT}") is not None


def test_no_unit_is_invented_for_these_fields() -> None:
    """The catalogue publishes no unit and no type here, and neither do we.

    Resolving the name must not start claiming a quantity — this is the field
    family we deliberately refused to turn into sensors.
    """
    entry = dd.lookup(AS_SENT)
    assert entry is not None
    assert entry.get("unit") in (None, "", "-")
    assert entry.get("type") in (None, "", "-")
    # describe() therefore returns the bare name, with no "(unit)" suffix.
    label = dd.describe(AS_SENT)
    assert label and "(" not in label


def test_a_name_with_a_contested_stripped_form_stays_unresolved() -> None:
    """``Fuel level`` is ``(%)``/number in one cluster and unitless/string in
    another, so its stripped form is ambiguous and must NOT answer a lookup.

    A made-up spelling that only normalises onto it has to come back None.
    Otherwise an auto-created sensor could inherit whichever unit won the race.
    """
    assert dd.lookup("Fuel  level") is None
    assert dd.lookup("F u e l l e v e l") is None
    # The exact spellings still resolve, unchanged, via the exact index.
    assert dd.lookup("Fuel level") is not None
    assert dd.lookup("Fuellevel") is not None


def test_exact_matches_are_unaffected() -> None:
    """The fallback must not change any field that already resolved."""
    for name in ("soc", "odometer", "target_soc"):
        entry = dd.lookup(name)
        assert entry is not None, name
        assert entry.get("name") == name


def test_unknown_names_still_return_none() -> None:
    assert dd.lookup("definitely_not_a_portal_field_xyz") is None
    assert dd.lookup("   ") is None
    assert dd.lookup(None) is None
