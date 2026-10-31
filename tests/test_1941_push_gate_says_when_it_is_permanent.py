"""#1941 (@philf90) — the push gate must not report a permanent stop as transient.

He enabled the Audi/VW push toggle, confirmed `enable_push_audi_vw: true` in
diagnostics, and got one line per setup:

    Push setup skipped: no user_id captured by the brand client

"captured" reads as "not captured *yet*", and the comment above the gate said
as much ("next refresh re-tries"). For his brand it never resolves: neither
``VWEUClient`` nor ``AudiClient`` assigns ``user_id`` or ``_user_id`` anywhere,
so the gate bails on every single setup. It was also logged at DEBUG, so a user
who had not turned debug logging on saw nothing at all.

What is pinned here is the gate's behaviour, not any client's shape — a client
that gains a user id later must not turn these tests red, because that would
make the real fix harder rather than easier:

* no user-id slot at all  → WARNING, once per entry, naming the brand, and
  saying plainly that it will not resolve on its own;
* slot present but empty  → DEBUG, with transient wording, every time.

Deliberately NOT pinned: that the Audi/VW toggle starts. The push manager ships
with an unverified subscription body by its own docstring, so making the toggle
reachable is a change that belongs with a tester on a real car.
"""
from __future__ import annotations

import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

_LOGGER_NAME = "custom_components.vag_connect.coordinator"


def _coordinator(client: object, *, brand: str = "volkswagen", vins=("WVW1",)):
    """A coordinator stripped to exactly what the gate reads."""
    from custom_components.vag_connect.coordinator import VagConnectCoordinator

    coord = VagConnectCoordinator.__new__(VagConnectCoordinator)
    coord.entry = SimpleNamespace(
        data={"brand": brand, "enable_push_audi_vw": True},
        options={},
        entry_id="01ABC",
    )
    coord._cariad_client = client
    coord.vehicles = dict.fromkeys(vins, object())
    coord._push_user_id_unsupported_logged = False
    coord.hass = MagicMock()
    return coord


class _NoSlot:
    """A brand client that never had a user-id concept (VW EU / Audi today)."""


class _EmptySlot:
    """A brand client that has the slot and has not filled it yet."""

    user_id = ""


async def _run(coord) -> None:
    await coord.async_start_push_managers()


@pytest.mark.asyncio
async def test_no_user_id_slot_warns_and_says_it_is_permanent(caplog) -> None:
    coord = _coordinator(_NoSlot())
    with caplog.at_level(logging.DEBUG, logger=_LOGGER_NAME):
        await _run(coord)

    warnings = [r for r in caplog.records if r.levelno >= logging.WARNING]
    assert warnings, (
        "a condition that cannot resolve was reported below WARNING, so the "
        "person who switched the toggle on sees nothing"
    )
    text = warnings[0].getMessage()
    assert "volkswagen" in text.lower(), "the warning must name the brand"
    assert "not resolve on its own" in text, (
        "the wording must not read as transient — that is the whole defect"
    )
    assert "1941" in text, "point at the tracking issue"


@pytest.mark.asyncio
async def test_the_permanent_warning_is_said_once_per_entry(caplog) -> None:
    coord = _coordinator(_NoSlot())
    with caplog.at_level(logging.DEBUG, logger=_LOGGER_NAME):
        await _run(coord)
        await _run(coord)
        await _run(coord)

    warnings = [r for r in caplog.records if r.levelno >= logging.WARNING]
    assert len(warnings) == 1, (
        f"{len(warnings)} warnings for three setups — a per-refresh warning "
        "becomes noise and gets filtered, which is how the first version of "
        "this line stopped being read"
    )


@pytest.mark.asyncio
async def test_an_unfilled_slot_stays_transient_and_quiet(caplog) -> None:
    """The case that really does resolve on its own keeps the old treatment."""
    coord = _coordinator(_EmptySlot())
    with caplog.at_level(logging.DEBUG, logger=_LOGGER_NAME):
        await _run(coord)

    assert not [r for r in caplog.records if r.levelno >= logging.WARNING], (
        "a transient state must not warn, or every cold start warns once"
    )
    debug = " ".join(
        r.getMessage() for r in caplog.records if r.levelno == logging.DEBUG
    )
    assert "not captured yet" in debug
    assert "re-tries" in debug


@pytest.mark.asyncio
async def test_no_vehicles_is_reported_as_its_own_reason(caplog) -> None:
    """Positive control: the gate's other branch still says which one it is."""
    coord = _coordinator(_EmptySlot(), vins=())
    with caplog.at_level(logging.DEBUG, logger=_LOGGER_NAME):
        await _run(coord)

    debug = " ".join(
        r.getMessage() for r in caplog.records if r.levelno == logging.DEBUG
    )
    assert "no vehicles known yet" in debug or "not captured yet" in debug, (
        f"the gate went quiet on an empty vehicle list: {debug!r}"
    )


@pytest.mark.asyncio
async def test_a_client_with_a_user_id_gets_past_the_gate(caplog) -> None:
    """The guard must not become the thing that blocks the real fix.

    A brand client that does produce a user id has to reach the code beyond
    this gate. Anything after it is mocked away — what is asserted is only
    that neither skip branch fired.
    """
    client = SimpleNamespace(user_id="u-123")
    coord = _coordinator(client)
    coord._start_push_for_brand = AsyncMock()
    with caplog.at_level(logging.DEBUG, logger=_LOGGER_NAME):
        try:
            await _run(coord)
        except Exception:  # noqa: BLE001 — anything past the gate is fine here
            pass

    text = " ".join(r.getMessage() for r in caplog.records)
    assert "Push setup skipped" not in text, (
        "a client WITH a user id was still skipped by the gate"
    )
