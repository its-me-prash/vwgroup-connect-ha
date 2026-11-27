# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Scout intentional-skip — repair suppression WITHOUT data suppression.

`scope_potential_total` (PPE-opaque) and the ownerless opening UUIDs
`c0bb1348` / `d5dc7c87` are deliberately kept Scout-VISIBLE in diagnostics, but
they spawned a fresh hand-filed GitHub issue per reporter (#1151/#1156/#1164/…,
#1140/#1149/#1152/#1161/#1168). The intentional-skip allowlist keeps them out of
the user-facing Scout *repair* only — a genuinely-new field or a new opening UUID
still raises it.
"""
from __future__ import annotations

from custom_components.vag_connect.cariad._reporter_pipeline import (
    _is_scout_repair_skipped,
)
from custom_components.vag_connect.cariad._unexpected_keys import UnexpectedField


def _f(path: str, sample: str = "") -> UnexpectedField:
    return UnexpectedField(
        path=path, sample_masked=sample,
        endpoint="eu_data_act", first_seen_at="2026-08-14T00:00:00Z",
    )


def test_scope_potential_total_is_repair_skipped() -> None:
    assert _is_scout_repair_skipped(_f("eu_data_act.scope_potential_total", "0"))


def test_ownerless_opening_uuids_are_repair_skipped() -> None:
    assert _is_scout_repair_skipped(_f("eu_data_act.open", "true (uuid c0bb1348)"))
    assert _is_scout_repair_skipped(_f("eu_data_act.open", "true (uuid d5dc7c87)"))


def test_is_set_envelope_flags_are_repair_skipped() -> None:
    # #465/#1216 — every EU-DA `*.is_set` present-flag is envelope metadata; the
    # leaf match catches them all in one allowlist entry.
    assert _is_scout_repair_skipped(_f("eu_data_act.mileage.is_set", "true"))
    assert _is_scout_repair_skipped(_f("eu_data_act.hvbatterytemperature.is_set", "true"))
    assert _is_scout_repair_skipped(_f("eu_data_act.trunk.is_set", "true"))


def test_did_0x3504_life_cycle_data_is_repair_skipped() -> None:
    # #1979 (@mkevenaar) — the LL_GatewUDS 0x3504 blob is a raw, unmappable
    # base64-JSON envelope; it stays on the raw_api_fields sensor as an attribute
    # but must stop raising the per-poll repair (#1987/#1989/#2041/#2043 all
    # re-filed the identical leaf).
    assert _is_scout_repair_skipped(_f(
        "eu_data_act.LL_GatewUDS_ReadDataByIdentMeasuValue_Life Cycle Data 5 Generation 2_0x3504",
        "eyJzY2hlbWEiOi[...2837 chars...]",
    ))


def test_a_different_ll_gatewuds_did_still_raises_the_repair() -> None:
    # The skip is keyed to the exact 0x3504 DID leaf, not the LL_GatewUDS family:
    # the tyre-pressure DIDs 0x4E94–0x4E97 were MAPPED as unitless diagnostics, so
    # a different DID on the same logical link must still surface for mapping.
    assert not _is_scout_repair_skipped(_f(
        "eu_data_act.LL_GatewUDS_ReadDataByIdentMeasuValue_Tyre Pressure_0x4e94", "123",
    ))


def test_a_new_opening_uuid_still_raises_the_repair() -> None:
    """Keying on the UUID (not the `open` path) preserves discovery."""
    assert not _is_scout_repair_skipped(_f("eu_data_act.open", "true (uuid deadbeef)"))


def test_an_unrelated_new_field_still_raises_the_repair() -> None:
    assert not _is_scout_repair_skipped(_f("eu_data_act.some_new_field", "42"))


# #2204 follow-up — the skip needs EVERY key a row names to be ownerless. The
# samples here are what the coordinator files: mask_value wraps a string in
# quotes, so the annotation ends just before the closing quote.
def test_both_ownerless_keys_together_are_repair_skipped() -> None:
    assert _is_scout_repair_skipped(
        _f("eu_data_act.open", '"false (uuid c0bb1348, d5dc7c87)"')
    )


def test_an_unknown_opening_key_next_to_an_ownerless_one_raises_the_repair() -> None:
    """The gap the substring test left: a new opening point that sent the same
    value as c0bb1348 stood next to it and was skipped with it."""
    assert not _is_scout_repair_skipped(
        _f("eu_data_act.open", '"false (uuid c0bb1348, deadbeef)"')
    )
    assert not _is_scout_repair_skipped(
        _f("eu_data_act.open", '"false (uuid 0718582b, d5dc7c87)"')
    )


def test_quoted_single_ownerless_key_is_repair_skipped() -> None:
    assert _is_scout_repair_skipped(_f("eu_data_act.open", '"true (uuid c0bb1348)"'))


def test_a_sample_without_a_readable_annotation_keeps_the_substring_test() -> None:
    """The mask cuts a string at 80 characters, which can cut the annotation;
    then the old substring test still applies."""
    from custom_components.vag_connect.cariad._unexpected_keys import mask_value

    path = "eu_data_act.some_long_field"
    cut = mask_value("x" * 60 + " (uuid c0bb1348, deadbeef)", path_hint=path)
    assert cut.endswith('..."') and "(uuid c0bb1348" in cut  # really cut
    assert _is_scout_repair_skipped(_f(path, cut))
    assert not _is_scout_repair_skipped(
        _f("eu_data_act.some_long_field", '"' + "x" * 60 + ' (uuid deadbeef, cafe..."')
    )


def test_the_real_coordinator_sample_of_a_mixed_row_raises_the_repair() -> None:
    """End to end: the masked sample the coordinator builds from a discovery row."""
    from custom_components.vag_connect.cariad._unexpected_keys import mask_value

    row = "false (uuid c0bb1348, deadbeef)"
    path = "eu_data_act.open"
    assert not _is_scout_repair_skipped(_f(path, mask_value(row, path_hint=path)))
    row_known = "false (uuid c0bb1348)"
    assert _is_scout_repair_skipped(_f(path, mask_value(row_known, path_hint=path)))


def test_only_the_annotation_at_the_end_counts() -> None:
    """A value that itself contains text shaped like an annotation must not
    decide; the annotation the parser adds is always the last part."""
    assert not _is_scout_repair_skipped(
        _f("eu_data_act.some_new_field", '"(uuid c0bb1348) (uuid deadbeef)"')
    )
