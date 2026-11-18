# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Marketplace categories in manifest.json (#2089).

Home Assistant 2026.11's Marketplace lists custom integrations by the
categories the catalog carries for them, and the catalog takes them from the
integration's manifest. hassfest (home-assistant/core script/hassfest/
manifest.py at 2026.11.2) accepts one to three unique ``categories`` of the
form ``parent`` or ``parent.sub``, refuses a parent next to its own
subcategory, and accepts a ``connectivity`` list; a ``hub`` may carry both.
This pins the shape, so a later edit cannot drop or malform them unnoticed.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

MANIFEST = Path(__file__).resolve().parents[1] / "custom_components" / "vag_connect" / "manifest.json"


def _manifest() -> dict:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def test_categories_have_the_shape_hassfest_accepts() -> None:
    cats = _manifest()["categories"]
    assert isinstance(cats, list) and 1 <= len(cats) <= 3
    assert len(set(cats)) == len(cats)
    for c in cats:
        assert re.fullmatch(r"[a-z0-9_]+(\.[a-z0-9_]+)?", c), c
    parents = {c for c in cats if "." not in c}
    assert not {c.split(".")[0] for c in cats if "." in c} & parents


def test_the_chosen_categories_and_connectivity() -> None:
    m = _manifest()
    assert m["categories"] == ["vehicles_transport.cars_evs", "energy.ev_charging"]
    assert m["connectivity"] == ["cloud"]
    assert m["integration_type"] == "hub"
