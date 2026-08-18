# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""VW EU Two-Way kill-switch (2026-08-18).

VW disabled the 650d46ca device_code grant, so the BFF two-way can no longer be
minted. The whole flow is preserved behind ``VWEU_TWOWAY_DISABLED``: the options
add-toggle is hidden and the mint sub-flow aborts, but flipping the switch back
to ``False`` revives it unchanged. These pin that behaviour + the honest strings
+ the MBB ALPHA→BETA relabel.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

_ROOT = Path(__file__).resolve().parents[1] / "custom_components" / "vag_connect"


def _vw_options_keys(entry_data: dict) -> set:
    from custom_components.vag_connect.config_flow import VagConnectOptionsFlow

    entry = MagicMock()
    entry.data = entry_data
    entry.runtime_data = None
    flow = VagConnectOptionsFlow(entry)
    result = asyncio.run(flow.async_step_init(None))
    return {getattr(k, "schema", k) for k in result["data_schema"].schema}


def test_killswitch_is_active() -> None:
    from custom_components.vag_connect.cariad.auth._device_grant import (
        VWEU_TWOWAY_DISABLED,
    )

    assert VWEU_TWOWAY_DISABLED is True


def test_add_toggle_hidden_while_disabled() -> None:
    from custom_components.vag_connect.const import (
        CONF_BRAND,
        CONF_SCAN_INTERVAL,
        CONF_SPIN,
        CONF_VWEU_DEVICE_GRANT,
    )

    keys = _vw_options_keys(
        {CONF_BRAND: "volkswagen", CONF_SCAN_INTERVAL: 5, CONF_SPIN: ""}
    )
    assert CONF_VWEU_DEVICE_GRANT not in keys


def test_add_toggle_returns_when_reenabled() -> None:
    from custom_components.vag_connect.const import (
        CONF_BRAND,
        CONF_SCAN_INTERVAL,
        CONF_SPIN,
        CONF_VWEU_DEVICE_GRANT,
    )

    with patch(
        "custom_components.vag_connect.cariad.auth._device_grant.VWEU_TWOWAY_DISABLED",
        False,
    ):
        keys = _vw_options_keys(
            {CONF_BRAND: "volkswagen", CONF_SCAN_INTERVAL: 5, CONF_SPIN: ""}
        )
    assert CONF_VWEU_DEVICE_GRANT in keys


def test_remove_toggle_still_shown_for_armed_user() -> None:
    from custom_components.vag_connect.const import (
        CONF_BRAND,
        CONF_SCAN_INTERVAL,
        CONF_SPIN,
        CONF_VWEU_DEVICE_GRANT,
    )

    keys = _vw_options_keys(
        {
            CONF_BRAND: "volkswagen",
            CONF_VWEU_DEVICE_GRANT: True,
            CONF_SCAN_INTERVAL: 5,
            CONF_SPIN: "",
        }
    )
    assert "remove_vweu_twoway" in keys


def test_abort_and_issue_strings_present() -> None:
    en = json.loads((_ROOT / "translations" / "en.json").read_text(encoding="utf-8"))
    assert "vweu_twoway_vw_disabled" in en["options"]["abort"]
    assert "vweu_twoway_disabled" in en["issues"]
    de = json.loads((_ROOT / "translations" / "de.json").read_text(encoding="utf-8"))
    assert "vweu_twoway_disabled" in de["issues"]


def test_mbb_relabelled_beta_not_alpha() -> None:
    for lang in ("en", "de"):
        txt = (_ROOT / "translations" / f"{lang}.json").read_text(encoding="utf-8")
        assert "MBB, ALPHA" not in txt
    assert "MBB, BETA" in (_ROOT / "translations" / "en.json").read_text(
        encoding="utf-8"
    )
