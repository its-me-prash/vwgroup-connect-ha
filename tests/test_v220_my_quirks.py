# Copyright 2026 Prash Balan (@its-me-prash) — Apache License 2.0
# SPDX-License-Identifier: Apache-2.0
"""v2.2.0 PR #5 — MY/Platform quirk-suppression layer.

Catches the bug-class that the existing ``_capabilities.py`` Phase 3
filter cannot: backend advertises capability as supported but the
specific firmware/MY combination silently fails the actual call.

Seed-rows under test:
- CUPRA Born MY24-MY25 → suppress ``command_unlock`` (pycupra #79)
- Audi e-tron MY24+    → suppress engine_start/stop  (upstream #711)

"Have you met... your car's actual capabilities?"
— Ted Mosby, on quirk-suppression
"""

from __future__ import annotations

import pytest

from custom_components.vag_connect.cariad._my_quirks import (
    QUIRKS,
    MYQuirk,
    is_command_suppressed,
)


class TestSeedRows:
    """The shipped quirks must keep doing their thing — regression-shield."""

    def test_cupra_born_my24_unlock_suppressed(self) -> None:
        assert is_command_suppressed("cupra", "Born", 2024, "command_unlock") is True

    def test_cupra_born_my25_unlock_suppressed(self) -> None:
        assert is_command_suppressed("cupra", "Born", 2025, "command_unlock") is True

    def test_cupra_born_my26_unlock_not_suppressed(self) -> None:
        # year_max is 2025 → MY26+ should NOT be suppressed
        assert is_command_suppressed("cupra", "Born", 2026, "command_unlock") is False

    def test_cupra_born_my23_unlock_not_suppressed(self) -> None:
        # year_min is 2024 → MY23 should NOT be suppressed
        assert is_command_suppressed("cupra", "Born", 2023, "command_unlock") is False

    def test_audi_q6_etron_my24_engine_start_suppressed(self) -> None:
        # PPE platform pure-electric: no remote engine start possible
        assert (
            is_command_suppressed("audi", "Q6 e-tron", 2024, "command_engine_start")
            is True
        )

    def test_audi_a6_etron_my25_engine_stop_suppressed(self) -> None:
        assert (
            is_command_suppressed("audi", "A6 e-tron", 2025, "command_engine_stop")
            is True
        )

    def test_audi_q6_etron_my23_engine_start_not_suppressed(self) -> None:
        # year_min is 2024 → MY23 not matched
        assert (
            is_command_suppressed("audi", "Q6 e-tron", 2023, "command_engine_start")
            is False
        )

    def test_audi_a4_my24_engine_start_not_suppressed(self) -> None:
        # Not an e-tron → quirk's model_glob doesn't match
        assert (
            is_command_suppressed("audi", "A4", 2024, "command_engine_start") is False
        )


class TestBrandMatching:
    """Brand match is exact lower-case — no fuzzy."""

    def test_uppercase_brand_normalised(self) -> None:
        assert is_command_suppressed("CUPRA", "Born", 2024, "command_unlock") is True

    def test_mixed_case_brand_normalised(self) -> None:
        assert is_command_suppressed("Cupra", "Born", 2024, "command_unlock") is True

    def test_wrong_brand_does_not_match(self) -> None:
        # Born is CUPRA — skoda model lookup shouldn't trip the quirk
        assert is_command_suppressed("skoda", "Born", 2024, "command_unlock") is False

    def test_volkswagen_not_matched_by_cupra_quirk(self) -> None:
        assert (
            is_command_suppressed("volkswagen", "Born", 2024, "command_unlock") is False
        )

    def test_empty_brand_is_safe(self) -> None:
        # Defensive: don't crash, just don't suppress
        assert is_command_suppressed("", "Born", 2024, "command_unlock") is False

    def test_none_brand_is_safe(self) -> None:
        # Defensive — code uses ``(brand or "")`` so None must not crash
        assert (
            is_command_suppressed(None, "Born", 2024, "command_unlock")  # type: ignore[arg-type]
            is False
        )


class TestModelGlobMatching:
    """Case-insensitive substring — surgical scoping."""

    def test_substring_match_lowercase(self) -> None:
        # "Born" substring matches "cupra born" or "Born e-Boost"
        assert (
            is_command_suppressed("cupra", "cupra born", 2024, "command_unlock")
            is True
        )

    def test_substring_match_with_trim(self) -> None:
        assert (
            is_command_suppressed("cupra", "Born e-Boost", 2024, "command_unlock")
            is True
        )

    def test_etron_substring_matches_q6(self) -> None:
        assert (
            is_command_suppressed(
                "audi", "Q6 e-tron quattro", 2024, "command_engine_start"
            )
            is True
        )

    def test_etron_substring_matches_a6(self) -> None:
        assert (
            is_command_suppressed(
                "audi", "A6 e-tron Sportback", 2025, "command_engine_stop"
            )
            is True
        )

    def test_wrong_model_does_not_match(self) -> None:
        # Leon != Born
        assert (
            is_command_suppressed("cupra", "Leon e-Hybrid", 2024, "command_unlock")
            is False
        )

    def test_missing_model_with_glob_quirk_safe(self) -> None:
        # Defensive: if model is missing but quirk requires model match,
        # don't suppress
        assert is_command_suppressed("cupra", None, 2024, "command_unlock") is False

    def test_empty_model_with_glob_quirk_safe(self) -> None:
        assert is_command_suppressed("cupra", "", 2024, "command_unlock") is False


class TestYearBracketing:
    """Inclusive year bounds — match boundary conditions explicitly."""

    def test_year_min_boundary_inclusive(self) -> None:
        # 2024 is the lower bound — must match
        assert is_command_suppressed("cupra", "Born", 2024, "command_unlock") is True

    def test_year_max_boundary_inclusive(self) -> None:
        # 2025 is the upper bound — must match
        assert is_command_suppressed("cupra", "Born", 2025, "command_unlock") is True

    def test_year_below_min_excluded(self) -> None:
        assert is_command_suppressed("cupra", "Born", 2023, "command_unlock") is False

    def test_year_above_max_excluded(self) -> None:
        assert is_command_suppressed("cupra", "Born", 2026, "command_unlock") is False

    def test_open_ended_year_max(self) -> None:
        # Audi e-tron quirk has year_max=None → MY99 should still match
        assert (
            is_command_suppressed("audi", "Q6 e-tron", 2099, "command_engine_start")
            is True
        )

    def test_missing_year_with_year_min_safe(self) -> None:
        # Defensive: if model_year is missing but year_min is set, don't suppress
        assert is_command_suppressed("cupra", "Born", None, "command_unlock") is False


class TestCommandIdMatching:
    """Only commands in ``suppress_commands`` get suppressed."""

    def test_unrelated_command_not_suppressed(self) -> None:
        # CUPRA Born MY24 quirk only suppresses unlock, NOT lock
        assert is_command_suppressed("cupra", "Born", 2024, "command_lock") is False

    def test_unrelated_command_audi_etron(self) -> None:
        # Audi e-tron quirk only suppresses engine_start/stop, NOT charging
        assert (
            is_command_suppressed("audi", "Q6 e-tron", 2024, "command_start_charging")
            is False
        )

    def test_unknown_command_not_suppressed(self) -> None:
        # Random made-up command never appears in any quirk
        assert (
            is_command_suppressed("cupra", "Born", 2024, "command_make_coffee")
            is False
        )


class TestMultipleQuirksExtensibility:
    """Adding a second quirk that targets the same vehicle must compose."""

    def test_synthetic_overlapping_quirk(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Two quirks both target CUPRA Born MY24 with different commands.

        Both must independently suppress their own command_id.
        """
        extra = MYQuirk(
            brand="cupra",
            model_glob="Born",
            year_min=2024,
            year_max=2025,
            suppress_commands=frozenset({"command_climatisation_start"}),
            source="synthetic test row",
        )
        monkeypatch.setattr(
            "custom_components.vag_connect.cariad._my_quirks.QUIRKS",
            [*QUIRKS, extra],
        )
        # Existing quirk still works
        assert is_command_suppressed("cupra", "Born", 2024, "command_unlock") is True
        # New quirk works
        assert (
            is_command_suppressed(
                "cupra", "Born", 2024, "command_climatisation_start"
            )
            is True
        )
        # Unrelated command still not suppressed
        assert is_command_suppressed("cupra", "Born", 2024, "command_lock") is False


class TestQuirkDataclassImmutability:
    """``frozen=True`` means quirks can't be mutated at runtime."""

    def test_quirk_is_frozen(self) -> None:
        quirk = QUIRKS[0]
        with pytest.raises((AttributeError, Exception)):
            quirk.brand = "skoda"  # type: ignore[misc]

    def test_quirk_has_source_string(self) -> None:
        # Every quirk must have a source for future-archaeology
        for q in QUIRKS:
            assert q.source, f"Quirk {q!r} missing source attribution"
            assert isinstance(q.source, str)
