# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#602: the Škoda push user-id survives a persisted-token restart.

Marco Schmidt (HA Tipps und Tricks Facebook group): enable_push_mqtt on, but
push_states was empty — the manager was never even constructed, because the
arming guard needs a user_id and SkodaClient only captured it inside the
interactive authenticate(). On a persisted-token restart that path never runs,
so user_id stayed None and the push channel silently never armed. The user_id
property now decodes the id_token 'sub' lazily off whatever tokens are loaded.
"""
from __future__ import annotations

import base64
import json


def _id_token(sub: str) -> str:
    def _b64(d: dict) -> str:
        return base64.urlsafe_b64encode(json.dumps(d).encode()).decode().rstrip("=")

    return f"{_b64({'alg': 'RS256'})}.{_b64({'sub': sub})}.sig"


def _client(user_id, id_token):
    from custom_components.vag_connect.cariad.api.skoda import SkodaClient

    c = SkodaClient.__new__(SkodaClient)
    c._user_id = user_id
    c._tokens = type("Tok", (), {"id_token": id_token})() if id_token is not None else None
    return c


def test_user_id_decoded_from_persisted_tokens_without_authenticate():
    c = _client(None, _id_token("acct-abc-123"))
    assert c.user_id == "acct-abc-123"      # no interactive authenticate() ran
    assert c._user_id == "acct-abc-123"     # and it is cached


def test_user_id_none_when_no_tokens():
    c = _client(None, None)
    assert c.user_id is None


def test_already_captured_id_is_not_re_decoded():
    c = _client("from-interactive-login", _id_token("different"))
    assert c.user_id == "from-interactive-login"


def test_sub_decoder_is_defensive():
    from custom_components.vag_connect.cariad.api.skoda import SkodaClient

    assert SkodaClient._sub_from_id_token(None) is None
    assert SkodaClient._sub_from_id_token("") is None
    assert SkodaClient._sub_from_id_token("not-a-jwt") is None
    assert SkodaClient._sub_from_id_token(_id_token("ok")) == "ok"
