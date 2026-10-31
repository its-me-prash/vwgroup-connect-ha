"""#923 follow-up — a charging profile's coordinates must not reach the download.

The cookie-jar defect was a SHAPE problem: a list of objects whose inner key
names are in no redaction set. Generalising from it found a second one of
exactly that shape, and this one was emitting in the clear.

``coordinator.py`` flattens each Škoda / SEAT / CUPRA charging profile into
``{"name": ..., "location_lat": ..., "location_lon": ...}`` and the GPS branch
in ``diagnostics.py`` only ever matched the spellings ``latitude`` and
``longitude``. So the coordinates of the place the car habitually charges —
home, for most people — went into the diagnostics download at two decimals,
roughly a kilometre, in both the default and the opt-in mode, while that
module's own contract promises privacy-by-default removal. The owner's label
for the place ("Home", an employer) went with it, although the project had
already registered the sibling ``charging_location_N_name`` on exactly the
argument that such a label is the owner's own word for a place.

The last test here is the one that would have caught it: it derives the set of
coordinate key names from the SOURCE rather than from the redaction set, which
is the same inversion that found the three credential keys in 5.2.1 — a list
checked against itself always looks complete.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from custom_components.vag_connect import diagnostics as D

_PKG = Path(__file__).resolve().parents[1] / "custom_components" / "vag_connect"

_LAT = 48.14
_LON = 11.58
_LABEL = "Home"


def _profile(**over) -> dict:
    """A profile in exactly the shape coordinator.py appends."""
    base = {
        "id": 1,
        "name": _LABEL,
        "target_soc_pct": 80,
        "max_charging_current": "maximum",
        "auto_unlock_plug": True,
        "min_battery_soc_pct": 20,
        "location_lat": _LAT,
        "location_lon": _LON,
        "preferred_times_count": 2,
        "timers_count": 1,
    }
    base.update(over)
    return base


def _vehicle(**over) -> dict:
    base = {
        "charging_profiles": [_profile()],
        "active_charging_profile_name": _LABEL,
    }
    base.update(over)
    return base


def _text(value, **kwargs) -> str:
    return json.dumps(D._scrub(value, **kwargs), default=str)


class TestTheProfileCoordinatesAreGone:
    def test_default_mode_removes_both_coordinates(self) -> None:
        out = _text(_vehicle())
        assert str(_LAT) not in out, "the profile latitude reached the download"
        assert str(_LON) not in out, "the profile longitude reached the download"

    def test_default_mode_removes_the_owners_label(self) -> None:
        out = _text(_vehicle())
        assert _LABEL not in out, (
            "the owner's name for a habitual charging place reached the "
            "download; charging_location_N_name is registered for this reason"
        )

    def test_opt_in_rounds_instead_of_removing_like_the_other_gps(self) -> None:
        """Consistency: the opt-in path must behave as it does for latitude."""
        out = _text(_vehicle(), gps_round=True)
        assert "48.1" in out and "11.6" in out, out[:300]
        assert str(_LAT) not in out, "two decimals survived the opt-in rounding"
        assert _LABEL not in out, "the label is not GPS; rounding must not keep it"

    def test_the_fields_triage_needs_are_kept(self) -> None:
        """Over-redaction would make the section useless; that is not the fix."""
        scrubbed = D._scrub(_vehicle())
        prof = scrubbed["charging_profiles"][0]
        assert prof["target_soc_pct"] == 80
        assert prof["max_charging_current"] == "maximum"
        assert prof["timers_count"] == 1
        assert prof["id"] == 1


class TestEmptyStaysVisiblyEmpty:
    """#923 rule: a redacted empty is indistinguishable from a hidden value."""

    def test_an_absent_coordinate_is_not_faked_as_redacted(self) -> None:
        scrubbed = D._scrub(
            _vehicle(charging_profiles=[_profile(location_lat=None, location_lon=None)])
        )
        prof = scrubbed["charging_profiles"][0]
        assert prof["location_lat"] is None
        assert prof["location_lon"] is None

    def test_an_absent_label_is_not_faked_as_redacted(self) -> None:
        scrubbed = D._scrub(
            _vehicle(charging_profiles=[_profile(name=None)])
        )
        assert scrubbed["charging_profiles"][0]["name"] is None


class TestTheHarnessItself:
    def test_positive_control_bare_latitude_is_still_removed(self) -> None:
        """If this fails, every assertion above is void."""
        out = _text({"latitude": _LAT, "longitude": _LON})
        assert str(_LAT) not in out and "REDACTED" in out

    def test_an_unrelated_number_is_not_redacted(self) -> None:
        """And the scrubber must not simply blank everything numeric."""
        out = _text({"odometer_km": 48})
        assert "48" in out


# ── the guard that would have found this ────────────────────────────────────
#
# Every key name under which this integration writes a coordinate into its own
# output has to be covered by one of the two sets: _GPS_KEYS for our own
# flattened output, _RAW_REDACT_KEYS for wire payloads that go through
# _scrub_raw. Derived from the source, so a new spelling fails here instead of
# shipping.
_COORD_KEY = re.compile(
    r"""["']((?:[a-z_]*_)?(?:lat|lon|latitude|longitude))["']\s*:""",
    re.IGNORECASE,
)


def _coordinate_keys_written_in_source() -> set[str]:
    found: set[str] = set()
    for path in _PKG.rglob("*.py"):
        if path.name == "diagnostics.py":
            continue  # the redaction module names them to redact them
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.lstrip()
            if stripped.startswith("#"):
                continue  # a comment describing a wire shape writes nothing
            for hit in _COORD_KEY.findall(line):
                found.add(hit.lower())
    return found


def test_every_coordinate_key_in_the_source_is_covered() -> None:
    written = _coordinate_keys_written_in_source()
    covered = set(D._GPS_KEYS) | {k.lower() for k in D._RAW_REDACT_KEYS}
    missing = sorted(k for k in written if k not in covered)
    assert not missing, (
        f"these coordinate key names are written somewhere in the package and "
        f"are in neither _GPS_KEYS nor _RAW_REDACT_KEYS: {missing}. That is "
        "how the charging-profile coordinates reached the download — the GPS "
        "branch matched two spellings and the code wrote a third."
    )


def test_positive_control_the_scan_actually_finds_keys() -> None:
    """Without this, a broken regex makes the guard above pass vacuously."""
    written = _coordinate_keys_written_in_source()
    assert "location_lat" in written, (
        f"the scan missed the key this whole module is about: {sorted(written)}"
    )
    assert len(written) >= 3, f"implausibly few coordinate keys: {sorted(written)}"


@pytest.mark.parametrize("key", ["latitude", "longitude", "location_lat", "location_lon"])
def test_the_known_four_are_in_the_gps_set(key: str) -> None:
    assert key in D._GPS_KEYS
