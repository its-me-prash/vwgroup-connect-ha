# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#1752 — a solved captcha has to go back into the SAME Auth0 transaction.

Auth0 binds a login transaction to a session cookie as well as to the ``state``
parameter. Our captcha resume re-entered ``_validate_credentials``, which built
a brand-new ``ClientSession`` with a brand-new empty jar, so every cookie the
tenant had set during the attempt that produced the captcha was gone by the
time the solved captcha was replayed: the right answer, delivered into a
session the tenant had never seen.

Grounded against the clients that work. Each of them keeps one session and one
jar alive across the captcha pause — evcc holds the jar on its login-session
struct for exactly this reason, and CJNE, openWB and the ioBroker adapter all
carry a single client for the whole flow. We were the only implementation
rebuilding it empty.

What travels is the JAR, not the session: it is plain memory with no socket
attached, so nothing stays open while the user reads the image. The first test
below pins that property on aiohttp itself, because the whole fix rests on it.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import pytest
from yarl import URL

from custom_components.vag_connect import config_flow as cf
from custom_components.vag_connect.cariad.exceptions import (
    PorscheCaptchaRequiredError,
)
from custom_components.vag_connect.const import CONF_BRAND, DOMAIN

_FACTORY = "custom_components.vag_connect.cariad.CariadClientFactory"
_VALIDATE = "custom_components.vag_connect.config_flow._validate_credentials"
_IDP = URL("https://identity.porsche.com/")
_IMG = "data:image/svg+xml;base64,PHN2Zz48L3N2Zz4="


def _hass() -> MagicMock:
    hass = MagicMock()
    hass.config.language = "de"
    hass.config.country = "DE"
    return hass


class _StubClient:
    """Stands in for PorscheClient: sets a tenant cookie, then raises."""

    def __init__(self, session: aiohttp.ClientSession) -> None:
        self.session = session
        self.seen_cookies: list[str] = []

    async def authenticate(self, **_: object) -> None:
        # whatever Auth0 had already put in the jar when we got here
        self.seen_cookies = [c.key for c in self.session.cookie_jar]
        self.session.cookie_jar.update_cookies(
            {"auth0": "transaction-abc"}, response_url=_IDP,
        )
        raise PorscheCaptchaRequiredError(_IMG, "state-1", "verifier-1")


def _factory(record: dict) -> MagicMock:
    def create(brand, session, username, password, country="us"):  # noqa: ANN001
        client = _StubClient(session)
        record["client"] = client
        record["jar"] = session.cookie_jar
        return client

    factory = MagicMock()
    factory.create = MagicMock(side_effect=create)
    return factory


# ── the property the whole fix rests on ─────────────────────────────────────


@pytest.mark.asyncio
async def test_a_cookie_jar_outlives_the_session_it_was_handed_to() -> None:
    """If aiohttp ever empties a jar on close, this fix is silently dead."""
    jar = aiohttp.CookieJar(unsafe=True)
    async with aiohttp.ClientSession(cookie_jar=jar) as session:
        session.cookie_jar.update_cookies({"auth0": "abc"}, response_url=_IDP)
    assert [c.key for c in jar] == ["auth0"]

    # ...and a fresh session handed the same jar starts with it populated
    async with aiohttp.ClientSession(cookie_jar=jar) as second:
        assert [c.key for c in second.cookie_jar] == ["auth0"]


# ── the jar leaves with the error ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_the_captcha_error_carries_the_jar_of_its_own_attempt() -> None:
    record: dict = {}
    with patch(_FACTORY, _factory(record)):
        with pytest.raises(PorscheCaptchaRequiredError) as caught:
            await cf._validate_credentials(_hass(), "porsche", "u", "p")

    assert caught.value.cookie_jar is record["jar"]
    assert "auth0" in [c.key for c in caught.value.cookie_jar]


@pytest.mark.asyncio
async def test_a_resume_replays_into_the_cookies_it_was_given() -> None:
    """The point of the whole change: the second attempt starts where the first
    one left off, instead of in an empty session."""
    first: dict = {}
    with patch(_FACTORY, _factory(first)):
        with pytest.raises(PorscheCaptchaRequiredError) as caught:
            await cf._validate_credentials(_hass(), "porsche", "u", "p")

    second: dict = {}
    with patch(_FACTORY, _factory(second)):
        with pytest.raises(PorscheCaptchaRequiredError):
            await cf._validate_credentials(
                _hass(), "porsche", "u", "p",
                cookie_jar=caught.value.cookie_jar,
            )

    assert second["client"].seen_cookies == ["auth0"]
    assert first["client"].seen_cookies == [], "the first attempt starts clean"


@pytest.mark.asyncio
async def test_an_ordinary_login_still_gets_a_jar_of_its_own() -> None:
    """No jar passed, no cookies inherited — two unrelated logins must not see
    each other's session."""
    record: dict = {}
    with patch(_FACTORY, _factory(record)):
        with pytest.raises(PorscheCaptchaRequiredError):
            await cf._validate_credentials(_hass(), "porsche", "u", "p")
    assert record["client"].seen_cookies == []


# ── the config flow carries it across the pause ─────────────────────────────


def _flow() -> cf.VagConnectConfigFlow:
    f = cf.VagConnectConfigFlow()
    f.hass = _hass()
    f.context = {}
    f.handler = DOMAIN
    f.flow_id = "t"
    f._pending_username = "u"
    f._pending_password = "p"
    f._pending_entry_data = {}
    f._porsche_captcha_image = _IMG
    f._porsche_captcha_state = "state-1"
    f._porsche_captcha_verifier = "verifier-1"
    f._porsche_captcha_return = "email_password"
    f._porsche_captcha_attempts = 0
    return f


@pytest.mark.asyncio
async def test_the_initial_step_stashes_the_jar_it_was_handed() -> None:
    jar = aiohttp.CookieJar(unsafe=True)
    jar.update_cookies({"auth0": "abc"}, response_url=_IDP)
    err = PorscheCaptchaRequiredError(_IMG, "s", "v")
    err.cookie_jar = jar

    f = _flow()
    f._porsche_captcha_jar = None
    # the unique-id guard runs before the login and has nothing to check here
    f.async_set_unique_id = AsyncMock(return_value=None)  # type: ignore[method-assign]
    f._abort_if_unique_id_configured = MagicMock()  # type: ignore[method-assign]
    with patch(_VALIDATE, new=AsyncMock(side_effect=err)):
        await f.async_step_email_password({
            CONF_BRAND: "porsche",
            cf.CONF_USERNAME: "u",
            cf.CONF_PASSWORD: "p",
        })

    assert f._porsche_captcha_jar is jar


@pytest.mark.asyncio
async def test_the_resume_hands_that_jar_back() -> None:
    jar = aiohttp.CookieJar(unsafe=True)
    f = _flow()
    f._porsche_captcha_jar = jar
    seen: dict = {}

    async def _capture(*args: object, **kwargs: object) -> dict:
        seen.update(kwargs)
        return {"access_token": "t"}

    with patch(_VALIDATE, new=AsyncMock(side_effect=_capture)):
        await f.async_step_porsche_captcha({cf.CONF_CAPTCHA_CODE: "AAAA"})

    assert seen.get("cookie_jar") is jar
    # the rest of the transaction still rides along unchanged
    assert seen.get("captcha_state") == "state-1"
    assert seen.get("captcha_verifier") == "verifier-1"


@pytest.mark.asyncio
async def test_a_chained_captcha_keeps_carrying_the_jar() -> None:
    """Auth0 answering with a second image must not reset the transaction."""
    jar = aiohttp.CookieJar(unsafe=True)
    err = PorscheCaptchaRequiredError(_IMG, "s2", "v2")
    err.cookie_jar = jar

    f = _flow()
    f._porsche_captcha_jar = None
    with patch(_VALIDATE, new=AsyncMock(side_effect=err)):
        res = await f.async_step_porsche_captcha({cf.CONF_CAPTCHA_CODE: "AAAA"})

    assert res["type"] == "form"
    assert res["errors"]["base"] == "captcha_retry"
    assert f._porsche_captcha_jar is jar


def test_the_error_defaults_to_no_jar_so_older_callers_still_work() -> None:
    err = PorscheCaptchaRequiredError(_IMG, "s", "v")
    assert err.cookie_jar is None
    assert err.resume is None

