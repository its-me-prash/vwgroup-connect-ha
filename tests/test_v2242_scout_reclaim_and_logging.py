# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""v2.24.2 — two chronic Scout re-reporters, and four silent outcomes.

Both parser defects have the same shape: the value IS consumed and mapped, but
the bookkeeping never records that, so the Scout files the identical one-row
report on every single poll. The reporter cannot act on it and we cannot either.

1. #959 / #960 / #961 — three people filed the same bare ``open`` row within a
   day. The UUID-alias branch of ``_walk_fields`` emitted the mapped alias but,
   unlike the container-qualified branch right below it, recorded no synonym
   pair, so ``first()``'s synonym-collapse never reclaimed the bare leaf. The
   row is unactionable by design too: around ten opening UUIDs share that leaf,
   so nobody can say which one it belongs to. Suppressing it is NOT the fix and
   is forbidden by the project's no-suppression policy — it needed reclaiming.

2. #963 — ``value is not None and _value_type_ok(...)`` short-circuits whenever
   the physical value is absent, so the companion ``value_type`` is never
   consumed. Cars that ship the companion WITHOUT the reading are precisely the
   ones affected, so they got the report every poll, forever.
"""
from __future__ import annotations

from custom_components.vag_connect.cariad.models import VehicleData


def _map(payload: dict) -> VehicleData:
    from custom_components.vag_connect.cariad.auth._eu_data_act import (
        map_dataset_to_vehicle_data,
    )
    return map_dataset_to_vehicle_data(payload, VehicleData(vin="X"))


# ── 1. the UUID alias reclaims its bare leaf ───────────────────────────────


class TestUuidAliasSynonym:
    def test_the_alias_branch_records_a_synonym_pair(self) -> None:
        """The whole defect, against a real payload: a generic ``open`` leaf
        carrying a mapped UUID in ``key`` must register the two names as
        synonyms, so first() can reclaim the bare leaf once it consumes the
        alias. Without the pair the leaf stays in raw_unmapped_fields forever."""
        from custom_components.vag_connect.cariad.auth._eu_data_act import (
            _walk_fields,
        )

        trunk_open = "25ed3407-82de-353e-9f3e-f37952731932"
        syn: dict[str, set[str]] = {}
        fields = _walk_fields(
            {"data": [{"dataFieldName": "open", "key": trunk_open, "value": "true"}]},
            None,
            syn,
        )
        # both spellings are emitted (unchanged behaviour)
        assert fields.get(trunk_open) == "true"
        # ...and they now know about each other (the fix)
        assert trunk_open in syn.get("open", set()), (
            "the bare leaf has no route back to its UUID, so it is never "
            "reclaimed and re-reports to the Scout on every poll (#959)"
        )
        assert "open" in syn.get(trunk_open, set()), "pair is not bidirectional"

    def test_an_unmapped_uuid_is_not_aliased(self) -> None:
        """The v2.17.5 guard: aliasing every generic point flooded the Scout
        with dozens of unmapped UUID rows. Only mapped UUIDs get the treatment."""
        from custom_components.vag_connect.cariad.auth._eu_data_act import (
            _walk_fields,
        )

        syn: dict[str, set[str]] = {}
        _walk_fields(
            {"data": [{
                "dataFieldName": "open",
                "key": "00000000-dead-beef-0000-000000000000",
                "value": "true",
            }]},
            None,
            syn,
        )
        assert not syn, "an unmapped UUID was aliased (2.17.4 regression)"

    def test_the_container_qualified_pair_still_works(self) -> None:
        """v2.15.4 carve-out guard: the neighbouring branch must be untouched.
        This is the machinery ascent/descent disambiguation rides on."""
        import inspect

        from custom_components.vag_connect.cariad.auth import _eu_data_act as m

        src = inspect.getsource(m)
        assert "_syn_out.setdefault(fname, set()).add(prefix)" in src
        assert "_syn_out.setdefault(prefix, set()).add(fname)" in src

    def test_ascent_and_descent_still_disambiguate(self) -> None:
        # The shared bare leaf physical_value must not collapse the siblings.
        d = _map({
            "slope_consumption_values.ascent_slope_consumption.physical_value": "120",
            "slope_consumption_values.descent_slope_consumption.physical_value": "35",
        })
        assert d.ascent_slope_consumption == 120.0
        assert d.descent_slope_consumption == 35.0


# ── 2. the value_type companion is always consumed ─────────────────────────


class TestValueTypeCompanionConsumed:
    def test_companion_consumed_even_without_the_reading(self) -> None:
        """#963: the car sends value_type but no physical_value."""
        d = _map({
            "energy_contents.current_energy_content.value_type": "measured",
        })
        raw = d.raw_unmapped_fields or {}
        leftover = [k for k in raw if "value_type" in str(k)]
        assert not leftover, (
            f"value_type companion was not consumed and will be re-reported to "
            f"the Scout on every poll: {leftover}"
        )

    def test_the_gate_still_blocks_an_invalid_reading(self) -> None:
        d = _map({
            "energy_contents.current_energy_content.physical_value": "756",
            "energy_contents.current_energy_content.value_type": "invalid",
        })
        assert d.battery_available_kwh is None

    def test_a_valid_reading_still_lands(self) -> None:
        d = _map({
            "energy_contents.current_energy_content.physical_value": "756",
            "energy_contents.current_energy_content.value_type": "measured",
        })
        assert d.battery_available_kwh == 75.6

    def test_no_companion_at_all_does_not_block(self) -> None:
        d = _map({
            "energy_contents.current_energy_content.physical_value": "756",
        })
        assert d.battery_available_kwh == 75.6

    def test_slope_companions_are_consumed_too(self) -> None:
        d = _map({
            "slope_consumption_values.ascent_slope_consumption.value_type": "measured",
            "slope_consumption_values.descent_slope_consumption.value_type": "measured",
        })
        raw = d.raw_unmapped_fields or {}
        assert not [k for k in raw if "value_type" in str(k)]

    def test_the_helper_is_the_left_operand_everywhere(self) -> None:
        """Guards the actual mechanism: written the other way round, Python
        short-circuits and the companion is silently never consumed again."""
        import inspect

        from custom_components.vag_connect.cariad.auth import _eu_data_act as m

        src = inspect.getsource(m)
        for var in ("_cur_kwh", "_max_kwh", "_asc_slope", "_desc_slope"):
            assert f"if {var} is not None and _value_type_ok(" not in src, (
                f"{var} short-circuits the companion consumption again (#963)"
            )
            assert f") and {var} is not None:" in src, var


# ── 3. logging: quieter where it floods, louder where it was silent ────────


def test_ola_403_retry_is_debug_not_warning() -> None:
    """#779: ~19 endpoints per poll produced ~22 identical warnings in 0.3 s
    for a condition the user cannot resolve. The ERROR after the fallbacks are
    exhausted, and the Repair issue, both stay."""
    import inspect

    from custom_components.vag_connect.cariad.api import seat_cupra

    src = inspect.getsource(seat_cupra)
    idx = src.find("retrying with fallback header-set")
    assert idx > 0
    assert "_LOGGER.debug(" in src[max(0, idx - 400):idx], (
        "the per-403 retry line is still at WARNING"
    )


def test_vwde_resume_failure_states_the_reason() -> None:
    import inspect

    from custom_components.vag_connect.cariad.api import base

    src = inspect.getsource(base)
    idx = src.find("could not silently")
    assert idx > 0
    window = src[max(0, idx - 900):idx + 900]
    assert "except AuthenticationError as err:" in window, (
        "an auth failure still logs only the exception class, so the pasted "
        "log cannot distinguish an expired session from a redirect loop"
    )


def test_vwde_generic_failure_still_redacts_the_message() -> None:
    """Non-negotiable: aiohttp.InvalidURL puts the OAuth callback URL in
    __str__, and that URL carries access_token and id_token JWTs."""
    import inspect

    from custom_components.vag_connect.cariad.api import base

    src = inspect.getsource(base)
    idx = src.find("message redacted, see DEBUG")
    assert idx > 0, "the generic branch no longer redacts"
    window = src[idx:idx + 400]
    assert "type(err).__name__" in window


def test_historical_import_names_its_failure_mode() -> None:
    import inspect

    from custom_components.vag_connect import coordinator

    src = inspect.getsource(coordinator.VagConnectCoordinator.async_import_historical_export)
    assert "last_no_data_reason" in src, (
        "the service still returns a bare False with no log for several "
        "completely different outcomes"
    )
    assert "nothing needed importing" in src, (
        "parsed-but-nothing-merged is still silent and looks like a failure"
    )


def test_repair_logs_are_english() -> None:
    import inspect

    from custom_components.vag_connect import repairs

    src = inspect.getsource(repairs)
    assert "Repair-Issue erstellt" not in src
    assert "repair issue created" in src
