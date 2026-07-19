"""v2.20.0 — groundwork fixes mined from the issue tracker.

- mask_email: account identifier must never appear verbatim in logs (#709).
- seat_cupra persistent-403: log ONCE on crossing the threshold (not ~18×/poll)
  and with the honest device-attestation wording, not the stale "check for an
  integration update" that sent attestation-walled users chasing a phantom fix
  (#779, rmalbrecht's CUPRA Born still 403'd "Forbidden device detected" after
  the header bump).
"""

from __future__ import annotations

import asyncio
import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.vag_connect.cariad._util import mask_email
from custom_components.vag_connect.cariad.api import seat_cupra as sc
from custom_components.vag_connect.cariad.api.base import CariadBaseClient
from custom_components.vag_connect.cariad.api.seat_cupra import SeatCupraClient
from custom_components.vag_connect.cariad.exceptions import APIError


# ── mask_email (#709) ───────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("user@example.com", "u***@***.com"),
        ("prash@googlemail.co.uk", "p***@***.uk"),
        ("plainusername", "p***"),  # no @ → opaque username
        ("", "***"),
        (None, "***"),
    ],
)
def test_mask_email(value: str | None, expected: str) -> None:
    assert mask_email(value) == expected


def test_mask_email_never_contains_full_local_or_domain() -> None:
    out = mask_email("johndoe@secretdomain.com")
    assert "johndoe" not in out
    assert "secretdomain" not in out


# ── seat_cupra persistent-403 (#779) ────────────────────────────────────

_OLA_URL = "https://ola.prod.code.seat.cloud.vwgroup.com/v1/vehicles/X/capabilities"


def _run_persistent_403(n: int) -> SeatCupraClient:
    client = SeatCupraClient(MagicMock(), "cupra", "u@t.de", "pw")
    exc = APIError(403, _OLA_URL, '{"message":"Forbidden device detected"}')
    with (
        patch.object(CariadBaseClient, "_request", new=AsyncMock(side_effect=exc)),
        patch.object(sc, "get_fallback_count", return_value=0),
    ):

        async def _drive() -> None:
            for _ in range(n):
                with pytest.raises(APIError):
                    await client._request("GET", _OLA_URL)

        asyncio.run(_drive())
    return client


def test_persistent_403_sets_repair_flag() -> None:
    client = _run_persistent_403(sc._OLA_REPAIR_THRESHOLD + 3)
    assert client.ola_headers_repair_needed is True
    assert client._ola_consecutive_403 >= sc._OLA_REPAIR_THRESHOLD


def test_persistent_403_logs_error_once_not_per_endpoint(
    caplog: pytest.LogCaptureFixture,
) -> None:
    # 8 consecutive 403s over the threshold (5) must yield exactly ONE ERROR,
    # not one per call — the flood the fix removes.
    with caplog.at_level(logging.ERROR, logger="custom_components.vag_connect"):
        _run_persistent_403(sc._OLA_REPAIR_THRESHOLD + 3)
    errors = [r for r in caplog.records if "OLA 403 persistent" in r.getMessage()]
    assert len(errors) == 1


def test_persistent_403_message_is_honest_attestation() -> None:
    caplog_msgs: list[str] = []
    handler = logging.Handler()
    handler.emit = lambda record: caplog_msgs.append(record.getMessage())  # type: ignore[method-assign]
    logger = logging.getLogger("custom_components.vag_connect.cariad.api.seat_cupra")
    logger.addHandler(handler)
    try:
        _run_persistent_403(sc._OLA_REPAIR_THRESHOLD + 1)
    finally:
        logger.removeHandler(handler)
    msg = next(m for m in caplog_msgs if "OLA 403 persistent" in m)
    # Honest: attestation, not the stale "check for an integration update".
    assert "attestation" in msg.lower()
    assert "integration update can fix" not in msg or "not something" in msg.lower()
    assert "check for integration update" not in msg.lower()
    # The confirmed marker note appears because the body carries it.
    assert "marker confirmed" in msg.lower()
