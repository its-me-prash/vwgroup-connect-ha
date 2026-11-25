# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#1973 (@indigomejor) — the 5xx retry memory must survive a restart.

The first fix withholds the retries from a URL that already spent its whole
5xx budget for nothing. @indigomejor then measured what it does not cover: the
memory lived only in the running client, so after every restart each
always-failing endpoint got the full ladder again — four endpoints, four
requests each, about 21 s of waiting per restart.

The memory is now saved with the per-entry vehicle cache, next to the #1850
drop-retry budget, and restored defensively at setup. The rules pinned here:

* a restored entry gives the first poll after a restart ONE attempt, not four;
* a success still clears an entry, and the cleared entry is not saved again;
* restore never raises and ignores anything malformed;
* an entry not seen for more than 24 h is dropped, on save and on restore.
"""
from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest



def retry_memory_from_cache(*a: Any) -> Any:
    from custom_components.vag_connect.cariad import vehicle_cache

    return vehicle_cache.retry_memory_from_cache(*a)


def retry_memory_to_cache(*a: Any) -> Any:
    from custom_components.vag_connect.cariad import vehicle_cache

    return vehicle_cache.retry_memory_to_cache(*a)


# Synthetic VIN, see tests/test_no_real_vins.py.
_VIN = "WVWZZZAUZFW000000"
_READINESS = f"https://mysmob.api.connect.skoda-auto.cz/api/v2/connection-status/{_VIN}/readiness"
_UPDATE = (
    "https://mysmob.api.connect.skoda-auto.cz/api/v1/vehicle-information/"
    f"{_VIN}/software-version/update-status"
)
_NOW = 1_800_000_000.0
_DAY = 24 * 3600.0


class _Resp:
    def __init__(self, status: int) -> None:
        self.status = status
        self.headers: dict[str, str] = {"Content-Type": "application/json"}

    async def text(self, **_kw: Any) -> str:
        return "upstream said 500"

    async def json(self, **_kw: Any) -> Any:
        return {"ok": True}

    async def __aenter__(self) -> _Resp:
        return self

    async def __aexit__(self, *_exc: Any) -> None:
        return None


class _Session:
    def __init__(self, default: int = 500) -> None:
        self.default = default
        self.calls: list[str] = []

    def request(self, method: str, url: str, **_kw: Any) -> _Resp:
        self.calls.append(url)
        return _Resp(self.default)

    def count(self, url: str) -> int:
        return sum(1 for u in self.calls if u == url)


def _client(session: _Session) -> Any:
    from custom_components.vag_connect.cariad.api.skoda import SkodaClient

    c = SkodaClient(session, "u@t.invalid", "pw")  # type: ignore[arg-type]
    c._session = session  # type: ignore[assignment]
    c._tokens = SimpleNamespace(access_token="tok")  # type: ignore[assignment]
    return c


@pytest.fixture(autouse=True)
def _no_real_sleeping(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    from custom_components.vag_connect.cariad.api import base

    waits: list[float] = []

    async def _fake_sleep(seconds: float) -> None:
        waits.append(seconds)

    monkeypatch.setattr(base.asyncio, "sleep", _fake_sleep)
    return waits


def _get(c: Any, url: str) -> Any:
    from custom_components.vag_connect.cariad.exceptions import APIError

    try:
        return asyncio.new_event_loop().run_until_complete(c._request("GET", url))
    except APIError as err:
        return err


def _through_the_store(c: Any) -> Any:
    """What the .storage round trip does to the value: JSON, nothing else."""
    return json.loads(json.dumps(c.export_5xx_memory()))


# --------------------------------------------------------------------------
# The reported scenario, end to end through a client.
# --------------------------------------------------------------------------

class TestARestartDoesNotRefillTheBudget:
    def test_the_first_poll_after_a_restart_is_one_attempt(
        self, _no_real_sleeping: list[float],
    ) -> None:
        before = _Session()
        old = _client(before)
        _get(old, _READINESS)
        assert before.count(_READINESS) == 4, "positive control: full ladder"

        saved = _through_the_store(old)

        after = _Session()
        fresh = _client(after)
        _no_real_sleeping.clear()
        assert fresh.restore_5xx_memory(saved) == 1
        _get(fresh, _READINESS)
        assert after.count(_READINESS) == 1
        assert _no_real_sleeping == [], "a withheld retry must not wait either"

    def test_without_the_restore_the_ladder_comes_back(self) -> None:
        """The negative control: this is the bug, kept as a measurement."""
        after = _Session()
        _get(_client(after), _READINESS)
        assert after.count(_READINESS) == 4

    def test_an_endpoint_that_was_never_spent_still_gets_its_ladder(self) -> None:
        old = _client(_Session())
        _get(old, _READINESS)
        saved = _through_the_store(old)

        after = _Session()
        fresh = _client(after)
        fresh.restore_5xx_memory(saved)
        _get(fresh, _UPDATE)
        assert after.count(_UPDATE) == 4

    def test_a_success_clears_a_restored_entry(self) -> None:
        old = _client(_Session())
        _get(old, _READINESS)
        saved = _through_the_store(old)

        ok = _Session(default=200)
        fresh = _client(ok)
        fresh.restore_5xx_memory(saved)
        _get(fresh, _READINESS)
        assert fresh.export_5xx_memory() == {}, "a good answer withdraws the mark"
        # and the next outage spends the full budget again
        ok.default = 500
        before = ok.count(_READINESS)
        _get(fresh, _READINESS)
        assert ok.count(_READINESS) - before == 4

    def test_a_still_failing_restored_entry_stays_suppressed(self) -> None:
        old = _client(_Session())
        _get(old, _READINESS)
        saved = _through_the_store(old)

        after = _Session()
        fresh = _client(after)
        fresh.restore_5xx_memory(saved)
        for _ in range(3):
            _get(fresh, _READINESS)
        assert after.count(_READINESS) == 3

    def test_the_saved_form_carries_no_secret_beyond_the_path(self) -> None:
        old = _client(_Session())
        _get(old, _READINESS)
        text = json.dumps(old.export_5xx_memory())
        assert "tok" not in text and "pw" not in text and "u@t.invalid" not in text
        assert "?" not in text, "the query is stripped from the key"


class TestAnAgedEntryIsDropped:
    def test_older_than_a_day_is_not_restored(self) -> None:
        raw = retry_memory_to_cache({"GET /a": 2}, {"GET /a": _NOW - _DAY - 1}, _NOW - _DAY - 1, _DAY)
        assert retry_memory_from_cache(raw, _NOW, _DAY) == {}

    def test_just_under_a_day_is_kept(self) -> None:
        raw = {"GET /a": {"spent": 2, "at": _NOW - _DAY + 60}}
        assert retry_memory_from_cache(raw, _NOW, _DAY) == {
            "GET /a": (2, _NOW - _DAY + 60)
        }

    def test_the_save_side_drops_it_too(self) -> None:
        out = retry_memory_to_cache(
            {"GET /old": 1, "GET /new": 3},
            {"GET /old": _NOW - _DAY - 5, "GET /new": _NOW - 10},
            _NOW, _DAY,
        )
        assert list(out) == ["GET /new"]

    def test_an_entry_without_a_stamp_is_not_saved(self) -> None:
        assert retry_memory_to_cache({"GET /a": 1}, {}, _NOW, _DAY) == {}

    def test_a_future_stamp_is_clamped_not_trusted(self) -> None:
        """A wrong clock must not keep a mark alive for ever."""
        got = retry_memory_from_cache(
            {"GET /a": {"spent": 1, "at": _NOW + 10 * _DAY}}, _NOW, _DAY)
        assert got == {"GET /a": (1, _NOW)}

    def test_through_a_client_an_old_entry_gives_the_full_ladder(self) -> None:
        old = _client(_Session())
        _get(old, _READINESS)
        saved = _through_the_store(old)
        for entry in saved.values():
            entry["at"] = entry["at"] - 2 * _DAY

        after = _Session()
        fresh = _client(after)
        assert fresh.restore_5xx_memory(saved) == 0
        _get(fresh, _READINESS)
        assert after.count(_READINESS) == 4


class TestRestoreNeverRaises:
    @pytest.mark.parametrize("raw", [
        None, 0, 1.5, "x", [], [1, 2], {"GET /a": 1}, {"GET /a": "x"},
        {"GET /a": None}, {"GET /a": {}}, {"GET /a": {"spent": "2", "at": _NOW}},
        {"GET /a": {"spent": 2, "at": "now"}}, {"GET /a": {"spent": 2}},
        {"GET /a": {"spent": True, "at": _NOW}},
        {"GET /a": {"spent": 0, "at": _NOW}},
        {"GET /a": {"spent": -3, "at": _NOW}},
        {"GET /a": {"spent": 2, "at": True}},
        {"GET /a": {"spent": 2, "at": float("nan")}},
        {"GET /a": {"spent": 2, "at": float("inf")}},
        {"": {"spent": 1, "at": _NOW}},
        {7: {"spent": 1, "at": _NOW}},
        {"x" * 5000: {"spent": 1, "at": _NOW}},
    ])
    def test_malformed_input_restores_nothing(self, raw: Any) -> None:
        assert retry_memory_from_cache(raw, _NOW, _DAY) == {}
        c = _client(_Session())
        assert c.restore_5xx_memory(raw) == 0
        assert c.export_5xx_memory() == {}

    def test_one_bad_entry_does_not_cost_the_good_one(self) -> None:
        raw = {
            "GET /bad": {"spent": "x", "at": _NOW},
            "GET /good": {"spent": 2, "at": _NOW - 5},
        }
        assert retry_memory_from_cache(raw, _NOW, _DAY) == {
            "GET /good": (2, _NOW - 5)
        }

    def test_an_edited_store_cannot_grow_the_memory_without_bound(self) -> None:
        raw = {f"GET /p{i}": {"spent": 1, "at": _NOW} for i in range(5000)}
        assert len(retry_memory_from_cache(raw, _NOW, _DAY)) <= 64

    def test_a_huge_count_is_clamped(self) -> None:
        got = retry_memory_from_cache(
            {"GET /a": {"spent": 10**12, "at": _NOW}}, _NOW, _DAY)
        assert 1 <= got["GET /a"][0] <= 1000

    def test_restore_does_not_overwrite_what_the_live_client_already_knows(self) -> None:
        c = _client(_Session())
        _get(c, _READINESS)
        _get(c, _READINESS)  # suppressed poll; count is 1
        key = next(iter(c.export_5xx_memory()))
        c.restore_5xx_memory({key: {"spent": 9, "at": _NOW}})
        assert c.export_5xx_memory()[key]["spent"] == 1


class TestOtherClientsAreUnaffected:
    def test_a_client_that_never_saw_a_5xx_exports_nothing(self) -> None:
        assert _client(_Session(default=200)).export_5xx_memory() == {}

    def test_a_client_built_without_init_still_exports_and_restores(self) -> None:
        from custom_components.vag_connect.cariad.api.skoda import SkodaClient

        c = SkodaClient.__new__(SkodaClient)
        assert c.export_5xx_memory() == {}
        assert c.restore_5xx_memory({"GET /a": {"spent": 1, "at": _NOW - 1}}) in (0, 1)

    def test_the_shared_base_is_the_only_owner(self) -> None:
        """Every client built on the base gets the same two methods; the ones
        that are not (Porsche, VW NA, companion) are skipped by the coordinator
        through ``getattr``, so a brand without the memory is not touched."""
        from custom_components.vag_connect.cariad.api.base import CariadBaseClient
        from custom_components.vag_connect.cariad.api.porsche import PorscheClient

        assert hasattr(CariadBaseClient, "export_5xx_memory")
        assert not hasattr(PorscheClient, "export_5xx_memory")


# --------------------------------------------------------------------------
# Wiring: the coordinator has to write what it later reads.
# --------------------------------------------------------------------------

def _coordinator_src() -> str:
    path = (Path(__file__).parent.parent / "custom_components" / "vag_connect"
            / "coordinator.py")
    return path.read_text(encoding="utf-8")


def test_the_snapshot_key_written_is_the_key_setup_reads() -> None:
    src = _coordinator_src()
    written = re.findall(r'"([A-Za-z_0-9]+)":\s*_retry_5xx_snapshot\(', src)
    assert len(written) == 1, f"expected one written key, found {written}"
    read = re.findall(r'cached\.get\("([A-Za-z_0-9]+)"\)\s*,?\s*\)?\s*#\s*5xx-restore', src)
    assert read == written, (
        f"the snapshot writes {written} but setup reads {read}; the memory "
        "would be saved and never restored"
    )


def test_the_snapshot_helper_survives_a_client_without_the_memory() -> None:
    from custom_components.vag_connect.coordinator import _retry_5xx_snapshot

    assert _retry_5xx_snapshot(None) == {}
    assert _retry_5xx_snapshot(object()) == {}
    assert _retry_5xx_snapshot(SimpleNamespace(export_5xx_memory=lambda: 5)) == {}

    def _boom() -> dict[str, Any]:
        raise RuntimeError("x")

    assert _retry_5xx_snapshot(SimpleNamespace(export_5xx_memory=_boom)) == {}


def test_the_snapshot_helper_passes_the_clients_memory_through() -> None:
    from custom_components.vag_connect.coordinator import _retry_5xx_snapshot

    c = _client(_Session())
    _get(c, _READINESS)
    snap = _retry_5xx_snapshot(c)
    assert snap and json.loads(json.dumps(snap)) == snap
