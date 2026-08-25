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
