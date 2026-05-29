# Copyright 2026 Prash Balan (@its-me-prash) — Apache License 2.0
"""v2.5.7 — UpstreamUnavailableError (502-storm UX fix).

When CARIAD-BFF returns 5xx on token exchange, that's NOT a credentials
problem — it's VW's server-side flapping (Azure WAF + upstream
incidents, e.g. the 2026-05-28 + 2026-05-29 502 storm).

These tests verify:
1. The new exception class exists and is distinct from AuthenticationError
2. The exception carries the HTTP status + brand for diagnostics
3. The user-visible message clearly says "server-side issue, NOT credentials"
4. The exception is mapped to the dedicated `upstream_unavailable`
   error key in config_flow (not the misleading `invalid_credentials`)
"""

from __future__ import annotations


class TestUpstreamUnavailableErrorClass:
    """The exception class itself — shape contract."""

    def test_class_exists_and_is_distinct_from_auth(self) -> None:
        from custom_components.vag_connect.cariad.exceptions import (
            AuthenticationError,
            CariadError,
            UpstreamUnavailableError,
        )
        # Must be a CariadError but NOT an AuthenticationError —
        # otherwise existing except-clauses would catch it and the
        # config-flow would surface it as invalid_credentials again.
        assert issubclass(UpstreamUnavailableError, CariadError)
        assert not issubclass(UpstreamUnavailableError, AuthenticationError)

    def test_carries_status_and_brand(self) -> None:
        from custom_components.vag_connect.cariad.exceptions import (
            UpstreamUnavailableError,
        )
        err = UpstreamUnavailableError(502, brand="audi")
        assert err.status == 502
        assert err.brand == "audi"

    def test_user_message_says_not_credentials(self) -> None:
        """The whole point of this exception is so the user does not
        misdiagnose a server outage as a credentials failure. Make sure
        the message stays explicit."""
        from custom_components.vag_connect.cariad.exceptions import (
            UpstreamUnavailableError,
        )
        msg = str(UpstreamUnavailableError(502, brand="audi"))
        assert "credentials" in msg.lower() or "credential" in msg.lower()
        # Specifically NOT a credentials problem
        assert "not" in msg.lower()
        # Tells the user to wait
        assert any(word in msg.lower() for word in ("wait", "again", "retry"))
        # Tells the user NOT to reconfigure
        assert "reconfigur" in msg.lower()

    def test_message_includes_status_code(self) -> None:
        from custom_components.vag_connect.cariad.exceptions import (
            UpstreamUnavailableError,
        )
        msg = str(UpstreamUnavailableError(503, brand="volkswagen"))
        assert "503" in msg

    def test_message_works_without_brand(self) -> None:
        from custom_components.vag_connect.cariad.exceptions import (
            UpstreamUnavailableError,
        )
        # brand="" is the default — should still produce a sensible message
        msg = str(UpstreamUnavailableError(502))
        assert "502" in msg
        assert "credentials" in msg.lower()


class TestConfigFlowMapping:
    """The config_flow must route UpstreamUnavailableError to the
    dedicated `upstream_unavailable` error key — not `invalid_credentials`."""

    def test_map_error_accepts_upstream_unavailable(self) -> None:
        from custom_components.vag_connect.config_flow import _map_error
        # Must NOT fall through to cannot_connect
        assert _map_error("upstream_unavailable") == "upstream_unavailable"

    def test_map_error_known_keys_include_upstream(self) -> None:
        """Heuristic check that the allow-list in _map_error wasn't
        accidentally regressed when we added upstream_unavailable."""
        from custom_components.vag_connect.config_flow import _map_error
        # All these should pass through unchanged
        for key in (
            "terms_and_conditions", "marketing_consent", "two_factor_required",
            "too_many_requests", "invalid_credentials", "missing_library",
            "upstream_unavailable",
        ):
            assert _map_error(key) == key

    def test_unknown_keys_still_fall_back_to_cannot_connect(self) -> None:
        from custom_components.vag_connect.config_flow import _map_error
        # Unknown keys must still fall through — defense-in-depth
        # for typo prevention.
        assert _map_error("totally_made_up_error") == "cannot_connect"


class TestStringsJsonHasNewKey:
    """The English strings.json must declare the new error key with a
    message that explicitly tells the user 'NOT credentials'."""

    def test_strings_json_has_upstream_unavailable(self) -> None:
        import json
        from pathlib import Path
        here = Path(__file__).resolve().parent.parent
        strings = json.loads(
            (here / "custom_components" / "vag_connect" / "strings.json").read_text(
                encoding="utf-8"
            )
        )
        errors = strings["config"]["error"]
        assert "upstream_unavailable" in errors
        msg = errors["upstream_unavailable"]
        assert "credentials" in msg.lower()
        assert "not" in msg.lower()
        assert "wait" in msg.lower() or "again" in msg.lower()


class TestAllTranslationsHaveNewKey:
    """All 8 shipped language translations must include the new key
    with localised text — otherwise HA shows the English fallback."""

    def test_all_translations_have_key(self) -> None:
        import json
        from pathlib import Path
        here = Path(__file__).resolve().parent.parent
        translations_dir = here / "custom_components" / "vag_connect" / "translations"
        missing = []
        for lang in ("cs", "de", "en", "es", "fr", "nl", "pl", "sv"):
            data = json.loads((translations_dir / f"{lang}.json").read_text(encoding="utf-8"))
            errors = data["config"]["error"]
            if "upstream_unavailable" not in errors:
                missing.append(lang)
        assert not missing, f"Missing upstream_unavailable in: {missing}"
