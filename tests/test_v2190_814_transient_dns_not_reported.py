# Copyright 2026 Prash Balan (@its-me-prash) - Apache License 2.0
# SPDX-License-Identifier: AGPL-3.0-or-later
"""v2.19.0 (#814) — a transient DNS/network error must NOT be error-reported.

#814 was an auto-filed Error Reporter issue whose 3 errors were all
``ClientConnectorDNSError: Timeout while contacting DNS servers`` — the user's HA
box failing to resolve ``emea.bff.cariad.digital``. base._request retries those,
then raises ``APIError(0, url, "transient: ...")``. The poll handler previously
only de-escalated 5xx (``status >= 500``), so the status-0 transient network
error fell through and got escalated to the public Error Reporter — noise, not a
bug. ``_is_selfhealing_poll_error`` now catches it.
"""
from __future__ import annotations

import asyncio

import pytest
from aiohttp import ClientConnectorError, ClientPayloadError, ServerDisconnectedError

from custom_components.vag_connect.coordinator import _is_selfhealing_poll_error
from custom_components.vag_connect.cariad.exceptions import (
    APIError,
    UpstreamUnavailableError,
)


def test_814_dns_timeout_is_self_healing() -> None:
    err = APIError(
        0,
        "https://emea.bff.cariad.digital/vehicle/v1/vehicles/X/selectivestatus",
        "transient: ClientConnectorDNSError: Cannot connect to host "
        "emea.bff.cariad.digital:443 ssl:default [Timeout while contacting DNS servers]",
    )
    assert _is_selfhealing_poll_error(err) is True


def test_5xx_and_upstream_are_self_healing() -> None:
    assert _is_selfhealing_poll_error(APIError(503, "u", "service unavailable")) is True
    assert _is_selfhealing_poll_error(APIError(500, "u", "boom")) is True
    assert _is_selfhealing_poll_error(UpstreamUnavailableError("backend down")) is True


def test_real_data_plane_403_still_reported() -> None:
    # a genuine entitlement/attestation 403 IS our concern → still escalated
    assert _is_selfhealing_poll_error(APIError(403, "u", "USER_NOT_AUTHORIZED")) is False


def test_status0_without_transient_tag_not_blanket_suppressed() -> None:
    # only the explicit "transient:" tag from base._request self-heals; a bare
    # status-0 with some other body is not swallowed.
    assert _is_selfhealing_poll_error(APIError(0, "u", "unexpected empty body")) is False


def test_parse_and_other_exceptions_still_reported() -> None:
    assert _is_selfhealing_poll_error(ValueError("bad parse")) is False
    assert _is_selfhealing_poll_error(KeyError("missing")) is False


def test_transient_gateway_404_not_reported() -> None:
    # #1233/#1242/#1244 — the emea.bff.cariad.digital edge intermittently returns
    # the generic router "404 page not found" for selectivestatus; it clears next
    # poll, so it must NOT spam the public Error Reporter.
    body = ('{"error":{"message":"Upstream service responded with 404 Not Found",'
            '"info":"404 page not found\\n"}}')
    assert _is_selfhealing_poll_error(APIError(404, "u", body)) is True


def test_structured_404_still_reported() -> None:
    # a real per-vehicle not-found (different body) is our concern → still escalated
    assert _is_selfhealing_poll_error(
        APIError(404, "u", '{"error":"vehicle not found"}')
    ) is False


# ── #1959 — the RAW exception, from a client that is not base ────────────────
#
# #814 above was fixed for the shape ``base._request`` produces: an ``APIError``
# with status 0 and a ``"transient:"`` body. Every branch in the classifier
# tested an ``APIError``, so the fix only reached the clients that go through
# base.
#
# **Five of the fifteen clients do not** build on it: PlugAndPlay and WCG (the
# dongle cloud), Porsche, Skoda-official and VW-NA each have their own request
# path, verified by resolving the real MRO rather than grepping for
# ``(CariadBaseClient)`` — an earlier grep called every client standalone because
# it missed indirect inheritance.
#
# But "does not inherit" is not the same question as "lets the exception
# through", and only the second one matters here. Measured per client:
#
#   dongle cloud, Skoda-official  convert nothing  -> all four classes arrive raw
#   VW-NA                         catches 3 of 4   -> leaks ClientPayloadError
#   Porsche                       retries, then raises the tagged APIError
#
# So the gap is real on two clients and partial on a third; Porsche was already
# covered by the #814 branch above. The guard is still written for the whole
# tuple, because it costs nothing and a client added later inherits the cover.
#
# That filed #1959: one "Connection reset by peer" against the dongle cloud, on
# one car, over two days. Ordinary internet, presented as a defect — and noise
# in that report teaches people to ignore the next one.


class _ConnKey:
    """The minimum aiohttp needs to build a ClientConnectorError."""

    host = "prod.acpp.cariad.digital"
    port = 443
    ssl = True

    def __repr__(self) -> str:
        return self.host


@pytest.mark.parametrize(
    ("err", "what"),
    [
        (ClientConnectorError(_ConnKey(), OSError("Connection reset by peer")),
         "the #1959 reset against the dongle cloud"),
        (ServerDisconnectedError(), "a mid-stream disconnect"),
        (ClientPayloadError("truncated"), "a truncated response body"),
        (asyncio.TimeoutError(), "a request timeout"),
    ],
    ids=["connector-reset", "disconnected", "payload", "timeout"],
)
def test_1959_a_raw_transient_from_a_standalone_client_is_self_healing(
    err: Exception, what: str
) -> None:
    assert _is_selfhealing_poll_error(err) is True, (
        f"{what} would be escalated to the public Error Reporter"
    )


def test_1959_the_list_is_imported_rather_than_restated() -> None:
    """One list of what counts as transient, not two that drift apart. If base
    adds a class, the classifier gains it without being edited — and this test
    is what makes that claim checkable."""
    from custom_components.vag_connect.cariad.api.base import _TRANSIENT_NET_ERRORS

    for cls in _TRANSIENT_NET_ERRORS:
        assert _is_selfhealing_poll_error(cls.__new__(cls)) is True, cls.__name__


def test_1959_a_genuine_defect_from_the_same_client_is_still_reported() -> None:
    """The exclusion is by exception CLASS, never by which client raised it. A
    real failure on the dongle path must still reach the reporter — otherwise
    this fix would have silenced a whole channel."""
    assert _is_selfhealing_poll_error(APIError(400, "u", "bad request")) is False
    assert _is_selfhealing_poll_error(TypeError("mapper got a list")) is False
    assert _is_selfhealing_poll_error(AttributeError("no attribute 'soc'")) is False


def test_1959_an_os_error_is_not_blanket_suppressed() -> None:
    """``ClientConnectorError`` wraps an ``OSError``, but a bare ``OSError``
    reaching the poll handler is not the same thing — it could be a local file
    or permission failure, which IS worth reporting. The guard must test the
    aiohttp classes, not their cause."""
    assert _is_selfhealing_poll_error(OSError("Connection reset by peer")) is False
