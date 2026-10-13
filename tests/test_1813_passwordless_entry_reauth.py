# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#1813 — a passwordless entry must ask for a new sign-in, not guess a password.

A UK Audi Q4 e-tron was set up in July 2026 through the app device-login. That
entry stores the BrandID ``sub`` UUID as its username and NO password. It ran
for 87 days, then the token refresh failed, and from there the integration spent
seven hours doing the wrong thing once an hour.

The chain, each link read in the source:

- ``dag_initial_tokens`` carries ``strategy: "device_grant"`` for the non-MBB
  device login (config_flow.py).
- In ``_refresh_tokens`` the ``device_grant_portal`` branch does not match that
  strategy, and the ``device_grant`` branch is gated on
  ``self._brand.name == "volkswagen"``, so an Audi matches neither and falls
  through to ``authenticate()``.
- ``authenticate()`` builds the Audi chain ``idk(classic) -> idk(hybrid_full) ->
  data_act_portal``. All three are email+password strategies, so all three are
  doomed on an entry that has no password, and the last one puts the account
  UUID into the identity service's email field.
- The identity service answers ``validator.email.invalid``. That code is not in
  the classifier's ``cred_codes`` tuple, so it lands in the
  ``portal_interaction_required`` bucket, and the reporter, who lives in the UK
  and whose car cannot use the EU Data Act portal at all, is told to go and do
  something in that portal.
- The resulting ``PortalInteractionRequiredError`` reaches the poll loop as a
  ``gather`` RESULT, not as a raised exception. The per-VIN handler recognises
  it as an auth interaction and keeps it out of the Error Reporter, which is
  right, but nothing escalates it, so the loop never stops.
- The one escalation that existed for this exact shape was brand-gated to
  Porsche (#1337, then named after it; it is ``_entry_auth_dead`` now). Its own
  comment described this reporter's symptom: "the per-VIN failures were only
  counted, so the entry re-ran that interactive login up to 3x per hour
  indefinitely with no reauth prompt."

The recovery already exists and is correct: ``config_flow`` routes an entry with
``dag_initial_tokens`` and no password straight to the QR sign-in, which updates
the tokens in place (#845/#835). It was simply never reached.

So this fixes the reaching, not the recovery:

1. A passwordless entry stops running login strategies that cannot succeed.
2. It raises its own error class, so the setup ladder can say "your device-login
   session expired, sign in again" instead of the credential catch-all. That
   mirrors ``PortalSessionExpiredError``, whose docstring gives the same reason:
   telling a user to re-type a password that is provably fine is wrong. Here it
   is stronger still, because there is no password to re-type.
3. The poll loop escalates to a reauth prompt for a passwordless entry whose
   every read failed on two consecutive polls, the same two-poll rule Porsche
   already uses, so the entry stops hammering the identity service with a UUID.

Deliberately NOT changed here: that an Audi device-grant entry has no re-mint
path in ``_refresh_tokens`` at all. Giving it one needs evidence that Audi's
device-grant refresh works, which no report provides.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from custom_components.vag_connect.const import CONF_BRAND, CONF_PASSWORD


# ─────────────────────────────────────────────────────────────────────────────
# The exception class
# ─────────────────────────────────────────────────────────────────────────────


class TestTheErrorClass:
    """Its place in the hierarchy decides how three other layers treat it."""

    def test_it_exists(self):
        from custom_components.vag_connect.cariad.exceptions import (
            DeviceLoginExpiredError,
        )

        assert issubclass(DeviceLoginExpiredError, Exception)

    def test_it_is_an_authentication_error(self):
        """So the existing auth-interaction de-escalation keeps applying."""
        from custom_components.vag_connect.cariad.exceptions import (
            AuthenticationError,
            DeviceLoginExpiredError,
        )

        assert issubclass(DeviceLoginExpiredError, AuthenticationError)

    def test_it_is_not_an_invalid_credentials_error(self):
        """There is no password, so the credential bucket is the wrong one."""
        from custom_components.vag_connect.cariad.exceptions import (
            DeviceLoginExpiredError,
            InvalidCredentialsError,
        )

        assert not issubclass(DeviceLoginExpiredError, InvalidCredentialsError)

    def test_its_message_names_the_sign_in_and_not_a_password(self):
        from custom_components.vag_connect.cariad.exceptions import (
            DeviceLoginExpiredError,
        )

        msg = str(DeviceLoginExpiredError())
        assert "sign in" in msg.lower()
        assert "password" not in msg.lower()

    def test_its_message_does_not_send_the_user_to_the_portal(self):
        """The reporter is in the UK; the EU portal is not available to him."""
        from custom_components.vag_connect.cariad.exceptions import (
            DeviceLoginExpiredError,
        )

        assert "data act" not in str(DeviceLoginExpiredError()).lower()


# ─────────────────────────────────────────────────────────────────────────────
# authenticate() stops running strategies that cannot succeed
# ─────────────────────────────────────────────────────────────────────────────


def _client(password: str, strategy: str | None = "device_grant"):
    """A brand client stub shaped for ``authenticate``'s own preconditions."""
    from custom_components.vag_connect.cariad.api.base import CariadBaseClient

    me = CariadBaseClient.__new__(CariadBaseClient)
    me._brand = SimpleNamespace(name="audi")
    me._email = "0a1b2c3d-dead-beef-cafe-000000000000"
    me._password = password
    me._spin = ""
    me._use_website_proxy = False
    me._tokens = (
        None if strategy is None else SimpleNamespace(strategy=strategy, refresh_token="r")
    )
    return me


class TestPasswordlessEntryDoesNotGuess:
    """Three doomed logins per attempt, with a UUID in the email field."""

    @pytest.mark.asyncio
    async def test_it_raises_the_device_login_error(self):
        from custom_components.vag_connect.cariad.exceptions import (
            DeviceLoginExpiredError,
        )

        with pytest.raises(DeviceLoginExpiredError):
            await _client(password="").authenticate()

    @pytest.mark.asyncio
    async def test_it_sends_nothing_to_the_identity_service(self):
        """The point is that no doomed login leaves the machine at all."""
        me = _client(password="")
        calls: list[str] = []
        me._authenticate_with_strategy = lambda *a, **k: calls.append("strategy")
        from custom_components.vag_connect.cariad.exceptions import (
            DeviceLoginExpiredError,
        )

        with pytest.raises(DeviceLoginExpiredError):
            await me.authenticate()
        assert calls == []

    @pytest.mark.asyncio
    async def test_the_mbb_strategy_counts_as_passwordless_too(self):
        from custom_components.vag_connect.cariad.exceptions import (
            DeviceLoginExpiredError,
        )

        with pytest.raises(DeviceLoginExpiredError):
            await _client(password="", strategy="mbb").authenticate()

    @pytest.mark.asyncio
    async def test_the_portal_device_grant_counts_too(self):
        from custom_components.vag_connect.cariad.exceptions import (
            DeviceLoginExpiredError,
        )

        with pytest.raises(DeviceLoginExpiredError):
            await _client(password="", strategy="device_grant_portal").authenticate()

    @pytest.mark.asyncio
    async def test_a_client_with_no_tokens_at_all_is_left_alone(self):
        """A first-ever login has no tokens yet and must not be short-circuited."""
        from custom_components.vag_connect.cariad.exceptions import (
            DeviceLoginExpiredError,
        )

        me = _client(password="", strategy=None)
        try:
            await me.authenticate()
        except DeviceLoginExpiredError:  # pragma: no cover
            pytest.fail("a tokenless client must not be treated as a dead device login")
        except Exception:
            pass  # any other failure is the pre-existing behaviour, which is fine

    @pytest.mark.asyncio
    async def test_a_credential_entry_is_untouched(self):
        """Regression guard: a normal entry must still run its strategies."""
        from custom_components.vag_connect.cariad.exceptions import (
            DeviceLoginExpiredError,
        )

        me = _client(password="hunter2", strategy="classic")
        try:
            await me.authenticate()
        except DeviceLoginExpiredError:  # pragma: no cover
            pytest.fail("an entry with a password must not be short-circuited")
        except Exception:
            pass


# ─────────────────────────────────────────────────────────────────────────────
# The poll loop stops instead of retrying hourly forever
# ─────────────────────────────────────────────────────────────────────────────


def _coord(brand: str = "audi", *, passwordless: bool = True):
    data: dict = {CONF_BRAND: brand}
    if passwordless:
        data["dag_initial_tokens"] = {"strategy": "device_grant"}
    else:
        data[CONF_PASSWORD] = "hunter2"
    return SimpleNamespace(entry=SimpleNamespace(data=data))


def _auth_dead(me, vins, results) -> bool:
    from custom_components.vag_connect.coordinator import VagConnectCoordinator

    return VagConnectCoordinator._entry_auth_dead(me, vins, results)


def _authfail(n: int = 2) -> list:
    from custom_components.vag_connect.cariad.exceptions import AuthenticationError

    return [AuthenticationError(f"e{i}") for i in range(n)]


class TestPollLoopEscalates:
    """The shape #1337 fixed for Porsche and left open everywhere else."""

    def test_two_consecutive_all_auth_fail_polls_escalate(self):
        me = _coord()
        assert _auth_dead(me, ["V1", "V2"], _authfail()) is False
        assert _auth_dead(me, ["V1", "V2"], _authfail()) is True

    def test_one_poll_is_not_enough(self):
        """A single all-auth-fail poll can still be a blip."""
        assert _auth_dead(_coord(), ["V1"], _authfail(1)) is False

    def test_any_success_resets_the_counter(self):
        from custom_components.vag_connect.cariad.models import VehicleData

        me = _coord()
        assert _auth_dead(me, ["V1"], _authfail(1)) is False
        assert _auth_dead(me, ["V1"], [VehicleData(vin="V1")]) is False
        assert _auth_dead(me, ["V1"], _authfail(1)) is False  # counts from 1 again

    def test_a_partial_failure_does_not_escalate(self):
        me = _coord()
        mixed = [*_authfail(1), RuntimeError("net")]
        assert _auth_dead(me, ["V1", "V2"], mixed) is False
        assert _auth_dead(me, ["V1", "V2"], mixed) is False

    def test_a_credential_entry_does_not_escalate(self):
        """Unchanged for every entry that still has a password to retry with."""
        me = _coord(passwordless=False)
        assert _auth_dead(me, ["V1"], _authfail(1)) is False
        assert _auth_dead(me, ["V1"], _authfail(1)) is False

    def test_porsche_still_escalates_on_its_own_terms(self):
        """#1337 must keep working, password or not."""
        me = _coord("porsche", passwordless=False)
        assert _auth_dead(me, ["V1"], _authfail(1)) is False
        assert _auth_dead(me, ["V1"], _authfail(1)) is True

    def test_no_vehicles_never_escalates(self):
        assert _auth_dead(_coord(), [], []) is False

    def test_an_empty_result_list_never_escalates(self):
        assert _auth_dead(_coord(), ["V1"], []) is False


# ─────────────────────────────────────────────────────────────────────────────
# What the user is told
# ─────────────────────────────────────────────────────────────────────────────


class TestTheUserFacingSide:
    """The reporter's complaint was the message, not only the failure."""

    def test_the_setup_reason_is_a_hard_auth_error(self):
        """So Home Assistant offers Reauthenticate rather than retrying."""
        from custom_components.vag_connect import _HARD_AUTH_SETUP_ERRORS

        assert "device_login_expired" in _HARD_AUTH_SETUP_ERRORS

    def test_the_setup_reason_has_its_own_message(self):
        from custom_components.vag_connect import _SETUP_ERRORS

        text = _SETUP_ERRORS.get("device_login_expired", "")
        assert text
        assert "password" not in text.lower()

    def test_the_repair_has_its_own_entry(self):
        """Without a mapping it would register a generic auth_failed repair."""
        import inspect

        from custom_components.vag_connect import repairs

        src = inspect.getsource(repairs.raise_issue_auth_required)
        assert "device_login_expired" in src

    def test_a_successful_sign_in_clears_the_repair(self):
        """A repair that outlives its own fix is worse than no repair.

        ``raise_issue_auth_required`` registers the issue as
        ``f"{entry_id}_{reason}"``, so a reason missing from
        ``clear_auth_issues`` leaves the notice standing after the sign-in that
        fixed it. Checking this found the same gap in
        ``portal_interaction_required``, which has had it since it was added.
        """
        import inspect

        from custom_components.vag_connect import repairs

        src = inspect.getsource(repairs.clear_auth_issues)
        assert "device_login_expired" in src
        assert "portal_interaction_required" in src

    def test_every_raisable_auth_reason_is_also_clearable(self):
        """The general rule behind the test above, so the next one cannot slip."""
        import inspect
        import re

        from custom_components.vag_connect import repairs

        # Only the keys of the issue_map literal itself: the surrounding function
        # mentions other quoted names (a "brand" placeholder among them) and a
        # looser pattern picks those up and makes the test lie.
        fn = inspect.getsource(repairs.raise_issue_auth_required)
        start = fn.index("issue_map = {")
        table = fn[start : fn.index("\n    }", start)]
        raised = set(re.findall(r'^\s{8}"([a-z_]+)":\s*\(', table, re.M))
        cleared = set(
            re.findall(r'"([a-z_]+)"', inspect.getsource(repairs.clear_auth_issues))
        )
        assert raised, "the reason table was not found, so this test proves nothing"
        assert not (raised - cleared), sorted(raised - cleared)

    def test_the_repair_text_exists_in_every_language(self):
        """HA does not fall back to English for a custom integration."""
        import json
        from pathlib import Path

        root = Path(__file__).resolve().parents[1] / "custom_components" / "vag_connect"
        paths = [root / "strings.json"] + sorted((root / "translations").glob("*.json"))
        assert len(paths) >= 12
        missing = []
        for p in paths:
            data = json.loads(p.read_text(encoding="utf-8"))
            node = data.get("issues", {}).get("device_login_expired", {})
            if not node.get("title") or not node.get("description"):
                missing.append(p.name)
        assert not missing, missing
