# Copyright 2026 Prash Balan (@its-me-prash) - Apache License 2.0
# SPDX-License-Identifier: Apache-2.0
"""Tests for v2.8.0 quick win C: brake-service + preferred-workshop sensors.

Coverage:

- ``days_or_date_to_iso`` accepts int day-offsets, EU dd.mm.yyyy, ISO 8601;
  rejects garbage / out-of-range values.
- ``normalize_workshop_string`` collapses whitespace.
- ``compose_workshop_address`` composes the typical multi-part address shape.
- ``workshop_phone_from_contact`` finds the phone in the alternatives.
- All 6 new sensor keys are listed in ``sensor._DATA_PRESENT_REQUIRED`` so
  non-supporting brands do not get phantom Unbekannt entities.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest


pytestmark = pytest.mark.ha_required


def _today_utc_midnight() -> datetime:
    return datetime.now(tz=timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0,
    )


class TestDaysOrDateToIso:
    """``cariad._util.days_or_date_to_iso``."""

    def test_int_day_offset_returns_today_plus_days_midnight_utc(self) -> None:
        from custom_components.vag_connect.cariad._util import days_or_date_to_iso

        result = days_or_date_to_iso(30)

        assert result is not None
        parsed = datetime.fromisoformat(result)
        expected = _today_utc_midnight() + timedelta(days=30)
        assert parsed == expected

    def test_zero_days_returns_today_midnight(self) -> None:
        from custom_components.vag_connect.cariad._util import days_or_date_to_iso

        result = days_or_date_to_iso(0)
        assert result is not None
        assert datetime.fromisoformat(result) == _today_utc_midnight()

    def test_negative_days_returns_past(self) -> None:
        from custom_components.vag_connect.cariad._util import days_or_date_to_iso

        result = days_or_date_to_iso(-7)
        assert result is not None
        assert datetime.fromisoformat(result) < _today_utc_midnight()

    def test_numeric_string_treated_as_int(self) -> None:
        from custom_components.vag_connect.cariad._util import days_or_date_to_iso

        result = days_or_date_to_iso("365")
        assert result is not None
        parsed = datetime.fromisoformat(result)
        expected = _today_utc_midnight() + timedelta(days=365)
        assert parsed == expected

    def test_eu_date_format(self) -> None:
        from custom_components.vag_connect.cariad._util import days_or_date_to_iso

        result = days_or_date_to_iso("15.06.2027")
        assert result is not None
        parsed = datetime.fromisoformat(result)
        assert parsed.year == 2027
        assert parsed.month == 6
        assert parsed.day == 15
        assert parsed.tzinfo is not None

    def test_iso_date_format(self) -> None:
        from custom_components.vag_connect.cariad._util import days_or_date_to_iso

        result = days_or_date_to_iso("2027-06-15")
        assert result is not None
        parsed = datetime.fromisoformat(result)
        assert parsed.year == 2027
        assert parsed.month == 6

    def test_iso_datetime_with_z(self) -> None:
        from custom_components.vag_connect.cariad._util import days_or_date_to_iso

        result = days_or_date_to_iso("2027-06-15T14:30:00Z")
        assert result is not None
        parsed = datetime.fromisoformat(result)
        assert parsed.hour == 14
        assert parsed.tzinfo is not None

    def test_returns_none_for_none(self) -> None:
        from custom_components.vag_connect.cariad._util import days_or_date_to_iso

        assert days_or_date_to_iso(None) is None

    def test_returns_none_for_empty_string(self) -> None:
        from custom_components.vag_connect.cariad._util import days_or_date_to_iso

        assert days_or_date_to_iso("") is None
        assert days_or_date_to_iso("   ") is None

    def test_returns_none_for_int_outside_sanity_bound(self) -> None:
        from custom_components.vag_connect.cariad._util import days_or_date_to_iso

        # Backend ships INT_MIN during error-envelope conditions.
        assert days_or_date_to_iso(-2_147_483_648) is None
        assert days_or_date_to_iso(99_999_999) is None

    def test_returns_none_for_bool(self) -> None:
        from custom_components.vag_connect.cariad._util import days_or_date_to_iso

        assert days_or_date_to_iso(True) is None
        assert days_or_date_to_iso(False) is None

    def test_returns_none_for_garbage(self) -> None:
        from custom_components.vag_connect.cariad._util import days_or_date_to_iso

        assert days_or_date_to_iso("not a date") is None
        assert days_or_date_to_iso("99.99.9999") is None
        assert days_or_date_to_iso([2027, 6, 15]) is None


class TestNormalizeWorkshopString:
    def test_collapses_double_spaces(self) -> None:
        from custom_components.vag_connect.cariad._util import normalize_workshop_string

        assert normalize_workshop_string("Foo   Bar") == "Foo Bar"

    def test_strips_newlines(self) -> None:
        from custom_components.vag_connect.cariad._util import normalize_workshop_string

        assert normalize_workshop_string("Foo\nBar\t  Baz") == "Foo Bar Baz"

    def test_returns_none_for_empty(self) -> None:
        from custom_components.vag_connect.cariad._util import normalize_workshop_string

        assert normalize_workshop_string("") is None
        assert normalize_workshop_string("   ") is None

    def test_returns_none_for_non_string(self) -> None:
        from custom_components.vag_connect.cariad._util import normalize_workshop_string

        assert normalize_workshop_string(None) is None
        assert normalize_workshop_string(42) is None


class TestComposeWorkshopAddress:
    def test_composes_typical_shape(self) -> None:
        from custom_components.vag_connect.cariad._util import compose_workshop_address

        addr = compose_workshop_address({
            "street": "Bünzweg",
            "houseNumber": "16",
            "postalCode": "5504",
            "city": "Othmarsingen",
            "country": "CH",
        })
        assert addr == "Bünzweg 16, 5504 Othmarsingen, CH"

    def test_uses_formatted_address_when_present(self) -> None:
        from custom_components.vag_connect.cariad._util import compose_workshop_address

        addr = compose_workshop_address({
            "formattedAddress": "  Foo  Garage,  Bar  Strasse  1, 8000 Zürich  ",
            "street": "ignored",
            "city": "ignored",
        })
        assert addr == "Foo Garage, Bar Strasse 1, 8000 Zürich"

    def test_returns_none_when_empty(self) -> None:
        from custom_components.vag_connect.cariad._util import compose_workshop_address

        assert compose_workshop_address({}) is None
        assert compose_workshop_address(None) is None

    def test_partial_fields_still_compose(self) -> None:
        from custom_components.vag_connect.cariad._util import compose_workshop_address

        addr = compose_workshop_address({"city": "Zürich", "country": "CH"})
        assert addr == "Zürich, CH"


class TestWorkshopPhoneFromContact:
    def test_finds_phone_key(self) -> None:
        from custom_components.vag_connect.cariad._util import workshop_phone_from_contact

        assert workshop_phone_from_contact({"phone": "+41 62 889 60 80"}) == "+41 62 889 60 80"

    def test_alternate_phone_keys(self) -> None:
        from custom_components.vag_connect.cariad._util import workshop_phone_from_contact

        assert workshop_phone_from_contact({"phoneNumber": "+49 30 12345"}) == "+49 30 12345"
        assert workshop_phone_from_contact({"telephone": "+43 1 234"}) == "+43 1 234"
        assert workshop_phone_from_contact({"tel": "+1 555 1234"}) == "+1 555 1234"

    def test_phones_list_of_strings(self) -> None:
        from custom_components.vag_connect.cariad._util import workshop_phone_from_contact

        assert workshop_phone_from_contact({"phones": ["+41 22 111 22 33", "+41 22 444"]}) == "+41 22 111 22 33"

    def test_phones_list_of_dicts(self) -> None:
        from custom_components.vag_connect.cariad._util import workshop_phone_from_contact

        assert workshop_phone_from_contact({"phones": [{"number": "+41 1 999"}]}) == "+41 1 999"

    def test_returns_none_on_miss(self) -> None:
        from custom_components.vag_connect.cariad._util import workshop_phone_from_contact

        assert workshop_phone_from_contact({}) is None
        assert workshop_phone_from_contact(None) is None
        assert workshop_phone_from_contact({"email": "foo@bar"}) is None


class TestSensorPhantomGate:
    def test_all_six_new_keys_listed_in_data_present_required(self) -> None:
        from custom_components.vag_connect.sensor import _DATA_PRESENT_REQUIRED

        expected = {
            "brake_fluid_change_due_at",
            "brake_pads_front_inspection_due_at",
            "brake_pads_rear_inspection_due_at",
            "preferred_workshop_name",
            "preferred_workshop_address",
            "preferred_workshop_phone",
        }
        assert expected.issubset(_DATA_PRESENT_REQUIRED)


class TestVehicleDataFields:
    def test_default_to_none(self) -> None:
        from custom_components.vag_connect.cariad.models import VehicleData

        d = VehicleData(vin="TEST_VIN")
        assert d.brake_fluid_change_due_at is None
        assert d.brake_pads_front_inspection_due_at is None
        assert d.brake_pads_rear_inspection_due_at is None
        assert d.preferred_workshop_name is None
        assert d.preferred_workshop_address is None
        assert d.preferred_workshop_phone is None
