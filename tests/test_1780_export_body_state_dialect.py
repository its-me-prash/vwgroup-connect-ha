# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#1780 (@kmeinderink, Audi Q4 e-tron) — his doors, windows, boot and bonnet
entities sat at ``unknown`` while his own downloaded one-time export carried
CLOSED and LOCKED for every one of them.

He then corrected his own report after checking the diagnostics: his periodic
feed does not contain those fields at all, only the export does. So this is not
a parser failure — we never asked for the export's spelling. The continuous feed
sends numeric enums (``open_state_front_left_door`` = 2/3); the export sends
string enums under per-part containers, and all of them are catalogued under
``Historical Export``.

Two traps are pinned here on purpose, because getting either wrong is worse than
mapping nothing at all:

* ``windows_individual`` holds **True == CLOSED**, the inverse of
  ``doors_individual``. Reading the export's openness straight into it would
  report every closed window as open.
* Only the two documented tokens are believed. The family also carries
  UNSUPPORTED / INVALID / UNKNOWN on cars that cannot report a part, and folding
  those into ``False`` would tell an owner the boot is shut when the car never
  said so.
"""
from __future__ import annotations

from custom_components.vag_connect.cariad.auth._eu_data_act import (
    _walk_fields,
    map_dataset_to_vehicle_data,
)
from custom_components.vag_connect.cariad.models import VehicleData

_SLOTS = ("front_left", "front_right", "rear_left", "rear_right")


def _map(fields: dict, base: VehicleData | None = None) -> VehicleData:
    """Map a ``{dataFieldName: value}`` set through the real portal envelope.

    The portal does NOT send these as nested objects — it sends a ``Data`` list
    of ``{dataFieldName, value}`` records whose names are the dotted catalogue
    paths, which is how @kmeinderink reported them ("Portal field
    (``dataFieldName``)"). Building a nested shape here instead produced a
    payload the walker flattens to nothing, and six tests that failed against
    correct code — so the envelope is part of what is under test.
    """
    payload = {
        "Data": [
            {"dataFieldName": name, "value": value}
            for name, value in fields.items()
        ]
    }
    return map_dataset_to_vehicle_data(
        _walk_fields(payload), base or VehicleData(vin="X")
    )


def _closed_car() -> dict:
    """@kmeinderink's reported export: everything shut and locked."""
    fields: dict = {}
    for p in _SLOTS:
        fields[f"door_info.{p}.door_status.value"] = "CLOSED"
        fields[f"door_info.{p}.door_lock_status.value"] = "LOCKED"
        fields[f"window_info.{p}.window_status.value"] = "CLOSED"
        fields[f"window_info.{p}.window_percentage_open.value"] = 0
    fields["trunk_lid_info.trunk_lid_status.value"] = "CLOSED"
    fields["trunk_lid_info.trunk_lid_lock_status.value"] = "LOCKED"
    fields["hood_info.hood_status.value"] = "CLOSED"
    fields["hood_info.hood_lock_status.value"] = "UNLOCKED"
    fields["parking_lights_info.left_status.value"] = "OFF"
    fields["parking_lights_info.right_status.value"] = "OFF"
    return fields


def test_his_export_fills_every_entity_that_was_unknown() -> None:
    d = _map(_closed_car())
    assert d.doors_open is False
    assert d.doors_locked is True
    assert d.windows_open is False
    assert d.trunk_open is False
    assert d.trunk_locked is True
    assert d.hood_open is False
    assert d.parking_light is False
    assert d.parking_light_left is False
    assert d.parking_light_right is False


def test_window_polarity_is_not_inverted() -> None:
    """The trap. An OPEN window must read as open, and the per-slot dict must
    hold False for it, because that dict means CLOSED."""
    payload = _closed_car()
    payload["window_info.rear_left.window_status.value"] = "OPEN"
    payload["window_info.rear_left.window_percentage_open.value"] = 42
    d = _map(payload)
    assert d.windows_open is True
    assert d.windows_individual["rearLeft"] is False      # False == open
    assert d.windows_individual["frontLeft"] is True      # True  == closed
    assert d.windows_position["rearLeft"] == 42


def test_one_open_door_opens_the_aggregate_and_one_unlocked_unlocks_it() -> None:
    payload = _closed_car()
    payload["door_info.front_right.door_status.value"] = "OPEN"
    payload["door_info.rear_right.door_lock_status.value"] = "UNLOCKED"
    d = _map(payload)
    assert d.doors_open is True
    assert d.doors_individual["frontRight"] is True       # True == open
    assert d.doors_individual["frontLeft"] is False
    assert d.doors_locked is False


def test_an_undocumented_token_yields_nothing_rather_than_closed() -> None:
    """A car that cannot report a part must leave the entity unknown."""
    for token in ("UNSUPPORTED", "INVALID", "UNKNOWN", "", "0", "ajar"):
        payload = _closed_car()
        payload["trunk_lid_info.trunk_lid_status.value"] = token
        payload["hood_info.hood_status.value"] = token
        d = _map(payload)
        assert d.trunk_open is None, f"{token!r} must not decide the boot"
        assert d.hood_open is None, f"{token!r} must not decide the bonnet"
        # The rest of the car still maps — one bad token is not a cliff.
        assert d.doors_locked is True


def test_a_live_feed_value_wins_over_the_export() -> None:
    """Fill-if-empty: the export is an older snapshot and must never overwrite
    a current reading, per slot as well as per field."""
    base = VehicleData(vin="X")
    base.trunk_open = True
    base.doors_locked = False
    base.doors_individual = {"frontLeft": True}
    base.windows_individual = {"frontLeft": False}
    d = _map(_closed_car(), base)
    assert d.trunk_open is True                      # not overwritten to False
    assert d.doors_locked is False                   # not overwritten to True
    assert d.doors_individual["frontLeft"] is True   # live slot kept
    assert d.windows_individual["frontLeft"] is False
    # …while the slots the feed did not have are still filled from the export.
    assert d.doors_individual["rearRight"] is False
    assert d.windows_individual["rearRight"] is True


def test_the_numeric_feed_dialect_still_works_untouched() -> None:
    """Control. If the continuous-feed path regressed, the rest proves nothing."""
    d = _map({
        "open_state_front_left_door": 2,       # 2 = open
        "open_state_front_right_door": 3,      # 3 = closed
        "locked_state_front_left_door": 2,     # 2 = locked
        "state_front_left_door_window_lifter": 3,   # 3 = closed
    })
    assert d.doors_individual["frontLeft"] is True
    assert d.doors_individual["frontRight"] is False
    assert d.doors_open is True
    assert d.windows_individual["frontLeft"] is True


def test_an_implausible_percentage_is_refused() -> None:
    payload = _closed_car()
    payload["window_info.front_left.window_percentage_open.value"] = 255
    d = _map(payload)
    assert "frontLeft" not in d.windows_position


def test_hood_lock_stays_scout_visible() -> None:
    """There is no hood-lock field in the model, so the leaf must NOT be
    consumed — consuming it would remove it from Scout discovery and we would
    never learn that cars send it."""
    syn: dict = {}
    flat = _walk_fields({"Data": [{"dataFieldName": n, "value": v}
                                   for n, v in _closed_car().items()]}, None, syn)
    d = map_dataset_to_vehicle_data(flat, VehicleData(vin="X"), field_syn=syn)
    leaves = {k.rsplit(".", 1)[-1] for k in (d.raw_unmapped_fields or {})}
    paths = " ".join(d.raw_unmapped_fields or {})
    assert "hood_lock_status" in paths or "hood_lock_status" in leaves
    # …and the ones we DO map are reclaimed, so they stop being reported.
    assert "trunk_lid_status" not in paths


# ── the discovery blind spot that hid this family in the first place ────────
def test_a_published_field_name_is_not_silenced_by_its_generic_leaf() -> None:
    """The reason nobody ever filed these fields.

    ``_is_envelope_noise`` matched on the leaf alone, and every field in this
    dialect ends in ``.value`` — so 231 catalogued field names were dropped from
    the Scout surface before anyone could see them. @kmeinderink found his own
    door and window states by reading his downloaded export by hand, which is
    not a discovery mechanism.
    """
    from custom_components.vag_connect.cariad.auth._eu_data_act import (
        _is_envelope_noise,
    )
    for name in (
        "door_info.front_left.door_status.value",
        "door_info.rear_left.door_lock_status.value",
        "window_info.front_right.window_percentage_open.value",
        "trunk_lid_info.trunk_lid_status.value",
        "hood_info.hood_lock_status.value",
        "parking_lights_info.left_status.value",
        "lvsoc_info.value",
        "service_maintenance_info.due_in_distance.unit",
        "cruise_range_secondary_info.value",
        "tires.[*].state",
        # our own endpoint tag in front of a real name must not change the verdict
        "eu_data_act.door_info.front_left.door_status.value",
    ):
        assert not _is_envelope_noise(name), f"{name} must stay discoverable"


def test_real_envelope_metadata_stays_silenced() -> None:
    """The carve-out still has to carve. A generic leaf that is generic all the
    way up is packaging, not a field — bare, or wrapped in nothing but the
    response envelope. These are the 142 catalogue rows that are just
    ``timestamp`` / ``message_id`` / ``state`` / ``value``.
    """
    from custom_components.vag_connect.cariad.auth._eu_data_act import (
        _is_envelope_noise,
    )
    for name in (
        "vin", "user_id", "userid", "timestamp", "timestampUtc", "message_id",
        "echo", "state", "value", "unit", "key", "auth_level", "transaction_id",
        "eu_data_act.vin", "eu_data_act.timestamp", "Data.key",
        "dataPoints.state",                      # the portal's own array wrapper
        "0001a2d8-ce6b-3fc7-aff3-bfaa2ada0979",  # a bare point UUID
    ):
        assert _is_envelope_noise(name), f"{name} must stay out of the Scout"


def test_a_non_generic_leaf_was_never_noise_and_still_is_not() -> None:
    """Control: the filter only ever applied to the generic-leaf set, so a real
    leaf name must be unaffected in both directions."""
    from custom_components.vag_connect.cariad.auth._eu_data_act import (
        _is_envelope_noise,
    )
    for name in ("soc", "odometer", "battery_level_HV", "trunk.open",
                 "ocpp_transaction_id", "climatisation_settings.duration"):
        assert not _is_envelope_noise(name)
