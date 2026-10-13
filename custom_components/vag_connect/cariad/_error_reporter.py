# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
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
from dataclasses import dataclass, field, replace
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
        model: Vehicle model name if known (e.g. ``"ID.4"``). Generic,
            NOT PII — makes the bug report recognizable at a glance.
        model_year: Model year if known (helps PPC/PPE detection).
        firmware: Firmware version string if known.
        exception_type: Class name of the exception (e.g. ``"APIError"``).
        message_masked: Exception message after running through
            ``_redact`` to strip tokens / VINs / emails / UUIDs.
        traceback_masked: Last frames of the traceback (max ~10 lines)
            after running through ``_redact``. Skipped if not available.
        endpoint: Optional URL or logical endpoint name (e.g.
            ``"/v1/vehicles/{vin}/access/lock"``) — VIN already masked.
        repeat_count: How many times this identical error arrived in a row.
            ``1`` for a one-off. ``timestamp`` stays at the FIRST occurrence,
            so a persistent failure reads as "started then, seen N times".
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
    model: str | None = None
    repeat_count: int = 1


# Fields that identify "this same failure happened again": everything except
# the timestamp, which differs by definition, and the counter itself.
_IDENTITY_FIELDS = (
    "brand",
    "vin_masked",
    "model",
    "model_year",
    "firmware",
    "exception_type",
    "message_masked",
    "traceback_masked",
    "endpoint",
)


def _is_same_error(a: ErrorRecord, b: ErrorRecord) -> bool:
    """True when two records describe the same failure, ignoring when."""
    return all(getattr(a, f) == getattr(b, f) for f in _IDENTITY_FIELDS)


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
        """Append a record, evicting the oldest if the buffer is full.

        A record identical to the newest one is collapsed into it, raising its
        ``repeat_count`` and keeping the first occurrence's timestamp. #1808: a
        car that fails the same way on every poll used to push 20 copies of one
        error through the buffer within hours, evicting every unrelated record,
        so the report that reached the tracker showed a single error and no
        history at all. Collapsing keeps the signal, including how persistent
        the failure is, rather than either spamming or silencing it.

        Only CONSECUTIVE repeats collapse. Merging across an intervening
        different error would make the order of the buffer lie, so an
        alternating A-B-A pattern is deliberately left as three records.
        """
        prev = self.records[-1] if self.records else None
        if prev is not None and _is_same_error(prev, record):
            self.records[-1] = replace(
                prev, repeat_count=prev.repeat_count + 1,
            )
            return
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


# The response body gets its own budget rather than sharing the message's, so
# a long body cannot push the status line out of the record.
_BODY_MAX_LEN = 600


def _exception_body(exception: BaseException) -> str:
    """The HTTP response body an ``APIError`` carries, or ``""``.

    ``base._request`` reads the body and passes it to
    ``APIError(status, url, body)``, where #1355 deliberately keeps it out of
    ``__str__``, so that any call site logging or re-raising the exception
    cannot leak a VIN or a token through the message. The body stays on the
    exception as an attribute "for classification".

    That is also why #1808 arrived unactionable: this reporter recorded
    ``str(exception)`` and nothing else, so an Audi's repeated ``400`` on
    ``selectivestatus`` reached the tracker as a bare "API error 400 for
    <url>". The integration's own note in ``exceptions.py`` calls a 400
    ambiguous (expired subscription, transient backend error, or our own
    payload), and the body is the only thing that separates those. Here the
    body is wanted, and it goes through ``_redact`` like every other captured
    string, so masking still happens before anything is shown.
    """
    body = getattr(exception, "body", None)
    if not isinstance(body, str):
        return ""
    return body.strip()


def record_error(
    buffer: ErrorRingBuffer,
    *,
    exception: BaseException,
    brand: str,
    vin: str | None = None,
    model: str | None = None,
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
        # The message, plus the response body when the exception carries one
        # that is not already part of the message (#1808).
        message = _redact(str(exception))
        body_text = _redact(_exception_body(exception), max_len=_BODY_MAX_LEN)
        if body_text and body_text not in message:
            message = f"{message}\nresponse body: {body_text}"
        record = ErrorRecord(
            timestamp=datetime.now(tz=timezone.utc).isoformat(),
            brand=brand,
            vin_masked=mask_vin(vin) if vin else "",
            model=model,
            model_year=model_year,
            firmware=firmware,
            exception_type=type(exception).__name__,
            message_masked=message,
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
            model=model,
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
            "model": r.model,
            "model_year": r.model_year,
            "firmware": r.firmware,
            "exception_type": r.exception_type,
            "message": r.message_masked,
            "traceback": r.traceback_masked,
            "endpoint": r.endpoint,
            "repeat_count": r.repeat_count,
        }
        for r in buffer.records
    ]
