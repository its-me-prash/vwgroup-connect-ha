# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for #1808 — an Error Reporter report you can actually act on.

An Audi A6 Sportback e-tron reported ``APIError 400`` on ``selectivestatus``
and the report was unactionable, for two independent reasons.

**The response body never arrived.** ``base._request`` reads the body and
hands it to ``APIError(status, url, body)``, where #1355 deliberately keeps
it off ``__str__`` so that re-raising or logging the exception cannot leak a
VIN. The reporter then records ``_redact(str(exception))`` — so the one place
whose entire job is to mask and surface diagnostics dropped the only part
that says *why* the backend refused. The integration's own comment in
``exceptions.py`` calls a 400 ambiguous ("could be expired subscription,
could be a transient backend error, could be our payload"), and without the
body there is no way to tell those apart. These tests pin the body into the
record, redacted through the same helper as everything else.

**Identical failures ate the history.** The ring buffer holds 20 records with
no de-duplication, so a car failing the same way every poll overwrites every
other record within a few hours: by the time anyone looks, the buffer says
only that one error exists and every unrelated clue is gone. These tests pin
consecutive-identical collapsing with a repeat count, which keeps the signal
(including how persistent it is) instead of either spamming or silencing it.

Deliberately NOT covered here, because it is not knowable yet: whether this
400 deserves a backoff or de-escalation from the public reporter. Availability
is already handled upstream (``_FAILURE_TOLERANCE`` 3 plus a 6 h stale-cache
window), and silencing an ambiguous 400 could hide a payload bug of ours. The
body has to be visible first.
"""

from __future__ import annotations

# A real-shaped VIN and a JWT-shaped token, used to prove the body is masked
# on its way into the record. Neither belongs to anyone: the VIN is the
# documentation example used across this suite.
_VIN = "WVWZZZ1KZAW000123"
_JWT = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjMifQ.dBjftJeZ4CVPmB92K27uhbUJU1p1r"


def _api_error(status: int = 400, body: str = "", url: str = ""):
    """An ``APIError`` shaped exactly like the one ``base._request`` raises."""
    from custom_components.vag_connect.cariad.exceptions import APIError

    return APIError(
        status,
        url or f"https://emea.bff.cariad.digital/vehicle/v1/vehicles/{_VIN}"
        "/selectivestatus",
        body,
    )


def _raised(exc: BaseException) -> BaseException:
    """Give ``exc`` a real ``__traceback__``, as ``record_error`` expects."""
    try:
        raise exc
    except BaseException as caught:  # noqa: BLE001 — that is the point
        return caught


def _record(exception: BaseException, **kw):
    """Record one error into a fresh buffer and return the record."""
    from custom_components.vag_connect.cariad._error_reporter import (
        ErrorRingBuffer,
        record_error,
    )

    buf = ErrorRingBuffer()
    kw.setdefault("brand", "audi")
    return record_error(buf, exception=exception, **kw)


# ─────────────────────────────────────────────────────────────────────────────
# The response body reaches the record
# ─────────────────────────────────────────────────────────────────────────────


class TestResponseBodySurfaced:
    """A 400's body is what makes the report actionable — it must be there."""

    def test_body_appears_in_the_recorded_message(self):
        rec = _record(_raised(_api_error(body='{"error":"invalid_jobs"}')))
        assert "invalid_jobs" in rec.message_masked

    def test_status_and_url_still_there(self):
        """The body is added, it does not replace the existing message."""
        rec = _record(_raised(_api_error(body='{"error":"invalid_jobs"}')))
        assert "API error 400" in rec.message_masked
        assert "selectivestatus" in rec.message_masked

    def test_body_is_labelled_so_a_reader_knows_what_it_is(self):
        rec = _record(_raised(_api_error(body="subscription expired")))
        assert "response body" in rec.message_masked.lower()

    def test_no_body_leaves_the_message_alone(self):
        rec = _record(_raised(_api_error(body="")))
        assert "response body" not in rec.message_masked.lower()
        assert rec.message_masked.strip() == rec.message_masked

    def test_whitespace_only_body_counts_as_no_body(self):
        rec = _record(_raised(_api_error(body="   \n  ")))
        assert "response body" not in rec.message_masked.lower()

    def test_exception_without_a_body_attribute_is_unchanged(self):
        rec = _record(_raised(ValueError("plain failure")))
        assert "plain failure" in rec.message_masked
        assert "response body" not in rec.message_masked.lower()

    def test_non_string_body_is_ignored_and_does_not_raise(self):
        """``record_error`` must NEVER raise — a odd body type included."""
        exc = _raised(ValueError("odd"))
        exc.body = {"not": "a string"}  # type: ignore[attr-defined]
        rec = _record(exc)
        assert rec.exception_type == "ValueError"
        assert "response body" not in rec.message_masked.lower()

    def test_body_already_in_the_message_is_not_appended_again(self):
        """A body identical to the message would otherwise print twice."""
        exc = _raised(_api_error(body=""))
        exc.body = str(exc)  # type: ignore[attr-defined]
        rec = _record(exc)
        assert "response body" not in rec.message_masked.lower()
        assert rec.message_masked.count("API error 400") == 1


class TestBodyIsRedacted:
    """The body is untrusted backend text, so it goes through ``_redact``."""

    def test_vin_in_the_body_is_masked(self):
        rec = _record(_raised(_api_error(body=f'{{"vin":"{_VIN}"}}')))
        assert _VIN not in rec.message_masked
        # and the masked form did land, so the body was carried, not dropped
        assert "***000123" in rec.message_masked

    def test_email_in_the_body_is_masked(self):
        rec = _record(_raised(_api_error(body="owner: someone@example.com")))
        assert "someone@example.com" not in rec.message_masked
        assert "***@***" in rec.message_masked

    def test_jwt_in_the_body_is_stripped(self):
        rec = _record(_raised(_api_error(body=f"token={_JWT}")))
        assert _JWT not in rec.message_masked

    def test_long_body_is_truncated(self):
        """A hostile or HTML error page must not bloat the record."""
        rec = _record(_raised(_api_error(body="x" * 5000)))
        assert len(rec.message_masked) < 1200

    def test_truncation_does_not_eat_the_status_line(self):
        rec = _record(_raised(_api_error(body="y" * 5000)))
        assert "API error 400" in rec.message_masked


# ─────────────────────────────────────────────────────────────────────────────
# Repeated identical failures stop eating the buffer
# ─────────────────────────────────────────────────────────────────────────────


class TestRepeatCollapsing:
    """20 identical records used to evict every other clue."""

    def _buf(self):
        from custom_components.vag_connect.cariad._error_reporter import (
            ErrorRingBuffer,
        )

        return ErrorRingBuffer()

    def _put(self, buf, exc, **kw):
        from custom_components.vag_connect.cariad._error_reporter import (
            record_error,
        )

        kw.setdefault("brand", "audi")
        return record_error(buf, exception=exc, **kw)

    def test_a_single_error_has_repeat_count_one(self):
        rec = _record(_raised(_api_error(body="a")))
        assert rec.repeat_count == 1

    def test_two_identical_errors_collapse_to_one_record(self):
        buf = self._buf()
        for _ in range(2):
            self._put(buf, _raised(_api_error(body="same")))
        assert len(buf.records) == 1

    def test_the_collapsed_record_counts_both(self):
        buf = self._buf()
        for _ in range(2):
            self._put(buf, _raised(_api_error(body="same")))
        assert buf.records[0].repeat_count == 2

    def test_the_collapsed_record_keeps_the_first_timestamp(self):
        """'When did this start' is the useful end of a persistent failure."""
        buf = self._buf()
        first = self._put(buf, _raised(_api_error(body="same")))
        started = first.timestamp
        for _ in range(4):
            self._put(buf, _raised(_api_error(body="same")))
        assert buf.records[0].timestamp == started

    def test_a_different_error_does_not_collapse(self):
        buf = self._buf()
        self._put(buf, _raised(_api_error(body="one")))
        self._put(buf, _raised(_api_error(body="two")))
        assert len(buf.records) == 2
        assert [r.repeat_count for r in buf.records] == [1, 1]

    def test_a_different_status_does_not_collapse(self):
        buf = self._buf()
        self._put(buf, _raised(_api_error(status=400, body="x")))
        self._put(buf, _raised(_api_error(status=404, body="x")))
        assert len(buf.records) == 2

    def test_a_different_vehicle_does_not_collapse(self):
        buf = self._buf()
        self._put(buf, _raised(_api_error(body="x")), vin=_VIN)
        self._put(buf, _raised(_api_error(body="x")), vin="WVWZZZ1KZAW999888")
        assert len(buf.records) == 2

    def test_only_consecutive_repeats_collapse(self):
        """A documented limit: interleaving keeps the chronology honest."""
        buf = self._buf()
        self._put(buf, _raised(_api_error(body="A")))
        self._put(buf, _raised(_api_error(body="B")))
        self._put(buf, _raised(_api_error(body="A")))
        assert len(buf.records) == 3

    def test_a_persistent_failure_no_longer_evicts_the_history(self):
        """The #1808 regression, stated as the user experiences it."""
        buf = self._buf()
        self._put(buf, _raised(ValueError("the clue worth keeping")))
        for _ in range(200):
            self._put(buf, _raised(_api_error(body="persistent 400")))
        kept = [r.message_masked for r in buf.records]
        assert any("the clue worth keeping" in m for m in kept)
        assert len(buf.records) == 2
        assert buf.records[-1].repeat_count == 200

    def test_the_buffer_still_evicts_when_genuinely_full(self):
        """Collapsing must not break the bound on distinct errors."""
        buf = self._buf()
        for i in range(30):
            self._put(buf, _raised(_api_error(body=f"distinct {i}")))
        assert len(buf.records) == buf.max_size

    def test_latest_still_points_at_the_newest_record(self):
        buf = self._buf()
        self._put(buf, _raised(_api_error(body="old")))
        for _ in range(3):
            self._put(buf, _raised(_api_error(body="new")))
        assert buf.latest is not None
        assert "new" in buf.latest.message_masked
        assert buf.latest.repeat_count == 3


# ─────────────────────────────────────────────────────────────────────────────
# It has to be visible in what the user actually posts
# ─────────────────────────────────────────────────────────────────────────────


class TestRenderedReport:
    """A fix nobody can see in the issue body is not a fix."""

    def _body(self, records):
        from custom_components.vag_connect.cariad._reporter_pipeline import (
            build_error_report,
        )

        return build_error_report(records, brand="audi", model="A6")

    def test_the_body_text_shows_up_in_the_report(self):
        rec = _record(_raised(_api_error(body='{"error":"invalid_jobs"}')))
        assert "invalid_jobs" in self._body([rec])

    def test_a_repeat_count_is_shown(self):
        from dataclasses import replace

        rec = replace(_record(_raised(_api_error(body="x"))), repeat_count=42)
        out = self._body([rec])
        assert "42" in out

    def test_a_single_occurrence_says_nothing_about_repeats(self):
        rec = _record(_raised(_api_error(body="x")))
        assert "Seen:" not in self._body([rec])

    def test_diagnostics_export_carries_the_repeat_count(self):
        from custom_components.vag_connect.cariad._error_reporter import (
            ErrorRingBuffer,
            record_error,
            serialise_for_diagnostics,
        )

        buf = ErrorRingBuffer()
        for _ in range(3):
            record_error(buf, exception=_raised(_api_error(body="z")), brand="audi")
        rows = serialise_for_diagnostics(buf)
        assert rows[0]["repeat_count"] == 3
