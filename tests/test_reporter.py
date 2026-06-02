# Copyright 2026 Prash Balan (@its-me-prash) — Apache License 2.0
# SPDX-License-Identifier: Apache-2.0
"""Tests for v1.9.0 — Vehicle Data Scout + Error Reporter + Pipeline.

Three modules under test, each with its own class:

- ``_unexpected_keys``: detector + EXPECTED_KEYS table + masking
- ``_error_reporter``: ring buffer + redaction + record_error never raises
- ``_reporter_pipeline``: Markdown formatter + GitHub URL builder
  (the ``ensure_*_issue`` helpers touch HA registry — covered by an
  integration test that mocks ``ir.async_create_issue``).

Privacy is the most-important property here, so half the assertions are
"sensitive value X is NOT present in output Y".
"""

from __future__ import annotations

from unittest.mock import patch
import urllib.parse



# ─────────────────────────────────────────────────────────────────────────────
# _unexpected_keys
# ─────────────────────────────────────────────────────────────────────────────


class TestUnexpectedKeys:
    """Vehicle Data Scout — drift detection + privacy masking."""

    def test_known_skoda_keys_are_not_flagged(self):
        from custom_components.vag_connect.cariad._unexpected_keys import (
            detect_unexpected,
        )
        # vehicle-status with only registered fields
        response = {
            "overall": {"doorsLocked": "YES", "reliableLockStatus": "LOCKED"},
            "detail": {"sunroof": "CLOSED", "trunk": "CLOSED", "bonnet": "CLOSED"},
            "carCapturedTimestamp": "2026-04-29T10:00:00Z",
        }
        findings = list(detect_unexpected("skoda", "vehicle-status", response))
        assert findings == []

    def test_unknown_skoda_key_is_flagged(self):
        from custom_components.vag_connect.cariad._unexpected_keys import (
            detect_unexpected,
        )
        response = {
            "overall": {"doorsLocked": "YES"},
            "carCapturedTimestamp": "2026-04-29T10:00:00Z",
            "newFirmwareField": "EXPERIMENTAL",
        }
        findings = list(detect_unexpected("skoda", "vehicle-status", response))
        paths = [f.path for f in findings]
        assert "newFirmwareField" in paths
        assert all(f.endpoint == "vehicle-status" for f in findings)

    def test_unregistered_brand_yields_nothing(self):
        from custom_components.vag_connect.cariad._unexpected_keys import (
            detect_unexpected,
        )
        # No EXPECTED_KEYS for "porsche" yet — must stay silent
        findings = list(detect_unexpected("porsche", "anything", {"x": 1}))
        assert findings == []

    def test_seat_inherits_cupra_table(self):
        from custom_components.vag_connect.cariad._unexpected_keys import (
            EXPECTED_KEYS,
        )
        assert EXPECTED_KEYS["seat"] is EXPECTED_KEYS["cupra"]

    def test_audi_inherits_volkswagen_table(self):
        from custom_components.vag_connect.cariad._unexpected_keys import (
            EXPECTED_KEYS,
        )
        assert EXPECTED_KEYS["audi"] is EXPECTED_KEYS["volkswagen"]

    def test_mask_value_redacts_vin_in_string(self):
        from custom_components.vag_connect.cariad._unexpected_keys import mask_value

        masked = mask_value("WAUZZZ4G3MN012345 reported")
        assert "WAUZZZ4G3MN012345" not in masked
        assert "012345" in masked  # last-6 still present (privacy-safe)

    def test_mask_value_rounds_floats(self):
        from custom_components.vag_connect.cariad._unexpected_keys import mask_value

        # GPS-precision floats get squashed to 1 decimal (~11 km buckets)
        assert mask_value(48.137154) == "48.1"
        assert mask_value(11.575401) == "11.6"

    def test_mask_value_strips_jwt(self):
        from custom_components.vag_connect.cariad._unexpected_keys import mask_value

        token = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjMifQ.aBc-def_ghi"
        out = mask_value(f"Bearer payload {token}")
        assert "[token]" in out
        assert "aBc-def_ghi" not in out

    def test_mask_value_strips_uuid(self):
        from custom_components.vag_connect.cariad._unexpected_keys import mask_value

        uid = "11111111-2222-3333-4444-555555555555"
        out = mask_value(f"user {uid} requested")
        assert "[uuid]" in out
        assert uid not in out

    def test_mask_value_strips_email(self):
        from custom_components.vag_connect.cariad._unexpected_keys import mask_value

        out = mask_value("contact prash@example.com today")
        assert "***@***" in out
        assert "prash@example.com" not in out

    def test_wildcard_path_matches(self):
        from custom_components.vag_connect.cariad._unexpected_keys import (
            detect_unexpected,
        )
        # cupra "status" expected has "doors.*.locked"
        response = {
            "doors": {
                "frontLeft": {"locked": True, "open": False},
                "frontRight": {"locked": True, "open": False},
            },
            "carCapturedTimestamp": "2026-04-29T10:00:00Z",
        }
        findings = list(detect_unexpected("cupra", "status", response))
        # known path doors.{position}.{locked,open} all covered by wildcards
        assert findings == []


# ─────────────────────────────────────────────────────────────────────────────
# _error_reporter
# ─────────────────────────────────────────────────────────────────────────────


class TestErrorReporter:
    """Ring buffer + redaction + NEVER-raises guarantee."""

    def test_ring_buffer_evicts_oldest(self):
        from custom_components.vag_connect.cariad._error_reporter import (
            ErrorRecord,
            ErrorRingBuffer,
        )
        buf = ErrorRingBuffer(max_size=3)
        for i in range(5):
            buf.append(
                ErrorRecord(
                    timestamp=f"2026-04-29T10:00:0{i}",
                    brand="skoda",
                    vin_masked="***ABC123",
                    model_year=None,
                    firmware=None,
                    exception_type=f"E{i}",
                    message_masked="x",
                    traceback_masked="",
                )
            )
        assert len(buf) == 3
        assert [r.exception_type for r in buf.records] == ["E2", "E3", "E4"]
        assert buf.latest is not None and buf.latest.exception_type == "E4"

    def test_record_error_masks_sensitive_data(self):
        from custom_components.vag_connect.cariad._error_reporter import (
            ErrorRingBuffer,
            record_error,
        )
        buf = ErrorRingBuffer()
        try:
            raise RuntimeError(
                "Failed for VIN WAUZZZ4G3MN012345 token "
                "eyJhbGc.eyJzdWI.aBcDef user 11111111-2222-3333-4444-555555555555 "
                "(prash@example.com)"
            )
        except RuntimeError as e:
            rec = record_error(buf, exception=e, brand="audi", vin="WAUZZZ4G3MN012345")

        msg = rec.message_masked
        # Sensitive substrings are GONE
        assert "WAUZZZ4G3MN012345" not in msg
        assert "aBcDef" not in msg
        assert "11111111-2222-3333-4444-555555555555" not in msg
        assert "prash@example.com" not in msg
        # Markers ARE present
        assert "[token]" in msg
        assert "[uuid]" in msg
        assert "***@***" in msg
        # VIN context preserved (last-6 only)
        assert rec.vin_masked == "***012345"
        assert rec.brand == "audi"
        assert rec.exception_type == "RuntimeError"

    def test_record_error_never_raises_on_failure(self):
        """``record_error`` MUST NOT raise even if buffer.append blows up."""
        from custom_components.vag_connect.cariad._error_reporter import (
            ErrorRingBuffer,
            record_error,
        )

        class BoomBuffer(ErrorRingBuffer):
            def append(self, record):
                raise RuntimeError("buffer is on fire")

        buf = BoomBuffer()
        # Should not raise — fallback path swallows the buffer error
        rec = record_error(buf, exception=ValueError("x"), brand="skoda")
        assert rec is not None

    def test_serialise_for_diagnostics_is_json_safe(self):
        import json

        from custom_components.vag_connect.cariad._error_reporter import (
            ErrorRingBuffer,
            record_error,
            serialise_for_diagnostics,
        )

        buf = ErrorRingBuffer()
        try:
            raise ValueError("simple message")
        except ValueError as e:
            record_error(buf, exception=e, brand="vw_eu", endpoint="/v1/x")

        payload = serialise_for_diagnostics(buf)
        # round-trips through json without errors
        assert json.dumps(payload)
        assert payload[0]["brand"] == "vw_eu"
        assert payload[0]["endpoint"] == "/v1/x"


# ─────────────────────────────────────────────────────────────────────────────
# _reporter_pipeline
# ─────────────────────────────────────────────────────────────────────────────


class TestReporterPipeline:
    """Markdown formatters + GitHub URL builder + HA repair-issue glue."""

    def test_unexpected_keys_report_renders_table(self):
        from custom_components.vag_connect.cariad._reporter_pipeline import (
            build_unexpected_keys_report,
        )
        from custom_components.vag_connect.cariad._unexpected_keys import (
            UnexpectedField,
        )

        findings = [
            UnexpectedField(
                path="overall.newField",
                sample_masked='"YES"',
                endpoint="vehicle-status",
                first_seen_at="2026-04-29T10:00:00Z",
            )
        ]
        body = build_unexpected_keys_report(
            findings, brand="skoda", model_year=2026, integration_version="1.9.0"
        )
        assert "Vehicle Data Scout" in body
        assert "skoda" in body
        assert "2026" in body
        assert "1.9.0" in body
        assert "overall.newField" in body
        assert "vehicle-status" in body
        # Privacy footer is mandatory
        assert "VINs masked" in body

    def test_unexpected_keys_report_empty_findings_returns_empty(self):
        from custom_components.vag_connect.cariad._reporter_pipeline import (
            build_unexpected_keys_report,
        )

        assert build_unexpected_keys_report([], brand="audi") == ""

    def test_error_report_renders_traceback(self):
        from custom_components.vag_connect.cariad._error_reporter import (
            ErrorRecord,
        )
        from custom_components.vag_connect.cariad._reporter_pipeline import (
            build_error_report,
        )

        rec = ErrorRecord(
            timestamp="2026-04-29T10:00:00",
            brand="vw_eu",
            vin_masked="***ABC123",
            model_year=2025,
            firmware="ME3 1.5",
            exception_type="APIError",
            message_masked="HTTP 500 from /v1/foo",
            traceback_masked='File "x.py", line 1\n  raise APIError(...)',
            endpoint="/v1/foo",
        )
        body = build_error_report([rec], brand="vw_eu", integration_version="1.9.0")
        assert "Error Reporter" in body
        assert "APIError" in body
        assert "***ABC123" in body
        assert "/v1/foo" in body
        # Traceback is fenced
        assert "```" in body

    def test_github_issue_url_is_pre_filled(self):
        from custom_components.vag_connect.cariad._reporter_pipeline import (
            github_issue_url,
        )

        url = github_issue_url(
            "[Vehicle Data Scout] 1 new field on skoda",
            "Body content here",
            labels=("vehicle-data-scout", "skoda"),
        )
        assert url.startswith(
            "https://github.com/its-me-prash/vag-connect-ha/issues/new?"
        )
        # Title, body, labels all present (URL-encoded)
        parsed = urllib.parse.parse_qs(url.split("?", 1)[1])
        assert parsed["title"][0].startswith("[Vehicle Data Scout]")
        assert parsed["body"][0] == "Body content here"
        assert parsed["labels"][0] == "vehicle-data-scout,skoda"

    def test_github_issue_url_truncates_long_body(self):
        from custom_components.vag_connect.cariad._reporter_pipeline import (
            github_issue_url,
        )

        big_body = "X" * 10_000
        url = github_issue_url("title", big_body, body_max=500)
        # Truncation marker is present
        assert "truncated" in urllib.parse.unquote(url)
        # Total query length is bounded
        assert len(url) < 1500

    def test_ensure_unexpected_keys_issue_creates_when_findings_present(self):
        from custom_components.vag_connect.cariad._reporter_pipeline import (
            ensure_unexpected_keys_issue,
        )
        from custom_components.vag_connect.cariad._unexpected_keys import (
            UnexpectedField,
        )

        findings = [
            UnexpectedField("a.b", '"x"', "vehicle-status", "2026-04-29T10:00:00")
        ]
        with patch(
            "custom_components.vag_connect.cariad._reporter_pipeline.ir.async_create_issue"
        ) as mock_create:
            ensure_unexpected_keys_issue(
                hass=object(),
                entry_id="entry1",
                findings=findings,
                brand="skoda",
            )
            assert mock_create.called
            # learn_more_url is a GitHub issue-new URL
            kwargs = mock_create.call_args.kwargs
            assert kwargs["learn_more_url"].startswith(
                "https://github.com/its-me-prash/vag-connect-ha/issues/new?"
            )
            assert kwargs["translation_key"] == "vehicle_data_scout_findings"

    def test_ensure_unexpected_keys_issue_deletes_when_empty(self):
        from custom_components.vag_connect.cariad._reporter_pipeline import (
            ensure_unexpected_keys_issue,
        )

        with patch(
            "custom_components.vag_connect.cariad._reporter_pipeline.ir.async_delete_issue"
        ) as mock_delete:
            ensure_unexpected_keys_issue(
                hass=object(),
                entry_id="entry1",
                findings=[],
                brand="skoda",
            )
            assert mock_delete.called

    def test_ensure_error_reporter_issue_severity_is_error(self):
        from custom_components.vag_connect.cariad._error_reporter import (
            ErrorRecord,
        )
        from custom_components.vag_connect.cariad._reporter_pipeline import (
            ensure_error_reporter_issue,
        )
        import homeassistant.helpers.issue_registry as ir

        rec = ErrorRecord(
            timestamp="2026-04-29",
            brand="audi",
            vin_masked="",
            model_year=None,
            firmware=None,
            exception_type="X",
            message_masked="m",
            traceback_masked="",
        )
        with patch(
            "custom_components.vag_connect.cariad._reporter_pipeline.ir.async_create_issue"
        ) as mock_create:
            ensure_error_reporter_issue(
                hass=object(), entry_id="e", records=[rec], brand="audi",
            )
            kwargs = mock_create.call_args.kwargs
            # Errors get higher severity than unexpected keys
            assert kwargs["severity"] == ir.IssueSeverity.ERROR
