# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#1813: the passwordless guard has to hold after the entry's first refresh.

The guard in ``authenticate()`` asked two questions before it refused to run a
login: is there no password, and does the token set carry a device-login
strategy tag. The second question stops being answerable the first time the
entry refreshes its token the ordinary way.

The chain, each link read in the source:

- ``_refresh_tokens`` has dedicated branches for ``mbb``, ``device_grant_portal``
  and ``auth0``, and each of them writes its own tag back. Everything else falls
  through to ``self._tokens = await self._auth.refresh(...)``.
- ``IDKAuth.refresh`` builds its result in ``_parse_tokens``, which sets the
  three tokens and nothing else. ``TokenSet.strategy`` defaults to ``""``.
- ``_notify_tokens_changed`` then stores that set, so the empty tag is also what
  the next restart loads.

So an entry created by scanning the sign-in code is tagged ``device_grant``
exactly until its first successful refresh, which is about an hour. The entry in
the report ran for 87 days. When its refresh was finally rejected, the guard saw
an untagged token set, let the call through, and the identity service was sent
the account id in the email field with an empty password, once for each login
in the chain.

Review finding: the tests that came with the guard could not see this. They put
a ``SimpleNamespace(strategy="device_grant")`` straight onto the client and
never ran a refresh, so the tag was always there.

That is why everything below goes through the real ``_refresh_tokens`` and the
real ``IDKAuth.refresh`` on the real brand clients. The only thing replaced is
the HTTP session, and the assertions are about what reached it.
"""
from __future__ import annotations

from typing import Any

import pytest

from custom_components.vag_connect.cariad.api.factory import CariadClientFactory
from custom_components.vag_connect.cariad.auth import _audi_market_config
from custom_components.vag_connect.cariad.auth._eu_data_act import EUDataActConnector
from custom_components.vag_connect.cariad.auth.idk import IDKAuth
from custom_components.vag_connect.cariad.exceptions import DeviceLoginExpiredError
from custom_components.vag_connect.cariad.models import TokenSet

# What a code sign-in stores as the username: the BrandID ``sub``. Synthetic.
_ACCOUNT_ID = "0a1b2c3d-dead-beef-cafe-000000000000"
_EMAIL = "owner@example.test"
_PASSWORD = "a-real-password"

# Every brand that has or had the code sign-in, whose client reaches
# ``CariadBaseClient.authenticate`` and whose refresh takes the generic branch.
# SEAT, CUPRA and Škoda override ``authenticate`` and call ``super()``, so they
# are in the same position. Audi North America is built on the same base client.
_BRANDS = ["audi", "seat", "cupra", "skoda", "audi_na"]


# ─────────────────────────────────────────────────────────────────────────────
# The HTTP layer, the one thing these tests replace
# ─────────────────────────────────────────────────────────────────────────────


class _Resp:
    """Just enough of an aiohttp response for the token endpoints."""

    url = "https://wire.invalid/"
    headers: dict[str, str] = {}
    history: tuple[Any, ...] = ()

    def __init__(self, status: int, payload: dict[str, Any] | None = None) -> None:
        self.status = status
        self._payload = payload or {}

    async def __aenter__(self) -> "_Resp":
        return self

    async def __aexit__(self, *exc: Any) -> bool:
        return False

    async def json(self, *a: Any, **k: Any) -> dict[str, Any]:
        return self._payload

    async def text(self, *a: Any, **k: Any) -> str:
        return ""


def _is_refresh(url: str, kwargs: dict[str, Any]) -> bool:
    """A refresh-token exchange, in either of the two shapes the brands use."""
    form = kwargs.get("data")
    if isinstance(form, dict) and form.get("grant_type") == "refresh_token":
        return True  # CARIAD BFF (Audi) and OLA (SEAT, CUPRA)
    body = kwargs.get("json")
    return isinstance(body, dict) and "token" in body and "refresh-token" in url


class _Wire:
    """Records every request and answers refreshes from a script.

    ``refresh_answers`` is the list of HTTP statuses the token endpoint gives,
    in order. Anything that is not a refresh is answered 400, which is what
    makes a login that should not have started fail fast instead of hanging.
    """

    def __init__(self, *refresh_answers: int, other: int = 400) -> None:
        self._answers = list(refresh_answers)
        self._other = other
        self.requests: list[str] = []
        self._minted = 0

    def _answer(self, method: str, url: str, kwargs: dict[str, Any]) -> _Resp:
        if not _is_refresh(url, kwargs):
            self.requests.append(f"{method} other")
            return _Resp(self._other)
        self.requests.append("POST refresh")
        if not self._answers:
            raise AssertionError("a refresh the test did not script")
        status = self._answers.pop(0)
        if status != 200:
            return _Resp(status)
        self._minted += 1
        return _Resp(200, {
            "access_token": f"access-{self._minted}",
            "refresh_token": f"refresh-{self._minted}",
            "id_token": f"id-{self._minted}",
        })

    def post(self, url: str, **kwargs: Any) -> _Resp:
        return self._answer("POST", str(url), kwargs)

    def get(self, url: str, **kwargs: Any) -> _Resp:
        return self._answer("GET", str(url), kwargs)

    def request(self, method: str, url: str, **kwargs: Any) -> _Resp:
        return self._answer(str(method).upper(), str(url), kwargs)


@pytest.fixture(autouse=True)
def _no_market_config_fetch(monkeypatch: pytest.MonkeyPatch) -> None:
    """Audi's refresh also fetches a market config from a CDN, at most once a
    day per process. It is unrelated to sign-in, and whether it fires depends
    on which test ran first, so it is taken off the wire here to keep the
    request log exact."""

    async def _nothing(*a: Any, **k: Any) -> dict[str, str]:
        return {}

    monkeypatch.setattr(_audi_market_config, "fetch_audi_market_config", _nothing)


@pytest.fixture
def logins(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str, str]]:
    """Every sign-in that was started, as ``(which, identifier, password)``.

    The two entry points are wrapped, not replaced: the real login still runs
    against the wire. They are patched on the classes with ``monkeypatch``,
    which raises if the attribute is not there, so a rename breaks this fixture
    loudly instead of leaving a list that can only ever be empty.
    """
    seen: list[tuple[str, str, str]] = []
    real_idk = IDKAuth.authenticate
    real_portal = EUDataActConnector.login

    async def _idk(self: Any, email: str, password: str, **kw: Any) -> Any:
        seen.append(("identity service", email, password))
        return await real_idk(self, email, password, **kw)

    async def _portal(self: Any, email: str, password: str) -> Any:
        seen.append(("data act portal", email, password))
        return await real_portal(self, email, password)

    monkeypatch.setattr(IDKAuth, "authenticate", _idk)
    monkeypatch.setattr(EUDataActConnector, "login", _portal)
    return seen


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


def _device_login_tokens() -> TokenSet:
    """What the config flow stores for a code sign-in (``dag_initial_tokens``)."""
    return TokenSet(
        access_token="access-0",
        refresh_token="refresh-0",
        id_token="id-0",
        expires_at=0.0,
        strategy="device_grant",
    )


def _entry(brand: str, wire: _Wire, *, password: str = "", stored: TokenSet | None):
    """A brand client the way the coordinator sets one up: built by the factory,
    then handed the stored token set and a save hook."""
    username = _EMAIL if password else _ACCOUNT_ID
    client = CariadClientFactory.create(brand, wire, username, password)
    saved: list[TokenSet] = []

    async def _save(tokens: TokenSet) -> None:
        saved.append(tokens)

    client.on_tokens_changed = _save
    if stored is not None:
        client.set_persisted_tokens(stored)
        assert client._tokens is stored, "the stored token set was not loaded"
    return client, saved


async def _outcome(awaitable: Any) -> BaseException | None:
    """The exception an awaitable ended with, or ``None``. The tests assert on
    what was sent BEFORE they assert on the error class, so a failure names the
    logins that ran instead of only saying the wrong exception came out."""
    try:
        await awaitable
    except Exception as err:  # noqa: BLE001
        return err
    return None


# ─────────────────────────────────────────────────────────────────────────────
# The defect
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("brand", _BRANDS)
async def test_the_first_ordinary_refresh_removes_the_tag_the_guard_read(
    brand: str,
) -> None:
    """The mechanism itself, pinned so the reason for the guard's shape stays
    visible: a refreshed token set does not say where it came from, in memory
    or in the store. Anything that decides on that tag decides wrongly from the
    first refresh on."""
    wire = _Wire(200)
    client, saved = _entry(brand, wire, stored=_device_login_tokens())

    await client._refresh_tokens()

    assert wire.requests == ["POST refresh"]
    assert client._tokens.access_token == "access-1"
    assert client._tokens.strategy == ""
    assert [t.strategy for t in saved] == [""]


@pytest.mark.parametrize("brand", _BRANDS)
async def test_a_rejected_refresh_after_a_good_one_asks_for_a_new_sign_in(
    brand: str, logins: list[tuple[str, str, str]]
) -> None:
    """The report: the entry renews normally for a while, then the refresh
    token dies. No login may be attempted, because there is nothing to attempt
    one with."""
    wire = _Wire(200, 400)
    client, _saved = _entry(brand, wire, stored=_device_login_tokens())

    await client._refresh_tokens()
    assert wire.requests == ["POST refresh"], "the good refresh did not happen"

    sent_before = len(wire.requests)
    outcome = await _outcome(client._refresh_tokens())

    assert logins == []
    assert wire.requests[sent_before:] == ["POST refresh"]
    assert isinstance(outcome, DeviceLoginExpiredError), repr(outcome)


@pytest.mark.parametrize("brand", _BRANDS)
async def test_it_also_holds_for_an_entry_restarted_on_its_stored_tokens(
    brand: str, logins: list[tuple[str, str, str]]
) -> None:
    """Entries that are running today have already refreshed, so what they have
    in the store is the untagged set. A restart loads exactly that. This is the
    case a fix that only tags tokens from now on would leave open."""
    first, saved = _entry(brand, _Wire(200), stored=_device_login_tokens())
    await first._refresh_tokens()
    stored = saved[-1]
    assert stored.strategy == "", "the store was expected to hold an untagged set"

    wire = _Wire(400)
    restarted, _ = _entry(brand, wire, stored=stored)
    outcome = await _outcome(restarted._refresh_tokens())

    assert logins == []
    assert wire.requests == ["POST refresh"]
    assert isinstance(outcome, DeviceLoginExpiredError), repr(outcome)


# ─────────────────────────────────────────────────────────────────────────────
# Positive controls: what must keep working
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("brand", _BRANDS)
async def test_an_entry_with_a_password_still_signs_in_again(
    brand: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The same sequence on an entry that does hold credentials has to end in a
    fresh login with exactly those credentials, and in a usable token set."""
    calls: list[tuple[str, str]] = []
    fresh = TokenSet(
        access_token="access-fresh", refresh_token="refresh-fresh",
        id_token="id-fresh", expires_at=0.0,
    )

    async def _login(self: Any, email: str, password: str, **kw: Any) -> TokenSet:
        calls.append((email, password))
        return fresh

    monkeypatch.setattr(IDKAuth, "authenticate", _login)

    wire = _Wire(200, 400)
    client, saved = _entry(
        brand, wire, password=_PASSWORD, stored=_device_login_tokens()
    )
    # SEAT and CUPRA take their user id from the login redirect and otherwise
    # read it from the API. That read is not what this test is about.
    client._auth.user_id = "user-1"
    await client._refresh_tokens()
    outcome = await _outcome(client._refresh_tokens())

    assert outcome is None, repr(outcome)
    assert calls == [(_EMAIL, _PASSWORD)]
    assert client._tokens is fresh
    assert saved[-1] is fresh


@pytest.mark.parametrize("brand", _BRANDS)
async def test_a_first_login_with_a_password_is_not_short_circuited(
    brand: str, logins: list[tuple[str, str, str]]
) -> None:
    """The config flow validates new credentials on a client that has no tokens
    yet. That call has to reach the identity service."""
    wire = _Wire()
    client, _ = _entry(brand, wire, password=_PASSWORD, stored=None)

    outcome = await _outcome(client.authenticate())

    assert not isinstance(outcome, DeviceLoginExpiredError), repr(outcome)
    assert logins[0] == ("identity service", _EMAIL, _PASSWORD)
    assert wire.requests, "the login never reached the wire"


async def test_the_website_sign_in_can_resume_without_a_password(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The one strategy in the resolver that can finish with no password: the
    volkswagen.de channel resumes from its stored session cookies and posts
    credentials only when that fails. A guard keyed on the password alone must
    leave it alone, or it would stop a sign-in that could have succeeded."""
    from custom_components.vag_connect.cariad.auth._website_authproxy import (
        WebsiteAuthProxyConnector,
    )

    resumed: list[str] = []

    async def _resume(self: Any) -> None:
        resumed.append("cookie resume")

    monkeypatch.setattr(WebsiteAuthProxyConnector, "refresh", _resume)
    monkeypatch.setattr(
        WebsiteAuthProxyConnector, "import_cookies", lambda self, cookies: None
    )

    client, _ = _entry("volkswagen", _Wire(), stored=None)
    client.set_website_authproxy_mode(True, cookies=[{"name": "sso", "value": "x"}])

    outcome = await _outcome(client.authenticate())

    assert outcome is None, repr(outcome)
    assert resumed == ["cookie resume"]
    assert client._tokens.strategy == "website_authproxy"


# ─────────────────────────────────────────────────────────────────────────────
# A setup run that ends up with no token set at all
# ─────────────────────────────────────────────────────────────────────────────
#
# The refresh is not the only way a passwordless entry reaches a login. Setup
# can get there with NO token set on the client, and a guard that reads the
# token set cannot see that case, because there is nothing to read.
#
# Two routes, both in the source:
#
# - Volkswagen is the one brand where setup may throw a stored token away
#   before the client ever sees it: a ``device_grant`` token left behind by the
#   two-way channel is discarded when that channel is no longer configured, and
#   the entry then starts a fresh login. For an entry that holds a password
#   that is the intended way back. For one that does not, it is the same doomed
#   login by another route.
# - ``set_persisted_tokens`` loads a stored set only if it is valid, and valid
#   means an access token AND an id token. A stored set without an id token is
#   skipped, the first read fails for want of a token, and setup answers that
#   with the fresh login it had skipped.


def _setup_run(
    brand: str, stored: TokenSet, wire: _Wire, *, portal: Any = None
) -> BaseException | bool:
    """Run the coordinator's real ``async_setup`` for an entry that has no
    password, on the real brand client, with only the session and the token
    store replaced. Returns what setup returned or raised.

    ``portal`` stands in for a supplementary EU Data Act channel the user added
    with its own credentials; when given, it is what the arming step installs.
    """
    import asyncio
    import threading
    from unittest.mock import AsyncMock, MagicMock, patch

    from custom_components.vag_connect.coordinator import VagConnectCoordinator

    coord = VagConnectCoordinator.__new__(VagConnectCoordinator)
    coord.hass = MagicMock()
    coord.hass.loop = MagicMock()
    coord.entry = MagicMock()
    coord.entry.entry_id = "test"
    coord.entry.options = {}
    coord.entry.data = {
        "brand": brand, "username": _ACCOUNT_ID, "password": "",
        "spin": "", "scan_interval": 5,
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

    _store = "custom_components.vag_connect.cariad.auth._token_storage.TokenStorage"
    _http = "homeassistant.helpers.aiohttp_client"

    async def _run() -> BaseException | bool:
        try:
            return bool(await coord.async_setup())
        except Exception as err:  # noqa: BLE001
            return err

    async def _arm() -> None:
        coord._cariad_client._supplementary_eu_portal = portal

    if portal is not None:
        coord._arm_supplementary_channels = _arm

    with patch(f"{_http}.async_get_clientsession", return_value=wire), \
         patch(f"{_http}.async_create_clientsession", return_value=wire), \
         patch(f"{_store}.load", new=AsyncMock(return_value=stored)), \
         patch(f"{_store}.save", new=AsyncMock()):
        return asyncio.run(_run())


@pytest.mark.parametrize(
    "strategy",
    ["", "device_grant"],
    ids=["untagged-after-a-refresh", "device_grant-left-by-the-two-way-channel"],
)
def test_a_setup_run_on_a_stored_volkswagen_token_starts_no_login(
    strategy: str, logins: list[tuple[str, str, str]]
) -> None:
    stored = TokenSet(
        access_token="access-0", refresh_token="refresh-0", id_token="id-0",
        expires_at=0.0, strategy=strategy,
    )
    # Reads are answered 401 so the untagged token is put through a refresh,
    # and every refresh is rejected.
    wire = _Wire(400, 400, 400, other=401)

    outcome = _setup_run("volkswagen", stored, wire)

    assert logins == []
    assert isinstance(outcome, ValueError), repr(outcome)
    assert str(outcome) == "device_login_expired"


@pytest.mark.parametrize("brand", _BRANDS)
def test_a_setup_run_on_a_stored_set_that_does_not_load_starts_no_login(
    brand: str, logins: list[tuple[str, str, str]]
) -> None:
    stored = TokenSet(
        access_token="access-0", refresh_token="refresh-0", id_token="",
        expires_at=0.0, strategy="",
    )
    assert not stored.is_valid(), "this set was meant to be one that is skipped"
    wire = _Wire(other=401)

    outcome = _setup_run(brand, stored, wire)

    assert logins == []
    assert wire.requests == [], "nothing should have left the machine"
    assert isinstance(outcome, ValueError), repr(outcome)
    assert str(outcome) == "device_login_expired"


def test_the_portal_fallback_is_still_asked_before_setup_gives_up(
    logins: list[tuple[str, str, str]],
) -> None:
    """Refusing the login must not also take away the way out that setup keeps
    for a dead primary sign-in: an EU Data Act channel the user added with its
    own credentials is asked for the vehicle list before setup gives up. The
    refusal is an ``AuthenticationError`` like the failure it replaces, so it
    lands in the same handler. Pinned because the more specific handler for it
    further out would be the easy place to route it past that fallback."""
    from unittest.mock import AsyncMock, MagicMock

    portal = MagicMock()
    portal.list_vehicle_vins = AsyncMock(return_value=[])
    stored = TokenSet(
        access_token="access-0", refresh_token="refresh-0", id_token="id-0",
        expires_at=0.0, strategy="",
    )
    wire = _Wire(400, 400, 400, other=401)

    outcome = _setup_run("audi", stored, wire, portal=portal)

    assert logins == []
    assert portal.list_vehicle_vins.await_count == 1
    assert isinstance(outcome, ValueError), repr(outcome)
    assert str(outcome) == "device_login_expired"
