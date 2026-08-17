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


def test_a_new_opening_uuid_still_raises_the_repair() -> None:
    """Keying on the UUID (not the `open` path) preserves discovery."""
    assert not _is_scout_repair_skipped(_f("eu_data_act.open", "true (uuid deadbeef)"))


def test_an_unrelated_new_field_still_raises_the_repair() -> None:
    assert not _is_scout_repair_skipped(_f("eu_data_act.some_new_field", "42"))
