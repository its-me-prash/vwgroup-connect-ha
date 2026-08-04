# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""An identity token is not vehicle data and must not enter discovery.

The portal export carries ``idp_idt``, a token identifying the ACCOUNT HOLDER
rather than anything about the car. It reached the Vehicle Data Scout as an
unmapped field, and only the JWT masker kept its value out of a public issue.

Everywhere else the rule is that a discovered field stays visible until it is
mapped, because a hidden field is a field nobody ever maps. This is the single
exception, and it exists because the alternative is worse: leaving the name in
discovery is a promise to map it, and mapping it would write a token that
identifies a real person into the entity state, and from there into every
backup and every diagnostics download someone attaches to a bug report.

The two properties that make this an exception rather than a hole: it is scoped
to an explicit list, and it is logged rather than silent.
"""
from __future__ import annotations

import logging

from custom_components.vag_connect.cariad.auth._eu_data_act import (
    _CREDENTIAL_FIELDS,
    _walk_fields,
    map_dataset_to_vehicle_data,
)


def _dataset(entries: list[tuple[str, str]]) -> dict:
    return {"data": [{"dataFieldName": n, "value": v} for n, v in entries]}


def _parse(entries: list[tuple[str, str]]):
    from custom_components.vag_connect.cariad.models import VehicleData

    ts: dict = {}
    syn: dict = {}
    fields = _walk_fields(_dataset(entries), ts, syn)
    d = VehicleData(vin="WVWZZZ000000TEST1")
    return map_dataset_to_vehicle_data(fields, d, ts, syn)


class TestTheTokenNeverReachesDiscovery:
    def test_idp_idt_is_absent_from_raw_fields(self) -> None:
        d = _parse([
            ("car_captured_time", "2026-08-04T20:00:00Z"),
            ("idp_idt", "eyJhbGciOiJSUzI1NiJ9.eyJzdWIiOiJ4In0.sig"),
            ("some_unknown_reading", "17"),
        ])
        raw = d.raw_unmapped_fields or {}
        assert not any(k.rsplit(".", 1)[-1] == "idp_idt" for k in raw), raw

    def test_the_token_value_appears_nowhere_in_the_result(self) -> None:
        """Not in the raw fields, not carried into some other attribute."""
        secret = "eyJhbGciOiJSUzI1NiJ9.eyJzdWIiOiJzZWNyZXQifQ.signature"
        d = _parse([
            ("car_captured_time", "2026-08-04T20:00:00Z"),
            ("idp_idt", secret),
        ])
        assert secret not in repr(d.__dict__)

    def test_ordinary_unknown_fields_are_still_surfaced(self) -> None:
        """The guard rail: this must stay one named exception, not a habit of
        hiding things the parser does not understand."""
        d = _parse([
            ("car_captured_time", "2026-08-04T20:00:00Z"),
            ("idp_idt", "eyJhbGciOiJSUzI1NiJ9.eyJzdWIiOiJ4In0.sig"),
            ("brand_new_thing", "42"),
        ])
        raw = d.raw_unmapped_fields or {}
        assert any(k.rsplit(".", 1)[-1] == "brand_new_thing" for k in raw), raw

    def test_withholding_is_logged_not_silent(self, caplog) -> None:
        with caplog.at_level(logging.DEBUG):
            _parse([
                ("car_captured_time", "2026-08-04T20:00:00Z"),
                ("idp_idt", "eyJhbGciOiJSUzI1NiJ9.eyJzdWIiOiJ4In0.sig"),
            ])
        assert any("withholding" in r.message.lower() or "withholding" in r.getMessage().lower()
                   for r in caplog.records), [r.getMessage() for r in caplog.records]

    def test_the_exception_list_is_narrow(self) -> None:
        """If this ever grows, it should be a decision someone made on purpose."""
        assert _CREDENTIAL_FIELDS == frozenset({"idp_idt"})
