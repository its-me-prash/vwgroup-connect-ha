# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#1867 — no SEAT/CUPRA user ID lookup after the sign-in fell back to a cookie session.

@georghaberkorn68-ctrl's debug log on 5.4.1: the CUPRA entry signed in through
the EU Data Act portal fallback, and right after it the integration looked the
user ID up on the app API with the portal's placeholder instead of a token,
which answered 404 and logged "Could not fetch SEAT/CUPRA user ID" on every
reload. After a cookie-session sign-in the lookup is skipped; after a real
token sign-in without a user ID from the redirect it still runs, and a user ID
from the redirect is still taken as before.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest

from custom_components.vag_connect.cariad.api import base as base_mod
from custom_components.vag_connect.cariad.api.seat_cupra import SeatCupraClient


def _run(brand: str, strategy: str, redirect_user_id: str | None,
         monkeypatch: pytest.MonkeyPatch) -> tuple[SeatCupraClient, list[str]]:
    c = SeatCupraClient(MagicMock(), brand, "u@t.invalid", "pw")
    calls: list[str] = []

    async def _base_authenticate(self: Any, mfa_code: str | None = None) -> None:
        self._tokens = SimpleNamespace(access_token="tok", refresh_token=None, id_token=None,
                                       expires_at=0.0, strategy=strategy)

    async def _fetch_user_id(self: Any) -> None:
        calls.append(strategy)

    monkeypatch.setattr(base_mod.CariadBaseClient, "authenticate", _base_authenticate)
    monkeypatch.setattr(SeatCupraClient, "_fetch_user_id", _fetch_user_id)
    c._auth = SimpleNamespace(user_id=redirect_user_id)  # type: ignore[assignment]
    asyncio.new_event_loop().run_until_complete(c.authenticate())
    return c, calls


@pytest.mark.parametrize("brand", ["seat", "cupra"])
@pytest.mark.parametrize("strategy", ["data_act_portal", "website_authproxy"])
def test_no_lookup_after_a_cookie_session_sign_in(brand: str, strategy: str,
                                                  monkeypatch: pytest.MonkeyPatch) -> None:
    c, calls = _run(brand, strategy, None, monkeypatch)
    assert calls == [], "the user ID was looked up with the cookie-session placeholder"
    assert c._user_id is None


@pytest.mark.parametrize("brand", ["seat", "cupra"])
@pytest.mark.parametrize("strategy", ["idk", "test"])
def test_lookup_still_runs_after_a_token_sign_in(brand: str, strategy: str,
                                                 monkeypatch: pytest.MonkeyPatch) -> None:
    _c, calls = _run(brand, strategy, None, monkeypatch)
    assert calls == [strategy], "a real token sign-in without a redirect user ID must still look it up"


@pytest.mark.parametrize("strategy", ["idk", "data_act_portal"])
def test_redirect_user_id_is_taken_as_before(strategy: str, monkeypatch: pytest.MonkeyPatch) -> None:
    c, calls = _run("cupra", strategy, "user-from-redirect", monkeypatch)
    assert calls == []
    assert c._user_id == "user-from-redirect"


def test_the_pair_is_the_shared_one() -> None:
    # Same discriminator as the coordinator's forced fresh login and the BFF
    # capabilities guard; a new cookie-session strategy is picked up here too.
    assert set(base_mod._COOKIE_SESSION_STRATEGIES) == {"data_act_portal", "website_authproxy"}
