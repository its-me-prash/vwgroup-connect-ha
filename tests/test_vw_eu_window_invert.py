# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""vw_eu CARIAD parser: ``windows_individual`` must follow the documented
``True == closed`` convention — the same one the EU-Data-Act portal parser
and ``VagWindowSensor`` already use. The CARIAD ``_parse_status`` path was the
lone outlier storing ``True == open``, so ``VagWindowSensor`` (which inverts)
rendered every *closed* window as *open* on Audi / VW-EU cars.

Also: option-dependent roof parts (rear sunroof / roof cover) that report a
non-open/closed sentinel status on a car without an opening roof must not
create a phantom 'open' entity — the descriptor stays None (phantom-guarded)
and no window entry is emitted.
"""
from __future__ import annotations


def _vw_client():
    from custom_components.vag_connect.cariad.api.vw_eu import VWEUClient
    client = VWEUClient.__new__(VWEUClient)
    client._vehicle_metadata = {}
    return client


def _windows_raw(*entries):
    return {"access": {"accessStatus": {"value": {"windows": list(entries)}}}}


def test_windows_individual_uses_true_equals_closed():
    """Documented convention: windows_individual stores True == closed."""
    client = _vw_client()
    raw = _windows_raw(
        {"name": "frontLeft", "status": [{"value": "closed"}]},
        {"name": "frontRight", "status": [{"value": "open"}]},
    )
    data = client._parse_status("VINX", raw, parking={})
    assert data.windows_individual["frontLeft"] is True    # closed
    assert data.windows_individual["frontRight"] is False   # open


def test_sentinel_roof_status_not_added_as_window():
    """A non-open/closed sentinel (SUV without an opening roof) is skipped,
    not stored as a phantom 'open' window."""
    client = _vw_client()
    raw = _windows_raw(
        {"name": "frontLeft", "status": [{"value": "closed"}]},
        {"name": "roofCover", "status": [{"value": "unsupported"}]},
        {"name": "sunRoofRear", "status": [{"value": "invalid"}]},
    )
    data = client._parse_status("VINX", raw, parking={})
    assert data.windows_individual["frontLeft"] is True
    assert "roofCover" not in data.windows_individual
    assert "sunRoofRear" not in data.windows_individual


def test_sentinel_roof_status_leaves_descriptor_none():
    """A sentinel roof status leaves the *_closed descriptor None so the
    phantom-entity guard suppresses it (instead of False → 'open')."""
    client = _vw_client()
    raw = _windows_raw(
        {"name": "roofCover", "status": [{"value": "unsupported"}]},
        {"name": "sunRoofRear", "status": [{"value": "invalid"}]},
    )
    data = client._parse_status("VINX", raw, parking={})
    assert data.roof_cover_closed is None
    assert data.sunroof_rear_closed is None


def test_real_open_closed_roof_still_parsed():
    """Regression guard: a car that genuinely reports open/closed roof parts
    must still populate the descriptors (sentinel skip must not drop real data)."""
    client = _vw_client()
    raw = _windows_raw(
        {"name": "sunRoofRear", "status": [{"value": "closed"}]},
        {"name": "roofCover", "status": [{"value": "open"}]},
    )
    data = client._parse_status("VINX", raw, parking={})
    assert data.sunroof_rear_closed is True
    assert data.roof_cover_closed is False
