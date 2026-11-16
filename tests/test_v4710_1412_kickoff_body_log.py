# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#1412 (chrisbamtam, Audi Q6 e-tron) — the kickoff POST used to log only
``len(body_text)`` on a non-2xx, so the actual 400/500 reason was invisible to
the reporter and to us. These pin the new behaviour: both non-2xx branches now
carry a REDACTED body excerpt (whitespace-collapsed, VIN masked, e-mails /
tokens / URL query strings scrubbed, length-capped) plus the ``x-sky-isauth``
header and content-type, and the wording states facts only — no unproven "a
request likely already exists; a live feed may still deliver" guess on a branch
that performs no readback.
"""
from __future__ import annotations

import logging
from typing import Any
from unittest.mock import AsyncMock

import pytest

from custom_components.vag_connect.cariad.auth._data_act_scraper import (
    DataActScraper,
    _redact_body_snippet,
)

_VIN = "WVWZZZAUZFW000000"

# A worst-case error body: it echoes the full VIN, the account e-mail, a
# bearer-like token, a request URL with a query string, and enough prose filler
# (no 20+ char run, so the token scrubber leaves it be) to blow past the cap.
_EMAIL = "chris.bamtam@example.com"
_TOKEN = "a1b2c3d4e5f60718293a4b5c6d7e8f9012345678"
_QUERY_URL = "https://eu-data-act.vwgroup-datahub.com/x?access_token=SEKRET99"
_TAIL = "TAILENDMARKER"
_BODY = (
    f"Rejected for VIN {_VIN} account {_EMAIL} token {_TOKEN} "
    f"see {_QUERY_URL} . " + ("reason lorem ipsum dolor " * 30) + _TAIL
)


class _Resp:
    def __init__(self, status: int) -> None:
        self.status = status
        self.headers = {"x-sky-isauth": "0", "Content-Type": "application/json"}

    async def __aenter__(self) -> "_Resp":
        return self

    async def __aexit__(self, *_a: Any) -> bool:
        return False

    async def text(self, errors: str | None = None) -> str:
        return _BODY

    async def json(self, content_type: Any = None) -> Any:
        return {}


class _ScriptedSession:
    def __init__(self, statuses: list[int]) -> None:
        self.statuses = statuses
        self.post_calls: list[tuple[str, dict]] = []

    def post(self, url: str, **kw: Any) -> _Resp:
        self.post_calls.append((url, kw))
        index = min(len(self.post_calls) - 1, len(self.statuses) - 1)
        return _Resp(self.statuses[index])


def _scraper(sess: Any) -> DataActScraper:
    s = DataActScraper(sess, brand_name="volkswagen")
    s._fetch_csrf_token = AsyncMock(return_value="")  # type: ignore[method-assign]
    s.get_active_custom_request_identifier = AsyncMock(  # type: ignore[method-assign]
        return_value=None
    )
    return s


# --- the redaction helper in isolation -------------------------------------


def test_snippet_masks_vin_and_scrubs_secrets() -> None:
    out = _redact_body_snippet(_BODY, _VIN)
    assert _VIN not in out
    assert "...000000" in out           # last 6 kept
    assert _EMAIL not in out
    assert "<redacted-email>" in out
    assert _TOKEN not in out
    assert "SEKRET99" not in out         # URL query scrubbed
    assert "access_token=" not in out


def test_snippet_is_capped_and_collapses_whitespace() -> None:
    out = _redact_body_snippet(_BODY, _VIN)
    assert len(out) <= 303               # 300 + "..."
    assert out.endswith("...")
    assert _TAIL not in out              # tail past the cap is dropped
    assert "\n" not in out and "  " not in out


def test_empty_body_gives_empty_snippet() -> None:
    assert _redact_body_snippet("", _VIN) == ""


# --- the kickoff log lines --------------------------------------------------


@pytest.mark.asyncio
async def test_retry_branch_logs_redacted_snippet(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """First (non-last) rejection: facts-only retry line with the snippet."""
    sess = _ScriptedSession([400, 201])
    with caplog.at_level(logging.INFO):
        await _scraper(sess).kickoff_custom_data_request(_VIN)
    text = caplog.text
    assert "attempt with Duration='No Expiry'" in text
    assert "trying 'One Month' next" in text
    assert "x-sky-isauth=0" in text
    assert "body (" in text
    # redaction held on the retry line too
    assert _VIN not in text
    assert _EMAIL not in text
    assert _TOKEN not in text


@pytest.mark.asyncio
async def test_final_4xx_is_warning_with_redacted_snippet(
    caplog: pytest.LogCaptureFixture,
) -> None:
    sess = _ScriptedSession([400, 400])
    with caplog.at_level(logging.INFO):
        result = await _scraper(sess).kickoff_custom_data_request(_VIN)
    assert result is None
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert warnings, "final 4xx must stay a WARNING"
    msg = warnings[-1].getMessage()
    assert "HTTP 400" in msg
    assert "no data feed will start" in msg
    assert "x-sky-isauth=0" in msg
    assert "...000000" in msg
    assert _VIN not in msg
    assert _EMAIL not in msg
    assert "<redacted-email>" in msg
    assert _TOKEN not in msg
    assert "SEKRET99" not in msg


@pytest.mark.asyncio
async def test_final_5xx_is_info_and_drops_unproven_wording(
    caplog: pytest.LogCaptureFixture,
) -> None:
    sess = _ScriptedSession([500, 500])
    with caplog.at_level(logging.INFO):
        result = await _scraper(sess).kickoff_custom_data_request(_VIN)
    assert result is None
    text = caplog.text
    # severity split kept: no WARNING for a 5xx
    assert not [r for r in caplog.records if r.levelno == logging.WARNING]
    assert "HTTP 500" in text
    # the unproven guess is gone
    assert "likely already exists" not in text
    assert "may still deliver" not in text
    # still diagnosable + redacted
    assert "x-sky-isauth=0" in text
    assert _VIN not in text
    assert _TOKEN not in text
