# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#1165 / #659 — VW North America sign-in attestation wall.

Since ~2026-07-30 VW put the North-America con-veh SIGN-IN token exchange behind
Play-Integrity attestation. It 401s with a CarnetSP INVALID_REQUEST body BEFORE any
vehicle read, so without a dedicated error it looked identical to a wrong password
and NA owners looped re-entering credentials.

These tests verify:
1. The exception class exists and IS an AuthenticationError subclass (so the auth
   loop re-raises it) — but the config-flow maps it BEFORE the generic
   AuthenticationError, to its own error key rather than invalid_credentials.
2. _map_error routes na_signin_attestation to its own key, not cannot_connect.
3. strings.json + all 12 translations declare the key.
"""
from __future__ import annotations


class TestNorthAmericaAttestationErrorClass:
    def test_class_exists_and_subclasses_authentication_error(self) -> None:
        from custom_components.vag_connect.cariad.exceptions import (
            AuthenticationError,
            NorthAmericaAttestationError,
        )
        # It IS an AuthenticationError (the idk token-exchange loop re-raises
        # AuthenticationError subclasses) — the config-flow discriminates it by
        # catching it BEFORE the generic AuthenticationError branch.
        assert issubclass(NorthAmericaAttestationError, AuthenticationError)

    def test_message_mentions_attestation_not_credentials(self) -> None:
        from custom_components.vag_connect.cariad.exceptions import (
            NorthAmericaAttestationError,
        )
        msg = str(NorthAmericaAttestationError(
            "VW North America sign-in blocked by device attestation (HTTP 401)"
        ))
        assert "attestation" in msg.lower()
        assert "401" in msg


class TestConfigFlowMapping:
    def test_map_error_accepts_na_signin_attestation(self) -> None:
        from custom_components.vag_connect.config_flow import _map_error
        assert _map_error("na_signin_attestation") == "na_signin_attestation"

    def test_unknown_keys_still_fall_back(self) -> None:
        from custom_components.vag_connect.config_flow import _map_error
        assert _map_error("totally_made_up_error") == "cannot_connect"


class TestStringsJsonHasNewKey:
    def test_strings_json_has_na_signin_attestation(self) -> None:
        import json
        from pathlib import Path
        here = Path(__file__).resolve().parent.parent
        strings = json.loads(
            (here / "custom_components" / "vag_connect" / "strings.json").read_text(
                encoding="utf-8"
            )
        )
        errors = strings["config"]["error"]
        assert "na_signin_attestation" in errors
        msg = errors["na_signin_attestation"].lower()
        # Must tell the user it's NOT their password and is a VW-side lock.
        assert "password" in msg or "credentials" in msg
        assert "not" in msg
        assert "attestation" in msg or "play integrity" in msg


class TestAllTranslationsHaveNewKey:
    def test_all_translations_have_key(self) -> None:
        import json
        from pathlib import Path
        here = Path(__file__).resolve().parent.parent
        tdir = here / "custom_components" / "vag_connect" / "translations"
        missing = []
        for lang in ("cs", "de", "en", "es", "fr", "nl", "pl", "sv", "it", "nb", "da", "fi"):
            data = json.loads((tdir / f"{lang}.json").read_text(encoding="utf-8"))
            if "na_signin_attestation" not in data["config"]["error"]:
                missing.append(lang)
        assert not missing, f"Missing na_signin_attestation in: {missing}"
