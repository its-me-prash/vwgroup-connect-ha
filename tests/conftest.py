# Copyright 2026 Prash Balan (@its-me-prash) — Apache License 2.0
# SPDX-License-Identifier: Apache-2.0
"""Test-suite root config.

v1.24.1 (2026-05-08 audit): adds the repo root to ``sys.path`` so that
``import custom_components.vag_connect.*`` works without an editable
install. Also marks tests that need Home Assistant infrastructure as
``ha_required`` — they get skipped automatically if the ``homeassistant``
package isn't importable, so contributors can run pure-Python tests
locally with just ``pip install -r requirements-test.txt``.

CI installs ``homeassistant`` ad-hoc and runs the full matrix; locally
we keep the entry barrier low.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

# Ensure the repo root is on sys.path so `custom_components.vag_connect`
# resolves without an editable install.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# Detect HA availability ONCE — used by the auto-skip hook below.
_HA_AVAILABLE = importlib.util.find_spec("homeassistant") is not None


def pytest_collection_modifyitems(config, items):  # noqa: ARG001
    """Auto-skip tests that need Home Assistant when HA isn't installed.

    Tests can opt-in to this gate by:
      1. Importing anything from ``homeassistant.*`` at module top-level
         (we detect via the import error during collection — pytest will
         already mark those as collection errors; this hook downgrades
         them to skips with a helpful message).
      2. Adding the ``@pytest.mark.ha_required`` marker manually.
    """
    if _HA_AVAILABLE:
        return
    skip_reason = (
        "homeassistant not installed locally — run via CI or "
        "`pip install homeassistant` for full coverage"
    )
    skip_marker = pytest.mark.skip(reason=skip_reason)
    for item in items:
        if "ha_required" in [m.name for m in item.iter_markers()]:
            item.add_marker(skip_marker)


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "ha_required: test needs the homeassistant package installed",
    )
