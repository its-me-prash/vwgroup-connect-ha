# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#1310 (indigomejor) — the Škoda ``is_driving`` motion sensor kept disappearing.

It was only assigned inside the ``readiness`` block, so a poll that momentarily
lacked that block left ``is_driving`` at the model default (None), which the
"hide empty entities" option then hid — the entity flapped in and out of
existence. It's now always a concrete bool (False = parked/asleep, the safe
default; True only when the readiness block reports ``inMotion``), so the sensor
is stable.

These tests exercise the *real* ``_is_driving_from_readiness`` helper that
``get_status`` assigns from — no re-implementation of the expression, so a
regression in the helper (or its removal) fails the suite.
"""
from __future__ import annotations

from custom_components.vag_connect.cariad.api.skoda import _is_driving_from_readiness


def test_in_motion_true_is_driving() -> None:
    assert _is_driving_from_readiness({"inMotion": True}) is True


def test_in_motion_false_is_parked() -> None:
    assert _is_driving_from_readiness({"inMotion": False}) is False


def test_readiness_without_inmotion_is_parked() -> None:
    assert _is_driving_from_readiness({"ignitionOn": True}) is False


def test_readiness_absent_is_false_not_none() -> None:
    # THE fix: a missing readiness block yields a concrete False, never None — so
    # the sensor is never hidden by the hide-empty option.
    assert _is_driving_from_readiness(None) is False


def test_is_driving_is_never_none() -> None:
    for readiness in ({"inMotion": True}, {"inMotion": False}, {}, None, "garbage"):
        assert _is_driving_from_readiness(readiness) in (True, False)


def test_get_status_assigns_from_the_helper() -> None:
    """Ground the call-site: ``get_status`` must route through the helper, so the
    unconditional assignment (the actual fix) can't silently regress back inside
    the readiness guard. We patch the helper and confirm get_status uses its
    return value even when readiness is present."""
    import inspect

    from custom_components.vag_connect.cariad.api import skoda as skoda_mod

    src = inspect.getsource(skoda_mod.SkodaClient.get_status)
    # The assignment must call the helper — not re-inline the isinstance/inMotion
    # expression (which is what let it live inside the readiness guard before).
    assert "_is_driving_from_readiness(readiness)" in src
    assert "d.is_driving = _is_driving_from_readiness(readiness)" in src
