# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Reconfigure to another account must not keep the previous account's tokens (#118).

Reconfigure lets the brand and the username of an entry change. For a changed
account it already rebuilds the entry's data from scratch, with the stated
reason that carrying the previous account's tokens forward would be wrong
(tests/test_v2172_reconfigure_mbb.py pins that for the entry data). The token
file was left out of that: it is keyed by the entry, not by the account, so it
stayed where it was.

What that does, measured at the coordinator with the real setup: a start with
a changed username and an untouched token file starts no sign-in. It takes the
stored set, and the entry goes on reading the previous account under the new
account's name until that account's refresh token is refused.

This became pressing with the change next to it: Volkswagen US and Canada now
keeps a token file too, so without this an entry of that brand would have
gained the same behaviour.

Scope, deliberately narrow. The file is emptied only on the exit that updates
the entry right there, and only when the account changed:

* new credentials for the SAME account keep the file. Throwing a refreshable
  set away on every credential update is #118 again.
* a switch that fails validation, or that is refused because the other account
  already has an entry, changes nothing, so it keeps the file as well.
* Porsche saves the new account's own token set after the file is emptied, so
  the order matters and is pinned.

Not covered here: the exit through the code sign-in for the command channel
(Volkswagen and Audi), which updates the entry in a later step.
"""
from __future__ import annotations

import copy
import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.vag_connect.cariad.auth._token_storage import (
    storage_key_for_entry,
)
from custom_components.vag_connect.const import (
    CONF_BRAND,
    CONF_PASSWORD,
    CONF_SPIN,
    CONF_USERNAME,
)

_ENTRY_ID = "eid"
_KEY = storage_key_for_entry(_ENTRY_ID)
_VALIDATE = "custom_components.vag_connect.config_flow._validate_credentials"


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


def _entry(brand: str, username: str) -> MagicMock:
    entry = MagicMock()
    entry.entry_id = _ENTRY_ID
    entry.unique_id = f"{brand}_{username}"
    entry.data = {CONF_BRAND: brand, CONF_USERNAME: username, CONF_PASSWORD: "old"}
    return entry


def _flow(entry: MagicMock) -> Any:
    from custom_components.vag_connect.config_flow import VagConnectConfigFlow

    flow = VagConnectConfigFlow()
    flow.hass = MagicMock()
    flow.hass.config_entries.async_get_entry = MagicMock(return_value=entry)
    flow.hass.config_entries.async_update_entry = MagicMock()
    flow.hass.config_entries.async_reload = AsyncMock()
    flow.context = {"entry_id": entry.entry_id}
    flow.async_set_unique_id = AsyncMock()
    flow._abort_if_unique_id_configured = MagicMock()
    flow.async_abort = MagicMock(
        return_value={"type": "abort", "reason": "reconfigure_successful"}
    )
    flow.async_show_form = MagicMock(return_value={"type": "form"})
    return flow


async def _reconfigure(
    flow: Any, brand: str, username: str, validated: Any = None,
) -> Any:
    form = {
        CONF_BRAND: brand, CONF_USERNAME: username,
        CONF_PASSWORD: "new", CONF_SPIN: "",
    }
    with patch(_VALIDATE, new=AsyncMock(return_value=validated)), \
         patch("homeassistant.helpers.storage.Store", _Store):
        return await flow.async_step_reconfigure(form)


@pytest.mark.parametrize("brand", ["volkswagen_na", "skoda", "cupra"])
async def test_switching_to_another_account_empties_the_token_file(
    files: dict[str, Any], brand: str,
) -> None:
    flow = _flow(_entry(brand, "previous@example.invalid"))

    await _reconfigure(flow, brand, "next@example.invalid")

    flow.hass.config_entries.async_update_entry.assert_called_once()
    assert _KEY not in files


async def test_switching_the_brand_empties_the_token_file(
    files: dict[str, Any],
) -> None:
    """The stored set was minted by the other brand's client. Before the North
    America client could take a stored set at all, this start did not merely
    read the wrong account, it raised on the missing method."""
    flow = _flow(_entry("volkswagen", "owner@example.invalid"))

    await _reconfigure(flow, "volkswagen_na", "owner@example.invalid")

    assert _KEY not in files


async def test_the_file_is_empty_before_the_entry_changes_and_before_the_reload(
    files: dict[str, Any],
) -> None:
    """The entry has an update listener, so a changed entry can be reloaded
    by Home Assistant before this step gets to its own reload. A reload that
    still finds the file starts on the previous account."""
    flow = _flow(_entry("volkswagen_na", "previous@example.invalid"))
    seen: dict[str, bool] = {}
    flow.hass.config_entries.async_update_entry.side_effect = (
        lambda *a, **k: seen.__setitem__("at_update", _KEY in files)
    )
    flow.hass.config_entries.async_reload.side_effect = (
        lambda *a, **k: seen.__setitem__("at_reload", _KEY in files)
    )

    await _reconfigure(flow, "volkswagen_na", "next@example.invalid")

    assert seen == {"at_update": False, "at_reload": False}


async def test_new_credentials_for_the_same_account_keep_the_token_file(
    files: dict[str, Any],
) -> None:
    """Control, green before the change: the account did not change, so its
    stored set is still its own."""
    flow = _flow(_entry("volkswagen_na", "owner@example.invalid"))

    await _reconfigure(flow, "volkswagen_na", "owner@example.invalid")

    flow.hass.config_entries.async_update_entry.assert_called_once()
    assert files[_KEY] == _previous_account_file()


async def test_a_porsche_switch_ends_with_the_new_account_s_tokens_in_the_file(
    files: dict[str, Any],
) -> None:
    """Porsche's sign-in in this step returns a token set, and the step saves
    it for the reload. Emptying the file after that save would delete exactly
    the set the new account needs."""
    flow = _flow(_entry("porsche", "previous@example.invalid"))
    fresh = {
        "access_token": "access-next", "refresh_token": "refresh-next",
        "id_token": "id-next", "expires_at": 5.0, "strategy": "porsche",
    }

    await _reconfigure(flow, "porsche", "next@example.invalid", validated=fresh)

    stored = (files.get(_KEY) or {}).get("tokens") or {}
    assert stored.get("refresh_token") == "refresh-next"


async def test_a_switch_that_fails_validation_keeps_the_token_file(
    files: dict[str, Any],
) -> None:
    """Control: nothing about the entry changed, so nothing about its file may."""
    flow = _flow(_entry("volkswagen_na", "previous@example.invalid"))
    form = {
        CONF_BRAND: "volkswagen_na", CONF_USERNAME: "next@example.invalid",
        CONF_PASSWORD: "wrong", CONF_SPIN: "",
    }
    with patch(_VALIDATE, new=AsyncMock(side_effect=ValueError("invalid_credentials"))), \
         patch("homeassistant.helpers.storage.Store", _Store):
        await flow.async_step_reconfigure(form)

    flow.hass.config_entries.async_update_entry.assert_not_called()
    assert files[_KEY] == _previous_account_file()


async def test_a_switch_to_an_account_with_its_own_entry_keeps_the_token_file(
    files: dict[str, Any],
) -> None:
    """Control: the flow aborts before it touches the entry."""
    from homeassistant.data_entry_flow import AbortFlow

    flow = _flow(_entry("volkswagen_na", "previous@example.invalid"))
    flow._abort_if_unique_id_configured.side_effect = AbortFlow("already_configured")

    with pytest.raises(AbortFlow):
        await _reconfigure(flow, "volkswagen_na", "next@example.invalid")

    flow.hass.config_entries.async_update_entry.assert_not_called()
    assert files[_KEY] == _previous_account_file()
