# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Volkswagen US and Canada: the sign-in's tokens survive a restart (#118).

#118 was "after every update the password must be entered again". v1.19.2
answered it by writing the token set to Home Assistant's storage and loading it
at setup, in the base client every European brand shares. The North America
client is not a base client, and the two hooks never reached it: the
coordinator assigned the save callback on it and nothing ever called it.

Measured before this change, with the coordinator's real setup, the real
client and the real storage: one full sign-in per setup run, no token file
after the sign-in and none after a token refresh. Every restart, every update,
every reload and every automatic setup retry walked the sign-in pages again,
and that sign-in is the step the backend rate-limits.

What is replaced here and what is not. Replaced: the HTTP session, the token
file (one dict that outlives the client, as the file on disk outlives a
restart) and the walk through the sign-in pages, which is cut down to "count
one sign-in, hand back a token set with a verifier". Real: the client, its
refresh, the token parsing, the storage, and in the last group the
coordinator's setup.

Three things ride along because storing the tokens makes them matter:

* the PKCE verifier of the sign-in is stored with the set. The token endpoint
  is said to bind a refresh to it, so a stored set without it could not renew.
* a release from before this change cannot take a stored set for this brand:
  it calls a method the client did not have and the entry never comes up.
  Those releases discard a payload version they do not know and sign in
  instead, so this brand's file is written under a version of its own.
* the verifier is registered for masking in the diagnostics download, next to
  the tokens it travels with.
"""
from __future__ import annotations

import base64
import copy
import json
import threading
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.vag_connect.cariad.api.vw_na import VWNAClient
from custom_components.vag_connect.cariad.auth._token_storage import TokenStorage
from custom_components.vag_connect.cariad.auth.idk import IDKAuth
from custom_components.vag_connect.cariad.models import TokenSet

_VIN = "WVWZZZE1ZTP000001"  # synthetic, padded counter serial
_SUB = "00000000-0000-4000-8000-000000000001"  # synthetic account id
_KEY = "vag_connect_tokens_test"
_HTTP = "homeassistant.helpers.aiohttp_client"


def _jwt(claims: dict[str, Any]) -> str:
    body = base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip("=")
    return f"e30.{body}.sig"


# ── the token file ───────────────────────────────────────────────────────────
class _Store:
    """Home Assistant's Store, reduced to the three calls the storage makes.

    ``files`` is the disk: it is handed in, so a second client built later reads
    what the first one wrote.
    """

    files: dict[str, Any] = {}

    def __init__(self, hass: Any, version: int, key: str, *a: Any, **k: Any) -> None:
        self.key = key

    async def async_load(self) -> Any:
        return copy.deepcopy(self.files.get(self.key))

    async def async_save(self, data: Any) -> None:
        self.files[self.key] = json.loads(json.dumps(data))

    async def async_remove(self) -> None:
        self.files.pop(self.key, None)

    def async_delay_save(self, *a: Any, **k: Any) -> None:
        return None


@pytest.fixture
def files() -> dict[str, Any]:
    _Store.files = {}
    return _Store.files


def _stored(files: dict[str, Any], key: str = _KEY) -> dict[str, Any]:
    """The token part of the file, or an empty dict when there is no file."""
    return dict((files.get(key) or {}).get("tokens") or {})


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
    """Answers the garage read and the refresh grant, and records both."""

    def __init__(self) -> None:
        self.refresh_forms: list[dict[str, Any]] = []
        self.reads = 0
        self.reads_401 = 0          # answer this many reads with 401 first
        self.refresh_status = 200

    def post(self, url: str, **kwargs: Any) -> _Resp:
        form = kwargs.get("data")
        if isinstance(form, dict) and form.get("grant_type") == "refresh_token":
            self.refresh_forms.append(dict(form))
            if self.refresh_status != 200:
                return _Resp(self.refresh_status)
            n = len(self.refresh_forms)
            return _Resp(200, {
                "access_token": f"access-refresh{n}",
                "refresh_token": f"refresh-refresh{n}",
                "id_token": _jwt({"sub": _SUB}),
            })
        return _Resp(200, {})

    def get(self, url: str, **kwargs: Any) -> _Resp:
        return self.request("GET", url, **kwargs)

    def request(self, method: str, url: str, **kwargs: Any) -> _Resp:
        self.reads += 1
        if self.reads_401 > 0:
            self.reads_401 -= 1
            return _Resp(401)
        if str(url).endswith("/account/v1/garage"):
            return _Resp(200, {"data": {"vehicles": [
                {"vin": _VIN, "vehicleId": "uuid-0001", "modelName": "ID.4"},
            ]}})
        return _Resp(200, {})


# ── the sign-in ──────────────────────────────────────────────────────────────
@pytest.fixture
def signins(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Every full sign-in, in order. The page walk itself is not under test."""
    seen: list[str] = []

    async def _signin(self: Any, email: str, password: str, **kw: Any) -> TokenSet:
        seen.append(email)
        n = len(seen)
        return TokenSet(
            access_token=f"access-signin{n}",
            refresh_token=f"refresh-signin{n}",
            id_token=_jwt({"sub": _SUB}),
            code_verifier=f"verifier-signin{n}",
        )

    monkeypatch.setattr(IDKAuth, "authenticate", _signin)
    return seen


def _client(wire: _Wire) -> tuple[VWNAClient, TokenStorage]:
    """A client wired to the token file the way the coordinator wires it."""
    client = VWNAClient(wire, "owner@example.invalid", "pw", "", country="us")
    storage = TokenStorage(_Store(None, 1, _KEY))
    client.on_tokens_changed = storage.save
    return client, storage


async def _restarted(wire: _Wire) -> VWNAClient:
    """A new client that is handed whatever the token file holds."""
    client, storage = _client(wire)
    client.set_persisted_tokens(await storage.load())
    return client


# ── 1. what is written ───────────────────────────────────────────────────────
async def test_a_sign_in_is_written_to_the_token_file(
    files: dict[str, Any], signins: list[str],
) -> None:
    client, _ = _client(_Wire())
    await client.authenticate()

    stored = _stored(files)
    assert stored.get("access_token") == "access-signin1"
    assert stored.get("refresh_token") == "refresh-signin1"
    # without the verifier the stored set could not be renewed
    assert stored.get("code_verifier") == "verifier-signin1"


async def test_a_token_refresh_is_written_to_the_token_file(
    files: dict[str, Any], signins: list[str],
) -> None:
    wire = _Wire()
    client, _ = _client(wire)
    await client.authenticate()

    wire.reads_401 = 1                       # the access token has run out
    assert await client.get_vehicles() == [_VIN]

    assert len(wire.refresh_forms) == 1
    stored = _stored(files)
    assert stored.get("access_token") == "access-refresh1"
    assert stored.get("refresh_token") == "refresh-refresh1"
    assert len(signins) == 1                 # the refresh was not a sign-in


async def test_a_token_file_that_cannot_be_written_does_not_break_the_sign_in(
    files: dict[str, Any], signins: list[str],
) -> None:
    client, _ = _client(_Wire())

    async def _disk_full(tokens: TokenSet) -> None:
        raise OSError("no space left on device")

    client.on_tokens_changed = _disk_full
    await client.authenticate()              # must not raise

    assert client._tokens is not None
    assert client._tokens.access_token == "access-signin1"


# ── 2. what a restart does with it ───────────────────────────────────────────
async def test_a_restart_uses_the_stored_tokens_and_does_not_sign_in(
    files: dict[str, Any], signins: list[str],
) -> None:
    first, _ = _client(_Wire())
    await first.authenticate()

    wire = _Wire()
    second = await _restarted(wire)
    assert await second.get_vehicles() == [_VIN]

    assert len(signins) == 1                 # only the first start signed in
    assert wire.refresh_forms == []          # and the access token still worked
    assert wire.reads == 1


async def test_a_restart_renews_an_expired_access_token_from_the_file(
    files: dict[str, Any], signins: list[str],
) -> None:
    first, _ = _client(_Wire())
    await first.authenticate()

    wire = _Wire()
    wire.reads_401 = 1                       # the stored access token ran out
    second = await _restarted(wire)
    assert await second.get_vehicles() == [_VIN]

    assert len(signins) == 1
    assert len(wire.refresh_forms) == 1
    form = wire.refresh_forms[0]
    assert form["refresh_token"] == "refresh-signin1"
    # the verifier of the sign-in that minted the refresh token, read back
    # from the file, and the field the endpoint has required since #1012
    assert form.get("code_verifier") == "verifier-signin1"
    assert form.get("play_integrity_token") == "unavailable"
    # and the renewed set is what the next restart will find
    assert _stored(files).get("access_token") == "access-refresh1"


async def test_a_restored_client_addresses_the_same_user_as_a_fresh_one(
    files: dict[str, Any], signins: list[str],
) -> None:
    """The privileges read and the S-PIN session are addressed by user id. A
    restart has no sign-in redirect to read it from, so it has to come out of
    the stored id token, which is where a fresh sign-in takes it from when the
    redirect does not name it."""
    first, _ = _client(_Wire())
    await first.authenticate()
    assert first._user_id == _SUB

    second = await _restarted(_Wire())
    assert second._user_id == _SUB


@pytest.mark.parametrize("status", [400, 401, 403])
async def test_a_refused_renewal_costs_one_sign_in_and_no_more(
    files: dict[str, Any], signins: list[str], status: int,
) -> None:
    """A stored set the server no longer takes must end where every start
    ended before this change: in one sign-in. 400 is handled by the client
    itself; 401 and 403 leave the client as errors and are picked up by the
    coordinator at setup, which is covered in the last group."""
    first, _ = _client(_Wire())
    await first.authenticate()

    wire = _Wire()
    wire.reads_401 = 1
    wire.refresh_status = status
    second = await _restarted(wire)
    try:
        await second.get_vehicles()
    except Exception:  # noqa: BLE001 - 401 and 403 are the coordinator's to catch
        await second.authenticate()

    assert len(wire.refresh_forms) == 1      # one refused request, not a loop
    assert len(signins) == 2                 # the first start, and this one
    assert _stored(files).get("access_token") == "access-signin2"
    assert _stored(files).get("code_verifier") == "verifier-signin2"


async def test_a_stored_set_that_cannot_be_renewed_is_not_taken(
    files: dict[str, Any],
) -> None:
    client, _ = _client(_Wire())

    client.set_persisted_tokens(None)
    assert client._tokens is None

    client.set_persisted_tokens(
        TokenSet(access_token="a", refresh_token="", id_token=_jwt({"sub": _SUB}))
    )
    assert client._tokens is None


# ── 3. the storage layer ─────────────────────────────────────────────────────
async def test_the_verifier_comes_back_from_the_token_file(
    files: dict[str, Any],
) -> None:
    storage = TokenStorage(_Store(None, 1, _KEY))
    await storage.save(TokenSet(
        access_token="a", refresh_token="r", id_token="i", code_verifier="v",
    ))

    back = await storage.load()
    assert back is not None
    assert back.code_verifier == "v"


async def test_a_file_from_before_the_verifier_was_stored_still_loads(
    files: dict[str, Any],
) -> None:
    """Control, green before the change as well: every European entry has a
    file of this shape today and must keep its tokens."""
    files[_KEY] = {"version": 1, "tokens": {
        "access_token": "a", "refresh_token": "r", "id_token": "i",
        "expires_at": 0.0, "strategy": "", "auth_cookies": [],
    }}

    back = await TokenStorage(_Store(None, 1, _KEY)).load()
    assert back is not None
    assert back.refresh_token == "r"
    assert back.code_verifier == ""


# ── 4. a release from before this change must not be handed the file ─────────
def test_this_brand_writes_a_payload_version_older_releases_do_not_read() -> None:
    """Releases up to 5.3.0 accept exactly payload version 1 and discard
    anything else, which makes them sign in. That is the outcome wanted for a
    downgrade: handed a readable file, they call a method this brand's client
    did not have then, and the entry never comes up."""
    from custom_components.vag_connect.cariad.auth._token_storage import (
        payload_version_for_brand,
    )

    assert payload_version_for_brand("volkswagen_na") != 1


def test_every_other_brand_keeps_the_version_older_releases_read() -> None:
    """A downgrade must not cost any other brand its stored tokens. For an
    entry without a password that would be the end of the entry."""
    from custom_components.vag_connect.cariad.auth._token_storage import (
        payload_version_for_brand,
    )

    # ``audi_acpp`` is not in this list: its client had no way to take a
    # stored set either, see tests/test_plugandplay_tokens_survive_a_restart.py.
    for brand in ("volkswagen", "volkswagen_commercial", "audi", "skoda", "seat",
                  "cupra", "audi_na", "porsche", "bentley"):
        assert payload_version_for_brand(brand) == 1, brand


async def test_the_default_storage_still_writes_version_one(
    files: dict[str, Any],
) -> None:
    """Control: the config flow and the entry removal build the storage without
    naming a version, for brands that are not this one."""
    await TokenStorage(_Store(None, 1, _KEY)).save(
        TokenSet(access_token="a", refresh_token="r", id_token="i")
    )
    assert files[_KEY]["version"] == 1


@pytest.mark.parametrize(("version", "readable"), [
    (1, True), (2, True), (3, False), ("2", False), (None, False),
])
async def test_the_loader_reads_both_versions_and_nothing_else(
    files: dict[str, Any], version: Any, readable: bool,
) -> None:
    files[_KEY] = {"version": version, "tokens": {
        "access_token": "a", "refresh_token": "r", "id_token": "i",
        "expires_at": 0.0, "strategy": "", "auth_cookies": [],
        "code_verifier": "v",
    }}

    back = await TokenStorage(_Store(None, 1, _KEY)).load()
    assert (back is not None) is readable


# ── 5. the verifier in a diagnostics download ────────────────────────────────
def test_a_verifier_is_masked_in_a_diagnostics_download() -> None:
    """Nothing puts a token set into the download today. The tokens are
    registered for masking anyway, in case a later change does, and the
    verifier now travels with them."""
    from custom_components.vag_connect.diagnostics import _scrub, _scrub_raw

    payload = {
        "tokens": {"refresh_token": "plain-refresh", "code_verifier": "plain-one"},
        "auth.tokens.code_verifier": "plain-two",
        "codeVerifier": "plain-three",
    }
    for scrub in (_scrub, _scrub_raw):
        out = json.dumps(scrub(copy.deepcopy(payload)))
        for secret in ("plain-refresh", "plain-one", "plain-two", "plain-three"):
            assert secret not in out, (scrub.__name__, secret)


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
        "brand": "volkswagen_na", "username": "owner@example.invalid",
        "password": "pw", "spin": "", "scan_interval": 5, "country": "us",
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


async def test_a_restart_of_the_entry_does_not_sign_in_again(
    files: dict[str, Any], signins: list[str],
) -> None:
    _, ok = await _start(_Wire())
    assert ok is True
    assert len(signins) == 1
    assert _stored(files).get("refresh_token") == "refresh-signin1"
    assert _stored(files).get("code_verifier") == "verifier-signin1"
    # written under the version a release from before this change discards
    assert (files.get(_KEY) or {}).get("version") == 2

    coord, ok = await _start(_Wire())
    assert ok is True
    assert len(signins) == 1                 # no second sign-in
    assert _VIN in coord.vehicles
    assert coord._cariad_client._tokens.access_token == "access-signin1"

    _, ok = await _start(_Wire())            # and a reload is the same thing
    assert ok is True
    assert len(signins) == 1


@pytest.mark.parametrize("status", [400, 401, 403])
async def test_a_restart_on_a_dead_token_file_still_comes_up(
    files: dict[str, Any], signins: list[str], status: int,
) -> None:
    """The worst a stored set can do is be refused. The entry must then come
    up on one sign-in, as it did before there was a file, whichever way the
    token endpoint words its refusal."""
    await _start(_Wire())
    assert len(signins) == 1

    wire = _Wire()
    wire.reads_401 = 1
    wire.refresh_status = status
    coord, ok = await _start(wire)

    assert ok is True
    assert _VIN in coord.vehicles
    assert len(wire.refresh_forms) == 1
    assert len(signins) == 2
    assert _stored(files).get("access_token") == "access-signin2"
