# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Reconfigure through the code sign-in must end like the plain exit (#118).

Reconfigure has two ways out for Volkswagen and Audi. Without the box
"enable_mbb_commands" the step updates the entry right there: new title, new
unique id, new data. With the box ticked the step hands over to the code
sign-in for the command channel, and the entry is updated later, in
``_create_or_update_portal_entry``.

That later update passed the title and the data and nothing else. Measured
with the real flow steps on a real Home Assistant object after a switch to
another account:

* the token file still held the previous account's set. It is keyed by the
  entry, not by the account, and the next start takes a stored set without
  signing in, so the entry went on reading the previous account under the new
  account's name;
* the entry kept the previous account's unique id. A later plain Reconfigure
  for the same new account was therefore taken for another switch: the data
  was rebuilt from scratch and the command channel that had just been armed
  was gone.

Both happened on the full success and when the sign-in worked but the command
token exchange failed, because that case updates the entry as well.

Scope, deliberately narrow:

* the file is emptied only once the entry is really updated, and before that
  update. A sign-in that is left, expires or is refused changes nothing, so
  it keeps the file. Emptying it before the sign-in would cost the previous
  account its stored set whenever the dialog is closed.
* new credentials for the SAME account keep the file. Throwing a refreshable
  set away on every credential update is #118 again.
* the command tokens are not in the file. They live in the entry's data and
  come from this very sign-in.
"""
from __future__ import annotations

import asyncio
import copy
import json
from contextlib import contextmanager
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.vag_connect.cariad.auth._token_storage import (
    storage_key_for_entry,
)
from custom_components.vag_connect.cariad.models import TokenSet
from custom_components.vag_connect.const import (
    CONF_BRAND,
    CONF_MBB_COMMAND_CHANNEL,
    CONF_MBB_COMMAND_TOKENS,
    CONF_PASSWORD,
    CONF_SPIN,
    CONF_USERNAME,
    DOMAIN,
)

_ENTRY_ID = "eid"
_KEY = storage_key_for_entry(_ENTRY_ID)
_PREVIOUS = "previous@example.invalid"
_NEXT = "next@example.invalid"
_VALIDATE = "custom_components.vag_connect.config_flow._validate_credentials"
_GRANT = (
    "custom_components.vag_connect.cariad.auth._device_grant."
    "DeviceAuthorizationGrant"
)
_MINT = "custom_components.vag_connect.cariad.auth._mbboauth.mint_mbb_bearer"


class _Store:
    """Home Assistant's Store, reduced to the calls the token storage makes."""

    files: dict[str, Any] = {}

    def __init__(self, hass: Any, version: int, key: str, *a: Any, **k: Any) -> None:
        self.key = key

    async def async_load(self) -> Any:
        return copy.deepcopy(self.files.get(self.key))

    async def async_save(self, data: Any) -> None:
        self.files[self.key] = json.loads(json.dumps(data))

    async def async_remove(self) -> None:
        self.files.pop(self.key, None)


def _previous_account_file() -> dict[str, Any]:
    return {"version": 1, "tokens": {
        "access_token": "access-previous", "refresh_token": "refresh-previous",
        "id_token": "id-previous", "expires_at": 0.0, "strategy": "",
        "auth_cookies": [],
    }}


@pytest.fixture
def files() -> dict[str, Any]:
    _Store.files = {_KEY: _previous_account_file()}
    return _Store.files


class _Session:
    """Stands in for the HTTP session the sign-in opens and closes."""

    def __init__(self, *a: Any, **k: Any) -> None:
        pass

    async def close(self) -> None:
        return None


class _Code:
    device_code = "device-code"
    user_code = "USERCODE"
    verification_uri_complete = "https://sign-in.invalid/device?user_code=USERCODE"
    verification_uri = "https://sign-in.invalid/device"
    interval = 1
    expires_in = 300


def _grant(outcomes: list[str]) -> type:
    """The code sign-in. One outcome per attempt, in order:

    ``ok``       the code is approved,
    ``expired``  the code is never approved,
    ``refused``  no code is handed out,
    ``pending``  the user never comes back to the dialog.
    """

    class Grant:
        def __init__(self, session: Any, client_id: str, **kw: Any) -> None:
            pass

        async def request_device_code(self) -> Any:
            if outcomes[0] == "refused":
                outcomes.pop(0)
                raise RuntimeError("device code request refused")
            return _Code()

        async def poll_for_tokens(self, device_code: str, **kw: Any) -> TokenSet:
            outcome = outcomes.pop(0)
            if outcome == "expired":
                raise RuntimeError("expired_token")
            if outcome == "pending":
                await asyncio.sleep(3600)
            return TokenSet(
                access_token="app-access-next", refresh_token="app-refresh-next",
                id_token="app-id-next", expires_at=9e9,
            )

    return Grant


def _mint(works: bool) -> Any:
    async def mint(session: Any, id_token: str) -> Any:
        if not works:
            raise RuntimeError("HTTP 503 from the token exchange")
        return (
            TokenSet(
                access_token="cmd-access-next", refresh_token="cmd-refresh-next",
                id_token="", expires_at=9e9, strategy="mbb",
            ),
            "cmd-client-id",
        )

    return mint


@contextmanager
def _sign_in(*outcomes: str, exchange_works: bool = True) -> Any:
    """Everything outside the flow steps: the credential check, the code
    sign-in and the file."""
    with patch(_VALIDATE, new=AsyncMock(return_value=None)), \
         patch("homeassistant.helpers.storage.Store", _Store), \
         patch(_GRANT, _grant(list(outcomes))), \
         patch(_MINT, _mint(exchange_works)), \
         patch("aiohttp.ClientSession", _Session), \
         patch("aiohttp.TCPConnector", MagicMock()):
        yield


def _entry(brand: str, username: str = _PREVIOUS, armed: bool = False) -> MagicMock:
    entry = MagicMock()
    entry.entry_id = _ENTRY_ID
    entry.unique_id = f"{brand}_{username}"
    entry.title = f"{brand} / {username}"
    entry.data = {CONF_BRAND: brand, CONF_USERNAME: username, CONF_PASSWORD: "old"}
    if armed:
        entry.data[CONF_MBB_COMMAND_CHANNEL] = True
        entry.data[CONF_MBB_COMMAND_TOKENS] = {"refresh_token": "cmd-refresh-previous"}
    return entry


def _flow(entry: MagicMock) -> Any:
    from custom_components.vag_connect.config_flow import VagConnectConfigFlow

    flow = VagConnectConfigFlow()
    flow.hass = MagicMock()
    flow.hass.config_entries.async_get_entry = MagicMock(return_value=entry)
    flow.hass.config_entries.async_update_entry = MagicMock()
    flow.hass.config_entries.async_reload = AsyncMock()
    flow.hass.async_create_task = lambda coro, *a, **k: asyncio.ensure_future(coro)
    flow.handler = DOMAIN
    flow.flow_id = "flow"
    flow.context = {"source": "reconfigure", "entry_id": entry.entry_id}
    flow.async_set_unique_id = AsyncMock()
    flow._abort_if_unique_id_configured = MagicMock()
    # A second way to show the code, beside the dialog. Not part of the path.
    flow._fire_dag_persistent_notification = MagicMock()
    flow._dismiss_dag_persistent_notification = MagicMock()
    return flow


async def _settle(flow: Any, result: Any) -> Any:
    """Call the steps Home Assistant calls by itself, up to a form or an end."""
    for _ in range(6):
        kind = str(result.get("type"))
        if kind == "progress":
            await flow._dag_request_task
            result = await flow.async_step_browser_login_pending()
        elif kind == "progress_done":
            result = await getattr(flow, f"async_step_{result['step_id']}")()
        else:
            return result
    raise AssertionError("the flow did not come to a form or an end")


async def _reconfigure(flow: Any, brand: str, username: str) -> Any:
    form = {
        CONF_BRAND: brand, CONF_USERNAME: username, CONF_PASSWORD: "new",
        CONF_SPIN: "", "enable_mbb_commands": True,
    }
    return await _settle(flow, await flow.async_step_reconfigure(form))


async def _submit_the_approval(flow: Any) -> Any:
    await asyncio.gather(flow._dag_poll_task, return_exceptions=True)
    return await _settle(
        flow,
        await flow.async_step_browser_login_approve({"approved_in_browser": True}),
    )


def _update(flow: Any) -> dict[str, Any]:
    flow.hass.config_entries.async_update_entry.assert_called_once()
    return dict(flow.hass.config_entries.async_update_entry.call_args.kwargs)


# ── the account changed and the sign-in completes ────────────────────────────

@pytest.mark.parametrize("brand", ["volkswagen", "audi"])
async def test_switching_the_account_empties_the_token_file(
    files: dict[str, Any], brand: str,
) -> None:
    flow = _flow(_entry(brand))

    with _sign_in("ok"):
        assert (await _reconfigure(flow, brand, _NEXT))["step_id"] == "browser_login_approve"
        result = await _submit_the_approval(flow)

    assert result["reason"] == "reconfigure_successful"
    assert _update(flow)["data"][CONF_USERNAME] == _NEXT
    assert _KEY not in files


async def test_the_file_is_empty_before_the_entry_changes_and_before_the_reload(
    files: dict[str, Any],
) -> None:
    """The entry has an update listener, and the reload starts the entry on
    whatever the file holds. Both must find it empty."""
    flow = _flow(_entry("volkswagen"))
    seen: dict[str, bool] = {}
    flow.hass.config_entries.async_update_entry.side_effect = (
        lambda *a, **k: seen.__setitem__("at_update", _KEY in files)
    )
    flow.hass.config_entries.async_reload.side_effect = (
        lambda *a, **k: seen.__setitem__("at_reload", _KEY in files)
    )

    with _sign_in("ok"):
        await _reconfigure(flow, "volkswagen", _NEXT)
        await _submit_the_approval(flow)

    assert seen == {"at_update": False, "at_reload": False}


@pytest.mark.parametrize("brand", ["volkswagen", "audi"])
async def test_the_entry_takes_the_new_account_s_unique_id(
    files: dict[str, Any], brand: str,
) -> None:
    """As on the plain exit. With the previous id left on the entry, the next
    Reconfigure for the same account counts as another switch and rebuilds
    the data without the command channel."""
    flow = _flow(_entry(brand))

    with _sign_in("ok"):
        await _reconfigure(flow, brand, _NEXT)
        await _submit_the_approval(flow)

    update = _update(flow)
    assert update.get("unique_id") == f"{brand}_{_NEXT}"
    assert update["title"].endswith(_NEXT)
    assert update["data"][CONF_MBB_COMMAND_TOKENS]["refresh_token"] == "cmd-refresh-next"


async def test_a_failed_command_token_exchange_ends_the_same_way(
    files: dict[str, Any],
) -> None:
    """The sign-in worked, the exchange for the command tokens did not. The
    entry is moved to the new account all the same (read-only, with the reason
    recorded), so its file and its unique id have to follow."""
    flow = _flow(_entry("volkswagen"))

    with _sign_in("ok", exchange_works=False):
        await _reconfigure(flow, "volkswagen", _NEXT)
        result = await _submit_the_approval(flow)

    assert result["reason"] == "reconfigure_successful"
    update = _update(flow)
    assert update["data"][CONF_USERNAME] == _NEXT
    assert CONF_MBB_COMMAND_TOKENS not in update["data"]
    assert update.get("unique_id") == f"volkswagen_{_NEXT}"
    assert _KEY not in files


async def test_a_second_attempt_after_an_expired_code_ends_the_same_way(
    files: dict[str, Any],
) -> None:
    """An expired code leads to a retry form. What Reconfigure decided has to
    survive that form, or the retry ends like the unfixed path."""
    flow = _flow(_entry("audi"))

    with _sign_in("expired", "ok"):
        await _reconfigure(flow, "audi", _NEXT)
        retry = await _submit_the_approval(flow)
        assert retry["step_id"] == "mbb_login"
        flow.hass.config_entries.async_update_entry.assert_not_called()
        assert files.get(_KEY) == _previous_account_file()

        await _settle(flow, await flow.async_step_mbb_login({CONF_SPIN: ""}))
        result = await _submit_the_approval(flow)

    assert result["reason"] == "reconfigure_successful"
    assert _update(flow).get("unique_id") == f"audi_{_NEXT}"
    assert _KEY not in files


# ── controls: green before the change ────────────────────────────────────────

async def test_the_same_account_keeps_its_token_file_and_its_unique_id(
    files: dict[str, Any],
) -> None:
    """Re-approving the command channel for the account the entry already has
    is not a switch. Its stored set is still its own."""
    entry = _entry("volkswagen", armed=True)
    flow = _flow(entry)

    with _sign_in("ok"):
        await _reconfigure(flow, "volkswagen", _PREVIOUS)
        result = await _submit_the_approval(flow)

    assert result["reason"] == "reconfigure_successful"
    update = _update(flow)
    assert update.get("unique_id", entry.unique_id) == entry.unique_id
    assert update["data"][CONF_MBB_COMMAND_TOKENS]["refresh_token"] == "cmd-refresh-next"
    assert files.get(_KEY) == _previous_account_file()


async def test_a_dialog_that_is_left_changes_nothing(files: dict[str, Any]) -> None:
    flow = _flow(_entry("volkswagen"))

    with _sign_in("pending"):
        shown = await _reconfigure(flow, "volkswagen", _NEXT)
        flow._dag_poll_task.cancel()
        await asyncio.gather(flow._dag_poll_task, return_exceptions=True)

    assert shown["step_id"] == "browser_login_approve"
    flow.hass.config_entries.async_update_entry.assert_not_called()
    assert files.get(_KEY) == _previous_account_file()


@pytest.mark.parametrize("outcome", ["expired", "refused"])
async def test_a_sign_in_that_fails_changes_nothing(
    files: dict[str, Any], outcome: str,
) -> None:
    flow = _flow(_entry("volkswagen"))

    with _sign_in(outcome):
        shown = await _reconfigure(flow, "volkswagen", _NEXT)
        if outcome == "expired":
            shown = await _submit_the_approval(flow)

    assert shown["step_id"] == "mbb_login"
    flow.hass.config_entries.async_update_entry.assert_not_called()
    assert files.get(_KEY) == _previous_account_file()


async def test_without_a_unique_id_from_reconfigure_none_is_written(
    files: dict[str, Any],
) -> None:
    """Home Assistant takes ``unique_id=None`` as "remove the unique id". The
    update may name a unique id only when Reconfigure handed one over."""
    flow = _flow(_entry("volkswagen"))
    flow._mbb_reconfigure_entry_id = _ENTRY_ID

    with _sign_in():
        await flow._create_or_update_portal_entry(title="T", data={"a": 1})

    assert "unique_id" not in _update(flow)
    assert files.get(_KEY) == _previous_account_file()
