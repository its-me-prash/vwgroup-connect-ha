"""v4.7.11 (departure-timer-rich-setter, myskoda #631/#640).

Covers the rich optional fields added to ``set_departure_timer``:
charging / climatisation / target_soc_pct / one_off_day.

- CARIAD (vw_eu) sends the extras ONLY when the entry is in the test cohort;
  without the cohort the request body is byte-identical to what shipped before
  (the BFF write field names are inferred from the read DTO, so a wrong name
  must never reach a real user's car).
- RECURRING vs ONE_OFF body shape on the CARIAD client.
- vw_na and porsche accept the new kwargs (uniform cross-brand signature) but
  never add the guessed fields to their bodies.
- Škoda stays READ-ONLY: no departure-timer setter exists (no grounded write
  route), so the SkodaClient exposes no ``command_set_departure_timer``.
- The service schema accepts valid rich values and rejects an out-of-range SoC.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
import voluptuous as vol


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _vw_eu(cohort: bool):
    """VWEUClient stub: only the attrs command_set_departure_timer touches."""
    from custom_components.vag_connect.cariad.api.vw_eu import VWEUClient

    client = VWEUClient.__new__(VWEUClient)
    client._test_cohort = cohort
    client._base_for_vin = lambda vin: "https://bff.example.test"  # type: ignore[method-assign]
    client._post = AsyncMock()  # type: ignore[method-assign]
    return client


def _posted_body(client) -> dict:
    """The ``json=`` kwarg of the single _post call."""
    assert client._post.await_count == 1
    return client._post.await_args.kwargs["json"]


# ---------------------------------------------------------------------------
# CARIAD (vw_eu) — cohort gating + byte-identical non-cohort body
# ---------------------------------------------------------------------------

class TestVwEuCohortGating:
    def test_non_cohort_body_byte_identical_to_today(self):
        """Rich fields supplied but cohort off → body == the pre-4.7.11 body."""
        rich = _vw_eu(cohort=False)
        asyncio.run(rich.command_set_departure_timer(
            "VIN0000000000001", 1, True, "07:30",
            recurring_on=["monday", "friday"],
            charging=True, climatisation=True, target_soc_pct=80,
            one_off_day="2026-09-20",
        ))
        got = _posted_body(rich)

        # Reproduce exactly what the old signature would have produced.
        expected = {
            "id": 1,
            "enabled": True,
            "departureTime": {"time": "07:30"},
            "recurringOn": ["MONDAY", "FRIDAY"],
            "type": "RECURRING",
        }
        assert got == expected
        for k in ("charging", "climatisation",
                  "targetBatteryStateOfChargeInPercent", "singleTimer"):
            assert k not in got

    def test_cohort_recurring_includes_rich_fields(self):
        client = _vw_eu(cohort=True)
        asyncio.run(client.command_set_departure_timer(
            "VIN0000000000002", 2, True, "06:00",
            recurring_on=["MONDAY"],
            charging=True, climatisation=False, target_soc_pct=90,
        ))
        got = _posted_body(client)
        assert got["type"] == "RECURRING"
        assert got["recurringOn"] == ["MONDAY"]
        assert got["charging"] is True
        assert got["climatisation"] is False
        assert got["targetBatteryStateOfChargeInPercent"] == 90
        assert "singleTimer" not in got

    def test_cohort_one_off_overrides_recurring(self):
        """one_off_day → type ONE_OFF and any recurring marker is dropped."""
        client = _vw_eu(cohort=True)
        asyncio.run(client.command_set_departure_timer(
            "VIN0000000000003", 3, True, "05:15",
            recurring_on=["TUESDAY"],  # should be superseded by the one-off day
            one_off_day="2026-12-24",
        ))
        got = _posted_body(client)
        assert got["type"] == "ONE_OFF"
        assert got["singleTimer"] == {"startDateTime": "2026-12-24"}
        assert "recurringOn" not in got

    def test_cohort_no_rich_args_matches_plain_body(self):
        """Cohort on but no extras passed → still the plain body."""
        client = _vw_eu(cohort=True)
        asyncio.run(client.command_set_departure_timer(
            "VIN0000000000004", 1, False, None,
        ))
        assert _posted_body(client) == {"id": 1, "enabled": False}


# ---------------------------------------------------------------------------
# vw_na / porsche — accept kwargs, never emit the guessed fields
# ---------------------------------------------------------------------------

class TestOtherBrandsIgnoreRich:
    def test_vw_na_accepts_and_ignores_rich(self):
        from custom_components.vag_connect.cariad.api.vw_na import VWNAClient

        client = VWNAClient.__new__(VWNAClient)
        client._base = "https://na.example.test"
        client._vin_to_uuid = {"VWNA0000000000001": "uuid-na"}
        client._carnet_command = AsyncMock()  # type: ignore[method-assign]

        asyncio.run(client.command_set_departure_timer(
            "VWNA0000000000001", 1, True, "07:30",
            charging=True, climatisation=True, target_soc_pct=70,
            one_off_day="2026-09-20",
        ))
        assert client._carnet_command.await_count == 1
        body = client._carnet_command.await_args.kwargs["json"]
        assert body == {"id": 1, "enabled": True,
                        "departureTime": {"time": "07:30"}}
        for k in ("charging", "climatisation",
                  "targetBatteryStateOfChargeInPercent", "singleTimer"):
            assert k not in body

    def test_porsche_accepts_and_ignores_rich(self):
        from custom_components.vag_connect.cariad.api.porsche import PorscheClient

        client = PorscheClient.__new__(PorscheClient)
        client._command = AsyncMock()  # type: ignore[method-assign]
        # My Porsche 21.26.46: DEPARTURES_EDIT sends the whole DEPARTURES list
        # back with one entry changed (see test_porsche_paket_b.py).
        entry = {"id": 1, "isEnabled": False,
                 "triggerDateTimeWithOffset": "2026-09-20T07:00:00+02:00",
                 "chargingOption": {"type": "ENABLED"},
                 "isClimatizationEnabled": False}
        client._get = AsyncMock(return_value={"measurements": [  # type: ignore[method-assign]
            {"key": "DEPARTURES", "status": {"isEnabled": True},
             "value": {"list": [entry]}},
        ]})

        asyncio.run(client.command_set_departure_timer(
            "PORS0000000000001", 1, True, "08:00",
            charging=True, target_soc_pct=100, one_off_day="2026-09-20",
        ))
        assert client._command.await_count == 1
        # _command(vin, key, payload)
        payload = client._command.await_args.args[2]
        assert payload == {"spin": None, "list": [{
            "id": 1, "isEnabled": True,
            "triggerDateTimeWithOffset": "2026-09-20T08:00:00+02:00",
            "chargingOption": {"type": "ENABLED"},
            "isClimatizationEnabled": False,
        }]}
        for k in ("charging", "climatisation", "targetBatteryStateOfChargeInPercent"):
            assert k not in payload["list"][0]


# ---------------------------------------------------------------------------
# Škoda stays read-only (no grounded write route → no setter)
# ---------------------------------------------------------------------------

class TestSkodaReadOnly:
    def test_skoda_has_no_departure_timer_setter(self):
        from custom_components.vag_connect.cariad.api.skoda import SkodaClient

        assert not hasattr(SkodaClient, "command_set_departure_timer")
        # The read side is present and untouched.
        assert hasattr(SkodaClient, "get_departure_timers")


# ---------------------------------------------------------------------------
# service schema accepts / rejects
# ---------------------------------------------------------------------------

def _departure_schema() -> vol.Schema:
    """Pull the real set_departure_timer vol schema out of _register_services."""
    from custom_components.vag_connect import _register_services

    captured: dict = {}

    def _register(domain, name, handler, schema=None, supports_response=None):
        captured[name] = schema

    hass = MagicMock()
    hass.services.async_register = MagicMock(side_effect=_register)
    hass.services.has_service = MagicMock(return_value=False)
    _register_services(hass)
    schema = captured["set_departure_timer"]
    assert schema is not None
    return schema


class TestServiceSchema:
    def test_accepts_full_rich_call(self):
        schema = _departure_schema()
        out = schema({
            "vin": "VIN0000000000001",
            "timer_id": 1,
            "enabled": True,
            "departure_time": "07:30",
            "recurring_on": ["MONDAY", "FRIDAY"],
            "charging": True,
            "climatisation": False,
            "target_soc_pct": 80,
            "one_off_day": "2026-09-20",
        })
        assert out["target_soc_pct"] == 80
        assert out["charging"] is True

    def test_rejects_out_of_range_target_soc(self):
        schema = _departure_schema()
        with pytest.raises(vol.Invalid):
            schema({
                "vin": "VIN0000000000001",
                "timer_id": 1,
                "enabled": True,
                "target_soc_pct": 5,  # below the 10 minimum
            })

    def test_rejects_bad_timer_id(self):
        schema = _departure_schema()
        with pytest.raises(vol.Invalid):
            schema({
                "vin": "VIN0000000000001",
                "timer_id": 4,  # only 1..3 allowed
                "enabled": True,
            })

    def test_minimal_call_still_valid(self):
        schema = _departure_schema()
        out = schema({"vin": "V", "timer_id": 2, "enabled": False})
        assert out["timer_id"] == 2
        assert "charging" not in out
