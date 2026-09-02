# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#709 — a failed CSRF fetch said nothing about why, and it gates everything.

@dazj1990 sent a debug log whose entire story was:

    kickoff_custom_data_request: no CSRF token - aborting

No CSRF means no data request; no data request means no feed; no feed means no
entities. So this is the failure that matters most, and it was the one that
told us the least — every branch returned a bare None. A non-200, a timeout, a
renamed field and a portal that moved endpoints all looked identical.

It cost us: the reply drafted for him blamed the request format (fixed in
2.17.3) and told him to upgrade. His log shows he never got as far as sending a
request — he fails upstream of that fix, so upgrading would have changed
nothing and we'd have spent his goodwill on it. The reason we reached for that
explanation is that his log had no other detail to offer.

These tests assert on log output, which is normally a smell. Here the log IS
the feature: it's the only artefact a reporter can hand us.
"""
from __future__ import annotations

import logging
from typing import Any

import pytest

from custom_components.vag_connect.cariad.auth import _data_act_scraper


class _Resp:
    def __init__(self, status: int, payload: Any = None) -> None:
        self.status = status
        self._payload = payload

    async def __aenter__(self) -> "_Resp":
        return self

    async def __aexit__(self, *a: Any) -> None:
        return None

    async def json(self, content_type: Any = None) -> Any:
        return self._payload


class _Session:
    def __init__(self, resp: Any) -> None:
        self._resp = resp

    def get(self, url: str, **kw: Any) -> Any:
        if isinstance(self._resp, Exception):
            raise self._resp
        return self._resp


def _scraper(resp: Any) -> Any:
    s = _data_act_scraper.DataActScraper.__new__(_data_act_scraper.DataActScraper)
    s._session = _Session(resp)  # type: ignore[attr-defined]
    return s


@pytest.mark.asyncio
async def test_http_error_says_which_status(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG, logger=_data_act_scraper._LOGGER.name)
    assert await _scraper(_Resp(403))._fetch_csrf_token() is None
    assert "403" in caplog.text


@pytest.mark.asyncio
async def test_moved_endpoint_is_visible(caplog: pytest.LogCaptureFixture) -> None:
    # The path is an Adobe AEM endpoint. If VW moves off AEM this is what every
    # user hits at once, so a 404 must be legible.
    caplog.set_level(logging.DEBUG, logger=_data_act_scraper._LOGGER.name)
    assert await _scraper(_Resp(404))._fetch_csrf_token() is None
    assert "404" in caplog.text


@pytest.mark.asyncio
async def test_network_failure_names_the_exception(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG, logger=_data_act_scraper._LOGGER.name)
    assert await _scraper(TimeoutError("timed out"))._fetch_csrf_token() is None
    assert "TimeoutError" in caplog.text


@pytest.mark.asyncio
async def test_renamed_field_reports_the_keys_it_did_get(
    caplog: pytest.LogCaptureFixture,
) -> None:
    # The nastiest variant: HTTP 200, valid JSON, no token we recognise. Logging
    # the keys is what would let us spot a rename without a live account.
    caplog.set_level(logging.DEBUG, logger=_data_act_scraper._LOGGER.name)
    resp = _Resp(200, {"csrf_token": "x", "expires": 1})
    assert await _scraper(resp)._fetch_csrf_token() is None
    assert "csrf_token" in caplog.text


@pytest.mark.asyncio
async def test_unexpected_body_type_is_reported(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG, logger=_data_act_scraper._LOGGER.name)
    assert await _scraper(_Resp(200, ["not", "an", "object"]))._fetch_csrf_token() is None
    assert "list" in caplog.text


@pytest.mark.asyncio
async def test_both_known_spellings_still_work() -> None:
    assert await _scraper(_Resp(200, {"token": "T1"}))._fetch_csrf_token() == "T1"
    assert await _scraper(_Resp(200, {"csrfToken": "T2"}))._fetch_csrf_token() == "T2"


@pytest.mark.asyncio
async def test_the_token_value_never_reaches_the_log(
    caplog: pytest.LogCaptureFixture,
) -> None:
    # A CSRF token is a session credential. Reporters paste these logs into
    # public issues — the keys may be logged, the values must not.
    caplog.set_level(logging.DEBUG, logger=_data_act_scraper._LOGGER.name)
    resp = _Resp(200, {"csrf_token": "SUPER-SECRET-VALUE", "expires": 1})
    await _scraper(resp)._fetch_csrf_token()
    assert "SUPER-SECRET-VALUE" not in caplog.text


# ── #966 (Jradon001): the empty-body case is now diagnosable AND retried ─────
#
# His log showed `HTTP 200 but no usable token. Keys present: []`, which read as
# "VW renamed the field". Probing the live portal showed otherwise: an anonymous
# request gets exactly that body plus `x-sky-isauth: 0`. The portal runs two
# independent auth layers on one host — our session is valid at /proxy_api/*
# (his reads work, and the metadata call answered 404, not 401) while being
# anonymous at /libs/granite/* where the token lives. Those two causes need
# opposite responses, and the old code could not tell them apart.


class _HeaderResp(_Resp):
    """A response that also carries headers, like the real portal edge."""

    def __init__(self, status: int, payload: Any = None,
                 headers: dict[str, str] | None = None) -> None:
        super().__init__(status, payload)
        self.headers = headers or {}
        self.url = "https://eu-data-act.drivesomethinggreater.com/de/en/user.html"


class _SeqSession:
    """Returns a different response per call, so a retry can be observed."""

    def __init__(self, *responses: Any) -> None:
        self._responses = list(responses)
        self.calls: list[str] = []

    def get(self, url: str, **kw: Any) -> Any:
        self.calls.append(url)
        return self._responses.pop(0) if self._responses else _HeaderResp(200, {})


def _seq_scraper(*responses: Any) -> Any:
    s = _data_act_scraper.DataActScraper.__new__(_data_act_scraper.DataActScraper)
    s._session = _SeqSession(*responses)  # type: ignore[attr-defined]
    return s


@pytest.mark.asyncio
async def test_anonymous_at_aem_is_named_in_the_log(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level("DEBUG")
    s = _seq_scraper(
        _HeaderResp(200, {}, {"x-sky-isauth": "0"}),   # token fetch: anonymous
        _HeaderResp(200, {}),                           # the page GET
        _HeaderResp(200, {}, {"x-sky-isauth": "0"}),   # retry: still anonymous
    )
    assert await s._fetch_csrf_token() is None
    assert "ANONYMOUS" in caplog.text
    assert "x-sky-isauth=0" in caplog.text


@pytest.mark.asyncio
async def test_anonymous_triggers_one_page_load_and_a_retry() -> None:
    """The page GET is the same request a browser makes when opening the portal
    — our best effort at reviving the AEM leg before giving up."""
    s = _seq_scraper(
        _HeaderResp(200, {}, {"x-sky-isauth": "0"}),
        _HeaderResp(200, {}),
        _HeaderResp(200, {"token": "revived"}, {"x-sky-isauth": "1"}),
    )
    assert await s._fetch_csrf_token() == "revived"
    calls = s._session.calls  # type: ignore[attr-defined]
    assert any("/de/en/user.html" in c for c in calls), calls
    assert sum("token.json" in c for c in calls) == 2, calls


@pytest.mark.asyncio
async def test_second_revive_endpoint_recovers_the_token() -> None:
    """#1273 (steemandavid) — the user-page GET can land 200 yet leave the AEM leg
    anonymous, so the permission-check service is tried as a second revive; a token
    from that second retry is used."""
    s = _seq_scraper(
        _HeaderResp(200, {}, {"x-sky-isauth": "0"}),               # fetch: anonymous
        _HeaderResp(200, {}),                                       # revive 1: user.html
        _HeaderResp(200, {}, {"x-sky-isauth": "0"}),               # retry 1: still anon
        _HeaderResp(200, {}),                                       # revive 2: permissioncheck
        _HeaderResp(200, {"token": "T"}, {"x-sky-isauth": "1"}),  # retry 2: token!
    )
    assert await s._fetch_csrf_token() == "T"
    calls = s._session.calls  # type: ignore[attr-defined]
    assert any("/de/en/user.html" in c for c in calls), calls
    assert any("/services/permissioncheck" in c for c in calls), calls
    assert sum("token.json" in c for c in calls) == 3, calls   # initial + 2 retries


@pytest.mark.asyncio
async def test_authenticated_but_empty_does_not_retry(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Authenticated at AEM and still empty IS the renamed-field case. Loading
    the page cannot help, so it must not fire — that would be a pointless extra
    request on every poll."""
    caplog.set_level("DEBUG")
    s = _seq_scraper(_HeaderResp(200, {}, {"x-sky-isauth": "1"}))
    assert await s._fetch_csrf_token() is None
    assert s._session.calls == [  # type: ignore[attr-defined]
        "https://eu-data-act.drivesomethinggreater.com/libs/granite/csrf/token.json"
    ]
    assert "authenticated at the AEM layer" in caplog.text


@pytest.mark.asyncio
async def test_a_hard_http_error_does_not_trigger_the_page_load() -> None:
    """403/404 are not the anonymous case; retrying the page helps neither."""
    s = _seq_scraper(_HeaderResp(403, None, {}))
    assert await s._fetch_csrf_token() is None
    assert len(s._session.calls) == 1  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_cookie_names_are_logged_but_never_values(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Which cookies we hold is the other half of the diagnosis; a value here
    would be a live session token."""
    caplog.set_level("DEBUG")

    class _Cookie(dict):
        def __init__(self, key: str, domain: str) -> None:
            super().__init__({"domain": domain})
            self.key = key

    s = _seq_scraper(
        _HeaderResp(200, {}, {"x-sky-isauth": "0"}),
        _HeaderResp(200, {}),
        _HeaderResp(200, {}, {"x-sky-isauth": "0"}),
    )
    s._session.cookie_jar = [  # type: ignore[attr-defined]
        _Cookie("login-token", "eu-data-act.drivesomethinggreater.com"),
    ]
    await s._fetch_csrf_token()
    assert "login-token" in caplog.text
