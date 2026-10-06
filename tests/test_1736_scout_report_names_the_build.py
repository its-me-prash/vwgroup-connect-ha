# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""A Scout or error report has to say which build produced it.

The report builder has rendered an ``Integration:`` line since v1.9.0 — when it
is handed a version. The coordinator never handed it one, so every report that
reached us was build-less, and three issues in one week (#1730, #1736, #1738)
opened with "which version are you on". In #1730 the answer was that the field
had been mapped thirty-seven minutes before the report was filed.

The renderer was never the problem, so what is tested here is the wiring — and
one thing that is not wiring at all. The first attempt resolved the version in
``async_setup`` by awaiting ``async_get_integration``, and that hung the suite:
handed a mocked hass, the real loader goes looking for the integration on disk
and does not come back. ``test_an_unloaded_integration_costs_nothing`` is that
case. Against the awaiting version it does not fail, it hangs — which is worse,
and worth knowing about.
"""
from __future__ import annotations

import types
from typing import Any
from unittest.mock import MagicMock

from custom_components.vag_connect.cariad._error_reporter import ErrorRingBuffer
from custom_components.vag_connect.cariad._unexpected_keys import UnexpectedField
from custom_components.vag_connect.coordinator import VagConnectCoordinator

_VIN = "WVWZZZ1KZAW000596"


def _coordinator() -> VagConnectCoordinator:
    """A coordinator carrying only what _refresh_reporter_issues reads."""
    coord = VagConnectCoordinator.__new__(VagConnectCoordinator)
    coord.vehicles = {_VIN: {"model": "ID.4"}}
    coord.error_buffer = ErrorRingBuffer()
    coord.unexpected_findings = {
        _VIN: {
            "eu_data_act.something_new": UnexpectedField(
                path="eu_data_act.something_new",
                sample_masked='"42"',
                endpoint="eu_data_act",
                first_seen_at="2026-10-06T05:39:40+00:00",
            ),
        },
    }
    coord.entry = types.SimpleNamespace(
        data={"brand": "volkswagen"},
        options={},
        entry_id="e1",
    )
    coord.hass = MagicMock(name="hass")
    return coord


def _capture(coord: VagConnectCoordinator) -> dict[str, dict[str, Any]]:
    """Run the refresh with both pipeline helpers replaced by recorders."""
    import custom_components.vag_connect.coordinator as mod

    seen: dict[str, dict[str, Any]] = {}

    def _scout(_hass: Any, **kwargs: Any) -> None:
        seen["scout"] = kwargs

    def _errors(_hass: Any, **kwargs: Any) -> None:
        seen["errors"] = kwargs

    original = (mod.ensure_unexpected_keys_issue, mod.ensure_error_reporter_issue)
    mod.ensure_unexpected_keys_issue = _scout  # type: ignore[assignment]
    mod.ensure_error_reporter_issue = _errors  # type: ignore[assignment]
    try:
        coord._refresh_reporter_issues()
    finally:
        (mod.ensure_unexpected_keys_issue,
         mod.ensure_error_reporter_issue) = original
    return seen


def test_both_reports_are_told_the_build():
    coord = _coordinator()
    coord._integration_version = lambda: "4.11.0"  # type: ignore[method-assign]

    seen = _capture(coord)

    assert seen["scout"]["integration_version"] == "4.11.0"
    assert seen["errors"]["integration_version"] == "4.11.0"


def test_an_unloaded_integration_costs_nothing():
    """The real resolver against a hass that knows nothing.

    It must come back, come back empty, and leave both reports intact — a
    missing version line is a cosmetic loss, a missing report is not.
    """
    coord = _coordinator()

    assert coord._integration_version() == ""

    seen = _capture(coord)

    assert seen["scout"]["integration_version"] == ""
    assert seen["errors"]["integration_version"] == ""
    assert seen["scout"]["brand"] == "volkswagen"
    assert seen["scout"]["findings"], "the findings still have to be handed over"


def test_the_resolver_stays_synchronous():
    """Source-level, and deliberately so: the awaiting variant HANGS here.

    A behavioural test cannot distinguish "returned empty" from "never
    returned" without a timeout the suite does not have, so the thing that
    must not come back is named instead.
    """
    import inspect

    from custom_components.vag_connect import coordinator as mod

    src = inspect.getsource(mod.VagConnectCoordinator._integration_version)
    assert "async_get_loaded_integration" in src
    assert "await " not in src
    assert not inspect.iscoroutinefunction(
        mod.VagConnectCoordinator._integration_version)


def test_the_version_reaches_the_rendered_report():
    """End to end through the real builder, not a second copy of its format."""
    from custom_components.vag_connect.cariad._reporter_pipeline import (
        build_unexpected_keys_report,
    )

    coord = _coordinator()
    coord._integration_version = lambda: "4.11.0"  # type: ignore[method-assign]
    seen = _capture(coord)

    body = build_unexpected_keys_report(
        seen["scout"]["findings"],
        brand=seen["scout"]["brand"],
        model=seen["scout"]["model"],
        integration_version=seen["scout"]["integration_version"],
    )

    assert "**Integration:** `vag_connect 4.11.0`" in body


def test_an_empty_version_renders_no_integration_line():
    """Rather than `vag_connect ` with nothing after it."""
    from custom_components.vag_connect.cariad._reporter_pipeline import (
        build_unexpected_keys_report,
    )

    seen = _capture(_coordinator())
    body = build_unexpected_keys_report(
        seen["scout"]["findings"],
        brand=seen["scout"]["brand"],
        integration_version=seen["scout"]["integration_version"],
    )

    assert "Integration:" not in body
    assert "Brand:" in body, "the rest of the header must still be there"
