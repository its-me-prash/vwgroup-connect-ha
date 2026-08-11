# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#1135 (@Fishermanjb) — the ABRP "data changed" binary sensor is a latched
level flag that only clears on a SUCCESSFUL upload. The shipped blueprint
triggered ONLY on the OFF->ON edge, so if the single upload on that edge failed
(a transient ABRP/network error) the sensor stayed welded ON and, with an
edge-only trigger, never fired again — silently stranding every later upload.

The fix adds a periodic ``time_pattern`` re-check gated on the sensor still being
``on``, so a stuck flag self-heals on the next tick. This test locks that shape
into the blueprint so it can't silently regress to edge-only.
"""
from __future__ import annotations

from pathlib import Path

import yaml

_BLUEPRINT = (
    Path(__file__).resolve().parent.parent
    / "blueprints" / "automation" / "vag_connect"
    / "abrp_upload_on_data_change.yaml"
)


class _BlueprintLoader(yaml.SafeLoader):
    """SafeLoader that tolerates Home Assistant's ``!input`` blueprint tag."""


def _construct_input(loader: yaml.Loader, node: yaml.Node) -> dict:
    return {"__input__": loader.construct_scalar(node)}


_BlueprintLoader.add_constructor("!input", _construct_input)


def _load() -> dict:
    return yaml.load(_BLUEPRINT.read_text(encoding="utf-8"), Loader=_BlueprintLoader)


def _as_list(node: object) -> list:
    return node if isinstance(node, list) else [node]


def test_blueprint_parses() -> None:
    doc = _load()
    assert doc["blueprint"]["domain"] == "automation"


def test_has_both_the_edge_and_the_periodic_trigger() -> None:
    """The immediate edge stays, AND a periodic safety net is added."""
    triggers = _as_list(_load()["trigger"])
    platforms = [t.get("platform") for t in triggers]
    assert "state" in platforms, "the immediate data-changed edge trigger is gone"
    assert "time_pattern" in platforms, (
        "no periodic re-check — a failed edge upload would strand forever (#1135)"
    )
    # the state trigger still fires on turning ON
    state_trig = next(t for t in triggers if t.get("platform") == "state")
    assert state_trig.get("to") == "on"


def test_periodic_run_is_gated_on_the_flag_still_being_on() -> None:
    """Without a state==on guard, the time_pattern trigger would fire abrp_send
    even when there is nothing to upload — the guard is what makes it a safe
    self-heal rather than a blind periodic spam."""
    conditions = _as_list(_load()["condition"])
    assert any(
        c.get("condition") == "state" and c.get("state") == "on"
        for c in conditions
    ), "no 'sensor is still on' guard — periodic trigger would send with no data"


def test_edge_dedup_guard_survives_for_the_state_trigger() -> None:
    """The attribute-only re-fire guard must still be present so a state trigger
    that re-fires on->on doesn't double-upload; the periodic trigger is exempted
    from it (it has no from/to state)."""
    conditions = _as_list(_load()["condition"])
    tmpl = " ".join(
        str(c.get("value_template", "")) for c in conditions
        if c.get("condition") == "template"
    )
    assert "from_state" in tmpl
    assert "time_pattern" in tmpl, (
        "template guard must exempt the periodic trigger (no from/to state)"
    )
