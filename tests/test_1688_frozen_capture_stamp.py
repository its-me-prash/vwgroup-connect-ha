# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#1688 (@Datendieb, VW Multivan T7 eHybrid) — the stale-data verdict fired on
data that was minutes old.

His portal kept delivering across one afternoon — odometer 18987 → 19002, SoC
79 → 45 → 82 while charging — but the car's own ``car_captured_*`` stamp stayed
on 28 September. We report VW's stamp faithfully; the verdict built on top of it
was the part that was wrong, so the Repair claimed 105 h and the problem sensor
went on.

He also spotted the giveaway himself: ``last_snapshot_at`` read minutes ago while
``minutes_since_last_snapshot`` next to it read 6317. That field is named for the
snapshot and was computed from the capture age.

The liveness rule is deliberately ONE-DIRECTIONAL: a changed reading proves the
feed is live, an unchanged one proves nothing — a car parked for days repeats its
readings, and that case must keep relying on the capture age or a genuinely
frozen feed would stop being reported, which is what the Repair is for.
"""
from __future__ import annotations

from custom_components.vag_connect.coordinator import _age_s, _values_moved


# --- the liveness probe -----------------------------------------------------

def test_the_reporters_own_evidence_counts_as_movement():
    prev = {"odometer_km": 18987, "battery_soc": 79}
    now = {"odometer_km": 19002, "battery_soc": 45}
    assert _values_moved(prev, now) in ("odometer_km", "battery_soc")


def test_a_charging_soc_climb_counts():
    assert _values_moved({"battery_soc": 55}, {"battery_soc": 82}) == "battery_soc"


def test_plug_and_lock_changes_count():
    assert _values_moved({"plug_connected": False}, {"plug_connected": True}) == (
        "plug_connected"
    )
    assert _values_moved({"doors_locked": True}, {"doors_locked": False}) == (
        "doors_locked"
    )


def test_a_parked_car_shows_no_movement():
    """The case that MUST keep relying on the capture age."""
    same = {"odometer_km": 19002, "battery_soc": 82, "plug_connected": True}
    assert _values_moved(dict(same), dict(same)) is None


def test_no_previous_snapshot_proves_nothing():
    assert _values_moved(None, {"odometer_km": 1}) is None
    assert _values_moved({}, {"odometer_km": 1}) is None


def test_appearing_or_vanishing_values_are_not_movement():
    # a field that was absent, or went None, says nothing about freshness —
    # treating it as movement would mask a feed that is dropping fields
    assert _values_moved({"battery_soc": None}, {"battery_soc": 80}) is None
    assert _values_moved({"battery_soc": 80}, {"battery_soc": None}) is None
    assert _values_moved({}, {"battery_soc": 80}) is None


def test_a_config_echo_is_not_movement():
    """A target temperature or charge limit can change without the car
    reporting anything new, so none of those may prove liveness."""
    prev = {"target_temperature": 21.0, "battery_care_target_soc_pct": 80}
    now = {"target_temperature": 23.0, "battery_care_target_soc_pct": 90}
    assert _values_moved(prev, now) is None


def test_it_names_the_field_not_the_value():
    """The debug line must be able to say WHICH reading moved without printing
    a position."""
    moved = _values_moved({"position_lat": 48.1}, {"position_lat": 52.5})
    assert moved == "position_lat"


# --- the snapshot age -------------------------------------------------------

def test_the_snapshot_age_reads_an_iso_stamp():
    from datetime import datetime, timedelta, timezone

    recent = (datetime.now(tz=timezone.utc) - timedelta(minutes=7)).isoformat()
    age = _age_s(recent)
    assert age is not None and 300 < age < 900


def test_the_snapshot_age_accepts_a_z_suffix_and_naive_datetimes():
    from datetime import datetime, timedelta, timezone

    z = (datetime.now(tz=timezone.utc) - timedelta(minutes=3)) \
        .isoformat().replace("+00:00", "Z")
    assert _age_s(z) is not None
    naive = datetime.utcnow() - timedelta(minutes=3)  # noqa: DTZ003
    assert _age_s(naive) is not None


def test_the_snapshot_age_is_none_for_nothing_usable():
    for raw in (None, "", "not-a-date", 42, [], {}):
        assert _age_s(raw) is None


def test_a_future_stamp_yields_a_negative_age_not_an_alarm():
    from datetime import datetime, timedelta, timezone

    future = (datetime.now(tz=timezone.utc) + timedelta(hours=2)).isoformat()
    age = _age_s(future)
    assert age is not None and age < 0


# --- the wiring -------------------------------------------------------------

def test_the_verdict_and_the_repair_use_the_liveness_rule():
    import inspect

    from custom_components.vag_connect import coordinator as mod

    src = inspect.getsource(mod)
    assert "_moved = _values_moved(_prev_snap, data)" in src
    # the binary and the Repair must agree — both gated on the same _moved
    assert 'data["data_stale"] = (' in src
    assert "if _age is not None and _age >= _threshold_s and not _moved:" in src
    # and the misnamed field now measures the snapshot
    assert "_snap_age = _age_s(_snap_at)" in src
