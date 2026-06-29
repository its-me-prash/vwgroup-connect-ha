# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""v2.2.0 PR #3 — json_safe converter tests.

Closes the bug-class that hit Skoda PR #1090: ``extra_state_attributes``
returning non-JSON-native types (datetime, dataclass, set, bytes) breaks
MQTT statestream + recorder + REST API silently.

"Worst. Bug. Ever."  — Comic Book Guy, on a datetime in extra_state_attributes
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from custom_components.vag_connect.cariad._util import json_safe


class TestJsonSafePrimitives:
    """Primitives pass through unchanged."""

    def test_none(self) -> None:
        assert json_safe(None) is None

    def test_str(self) -> None:
        assert json_safe("hello") == "hello"

    def test_int_float_bool(self) -> None:
        assert json_safe(42) == 42
        assert json_safe(3.14) == 3.14
        assert json_safe(True) is True
        assert json_safe(False) is False


class TestJsonSafeDatetime:
    """The Skoda PR #1090 root-cause: datetime needs ISO conversion."""

    def test_naive_datetime(self) -> None:
        d = datetime(2026, 5, 16, 12, 0, 0)
        out = json_safe(d)
        assert out == "2026-05-16T12:00:00"

    def test_tz_aware_datetime(self) -> None:
        d = datetime(2026, 5, 16, 12, 0, 0, tzinfo=timezone.utc)
        out = json_safe(d)
        assert out == "2026-05-16T12:00:00+00:00"

    def test_date_only(self) -> None:
        d = date(2026, 5, 16)
        out = json_safe(d)
        assert out == "2026-05-16"

    def test_timedelta(self) -> None:
        td = timedelta(minutes=5, seconds=30)
        out = json_safe(td)
        assert out == 330.0


class TestJsonSafeCollections:
    """Containers recursively processed."""

    def test_dict_with_datetime(self) -> None:
        d = {"last_seen_at": datetime(2026, 5, 16, tzinfo=timezone.utc)}
        out = json_safe(d)
        assert out == {"last_seen_at": "2026-05-16T00:00:00+00:00"}

    def test_nested_dict(self) -> None:
        d = {"a": {"b": {"c": datetime(2026, 1, 1)}}}
        out = json_safe(d)
        assert out == {"a": {"b": {"c": "2026-01-01T00:00:00"}}}

    def test_list_of_dicts_with_datetime(self) -> None:
        d = [{"ts": datetime(2026, 1, 1)}, {"ts": datetime(2026, 2, 1)}]
        out = json_safe(d)
        assert out == [
            {"ts": "2026-01-01T00:00:00"},
            {"ts": "2026-02-01T00:00:00"},
        ]

    def test_tuple_becomes_list(self) -> None:
        out = json_safe((1, 2, 3))
        assert out == [1, 2, 3]

    def test_set_sorted_to_list(self) -> None:
        out = json_safe({"b", "a", "c"})
        assert out == ["a", "b", "c"]


class TestJsonSafeDataclass:
    """Dataclass instances → dict (the actual Skoda PR #1090 scenario)."""

    def test_simple_dataclass(self) -> None:
        @dataclass
        class Event:
            vin: str
            event_type: str
            timestamp: datetime

        e = Event(
            vin="WAUZZZ123",
            event_type="charging",
            timestamp=datetime(2026, 5, 16, tzinfo=timezone.utc),
        )
        out = json_safe(e)
        assert out == {
            "vin": "WAUZZZ123",
            "event_type": "charging",
            "timestamp": "2026-05-16T00:00:00+00:00",
        }


class TestJsonSafeBytes:
    """bytes → utf-8 string or hex fallback."""

    def test_valid_utf8(self) -> None:
        assert json_safe(b"hello") == "hello"

    def test_invalid_utf8_falls_back_to_hex(self) -> None:
        out = json_safe(b"\xff\xfe\xfd")
        assert out == "fffefd"


class TestJsonSafeRoundtrip:
    """End-to-end: any json_safe output must survive json.dumps."""

    def test_complex_roundtrip(self) -> None:
        original = {
            "vin": "MASKED",
            "last_seen_at": datetime(2026, 5, 16, tzinfo=timezone.utc),
            "doors": [{"name": "front", "locked": True}],
            "history": [{"ts": datetime(2026, 1, 1)}, {"ts": datetime(2026, 2, 1)}],
            "tags": {"phev", "audi"},
        }
        out = json_safe(original)
        # Roundtrip must not raise
        encoded = json.dumps(out)
        decoded = json.loads(encoded)
        assert decoded["vin"] == "MASKED"
        assert decoded["last_seen_at"] == "2026-05-16T00:00:00+00:00"
        assert decoded["doors"] == [{"name": "front", "locked": True}]
        assert decoded["history"] == [
            {"ts": "2026-01-01T00:00:00"},
            {"ts": "2026-02-01T00:00:00"},
        ]
        assert sorted(decoded["tags"]) == ["audi", "phev"]


class TestJsonSafeDefensive:
    """Never raise, even on weird inputs."""

    def test_unhashable_unknown_type_falls_back_to_str(self) -> None:
        class Weird:
            def __str__(self) -> str:
                return "weird-instance"
        out = json_safe(Weird())
        assert out == "weird-instance"
