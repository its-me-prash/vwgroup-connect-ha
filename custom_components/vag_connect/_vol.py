# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The validation library Home Assistant is currently using, under one name.

Home Assistant 2026.10 replaced voluptuous with ``probatio`` as its validation
engine. It keeps our code working by aliasing the old name: ``homeassistant``'s
package ``__init__`` calls ``probatio.compat.install_as_voluptuous()`` before
anything can import voluptuous, and its comment names us as the reason —
"Custom integrations and a few dependencies still import voluptuous directly".
So at RUNTIME ``import voluptuous`` already hands us probatio on 2026.10 and
real voluptuous on everything older, and nothing about our schemas needs to
change. There is no user-visible bug here, and never was.

A type checker cannot be right about both, though, and that is the whole
problem this module exists to solve. The two libraries are distinct types to
mypy, and the HA signatures we pass schemas into changed from one to the other
in 2026.10: against 2026.10 our ``voluptuous.Schema`` is rejected, and if we
switched the import to probatio, the same 31 errors would reappear mirrored
against 2026.9 — measured, not assumed. Pinning either name makes the checker
wrong on one half of the versions we support, and our manifest floor is
2024.4.0.

So the schema factory is typed ``Any`` at this ONE seam instead of spreading
thirty-one ignores (or a version-dependent import) across six modules. What is
given up is type checking of our own schema construction, which voluptuous's
dynamic surface never really offered; what is kept is one documented place to
look when Home Assistant finishes the migration and drops the alias. At that
point this module becomes ``import probatio as vol`` and nothing else changes.

Import it as the drop-in it replaces::

    from ._vol import vol
"""
from __future__ import annotations

from typing import Any

import voluptuous as _voluptuous

# Deliberately Any — see the module docstring. Not a shortcut: a narrower type
# would have to name one of the two libraries, which is exactly the thing that
# cannot be right on both.
vol: Any = _voluptuous

__all__ = ["vol"]
