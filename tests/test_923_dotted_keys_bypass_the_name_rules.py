"""#923 follow-up — a dotted field name must not walk past the name rules.

Every rule in ``_scrub`` that keys off a NAME tested exact equality on the
whole key. EU Data Act field names are dotted — the dictionary's own count is
3206 of 7990 — and an UNMAPPED portal field lands verbatim in
``raw_unmapped_fields``, which the diagnostics download emits. So:

    latitude                     -> **REDACTED**
    parking_position.latitude    -> 48.1412345      (in the clear)
    access_token                 -> **REDACTED**
    settings.access_token        -> the token       (in the clear)
    user_id                      -> sha256:...
    vehicle.user_id              -> the id          (in the clear)

measured with one marker per key. What made it invisible is that the
value-PATTERN rules were never affected: ``profile.email`` masked correctly, so
the file read as redacted while five dotted spellings went through.

The last test is the one that generalises: it walks every name in all three
sets and demands that the dotted form is handled too, so a name added later is
covered without anyone remembering this file.
"""
from __future__ import annotations

import pytest

from custom_components.vag_connect import diagnostics as D

_MARK = "MARKER-VALUE-DO-NOT-LEAK"

# Both scrubbers had the gap, and fixing only the one that was measured first
# would have left the raw sections leaking while the tests for the other half
# went green. So every case below runs against both. (Measured: after _scrub
# was corrected, _scrub_raw still returned four of the five dotted spellings
# in the clear.)
_SCRUBBERS = [("_scrub", D._scrub), ("_scrub_raw", D._scrub_raw)]
_SCRUBBER_IDS = [name for name, _ in _SCRUBBERS]


def _scrubbed(key: str, value: str = _MARK, *, fn=D._scrub):
    """Through the section this actually reaches: raw_unmapped_fields."""
    out = fn({"raw_unmapped_fields": {key: value}})
    return out["raw_unmapped_fields"]


class TestTheFiveMeasuredLeaks:
    @pytest.mark.parametrize("fn", [f for _, f in _SCRUBBERS], ids=_SCRUBBER_IDS)
    @pytest.mark.parametrize(
        "key",
        [
            "parking_position.latitude",
            "vehicle.parking.longitude",
            "settings.access_token",
            "auth.tokens.refresh_token",
            "vehicle.user_id",
        ],
    )
    def test_the_dotted_spelling_is_handled(self, key: str, fn) -> None:
        got = _scrubbed(key, fn=fn)
        assert _MARK not in str(got.get(key)), (
            f"{key} passed the name rules because of the dot; the bare leaf "
            "is registered and this spelling carries the same kind of data"
        )

    @pytest.mark.parametrize("fn", [f for _, f in _SCRUBBERS], ids=_SCRUBBER_IDS)
    @pytest.mark.parametrize(
        "key", ["latitude", "longitude", "access_token", "refresh_token", "user_id"]
    )
    def test_the_bare_spelling_still_works(self, key: str, fn) -> None:
        """Control: the fix must not have moved the behaviour, only widened it."""
        got = _scrubbed(key, fn=fn)
        assert _MARK not in str(got.get(key))


class TestItDoesNotOverRedact:
    def test_a_harmless_dotted_field_stays_readable(self) -> None:
        """Over-redaction would make the Scout section useless."""
        got = _scrubbed("odometer.total_km", "123456")
        assert got.get("odometer.total_km") == "123456"

    def test_the_full_dotted_name_is_kept_as_the_key(self) -> None:
        """Triage must still see WHICH field was redacted."""
        got = _scrubbed("parking_position.latitude")
        assert "parking_position.latitude" in got

    def test_a_value_pattern_rule_is_unchanged(self) -> None:
        """E-mail masking never depended on the key name; keep it that way."""
        got = _scrubbed("profile.email", "someone@example.de")
        assert got.get("profile.email") == "s***@***.de"


# ── the generalising guard ──────────────────────────────────────────────────


def _all_name_keyed() -> list[str]:
    """Every name any name-keyed rule in the module reacts to."""
    names = set(D._REDACT_KEYS) | set(D._GPS_KEYS) | set(D._HASH_KEYS)
    # keys whose rule is about a CONTAINER at the top level, not a leaf name:
    # a dotted form of these cannot occur, and asserting on them would test
    # the identifier-map branch rather than the leaf matching.
    containers = {
        "skoda_official_keys",
        "charging_profiles",
    }
    return sorted(n for n in names if isinstance(n, str) and n not in containers)


_NAMES = _all_name_keyed()


def test_positive_control_the_sets_are_not_empty() -> None:
    """Without this, an empty set would make the sweep below pass vacuously."""
    assert len(_NAMES) >= 40, f"only {len(_NAMES)} name-keyed rules found"
    for expected in ("access_token", "latitude", "website_cookies"):
        assert expected in _NAMES, f"{expected} missing from the swept set"


@pytest.mark.parametrize("fn", [f for _, f in _SCRUBBERS], ids=_SCRUBBER_IDS)
@pytest.mark.parametrize("name", _NAMES)
def test_every_registered_name_is_also_handled_when_dotted(name: str, fn) -> None:
    key = f"some_container.{name}"
    got = _scrubbed(key, fn=fn)
    assert _MARK not in str(got.get(key)), (
        f"{key!r} is not handled by {fn.__name__} although {name!r} is "
        "registered. Any name in these sets can arrive dotted from the portal, "
        "so the leaf has to be matched — in BOTH scrubbers; see the comments."
    )


def test_positive_control_both_scrubbers_are_actually_swept() -> None:
    """A guard on one half is the gap it is meant to close."""
    assert len(_SCRUBBERS) == 2
    assert {n for n, _ in _SCRUBBERS} == {"_scrub", "_scrub_raw"}
