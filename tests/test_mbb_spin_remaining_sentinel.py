# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Regression: the leg-1 ``remainingTries: -1`` sentinel must NOT block MBB commands.

Live evidence (Golf 7 GTE, 2026-07-22): the MBB S-PIN leg-1
(``security-pin-auth-requested`` / ``op-auth``) returns
``securityPinTransmission.remainingTries = -1`` for lock, unlock, climate-start
and charge-start. Leg-1 does NOT consume an attempt — ``-1`` is a
"not tracked / not applicable" sentinel, not a real countdown.

The old guard ``if remaining is not None and remaining < 2`` treated ``-1`` as
"only -1 attempts left" and raised ``SpinError`` at BOTH command sites
(vw_eu.py lock/unlock and the generic climate/charge/timer op), refusing EVERY
two-way MBB command on exactly the account state the evidence documents — the
write path was dead-on-arrival. ``spin_tries_low`` fixes it: only a GENUINE
0 or 1 blocks; a negative sentinel (and ``None``) proceeds.
"""

from __future__ import annotations


class TestSpinTriesLow:
    def test_minus_one_sentinel_does_not_block(self):
        """The core regression: leg-1's -1 sentinel must proceed, not block."""
        from custom_components.vag_connect.cariad._mbb import spin_tries_low

        assert spin_tries_low(-1) is False

    def test_any_negative_is_sentinel_not_countdown(self):
        from custom_components.vag_connect.cariad._mbb import spin_tries_low

        assert spin_tries_low(-2) is False
        assert spin_tries_low(-99) is False

    def test_none_unreported_does_not_block(self):
        from custom_components.vag_connect.cariad._mbb import spin_tries_low

        assert spin_tries_low(None) is False

    def test_genuine_last_attempts_still_block(self):
        """0 and 1 are real last-attempt warnings — keep refusing to avoid lockout."""
        from custom_components.vag_connect.cariad._mbb import spin_tries_low

        assert spin_tries_low(0) is True
        assert spin_tries_low(1) is True

    def test_two_or_more_proceeds(self):
        from custom_components.vag_connect.cariad._mbb import spin_tries_low

        assert spin_tries_low(2) is False
        assert spin_tries_low(3) is False
        assert spin_tries_low(255) is False


class TestParsePreservesMinusOne:
    def test_parser_keeps_minus_one_feeding_the_guard(self):
        """parse_mbb_spin_challenge preserves -1 (regression cause) — the guard,
        not the parser, is where the sentinel must be tolerated."""
        from custom_components.vag_connect.cariad._mbb import (
            parse_mbb_spin_challenge,
            spin_tries_low,
        )

        leg1 = {
            "securityPinAuthInfo": {
                "securityToken": "tok",
                "securityPinTransmission": {
                    "hashProcedureVersion": 2,
                    "challenge": "ABCD1234",
                    "remainingTries": -1,
                },
            }
        }
        token, challenge, remaining = parse_mbb_spin_challenge(leg1)
        assert token == "tok"
        assert challenge == "ABCD1234"
        assert remaining == -1
        # end to end: a -1 leg-1 must NOT trip the low-tries guard
        assert spin_tries_low(remaining) is False

    def test_genuine_one_try_left_trips_guard(self):
        from custom_components.vag_connect.cariad._mbb import (
            parse_mbb_spin_challenge,
            spin_tries_low,
        )

        leg1 = {
            "securityPinAuthInfo": {
                "securityToken": "tok",
                "securityPinTransmission": {
                    "challenge": "DEAD",
                    "remainingTries": 1,
                },
            }
        }
        _, _, remaining = parse_mbb_spin_challenge(leg1)
        assert remaining == 1
        assert spin_tries_low(remaining) is True
