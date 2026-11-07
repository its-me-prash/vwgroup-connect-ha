# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#2030 — the fold belongs at the one place every path must pass.

**What happened.** @Kaputnixx reported that on 5.2.3 the Charging Port sensor
was dead and Home Assistant logged, 112 times in 22 hours at his 12-minute scan
interval:

    ValueError: Sensor sensor.…_ladeanschluss provides state value
    'DISCONNECTED', which is not in the list of options provided

He had already checked that ``normalize_enum_states`` exists and is called in
the enrichment step and in the cache restore, and concluded from the symptom
that *some other path* hands the entity the un-normalised value. He was right,
and he found it from the outside.

**The path.** ``_poll_loop`` calls ``_advance_historical_exports`` on every
iteration. That imports a pending EU-Data-Act export, writes the parsed snapshot
straight into ``self.vehicles[vin]`` — or gap-fills the current one from it —
and pushes with ``async_set_updated_data(dict(self.vehicles))``, bypassing both
``_async_push_update`` and the enrichment step. The export dialect carries
``plug_state`` and publishes the verbose upper-case token. Hence the 12-minute
cadence, and hence "a reload fixes it until the next poll": the restore path
does fold.

**Why #1739's test did not catch it.** Its docstring says "EVERY path that
reaches the platforms" and it asserts the call is present in the two paths it
names. It never enumerates the paths that exist, so a third one is invisible to
it — the guard covered the sites someone remembered. There are six
``async_set_updated_data`` call sites in the coordinator and four push
``dict(self.vehicles)`` with no enrichment in between.

So this file does two different jobs, and the second is the durable one:

1. the fold happens on the way out, for the real reporter's value;
2. **it is structurally impossible to bypass** — asserted by enumerating the
   call sites from the parse tree rather than by listing the ones known today.
"""
from __future__ import annotations

import ast
import inspect
import textwrap
from typing import Any
from unittest.mock import patch

from custom_components.vag_connect.coordinator import VagConnectCoordinator

#: The exact value from the reporter's traceback.
_ROH = "DISCONNECTED"


def _koordinator() -> VagConnectCoordinator:
    """A coordinator without ``__init__``.

    The module's own comments use this path for the same reason: the real
    constructor needs hass, an entry and a client, none of which this behaviour
    depends on.
    """
    return VagConnectCoordinator.__new__(VagConnectCoordinator)


def _push(data: Any) -> Any:
    """Call the override and return what reached the base class."""
    gesehen: list[Any] = []

    def _fange(self: Any, payload: Any) -> None:
        gesehen.append(payload)

    with patch(
        "homeassistant.helpers.update_coordinator.DataUpdateCoordinator"
        ".async_set_updated_data",
        _fange,
    ):
        VagConnectCoordinator.async_set_updated_data(_koordinator(), data)
    assert len(gesehen) == 1, f"base class called {len(gesehen)}x, expected once"
    return gesehen[0]


# ── 1. the behaviour, on the reporter's value ───────────────────────────────

def test_the_reporters_token_is_folded_on_the_way_out() -> None:
    raus = _push({"VIN1": {"plug_state": _ROH}})
    assert raus["VIN1"]["plug_state"] == "disconnected", (
        "the upper-case token still reaches the platforms, so the entity is "
        "refused and the Charging Port sensor stays dead (#2030)"
    )


def test_the_stored_snapshot_is_cleaned_too_not_only_the_copy() -> None:
    """The pushes pass a SHALLOW copy of self.vehicles, so the inner dicts are
    shared. Folding in place is what stops the raw token being written back to
    disk and restored on the next start."""
    gespeichert = {"plug_state": _ROH}
    _push({"VIN1": gespeichert})
    assert gespeichert["plug_state"] == "disconnected", (
        "only the outgoing copy was folded; the snapshot still holds the raw "
        "token and will be persisted and restored"
    )


def test_an_unknown_dialect_becomes_no_value_not_a_wrong_one() -> None:
    raus = _push({"VIN1": {"plug_state": "PLUG_CONNECTION_STATE_CONNECTED"}})
    assert raus["VIN1"]["plug_state"] is None


def test_an_already_folded_value_survives() -> None:
    """The enrichment path folds earlier; doing it twice must not destroy it."""
    raus = _push({"VIN1": {"plug_state": "connected"}})
    assert raus["VIN1"]["plug_state"] == "connected"


def test_non_vehicle_payloads_pass_through_untouched() -> None:
    assert _push(None) is None
    assert _push({"VIN1": "not a dict"})["VIN1"] == "not a dict"


def test_every_vehicle_in_the_payload_is_folded_not_just_the_first() -> None:
    raus = _push({
        "A": {"plug_state": _ROH},
        "B": {"plug_state": "CONNECTED"},
        "C": {"odometer_km": 1},
    })
    assert raus["A"]["plug_state"] == "disconnected"
    assert raus["B"]["plug_state"] == "connected"
    assert "plug_state" not in raus["C"]


# ── 2. the structural half: no path can bypass it ───────────────────────────

def _push_call_sites() -> list[ast.Call]:
    """Every ``async_set_updated_data(...)`` call in the coordinator module.

    Enumerated from the parse tree. #1739's test asserted the fold was present
    at the two call sites it named, which is why a third went unnoticed for as
    long as it existed — the measurement knew the answer it was looking for.
    """
    import custom_components.vag_connect.coordinator as mod

    tree = ast.parse(textwrap.dedent(inspect.getsource(mod)))
    treffer: list[ast.Call] = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "async_set_updated_data"
        ):
            treffer.append(node)
    return treffer


def test_the_instrument_finds_the_call_sites_at_all() -> None:
    """Positive control. Without it the two tests below pass on an empty set,
    which is the shape of the mistake they exist to prevent."""
    sites = _push_call_sites()
    assert len(sites) >= 5, (
        f"only {len(sites)} push site(s) found — the AST walk no longer matches "
        "the calls, so the completeness checks below are vacuous"
    )


def test_no_site_reaches_the_base_class_directly() -> None:
    """A call on ``super()`` or on the class is how the choke point gets
    bypassed: it would publish without folding and look perfectly ordinary."""
    erlaubt_super = 0
    for call in _push_call_sites():
        empfaenger = call.func.value  # type: ignore[attr-defined]
        if isinstance(empfaenger, ast.Call) and isinstance(empfaenger.func, ast.Name) \
                and empfaenger.func.id == "super":
            erlaubt_super += 1
            continue
        if isinstance(empfaenger, ast.Name) and empfaenger.id == "DataUpdateCoordinator":
            raise AssertionError(
                "a push calls DataUpdateCoordinator.async_set_updated_data "
                "directly, bypassing the fold"
            )
        assert isinstance(empfaenger, ast.Name) and empfaenger.id == "self", (
            "a push goes through something other than self, so the override "
            f"cannot see it: {ast.dump(empfaenger)[:120]}"
        )
    assert erlaubt_super == 1, (
        f"{erlaubt_super} super() calls found, expected exactly one — the "
        "override itself. More than one means a second bypass; none means the "
        "override no longer delegates and HA never receives the data."
    )


def test_the_override_exists_and_folds_before_delegating() -> None:
    """Order matters: a fold after ``super()`` would read as a fix and change
    nothing the platforms receive.

    **The first version of this test was vacuous, and the way it failed is the
    reason it is written this way now.** It dumped the whole function body and
    compared the string positions of "normalize_enum_states" and "super". The
    docstring of the override *mentions* ``normalize_enum_states``, and a
    docstring is the body's first statement — so the fold always "came first",
    whatever the code did. Reversing the two statements in the implementation
    left the test green. It was satisfied by its own prose.

    So the comparison is now between STATEMENT INDICES, with the docstring
    dropped, and each statement is searched as a parse tree rather than as text.
    """
    src = textwrap.dedent(
        inspect.getsource(VagConnectCoordinator.async_set_updated_data)
    )
    body: list[ast.stmt] = ast.parse(src).body[0].body  # type: ignore[attr-defined]

    # Drop the docstring: it is prose about the code, not the code.
    if (
        body
        and isinstance(body[0], ast.Expr)
        and isinstance(body[0].value, ast.Constant)
        and isinstance(body[0].value.value, str)
    ):
        body = body[1:]
    assert body, "the override has a docstring and nothing else"

    def _nennt(stmt: ast.stmt, name: str) -> bool:
        return any(
            isinstance(n, ast.Name) and n.id == name
            or isinstance(n, ast.Attribute) and n.attr == name
            for n in ast.walk(stmt)
        )

    fold = [i for i, s in enumerate(body) if _nennt(s, "normalize_enum_states")]
    deleg = [
        i for i, s in enumerate(body)
        if any(
            isinstance(n, ast.Call)
            and isinstance(n.func, ast.Name)
            and n.func.id == "super"
            for n in ast.walk(s)
        )
    ]
    assert fold, "the override no longer calls normalize_enum_states in its body"
    assert deleg, "the override no longer delegates to the base class"
    assert max(fold) < min(deleg), (
        f"the fold is at statement {fold} and the delegation at {deleg}: "
        "normalize_enum_states runs after super().async_set_updated_data, so "
        "the platforms already have the raw value"
    )
