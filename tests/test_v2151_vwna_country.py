# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""v2.15.1 (#503) — Volkswagen US/Canada region selector.

``cariad/api/vw_na.py`` takes a ``country='us'|'ca'`` argument, and
``cariad/api/factory.py`` ``create(..., country="us")`` forwards it. Until
this fix nothing let a user pick the region: the config flow never collected
a country and the coordinator never passed one, so every VW-NA install
defaulted to ``us``.

(v2.26.0 note, #915: US and CA share the one phone client, 59992128, but each
uses its OWN regional host — US = us00, CA = ca00 — confirmed by a live capture
of the official Canada app. The earlier N7 "CA = us00" was a static-scan
artefact: the host is runtime-templated by country code, so ``ca00`` never
appeared as a literal to grep.)

The fix plumbs a ``CONF_COUNTRY`` value end-to-end:

  const.py            — defines CONF_COUNTRY = "country"
  config_flow.py      — collects it (dropdown US/CA), validates against
                        the right endpoint, and stores it in entry.data
  coordinator.py      — passes entry.data[CONF_COUNTRY] (default "us")
                        to the factory on every reload

These are source-level + JSON-level assertions (same idiom as
``test_v230_sprint_b.py``) so they run without a live HA install. They
pin the wiring against regression and document the backward-compatible
``us`` default.
"""

from __future__ import annotations

import json
from pathlib import Path


_REPO_ROOT = Path(__file__).resolve().parent.parent
_COMPONENT = _REPO_ROOT / "custom_components" / "vag_connect"
_CONST_PY = _COMPONENT / "const.py"
_CONFIG_FLOW_PY = _COMPONENT / "config_flow.py"
_COORDINATOR_PY = _COMPONENT / "coordinator.py"
_FACTORY_PY = _COMPONENT / "cariad" / "api" / "factory.py"
_VW_NA_PY = _COMPONENT / "cariad" / "api" / "vw_na.py"
_STRINGS_JSON = _COMPONENT / "strings.json"
_TRANSLATIONS = _COMPONENT / "translations"
_LANGS = ["en", "de", "es", "fr", "nl", "pl", "cs", "sv", "it", "nb", "da", "fi"]


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


# ──────────────────────────────────────────────────────────────────────
# (a) Schema + selector wiring in config_flow.py / const.py
# ──────────────────────────────────────────────────────────────────────


class TestCaUsesOwnHostSharedClient:
    """v2.26.0 (#915) — Canada uses its OWN regional host (ca00), confirmed by a
    live capture of the official app, but still SHARES the 59992128 client with
    US (only the old per-CA client_id stays removed). The earlier N7 "CA = us00"
    was a static-scan artefact: the host is runtime-templated by country code, so
    ``ca00`` never appeared as a literal to find."""

    def test_no_ca_client_id_constant(self) -> None:
        src = _VW_NA_PY.read_text(encoding="utf-8")
        assert "_CA_CLIENT_ID" not in src

    def test_old_ca_client_id_stays_removed(self) -> None:
        # Only the HOST changed to ca00; the old unvalidated per-CA client_id
        # must stay gone (CA shares the 59992128 client with US).
        src = _VW_NA_PY.read_text(encoding="utf-8")
        assert "69eb3c39" not in src

    def test_ca_base_points_to_ca00(self) -> None:
        # The _COUNTRY_BASES["ca"] entry must resolve to Canada's own ca00 host.
        import re
        src = _VW_NA_PY.read_text(encoding="utf-8")
        m = re.search(r'"ca":\s*"([^"]+)"', src)
        assert m is not None
        assert m.group(1) == "https://b-h-s.spr.ca00.p.con-veh.net"

    def test_us_base_still_us00(self) -> None:
        import re
        src = _VW_NA_PY.read_text(encoding="utf-8")
        m = re.search(r'"us":\s*"([^"]+)"', src)
        assert m is not None
        assert m.group(1) == "https://b-h-s.spr.us00.p.con-veh.net"

    def test_client_id_is_unconditional_shared(self) -> None:
        # No country ternary selecting a different client_id: CA shares 59992128.
        src = _VW_NA_PY.read_text(encoding="utf-8")
        assert 'client_id = BRAND_VW_NA.client_id' in src
        assert 'if self._country == "ca"' not in src


class TestCountryConstAndSelector:
    """const.py defines CONF_COUNTRY; config_flow builds the dropdown."""

    def test_const_defines_conf_country(self) -> None:
        src = _CONST_PY.read_text(encoding="utf-8")
        assert 'CONF_COUNTRY' in src
        assert 'CONF_COUNTRY                  = "country"' in src

    def test_config_flow_imports_conf_country(self) -> None:
        src = _CONFIG_FLOW_PY.read_text(encoding="utf-8")
        assert "CONF_COUNTRY" in src

    def test_country_selector_defined(self) -> None:
        src = _CONFIG_FLOW_PY.read_text(encoding="utf-8")
        # The selector itself + its two inline-labelled options.
        assert "_COUNTRY_SELECTOR" in src
        assert 'value="us"' in src
        assert 'value="ca"' in src
        assert 'label="United States"' in src
        assert 'label="Canada"' in src

    def test_country_selector_is_dropdown_no_translation_key(self) -> None:
        """Dropdown mode, inline labels — no per-option i18n keys added."""
        src = _CONFIG_FLOW_PY.read_text(encoding="utf-8")
        # Pull out just the _COUNTRY_SELECTOR definition block.
        idx = src.index("_COUNTRY_SELECTOR")
        block = src[idx : idx + 400]
        assert "SelectSelectorMode.DROPDOWN" in block
        assert "translation_key" not in block

    def test_credentials_schema_has_country_field(self) -> None:
        src = _CONFIG_FLOW_PY.read_text(encoding="utf-8")
        # The builder gained a country= parameter ...
        assert 'country: str = "us"' in src
        # ... and the schema attaches the optional field with the selector.
        # v2.15.6 (gr6803/#465): the field is now added conditionally (only for
        # volkswagen_na) via item-assignment instead of an unconditional dict
        # literal, so we assert the selector wiring rather than the old literal.
        assert (
            "schema[vol.Optional(CONF_COUNTRY, default=country)] = _COUNTRY_SELECTOR"
            in src
        )


# ──────────────────────────────────────────────────────────────────────
# (b) _validate_credentials forwards country to the factory
# ──────────────────────────────────────────────────────────────────────


class TestValidateForwardsCountry:
    """_validate_credentials accepts country and passes it to the factory."""

    def test_validate_signature_has_country(self) -> None:
        src = _CONFIG_FLOW_PY.read_text(encoding="utf-8")
        assert 'country: str = "us"' in src

    def test_validate_passes_country_to_factory(self) -> None:
        src = _CONFIG_FLOW_PY.read_text(encoding="utf-8")
        assert (
            "CariadClientFactory.create(\n"
            "            brand, auth_session, username, password, country=country\n"
            "        )"
        ) in src

    def test_email_password_reads_and_forwards_country(self) -> None:
        src = _CONFIG_FLOW_PY.read_text(encoding="utf-8")
        assert 'country  = user_input.get(CONF_COUNTRY, "us")' in src
        # The email_password step calls _validate_credentials with country=.
        assert (
            "await _validate_credentials(\n"
            "                    self.hass, brand, username, password, country=country\n"
            "                )"
        ) in src

    def test_factory_create_accepts_country_kwarg(self) -> None:
        """Sanity: the factory really does take a country kwarg (the WHY)."""
        src = _FACTORY_PY.read_text(encoding="utf-8")
        assert 'country: str = "us"' in src
        assert "country=country" in src


# ──────────────────────────────────────────────────────────────────────
# (c) _build_entry_data persists CONF_COUNTRY
# ──────────────────────────────────────────────────────────────────────


class TestEntryDataStoresCountry:
    """The persisted entry data dict carries the chosen country — but ONLY
    for the volkswagen_na brand (v2.15.5 scoping fix)."""

    def test_build_entry_data_stores_country_for_vwna(self) -> None:
        src = _CONFIG_FLOW_PY.read_text(encoding="utf-8")
        # v2.15.5 — gated behind a volkswagen_na brand check so EU/other
        # brands no longer get a bogus country="us" stamped into entry.data.
        assert 'if brand.lower() == "volkswagen_na":' in src
        assert 'data[CONF_COUNTRY] = user_input.get(CONF_COUNTRY, "us")' in src


# ──────────────────────────────────────────────────────────────────────
# (d) coordinator passes country from entry.data
# ──────────────────────────────────────────────────────────────────────


class TestCoordinatorPassesCountry:
    """coordinator.py threads the stored country into the factory call."""

    def test_coordinator_imports_conf_country(self) -> None:
        src = _COORDINATOR_PY.read_text(encoding="utf-8")
        assert "CONF_COUNTRY" in src

    def test_coordinator_create_passes_country_from_entry(self) -> None:
        src = _COORDINATOR_PY.read_text(encoding="utf-8")
        assert 'country=self.entry.data.get(CONF_COUNTRY, "us")' in src


# ──────────────────────────────────────────────────────────────────────
# Backward-compat + reauth/reconfigure plumbing
# ──────────────────────────────────────────────────────────────────────


class TestReauthReconfigureThreadCountry:
    """Reauth + reconfigure reuse the stored country so CA users stay on CA."""

    def test_reauth_reuses_stored_country(self) -> None:
        src = _CONFIG_FLOW_PY.read_text(encoding="utf-8")
        assert 'country  = reauth_entry.data.get(CONF_COUNTRY, "us")' in src

    def test_reconfigure_schema_threads_country(self) -> None:
        src = _CONFIG_FLOW_PY.read_text(encoding="utf-8")
        assert 'country=current.get(CONF_COUNTRY, "us")' in src


# ──────────────────────────────────────────────────────────────────────
# i18n labels exist for every step whose schema now shows the field
# ──────────────────────────────────────────────────────────────────────


class TestCountryI18nLabels:
    """email_password + reconfigure steps must label the country field in
    strings.json and all 8 translation files."""

    _STEPS = ("email_password", "reconfigure")

    def test_strings_json_has_country_labels(self) -> None:
        data = _load(_STRINGS_JSON)
        steps = data["config"]["step"]
        for step in self._STEPS:
            assert "country" in steps[step]["data"], (
                f"strings.json {step}.data missing country label"
            )

    def test_all_translations_have_country_labels(self) -> None:
        for lang in _LANGS:
            data = _load(_TRANSLATIONS / f"{lang}.json")
            steps = data["config"]["step"]
            for step in self._STEPS:
                assert "country" in steps[step]["data"], (
                    f"{lang}.json {step}.data missing country label"
                )

    def test_strings_and_en_country_label_agree(self) -> None:
        s = _load(_STRINGS_JSON)["config"]["step"]
        e = _load(_TRANSLATIONS / "en.json")["config"]["step"]
        for step in self._STEPS:
            assert s[step]["data"]["country"] == e[step]["data"]["country"]

    def test_country_labels_are_translated_not_blank(self) -> None:
        """Non-EN labels must be non-empty (translated, not left raw EN-only)."""
        for lang in _LANGS:
            data = _load(_TRANSLATIONS / f"{lang}.json")
            for step in self._STEPS:
                label = data["config"]["step"][step]["data"]["country"]
                assert isinstance(label, str) and label.strip(), (
                    f"{lang}.json {step}.data.country is empty"
                )


if __name__ == "__main__":
    import pytest

    pytest.main([__file__, "-v"])
