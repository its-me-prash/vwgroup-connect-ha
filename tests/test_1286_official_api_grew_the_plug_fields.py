"""#1286 — the official Škoda spec grew the plug fields, and we read them raw.

The live OpenAPI spec (`public.api.connect.skoda-auto.cz/v3/api-docs`, fetched
2026-11-01, 83120 bytes) now declares **12** routes where the research note in
`docs/research/skoda-official-api.md` was written from **9**, and
``ChargingStatus`` gained ``plugConnectionState`` and ``plugLockState``.

Both are declared as plain `string` with **no enum**, so the allowed values are
not specified. That is the whole reason these tests exist: the parser must not
invent a mapping. It passes the raw token to the model and lets the
coordinator's ``normalize_enum_states`` fold it onto the sensor's declared
options, where an unrecognised value becomes no value rather than a wrong one.

Checked at the APK too, and the absence there is informative rather than
contradictory: MyŠkoda 8.18.0 (pulled 2026-11-01, versionCode 261012003)
contains neither string, because the app talks to the mysmob backend and not to
the public API. The spec is the authority for this surface; the app is not.
"""
from __future__ import annotations

from custom_components.vag_connect.cariad.api.skoda_official import (
    SkodaOfficialClient,
)

# The project's documented synthetic placeholder. A one-off VIN-shaped
# literal would trip every future VIN scan over this repo for no gain —
# this test passes the VIN through and never looks at it.
_VIN = "WVWZZZAUZFW000000"


def _parse(charging_status: dict) -> object:
    return SkodaOfficialClient._parse_vehicle(
        _VIN, {"charging": {"status": charging_status}}
    )


class TestThePlugFieldsArriveUnmapped:
    def test_the_connection_state_reaches_the_model(self) -> None:
        d = _parse({"plugConnectionState": "CONNECTED"})
        assert d.plug_state == "CONNECTED"

    def test_the_lock_state_reaches_the_model(self) -> None:
        d = _parse({"plugLockState": "LOCKED"})
        assert d.plug_lock_state == "LOCKED"

    def test_a_prefixed_dialect_is_passed_through_untouched(self) -> None:
        """The spec declares no enum, so the parser may not normalise. Whatever
        the backend sends goes to the model and is folded downstream."""
        d = _parse({"plugConnectionState": "PLUG_CONNECTION_STATE_CONNECTED"})
        assert d.plug_state == "PLUG_CONNECTION_STATE_CONNECTED"

    def test_both_together(self) -> None:
        d = _parse({"plugConnectionState": "DISCONNECTED", "plugLockState": "UNLOCKED"})
        assert d.plug_state == "DISCONNECTED"
        assert d.plug_lock_state == "UNLOCKED"


class TestNothingIsInvented:
    """Absent, blank or non-string leaves the field unset — never a guess."""

    def test_absent_leaves_both_unset(self) -> None:
        d = _parse({"state": "CHARGING"})
        assert d.plug_state is None
        assert d.plug_lock_state is None

    def test_a_blank_string_leaves_it_unset(self) -> None:
        d = _parse({"plugConnectionState": "   ", "plugLockState": ""})
        assert d.plug_state is None
        assert d.plug_lock_state is None

    def test_a_non_string_leaves_it_unset(self) -> None:
        d = _parse({"plugConnectionState": 1, "plugLockState": {"a": 1}})
        assert d.plug_state is None
        assert d.plug_lock_state is None

    def test_the_sentinel_guard_applies(self) -> None:
        """Same guard as ``chargeType`` below it (#1104): a documented
        no-reading token must not become a confident state."""
        d = _parse({"plugConnectionState": "INVALID"})
        assert d.plug_state is None, (
            "a no-reading sentinel became a state; drop_charge_sentinel is the "
            "guard and it has to run before the assignment"
        )


class TestTheRestOfTheChargingBlockStillWorks:
    """Controls — the new lines sit inside a block that already parsed these."""

    def test_the_charging_state_is_unaffected(self) -> None:
        d = _parse({"state": "CHARGING", "plugConnectionState": "CONNECTED"})
        assert d.charging_state == "CHARGING"
        assert d.is_charging is True

    def test_the_power_is_unaffected(self) -> None:
        d = _parse({"chargePowerInKw": 11.0, "plugLockState": "LOCKED"})
        assert d.charging_power_kw == 11.0

    def test_the_target_soc_is_unaffected(self) -> None:
        got = SkodaOfficialClient._parse_vehicle(
            _VIN,
            {
                "charging": {
                    "status": {"plugConnectionState": "CONNECTED"},
                    "settings": {"targetStateOfChargeInPercent": 80},
                }
            },
        )
        assert got.target_soc == 80
        assert got.plug_state == "CONNECTED"
