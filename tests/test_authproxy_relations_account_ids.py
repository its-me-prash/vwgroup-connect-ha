# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The authproxy relations read carries three account identifiers.

``GET .../authproxy/vw-de/proxy/v2/users/me/relations`` is recorded in the raw
section of the diagnostics download under
``vwde:app/authproxy/vw-de/proxy/v2/users/me/relations``. Its body names the
signed-in account three times: ``user.mbbUserId``, ``user.idKitUserId`` and, per
vehicle, ``relations[*].relationId``. The raw scrubber matches wire keys by exact
lowercased membership in ``_RAW_REDACT_KEYS``; ``userid`` was there, these three
spellings were not, and no value regex catches an opaque identifier. They went
out in cleartext in a section that is not opt-in.
"""
from __future__ import annotations

import json

import pytest

from custom_components.vag_connect.diagnostics import _RAW_REDACT_KEYS, _scrub_raw

# Invented values; the point is the KEY, not the value.
_MBB = "mbbuser0123456789abcdefghij"
_IDK = "idkit-user-0000-aaaa"
_REL = "relation-0000-bbbb"
_ENDPOINT = "vwde:app/authproxy/vw-de/proxy/v2/users/me/relations"


def _payload() -> dict:
    return {
        _ENDPOINT: {
            "user": {
                "mbbUserId": _MBB,
                "idKitUserId": _IDK,
                "legalEntityCode": "VWAG",
            },
            "relations": [
                {
                    "relationId": _REL,
                    "relationType": "OWNER_LIKE",
                    # already masked by the VIN rule
                    "vehicle": {"vin": "WVWZZZ**********000", "modBackend": "MBB"},
                    "role": "PRIMARY_USER",
                },
            ],
        },
    }


class TestAccountIdentifiersLeaveTheDownload:
    def test_none_of_the_three_values_survive_anywhere(self):
        blob = json.dumps(_scrub_raw(_payload()))
        assert _MBB not in blob
        assert _IDK not in blob
        assert _REL not in blob

    @pytest.mark.parametrize("key", ["mbbuserid", "idkituserid", "relationid"])
    def test_each_lowercased_key_is_registered(self, key):
        assert key in _RAW_REDACT_KEYS

    def test_the_keys_are_redacted_in_place_not_dropped(self):
        out = _scrub_raw(_payload())[_ENDPOINT]
        assert out["user"]["mbbUserId"] == "**REDACTED**"
        assert out["user"]["idKitUserId"] == "**REDACTED**"
        assert out["relations"][0]["relationId"] == "**REDACTED**"


class TestNegativeControl:
    def test_similar_shaped_keys_are_left_alone(self):
        out = _scrub_raw(_payload())[_ENDPOINT]
        assert out["relations"][0]["relationType"] == "OWNER_LIKE"
        assert out["user"]["legalEntityCode"] == "VWAG"
        assert out["relations"][0]["role"] == "PRIMARY_USER"
        assert out["relations"][0]["vehicle"]["modBackend"] == "MBB"

    def test_the_structure_the_export_exists_for_is_intact(self):
        out = _scrub_raw(_payload())[_ENDPOINT]
        assert set(out["user"]) == {"mbbUserId", "idKitUserId", "legalEntityCode"}
        assert set(out["relations"][0]) == {
            "relationId", "relationType", "vehicle", "role",
        }
