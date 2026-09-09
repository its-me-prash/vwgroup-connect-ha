# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#584 — cohort-only, read-only fetched-role leapfrog probe.

When the legacy ``operationlist/v3`` answers the definitive
``gw.error.authentication`` verdict for a car, the shipping We Connect app
(APK-verified) no longer uses operationlist at all — it reads the per-vehicle
permission gate via ``rolesrights/permissions/v1/{Brand}/{country}/vehicles/
{vin}/fetched-role`` on the modern EU-DP host ``mal-3a.prd.eu.dp``. This probe
tests, for the test cohort only, whether that modern gate answers where v3 401s,
and records ONLY the HTTP status into ``probe_outcomes`` (no VIN, no body, no
token). It is read-only, one-shot per VIN, fail-soft, and off for normal users.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from custom_components.vag_connect.cariad._mbb import build_mbb_fetched_role_url
from custom_components.vag_connect.cariad.api.vw_eu import VWEUClient
from custom_components.vag_connect.cariad.exceptions import APIError

VIN = "WVWZZZAUZFW805377"
_URL = "https://mal-1a.prd.ece.vwg-connect.com/api/rolesrights/operationlist/v3"
_AUTH_401 = APIError(
    401, _URL,
    '{"error":{"errorCode":"gw.error.authentication","description":"Unauthorized"}}',
)


# ── URL builder ─────────────────────────────────────────────────────────────
def test_fetched_role_url_matches_apk_literal() -> None:
    url = build_mbb_fetched_role_url(
        "https://mal-3a.prd.eu.dp.vwg-connect.com", "volkswagen", "DE", VIN
    )
    assert url == (
        "https://mal-3a.prd.eu.dp.vwg-connect.com/api/rolesrights/permissions/v1"
        f"/VW/DE/vehicles/{VIN}/fetched-role"
    )


def test_fetched_role_url_maps_audi_segment() -> None:
    url = build_mbb_fetched_role_url(
        "https://mal-3a.prd.eu.dp.vwg-connect.com", "audi", "CH", VIN
    )
    assert "/Audi/CH/vehicles/" in url and url.endswith("/fetched-role")


# ── gating: only the test cohort + only the gw.error verdict fire the probe ──
class _FakeResp:
    def __init__(self, status: int, body: str) -> None:
        self.status = status
        self._body = body

    async def __aenter__(self) -> "_FakeResp":
        return self

    async def __aexit__(self, *a: object) -> bool:
        return False

    async def text(self) -> str:
        return self._body


class _FakeSession:
    def __init__(self, responses: list[tuple[int, str]]) -> None:
        self._responses = list(responses)
        self.calls: list[str] = []

    def get(self, url: str, headers: dict | None = None) -> _FakeResp:
        self.calls.append(url)
        status, body = self._responses.pop(0)
        return _FakeResp(status, body)


def _oplist_client(cohort: bool) -> VWEUClient:
    c = VWEUClient.__new__(VWEUClient)
    c._mbb_get = AsyncMock(side_effect=[_AUTH_401])
    c._refresh_tokens = AsyncMock(return_value=None)
    c._test_cohort = cohort
    c._probe_fetched_role_cohort = AsyncMock(return_value=None)
    return c


def test_cohort_off_never_probes() -> None:
    c = _oplist_client(cohort=False)
    asyncio.run(c._get_mbb_operationlist(VIN, for_command=True))
    assert VIN in c.mbb_no_legacy_vins  # verdict still recorded
    c._probe_fetched_role_cohort.assert_not_called()  # but no probe for non-cohort


def test_cohort_on_fires_probe_after_gw_verdict() -> None:
    c = _oplist_client(cohort=True)
    asyncio.run(c._get_mbb_operationlist(VIN, for_command=True))
    assert VIN in c.mbb_no_legacy_vins
    c._probe_fetched_role_cohort.assert_awaited_once_with(VIN)


# ── the probe itself: records status only, read-only, fail-soft, one-shot ────
def _probe_client(session: _FakeSession) -> VWEUClient:
    c = VWEUClient.__new__(VWEUClient)
    c._session = session
    c.probe_outcomes = {}
    c._brand = SimpleNamespace(name="volkswagen")
    c._mbb_headers = lambda extra=None: {"Authorization": "Bearer redacted"}
    c._mbb_country_from_id_token = lambda: "DE"
    return c


def test_probe_records_leapfrog_win_200_on_eudp() -> None:
    """200 with a role payload on the modern host where v3 401s = the signal."""
    sess = _FakeSession([(200, '{"role":"PRIMARY_USER"}'), (404, "")])
    c = _probe_client(sess)
    asyncio.run(c._probe_fetched_role_cohort(VIN))
    assert c.probe_outcomes["fetched_role:eudp:VW/DE"] == "200 role"
    assert c.probe_outcomes["fetched_role:ece:VW/DE"] == "404"
    # read-only: both requests were GETs, VIN never leaks into the outcome keys
    assert all("vehicles" in u for u in sess.calls)
    assert all(VIN not in k for k in c.probe_outcomes)


def test_probe_records_404_not_found() -> None:
    sess = _FakeSession([(404, ""), (404, "")])
    c = _probe_client(sess)
    asyncio.run(c._probe_fetched_role_cohort(VIN))
    assert c.probe_outcomes["fetched_role:eudp:VW/DE"] == "404"


def test_probe_is_failsoft_on_network_error() -> None:
    class _BoomSession:
        calls: list[str] = []

        def get(self, url: str, headers: dict | None = None):
            raise ConnectionError("boom")

    c = _probe_client(_BoomSession())  # type: ignore[arg-type]
    asyncio.run(c._probe_fetched_role_cohort(VIN))  # must not raise
    assert c.probe_outcomes["fetched_role:eudp:VW/DE"].startswith("error:")


def test_probe_is_one_shot_per_vin() -> None:
    sess = _FakeSession([(200, '{"role":"x"}'), (404, ""),
                         (200, '{"role":"x"}'), (404, "")])
    c = _probe_client(sess)
    asyncio.run(c._probe_fetched_role_cohort(VIN))
    asyncio.run(c._probe_fetched_role_cohort(VIN))  # second call is a no-op
    assert len(sess.calls) == 2  # only the first pass issued requests
