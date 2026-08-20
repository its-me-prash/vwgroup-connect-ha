# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#1195 — a partial poll that drops the HV pair must not publish the frozen leaf.

The EU Data Act portal ships the SoC two ways: the single-occurrence, VALID
``battery_level_HV`` pair (the reliable live value) and a ``battery_state_report.soc``
leaf that can be the frozen value from the last stop-charging report, stamped with
a fresh-looking capture time. When a poll OMITS the HV pair, only that frozen leaf
survives — and on a car that normally reports HV the integration would publish it
as a phantom SoC up/down while the car is parked. ``reconcile`` now holds the
recorded value in that case.

The fixtures are soulriding's real CUPRA Born datasets 12–15 (#1195), redacted to
``<REDACTED>`` VIN/user_id. Chronologically: 12 has the live HV pair (SoC 66),
13 and 14 are partial (HV absent, only the frozen leaf 67), 15 has the HV pair
again (SoC 55). A correct parser+reconcile reads 66 → 66 → 66 → 55, never 67.
"""
from __future__ import annotations

import json
from pathlib import Path

from custom_components.vag_connect.cariad.auth._eu_data_act import (
    _walk_fields,
    map_dataset_to_vehicle_data,
)
from custom_components.vag_connect.cariad.models import VehicleData
from custom_components.vag_connect.cariad.vehicle_cache import reconcile, strip_runtime

_FIX = Path(__file__).parent / "fixtures" / "eu_data_act_1195"


def _parse(name: str) -> dict:
    payload = json.loads((_FIX / name).read_text(encoding="utf-8"))
    d = VehicleData(vin="TESTVIN0000000000")
    fts: dict = {}
    fsyn: dict = {}
    cont: dict = {}
    fuu: dict = {}
    fields = _walk_fields(payload, fts, fsyn, cont, fuu)
    return map_dataset_to_vehicle_data(fields, d, fts, fsyn, cont, fuu).to_dict()


# ── the real-data sequence ────────────────────────────────────────────────────
def test_partial_polls_hold_the_hv_soc_not_the_frozen_leaf() -> None:
    names = sorted(p.name for p in _FIX.glob("dataset_*.json"))
    assert [n[:10] for n in names] == ["dataset_12", "dataset_13", "dataset_14", "dataset_15"]

    previous: dict | None = None
    seq: list[int | None] = []
    for name in names:
        merged, _notes = reconcile(previous, _parse(name))
        seq.append(merged.get("battery_soc"))
        previous = strip_runtime(merged)

    # 66 (HV) → 66 held → 66 held → 55 (HV). Never the frozen 67.
    assert seq == [66, 66, 66, 55], seq


def test_each_dataset_parsed_alone_shows_the_bug_source() -> None:
    # Sanity: parsed in isolation, the partial datasets DO surface the frozen leaf
    # (67) — which is exactly why the cross-poll hold in reconcile is needed.
    assert _parse("dataset_12_20260818181316Z.json")["battery_soc"] == 66
    assert _parse("dataset_13_20260818182550Z.json")["battery_soc"] == 67
    assert _parse("dataset_15_20260818185540Z.json")["battery_soc"] == 55
    assert _parse("dataset_12_20260818181316Z.json")["battery_soc_from_hv"] is True
    assert _parse("dataset_13_20260818182550Z.json")["battery_soc_from_hv"] is False


# ── the reconcile guard in isolation ──────────────────────────────────────────
def test_leaf_only_after_hv_holds_recorded() -> None:
    prev = {"battery_soc": 55, "battery_soc_from_hv": True}
    fresh = {"battery_soc": 67, "battery_soc_from_hv": False}
    merged, notes = reconcile(prev, fresh)
    assert merged["battery_soc"] == 55
    assert merged["battery_soc_from_hv"] is True  # provenance stays HV (sticky)
    assert any("held recorded 55" in n for n in notes)


def test_never_hv_car_keeps_trusting_the_leaf() -> None:
    # A car that never ships HV: provenance is never True, so the guard is inert
    # and the leaf value is trusted — no regression.
    prev = {"battery_soc": 67, "battery_soc_from_hv": False}
    fresh = {"battery_soc": 70, "battery_soc_from_hv": False}
    merged, _ = reconcile(prev, fresh)
    assert merged["battery_soc"] == 70


def test_a_real_hv_poll_updates_normally() -> None:
    prev = {"battery_soc": 55, "battery_soc_from_hv": True}
    fresh = {"battery_soc": 60, "battery_soc_from_hv": True}
    merged, _ = reconcile(prev, fresh)
    assert merged["battery_soc"] == 60


def test_provenance_survives_a_soc_less_poll() -> None:
    # A poll with no SoC at all carries the recorded one forward AND keeps the HV
    # provenance sticky, so the next leaf-only poll is still guarded.
    prev = {"battery_soc": 55, "battery_soc_from_hv": True}
    fresh = {"battery_soc": None, "battery_soc_from_hv": None}
    merged, _ = reconcile(prev, fresh)
    assert merged["battery_soc"] == 55
    assert merged["battery_soc_from_hv"] is True
