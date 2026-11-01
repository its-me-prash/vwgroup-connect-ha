"""#1739 (@awood-ops) — the plug label is derived from the boolean, one way only.

On EU Data Act portal entries the portal never delivers the ``plug_state``
label, only the boolean ``plug_connected``. His Charging Port sensor therefore
held no value while the cable was demonstrably in: from the same poll,
``charging_status`` read ``CHARGING_HV_BATTERY`` and the
``charging_cable_connected`` binary sensor read on. He proposed deriving the
label from the boolean, and offered to test it.

The derivation is deliberately **asymmetric**, and that is what these tests pin.
``plug_connected`` has three producers:

1. the plug enum itself — then ``plug_state`` is already set and nothing is
   derived;
2. a German-language negation heuristic over a different signal field;
3. an inference from an active charging session.

Charging proves the cable is in. *Not* charging proves nothing, and a missing or
re-worded text makes the heuristic return False just as readily as a real
disconnection does. Publishing ``disconnected`` from such a False would be the
#1403 defect again — a connected plug reported as a confident False — and that
comment still stands: a definite wrong answer is worse than an absent one.

So: True derives ``connected``; False and None derive nothing, and Home
Assistant renders the absent value as ``unknown``, which is the honest state for
"we cannot tell".
"""
from __future__ import annotations

import asyncio
import threading
from unittest.mock import AsyncMock, MagicMock

from custom_components.vag_connect.coordinator import VagConnectCoordinator


def _make_coord():
    coord = VagConnectCoordinator.__new__(VagConnectCoordinator)
    coord.hass = MagicMock()
    coord.hass.async_add_executor_job = AsyncMock(return_value=None)
    coord.entry = MagicMock()
    coord.entry.data = {"brand": "volkswagen", "username": "t@t.com", "password": "x",
                        "spin": "", "update_interval": 300}
    coord._vehicles_lock = threading.Lock()
    coord._cariad_client = MagicMock()
    coord._cariad_client._image_data = {}
    coord.vehicle_static_info = {}
    coord._was_available = True
    coord.data = None
    return coord


def _enrich(**fields):
    """Run the real _enrich over a minimal vehicle dict and return it."""
    coord = _make_coord()
    data = {"vin": "V1", "latitude": None, "longitude": None}
    data.update(fields)
    return asyncio.run(coord._enrich(data))


class TestTheLabelIsDerivedWhenTheBooleanProvesTheCableIsIn:
    def test_true_derives_connected(self) -> None:
        out = _enrich(plug_state=None, plug_connected=True)
        assert out.get("plug_state") == "connected"

    def test_the_derived_label_is_a_declared_option(self) -> None:
        """It has to survive normalize_enum_states, not merely be assigned."""
        from custom_components.vag_connect.sensor import SENSOR_DESCRIPTIONS

        desc = next(d for d in SENSOR_DESCRIPTIONS
                    if getattr(d, "key", None) == "plug_state")
        out = _enrich(plug_state=None, plug_connected=True)
        assert out.get("plug_state") in desc.options

    def test_the_provenance_says_it_was_derived(self) -> None:
        """Triage must not mistake the derived label for a portal reading."""
        out = _enrich(plug_state=None, plug_connected=True, field_sources={})
        src = out.get("field_sources") or {}
        assert src.get("plug_state") == "derived:plug_connected"

    def test_a_missing_provenance_map_is_not_an_error(self) -> None:
        """Control: most call sites pass no field_sources at all."""
        out = _enrich(plug_state=None, plug_connected=True)
        assert out.get("plug_state") == "connected"


class TestTheOtherDirectionStaysSilent:
    """The whole point of the fix. If these ever pass as 'disconnected',
    #1403 is back."""

    def test_false_derives_nothing(self) -> None:
        out = _enrich(plug_state=None, plug_connected=False)
        assert out.get("plug_state") is None

    def test_none_derives_nothing(self) -> None:
        out = _enrich(plug_state=None, plug_connected=None)
        assert out.get("plug_state") is None

    def test_absent_boolean_derives_nothing(self) -> None:
        out = _enrich(plug_state=None)
        assert out.get("plug_state") is None

    def test_false_leaves_no_provenance_either(self) -> None:
        out = _enrich(plug_state=None, plug_connected=False, field_sources={})
        assert "plug_state" not in (out.get("field_sources") or {})


class TestOnlyARealBooleanCounts:
    """``is True``, not truthiness: the boolean is the contract."""

    def test_the_string_one_does_not_derive(self) -> None:
        out = _enrich(plug_state=None, plug_connected="1")
        assert out.get("plug_state") is None

    def test_the_integer_one_does_not_derive(self) -> None:
        out = _enrich(plug_state=None, plug_connected=1)
        assert out.get("plug_state") is None

    def test_the_string_true_does_not_derive(self) -> None:
        out = _enrich(plug_state=None, plug_connected="true")
        assert out.get("plug_state") is None


class TestARealReadingIsNeverOverwritten:
    """Controls: where the portal did deliver a label, the label wins."""

    def test_a_real_disconnected_survives_a_true_boolean(self) -> None:
        out = _enrich(plug_state="disconnected", plug_connected=True)
        assert out.get("plug_state") == "disconnected"

    def test_a_real_connected_survives(self) -> None:
        out = _enrich(plug_state="connected", plug_connected=False)
        assert out.get("plug_state") == "connected"

    def test_a_real_label_keeps_its_own_provenance(self) -> None:
        out = _enrich(plug_state="disconnected", plug_connected=True,
                      field_sources={"plug_state": "eu_data_act"})
        assert (out.get("field_sources") or {}).get("plug_state") == "eu_data_act"

    def test_a_sentinel_label_still_becomes_none_and_then_derives(self) -> None:
        """An 'invalid' sentinel is normalised to None (#1055). Whether the
        derivation then fills it depends on the order of the two steps, so this
        pins the order rather than leaving it to chance: normalisation first,
        derivation second, because a sentinel means "no reading" and the boolean
        may still prove the cable is in.
        """
        out = _enrich(plug_state="PLUG_CONNECTION_STATE_INVALID", plug_connected=True)
        assert out.get("plug_state") == "connected"
