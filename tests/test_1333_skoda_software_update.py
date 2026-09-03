# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#1333 (Scout, Elroq) — Škoda readiness ``softwareUpdateStatus`` mapping.

The readiness endpoint gained a software-update lifecycle field (e.g.
``UPDATE_IN_PROGRESS``). It is surfaced verbatim through a plain STRING sensor (not
an ENUM) so a value we haven't catalogued yet is shown as-is rather than dropped —
the Scout "never suppress" policy. These pin the pure extraction helper + its
call-site (mirrors the is_driving pattern) so it can't regress back inline.
"""
from __future__ import annotations

from custom_components.vag_connect.cariad.api.skoda import (
    _software_update_from_readiness,
)


def test_extracts_raw_value_verbatim() -> None:
    assert (
        _software_update_from_readiness({"softwareUpdateStatus": "UPDATE_IN_PROGRESS"})
        == "UPDATE_IN_PROGRESS"
    )


def test_strips_whitespace() -> None:
    assert (
        _software_update_from_readiness({"softwareUpdateStatus": "  UPDATE_SUCCESSFUL  "})
        == "UPDATE_SUCCESSFUL"
    )


def test_none_when_absent_or_blank() -> None:
    assert _software_update_from_readiness({"inMotion": True}) is None
    assert _software_update_from_readiness({"softwareUpdateStatus": ""}) is None
    assert _software_update_from_readiness({"softwareUpdateStatus": "   "}) is None


def test_none_for_non_dict() -> None:
    assert _software_update_from_readiness(None) is None
    assert _software_update_from_readiness("garbage") is None


def test_get_status_routes_through_the_helper() -> None:
    import inspect

    from custom_components.vag_connect.cariad.api import skoda as skoda_mod

    src = inspect.getsource(skoda_mod.SkodaClient.get_status)
    # the assignment must route through the helper (may wrap across lines for
    # line-length), so the readiness extraction can't silently regress back inline
    assert "_software_update_from_readiness" in src
    assert "d.readiness_software_update_status = _software_update_from_readiness" in src
