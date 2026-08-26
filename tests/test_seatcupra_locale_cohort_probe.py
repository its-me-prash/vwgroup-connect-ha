# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""SEAT/CUPRA en_GB locale A/B cohort probe.

The competitor lib pycupra sends a static ``Accept-Language: en_GB`` on every
OLA read; we send none. Source-grounding couldn't decide whether adding it
localises strings (fix) or forces English on a non-English account (regression),
so this opt-in probe captures the ``mycar`` localized strings from a default read
vs an ``en_GB`` read, once per VIN, for a real account to settle it.
"""
from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.vag_connect.cariad.api.seat_cupra import SeatCupraClient

_VIN = "VSSZZZ5FZLR000123"

# German (default, no Accept-Language) vs English (en_GB) mycar samples
_MYCAR_DE = {"vehicle": {"model": {"name": "León e-Hybrid"}},
             "services": [{"title": "Standheizung"}],
             "vin": _VIN, "code": "ABCD1234EFGH5678"}
_MYCAR_EN = {"vehicle": {"model": {"name": "Leon e-Hybrid"}},
             "services": [{"title": "Auxiliary heating"}],
             "vin": _VIN, "code": "ABCD1234EFGH5678"}


def _client() -> SeatCupraClient:
    c = SeatCupraClient(MagicMock(), "cupra", "e@x.com", "pw")
    c._user_id = "user-123"
    return c


# ── the collector ────────────────────────────────────────────────────────────

def test_collector_keeps_localized_text_masks_vin_skips_codes():
    got = SeatCupraClient._collect_localized_strings(_MYCAR_DE)
    vals = list(got.values())
    assert "León e-Hybrid" in vals
    assert "Standheizung" in vals
    # the raw VIN is masked, never emitted verbatim
    assert all(_VIN not in v for v in vals)
    # a pure code under a non-localized key ("code") is skipped
    assert "ABCD1234EFGH5678" not in vals


def test_collector_masks_email_and_vin_in_values():
    got = SeatCupraClient._collect_localized_strings(
        {"label": "owner me@example.com VSSZZZ5FZLR000999 here"}
    )
    v = got["label"]
    assert "me@example.com" not in v and "VSSZZZ5FZLR000999" not in v


# ── the A/B probe ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_probe_captures_default_vs_en_gb_and_sends_en_gb_header():
    c = _client()
    c._test_cohort = True
    c._get = AsyncMock(return_value=_MYCAR_DE)
    seen_headers: list[Any] = []

    async def _req(method, url, **kw):
        seen_headers.append(kw.get("headers"))
        return _MYCAR_EN

    c._request = _req  # type: ignore[assignment]

    await c._probe_ola_locale(_VIN)

    cap = c.ola_locale_captures[_VIN]
    assert "León e-Hybrid" in cap["default"].values()
    assert "Leon e-Hybrid" in cap["en_GB"].values()
    assert "Standheizung" in cap["default"].values()
    assert "Auxiliary heating" in cap["en_GB"].values()
    # the variant read carried pycupra's exact header (underscore form)
    assert {"Accept-Language": "en_GB"} in seen_headers


@pytest.mark.asyncio
async def test_probe_is_self_limiting_once_per_vin():
    c = _client()
    c._test_cohort = True
    c._get = AsyncMock(return_value=_MYCAR_DE)
    c._request = AsyncMock(return_value=_MYCAR_EN)

    await c._probe_ola_locale(_VIN)
    await c._probe_ola_locale(_VIN)  # second call must be a no-op

    assert c._get.await_count == 1  # not re-fetched


@pytest.mark.asyncio
async def test_probe_off_when_not_in_cohort():
    c = _client()  # _test_cohort defaults False
    c._get = AsyncMock(return_value=_MYCAR_DE)
    c._request = AsyncMock(return_value=_MYCAR_EN)

    await c._probe_ola_locale(_VIN)

    assert _VIN not in c.ola_locale_captures
    c._get.assert_not_awaited()


@pytest.mark.asyncio
async def test_probe_failsoft_records_error_not_raise():
    c = _client()
    c._test_cohort = True
    c._get = AsyncMock(side_effect=RuntimeError("boom"))
    c._request = AsyncMock(return_value=_MYCAR_EN)

    await c._probe_ola_locale(_VIN)  # must not raise

    assert c.ola_locale_captures[_VIN] == {"error": "RuntimeError"}
