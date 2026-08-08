# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#759 — the per-VIN S-PIN reached unlock everywhere, but not seat/cupra lock.

`command_unlock(vin, spin="")` has always taken a per-VIN S-PIN on every brand.
`command_lock` only took one on vw_eu (audi/volkswagen). On seat/cupra, lock
used `self._get_sec_token(self._spin)` — the shared entry PIN captured at client
build — so a two-car SEAT/CUPRA account on different S-PINs would unlock the
right car and then fail to lock it. The coordinator resolved the per-VIN PIN,
presence-checked it, and dropped it on the floor.

The fix threads it through, mirroring unlock: `spin or self._spin`, so a
single-PIN setup is byte-identical to before.

There is one invariant that must not drift: the coordinator passes `spin=` only
to brands whose `command_lock` accepts it. Add a brand to the gate whose client
doesn't accept spin and every lock on it becomes a TypeError. The last test
here pins the gate and the signatures to each other so that can't happen
silently.
"""
from __future__ import annotations

import ast
import inspect
import pathlib

import pytest

_API = pathlib.Path(__file__).resolve().parents[1] / "custom_components/vag_connect/cariad/api"


def _command_lock_takes_spin(module: str) -> bool:
    src = (_API / f"{module}.py").read_text(encoding="utf-8")
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "command_lock":
            return "spin" in {a.arg for a in node.args.args}
    return False


class _SecTokenSpy:
    """Minimal seat/cupra client that records which PIN reached the sec-token."""

    def __init__(self, shared: str) -> None:
        self._spin = shared
        self.used: str | None = None

    async def _get_sec_token(self, spin: str) -> str:
        self.used = spin
        return "SECTOKEN"

    async def _post(self, url: str, **kw: object) -> None:
        return None


@pytest.mark.asyncio
async def test_per_vin_pin_reaches_seat_cupra_lock() -> None:
    from custom_components.vag_connect.cariad.api.seat_cupra import SeatCupraClient

    spy = _SecTokenSpy(shared="0000")
    await SeatCupraClient.command_lock(spy, "VIN", spin="4321")  # type: ignore[arg-type]
    assert spy.used == "4321", "the per-VIN S-PIN must reach the sec-token, not the shared one"


@pytest.mark.asyncio
async def test_single_pin_setup_is_unchanged() -> None:
    # No per-VIN override → empty spin → falls back to self._spin, exactly as
    # before the fix. This is the property that makes the change non-regressing.
    from custom_components.vag_connect.cariad.api.seat_cupra import SeatCupraClient

    spy = _SecTokenSpy(shared="0000")
    await SeatCupraClient.command_lock(spy, "VIN", spin="")  # type: ignore[arg-type]
    assert spy.used == "0000"


def test_lock_gate_matches_the_clients_that_accept_spin() -> None:
    # The coordinator's lock gate and the set of spin-accepting command_lock
    # signatures must be the same set of brands, or a mismatch is either a
    # dropped PIN (in the gate, client can't take it → wait, that TypeErrors)
    # or a silent shared-PIN fallback (client takes it, gate doesn't pass it).
    from custom_components.vag_connect import coordinator

    src = inspect.getsource(coordinator.VagConnectCoordinator.async_lock)
    # brands the coordinator will pass spin= to on lock
    gate = {
        b for b in ("audi", "volkswagen", "seat", "cupra", "skoda", "porsche")
        if f'"{b}"' in src.split("cmd_kwargs")[1].split("_cariad_cmd_optimistic")[0]
    }
    # v2.31.0 — skoda joined the gate: MyŠkoda 8.15.0 moved lock to v2
    # (AccessRequestDto{spin}), so Škoda lock accepts + wants the per-VIN S-PIN.
    assert gate == {"audi", "volkswagen", "seat", "cupra", "skoda"}, gate

    # audi/volkswagen are served by the vw_eu client; seat/cupra by seat_cupra;
    # skoda by skoda. Each of those clients' command_lock must accept spin.
    assert _command_lock_takes_spin("vw_eu")
    assert _command_lock_takes_spin("seat_cupra")
    assert _command_lock_takes_spin("skoda")

    # And the brands NOT in the gate must NOT be passed spin — porsche/vw_na
    # don't accept it. If a future edit adds spin to one of their signatures,
    # that's fine; but if it adds one to the GATE without the signature, this
    # test's gate assertion above already fails.
    for module in ("porsche", "vw_na", "base"):
        assert not _command_lock_takes_spin(module), (
            f"{module}.command_lock grew a spin param — if intended, add the "
            f"brand to the coordinator lock gate too, or the PIN is dropped"
        )
