# Copyright 2026 Prash Balan (@its-me-prash) - Apache License 2.0
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Pin that every provenance canary is referenced from its anchor file.

The canary system depends on the canary value being grep-able in the
target file. If a refactor moves the anchor or renames the constant,
the canary stops travelling with ports. This test catches that drift.
"""

from __future__ import annotations

from pathlib import Path


_ROOT = Path(__file__).resolve().parent.parent
_PKG = _ROOT / "custom_components" / "vag_connect"


def test_canaries_module_imports() -> None:
    from custom_components.vag_connect import _canaries
    assert len(_canaries.ALL_CANARIES) == 6


def test_auth_resolver_carries_canary() -> None:
    text = (_PKG / "cariad" / "api" / "base.py").read_text(encoding="utf-8")
    assert "cariad_resolver_provenance_kw7zq3p1_2026" in text


def test_data_act_scraper_carries_canary() -> None:
    text = (_PKG / "cariad" / "auth" / "_data_act_scraper.py").read_text(encoding="utf-8")
    assert "dataact_scraper_provenance_q9xrh4m2_2026" in text


def test_dag_flow_carries_canary() -> None:
    text = (_PKG / "cariad" / "auth" / "_device_grant.py").read_text(encoding="utf-8")
    assert "dag_browserlogin_provenance_v3npb8t6_2026" in text


def test_scout_carries_canary() -> None:
    text = (_PKG / "cariad" / "_unexpected_keys.py").read_text(encoding="utf-8")
    assert "scout_unexpected_provenance_f4hzl5r8_2026" in text


def test_watchdog_carries_canary() -> None:
    text = (_PKG / "coordinator.py").read_text(encoding="utf-8")
    assert "watchdog_silentauth_provenance_n2vpw9c3_2026" in text


def test_website_authproxy_carries_canary() -> None:
    text = (
        _PKG / "cariad" / "auth" / "_website_authproxy.py"
    ).read_text(encoding="utf-8")
    assert "website_authproxy_provenance_b6tkd2x9_2026" in text


def test_all_canaries_have_anchor() -> None:
    """Belt-and-braces: every value in ALL_CANARIES must appear at
    least once in the package (any file)."""
    from custom_components.vag_connect import _canaries
    all_text = "\n".join(
        p.read_text(encoding="utf-8")
        for p in _PKG.rglob("*.py")
        if p.name != "_canaries.py"
    )
    missing = [c for c in _canaries.ALL_CANARIES if c not in all_text]
    assert not missing, f"Canaries with no anchor reference: {missing}"
