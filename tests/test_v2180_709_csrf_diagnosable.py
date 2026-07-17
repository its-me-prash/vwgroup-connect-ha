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
