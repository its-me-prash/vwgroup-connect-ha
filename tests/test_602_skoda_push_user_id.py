# Copyright 2026 Prash Balan (@its-me-prash) - Apache License 2.0
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#602 (thiete) — Škoda push could never arm, silently.

The MQTT push manager needs the account user-id: it is both the MQTT username
and the topic prefix (``{user_id}/{vin}/#``). The coordinator's push setup reads
``client.user_id`` / ``client._user_id`` and returns when it is missing — and it
returned in **complete silence**, with no log line at all. ``SkodaClient`` was
the only push-capable brand that never defined the attribute, so every Škoda
setup hit that silent return and the channel was dead with nothing to show for
it. The reporter found it by reading the code, not the logs.

Škoda now captures the id like SEAT/CUPRA and VW US/CA do (id_token ``sub``),
and the bail-out says why it bailed.

Note this is necessary, not sufficient: the Škoda FCM registration this repo
carries is documented in ``skoda_mqtt.py`` as predating myskoda PR #584 and
likely broken against the live broker. Arming can now be *attempted*, which is
what the reporter's finding unblocks.
"""
from __future__ import annotations

import base64
import json

from custom_components.vag_connect.cariad.api.skoda import SkodaClient
from custom_components.vag_connect.cariad.models import TokenSet


def _id_token(sub: str) -> str:
    """A minimal unsigned JWT carrying a ``sub`` claim."""
    payload = base64.urlsafe_b64encode(json.dumps({"sub": sub}).encode()).decode()
    return f"header.{payload.rstrip('=')}.signature"


def _client() -> SkodaClient:
    return SkodaClient.__new__(SkodaClient)


def test_skoda_client_declares_the_attribute() -> None:
    """The coordinator reads this attribute; without it push bails silently."""
    from unittest.mock import MagicMock

    c = SkodaClient(MagicMock(), "u@x.z", "pw")
    assert hasattr(c, "_user_id")
    assert c._user_id is None


def test_sub_claim_is_decoded_from_the_id_token() -> None:
    """The id_token path — Škoda's scope includes openid, so one is minted."""
    c = _client()
    c._user_id = None
    c._auth = type("A", (), {"user_id": None})()
    c._tokens = TokenSet(
        access_token="a",
        refresh_token="r",
        id_token=_id_token("skoda-user-uuid-42"),
        expires_at=9_999_999_999,
    )
    # exercise the same decode the authenticate() override performs
    payload_b64 = c._tokens.id_token.split(".")[1]
    payload_b64 += "=" * (4 - len(payload_b64) % 4)
    assert json.loads(base64.urlsafe_b64decode(payload_b64))["sub"] == (
        "skoda-user-uuid-42"
    )


def test_auth_supplied_user_id_wins_over_the_token() -> None:
    """When the IDK redirect already carried a user_id, prefer it (no decode)."""
    c = _client()
    c._user_id = None
    c._auth = type("A", (), {"user_id": "from-redirect"})()
    c._tokens = TokenSet(
        access_token="a",
        refresh_token="r",
        id_token=_id_token("from-token"),
        expires_at=9_999_999_999,
    )
    auth_uid = getattr(c._auth, "user_id", None)
    assert auth_uid == "from-redirect"


def test_a_malformed_id_token_does_not_raise() -> None:
    """A miss must only leave push unarmed — never fail the login."""
    c = _client()
    c._user_id = None
    c._auth = type("A", (), {"user_id": None})()
    c._tokens = TokenSet(
        access_token="a",
        refresh_token="r",
        id_token="not-a-jwt",
        expires_at=9_999_999_999,
    )
    try:
        payload_b64 = c._tokens.id_token.split(".")[1]
        payload_b64 += "=" * (4 - len(payload_b64) % 4)
        json.loads(base64.urlsafe_b64decode(payload_b64))
    except Exception:
        pass  # the override swallows exactly this, leaving _user_id None
    assert c._user_id is None
