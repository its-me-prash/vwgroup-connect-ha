# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""v2.2.2 — Scout #260 silencer-fix + cross-language translation cleanup.

Scout #260 (j4x5mgq94b-commits, Audi 2026-05-17) reported
`charging.chargingStatus.value.chargeRate_kmph` as a "new field" on Audi.
Reality: the field was already parsed since v1.10.0 (`vw_eu.py:916` →
`d.charging_rate_kmh` → `sensor.charging_speed`) but the dotted path
was never registered in EXPECTED_KEYS for the CARIAD-BFF
``selectivestatus`` endpoint. Classic "silencer hasn't caught up with
the parser" gap — Audi inherits via ``EXPECTED_KEYS["audi"] =
EXPECTED_KEYS["volkswagen"]`` so the fix is a one-line addition.

While doing the silencer audit we also pass over all 8 i18n files and
eliminate technical jargon from entity names so non-tech users see
laien-friendly labels:

- `SoC` (State of Charge) — replaced with the natural-language
  equivalent in each lang (DE "Ladestand"/"Ladeziel", FR "Charge",
  ES "Carga", NL "Lading", PL "Naładowanie", CS "Nabití",
  SV "Laddning", EN "Charge")
- DE: `Ladegeschwindigkeit (km/h)` → `Ladegeschwindigkeit` (entity
  is `SensorDeviceClass.SPEED` → HA auto-converts km/h ↔ mph; the
  hardcoded `(km/h)` suffix lied to mph-locale users)
- DE: `HV-Batterie` → `Akku` (HV = high-voltage, tech jargon)
- 6 of 8 langs had untranslated English strings for
  `next_charging_timer_id` and `next_charging_timer_target_soc_reachable`
  — now translated everywhere.

These tests pin the cleanup to prevent regression — if anyone adds a
new entity with `SoC` in the name, or leaves a non-EN file with raw
English strings, CI fails.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest


_REPO_ROOT = Path(__file__).resolve().parent.parent
_COMPONENT_ROOT = _REPO_ROOT / "custom_components" / "vag_connect"
_TRANSLATIONS = _COMPONENT_ROOT / "translations"
_LANGS = ["en", "de", "es", "fr", "nl", "pl", "cs", "sv"]
_ENTITY_KINDS = ("sensor", "binary_sensor", "switch", "number", "select", "button")


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


class TestSilencerScout260:
    """One-line silencer fix for `chargeRate_kmph` on CARIAD-BFF selectivestatus."""

    def test_chargerate_kmph_path_present_in_vw(self) -> None:
        # Use a sys.modules-stubbed import so the test runs without HA installed.
        import importlib.util
        import sys

        spec = importlib.util.spec_from_file_location(
            "_uk_check_v222",
            _COMPONENT_ROOT / "cariad" / "_unexpected_keys.py",
        )
        # Pre-load _util as a sibling so the relative import resolves.
        util_spec = importlib.util.spec_from_file_location(
            "_util_check_v222",
            _COMPONENT_ROOT / "cariad" / "_util.py",
        )
        util_mod = importlib.util.module_from_spec(util_spec)
        sys.modules["_util_check_v222"] = util_mod
        util_spec.loader.exec_module(util_mod)

        # Build a fake package so the `from ._util import mask_vin` resolves.
        import types

        pkg = types.ModuleType("_uk_pkg_v222")
        pkg.__path__ = [str(_COMPONENT_ROOT / "cariad")]
        sys.modules["_uk_pkg_v222"] = pkg
        sys.modules["_uk_pkg_v222._util"] = util_mod

        spec2 = importlib.util.spec_from_file_location(
            "_uk_pkg_v222._unexpected_keys",
            _COMPONENT_ROOT / "cariad" / "_unexpected_keys.py",
        )
        mod = importlib.util.module_from_spec(spec2)
        sys.modules["_uk_pkg_v222._unexpected_keys"] = mod
        spec2.loader.exec_module(mod)

        ek = mod.EXPECTED_KEYS
        vw_paths = ek["volkswagen"]["selectivestatus"]
        assert "charging.chargingStatus.value.chargeRate_kmph" in vw_paths, (
            "Scout #260 path missing from VW selectivestatus silencer"
        )

    def test_audi_inherits_via_shared_dict(self) -> None:
        # Same import bootstrap as above (separate scope so each test
        # can run standalone — pytest may pick either first).
        import importlib.util
        import sys
        import types

        for k in ("_uk_audi_v222", "_uk_audi_v222._unexpected_keys", "_uk_audi_v222._util"):
            sys.modules.pop(k, None)

        util_spec = importlib.util.spec_from_file_location(
            "_uk_audi_v222._util",
            _COMPONENT_ROOT / "cariad" / "_util.py",
        )
        util_mod = importlib.util.module_from_spec(util_spec)
        pkg = types.ModuleType("_uk_audi_v222")
        pkg.__path__ = [str(_COMPONENT_ROOT / "cariad")]
        sys.modules["_uk_audi_v222"] = pkg
        sys.modules["_uk_audi_v222._util"] = util_mod
        util_spec.loader.exec_module(util_mod)

        spec = importlib.util.spec_from_file_location(
            "_uk_audi_v222._unexpected_keys",
            _COMPONENT_ROOT / "cariad" / "_unexpected_keys.py",
        )
        mod = importlib.util.module_from_spec(spec)
        sys.modules["_uk_audi_v222._unexpected_keys"] = mod
        spec.loader.exec_module(mod)

        ek = mod.EXPECTED_KEYS
        # Audi inherits VW by reference — same dict identity, not a copy.
        assert ek["audi"] is ek["volkswagen"], (
            "Audi must inherit VW EXPECTED_KEYS by reference, not copy"
        )
        # Audi sees the same chargeRate_kmph path transitively.
        assert (
            "charging.chargingStatus.value.chargeRate_kmph"
            in ek["audi"]["selectivestatus"]
        )


class TestLaienFriendlyEntityNames:
    """No technical jargon in user-facing entity-name translations."""

    @pytest.mark.parametrize("lang", _LANGS)
    def test_no_soc_in_entity_names(self, lang: str) -> None:
        """`SoC` (State-of-Charge) is tech jargon; replaced everywhere."""
        d = _load(_TRANSLATIONS / f"{lang}.json")
        offenders = []
        for kind in _ENTITY_KINDS:
            for key, val in d.get("entity", {}).get(kind, {}).items():
                name = val.get("name", "")
                if re.search(r"\bSoC\b", name):
                    offenders.append(f"{lang}/{kind}/{key}: {name}")
        assert not offenders, (
            "SoC tech-jargon must be replaced with laien-friendly term:\n"
            + "\n".join(offenders)
        )

    @pytest.mark.parametrize("lang", _LANGS)
    def test_no_hv_batterie_in_de(self, lang: str) -> None:
        """DE: `HV-Batterie` (high-voltage) → `Akku` (everyday word)."""
        if lang != "de":
            pytest.skip("DE-only cleanup")
        d = _load(_TRANSLATIONS / f"{lang}.json")
        for kind in _ENTITY_KINDS:
            for key, val in d.get("entity", {}).get(kind, {}).items():
                name = val.get("name", "")
                assert "HV-Batterie" not in name, (
                    f"de/{kind}/{key} still uses tech 'HV-Batterie': {name}"
                )

    def test_charging_rate_kmh_no_unit_suffix_in_de(self) -> None:
        """DE: removed hardcoded `(km/h)` since HA auto-converts km/h ↔ mph."""
        d = _load(_TRANSLATIONS / "de.json")
        name = d["entity"]["sensor"]["charging_rate_kmh"]["name"]
        assert "(km/h)" not in name, (
            f"`charging_rate_kmh` DE name lies to mph-locale users: {name}"
        )
        # Sanity: the natural name is preserved.
        assert "Ladegeschwindigkeit" in name


class TestNoUntranslatedEnglishInNonEnFiles:
    """6 of 8 langs had raw English strings for 2 entity names — fixed."""

    # English-only phrases that should NEVER appear in a non-EN translation
    # (anchored to specific entity contexts so we don't false-positive on
    # proper nouns or universal acronyms like 'AdBlue' / 'PHEV').
    _ENGLISH_RESIDUE = re.compile(
        r"\b(Next Charging Timer|Primary Engine SoC|Charging Timer ID|"
        r"Target SoC Reachable)\b"
    )

    @pytest.mark.parametrize("lang", [l for l in _LANGS if l != "en"])
    def test_no_english_residue(self, lang: str) -> None:
        d = _load(_TRANSLATIONS / f"{lang}.json")
        offenders = []
        for kind in _ENTITY_KINDS:
            for key, val in d.get("entity", {}).get(kind, {}).items():
                name = val.get("name", "")
                if self._ENGLISH_RESIDUE.search(name):
                    offenders.append(f"{lang}/{kind}/{key}: {name}")
        assert not offenders, (
            f"Untranslated English in {lang}.json:\n" + "\n".join(offenders)
        )


class TestCrossLangParity:
    """Every entity key must exist in every language file (parity check)."""

    def _entity_keys(self, doc: dict) -> set[str]:
        keys: set[str] = set()
        for kind in _ENTITY_KINDS:
            for k in doc.get("entity", {}).get(kind, {}):
                keys.add(f"{kind}.{k}")
        return keys

    def test_all_langs_have_same_entity_keys_as_en(self) -> None:
        en = self._entity_keys(_load(_TRANSLATIONS / "en.json"))
        for lang in _LANGS:
            if lang == "en":
                continue
            other = self._entity_keys(_load(_TRANSLATIONS / f"{lang}.json"))
            missing = en - other
            extra = other - en
            assert not missing, (
                f"{lang}.json missing entity keys vs en.json: {sorted(missing)}"
            )
            # `extra` keys in non-EN are tolerated (lang-specific aliases),
            # but warn via assertion when egregious (>5).
            assert len(extra) < 10, (
                f"{lang}.json has unexpected extra entity keys: {sorted(extra)}"
            )


class TestStringsJsonInSync:
    """strings.json (en fallback) must agree with en.json for the touched keys."""

    _TOUCHED = [
        "active_charging_profile_target_soc_pct",
        "battery_care_target_soc_pct",
        "primary_engine_soc_pct",
        "next_charging_timer_id",
        "next_charging_timer_target_soc_reachable",
    ]

    def test_strings_and_en_agree(self) -> None:
        strings = _load(_COMPONENT_ROOT / "strings.json")
        en = _load(_TRANSLATIONS / "en.json")
        for key in self._TOUCHED:
            s = strings["entity"]["sensor"][key]["name"]
            e = en["entity"]["sensor"][key]["name"]
            assert s == e, (
                f"strings.json and en.json disagree on `{key}`: "
                f"strings={s!r} en={e!r}"
            )
            assert "SoC" not in s, (
                f"strings.json still has SoC in {key}: {s}"
            )
