# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""CARIAD-BFF dashboard warning lights — dict-wrapper firmware.

Current firmware (Audi Q6 e-tron PPE, audi_na) ships
``vehicleHealthWarnings.warningLights.value`` as a DICT
``{"warningLights": [...], "campaigns": [...]}`` and keys each item's class under
``category`` / ``type`` (e.g. "LIGHTING" / "stoWarning") rather than the old
``warningType``. The previous ``isinstance(list)`` + ``warningType`` parser dropped
every warning on this firmware — a Q6 with 4 real active faults reported
``warning_count=0``. These tests pin the dict-unwrap, the class-token fallback, the
campaigns surfacing, and the still-working old bare-list shape.
"""
from __future__ import annotations

from custom_components.vag_connect.cariad.api.vw_eu import VWEUClient


def _parse(raw: dict):
    client = VWEUClient.__new__(VWEUClient)
    client._vehicle_metadata = {}
    return client._parse_status("VINX", raw, parking={})


# Real shape from the Audi Q6 e-tron PPE diagnostic (4 active warnings + 1 campaign).
_Q6_VALUE = {
    "warningLights": [
        {"text": "Vehicle lights: fault. Please contact workshop",
         "category": "LIGHTING", "type": "stoWarning", "messageId": "msgA317"},
        {"text": "Rear right turn signal defective",
         "category": "LIGHTING", "type": "stoWarning", "messageId": "msgA321"},
        {"text": "Number plate light defective",
         "category": "LIGHTING", "type": "stoWarning", "messageId": "msgA32A"},
        {"text": "Rear light on boot lid defective",
         "category": "LIGHTING", "type": "stoWarning", "messageId": "msgA35C"},
    ],
    "campaigns": [
        {"eventId": "06K2", "text": "Combined software update KD2* (03.11.00/C)",
         "type": "customerServiceCampaign", "timeOfOccurrence": "2026-06-19T00:00:00Z"},
    ],
}


def _raw(value):
    return {"vehicleHealthWarnings": {"warningLights": {"value": value}}}


class TestDictWrapperFirmware:
    def test_four_warnings_are_counted_not_dropped(self) -> None:
        d = _parse(_raw(_Q6_VALUE))
        assert d.warning_count == 4
        assert d.warning_active is True

    def test_warning_messages_populated_from_text(self) -> None:
        d = _parse(_raw(_Q6_VALUE))
        assert d.warning_messages
        assert "Number plate light defective" in d.warning_messages

    def test_service_campaigns_surfaced(self) -> None:
        d = _parse(_raw(_Q6_VALUE))
        assert d.service_campaign_count == 1
        assert "Combined software update" in (d.service_campaigns or "")

    def test_empty_dict_is_a_true_negative_not_unknown(self) -> None:
        # A healthy car answers the job with an empty wrapper.
        d = _parse(_raw({"warningLights": [], "campaigns": []}))
        assert d.warning_active is False
        assert d.warning_count == 0


class TestOldBareListFirmwareStillWorks:
    def test_legacy_warningtype_list_still_classified(self) -> None:
        raw = _raw([{"warningType": "OIL_LEVEL", "text": "Oil low"}])
        d = _parse(raw)
        assert d.warning_count == 1
        assert d.warning_active is True
        assert d.warning_oil is True
        assert "Oil low" in (d.warning_messages or "")


class TestChargingScenarioOnBff:
    def test_charging_scenario_read_from_bff(self) -> None:
        raw = {"charging": {"chargingStatus": {"value": {"chargingScenario": "off"}}}}
        d = _parse(raw)
        assert d.charging_scenario == "OFF"


class TestTyreWarningFromText:
    """warning_tyre must not depend on the class word alone.

    Real Audi shape: the class is the generic ``stoWarning`` and only the text says
    it is a tyre pressure warning ("Loss of pressure (front left)! Please check all
    tyres ..."). No language-independent code is known, so the text is matched with
    narrow tyre/tire/Reifen terms (EN/DE); other account languages stay unrecognised.
    """

    @staticmethod
    def _one(text: str, **cls: str):
        return _parse(_raw({"warningLights": [{"text": text, **cls}], "campaigns": []}))

    def test_audi_stowarning_tyre_text_sets_flag(self) -> None:
        d = self._one(
            "Loss of pressure (front left)! Please check all tyres and store "
            "pressures in MMI",
            type="stoWarning",
        )
        assert d.warning_active is True
        assert d.warning_tyre is True

    def test_us_spelling_and_german_text(self) -> None:
        assert self._one("Check tire pressure", type="stoWarning").warning_tyre is True
        assert self._one(
            "Reifendruck prüfen!", category="stoWarning"
        ).warning_tyre is True
        assert self._one("Reifenpanne", type="stoWarning").warning_tyre is True

    def test_other_stowarning_cases_are_not_tyre(self) -> None:
        for text in (
            "Check towing bracket",
            "Oil pressure too low. Stop vehicle",
            "Please check the entire system",
            "Vehicle lights: fault. Please contact workshop",
        ):
            d = self._one(text, type="stoWarning")
            assert d.warning_active is True
            assert d.warning_tyre is False, text

    def test_german_words_that_merely_contain_reifen_are_not_tyre(self) -> None:
        # Lane-keeping and hands-on texts must not raise the tyre warning.
        for text in (
            "Fahrstreifen verlassen",
            "Spurhalteassistent: Seitenstreifen erkannt",
            "Bitte Hand ans Lenkrad greifen",
            "Assistent ergreift keine Massnahme",
        ):
            assert self._one(text, type="stoWarning").warning_tyre is False, text

    def test_text_under_message_key_is_read_too(self) -> None:
        d = _parse(_raw({"warningLights": [{"message": "Check tyre pressure", "type": "stoWarning"}],
                         "campaigns": []}))
        assert d.warning_tyre is True

    def test_only_the_tyre_entry_of_several_counts(self) -> None:
        d = _parse(_raw({"warningLights": [
            {"text": "Check towing bracket", "type": "stoWarning"},
            {"text": "Reifendruck zu niedrig", "type": "stoWarning"},
        ], "campaigns": []}))
        assert d.warning_tyre is True
        d = _parse(_raw({"warningLights": [
            {"text": "Check towing bracket", "type": "stoWarning"},
            {"type": "stoWarning"},
        ], "campaigns": []}))
        assert d.warning_tyre is False

    def test_class_word_still_works_without_text(self) -> None:
        assert self._one("", warningType="TIRE_PRESSURE").warning_tyre is True

    def test_healthy_car_stays_false(self) -> None:
        d = _parse(_raw({"warningLights": [], "campaigns": []}))
        assert d.warning_tyre is False
