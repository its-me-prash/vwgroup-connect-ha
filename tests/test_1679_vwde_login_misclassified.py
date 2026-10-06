# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#1679 (@Fishermanjb) + #1313 (@realynot) — "invalid credentials" for a login
that never failed on the credentials.

Both reporters: the vw.de channel says the email/password are wrong, while the
same pair signs in fine on volkswagen.de and reaches the e-mail-code step. One
hit it at setup on 4.9.0, the other on a re-login on the beta.

Cause: both config-flow drivers mapped EVERY ``AuthenticationError`` from the
connector to ``invalid_credentials``, although the connector itself distinguishes
the genuine 401 from a redirect loop, a dead SSO session, an unrecognised
challenge page and a 4xx carrying its own BFF code. #957 noticed this and added a
log line — the verdict the user sees stayed "your password is wrong".

Only the IDP's own 401 may claim that now; everything else gets
``website_login_failed``, whose text says explicitly that the password is not the
problem and points at the log.
"""
from __future__ import annotations

import pytest

from custom_components.vag_connect.cariad.exceptions import (
    AuthenticationError,
    InvalidCredentialsError,
)
from custom_components.vag_connect.config_flow import _map_error


def test_invalid_credentials_is_an_authentication_error():
    # callers that catch the broad class must keep working
    assert issubclass(InvalidCredentialsError, AuthenticationError)


def test_both_codes_survive_the_mapper():
    assert _map_error("invalid_credentials") == "invalid_credentials"
    assert _map_error("website_login_failed") == "website_login_failed"


def test_an_unknown_code_still_falls_back():
    assert _map_error("something_new") == "cannot_connect"


def test_only_a_401_raises_the_credential_error():
    """The connector's own classification: 401 is the one credential verdict."""
    import inspect

    from custom_components.vag_connect.cariad.auth import _website_authproxy as wap

    src = inspect.getsource(wap)
    # the credential-specific exception is raised exactly once, under the 401
    assert src.count("raise InvalidCredentialsError(") == 1
    i = src.index("raise InvalidCredentialsError(")
    guard = src.rindex("if landed_status == 401:", 0, i)
    assert i - guard < 600, "the 401 guard is no longer what gates it"


def test_both_drivers_separate_the_two_cases():
    """config flow and options flow must BOTH classify — #957 only fixed one.

    The two drivers no longer live in one file: #1717 moved the options-flow
    one into ``_vwde_reauth`` so the repair flow could share it instead of
    carrying a second copy. This test caught that move, which is the useful
    thing about it, so it now searches both modules — the invariant is that each
    driver classifies, not which file it sits in.
    """
    import inspect

    from custom_components.vag_connect import _vwde_reauth as reauth
    from custom_components.vag_connect import config_flow as cf

    src = inspect.getsource(cf) + inspect.getsource(reauth)
    # one credential branch + one non-credential branch per driver
    assert src.count("except InvalidCredentialsError as err:") == 2
    assert src.count('raise ValueError("website_login_failed") from err') == 2
    for driver in ("_wap_begin_login", "_ovw_begin_login"):
        body = src[src.index(f"async def {driver}"):]
        body = body[: body.index("\n    async def ", 10)]
        assert "except InvalidCredentialsError" in body, driver
        assert 'ValueError("website_login_failed")' in body, driver
        # the credential verdict is still reachable for a real 401
        assert 'ValueError("invalid_credentials")' in body, driver


@pytest.mark.parametrize("lang", [
    "en", "de", "nl", "fr", "it", "es", "cs", "da", "fi", "nb", "sv", "pl",
])
def test_every_locale_can_render_both_errors_in_both_flows(lang):
    """The options step resolves against options.error — where neither key
    existed, so the user was shown the raw key instead of a sentence."""
    import json
    import pathlib

    p = pathlib.Path("custom_components/vag_connect/translations") / f"{lang}.json"
    doc = json.loads(p.read_text(encoding="utf-8"))
    for section in ("config", "options"):
        errs = doc[section]["error"]
        for key in ("invalid_credentials", "website_login_failed"):
            assert key in errs, f"{lang}/{section}.error/{key}"
            assert errs[key].strip(), f"{lang}/{section}.error/{key} is empty"


def test_the_new_message_does_not_blame_the_password():
    import json
    import pathlib

    doc = json.loads(
        pathlib.Path("custom_components/vag_connect/strings.json")
        .read_text(encoding="utf-8"))
    txt = doc["config"]["error"]["website_login_failed"].lower()
    assert "not the problem" in txt
    assert "log" in txt
