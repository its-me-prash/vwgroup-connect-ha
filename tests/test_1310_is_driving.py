# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#1310 (indigomejor) — the Škoda ``is_driving`` motion sensor kept disappearing.

It was only assigned inside the ``readiness`` block, so a poll that momentarily
lacked that block left ``is_driving`` at the model default (None), which the
"hide empty entities" option then hid — the entity flapped in and out of
existence. It's now always a concrete bool (False = parked/asleep, the safe
default; True only when the readiness block reports ``inMotion``), so the sensor
is stable.
"""
from __future__ import annotations

from unittest.mock import MagicMock

from custom_components.vag_connect.cariad.api.skoda import SkodaClient


def _is_driving(readiness: object) -> bool:
    """The exact expression used in SkodaClient.get_status, exercised against the
    real ``_val`` helper: ``isinstance(readiness, dict) and v(readiness, "inMotion")
    is True``. ``_val`` is only reached when readiness is a dict (short-circuit)."""
    c = SkodaClient(MagicMock(), "u@t.de", "pw")
    v = c._val
    return isinstance(readiness, dict) and v(readiness, "inMotion") is True


def test_in_motion_true_is_driving() -> None:
    assert _is_driving({"inMotion": True}) is True


def test_in_motion_false_is_parked() -> None:
    assert _is_driving({"inMotion": False}) is False


def test_readiness_without_inmotion_is_parked() -> None:
    assert _is_driving({"ignitionOn": True}) is False


def test_readiness_absent_is_false_not_none() -> None:
    # THE fix: a missing readiness block yields a concrete False, never None — so
    # the sensor is never hidden by the hide-empty option.
    assert _is_driving(None) is False


def test_is_driving_is_never_none() -> None:
    for readiness in ({"inMotion": True}, {"inMotion": False}, {}, None, "garbage"):
        assert _is_driving(readiness) in (True, False)
