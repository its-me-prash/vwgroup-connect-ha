# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The indicator whose job is to report a frozen feed was itself frozen.

@Mex-ai11's Audi (#1851) served a snapshot nine days old while reporting
``data outdated: off``. Not why his data stopped — that is the manufacturer's
side — but why nobody was told.

``data_stale`` is computed in exactly one place, ``_enrich``, and ``_enrich``
only runs on a poll that parsed vehicle data. Every path that republishes the
previous snapshot instead carried the old verdict with it, and
``strip_runtime`` keeps every key without a leading underscore, so it reached
the on-disk store and came back on load. A *not stale* verdict decided while
the data was still fresh could therefore be saved, restored, and held through
every empty read afterwards — indefinitely (#1920).

The fix re-decides the verdict wherever a snapshot is republished. That needs
no fresh poll: the capture stamp is carried forward, so the age is knowable,
and a republished snapshot gets a verdict that is true *now* rather than true
when it was last read.

**No "values moved" exemption on a republish.** That exemption (#1688) exists
because a stamp can read old while readings change underneath it. On a
republish nothing has changed by definition, so applying it would answer "is
this stale" with "it was not, last time".
"""
from __future__ import annotations

import ast
import inspect
import pathlib
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from custom_components.vag_connect.const import CONF_SCAN_INTERVAL
from custom_components.vag_connect.coordinator import VagConnectCoordinator
from custom_components.vag_connect.repairs import STALE_DATA_MIN_AGE_S


def _coordinator(interval_min: int = 10) -> VagConnectCoordinator:
    coord = VagConnectCoordinator.__new__(VagConnectCoordinator)
    coord.hass = MagicMock()
    coord.entry = SimpleNamespace(
        entry_id="entry1",
        data={"brand": "audi"},
        options={CONF_SCAN_INTERVAL: interval_min},
    )
    return coord


def _snapshot(age_hours: float) -> dict:
    stamp = datetime.now(tz=timezone.utc) - timedelta(hours=age_hours)
    return {"vin": "WVWZZZAUZFW000000", "last_seen_at": stamp.isoformat()}


# ── the reported case ──────────────────────────────────────────────────────


def test_a_nine_day_old_snapshot_is_reported_stale() -> None:
    """His entry, as it actually was: a capture stamp from nine days ago and a
    verdict saying everything is fine."""
    coord = _coordinator()
    snap = _snapshot(9 * 24)
    snap["data_stale"] = False  # decided while the data was still fresh
    coord._redecide_stale(snap)
    assert snap["data_stale"] is True


def test_a_fresh_snapshot_is_not_reported_stale() -> None:
    """The other direction, so the fix cannot be "always say stale"."""
    coord = _coordinator()
    snap = _snapshot(1)
    snap["data_stale"] = True
    coord._redecide_stale(snap)
    assert snap["data_stale"] is False


def test_the_boundary_belongs_to_stale() -> None:
    """Exactly at the threshold counts as frozen.

    Pinned because ``>=`` versus ``>`` is a one-character difference that no
    other test here would notice: every other case sits far from the edge, and
    a feed that stopped exactly on the boundary is the one a user is most
    likely to be staring at when they come to report it.
    """
    coord = _coordinator()
    threshold_h = coord._stale_threshold_s() / 3600
    just_under = _snapshot(threshold_h - 0.01)
    exactly = _snapshot(threshold_h + 0.001)
    coord._redecide_stale(just_under)
    coord._redecide_stale(exactly)
    assert just_under["data_stale"] is False
    assert exactly["data_stale"] is True


def test_an_unknown_age_stays_unknown() -> None:
    """A snapshot with no capture stamp cannot answer the question, and
    guessing *either* way would be worse than saying so."""
    coord = _coordinator()
    snap = {"vin": "WVWZZZAUZFW000000", "data_stale": False}
    coord._redecide_stale(snap)
    assert snap["data_stale"] is None


# ── the threshold is the one _enrich uses ──────────────────────────────────


def test_the_floor_is_the_shared_constant() -> None:
    """A short poll interval must not drag the threshold below the floor: a
    parked car sleeps, and 72 hours is the figure chosen to clear that."""
    coord = _coordinator(interval_min=1)
    assert coord._stale_threshold_s() == STALE_DATA_MIN_AGE_S


def test_a_long_interval_raises_the_threshold() -> None:
    """Eight intervals, so a user who polls rarely is not told their feed is
    frozen simply because they asked for fewer reads."""
    coord = _coordinator(interval_min=600)  # 10 h
    assert coord._stale_threshold_s() == 8 * 600 * 60


def test_the_threshold_matches_the_one_enrich_computes() -> None:
    """Pinned against ``_enrich``'s own source. Two thresholds that drift
    apart would let the card and the indicator disagree about the same feed.
    """
    src = inspect.getsource(VagConnectCoordinator._enrich)
    # #2209: the inline copy is gone, _enrich asks the helper
    assert "_threshold_s = self._stale_threshold_s()" in src, (
        "_enrich must take its threshold from _stale_threshold_s"
    )
    helper = inspect.getsource(VagConnectCoordinator._stale_threshold_s)
    assert "max(hours * 3600, 8 * interval_s)" in helper


# ── the exemption that must NOT apply here ─────────────────────────────────


def test_a_republish_gets_no_values_moved_exemption() -> None:
    """#1688 lets a value that moved clear a stale stamp. On a republish
    nothing moved, so applying it would answer "is this stale" with "it was
    not, last time"."""
    src = inspect.getsource(VagConnectCoordinator._redecide_stale)
    body = ast.parse(_dedent(src)).body[0]
    assert isinstance(body, ast.FunctionDef)
    code = [
        ast.unparse(stmt)
        for stmt in body.body
        if not (isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant))
    ]
    joined = "\n".join(code)
    assert "_moved" not in joined and "_values_moved" not in joined, (
        f"the moved-values exemption reached the republish path: {joined}"
    )


def _dedent(src: str) -> str:
    import textwrap

    return textwrap.dedent(src)


# ── completeness: every republish path re-decides ──────────────────────────


_REPUBLISH_SHAPES = (
    "fresh[vin] = old",
    "fresh[vin] = self.vehicles.get(vin, {})",
    "self.vehicles[vin] = restored",
)


def test_every_republish_path_re_decides_the_verdict() -> None:
    """The half that matters most, and the reason this is structural.

    The defect was never one bad line — it was that *five* separate paths
    republished a snapshot and none of them re-decided. A sixth added later
    would reintroduce it silently, so each republishing line is required to
    have the re-decide in view.

    Its limit, stated rather than hidden: this recognises the three shapes
    those paths use today. A path that republishes by some other spelling
    would not be seen, which is why ``test_the_call_count_is_what_it_was``
    sits next to it.
    """
    import custom_components.vag_connect.coordinator as coord_mod

    lines = pathlib.Path(coord_mod.__file__).read_text(encoding="utf-8").splitlines()
    unguarded: list[str] = []
    for idx, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        if not any(shape in stripped for shape in _REPUBLISH_SHAPES):
            continue
        window = "\n".join(lines[max(0, idx - 4):idx + 1])
        if "_redecide_stale" not in window:
            unguarded.append(f"line {idx + 1}: {stripped}")
    assert not unguarded, (
        "these paths republish a previous snapshot without re-deciding its "
        f"freshness verdict: {unguarded}"
    )


def test_the_call_count_is_what_it_was() -> None:
    """A bound on the shape above.

    Five republishing paths plus the on-disk restore. If this number changes,
    either a path was added — and the test above should be read again — or one
    was removed and this file is describing history.
    """
    import custom_components.vag_connect.coordinator as coord_mod

    source = pathlib.Path(coord_mod.__file__).read_text(encoding="utf-8")
    calls = sum(
        1
        for line in source.splitlines()
        if "self._redecide_stale(" in line and not line.strip().startswith("#")
    )
    assert calls == 6, f"{calls} call sites, expected 6"


def test_the_restore_from_disk_re_decides() -> None:
    """The half a failed poll alone would not catch.

    ``strip_runtime`` drops only keys beginning with an underscore, so
    ``data_stale`` is written to the store and read back. Without this, a
    restart republishes a verdict the running session never computed.

    Scoped to the statements around the restore, not to the function holding
    it. The first version asked whether the enclosing function mentioned
    ``_redecide_stale`` anywhere — and that function is ``async_setup``, 934
    lines long with *two* such calls in it, so deleting the restore's own call
    left the test passing on the other one. Containment is not protection.
    """
    import custom_components.vag_connect.coordinator as coord_mod

    lines = pathlib.Path(coord_mod.__file__).read_text(encoding="utf-8").splitlines()
    sites = [
        idx
        for idx, line in enumerate(lines)
        if 'restored["_restored"] = True' in line and not line.strip().startswith("#")
    ]
    assert sites, "the restore path moved; this test cannot see it any more"
    for idx in sites:
        window = "\n".join(lines[idx:idx + 6])
        assert "_redecide_stale" in window, (
            f"the snapshot restored from disk at line {idx + 1} keeps its "
            "stored freshness verdict, which this session never computed"
        )


@pytest.mark.parametrize("age_hours", [0, 1, 71, 72, 73, 24 * 30])
def test_the_verdict_is_a_bool_or_none_never_a_string(age_hours: float) -> None:
    """It feeds a binary sensor. A truthy string would read as "on" forever."""
    coord = _coordinator()
    snap = _snapshot(age_hours)
    coord._redecide_stale(snap)
    assert snap["data_stale"] in (True, False, None)
