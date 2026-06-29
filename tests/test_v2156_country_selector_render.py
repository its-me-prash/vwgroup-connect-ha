# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""v2.15.6 (gr6803/#465) — only SHOW the US/CA country selector to VW-NA.

Background (the defect)
=======================
v2.15.5 stopped *storing* ``CONF_COUNTRY`` for non-NA brands, but the dropdown
was still *rendered* on the shared credentials schema. Because the brand picker
lives in the very same form, a Volkswagen-EU user (or anyone before they pick a
brand) saw a stray "country" field that only offered USA / Canada — exactly the
report in gr6803 ("Bei country wird mir nur USA und Canada angeboten").

The fix
=======
``_credentials_schema`` now only includes the ``CONF_COUNTRY`` field when
``brand == "volkswagen_na"``. On the first render the brand is unknown so the
field is hidden; if a VW-NA login fails, the form re-renders with
``brand=volkswagen_na`` and the picker appears (us↔ca still selectable +
stored). Every other brand — and the brand-unknown first render — never shows
it. Reauth never had the field; reconfigure threads the stored brand, so an EU
reconfigure stays clean while a VW-NA reconfigure keeps the picker.

These are *behavioural* assertions: they build the real voluptuous schema and
inspect which keys it carries. ``config_flow`` is importable in this test env,
so we assert the actual rendered shape rather than grepping source.
"""

from __future__ import annotations

import voluptuous as vol

from custom_components.vag_connect import config_flow as cf
from custom_components.vag_connect.const import CONF_COUNTRY


def _schema_keys(schema: vol.Schema) -> set[str]:
    """Return the raw string keys of a voluptuous schema (unwraps Markers)."""
    return {str(getattr(marker, "schema", marker)) for marker in schema.schema}


class TestCountrySelectorRenderGating:
    """The country dropdown is rendered for volkswagen_na only."""

    def test_vw_na_schema_renders_country(self) -> None:
        schema = cf._credentials_schema(brand="volkswagen_na")
        assert CONF_COUNTRY in _schema_keys(schema)

    def test_vw_eu_schema_omits_country(self) -> None:
        schema = cf._credentials_schema(brand="volkswagen")
        assert CONF_COUNTRY not in _schema_keys(schema)

    def test_brand_unknown_first_render_omits_country(self) -> None:
        """The very first email_password render passes brand="" — no picker."""
        schema = cf._credentials_schema(brand="")
        assert CONF_COUNTRY not in _schema_keys(schema)

    def test_other_brands_omit_country(self) -> None:
        for brand in ("audi", "skoda", "seat", "cupra", "porsche", "bentley"):
            schema = cf._credentials_schema(brand=brand)
            assert CONF_COUNTRY not in _schema_keys(schema), (
                f"{brand} should not render the US/CA country picker"
            )

    def test_vw_na_picker_carries_us_ca_options_default(self) -> None:
        """VW-NA still gets the dropdown with the chosen country as default,
        proving us/ca remain selectable + threaded through."""
        schema = cf._credentials_schema(brand="volkswagen_na", country="ca")
        marker = next(
            m for m in schema.schema if str(getattr(m, "schema", m)) == CONF_COUNTRY
        )
        assert marker.default() == "ca"
        assert schema.schema[marker] is cf._COUNTRY_SELECTOR

    def test_core_fields_present_for_every_brand(self) -> None:
        """Gating the country field must not drop the rest of the schema."""
        core = {"brand", "username", "password", "spin", "scan_interval"}
        for brand in ("volkswagen", "volkswagen_na", "audi", ""):
            keys = _schema_keys(cf._credentials_schema(brand=brand))
            assert core <= keys, f"{brand} lost core fields: {core - keys}"


if __name__ == "__main__":
    import pytest

    pytest.main([__file__, "-v"])
