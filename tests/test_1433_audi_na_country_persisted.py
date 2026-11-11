# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#1433 — an Audi US/CA device-code login must capture the country, or a
Canadian car is routed to the US garage and discovers 0 vehicles.

audi_na already maps country -> garage base (``ca`` -> the EMEA CARIAD BFF), and
``_build_entry_data`` persists CONF_COUNTRY for the NA brands, and the
coordinator builds the client with it. The only gap was the device-code
(browser-login) form, which had no country field — so the country never reached
``_dag_user_input`` and defaulted to ``us``. The form now re-renders once with a
US/CA picker when a NA brand is chosen.
"""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from custom_components.vag_connect import config_flow as cf
from custom_components.vag_connect.const import (
    CONF_BRAND,
    CONF_COUNTRY,
    CONF_SCAN_INTERVAL,
    CONF_SPIN,
)


def _flow() -> Any:
    flow = cf.VagConnectConfigFlow()
    flow.hass = SimpleNamespace(  # type: ignore[assignment]
        config_entries=SimpleNamespace(),
        config=SimpleNamespace(
            language="en", country="CA", path=lambda *p: "/".join(p),
        ),
    )
    flow.context = {}  # type: ignore[assignment]
    flow._async_current_entries = lambda include_ignore=False: []  # type: ignore[method-assign]
    return flow


def _schema_keys(result: dict) -> set:
    return {getattr(k, "schema", k) for k in result["data_schema"].schema}


@pytest.mark.asyncio
async def test_audi_na_browser_login_re_renders_with_a_country_picker() -> None:
    flow = _flow()
    result = await flow.async_step_browser_login(
        {CONF_BRAND: "audi_na", CONF_SPIN: "", CONF_SCAN_INTERVAL: 15}
    )
    assert result["type"] == "form"
    assert result["step_id"] == "browser_login"
    assert CONF_COUNTRY in _schema_keys(result), "NA brand must get the US/CA picker"


def test_build_entry_data_persists_country_for_audi_na() -> None:
    flow = _flow()
    data = flow._build_entry_data("audi_na", "driver@example.invalid", "", {CONF_COUNTRY: "ca"})
    assert data[CONF_COUNTRY] == "ca"


def test_build_entry_data_does_not_pollute_an_eu_brand_with_a_country() -> None:
    flow = _flow()
    data = flow._build_entry_data("audi", "driver@example.invalid", "", {})
    assert CONF_COUNTRY not in data
