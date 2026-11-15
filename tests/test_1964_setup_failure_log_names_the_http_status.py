# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#1964: the setup failure line names the HTTP status when the error has one.

When ``async_setup`` ends in its catch-all, the ERROR line carried only the
exception class. For an ``UpstreamUnavailableError`` that is not enough to act
on: since 5.2.2 the class is raised for a 404 or 410 on the EU Data Act
portal's vehicle list as well as for 5xx answers, and the line did not say
which. The log attached to #1964 showed exactly that line, with no status, so
it could not answer whether the portal was down or had refused the list.

A status code is not a secret, so it is appended on its own, the way the
sign-in strategy line in ``cariad/api/base.py`` does since #1915. The exception
MESSAGE stays withheld exactly as before (#1355): it can carry a callback URL
or a token. The tests below pin both halves, because the status is exactly the
kind of detail someone later "improves" by reaching for ``str(err)``.
"""

from __future__ import annotations

import asyncio
import logging
import threading
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

_LOGGER_NAME = "custom_components.vag_connect.coordinator"

# The two lines of the catch-all as they read for an error without a status.
# Written out in full on purpose: "exactly as before" is only pinned by an
# exact comparison, a substring would let a reworded line through.
_ERROR_LINE = (
    "VW Group Connect setup failed: {cls} "
    "(message redacted, see DEBUG for details)"
)
_DEBUG_LINE = (
    "VW Group Connect setup failed details withheld ({cls}) \N{EM DASH} the"
    " exception message can carry an OAuth code/token"
)

_TOKEN = "eyJhbGciOiJIUzI1NiJ9.ZmFrZS1wYXlsb2Fk.c2lnbmF0dXJl"


def _coord(brand: str = "audi"):
    from custom_components.vag_connect.coordinator import VagConnectCoordinator
    coord = VagConnectCoordinator.__new__(VagConnectCoordinator)
    coord.hass = MagicMock()
    coord.hass.loop = MagicMock()
    coord.entry = MagicMock()
    coord.entry.entry_id = "test"
    coord.entry.data = {
        "brand": brand, "username": "u@t.de",
        "password": "pw", "spin": "", "scan_interval": 5,
    }
    coord._vehicles_lock = threading.Lock()
    coord._cariad_client = None
    coord._started = False
    coord._was_available = True
    coord.vehicles = {}
    coord.data = None
    coord.async_set_updated_data = MagicMock()
    coord.async_request_refresh = AsyncMock()
    coord.logger = MagicMock()
    return coord


def _persisted_tokens():
    from custom_components.vag_connect.cariad.models import TokenSet
    return TokenSet(
        access_token="a", refresh_token="r", id_token="",
        expires_at=0.0, strategy="",
    )


def _client(get_vehicles):
    client = MagicMock()
    client.authenticate = AsyncMock()
    client.set_persisted_tokens = MagicMock()
    client.get_vehicles = get_vehicles
    # explicit: a bare MagicMock would auto-create a truthy portal channel.
    client._supplementary_eu_portal = None
    client._eu_portal = None
    return client


def _setup_records(
    err: BaseException, caplog: pytest.LogCaptureFixture
) -> list[logging.LogRecord]:
    """Run the real ``async_setup`` with ``get_vehicles`` raising ``err``.

    Returns every record the coordinator logged. The outcome is asserted here
    so that no test can pass on a setup that did not end in the catch-all.
    """
    from custom_components.vag_connect.cariad.api.factory import CariadClientFactory

    coord = _coord()
    client = _client(AsyncMock(side_effect=err))
    with caplog.at_level(logging.DEBUG, logger=_LOGGER_NAME), \
         patch.object(CariadClientFactory, "create", return_value=client), \
         patch("homeassistant.helpers.aiohttp_client.async_get_clientsession",
               return_value=MagicMock()), \
         patch("custom_components.vag_connect.cariad.auth._token_storage."
               "TokenStorage.load", new=AsyncMock(return_value=_persisted_tokens())), \
         patch("custom_components.vag_connect.cariad.auth._token_storage."
               "TokenStorage.save", new=AsyncMock()):
        assert asyncio.run(coord.async_setup()) is False, (
            "what async_setup returns for this failure must not change"
        )
    client.get_vehicles.assert_awaited()
    return [r for r in caplog.records if r.name == _LOGGER_NAME]


def _only(records: list[logging.LogRecord], level: int, marker: str) -> str:
    hits = [
        r.getMessage() for r in records
        if r.levelno == level and marker in r.getMessage()
    ]
    assert len(hits) == 1, f"expected one {marker!r} line, found {hits!r}"
    return hits[0]


def _error_line(records: list[logging.LogRecord]) -> str:
    return _only(records, logging.ERROR, "VW Group Connect setup failed: ")


def _debug_line(records: list[logging.LogRecord]) -> str:
    return _only(records, logging.DEBUG, "setup failed details withheld")


@pytest.mark.parametrize("status", [404, 410, 503])
def test_the_error_line_names_the_http_status(
    status: int, caplog: pytest.LogCaptureFixture
) -> None:
    """The reporter's case. A refused vehicle list (404, 410) and a backend
    that is down (5xx) raise the same class, so the status is the only thing
    in the line that tells them apart."""
    from custom_components.vag_connect.cariad.exceptions import (
        UpstreamUnavailableError,
    )

    records = _setup_records(UpstreamUnavailableError(status, brand="audi"), caplog)

    line = _error_line(records)
    assert f"HTTP {status}" in line, (
        "the setup failure line still does not say which HTTP status it was"
    )
    assert line == (
        f"VW Group Connect setup failed: UpstreamUnavailableError (HTTP {status}) "
        "(message redacted, see DEBUG for details)"
    )


def test_the_debug_line_names_the_http_status_too(
    caplog: pytest.LogCaptureFixture,
) -> None:
    from custom_components.vag_connect.cariad.exceptions import (
        UpstreamUnavailableError,
    )

    records = _setup_records(UpstreamUnavailableError(404, brand="audi"), caplog)

    assert "UpstreamUnavailableError (HTTP 404)" in _debug_line(records)


def test_an_error_without_a_status_logs_exactly_as_before(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Strict no-op for every error that carries no status."""
    records = _setup_records(RuntimeError("no status on this one"), caplog)

    assert _error_line(records) == _ERROR_LINE.format(cls="RuntimeError")
    assert _debug_line(records) == _DEBUG_LINE.format(cls="RuntimeError")


def test_a_status_that_is_not_a_number_is_not_logged(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Only an int is appended. A foreign exception is free to call anything
    ``status``, and a string there can be as revealing as the message."""

    class _ForeignError(Exception):
        status = f"weconnect://authenticated#access_token={_TOKEN}"

    records = _setup_records(_ForeignError("foreign"), caplog)

    assert _error_line(records) == _ERROR_LINE.format(cls="_ForeignError")
    assert _debug_line(records) == _DEBUG_LINE.format(cls="_ForeignError")
    logged = "\n".join(r.getMessage() for r in records)
    assert _TOKEN not in logged
    assert "weconnect://" not in logged


def test_the_message_of_the_exception_never_reaches_the_log(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The half that must not regress (#1355). The status is appended on its
    own; the message is not un-redacted to get at it."""
    from custom_components.vag_connect.cariad.exceptions import (
        UpstreamUnavailableError,
    )

    # The portal passes its own value as ``brand``, and the class interpolates
    # it into the message. A marker there shows whether the message leaked.
    err = UpstreamUnavailableError(404, brand="MARKER-IN-THE-MESSAGE")
    assert "MARKER-IN-THE-MESSAGE" in str(err), (
        "the probe no longer carries the marker, so this test proves nothing"
    )

    logged = "\n".join(r.getMessage() for r in _setup_records(err, caplog))

    assert "HTTP 404" in logged
    assert str(err) not in logged
    assert "MARKER-IN-THE-MESSAGE" not in logged
    assert "temporarily unavailable" not in logged
    assert "Do NOT reconfigure" not in logged

    caplog.clear()

    class _CallbackError(Exception):
        status = 404

    oauth = _CallbackError(
        f"weconnect://authenticated#access_token={_TOKEN}&code={_TOKEN}"
    )
    logged = "\n".join(r.getMessage() for r in _setup_records(oauth, caplog))
    assert "_CallbackError (HTTP 404)" in logged
    assert _TOKEN not in logged, "an OAuth token leaked into the log (#1355)"
    assert "weconnect://" not in logged
