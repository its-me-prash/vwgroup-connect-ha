# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#1774 (@kalwados) — two config entries must not share one portal cookie jar.

He runs two Volkswagens on two config entries and saw **both cars on both hubs,
with neither working**. That symptom is the tell: the EU Data Act portal
authenticates with COOKIES rather than a bearer token, so the session's cookie
jar *is* the identity. Home Assistant hands every integration the same shared
client session, so the second entry's portal login overwrote the first one's
cookies in the same jar and both entries then read whichever car authenticated
last — which is why neither worked rather than one of them.

Only the portal connector is isolated. ``_session`` stays shared for the dozen
bearer-token APIs that do not care, because swapping those too would touch every
brand's auth path for nothing. The coordinator creates one jar-isolated session
per entry with ``async_create_clientsession`` — whose cleanup Home Assistant
ties to the config entry — and hands it over after construction, the same way
the locale and the MBB client id are handed over.

An earlier attempt replaced the session inside the connector and broke fifteen
unrelated tests, because ``async_create_clientsession`` reaches into Home
Assistant's frame helper and a mocked hass has never set it up. That is why the
hand-over is an attribute on an already-built client rather than a new keyword
threaded through the factory and five brand constructors.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from custom_components.vag_connect.cariad.api.base import CariadBaseClient


def _client(portal_session: object | None, shared: object) -> CariadBaseClient:
    c = CariadBaseClient(
        shared, MagicMock(name="brand"), "a@b.c", "pw",  # type: ignore[arg-type]
    )
    if portal_session is not None:
        c._portal_session = portal_session  # type: ignore[assignment]
    return c


def test_the_connector_gets_the_isolated_session_when_there_is_one() -> None:
    shared = object()
    own = object()
    c = _client(own, shared)
    assert (c._portal_session or c._session) is own


def test_two_entries_do_not_end_up_on_one_session() -> None:
    """The actual bug. Same shared session, two entries, two portal sessions —
    the connectors must not be handed the same object, or both entries write
    their cookies into one jar and the last login wins."""
    shared = object()
    a = _client(object(), shared)
    b = _client(object(), shared)
    assert (a._portal_session or a._session) is not (b._portal_session or b._session)
    # …while the shared session really is shared, which is the point of the
    # narrow fix: only the portal is isolated.
    assert a._session is b._session


def test_without_an_isolated_session_the_previous_behaviour_is_kept() -> None:
    """A caller that hands over nothing — the offline tooling, and every test
    that builds a client directly — must still work."""
    shared = object()
    c = _client(None, shared)
    assert c._portal_session is None
    assert (c._portal_session or c._session) is shared


@pytest.mark.asyncio
async def test_arm_eu_portal_really_uses_it() -> None:
    """The decisive one: it pins the live construction site rather than the
    expression. If someone reverts base.py to ``EUDataActConnector(self._session
    …)`` the three tests above keep passing and this one fails.
    """
    shared = MagicMock(name="shared-session")
    own = MagicMock(name="portal-session")
    c = _client(own, shared)
    c._email, c._password = "a@b.c", "pw"  # type: ignore[attr-defined]

    seen: list[object] = []

    class _Conn:
        def __init__(self, session: object, brand: str = "") -> None:
            seen.append(session)

        async def login(self, email: str, password: str) -> None:
            return None

    with patch(
        "custom_components.vag_connect.cariad.auth._eu_data_act.EUDataActConnector",
        _Conn,
    ):
        try:
            await c._arm_eu_portal()
        except Exception:
            # Arming does more than build the connector (tokens, sentinels); we
            # only care which session reached the constructor, and a later step
            # failing against a MagicMock brand is expected.
            pass

    assert seen, "the connector was never constructed — the test proves nothing"
    assert seen[0] is own, "the portal connector must get the isolated session"
    assert seen[0] is not shared
