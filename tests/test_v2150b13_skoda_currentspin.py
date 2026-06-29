# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""b13 (RE myskoda 8.13.0) — Škoda unlock S-PIN body uses ``currentSpin``.

The live MyŠkoda app's SpinDto wire key is ``currentSpin``; it never sends a
bare ``spin`` key, so our old payload was rejected by the mysmob backend.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

from custom_components.vag_connect.cariad.api.skoda import SkodaClient


def _client() -> SkodaClient:
    c = SkodaClient(MagicMock(), "u@t.de", "pw")
    c._post = AsyncMock(return_value={})
    return c


def test_unlock_sends_currentSpin_not_spin() -> None:
    c = _client()
    asyncio.run(c.command_unlock("TMBVIN0000000001", spin="1234"))
    body = c._post.call_args.kwargs["json"]
    assert body == {"currentSpin": "1234"}
    assert "spin" not in body  # the rejected bare-spin key is gone


def test_unlock_without_spin_sends_empty_body() -> None:
    c = _client()
    c._spin = ""
    asyncio.run(c.command_unlock("TMBVIN0000000001"))
    assert c._post.call_args.kwargs["json"] == {}
