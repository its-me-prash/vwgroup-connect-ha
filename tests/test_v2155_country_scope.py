# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""v2.15.5 — scope the US/Canada region selector to the volkswagen_na brand.

Background (the defect)
=======================
The ``CONF_COUNTRY`` (US/CA) region picker was added in v2.15.1 (#503) for
Volkswagen North America: US vs CA select different MYVW client_ids and API
hosts (``cariad/api/vw_na.py``). But the selector lived on the *shared*
credentials schema (``_credentials_schema``) with a hardcoded ``default="us"``,
and ``_build_entry_data`` wrote ``CONF_COUNTRY: user_input.get(...,"us")``
**unconditionally** for every brand.

Result: a Swiss/EU ``volkswagen`` user who never touched the dropdown got
``country="us"`` persisted into ``entry.data`` — exactly the field a user
reported. It is benign at runtime (the EU Data Act portal builds its OIDC
``state`` from its OWN ``country/language`` defaults — ``de__de__VW`` — never
from ``CONF_COUNTRY``; and ``factory.create`` only forwards ``country`` to the
``volkswagen_na`` client), but it is misleading in diagnostics and a latent
trap for any future code that naively trusts ``entry.data["country"]``.

The fix
=======
``_build_entry_data`` now persists ``CONF_COUNTRY`` ONLY when
``brand == "volkswagen_na"``. EU/other brands leave it unset. VW-NA behaviour
is unchanged (us/ca still stored and threaded to the factory). Existing EU
entries that already carry a stale ``country="us"`` keep working: the only
runtime reader is the VW-NA branch of the factory, which never runs for an EU
brand, so the stale value is simply ignored.

This file mixes a behavioural assertion (the EU portal ``state`` is built from
the connector's own country/language, NOT the NA selector) with source-level
assertions for the config-flow gating (config_flow imports HA, which is not
installed in this test env, so it is checked at the source level — same idiom
as ``test_v2151_vwna_country.py``).
"""

from __future__ import annotations

from pathlib import Path

from custom_components.vag_connect.cariad.auth._eu_data_act import (
    EUDataActConnector,
)

_REPO_ROOT = Path(__file__).resolve().parent.parent
_CONFIG_FLOW_PY = (
    _REPO_ROOT / "custom_components" / "vag_connect" / "config_flow.py"
)


class _DummySession:
    """Stand-in for aiohttp.ClientSession — the connector only stores it; the
    ``__init__`` we exercise here never touches the network."""


# ──────────────────────────────────────────────────────────────────────
# Behavioural: the EU portal OIDC state is built from the connector's own
# country/language, never from a NA-style country="us".
# ──────────────────────────────────────────────────────────────────────


class TestEuPortalStateIgnoresNaCountry:
    def test_eu_state_defaults_to_de_not_us(self) -> None:
        """An EU brand instantiated the way every runtime call site does
        (brand= only) yields a ``de__de__BRAND`` state — never ``us__…``."""
        conn = EUDataActConnector(_DummySession(), brand="volkswagen")
        assert conn._state == "de__de__VOLKSWAGEN_PASSENGER_CARS"
        assert not conn._state.startswith("us__")

    def test_eu_state_uses_supplied_country_language(self) -> None:
        """When a caller DOES thread EU country/language, the state reflects
        them — proving the state is driven by the EU fields, not the NA one."""
        conn = EUDataActConnector(
            _DummySession(), brand="volkswagen", country="ch", language="de"
        )
        assert conn._state == "ch__de__VOLKSWAGEN_PASSENGER_CARS"

    def test_na_country_value_never_leaks_into_eu_state(self) -> None:
        """Even if someone passed country='us' to the EU connector, that is the
        EU OIDC country field — it does NOT come from the NA selector. The
        config flow never threads CONF_COUNTRY here (see source test below),
        so in practice the EU state is country-neutral (de)."""
        # The realistic call (brand-only) is country-neutral:
        conn = EUDataActConnector(_DummySession(), brand="audi")
        assert conn._state.split("__")[0] == "de"


# ──────────────────────────────────────────────────────────────────────
# Source-level: _build_entry_data gating + EU call sites stay brand-only.
# ──────────────────────────────────────────────────────────────────────


class TestBuildEntryDataGatesCountry:
    def test_country_only_stored_for_volkswagen_na(self) -> None:
        src = _CONFIG_FLOW_PY.read_text(encoding="utf-8")
        # The gate exists ...
        assert 'if brand.lower() == "volkswagen_na":' in src
        assert 'data[CONF_COUNTRY] = user_input.get(CONF_COUNTRY, "us")' in src

    def test_country_not_stored_unconditionally(self) -> None:
        """The old unconditional persistence line must be gone."""
        src = _CONFIG_FLOW_PY.read_text(encoding="utf-8")
        assert 'CONF_COUNTRY:       user_input.get(CONF_COUNTRY, "us"),' not in src

    def test_build_entry_data_country_inside_brand_block(self) -> None:
        """Structurally: the only CONF_COUNTRY write in _build_entry_data sits
        under the volkswagen_na branch (defensive against an accidental
        un-gating regression)."""
        src = _CONFIG_FLOW_PY.read_text(encoding="utf-8")
        start = src.index("def _build_entry_data(")
        # The function ends at its sole ``return data`` statement.
        end = src.index("return data", start) + len("return data")
        body = src[start:end]
        gate_idx = body.index('if brand.lower() == "volkswagen_na":')
        write_idx = body.index("data[CONF_COUNTRY] = user_input.get(CONF_COUNTRY")
        assert write_idx > gate_idx, "CONF_COUNTRY write is not under the gate"


class TestEuConnectorCallSitesStayBrandOnly:
    """Every runtime EUDataActConnector(...) construction passes brand= only
    (no CONF_COUNTRY), so the NA selector can never reach the EU OIDC state."""

    def test_config_flow_eu_connector_is_brand_only(self) -> None:
        src = _CONFIG_FLOW_PY.read_text(encoding="utf-8")
        assert "EUDataActConnector(session, brand=brand)" in src
        # ... and it does NOT thread a country= into the EU connector.
        for line in src.splitlines():
            if "EUDataActConnector(" in line:
                assert "country=" not in line, (
                    f"EU connector got a country= in config_flow: {line!r}"
                )


if __name__ == "__main__":
    import pytest

    pytest.main([__file__, "-v"])
