# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#966 (Arno-MA-73, v3.2.3 re-test) — persist vw.de cookies after EVERY read.

The v3.2.3 cookie-twin fold stopped the set from doubling, but the SSO session
still died ~93 s after persist. Arno pinned it: the persist ran at arm (after the
first silent refresh) but the setup-time "immediate full read" rotated the SSO
cookie ~3.5 s later on a path the post-loop persist never reached, so the entry
kept the pre-second-refresh snapshot and the next restart replayed a superseded
cookie. Fix: ``_merge_supplementary`` persists the rotated cookies after every
successful supplementary read (idempotent equality guard keeps it cheap).
"""
from __future__ import annotations

import asyncio
from unittest.mock import MagicMock


def _coord(readers_return):
    from custom_components.vag_connect import coordinator as coord_mod

    c = coord_mod.VagConnectCoordinator.__new__(coord_mod.VagConnectCoordinator)
    c._cariad_client = MagicMock()
    c._cariad_client.supplementary_readers = MagicMock(return_value=readers_return)
    c._primary_channel_name = MagicMock(return_value="eu_data_act")
    c._persist_supplementary_cookies = MagicMock()
    return c


def test_persist_runs_after_a_successful_supplementary_read(monkeypatch):
    from custom_components.vag_connect.cariad import _channel_merge as cm

    async def _fake_gather(name, primary, suppliers):
        return primary  # a real read here would rotate the cookie jar

    monkeypatch.setattr(cm, "gather_and_merge", _fake_gather)
    monkeypatch.setattr(cm, "annotate_provenance", lambda name, primary: primary)

    c = _coord(["reader1"])  # a supplementary channel IS armed
    out = asyncio.run(c._merge_supplementary("VIN", {"battery_soc": 50}))
    assert out == {"battery_soc": 50}
    c._persist_supplementary_cookies.assert_called_once()


def test_no_persist_when_no_supplementary_channel(monkeypatch):
    from custom_components.vag_connect.cariad import _channel_merge as cm

    monkeypatch.setattr(cm, "annotate_provenance", lambda name, primary: primary)

    c = _coord([])  # no supplier for this VIN -> nothing rotated
    asyncio.run(c._merge_supplementary("VIN", {"battery_soc": 50}))
    c._persist_supplementary_cookies.assert_not_called()


def test_persist_still_runs_is_guarded_idempotent(monkeypatch):
    # The method is called on every read; the entry-write guard (fresh == stored)
    # makes the redundant calls no-ops. Here we only assert it is INVOKED — the
    # equality no-op is covered by the _persist_supplementary_cookies unit tests.
    from custom_components.vag_connect.cariad import _channel_merge as cm

    async def _fake_gather(name, primary, suppliers):
        return primary

    monkeypatch.setattr(cm, "gather_and_merge", _fake_gather)
    monkeypatch.setattr(cm, "annotate_provenance", lambda name, primary: primary)

    c = _coord(["r1"])
    asyncio.run(c._merge_supplementary("V1", {"a": 1}))
    asyncio.run(c._merge_supplementary("V2", {"a": 2}))
    assert c._persist_supplementary_cookies.call_count == 2
