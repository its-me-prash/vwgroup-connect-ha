# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Manual per-VIN Škoda official-API keys in the options flow.

Official public-API keys are VIN-bound (one per car, minted in the MyŠkoda app,
max 5/VIN). A multi-car Škoda account therefore needs one key PER VIN, not a
single shared key. The options flow renders one optional key field per VIN (in
addition to the single fallback field) and folds them into the
CONF_SKODA_OFFICIAL_KEYS map the coordinator already arms from.
"""
from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

from custom_components.vag_connect.config_flow import VagConnectOptionsFlow
from custom_components.vag_connect.const import (
    CONF_BRAND,
    CONF_SCAN_INTERVAL,
    CONF_SKODA_OFFICIAL_KEYS,
)

VIN_A = "TMBVINA0000000001"
VIN_B = "TMBVINB0000000002"


def _skoda_entry(data=None, options=None, vehicles=None):
    entry = MagicMock()
    entry.data = {CONF_SCAN_INTERVAL: 5, CONF_BRAND: "skoda", **(data or {})}
    entry.options = options if options is not None else {}
    if vehicles is not None:
        entry.runtime_data = MagicMock()
        entry.runtime_data.vehicles = vehicles
    return entry


def _submit(flow, user_input):
    with patch.object(
        flow, "async_create_entry", return_value={"type": "create_entry"}
    ) as save:
        asyncio.run(flow.async_step_init(user_input))
    return save


def test_per_vin_key_fields_render_only_for_multicar_skoda():
    # two Škoda vehicles → one official-key field per VIN, pre-filled from the map
    entry = _skoda_entry(
        data={CONF_SKODA_OFFICIAL_KEYS: {VIN_A: {"key": "msk_existing_a"}}},
        vehicles={VIN_A: {"vin": VIN_A}, VIN_B: {"vin": VIN_B}},
    )
    result = asyncio.run(VagConnectOptionsFlow(entry).async_step_init(None))
    keys = {str(k) for k in result["data_schema"].schema}
    assert f"{CONF_SKODA_OFFICIAL_KEYS}_{VIN_A}" in keys
    assert f"{CONF_SKODA_OFFICIAL_KEYS}_{VIN_B}" in keys
    # VIN_A field pre-filled from the stored map; VIN_B empty
    defaults = {
        str(k): (k.default() if callable(getattr(k, "default", None)) else None)
        for k in result["data_schema"].schema
    }
    assert defaults[f"{CONF_SKODA_OFFICIAL_KEYS}_{VIN_A}"] == "msk_existing_a"
    assert defaults[f"{CONF_SKODA_OFFICIAL_KEYS}_{VIN_B}"] == ""


def test_per_vin_key_fields_absent_for_singlecar():
    # one vehicle → no per-VIN fields (the single fallback field covers it)
    entry = _skoda_entry(vehicles={VIN_A: {"vin": VIN_A}})
    result = asyncio.run(VagConnectOptionsFlow(entry).async_step_init(None))
    keys = {str(k) for k in result["data_schema"].schema}
    assert not any(k.startswith(f"{CONF_SKODA_OFFICIAL_KEYS}_") for k in keys)


def test_submit_folds_typed_keys_into_map_and_pops_transients():
    entry = _skoda_entry()
    save = _submit(
        VagConnectOptionsFlow(entry),
        {
            CONF_SCAN_INTERVAL: 15,
            f"{CONF_SKODA_OFFICIAL_KEYS}_{VIN_A}": "msk_aaa",
            f"{CONF_SKODA_OFFICIAL_KEYS}_{VIN_B}": "",  # blank → no entry
        },
    )
    data = save.call_args.kwargs["data"]
    assert data[CONF_SKODA_OFFICIAL_KEYS] == {
        VIN_A: {"key": "msk_aaa", "source": "manual"}
    }
    # transient per-field keys never persist as standalone options
    assert not any(
        str(k).startswith(f"{CONF_SKODA_OFFICIAL_KEYS}_") for k in data
    )


def test_submit_blank_keeps_existing_and_preserves_auto_enrolled():
    entry = _skoda_entry(
        data={
            CONF_SKODA_OFFICIAL_KEYS: {
                VIN_A: {"key": "auto_a", "id": "id1", "validUntil": "2027-01-01"},
            }
        },
    )
    save = _submit(
        VagConnectOptionsFlow(entry),
        {
            CONF_SCAN_INTERVAL: 15,
            f"{CONF_SKODA_OFFICIAL_KEYS}_{VIN_A}": "",  # blank → keep auto-enrolled
            f"{CONF_SKODA_OFFICIAL_KEYS}_{VIN_B}": "msk_bbb",  # new manual
        },
    )
    data = save.call_args.kwargs["data"]
    assert data[CONF_SKODA_OFFICIAL_KEYS] == {
        VIN_A: {"key": "auto_a", "id": "id1", "validUntil": "2027-01-01"},
        VIN_B: {"key": "msk_bbb", "source": "manual"},
    }


def test_submit_typed_key_overrides_existing_and_drops_stale_id():
    entry = _skoda_entry(
        data={
            CONF_SKODA_OFFICIAL_KEYS: {
                VIN_A: {"key": "old_a", "id": "id1", "validUntil": "2027-01-01"},
            }
        },
    )
    save = _submit(
        VagConnectOptionsFlow(entry),
        {
            CONF_SCAN_INTERVAL: 15,
            f"{CONF_SKODA_OFFICIAL_KEYS}_{VIN_A}": "new_a",  # override
        },
    )
    data = save.call_args.kwargs["data"]
    # a new manual key replaces the record (stale id/validUntil of the old key gone)
    assert data[CONF_SKODA_OFFICIAL_KEYS][VIN_A] == {
        "key": "new_a",
        "source": "manual",
    }
