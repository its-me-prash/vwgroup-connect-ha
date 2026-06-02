# Copyright 2026 Prash Balan (@its-me-prash) — Apache License 2.0
# SPDX-License-Identifier: Apache-2.0
"""Error Reporter — captures recent integration errors with masked context.

Companion to ``_unexpected_keys.py``. Where the Vehicle Data Scout
detects API surface drift (new fields), the Error Reporter captures
runtime failures (Exceptions, API errors, stack traces) with enough
context — brand, model year, firmware, masked VIN — to file a useful
bug report.

Both feed into the shared ``_reporter_pipeline`` for the 1-click
GitHub-or-Copy-to-Clipboard workflow (planned in v1.9.0).

Privacy:
- VINs masked via ``mask_vin``
- userIDs (UUIDs) and JWT tokens stripped from message + traceback
- Email addresses replaced with ``***@***``
- No GPS coordinates surface here (errors don't typically include them,
  but if they did, ``mask_value`` would round to 1 decimal as in the
  Data Scout)

Implementation: a coordinator-attached ring buffer of the last
``_MAX_ERRORS`` records (default 20). Older records drop off. Exposed
via a sensor (count) and a diagnostics-export field (full content,
masked).
"""

from __future__ import annotations

import re
import traceback
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from ._unexpected_keys import (
    _EMAIL_RE,
    _JWT_RE,
    _UUID_RE,
    _VIN_RE,
)
from ._util import mask_vin

# Keep the buffer small — 20 errors is enough to find a pattern, and it
# bounds memory + diagnostics-export size. Older records drop off the
# tail when a 21st arrives.
_MAX_ERRORS = 20

# Mask anything that looks like a Bearer token in headers / log lines
_BEARER_RE = re.compile(r"Bearer\s+[A-Za-z0-9._-]+", re.IGNORECASE)
# Mask any long base64-shaped opaque token (>= 32 chars)
_OPAQUE_TOKEN_RE = re.compile(r"\b[A-Za-z0-9+/]{32,}={0,2}\b")


@dataclass(frozen=True)
class ErrorRecord:
    """One captured error with anonymised context.

    Attributes:
        timestamp: When the error occurred (UTC ISO string).
        brand: Brand identifier (e.g. ``"audi"``, ``"skoda"``).
        vin_masked: VIN masked via ``mask_vin`` (e.g. ``"***ABC123"``)
            or empty string if not vehicle-bound.
        model_year: Model year if known (helps PPC/PPE detection).
        firmware: Firmware version string if known.
        exception_type: Class name of the exception (e.g. ``"APIError"``).
        message_masked: Exception message after running through
            ``_redact`` to strip tokens / VINs / emails / UUIDs.
        traceback_masked: Last frames of the traceback (max ~10 lines)
            after running through ``_redact``. Skipped if not available.
        endpoint: Optional URL or logical endpoint name (e.g.
            ``"/v1/vehicles/{vin}/access/lock"``) — VIN already masked.
    """

    timestamp: str
    brand: str
    vin_masked: str
    model_year: int | None
    firmware: str | None
    exception_type: str
    message_masked: str
    traceback_masked: str
    endpoint: str = ""


@dataclass
class ErrorRingBuffer:
    """Bounded list of the most recent ``ErrorRecord`` instances.

    Why a dataclass and not ``collections.deque``: we want an explicit
    ``records: list`` we can serialise straight into diagnostics export
    without converting types, and we want the buffer to be safely
    inspectable from the entity layer (sensor reads ``len(records)``).
    """

    records: list[ErrorRecord] = field(default_factory=list)
    max_size: int = _MAX_ERRORS

    def append(self, record: ErrorRecord) -> None:
        """Append a record, evicting the oldest if the buffer is full."""
        self.records.append(record)
        if len(self.records) > self.max_size:
            # Drop oldest — index 0
            self.records.pop(0)

    def clear(self) -> None:
        """Remove all records (called when user dismisses the repair)."""
        self.records.clear()

    def __len__(self) -> int:
        return len(self.records)

    @property
    def latest(self) -> ErrorRecord | None:
        """The most recent record, or ``None`` if buffer is empty."""
        return self.records[-1] if self.records else None


def _redact(text: str | None, *, max_len: int = 500) -> str:
    """Strip VINs, emails, JWTs, UUIDs, Bearer tokens, opaque tokens
    from a string. Truncate to ``max_len`` chars."""
    if not text:
        return ""
    s = text
    s = _VIN_RE.sub(lambda m: mask_vin(m.group(0)), s)
    s = _EMAIL_RE.sub("***@***", s)
    s = _JWT_RE.sub("[token]", s)
    s = _UUID_RE.sub("[uuid]", s)
    s = _BEARER_RE.sub("Bearer [token]", s)
    s = _OPAQUE_TOKEN_RE.sub("[opaque]", s)
    if len(s) > max_len:
        s = s[: max_len - 3] + "..."
    return s


def record_error(
    buffer: ErrorRingBuffer,
    *,
    exception: BaseException,
    brand: str,
    vin: str | None = None,
    model_year: int | None = None,
    firmware: str | None = None,
    endpoint: str | None = None,
) -> ErrorRecord:
    """Capture an exception into the ring buffer with masked context.

    Returns the created ``ErrorRecord`` so callers (e.g. tests) can
    inspect it. Side effect: ``buffer`` gets one new record (may evict
    oldest). NEVER raises — error reporting must not cause errors.
    """
    try:
        # Last ~10 frames is enough to identify cause without bloating
        # diagnostics. Module/line info is what reviewers need.
        tb_lines = traceback.format_exception(
            type(exception), exception, exception.__traceback__,
        )
        # Keep last 12 lines (≈ 3 frames + headers)
        tb_text = "".join(tb_lines[-12:])
        record = ErrorRecord(
            timestamp=datetime.now(tz=timezone.utc).isoformat(),
            brand=brand,
            vin_masked=mask_vin(vin) if vin else "",
            model_year=model_year,
            firmware=firmware,
            exception_type=type(exception).__name__,
            message_masked=_redact(str(exception)),
            traceback_masked=_redact(tb_text, max_len=2000),
            endpoint=_redact(endpoint, max_len=200) if endpoint else "",
        )
        buffer.append(record)
        return record
    except Exception:  # noqa: BLE001 — see docstring: NEVER raise
        # Build a minimal "we tried to report and failed" record
        fallback = ErrorRecord(
            timestamp=datetime.now(tz=timezone.utc).isoformat(),
            brand=brand,
            vin_masked="",
            model_year=None,
            firmware=None,
            exception_type="ErrorReporterFailure",
            message_masked=f"Failed to capture {type(exception).__name__}",
            traceback_masked="",
        )
        try:
            buffer.append(fallback)
        except Exception:  # noqa: BLE001
            pass
        return fallback


def serialise_for_diagnostics(buffer: ErrorRingBuffer) -> list[dict[str, Any]]:
    """Convert the ring buffer to a JSON-serialisable list for HA's
    ``async_get_config_entry_diagnostics``. All values already masked."""
    return [
        {
            "timestamp": r.timestamp,
            "brand": r.brand,
            "vin_masked": r.vin_masked,
            "model_year": r.model_year,
            "firmware": r.firmware,
            "exception_type": r.exception_type,
            "message": r.message_masked,
            "traceback": r.traceback_masked,
            "endpoint": r.endpoint,
        }
        for r in buffer.records
    ]
