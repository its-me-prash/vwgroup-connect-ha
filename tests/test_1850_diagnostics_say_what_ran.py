# Copyright 2026 Prash Albert Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Two diagnostics that described a setup the user no longer had.

@indigomejor (#1850) delivered v5.1.0 measurements and found two things. He
called both cosmetic; one of them is not, quite.

**The stand-down that never happened.** On his portal-less entry the log said

    EU Data Act portal: 3 polls with no fresh snapshot — standing down from the
    60s drop-retry to the configured 600s until one lands

while his measured cadence was 621-643 s against a 600 s interval — so nothing
ever stood down, because the drop-retry was never running. The counting block
sat *before* the gate that asks whether a portal is armed, so it counted and
spoke on entries the retry does not apply to. The number was true; the action
it described never happened.

Not purely cosmetic, which is the part worth separating: the streak also kept
climbing while the portal was off, so arming the portal later started with the
retry budget already spent and the fast retry never got its first poll.

**The label that outlived its truth.** His diagnostics kept reporting
``skoda_official: disabled by source mode (mysmob_only)`` after he had switched
mode and the channel had been armed. The cause is a missing *write*, not a
missing clear: the steady-state already-enrolled path runs on every poll and
was the only arming path that recorded no label, so whichever label was written
last stood for the life of the client.

A clear would have been the wrong instrument. #1901 deliberately put failure
labels into ``probe_outcomes`` so a probe that ran and was refused can be told
apart from one that never ran; clearing the dict at the wrong moment throws
that away. The fix is the write.
"""
from __future__ import annotations

import inspect

from custom_components.vag_connect import coordinator as coord_mod


# ── the stand-down log and the budget ──────────────────────────────────────


def _loop_source() -> str:
    """The poll loop. Named _poll_loop, not _async_update_data — the first
    version of this file guessed the latter and every assertion below failed
    for the wrong reason, which is its own small lesson about asserting
    against a method you have not looked up."""
    return inspect.getsource(coord_mod.VagConnectCoordinator._poll_loop)


def test_the_streak_is_only_counted_where_the_retry_runs() -> None:
    """The fix, pinned at the source.

    Driving the real loop here would mean standing up a coordinator plus a
    client plus a portal just to observe an integer, and the thing that was
    wrong is structural: the block was in the wrong place relative to the gate.
    So the assertion is that the counting is guarded by the same two
    conditions the scheduler uses.
    """
    src = _loop_source()
    assert "if not nightly and _portal is not None:" in src, (
        "the overdue-streak block is no longer gated on the retry actually "
        "being in play; a portal-less entry will count and log again"
    )
    # and the guard has to come BEFORE the increment, not after it
    guard = src.index("if not nightly and _portal is not None:")
    bump = src.index("self._drop_overdue_streak += 1")
    assert guard < bump, "the guard sits after the increment it is meant to gate"


def test_the_mark_moves_only_when_a_drop_actually_landed() -> None:
    """SUPERSEDES ``test_the_anchor_is_still_tracked_unconditionally``.

    That test guarded the opposite shape, and it was right for the field it
    guarded: ``_drop_anchor_seen`` held the previous poll's anchor including
    None, and tracking it unconditionally was deliberate. #1850's second round
    (@indigomejor, four restarts with the same anchor on every poll of the
    burst) retired that field. It could not survive a restart even if it were
    persisted — the first poll after one has not read the portal yet, so the
    unconditional write put None over the restored value and the second poll
    refilled the budget exactly as before.

    The replacement is a monotone high-water mark, and its invariant is the
    inverse: it must move ONLY inside the branch that found a real advance, and
    must never be assigned unconditionally. Unconditionally, a single poll that
    computes no capture at all would set it to None, and the next poll with an
    ordinary old capture would read "advanced" and hand the budget back — the
    restart bug replayed mid-run, without a restart.
    """
    src = _loop_source()
    lines = src.splitlines()
    assigns = [ln for ln in lines
               if ln.strip() == "self._drop_anchor_high_water = _cap_anchor"]
    assert len(assigns) == 1, (
        f"expected exactly one high-water assignment, found {len(assigns)}"
    )
    gate = next(ln for ln in lines
                if ln.strip() == "if not nightly and _portal is not None:")
    gate_indent = len(gate) - len(gate.lstrip())
    assign_indent = len(assigns[0]) - len(assigns[0].lstrip())
    assert assign_indent > gate_indent + 4, (
        f"the high-water assignment sits at indent {assign_indent} against a "
        f"gate at {gate_indent}; it must be inside the advance branch, not at "
        "the gate's level and not outside it"
    )
    # And it has to be the advance branch specifically, not the overdue one.
    advance = src.index("if _drop_anchor_advanced(")
    overdue = src.index("elif _drop_overdue(")
    mark = src.index("self._drop_anchor_high_water = _cap_anchor")
    assert advance < mark < overdue, (
        "the high-water assignment is not inside the advance branch"
    )


def test_a_change_to_the_budget_is_persisted() -> None:
    """#1850 second round — the streak is the half that holds the budget down.

    With only the mark persisted, a restart restores a streak of zero and the
    three fast polls happen anyway. So any change to either value has to reach
    the store, and it has to be reached from the decision block rather than
    only from the fresh-data path: a poll that brings no new snapshot is exactly
    when the streak climbs.
    """
    src = _loop_source()
    assert "self._drop_overdue_streak != _streak_before" in src, (
        "nothing detects a streak change, so nothing persists it"
    )
    # Scoped to the decision block, not to the whole loop. A bare presence
    # check passed with the call in this block replaced by ``pass``, because
    # the loop calls ``_save_vehicle_cache`` elsewhere too (after a poll that
    # brought fresh data) — measured with a mutation, which is the only reason
    # this is a window and not a substring.
    lines = src.splitlines()
    call = next(i for i, ln in enumerate(lines)
                if "sleep_s: float = _drop_anchored_sleep_s(" in ln)
    start = next(i for i, ln in enumerate(lines)
                 if "_decision_now = datetime.now(" in ln)
    window = [ln.strip() for ln in lines[start:call]]
    assert any("self._save_vehicle_cache()" in ln for ln in window), (
        f"the decision block never asks for a save: {window}"
    )


def test_the_message_still_exists_for_the_case_it_is_about() -> None:
    """Gating it must not amount to deleting it: on a portal entry whose feed
    has stopped, the stand-down is real and worth logging."""
    src = _loop_source()
    # The needle is the FORMAT string, not the prose. "polls with no fresh
    # snapshot" also appears in the comment explaining this fix, so asserting
    # that phrase passed even with the log deleted -- the mutation check caught
    # it. "%ds drop-retry" exists only in the real _LOGGER call.
    assert "%ds drop-retry" in src, (
        "the stand-down log is gone, not gated; on a portal entry whose feed "
        "has stopped the message is real and worth keeping"
    )
    assert "_DROP_RETRY_MAX_STREAK" in src


# ── the arming label ───────────────────────────────────────────────────────


def test_every_arming_path_records_what_it_did() -> None:
    """The steady-state path was the only one that did not.

    Counted at the source rather than asserted one by one, so a path added
    later without a label fails here instead of going quiet for a release.
    """
    import ast
    import textwrap

    src = inspect.getsource(coord_mod.VagConnectCoordinator._auto_enroll_skoda_official)
    # Counted from the syntax tree. Counting the text missed the call at the
    # no-mint path, which wraps as ``self._skoda_probe(\n "skoda_official",``
    # — the same fragility as counting a comment as a reader, one file over.
    tree = ast.parse(textwrap.dedent(src))
    arms = sum(
        1 for n in ast.walk(tree)
        if isinstance(n, ast.Call)
        and ast.unparse(n.func).endswith("_arm_official_from_map")
    )
    assert arms >= 3, f"expected at least three arming paths, found {arms}"

    # Each path's own label, by its text. Comparing TOTALS was the first
    # version of this and it was too weak: the gate's label ("gate: not a
    # native mysmob login") is written where nothing was armed, so it padded
    # the count to three and removing a real one still satisfied the test. The
    # mutation check is what showed that.
    for marker, path in (
        ("armed from", "the steady-state already-enrolled path"),
        ("no key minted", "the nothing-minted path"),
        ("enrolled (", "the mint path"),
    ):
        assert marker in src, (
            f"{path} no longer records what it did (looking for {marker!r}); "
            "a path that arms without a label leaves the previous one standing"
        )


def test_the_steady_state_path_has_its_own_label() -> None:
    """The specific one he hit, so the general count above cannot be satisfied
    by two labels on some other path."""
    src = inspect.getsource(coord_mod.VagConnectCoordinator._auto_enroll_skoda_official)
    assert "armed from" in src, (
        "the already-enrolled path no longer writes its own label"
    )


def test_the_label_is_pii_free() -> None:
    """It goes into shared diagnostics. A count of keys is fine; a key is not."""
    src = inspect.getsource(coord_mod.VagConnectCoordinator._auto_enroll_skoda_official)
    line = next(ln for ln in src.splitlines() if "armed from" in ln)
    assert "len(stored)" in line or "len(" in line, (
        f"the label may be interpolating key material: {line.strip()!r}"
    )
    for leak in ("stored[", "keys_map[", '["key"]'):
        assert leak not in line, f"the label interpolates {leak}"


def test_nothing_clears_the_probe_outcomes_wholesale() -> None:
    """The instrument this fix deliberately did NOT reach for.

    #1901 put failure labels in there so a refused probe is distinguishable
    from one that never ran. A blanket clear would undo that, so the only
    sweep that exists stays scoped to the ``channel:`` prefix.
    """
    import pathlib

    import custom_components.vag_connect as pkg

    offenders: list[str] = []
    for path in pathlib.Path(pkg.__file__).parent.rglob("*.py"):
        lines = path.read_text(encoding="utf-8").splitlines()
        for idx, line in enumerate(lines, 1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            if "probe_outcomes" not in stripped:
                continue
            if ".clear()" not in stripped and not stripped.endswith(
                "probe_outcomes = {}"
            ):
                continue
            # A defensive re-init is not a clear. Three sites write
            # ``self.probe_outcomes = {}`` guarded by ``if not isinstance(...)``
            # or ``if not hasattr(...)`` immediately before merging a
            # connector's outcomes up — base.py, porsche.py and vw_eu.py. The
            # first version of this check flagged all three and the failure was
            # mine, not theirs.
            window = " ".join(lines[max(0, idx - 3):idx])
            if "isinstance" in window or "hasattr" in window:
                continue
            offenders.append(f"{path.name}:{idx}")
    assert not offenders, (
        f"probe_outcomes is cleared wholesale at {offenders}; #1901's failure "
        "labels would be lost with it"
    )
