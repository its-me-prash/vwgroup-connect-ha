# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""HA 2026.10 swapped voluptuous for probatio, and typing had to follow.

Home Assistant 2026.10 replaced voluptuous with ``probatio`` as its validation
engine and keeps old code working by aliasing the name: ``homeassistant``'s
package ``__init__`` calls ``probatio.compat.install_as_voluptuous()`` before
anything can import voluptuous, naming custom integrations as the reason. So
our schemas were never broken at runtime — only the type checker disagreed,
because the HA signatures we pass schemas into changed from one library's
``Schema`` to the other's.

Pinning either name is wrong on half the versions we support: against 2026.10
``voluptuous.Schema`` is rejected, and importing probatio instead reproduces
the same count mirrored against 2026.9 (measured, not assumed, and our manifest
floor is 2024.4.0). Hence one ``Any`` seam in ``_vol`` rather than thirty-one
ignores spread across six modules.

These tests exist to stop the wall coming back quietly: the first pins that
runtime behaviour is unchanged, and the second is the drift guard — a new
module importing voluptuous directly would put the errors straight back on the
next Home Assistant release, which is exactly how this one arrived.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

_PKG = Path(__file__).resolve().parents[1] / "custom_components" / "vag_connect"


# ── the seam does not change what runs ──────────────────────────────────────


def test_the_seam_hands_over_the_library_that_is_actually_installed() -> None:
    """``_vol.vol`` must BE the module ``import voluptuous`` yields, so that
    whatever Home Assistant has aliased into place is what we use."""
    import voluptuous

    from custom_components.vag_connect._vol import vol

    assert vol is voluptuous


def test_the_seam_still_builds_and_validates_a_schema() -> None:
    from custom_components.vag_connect._vol import vol

    schema = vol.Schema({vol.Required("vin"): str})
    assert schema({"vin": "X"}) == {"vin": "X"}
    with pytest.raises(Exception):
        schema({})


# ── the drift guard ─────────────────────────────────────────────────────────


def _integration_modules() -> list[Path]:
    return sorted(
        p for p in _PKG.rglob("*.py")
        if "__pycache__" not in p.parts and p.name != "_vol.py"
    )


def test_no_module_imports_the_validation_library_directly() -> None:
    """Everything goes through the seam. A direct import is how the 31 errors
    arrived, so it is the thing to catch — in review, not in a release."""
    direct = re.compile(r"^\s*(?:import\s+voluptuous|from\s+voluptuous\s+import)", re.M)
    offenders = [
        p.relative_to(_PKG).as_posix()
        for p in _integration_modules()
        if direct.search(p.read_text(encoding="utf-8"))
    ]
    assert not offenders, (
        "import vol from ._vol instead: " + ", ".join(offenders)
    )


def test_the_seam_itself_is_the_one_place_that_may() -> None:
    """Proves the guard above is not vacuous — it would catch a real import."""
    src = (_PKG / "_vol.py").read_text(encoding="utf-8")
    assert re.search(r"^import voluptuous as _voluptuous$", src, re.M)


def test_every_module_that_uses_vol_also_imports_it() -> None:
    """A module left using ``vol`` after a careless import removal would only
    fail at runtime, on whichever code path touches it."""
    uses = re.compile(r"\bvol\.")
    imports = re.compile(r"^from \.(?:\.)*_vol import vol$", re.M)
    missing = []
    for p in _integration_modules():
        src = p.read_text(encoding="utf-8")
        if uses.search(src) and not imports.search(src):
            missing.append(p.relative_to(_PKG).as_posix())
    assert not missing, f"use vol without importing it: {missing}"


# ── the repairs flow result ─────────────────────────────────────────────────


def test_repair_flow_steps_are_annotated_with_the_repairs_result() -> None:
    """HA 2026.10 parameterised RepairsFlow, so the bare FlowResult no longer
    matches what async_show_form returns in a repair flow."""
    src = (_PKG / "repairs.py").read_text(encoding="utf-8")
    code = "\n".join(
        line for line in src.split("\n") if not line.lstrip().startswith("#")
    )

    assert "-> RepairsFlowResult:" in code
    assert "data_entry_flow" not in code, "the unparameterised result is back"
    assert "from homeassistant.components.repairs import RepairsFlow, RepairsFlowResult" in code


def test_the_repairs_result_type_exists_on_the_installed_ha() -> None:
    """If a future HA drops the name, this fails here rather than as a red
    pipeline on an unrelated pull request."""
    from homeassistant.components.repairs import RepairsFlowResult

    assert RepairsFlowResult is not None
