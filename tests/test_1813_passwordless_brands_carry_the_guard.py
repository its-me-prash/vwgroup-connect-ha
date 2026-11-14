# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#1813: a brand that can be set up without a password builds a client that
carries the check for a sign-in without a password.

That check lives in ``CariadBaseClient.authenticate``. Two brand clients do
not derive from that class and bring their own ``authenticate``: ``VWNAClient``
(Volkswagen US/CA) and ``PorscheClient``. Both answer an expired refresh token
with ``self.authenticate()``, and neither asks whether there is a password to
sign in with. On an entry without one they would send the account id and an
empty password to the identity service, which is the request #1813 is about.

That costs nothing today for one reason only: no sign-in flow can create a
passwordless entry for those two brands, and neither brand was ever in one of
the sets those flows read. Their entries are created and updated by forms that
ask for an e-mail and a password, and each of those forms signs in before it
saves anything.

Review finding: no test checked that. The comment next to
``audi_na`` in the client factory called its client a subclass of
``VWNAClient``. It never was one. ``AudiNAClient`` is a ``VWEUClient`` and
takes the base class's ``authenticate``, so the Audi US/CA code sign-in is on
the guarded client. A reading of the source that trusted the comment came to
the opposite conclusion. And the day a code sign-in is offered for Volkswagen
US/CA or for Porsche, that wrong reading becomes the right one, with nothing
to say so.

This file holds both halves of the reason:

- Every brand named in a set that a passwordless sign-in reads builds a client
  that has the check: holding the token set a code sign-in leaves behind and
  no password, it starts no login. The list is computed from the sets, so a
  brand added to one of them is checked here without anyone having to remember
  this file.
- The config flow hands the entry builder an empty password in exactly the two
  finish steps known today. A third one, which could carry a brand list this
  file does not read, fails here and sends its author to this text.
- A sign-in step that does not ask for a brand but pins one never passes
  through a brand set. The brands pinned that way are read from the source and
  must be in the list as well.

The first test shows that the check can fire at all: the two clients it exists
for do start that login.

The tests call ``authenticate()`` directly and run no refresh. That is the
method each of these refresh fallbacks ends in, so it is where the check has to
be. This file is about WHICH client a brand gets, not about how far the check
reaches: every client is handed a token set that still carries the tag of a
code sign-in. Whether the check also holds once a refresh has dropped that tag
is the subject of #1813 itself and is not tested here.

What this file cannot see: an entry that is built without
``_build_entry_data`` and may hold no password. Two kinds exist today. The
volkswagen.de website sign-in has a builder of its own, which pins the brand to
``volkswagen``. The companion entry, which reads the brand's app on a phone,
holds no username and no password. It is offered for Volkswagen, Audi, Škoda,
SEAT and CUPRA, and it is served by a client of its own that never signs in to
an account, not by a brand client from the factory.
"""
from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

import pytest

from custom_components.vag_connect.cariad.api.base import CariadBaseClient
from custom_components.vag_connect.cariad.api.factory import CariadClientFactory
from custom_components.vag_connect.cariad.auth._auth0 import AUTH0_BRANDS
from custom_components.vag_connect.cariad.auth._device_grant import (
    DAG_ENABLED_BRANDS,
    MBB_DAG_BRANDS,
    PORTAL_DAG_BRANDS,
)
from custom_components.vag_connect.cariad.auth._eu_data_act import EUDataActConnector
from custom_components.vag_connect.cariad.auth.idk import IDKAuth
from custom_components.vag_connect.cariad.auth.porsche import PorscheAuth
from custom_components.vag_connect.cariad.exceptions import DeviceLoginExpiredError
from custom_components.vag_connect.cariad.models import TokenSet

# What a code sign-in stores as the username: the account id. Synthetic.
_ACCOUNT_ID = "0a1b2c3d-dead-beef-cafe-000000000000"
_EMAIL = "owner@example.test"
_PASSWORD = "a-real-password"

# Every brand a passwordless sign-in can produce an entry for: the code
# sign-in, its portal and e-Remote variants, and the browser sign-in.
_PASSWORDLESS_BRANDS = sorted(
    set(DAG_ENABLED_BRANDS)
    | set(PORTAL_DAG_BRANDS)
    | set(MBB_DAG_BRANDS)
    | set(AUTH0_BRANDS)
)

# The brands whose client signs in on its own, outside the base class.
_OWN_SIGN_IN = ["volkswagen_na", "porsche"]

_CONFIG_FLOW = (
    Path(__file__).resolve().parents[1]
    / "custom_components" / "vag_connect" / "config_flow.py"
)


# ─────────────────────────────────────────────────────────────────────────────
# The HTTP layer: the one thing these tests replace
# ─────────────────────────────────────────────────────────────────────────────


class _Resp:
    """Just enough of an aiohttp response. Always HTTP 400, so a login that
    should not have started fails at its first request instead of hanging."""

    status = 400
    url = "https://wire.invalid/"
    headers: dict[str, str] = {}
    history: tuple[Any, ...] = ()

    async def __aenter__(self) -> "_Resp":
        return self

    async def __aexit__(self, *exc: Any) -> bool:
        return False

    async def json(self, *a: Any, **k: Any) -> dict[str, Any]:
        return {}

    async def text(self, *a: Any, **k: Any) -> str:
        return ""


class _Wire:
    """Records every request."""

    def __init__(self) -> None:
        self.requests: list[str] = []

    def _answer(self, method: str, url: str) -> _Resp:
        self.requests.append(f"{method} {url.split('?', 1)[0]}")
        return _Resp()

    def post(self, url: str, **kwargs: Any) -> _Resp:
        return self._answer("POST", str(url))

    def get(self, url: str, **kwargs: Any) -> _Resp:
        return self._answer("GET", str(url))

    def request(self, method: str, url: str, **kwargs: Any) -> _Resp:
        return self._answer(str(method).upper(), str(url))


@pytest.fixture
def logins(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str, str]]:
    """Every sign-in that was started, as ``(which, identifier, password)``.

    The three entry points are wrapped, not replaced: the real login still runs
    against the wire. They are patched on the classes with ``monkeypatch``,
    which raises if the attribute is not there, so a rename breaks this fixture
    loudly instead of leaving a list that can only ever be empty.
    """
    seen: list[tuple[str, str, str]] = []
    real_idk = IDKAuth.authenticate
    real_portal = EUDataActConnector.login
    real_porsche = PorscheAuth.authenticate

    async def _idk(self: Any, email: str, password: str, **kw: Any) -> Any:
        seen.append(("identity service", email, password))
        return await real_idk(self, email, password, **kw)

    async def _portal(self: Any, email: str, password: str) -> Any:
        seen.append(("data act portal", email, password))
        return await real_portal(self, email, password)

    async def _porsche(self: Any, email: str, password: str, **kw: Any) -> Any:
        seen.append(("porsche identity", email, password))
        return await real_porsche(self, email, password, **kw)

    monkeypatch.setattr(IDKAuth, "authenticate", _idk)
    monkeypatch.setattr(EUDataActConnector, "login", _portal)
    monkeypatch.setattr(PorscheAuth, "authenticate", _porsche)
    return seen


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


def _entry(brand: str, wire: _Wire, *, password: str = "") -> Any:
    """A brand client built by the factory, holding the token set a code
    sign-in leaves behind."""
    username = _EMAIL if password else _ACCOUNT_ID
    client = CariadClientFactory.create(brand, wire, username, password)
    stored = TokenSet(
        access_token="access-0",
        refresh_token="refresh-0",
        id_token="id-0",
        expires_at=0.0,
        strategy="device_grant",
    )
    if hasattr(client, "set_persisted_tokens"):
        client.set_persisted_tokens(stored)
    else:
        # ``VWNAClient`` has no loader for a stored token set at all.
        client._tokens = stored
    assert client._tokens is stored, "the stored token set was not loaded"
    return client


async def _outcome(awaitable: Any) -> BaseException | None:
    """The exception an awaitable ended with, or ``None``."""
    try:
        await awaitable
    except Exception as err:  # noqa: BLE001
        return err
    return None


class _EntryBuilderCalls(ast.NodeVisitor):
    """Every call of ``_build_entry_data`` in a module, with the function it
    sits in and whether the password it passes is the literal ``""``."""

    def __init__(self) -> None:
        self._inside: list[str] = []
        self.calls: list[tuple[str, bool]] = []

    def _function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        self._inside.append(node.name)
        self.generic_visit(node)
        self._inside.pop()

    visit_FunctionDef = _function
    visit_AsyncFunctionDef = _function

    def visit_Call(self, node: ast.Call) -> None:
        func = node.func
        if isinstance(func, ast.Attribute) and func.attr == "_build_entry_data":
            # def _build_entry_data(brand, username, password, user_input)
            password: ast.expr | None = None
            if len(node.args) > 2:
                password = node.args[2]
            for keyword in node.keywords:
                if keyword.arg == "password":
                    password = keyword.value
            empty = isinstance(password, ast.Constant) and password.value == ""
            self.calls.append((self._inside[-1] if self._inside else "", empty))
        self.generic_visit(node)


def _pinned_sign_in_brands(tree: ast.AST) -> set[str]:
    """Every string literal assigned to ``self._dag_brand`` or
    ``self._auth0_brand``: the brand a code or browser sign-in runs for when
    the step sets it itself instead of taking it from the form."""
    pinned: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        value = node.value
        if not (isinstance(value, ast.Constant) and isinstance(value.value, str)):
            continue
        for target in node.targets:
            if (
                isinstance(target, ast.Attribute)
                and target.attr in ("_dag_brand", "_auth0_brand")
                and isinstance(target.value, ast.Name)
                and target.value.id == "self"
            ):
                pinned.add(value.value)
    return pinned


# ─────────────────────────────────────────────────────────────────────────────
# The check can fire
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("brand", _OWN_SIGN_IN)
async def test_a_client_with_its_own_sign_in_does_start_the_login(
    brand: str, logins: list[tuple[str, str, str]]
) -> None:
    """The reason these two brands must stay out of every passwordless set,
    measured instead of assumed. If this fails because the client now refuses
    the login, that is the better state: take the brand out of
    ``_OWN_SIGN_IN``, and the tests below cover it like any other."""
    wire = _Wire()
    client = _entry(brand, wire)
    assert not isinstance(client, CariadBaseClient)

    outcome = await _outcome(client.authenticate())

    assert [(ident, pw) for _which, ident, pw in logins] == [(_ACCOUNT_ID, "")]
    assert wire.requests, "the login never reached the wire"
    assert not isinstance(outcome, DeviceLoginExpiredError), repr(outcome)


# ─────────────────────────────────────────────────────────────────────────────
# The two halves of the reason
# ─────────────────────────────────────────────────────────────────────────────


def test_no_brand_with_its_own_sign_in_can_be_set_up_without_a_password() -> None:
    """Stated directly, so that the failure names the cause. The parametrised
    test below fails for the same change, but as one brand among several."""
    exposed = sorted(set(_OWN_SIGN_IN) & set(_PASSWORDLESS_BRANDS))
    assert exposed == [], (
        f"{exposed} can now be set up without a password, but the client "
        "signs in on its own and has no check for a missing password. Give "
        "it the check CariadBaseClient.authenticate has (#1813) before the "
        "sign-in is offered."
    )


@pytest.mark.parametrize("brand", _PASSWORDLESS_BRANDS)
async def test_a_passwordless_brand_starts_no_login_without_a_password(
    brand: str, logins: list[tuple[str, str, str]]
) -> None:
    wire = _Wire()
    client = _entry(brand, wire)

    outcome = await _outcome(client.authenticate())

    assert logins == [], (
        f"{brand} can be set up without a password, and its client "
        f"({type(client).__name__}) started a login with the account id and "
        "an empty password. See the docstring of this file."
    )
    assert wire.requests == [], "nothing should have left the machine"
    assert isinstance(outcome, DeviceLoginExpiredError), repr(outcome)


def test_the_entry_builder_gets_an_empty_password_in_two_finish_steps_only() -> None:
    """``_PASSWORDLESS_BRANDS`` is complete only as long as these two steps are
    the only ones that create a passwordless entry. The code sign-in step
    checks the brand from its form against ``DAG_ENABLED_BRANDS``, the browser
    sign-in against ``AUTH0_BRANDS``. A new step with a brand list of its own
    has to be added to that union."""
    finder = _EntryBuilderCalls()
    finder.visit(ast.parse(_CONFIG_FLOW.read_text(encoding="utf-8")))

    with_password = [where for where, empty in finder.calls if not empty]
    without_password = sorted(where for where, empty in finder.calls if empty)

    # The finder sees the ordinary call sites too. Without this, a rename of
    # the builder would leave both lists empty and the check below would then
    # fail for a reason that has nothing to do with what it is about.
    assert "async_step_email_password" in with_password
    assert without_password == ["_finish_auth0", "async_step_browser_login_finish"]


def test_a_brand_pinned_for_a_sign_in_is_one_of_the_passwordless_brands() -> None:
    """The e-Remote sign-in has no brand field: its steps set the brand
    themselves and then share the finish step of the code sign-in. A brand
    pinned like that is never compared with a brand set, so it is read from
    the source here. What this cannot see is a brand that reaches the same
    attribute through a variable no set was asked about."""
    pinned = _pinned_sign_in_brands(
        ast.parse(_CONFIG_FLOW.read_text(encoding="utf-8"))
    )

    # Not vacuous: the two steps that pin a brand today are found.
    assert {"volkswagen", "audi"} <= pinned
    stray = sorted(pinned - set(_PASSWORDLESS_BRANDS))
    assert stray == [], (
        f"{stray} is pinned for a code or browser sign-in but is in none of "
        "the brand sets this file reads. If its client signs in on its own, "
        "it has no check for a missing password (#1813)."
    )


# ─────────────────────────────────────────────────────────────────────────────
# Positive control: what must keep working
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("brand", _PASSWORDLESS_BRANDS + _OWN_SIGN_IN)
async def test_with_a_password_the_login_runs_with_exactly_those_credentials(
    brand: str, logins: list[tuple[str, str, str]]
) -> None:
    """The refusal is about the missing password and nothing else: the same
    client with the same token set, holding credentials, starts a login with
    them. The wire answers every request with HTTP 400. What is checked is that
    the login was started, and with what, not that it completes."""
    wire = _Wire()
    client = _entry(brand, wire, password=_PASSWORD)

    outcome = await _outcome(client.authenticate())

    assert not isinstance(outcome, DeviceLoginExpiredError), repr(outcome)
    assert logins, "no login was started"
    assert {(ident, pw) for _which, ident, pw in logins} == {(_EMAIL, _PASSWORD)}
    assert wire.requests, "the login never reached the wire"
