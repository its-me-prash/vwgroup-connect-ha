# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#1797 / #1803 / #1795 — the ``<container>.state`` validity companions.

Four Scout reports from three cars (a VW ID.3 Neo Life and two CUPRA Raval)
described the same three leaves: ``enginehood.state``, ``trunk.state`` and
``estimatedcruisingrangeprimary.state``, every sample reading ``VALID``.

They are not readings. Each one says whether the sibling value from the SAME
container is to be trusted, which is why publishing them as sensors would be
the wrong answer to a real finding: three entities permanently showing "VALID"
tell nobody anything, and the Scout would still be right that we never used
the datum. Nothing consumed them, so the Scout re-offered all three on every
poll until four issues described them.

So they get a gate instead of an entity, mirroring the ``battery_level_HV``
pair that #1088 already resolves this way: read the state, let it decide
whether the sibling counts, record it where diagnostics can see it, and
consume it.

Two properties matter beyond the happy path:

- **The gate is container-scoped.** ``trunk.state`` speaks for the ``trunk.*``
  container. The tailgate enum ``open_state_tailgate`` is a different data
  point with its own validity, so an INVALID trunk container must not take it
  down with it. Same for the range: ``cruising_range_primary_engine`` is not
  governed by ``estimatedcruisingrangeprimary.state``.
- **Only named, already-mapped containers are consumed.** Consuming every
  ``*.state`` leaf would also swallow the companion of a container we have not
  identified yet, and the no-suppression policy forbids hiding a field we do
  not actually use. An unknown container's companion stays visible to the
  Scout, which is the correct outcome: that one is a genuine discovery.
"""
from __future__ import annotations

from custom_components.vag_connect.cariad.auth._eu_data_act import (
    map_dataset_to_vehicle_data,
)
from custom_components.vag_connect.cariad.models import VehicleData

# The UUID the flattener aliases the generic ``open`` boolean to when it
# belongs to the engine hood (already in the mapper as enginehood.open).
_HOOD_UUID = "8540dd41-556c-3e41-aea9-3e28f8d80a2a"
_TRUNK_UUID = "25ed3407-82de-353e-9f3e-f37952731932"


def _map(fields: dict) -> VehicleData:
    return map_dataset_to_vehicle_data(fields, VehicleData(vin="X"))


# ─────────────────────────────────────────────────────────────────────────────
# The companion is read, recorded and consumed
# ─────────────────────────────────────────────────────────────────────────────


class TestCompanionIsConsumed:
    """The Scout must stop offering these three on every poll."""

    def test_trunk_state_is_consumed(self):
        d = _map({"trunk.state": "VALID", "trunk.open": "true"})
        assert "trunk.state" not in d.raw_unmapped_fields

    def test_enginehood_state_is_consumed(self):
        d = _map({"enginehood.state": "VALID", _HOOD_UUID: "true"})
        assert "enginehood.state" not in d.raw_unmapped_fields

    def test_range_state_is_consumed(self):
        d = _map({
            "estimatedcruisingrangeprimary.state": "VALID",
            "estimatedcruisingrangeprimary.value": "320",
        })
        assert "estimatedcruisingrangeprimary.state" not in d.raw_unmapped_fields

    def test_all_three_reported_together_are_all_consumed(self):
        """The CUPRA Raval report (#1795) carried the range one alongside
        seven bus signals; the VW report (#1797) carried two at once."""
        d = _map({
            "trunk.state": "VALID",
            "enginehood.state": "VALID",
            "estimatedcruisingrangeprimary.state": "VALID",
        })
        assert not [k for k in d.raw_unmapped_fields if k.endswith(".state")]


class TestCompanionIsVisible:
    """Consumed is not the same as hidden — the policy forbids hiding."""

    def test_the_state_is_recorded_for_diagnostics(self):
        d = _map({"trunk.state": "VALID", "trunk.open": "true"})
        assert d.validity_companions["trunk"] == "VALID"

    def test_an_invalid_state_is_recorded_too(self):
        d = _map({"trunk.state": "INVALID", "trunk.open": "true"})
        assert d.validity_companions["trunk"] == "INVALID"

    def test_absent_companions_record_nothing(self):
        d = _map({"trunk.open": "true"})
        assert d.validity_companions == {}

    def test_the_record_survives_into_to_dict(self):
        d = _map({"trunk.state": "VALID"})
        assert d.to_dict()["validity_companions"] == {"trunk": "VALID"}


# ─────────────────────────────────────────────────────────────────────────────
# VALID (or absent) changes nothing
# ─────────────────────────────────────────────────────────────────────────────


class TestValidBehavesAsBefore:
    """Every sample observed so far is VALID, so this is the live path."""

    def test_valid_trunk_open_is_believed(self):
        d = _map({"trunk.state": "VALID", "trunk.open": "true"})
        assert d.trunk_open is True

    def test_valid_trunk_locked_is_believed(self):
        d = _map({"trunk.state": "VALID", "trunk.locked": "true"})
        assert d.trunk_locked is True

    def test_valid_hood_uuid_is_believed(self):
        d = _map({"enginehood.state": "VALID", _HOOD_UUID: "true"})
        assert d.hood_open is True

    def test_valid_range_is_believed(self):
        d = _map({
            "estimatedcruisingrangeprimary.state": "VALID",
            "estimatedcruisingrangeprimary.value": "320",
        })
        assert d.electric_range_km == 320
        assert d.range_km == 320

    def test_no_companion_at_all_is_unchanged(self):
        """A car that never ships the companion must behave exactly as before."""
        d = _map({"trunk.open": "true", "trunk.locked": "true"})
        assert d.trunk_open is True
        assert d.trunk_locked is True

    def test_lowercase_valid_is_accepted(self):
        d = _map({"trunk.state": "valid", "trunk.open": "true"})
        assert d.trunk_open is True

    def test_surrounding_whitespace_is_tolerated(self):
        """The portal pads enum values (the E3V signals arrive as 'iO ')."""
        d = _map({"trunk.state": " VALID ", "trunk.open": "true"})
        assert d.trunk_open is True


# ─────────────────────────────────────────────────────────────────────────────
# A non-VALID companion withholds its own container's reading
# ─────────────────────────────────────────────────────────────────────────────


class TestInvalidWithholdsTheSibling:
    """The portal itself says the value is not valid, so do not publish it."""

    def test_invalid_withholds_trunk_open(self):
        d = _map({"trunk.state": "INVALID", "trunk.open": "true"})
        assert d.trunk_open is None

    def test_invalid_withholds_trunk_locked(self):
        d = _map({"trunk.state": "INVALID", "trunk.locked": "true"})
        assert d.trunk_locked is None

    def test_invalid_withholds_the_trunk_uuid_alias(self):
        """The same container reaches us as a UUID-keyed boolean too."""
        d = _map({"trunk.state": "INVALID", _TRUNK_UUID: "true"})
        assert d.trunk_open is None

    def test_invalid_withholds_the_hood(self):
        d = _map({"enginehood.state": "INVALID", _HOOD_UUID: "true"})
        assert d.hood_open is None

    def test_invalid_withholds_the_range_from_both_destinations(self):
        """The leaf feeds electric_range_km AND the headline range_km."""
        d = _map({
            "estimatedcruisingrangeprimary.state": "INVALID",
            "estimatedcruisingrangeprimary.value": "320",
        })
        assert d.electric_range_km is None
        assert d.range_km is None

    def test_an_unexpected_state_word_also_withholds(self):
        """Anything that is not VALID is not a promise of validity."""
        d = _map({"trunk.state": "NOT_SUPPORTED", "trunk.open": "true"})
        assert d.trunk_open is None

    def test_a_withheld_sibling_is_still_consumed(self):
        """Withholding the value must not hand the leaf back to the Scout."""
        d = _map({"trunk.state": "INVALID", "trunk.open": "true"})
        assert "trunk.open" not in d.raw_unmapped_fields


# ─────────────────────────────────────────────────────────────────────────────
# The gate stays inside its own container
# ─────────────────────────────────────────────────────────────────────────────


class TestGateIsContainerScoped:
    """A different data point has its own validity and must survive."""

    def test_invalid_trunk_does_not_take_down_the_tailgate_enum(self):
        d = _map({
            "trunk.state": "INVALID",
            "open_state_tailgate": "2",   # 2 == open, a separate data point
        })
        assert d.trunk_open is True

    def test_invalid_trunk_does_not_take_down_the_tailgate_lock_enum(self):
        d = _map({"trunk.state": "INVALID", "locked_state_tailgate": "2"})
        assert d.trunk_locked is True

    def test_invalid_hood_does_not_take_down_the_bonnet_enum(self):
        d = _map({
            "enginehood.state": "INVALID",
            "open_state_front_engine_bonnet": "2",
        })
        assert d.hood_open is True

    def test_invalid_range_does_not_take_down_the_canonical_leaf(self):
        d = _map({
            "estimatedcruisingrangeprimary.state": "INVALID",
            "cruising_range_primary_engine": "250",
        })
        assert d.electric_range_km == 250

    def test_invalid_range_does_not_take_down_the_bare_range_leaf(self):
        d = _map({
            "estimatedcruisingrangeprimary.state": "INVALID",
            "range": "250",
        })
        assert d.range_km == 250

    def test_one_invalid_container_does_not_distrust_another(self):
        d = _map({
            "trunk.state": "INVALID",
            "trunk.open": "true",
            "enginehood.state": "VALID",
            _HOOD_UUID: "true",
        })
        assert d.trunk_open is None
        assert d.hood_open is True


# ─────────────────────────────────────────────────────────────────────────────
# The no-suppression policy
# ─────────────────────────────────────────────────────────────────────────────


class TestNoSuppressionPolicy:
    """Scout fields get mapped, never suppressed."""

    def test_an_unknown_containers_companion_stays_visible(self):
        """A container we have not identified is a genuine discovery."""
        d = _map({"somethingbrandnew.state": "VALID"})
        assert d.raw_unmapped_fields.get("somethingbrandnew.state") is not None

    def test_an_unknown_containers_companion_is_not_recorded_as_handled(self):
        d = _map({"somethingbrandnew.state": "VALID"})
        assert "somethingbrandnew" not in d.validity_companions

    def test_a_bare_state_leaf_is_left_alone(self):
        """Only the dotted container form is a companion."""
        d = _map({"state": "VALID"})
        assert d.validity_companions == {}
