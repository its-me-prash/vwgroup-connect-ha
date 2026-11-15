# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Audi connect plug&play: the sign-in's tokens survive a restart (#118).

#118 was "after every update the password must be entered again". v1.19.2
answered it by writing the token set to Home Assistant's storage and loading it
at setup, in the base client every European brand shares. The plug&play cloud
client is not a base client, and the two hooks never reached it: the
coordinator assigned the save callback on it and nothing ever called it.

Measured before this change, with the coordinator's real setup, the real
client and the real storage: one full sign-in per setup run, no token file
after the sign-in and none after a token refresh. And a token file that was
already there, left by the brand the entry had before it was switched to
plug&play in Reconfigure, stopped the entry for good: the coordinator handed
the loaded set to a method this client did not have.

What is replaced here and what is not. Replaced: the HTTP session, the files
(one dict that outlives the client, as the files on disk outlive a restart)
and the walk through the sign-in pages, which is cut down to "count one
sign-in, hand back a token set". Real: the client, its refresh, the token
parsing, the storage, and in the last group the coordinator's setup.

Storing the tokens brings four cases with it, and each has its tests below:

* a stored session the server no longer takes must cost one sign-in, not the
  entry. The vehicle list used to come back empty on a refused session, which
  setup read as "no cars", and every later start met the same file.
* a set another brand's client stored is not this client's to use.
* the storage keeps a set only if it has an id_token, and a refresh answer
  may leave it out. The one from the sign-in is carried over.
* a release from before this change cannot take a stored set for this brand,
  so this brand's file is written under a version those releases discard.
"""
from __future__ import annotations

import base64
import copy
import json
import threading
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.vag_connect.cariad.api.plugandplay import (
    PlugAndPlayCloudClient,
)
from custom_components.vag_connect.cariad.auth._token_storage import (
    TokenStorage,
    payload_version_for_brand,
)
from custom_components.vag_connect.cariad.auth.idk import IDKAuth
from custom_components.vag_connect.cariad.exceptions import AuthenticationError
from custom_components.vag_connect.cariad.models import BRAND_AUDI_ACPP, TokenSet

_VIN = "WAUZZZ8T0AA000001"  # synthetic, padded counter serial
_SUB = "00000000-0000-4000-8000-000000000001"  # synthetic account id
_KEY = "vag_connect_tokens_test"
_CACHE_KEY = "vag_connect_vehicles_test"
_BRAND = "audi_acpp"
_HTTP = "homeassistant.helpers.aiohttp_client"
_LIVE_ODOMETER = 1000
_CACHED_ODOMETER = 777


def _jwt(claims: dict[str, Any]) -> str:
    body = base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip("=")
    return f"e30.{body}.sig"


# ── the files ────────────────────────────────────────────────────────────────
class _Store:
    """Home Assistant's Store, reduced to the calls the integration makes.

    ``files`` is the disk: it outlives every client and every coordinator, so
    a second start reads what the first one wrote.
    """

    files: dict[str, Any] = {}
    fail_saves_for: set[str] = set()

    def __init__(self, hass: Any, version: int, key: str, *a: Any, **k: Any) -> None:
        self.key = key

    async def async_load(self) -> Any:
        return copy.deepcopy(self.files.get(self.key))

    async def async_save(self, data: Any) -> None:
        if self.key in self.fail_saves_for:
            raise OSError("disk full")
        self.files[self.key] = json.loads(json.dumps(data, default=str))

    async def async_remove(self) -> None:
        self.files.pop(self.key, None)

    def async_delay_save(self, *a: Any, **k: Any) -> None:
        return None


@pytest.fixture
def files() -> dict[str, Any]:
    _Store.files = {}
    _Store.fail_saves_for = set()
    return _Store.files


def _stored(files: dict[str, Any]) -> dict[str, Any]:
    """The token part of the token file, or an empty dict when there is none."""
    return dict((files.get(_KEY) or {}).get("tokens") or {})


# ── the wire ─────────────────────────────────────────────────────────────────
class _Resp:
    url = "https://wire.invalid/"
    headers: dict[str, str] = {}
    history: tuple[Any, ...] = ()

    def __init__(self, status: int, body: Any = None) -> None:
        self.status = status
        self._body = {} if body is None else body

    async def __aenter__(self) -> "_Resp":
        return self

    async def __aexit__(self, *exc: Any) -> bool:
        return False

    async def json(self, *a: Any, **k: Any) -> Any:
        return self._body

    async def text(self, *a: Any, **k: Any) -> str:
        return json.dumps(self._body)


class _Wire:
    """The plug&play cloud: the vehicle list, one car, and the refresh grant.

    ``refused`` names the access tokens the cloud no longer takes. Naming them
    is deliberate: a counter ("refuse the next read") cannot tell a stored
    token from one a sign-in in the same start just produced.
    """

    def __init__(self) -> None:
        self.refresh_forms: list[dict[str, Any]] = []
        self.reads: list[tuple[str, str]] = []  # (path, access token used)
        self.refused: set[str] = set()
        self.refresh_status = 200
        self.refresh_carries_id_token = True

    def post(self, url: str, **kwargs: Any) -> _Resp:
        form = kwargs.get("data")
        if isinstance(form, dict) and form.get("grant_type") == "refresh_token":
            self.refresh_forms.append({"url": str(url), **form})
            if self.refresh_status != 200:
                return _Resp(self.refresh_status, {"error": "invalid_grant"})
            n = len(self.refresh_forms)
            answer = {
                "access_token": f"access-refresh{n}",
                "refresh_token": f"refresh-refresh{n}",
            }
            if self.refresh_carries_id_token:
                answer["id_token"] = _jwt({"sub": _SUB, "n": n})
            return _Resp(200, answer)
        return _Resp(200, {})

    def get(self, url: str, **kwargs: Any) -> _Resp:
        return self.request("GET", url, **kwargs)

    def request(self, method: str, url: str, **kwargs: Any) -> _Resp:
        auth = str((kwargs.get("headers") or {}).get("Authorization", ""))
        token = auth.removeprefix("Bearer ").strip()
        path = str(url).split("acpp.cariad.digital/", 1)[-1]
        self.reads.append((path, token))
        if token in self.refused:
            return _Resp(401, {"message": "unauthorized"})
        if path == "vehicles":
            return _Resp(200, [{"vehicle": {"id": 1, "vin": _VIN}}])
        if path == f"vehicle/{_VIN}":
            return _Resp(200, {
                "vehicle": {"id": 1, "vin": _VIN, "carPlatform": "KWP2000"},
                "odometer": float(_LIVE_ODOMETER),
            })
        if "acpp.cariad.digital" in str(url):
            return _Resp(404, {"message": "not found"})
        return _Resp(200, {})

    def list_reads(self) -> list[str]:
        """Access tokens that were used to ask for the vehicle list, in order."""
        return [token for path, token in self.reads if path == "vehicles"]


# ── the sign-in ──────────────────────────────────────────────────────────────
class _SignIns(list[str]):
    """Every full sign-in, in order. ``with_id_token`` shapes the answer."""

    with_id_token = True


@pytest.fixture(autouse=True)
def signins(monkeypatch: pytest.MonkeyPatch) -> _SignIns:
    """The page walk itself is not under test, and must never run for real."""
    seen = _SignIns()

    async def _signin(self: Any, email: str, password: str, **kw: Any) -> TokenSet:
        seen.append(email)
        n = len(seen)
        return TokenSet(
            access_token=f"access-signin{n}",
            refresh_token=f"refresh-signin{n}",
            id_token=_jwt({"sub": _SUB}) if seen.with_id_token else "",
        )

    monkeypatch.setattr(IDKAuth, "authenticate", _signin)
    return seen


def _storage() -> TokenStorage:
    """The storage the way the coordinator builds it for this brand."""
    return TokenStorage(
        _Store(None, 1, _KEY), payload_version=payload_version_for_brand(_BRAND),
    )


def _client(wire: _Wire) -> tuple[PlugAndPlayCloudClient, TokenStorage]:
    """A client wired to the token file the way the coordinator wires it."""
    client = PlugAndPlayCloudClient(
        wire, BRAND_AUDI_ACPP, "owner@example.invalid", "pw",
    )
    storage = _storage()
    client.on_tokens_changed = storage.save
    return client, storage


async def _restarted(wire: _Wire) -> PlugAndPlayCloudClient:
    """A new client that is handed whatever the token file holds."""
    client, storage = _client(wire)
    client.set_persisted_tokens(await storage.load())
    return client


# ── 1. what is written ───────────────────────────────────────────────────────
async def test_a_sign_in_is_written_to_the_token_file(
    files: dict[str, Any], signins: _SignIns,
) -> None:
    client, _ = _client(_Wire())
    await client.authenticate()

    assert len(signins) == 1
    assert _stored(files).get("access_token") == "access-signin1"
    assert _stored(files).get("refresh_token") == "refresh-signin1"
    # the set says which brand's client stored it
    assert _stored(files).get("strategy") == _BRAND


async def test_a_token_refresh_is_written_to_the_token_file(
    files: dict[str, Any], signins: _SignIns,
) -> None:
    """The refresh token changes with every refresh. A file that still held
    the one from the sign-in would be of no use after the first hour."""
    wire = _Wire()
    client, _ = _client(wire)
    await client.authenticate()

    wire.refused = {"access-signin1"}
    assert await client.get_vehicles() == [_VIN]

    assert len(wire.refresh_forms) == 1
    assert wire.refresh_forms[0]["refresh_token"] == "refresh-signin1"
    assert _stored(files).get("access_token") == "access-refresh1"
    assert _stored(files).get("refresh_token") == "refresh-refresh1"
    assert len(signins) == 1


async def test_a_refresh_answer_without_an_id_token_is_still_written(
    files: dict[str, Any],
) -> None:
    """The storage keeps a set only if it has an id_token. A refresh answer
    may leave it out; nothing reads this client's id_token, so the one from
    the sign-in is as good, and without it the file would keep a refresh token
    that has just been replaced."""
    wire = _Wire()
    wire.refresh_carries_id_token = False
    client, _ = _client(wire)
    await client.authenticate()
    signed_in_id_token = _stored(files).get("id_token")

    wire.refused = {"access-signin1"}
    assert await client.get_vehicles() == [_VIN]

    assert _stored(files).get("refresh_token") == "refresh-refresh1"
    assert _stored(files).get("id_token") == signed_in_id_token != ""


async def test_a_refresh_answer_with_an_id_token_replaces_the_stored_one(
    files: dict[str, Any],
) -> None:
    """Control for the test above: carrying the old one over is only for the
    answer that has none."""
    wire = _Wire()
    client, _ = _client(wire)
    await client.authenticate()
    signed_in_id_token = _stored(files).get("id_token")

    wire.refused = {"access-signin1"}
    assert await client.get_vehicles() == [_VIN]

    assert _stored(files).get("id_token") not in ("", signed_in_id_token)


async def test_a_token_file_that_cannot_be_written_does_not_break_the_sign_in(
    files: dict[str, Any], signins: _SignIns,
) -> None:
    _Store.fail_saves_for = {_KEY}
    wire = _Wire()
    client, _ = _client(wire)

    await client.authenticate()
    assert await client.get_vehicles() == [_VIN]

    wire.refused = {"access-signin1"}
    assert await client.get_vehicles() == [_VIN]  # the refresh still works
    assert _KEY not in files
    assert len(signins) == 1


async def test_a_save_hook_that_raises_does_not_break_the_sign_in_or_a_read(
    signins: _SignIns,
) -> None:
    """The storage swallows a failed write itself, so the test above never
    reaches the client's own guard. The hook is the coordinator's to assign;
    whatever it does, a sign-in and a read that needed a refresh must finish."""
    wire = _Wire()
    client = PlugAndPlayCloudClient(
        wire, BRAND_AUDI_ACPP, "owner@example.invalid", "pw",
    )
    calls: list[str] = []

    async def _boom(tokens: TokenSet) -> None:
        calls.append(tokens.access_token)
        raise RuntimeError("storage down")

    client.on_tokens_changed = _boom

    await client.authenticate()
    wire.refused = {"access-signin1"}
    assert await client.get_vehicles() == [_VIN]

    assert calls == ["access-signin1", "access-refresh1"]  # it was called, twice
    assert len(signins) == 1


# ── 2. what a restart does with the file ─────────────────────────────────────
async def test_a_restart_uses_the_stored_tokens_and_does_not_sign_in(
    files: dict[str, Any], signins: _SignIns,
) -> None:
    first, _ = _client(_Wire())
    await first.authenticate()

    wire = _Wire()
    second = await _restarted(wire)

    assert await second.get_vehicles() == [_VIN]
    assert wire.list_reads() == ["access-signin1"]
    assert len(wire.refresh_forms) == 0
    assert len(signins) == 1


async def test_a_restart_renews_an_expired_access_token_from_the_file(
    files: dict[str, Any], signins: _SignIns,
) -> None:
    first, _ = _client(_Wire())
    await first.authenticate()

    wire = _Wire()
    wire.refused = {"access-signin1"}  # an hour has passed
    second = await _restarted(wire)

    assert await second.get_vehicles() == [_VIN]
    assert wire.list_reads() == ["access-signin1", "access-refresh1"]
    assert [f["refresh_token"] for f in wire.refresh_forms] == ["refresh-signin1"]
    assert _stored(files).get("refresh_token") == "refresh-refresh1"
    assert len(signins) == 1


# ── 3. a stored set that is not this client's to use ─────────────────────────
@pytest.mark.parametrize("strategy", ["", "porsche", "device_grant", "mbb", "classic"])
async def test_a_set_stored_by_another_brand_is_not_taken(
    files: dict[str, Any], strategy: str,
) -> None:
    """Reconfigure can switch an entry to plug&play, and the entry keeps its
    id, so the file the previous brand wrote is found again. Its refresh token
    belongs to another client and must not be posted to this backend."""
    files[_KEY] = {"version": 1, "tokens": {
        "access_token": "access-other-brand", "refresh_token": "refresh-other-brand",
        "id_token": _jwt({"sub": _SUB}), "expires_at": 0.0,
        "strategy": strategy, "auth_cookies": [],
    }}
    wire = _Wire()
    wire.refused = {"access-other-brand"}
    client = await _restarted(wire)

    assert client.tokens is None
    with pytest.raises(AuthenticationError):
        await client.get_vehicles()
    assert wire.reads == []            # nothing was sent with the other token
    assert wire.refresh_forms == []    # and its refresh token went nowhere


async def test_a_stored_set_that_cannot_be_renewed_is_not_taken(
    files: dict[str, Any],
) -> None:
    files[_KEY] = {"version": 2, "tokens": {
        "access_token": "access-old", "refresh_token": "",
        "id_token": _jwt({"sub": _SUB}), "expires_at": 0.0,
        "strategy": _BRAND, "auth_cookies": [],
    }}
    client = await _restarted(_Wire())

    assert client.tokens is None


# ── 4. a stored session the server no longer takes ───────────────────────────
@pytest.mark.parametrize("status", [400, 401, 403])
async def test_a_refused_stored_session_is_reported_as_a_sign_in_failure(
    files: dict[str, Any], status: int,
) -> None:
    """The vehicle list of a refused session must not read as "no cars": that
    is what setup does with an empty list, and then nothing ever signs in
    again. An authentication error is what makes setup sign in."""
    first, _ = _client(_Wire())
    await first.authenticate()

    wire = _Wire()
    wire.refused = {"access-signin1"}
    wire.refresh_status = status
    second = await _restarted(wire)

    with pytest.raises(AuthenticationError):
        await second.get_vehicles()
    assert len(wire.refresh_forms) == 1  # the refresh was tried once, not looped


async def test_a_refreshed_stored_session_that_is_still_refused_is_reported_too(
    files: dict[str, Any],
) -> None:
    """The refresh works but the new access token is refused as well. Still a
    session from the file that does not work, so still one for a sign-in."""
    first, _ = _client(_Wire())
    await first.authenticate()

    wire = _Wire()
    wire.refused = {"access-signin1", "access-refresh1"}
    second = await _restarted(wire)

    with pytest.raises(AuthenticationError):
        await second.get_vehicles()


async def test_a_refused_fresh_sign_in_still_reads_as_no_cars(
    files: dict[str, Any],
) -> None:
    """Control, unchanged behaviour: right after a sign-in in this start there
    is no older session to blame, and setup's fallback to the cars it already
    knows keeps their last values on screen."""
    wire = _Wire()
    wire.refused = {"access-signin1"}
    wire.refresh_status = 400
    client, _ = _client(wire)
    await client.authenticate()

    assert await client.get_vehicles() == []


async def test_a_sign_in_after_a_refused_stored_session_clears_the_mark(
    files: dict[str, Any], signins: _SignIns,
) -> None:
    """After the sign-in setup starts, the session is no longer "from the
    file", so the list goes back to its ordinary behaviour."""
    first, _ = _client(_Wire())
    await first.authenticate()

    wire = _Wire()
    wire.refused = {"access-signin1"}
    wire.refresh_status = 400
    second = await _restarted(wire)
    with pytest.raises(AuthenticationError):
        await second.get_vehicles()

    await second.authenticate()
    assert await second.get_vehicles() == [_VIN]
    assert _stored(files).get("access_token") == "access-signin2"

    wire.refused = {"access-signin2"}
    assert await second.get_vehicles() == []
    assert len(signins) == 2


# ── 5. a release from before this change must not be handed the file ─────────
def test_this_brand_writes_a_payload_version_older_releases_do_not_read() -> None:
    """Releases up to 5.3.0 accept exactly payload version 1 and discard
    anything else, which makes them sign in. That is the outcome wanted for a
    downgrade: handed a readable file, they call a method this brand's client
    did not have then, and the entry never comes up."""
    assert payload_version_for_brand(_BRAND) != 1


async def test_the_file_of_a_sign_in_carries_that_version(
    files: dict[str, Any],
) -> None:
    client, _ = _client(_Wire())
    await client.authenticate()

    assert (files.get(_KEY) or {}).get("version") == payload_version_for_brand(_BRAND)


# ── 6. through the coordinator's own setup ───────────────────────────────────
def _coordinator() -> Any:
    from custom_components.vag_connect.coordinator import VagConnectCoordinator

    coord = VagConnectCoordinator.__new__(VagConnectCoordinator)
    coord.hass = MagicMock()
    coord.hass.loop = MagicMock()
    coord.entry = MagicMock()
    coord.entry.entry_id = "test"
    coord.entry.options = {}
    coord.entry.data = {
        "brand": _BRAND, "username": "owner@example.invalid",
        "password": "pw", "spin": "", "scan_interval": 60,
    }
    coord._vehicles_lock = threading.Lock()
    coord._cariad_client = None
    coord._started = False
    coord._was_available = True
    coord.vehicles = {}
    coord.data = None
    coord.async_set_updated_data = MagicMock()
    coord.async_request_refresh = AsyncMock()
    coord.logger = MagicMock()
    return coord


async def _start(wire: _Wire) -> tuple[Any, Any]:
    """One start of the entry: a new coordinator, a new client, the same disk."""
    coord = _coordinator()
    with patch(f"{_HTTP}.async_get_clientsession", return_value=wire), \
         patch(f"{_HTTP}.async_create_clientsession", return_value=wire), \
         patch("homeassistant.helpers.storage.Store", _Store):
        ok = await coord.async_setup()
    return coord, ok


def _odometer(coord: Any) -> Any:
    return (coord.vehicles.get(_VIN) or {}).get("odometer_km")


async def test_a_restart_of_the_entry_does_not_sign_in_again(
    files: dict[str, Any], signins: _SignIns,
) -> None:
    _, ok = await _start(_Wire())
    assert ok is True
    assert len(signins) == 1
    assert _stored(files).get("refresh_token") == "refresh-signin1"
    # written under the version a release from before this change discards
    assert (files.get(_KEY) or {}).get("version") == 2

    coord, ok = await _start(_Wire())
    assert ok is True
    assert len(signins) == 1                 # no second sign-in
    assert _odometer(coord) == _LIVE_ODOMETER
    assert coord._cariad_client.tokens.access_token == "access-signin1"

    _, ok = await _start(_Wire())            # and a reload is the same thing
    assert ok is True
    assert len(signins) == 1


@pytest.mark.parametrize("status", [400, 401, 403])
@pytest.mark.parametrize("cached_car", [False, True])
async def test_a_restart_on_a_dead_token_file_still_comes_up(
    files: dict[str, Any], signins: _SignIns, status: int, cached_car: bool,
) -> None:
    """The worst a stored set can do is be refused. The entry must then come
    up on one sign-in, as it did before there was a file, whichever way the
    token endpoint words its refusal.

    With a car in the vehicle cache the failure used to look different and
    was just as final: setup came up on the cached values, never signed in,
    and every read of the car failed. So the live value is asserted, not only
    that setup ended well."""
    await _start(_Wire())
    assert len(signins) == 1
    if cached_car:
        files[_CACHE_KEY] = {
            "saved_at": "2026-11-13T10:00:00+00:00",
            "vehicles": {_VIN: {"vin": _VIN, "odometer_km": _CACHED_ODOMETER}},
        }

    wire = _Wire()
    wire.refused = {"access-signin1"}
    wire.refresh_status = status
    coord, ok = await _start(wire)

    assert ok is True
    assert _odometer(coord) == _LIVE_ODOMETER
    assert len(wire.refresh_forms) == 1
    assert len(signins) == 2
    assert _stored(files).get("access_token") == "access-signin2"

    _, ok = await _start(_Wire())            # the next start is quiet again
    assert ok is True
    assert len(signins) == 2


async def test_an_entry_switched_over_from_another_brand_comes_up(
    files: dict[str, Any], signins: _SignIns,
) -> None:
    """The entry was set up under another brand, which wrote a token file,
    and was then switched to plug&play in Reconfigure. Before this change the
    setup stopped at the loaded set on every attempt and the entry stayed in
    setup retry until it was deleted."""
    files[_KEY] = {"version": 1, "tokens": {
        "access_token": "access-other-brand", "refresh_token": "refresh-other-brand",
        "id_token": _jwt({"sub": _SUB}), "expires_at": 0.0,
        "strategy": "", "auth_cookies": [],
    }}
    wire = _Wire()
    wire.refused = {"access-other-brand"}
    coord, ok = await _start(wire)

    assert ok is True
    assert _odometer(coord) == _LIVE_ODOMETER
    assert len(signins) == 1
    assert wire.refresh_forms == []          # the other brand's token went nowhere
    assert "access-other-brand" not in [token for _, token in wire.reads]
    assert _stored(files).get("access_token") == "access-signin1"
    assert _stored(files).get("strategy") == _BRAND
    assert (files.get(_KEY) or {}).get("version") == 2

    _, ok = await _start(_Wire())
    assert ok is True
    assert len(signins) == 1


async def test_a_sign_in_answer_without_an_id_token_stores_nothing(
    files: dict[str, Any], signins: _SignIns,
) -> None:
    """The limit of this change, pinned so it is not a surprise: the storage
    refuses a set without an id_token. If the sign-in answer has none, no file
    is written and every start signs in, exactly as before this change."""
    signins.with_id_token = False

    coord, ok = await _start(_Wire())
    assert ok is True
    assert _KEY not in files

    coord, ok = await _start(_Wire())
    assert ok is True
    assert _odometer(coord) == _LIVE_ODOMETER
    assert len(signins) == 2
