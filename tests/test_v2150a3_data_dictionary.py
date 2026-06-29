# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""b1/A3 — official EU Data Act Data Dictionary (V5.0) loader."""
from __future__ import annotations

from custom_components.vag_connect.cariad.auth import eu_data_dictionary as dd


class TestDictionaryLoader:
    def test_loads_full_v5_spec(self) -> None:
        assert dd.field_count() >= 1142

    def test_lookup_known_uuid(self) -> None:
        any_key = next(iter(dd._load()))
        entry = dd.lookup(any_key)
        assert entry is not None
        assert set(entry) == {"name", "unit", "type", "cluster", "description"}

    def test_lookup_dotted_path_falls_back_to_tail(self) -> None:
        any_key = next(iter(dd._load()))
        assert dd.lookup(f"data.points.{any_key}") == dd.lookup(any_key)

    def test_lookup_unknown_and_none(self) -> None:
        assert dd.lookup("not-a-real-uuid") is None
        assert dd.lookup(None) is None
        assert dd.lookup("") is None

    def test_describe_with_unit(self) -> None:
        # find a field that carries a real unit
        keyed = [
            (k, v) for k, v in dd._load().items()
            if v.get("unit") and v.get("name")
        ]
        assert keyed, "expected at least one field with a unit"
        key, val = keyed[0]
        label = dd.describe(key)
        assert label == f"{val['name']} ({val['unit']})"

    def test_describe_unknown_is_none(self) -> None:
        assert dd.describe("not-a-real-uuid") is None


class TestScoutReportEnrichment:
    """b1/A3 + Scout merge — the scout report names a known field UUID from the
    official spec (one detection pass → both maintainer report and, later, raw
    user-facing sensors)."""

    def test_known_uuid_gets_official_name(self) -> None:
        from custom_components.vag_connect.cariad._reporter_pipeline import (
            build_unexpected_keys_report,
        )
        from custom_components.vag_connect.cariad._unexpected_keys import (
            UnexpectedField,
        )

        named = [
            (k, v) for k, v in dd._load().items() if v.get("name")
        ]
        key, val = named[0]
        report = build_unexpected_keys_report(
            [
                UnexpectedField(key, "12", "eu-data-act", "2026-06-23T00:00:00+00:00"),
                UnexpectedField("totally.unknown", "x", "ep", "2026-06-23T00:00:00+00:00"),
            ],
            brand="vw",
        )
        assert "Spec field (official)" in report
        assert val["name"] in report          # known UUID → official name
        assert "| — |" in report              # unknown field → placeholder
