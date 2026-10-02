# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Porsche ``/authorize`` locale hints, read out of the official app.

androguard on ``de.porsche.one`` 21.26.39 (the version the atlas watcher flagged
in #1634) shows the app's authorize builder passing ``ui_locales``,
``ext-country`` and ``ext-language`` through Auth0's ``withParameters``. We sent
none of them — the same omission that once cost us the Audi model name, where a
missing ``Accept-Language`` / ``X-User-Country`` made the GraphQL ``media`` field
come back null.

Two details from the decompiled builder that a guess would have got wrong, and
that these tests pin:

* ``ext-country`` is LOWERCASE — the app computes ``getCountry().toLowerCase()``.
  The Audi header path wants it UPPERCASE, so the two must not be "harmonised".
* ``prompt=login`` is NOT copied. The app forces a fresh login; our flow depends
  on an existing Auth0 session short-circuiting straight to a code, and copying
  that parameter would throw the shortcut away on every call.
"""
from __future__ import annotations

from custom_components.vag_connect.cariad.auth.porsche import _locale_params


def test_full_locale():
    p = _locale_params("DE", "de")
    assert p == {"ui_locales": "de-DE", "ext-language": "de", "ext-country": "de"}


def test_country_is_lowercased_language_tag_is_not():
    # the app: getCountry().toLowerCase() for ext-country, a BCP47 tag elsewhere
    p = _locale_params("GB", "en")
    assert p["ext-country"] == "gb"
    assert p["ui_locales"] == "en-GB"


def test_regional_language_is_reduced_to_its_subtag():
    # HA hands out things like "pt-BR" / "zh_Hans"; ext-language wants the
    # language only, and ui_locales pairs it with the configured country.
    p = _locale_params("BR", "pt-BR")
    assert p["ext-language"] == "pt"
    assert p["ui_locales"] == "pt-BR"
    p = _locale_params("CH", "de_CH")
    assert p["ext-language"] == "de"
    assert p["ui_locales"] == "de-CH"


def test_language_without_country_still_sends_a_locale():
    p = _locale_params("", "nl")
    assert p == {"ui_locales": "nl", "ext-language": "nl"}
    assert "ext-country" not in p, "a country we do not know must not be invented"


def test_country_without_language():
    p = _locale_params("NL", "")
    assert p == {"ext-country": "nl"}


def test_nothing_known_sends_nothing():
    # status quo preserved: no locale is better than a wrong one
    assert _locale_params("", "") == {}
    assert _locale_params(None, None) == {}  # type: ignore[arg-type]


def test_whitespace_is_tolerated():
    assert _locale_params(" de ", " DE ")["ext-country"] == "de"


def test_prompt_and_device_are_not_copied_from_the_app():
    # prompt=login would defeat the existing-session shortcut; device=touch is
    # an app-shaped hint we cannot justify.
    for country, language in (("DE", "de"), ("", ""), ("GB", "en")):
        p = _locale_params(country, language)
        assert "prompt" not in p
        assert "device" not in p


def test_client_hands_its_locale_to_the_login():
    """The coordinator sets ``_ha_*`` AFTER the client is built, so the client
    must copy them per call instead of the auth object snapshotting them."""
    import asyncio
    from unittest.mock import MagicMock

    from custom_components.vag_connect.cariad.api.porsche import PorscheClient

    c = PorscheClient.__new__(PorscheClient)
    c._email, c._password = "a@b.c", "pw"
    c._tokens = None
    c.on_tokens_changed = None  # skip the persistence hook
    c._auth = MagicMock()

    async def _auth(*a, **kw):
        return "tokens"

    c._auth.authenticate = _auth
    # class defaults before the coordinator pushes anything
    assert c._ha_country == "" and c._ha_language == ""
    # ...and what the coordinator does later
    c._ha_country, c._ha_language = "AT", "de"
    asyncio.run(PorscheClient.authenticate(c))
    assert c._auth._ha_country == "AT"
    assert c._auth._ha_language == "de"


def test_authorize_sends_the_params(monkeypatch):
    """The params reach the real /authorize query, not just the helper."""
    import asyncio
    from types import SimpleNamespace

    from custom_components.vag_connect.cariad.auth import porsche as mod

    seen: dict = {}

    class _Resp:
        status = 302
        headers = {"Location": "https://identity.porsche.com/u/login/identifier"}

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

    class _Session:
        def get(self, url, **kw):
            seen["params"] = kw.get("params")
            return _Resp()

    auth = mod.PorscheAuth.__new__(mod.PorscheAuth)
    auth._session = _Session()
    auth._last_wall_screen = ""
    auth._last_wall_marker = ""
    auth._ha_country = "DE"
    auth._ha_language = "de"

    # stop right after the authorize GET — the identifier step is not under test
    monkeypatch.setattr(mod, "_CLIENT_ID", "test-client", raising=False)

    async def _boom(*a, **kw):
        raise RuntimeError("stop-after-authorize")

    monkeypatch.setattr(mod.PorscheAuth, "_post_identifier", _boom, raising=False)

    try:
        asyncio.run(auth.authenticate("a@b.c", "pw"))
    except Exception:  # the flow is cut short on purpose
        pass

    params = seen.get("params") or {}
    assert params.get("ui_locales") == "de-DE"
    assert params.get("ext-country") == "de"
    assert params.get("ext-language") == "de"
    assert "prompt" not in params
    # the PKCE/scope essentials must still be there
    assert params.get("code_challenge_method") == "S256"
    assert params.get("response_type") == "code"


def test_the_interactive_config_flow_login_also_gets_the_locale():
    """The login a user actually performs is the config flow's, not the
    coordinator's: the coordinator bridges the token from here and refreshes
    instead of logging in again, so its own locale-carrying login only runs once
    the refresh token has died. An adversarial review of this change found the
    config-flow client was never given the locale, which made the whole point of
    the change (comparable wall captures) not apply to the path that produces
    them."""
    import inspect

    from custom_components.vag_connect import config_flow as cf

    src = inspect.getsource(cf._validate_credentials)
    assert "_ha_language" in src and "_ha_country" in src, (
        "the interactive login must receive the HA locale"
    )
    # ...and it must be fail-soft: a missing hass.config value cannot break a login
    i = src.index("_ha_language")
    assert "try:" in src[max(0, i - 400):i]
    assert "except Exception" in src[i:i + 400]
    # ...and it must happen BEFORE the login is driven (the first real call, not
    # the mentions in docstrings/comments above it)
    assert i < src.index("await client.authenticate(")
