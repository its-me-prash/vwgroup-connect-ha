# Copyright 2026 Prash Balan (@its-me-prash) - Apache License 2.0
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Per-platform gdc + precondition/optional-read handling for the vw.de authproxy.

Regression cover for the 2026-07-12 fix. The myVolkswagen web app sends
``gdc=myvw-mbb-prod`` for legacy MBB/Car-Net cars and ``gdc=myvw-wcar-prod`` for
WeConnect cars; sending the WeConnect gdc to an MBB car 412s every live-status
read. The old code treated 412 (and the optional reads' 401/403) as a dead
session and re-logged in on every poll → email-OTP thrash + silent no-data. Now:

  * the live-status builders take a per-car ``gdc`` (default = WeConnect);
  * the connector resolves each VIN's platform from the relations parse and
    threads the matching gdc into the reads;
  * 412 and the optional live-status reads degrade to "no data this poll"
    instead of forcing a re-login — session validity stays on the CORE reads.

Verified live against an MBB Golf GTE: relations 200 (session valid) but every
vehicle read 412 with the WeConnect gdc.
"""
from __future__ import annotations

from typing import Any

import pytest

from custom_components.vag_connect.cariad._authproxy import (
    _GDC_MBB,
    _GDC_WCAR,
    build_transactionhistory_url,
    build_usercapabilities_url,
    build_warninglights_url,
    gdc_for_backend,
)
from custom_components.vag_connect.cariad.auth._website_authproxy import (
    WebsiteAuthProxyConnector,
)
from custom_components.vag_connect.cariad.exceptions import AuthenticationError


# ── pure: gdc_for_backend + builder gdc threading ──────────────────────────

@pytest.mark.parametrize(
    "backend, expected",
    [
        ("MBB", _GDC_MBB),
        ("mbb", _GDC_MBB),
        (" Mbb ", _GDC_MBB),
        # #632 parity — the real relations sentinel is suffixed; an exact "== MBB"
        # mis-routed these Car-Net cars to the WeConnect gdc and 412'd every read.
        ("MBB_ODP", _GDC_MBB),
        ("mbb_odp", _GDC_MBB),
        (" MBB_ODP ", _GDC_MBB),
        ("MEB", _GDC_WCAR),
        ("WCAR", _GDC_WCAR),
        ("", _GDC_WCAR),
        (None, _GDC_WCAR),
    ],
)
def test_gdc_for_backend(backend: str | None, expected: str) -> None:
    """MBB (any case) → the MBB gdc; everything else → the WeConnect default."""
    assert gdc_for_backend(backend) == expected


def test_builders_default_to_wcar_gdc() -> None:
    """No gdc arg keeps the historical WeConnect gdc (back-compat)."""
    vin = "WVWZZZTESTVHN0001"
    assert f"gdc={_GDC_WCAR}" in build_warninglights_url(vin)
    assert f"gdc={_GDC_WCAR}" in build_transactionhistory_url(vin)
    assert f"gdc={_GDC_WCAR}" in build_usercapabilities_url(vin)


def test_builders_accept_mbb_gdc() -> None:
    """An MBB gdc is threaded into every live-status builder URL."""
    vin = "WVWZZZTESTVHN0001"
    assert f"gdc={_GDC_MBB}" in build_warninglights_url(vin, _GDC_MBB)
    assert f"gdc={_GDC_MBB}" in build_transactionhistory_url(vin, _GDC_MBB)
    assert f"gdc={_GDC_MBB}" in build_usercapabilities_url(vin, _GDC_MBB)


# ── connector: precondition + optional-read handling ───────────────────────

class _FakeResp:
    def __init__(
        self, url: str, *, status: int = 200, text: str = "", json_data: Any = None
    ) -> None:
        self.url = url
        self.status = status
        self._text = text
        self._json = json_data

    async def __aenter__(self) -> "_FakeResp":
        return self

    async def __aexit__(self, *_a: Any) -> bool:
        return False

    async def text(self, errors: str | None = None) -> str:
        return self._text

    async def json(self, content_type: Any = None) -> Any:
        return self._json


_VIN = "WVWZZZTESTVHN0001"
_CHARGING_JSON = {"data": {"batteryStatus": {"currentSOC_pct": 42}}}
_WL_JSON = {"data": {"warningLights": []}}
# get_relations() reads the relations body as JSON (resp.json()), so the mock
# must return a parsed dict via json_data — not text.
_REL_MBB = {"relations": [{"vehicle": {"vin": _VIN, "modBackend": "MBB"}}]}
_REL_PLAIN = {"relations": [{"vehicle": {"vin": _VIN}}]}


@pytest.mark.asyncio
async def test_412_on_live_read_does_not_relogin() -> None:
    """A 412 (wrong-gdc symptom on MBB cars) degrades to no-data, never raises."""
    class _412Session:
        def get(self, url: str, **kw: Any) -> _FakeResp:
            if "relations" in url:
                return _FakeResp(url, json_data=_REL_MBB)
            if "charging/status" in url:
                return _FakeResp(url, json_data=_CHARGING_JSON)
            if "maintenance/status" in url:
                return _FakeResp(url, status=404)
            return _FakeResp(url, status=412)  # every live-status read 412s

    conn = WebsiteAuthProxyConnector(_412Session(), "u@x.z", "pw")  # type: ignore[arg-type]
    d = await conn.get_vehicle_data(_VIN)  # must NOT raise
    assert d.battery_soc == 42
    assert d.connection_state == "online"


@pytest.mark.asyncio
async def test_403_optional_read_swallowed() -> None:
    """403 on an OPTIONAL live-status read is swallowed (no re-login)."""
    class _WL403Session:
        def get(self, url: str, **kw: Any) -> _FakeResp:
            if "relations" in url:
                return _FakeResp(url, json_data=_REL_PLAIN)
            if "charging/status" in url:
                return _FakeResp(url, json_data=_CHARGING_JSON)
            if "maintenance/status" in url:
                return _FakeResp(url, status=404)
            return _FakeResp(url, status=403)  # warninglights + transactionhistory

    conn = WebsiteAuthProxyConnector(_WL403Session(), "u@x.z", "pw")  # type: ignore[arg-type]
    d = await conn.get_vehicle_data(_VIN)  # must NOT raise
    assert d.battery_soc == 42


@pytest.mark.asyncio
async def test_403_on_core_read_still_relogins() -> None:
    """403 on a CORE read (charging) still propagates so the caller re-logins."""
    class _Charging403Session:
        def get(self, url: str, **kw: Any) -> _FakeResp:
            if "relations" in url:
                return _FakeResp(url, json_data=_REL_PLAIN)
            if "charging/status" in url:
                return _FakeResp(url, status=403)
            return _FakeResp(url, status=404)

    conn = WebsiteAuthProxyConnector(_Charging403Session(), "u@x.z", "pw")  # type: ignore[arg-type]
    with pytest.raises(AuthenticationError):
        await conn.get_vehicle_data(_VIN)


@pytest.mark.asyncio
async def test_mbb_car_uses_mbb_gdc_on_live_reads() -> None:
    """An MBB ``modBackend`` makes the live-status reads use the MBB gdc."""
    class _RecordingSession:
        def __init__(self) -> None:
            self.gets: list[str] = []

        def get(self, url: str, **kw: Any) -> _FakeResp:
            self.gets.append(url)
            if "relations" in url:
                return _FakeResp(url, json_data=_REL_MBB)
            if "warninglights" in url:
                return _FakeResp(url, json_data=_WL_JSON)
            return _FakeResp(url, status=404)

    session = _RecordingSession()
    conn = WebsiteAuthProxyConnector(session, "u@x.z", "pw")  # type: ignore[arg-type]
    await conn.get_warning_lights(_VIN)
    wl = [u for u in session.gets if "warninglights" in u]
    assert wl, "warninglights endpoint was never called"
    assert f"gdc={_GDC_MBB}" in wl[0]


@pytest.mark.asyncio
async def test_weconnect_car_keeps_wcar_gdc() -> None:
    """A non-MBB (or backend-less) car keeps the WeConnect gdc default."""
    class _RecordingSession:
        def __init__(self) -> None:
            self.gets: list[str] = []

        def get(self, url: str, **kw: Any) -> _FakeResp:
            self.gets.append(url)
            if "relations" in url:
                return _FakeResp(url, json_data=_REL_PLAIN)
            if "warninglights" in url:
                return _FakeResp(url, json_data=_WL_JSON)
            return _FakeResp(url, status=404)

    session = _RecordingSession()
    conn = WebsiteAuthProxyConnector(session, "u@x.z", "pw")  # type: ignore[arg-type]
    await conn.get_warning_lights(_VIN)
    wl = [u for u in session.gets if "warninglights" in u]
    assert wl and f"gdc={_GDC_WCAR}" in wl[0]
