# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#2166 — a code entered in the config flow reaches the SEAT/CUPRA login.

@matroeh found that ``SeatCupraClient.authenticate(mfa_code=...)`` called the
base ``authenticate()`` without the argument, so the code the config flow
passes (``config_flow.py``: ``client.authenticate(mfa_code=mfa_code)``) arrived
at the IDK backend as ``None``. The Škoda override already forwards it; this
pins the SEAT/CUPRA one at the backend boundary, for a code and for none.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest


@pytest.mark.parametrize("brand", ["seat", "cupra"])
@pytest.mark.parametrize("code", ["123456", None])
def test_the_code_reaches_the_auth_backend(brand: str, code: str | None) -> None:
    from custom_components.vag_connect.cariad.api.seat_cupra import SeatCupraClient

    c = SeatCupraClient(MagicMock(), brand, "u@t.invalid", "pw")
    seen: dict[str, Any] = {}

    async def _backend_authenticate(_email: str, _password: str, **kw: Any) -> Any:
        seen.update(kw)
        return SimpleNamespace(access_token="tok", refresh_token="r", id_token=None,
                               expires_at=0.0, strategy="test")

    c._auth = SimpleNamespace(authenticate=_backend_authenticate, user_id="u-1")  # type: ignore[assignment]

    try:
        asyncio.new_event_loop().run_until_complete(c.authenticate(mfa_code=code))
    except Exception:  # noqa: BLE001 — only the backend boundary is under test
        pass

    assert "mfa_code" in seen, "the backend login was not reached"
    assert seen["mfa_code"] == code
