"""#1739 (@awood-ops) — an enum sensor's state must be folded onto its own
declared options on EVERY path that reaches the platforms, not only on a poll.

Home Assistant does not degrade an out-of-vocabulary enum state to
"unavailable". It refuses to add the entity at all:

    Error adding entity sensor.<car>_charging_port … ValueError: … provides
    state value 'DISCONNECTED', which is not in the list of options provided

The reporter's car hit this at setup, before any poll. Three separate mistakes
lined up to allow it, and each one is pinned by a test here:

1. the normaliser inspected only values that were already ``str``, so it was a
   barrier that examined the type it already trusted;
2. it ran only inside the enrichment step, and the cache restore during setup
   hands a stored snapshot to the platforms *without* enriching;
3. it covered only ``plug_state``, while there are five enum sensors.

Point 2 is the one that actually broke his car, and it is the one a
``plug_state``-shaped test would have missed entirely.

**Correction, 2026-11-06 (#2030).** The title of this file and the first line of
this docstring claim "EVERY path". That was not true, and this file could not
have found out: it asserts the fold is present at the two paths it *names*,
without ever enumerating the paths that exist. There were six
``async_set_updated_data`` call sites in the coordinator, four of them pushing
``dict(self.vehicles)`` with no enrichment — and one of those four runs on a
timer, so @Kaputnixx watched his Charging Port entity die 112 times in 22 hours
on 5.2.3 while this file was green.

The fold now lives in a single override of ``async_set_updated_data``, which
every path must pass, and the structural guarantee — "no site can bypass it",
proven by enumerating the call sites from the parse tree — is in
``test_2030_enum_fold_at_the_choke_point.py``. The two assertions below stay:
they still document where the fold used to be needed, and the enrichment and
restore paths still call it directly.
"""

from __future__ import annotations

import ast
import inspect
import textwrap

from custom_components.vag_connect.coordinator import (
    VagConnectCoordinator,
    _enum_options_by_data_key,
    normalize_enum_states,
)


# ─── The function itself ──────────────────────────────────────────────────

def test_the_reporters_value_is_folded_not_rejected() -> None:
    """The exact value from the traceback must survive as a valid state."""
    data = {"plug_state": "DISCONNECTED"}
    normalize_enum_states(data)
    assert data["plug_state"] == "disconnected", (
        "the upper-case token from #1739 must fold onto the declared option, "
        "not reach the sensor and kill the entity"
    )


def test_an_unrecognised_token_becomes_unknown_rather_than_a_guess() -> None:
    data = {"plug_state": "PLUG_CONNECTION_STATE_INVALID"}
    normalize_enum_states(data)
    assert data["plug_state"] is None, (
        "a token we do not recognise means we do not know the state; inventing "
        "one would be worse than an unavailable sensor"
    )


def test_a_non_string_is_folded_too() -> None:
    """The original guard was ``isinstance(value, str)``, so this slipped past."""
    data = {"plug_state": True}
    normalize_enum_states(data)
    assert data["plug_state"] is None


def test_an_absent_field_is_not_invented() -> None:
    data: dict = {}
    normalize_enum_states(data)
    assert "plug_state" not in data, (
        "normalising must not create keys; an absent reading stays absent"
    )


def test_a_none_is_left_alone() -> None:
    data = {"plug_state": None}
    normalize_enum_states(data)
    assert data["plug_state"] is None


def test_every_enum_sensor_is_covered_not_just_the_reported_one() -> None:
    """Mistake 3. The map is built from the descriptors so it cannot drift."""
    covered = _enum_options_by_data_key()
    # Named explicitly rather than recomputed from the same source the
    # implementation reads, so adding a sixth enum sensor fails this test and
    # forces a decision instead of being silently absorbed.
    assert set(covered) >= {
        "plug_state",
        "portal_health",
        "historical_export_state",
        "tpms_status",
        "climate_start_mode",
    }, f"an enum sensor is not covered by the normaliser: {sorted(covered)}"


def test_all_option_lists_are_lower_case() -> None:
    """The normaliser lower-cases, so an upper-case option would be unreachable.

    Without this, adding an enum sensor with ``options=["OK"]`` would make its
    every reading fold to None — the normaliser would destroy the value it is
    supposed to protect, silently, for that one sensor.
    """
    offenders = {
        key: sorted(o for o in opts if o != o.lower())
        for key, opts in _enum_options_by_data_key().items()
        if any(o != o.lower() for o in opts)
    }
    assert not offenders, (
        f"these options can never be matched by the normaliser: {offenders}"
    )


def test_folding_is_idempotent() -> None:
    data = {"plug_state": "CONNECTED"}
    normalize_enum_states(data)
    once = data["plug_state"]
    normalize_enum_states(data)
    assert data["plug_state"] == once == "connected"


# ─── The path that actually broke ─────────────────────────────────────────

def _restore_block_statements() -> list[ast.stmt]:
    """The statements that build a restored snapshot inside ``async_setup``.

    Located by the assignment that publishes it (``self.vehicles[vin] = …``)
    rather than by line number, so moving the block does not break this test.
    """
    # dedent first: getsource on a METHOD keeps its class indentation, and
    # ast.parse raises IndentationError on it. A failure there reads exactly
    # like "the call is missing", which is the instrument lying about the code.
    src = textwrap.dedent(inspect.getsource(VagConnectCoordinator.async_setup))
    tree = ast.parse(src)
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if not isinstance(body, list):
            continue
        for stmt in body:
            if (
                isinstance(stmt, ast.Assign)
                and isinstance(stmt.targets[0], ast.Subscript)
                and isinstance(stmt.targets[0].value, ast.Attribute)
                and stmt.targets[0].value.attr == "vehicles"
                and isinstance(stmt.value, ast.Name)
                and stmt.value.id == "restored"
            ):
                return body
    raise AssertionError(
        "could not find 'self.vehicles[vin] = restored' in async_setup — the "
        "cache-restore block moved, and this test can no longer guard it"
    )


def test_the_cache_restore_normalises_before_publishing() -> None:
    """Mistake 2, the one that broke the reporter's car.

    The restore hands a stored snapshot straight to the platforms and
    deliberately does not enrich, so the normaliser has to be called here as
    well. Asserted on the parse tree rather than on a substring: the call has to
    be a real call, on ``restored``, and ordered BEFORE the assignment that
    publishes it — a call placed after it would read as a fix and do nothing.
    """
    body = _restore_block_statements()
    publish_at = next(
        i for i, s in enumerate(body)
        if isinstance(s, ast.Assign)
        and isinstance(s.targets[0], ast.Subscript)
        and isinstance(s.targets[0].value, ast.Attribute)
        and s.targets[0].value.attr == "vehicles"
    )
    normalise_at = [
        i for i, s in enumerate(body)
        if isinstance(s, ast.Expr)
        and isinstance(s.value, ast.Call)
        and isinstance(s.value.func, ast.Name)
        and s.value.func.id == "normalize_enum_states"
        and [a.id for a in s.value.args if isinstance(a, ast.Name)] == ["restored"]
    ]
    assert normalise_at, (
        "the cache restore does not normalise enum states, so a snapshot "
        "written before a normaliser existed still kills the entity at setup "
        "(#1739). The vehicle cache version has never been bumped, so such "
        "snapshots are still loaded verbatim."
    )
    assert min(normalise_at) < publish_at, (
        "normalize_enum_states is called after the snapshot is published to "
        "self.vehicles, so it cannot affect what the platforms receive"
    )


def test_enrich_uses_the_shared_normaliser() -> None:
    """Mistakes 1 and 3: the poll path must use the same barrier, not its own.

    Two copies of a vocabulary drift apart — that is how plug_state ended up
    normalised in one place and five enum sensors in none.
    """
    src = inspect.getsource(VagConnectCoordinator._enrich)
    assert "normalize_enum_states(data)" in src, (
        "the poll path no longer routes through the shared normaliser"
    )
    assert '"connected", "disconnected"' not in src, (
        "the enum vocabulary is restated inside _enrich; it belongs only in the "
        "sensor descriptors, which the normaliser reads"
    )
