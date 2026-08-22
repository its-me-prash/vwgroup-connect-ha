# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#1227 (@ccsnet) — surface the EU-Data-Act portal's ``last_no_data_reason`` in
the diagnostics download.

A fresh MIB4 Golf came back with every field null, ``no_data: true`` and
``source_channel: null``. The portal records WHY (``no_request`` / ``empty`` /
``no_content``) and it drives the ``data_act_no_data`` Repair, but the reason was
only in the HA INFO log — never in the download — so telling the three apart cost
a second round-trip with the reporter. These tests pin that the reason is now
resolved the same way the coordinator resolves it (primary portal, then
supplementary) and wired into the export.

Everything here is synthetic.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from custom_components.vag_connect.diagnostics import _portal_no_data_reason


class TestPortalNoDataReason:
    def test_primary_portal_reason_is_surfaced(self) -> None:
        client = MagicMock()
        client._eu_portal.last_no_data_reason = "no_request"
        assert _portal_no_data_reason(client) == "no_request"

    def test_falls_back_to_supplementary_portal(self) -> None:
        client = MagicMock()
        client._eu_portal = None
        client._supplementary_eu_portal.last_no_data_reason = "no_content"
        assert _portal_no_data_reason(client) == "no_content"

    def test_empty_reason_is_none_not_blank(self) -> None:
        # A good poll clears the reason to "" — that must read as None (no
        # spurious value), not an empty string in the export.
        client = MagicMock()
        client._eu_portal.last_no_data_reason = ""
        client._supplementary_eu_portal = None
        assert _portal_no_data_reason(client) is None

    def test_no_client_is_none(self) -> None:
        assert _portal_no_data_reason(None) is None

    def test_client_without_portal_is_none(self) -> None:
        client = MagicMock()
        client._eu_portal = None
        client._supplementary_eu_portal = None
        assert _portal_no_data_reason(client) is None


def test_diagnostics_source_wires_portal_no_data_reason() -> None:
    # Mirror of test_diagnostics_source_wires_raw_responses: the export dict must
    # carry the field (red before the fix wired it in).
    src = (
        Path(__file__).resolve().parents[1]
        / "custom_components/vag_connect/diagnostics.py"
    ).read_text(encoding="utf-8")
    assert '"portal_no_data_reason": _portal_no_data_reason(client)' in src
