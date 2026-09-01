# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#1301 (@anju1337) — the SEAT/CUPRA ``ola_headers_outdated`` Repair must
auto-resolve once the entry reads via the EU Data Act portal.

OLA is server-side revoked for CUPRA/SEAT. In portal mode the client never calls
OLA again, so the 403 counter / repair flag (which reset only on a *successful*
OLA response) froze "on" and the coordinator re-raised the repair every poll
(270+ firings). The portal-mode guard in ``_reconcile_ola_repair`` now clears the
repair, resets the frozen counters, and never re-raises while a portal channel is
serving the data — while keeping the honest repair for a non-portal entry.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from custom_components.vag_connect.coordinator import VagConnectCoordinator

_CLEAR = "custom_components.vag_connect.repairs.clear_ola_headers_issue"
_RAISE = "custom_components.vag_connect.repairs.raise_issue_ola_headers_outdated"


def _coord(*, portal, ola_flag=False, count=0, has_ola_attrs=True):
    s = SimpleNamespace()
    s.hass = MagicMock()
    s.entry = SimpleNamespace(entry_id="e1", data={"brand": "cupra"})
    client = SimpleNamespace(
        _eu_portal=object() if portal else None,
        _supplementary_eu_portal=None,
    )
    if has_ola_attrs:
        client.ola_headers_repair_needed = ola_flag
        client._ola_consecutive_403 = count
    s._cariad_client = client
    return s


def _run(s):
    with patch(_CLEAR) as clear, patch(_RAISE) as raise_:
        VagConnectCoordinator._reconcile_ola_repair(s)
    return clear, raise_


# ── the #1301 fix: portal mode auto-resolves and never re-raises ─────────────

def test_portal_mode_clears_and_resets_a_tripped_repair():
    s = _coord(portal=True, ola_flag=True, count=270)
    clear, raise_ = _run(s)
    clear.assert_called_once_with(s.hass, "e1")
    raise_.assert_not_called()
    # frozen counters reset so a leftover best-effort OLA read can't re-trip it
    assert s._cariad_client.ola_headers_repair_needed is False
    assert s._cariad_client._ola_consecutive_403 == 0


def test_portal_mode_with_clean_counters_is_a_noop():
    s = _coord(portal=True, ola_flag=False, count=0)
    clear, raise_ = _run(s)
    clear.assert_not_called()
    raise_.assert_not_called()


# ── non-portal entries keep the honest OLA repair (no regression) ────────────

def test_non_portal_tripped_still_raises():
    s = _coord(portal=False, ola_flag=True, count=5)
    clear, raise_ = _run(s)
    raise_.assert_called_once_with(s.hass, "e1", "cupra", 5)
    clear.assert_not_called()


def test_non_portal_healthy_clears():
    s = _coord(portal=False, ola_flag=False, count=0)
    clear, raise_ = _run(s)
    clear.assert_called_once_with(s.hass, "e1")
    raise_.assert_not_called()


def test_non_ola_brand_is_safe():
    # a VW/Audi client without the OLA attrs: defaults False/0, no raise.
    s = _coord(portal=False, has_ola_attrs=False)
    clear, raise_ = _run(s)
    raise_.assert_not_called()
