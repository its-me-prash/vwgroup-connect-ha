# Copyright 2026 Prash Balan (@its-me-prash) - Apache License 2.0
"""v2.8.0 Action #3 - EU Data Act portal scraper tests.

Scope (per the v2.8.0 staging spec):

1. ``fetch_vehicle_zip`` handles a missing-zip response (Route A
   returns nothing, browser fallback disabled) without raising and
   advances the empty-streak counter so the coordinator can later
   surface a Repair issue.
2. ``parse_zip`` correctly extracts a subset of fields from a
   synthetic zip we build from the committed ``sample_export.spec.json``
   declarative fixture under ``tests/fixtures/data_act_portal/``.
3. ``to_vehicle_data`` produces a ``VehicleData`` populated with the
   core fields the coordinator expects (battery_soc, range_km,
   odometer, last_seen).

Tests stay pure-Python so they execute without a Home Assistant
install (per ``conftest.py`` policy). ``aiohttp`` is imported but
only as a type tag; no real network IO happens.
"""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path
from typing import Any

import pytest

from custom_components.vag_connect.cariad.auth._data_act_scraper import (
    DataActScraper,
)


_FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "data_act_portal"
_SPEC_FILE = _FIXTURE_DIR / "sample_export.spec.json"


def _build_zip_from_spec() -> bytes:
    """Build the synthetic export zip described by the committed spec.

    Reading the spec from disk on each test run keeps the test data
    auditable in plain text (reviewer can see exactly which JSON
    members are inside the zip) while letting the test use a real
    ``zipfile.ZipFile`` byte stream.
    """
    spec = json.loads(_SPEC_FILE.read_text(encoding="utf-8"))
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, body in spec["members"].items():
            if name.endswith(".json"):
                zf.writestr(name, json.dumps(body, sort_keys=True))
            else:
                zf.writestr(name, body)
    return buf.getvalue()


class _StubSession:
    """Minimal aiohttp.ClientSession stand-in for the scraper.

    The scraper uses ``self._session.get(...)`` as an async context
    manager and reads ``cookie_jar`` only inside the Playwright branch
    (which we don't exercise here). For the missing-zip test we want
    EVERY candidate path to fall through cleanly, so the stub raises
    ConnectionError on ``get`` to simulate "endpoint does not exist".
    The scraper catches that and continues to the next candidate.
    """

    def __init__(self) -> None:
        self.calls: int = 0

    def get(self, *_args: Any, **_kwargs: Any) -> Any:
        self.calls += 1
        raise ConnectionError("synthetic 'endpoint unreachable' for test")

    @property
    def cookie_jar(self) -> list[Any]:
        return []


@pytest.mark.asyncio
async def test_fetch_vehicle_zip_handles_missing_zip_without_raising() -> None:
    """Spec requirement #1: missing-zip response must not raise.

    Verifies:
    - ``fetch_vehicle_zip`` returns None when every candidate path
      raises a transient error (no real zip available).
    - The empty-streak counter advances by exactly 1 per failed poll.
    - The scraper does not raise to the caller (the coordinator
      depends on this contract for stale-cache UX).
    """
    scraper = DataActScraper(
        _StubSession(),
        brand_name="volkswagen",
        enable_browser_fallback=False,
    )
    assert scraper.empty_streak == 0
    result = await scraper.fetch_vehicle_zip("WVWZZZ1KZ8W123456")
    assert result is None
    assert scraper.empty_streak == 1
    assert scraper.needs_wake_hint is False

    # Three more empty polls should not raise either, and the
    # wake-hint threshold flips on at the documented count.
    for _ in range(3):
        result = await scraper.fetch_vehicle_zip("WVWZZZ1KZ8W123456")
        assert result is None
    assert scraper.empty_streak == 4
    assert scraper.needs_wake_hint is True


def test_parse_zip_extracts_json_members_from_fixture() -> None:
    """Spec requirement #2: parse_zip extracts JSON entries correctly.

    Builds the zip from the committed declarative spec and asserts
    that:
    - All four .json members appear in the returned dict keyed by
      their basename without the .json suffix.
    - The non-JSON README.txt member is ignored (parse_zip is JSON-only).
    - The values round-trip cleanly (currentSOC_pct, odometer, etc.).
    """
    scraper = DataActScraper(
        _StubSession(),
        brand_name="audi",
        enable_browser_fallback=False,
    )
    parsed = scraper.parse_zip(_build_zip_from_spec())

    assert set(parsed.keys()) == {"charging", "measurements", "status", "top"}
    assert "README" not in parsed  # non-json must be skipped

    assert parsed["charging"]["currentSOC_pct"] == 73
    assert parsed["charging"]["targetSOC_pct"] == 90
    assert parsed["measurements"]["odometerStatus"]["odometer"] == 42195
    assert parsed["measurements"]["rangeStatus"]["totalRange_km"] == 318
    assert parsed["status"]["carCapturedTimestamp"] == "2026-05-31T18:42:00Z"
    assert parsed["top"]["licensePlate"] == "AG 12345"


def test_parse_zip_returns_empty_dict_on_garbage_input() -> None:
    """Defensive bonus: non-zip bytes must yield an empty dict, not raise."""
    scraper = DataActScraper(
        _StubSession(),
        brand_name="skoda",
        enable_browser_fallback=False,
    )
    assert scraper.parse_zip(b"not a zip") == {}
    assert scraper.parse_zip(b"") == {}


def test_to_vehicle_data_populates_core_fields() -> None:
    """Spec requirement #3: to_vehicle_data fills the core fields.

    Asserts that the four fields the coordinator most depends on for
    headline UI (battery_soc, range_km, odometer, last_seen_at) all
    flow from the parsed zip into the VehicleData record. Also pins
    a couple of secondary fields (doors_locked, fuel_level, model,
    license_plate) so that the mapping doesn't silently regress.
    """
    scraper = DataActScraper(
        _StubSession(),
        brand_name="audi",
        enable_browser_fallback=False,
    )
    parsed = scraper.parse_zip(_build_zip_from_spec())
    vd = scraper.to_vehicle_data("WAUZZZ4G8KN123456", parsed)

    # Core fields per spec
    assert vd.battery_soc == 73
    assert vd.range_km == 318
    assert vd.odometer_km == 42195
    assert vd.last_seen_at == "2026-05-31T18:42:00Z"

    # Secondary defensive checks
    assert vd.target_soc == 90
    assert vd.charging_state == "charging"
    assert vd.fuel_level == 12
    assert vd.doors_locked is True
    assert vd.license_plate == "AG 12345"
    assert vd.model == "ID.4 Pro"
    assert vd.last_updated_at is not None
