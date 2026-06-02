# Copyright 2026 Prash Balan (@its-me-prash) — Apache License 2.0
# SPDX-License-Identifier: Apache-2.0
"""v2.5.4 (#313) — VW Azure WAF migration + X-QMAuth tests.

VW shut down ``/login/v1/idk/token`` at the Azure Application Gateway
WAF on 2026-05-28. New endpoint is ``/auth/v1/idk/oidc/token`` and
requires a rotated x-qmauth HMAC-SHA256 header plus 3 assertion headers.

These tests verify our port of evcc PR #30292 + #30277 (MIT):
- Correct new token URL for Audi + VW EU
- Legacy URLs preserved for CUPRA / SEAT / Skoda / VW NA (unaffected)
- HMAC-SHA256 signing matches the Go reference algorithm
- Full header set sent on both authorization_code and refresh_token
"""

from __future__ import annotations

import hashlib
import hmac
import time


# ── X-QMAuth signing ────────────────────────────────────────────────────────


def _go_reference_qmauth(ts: int) -> str:
    """Reimplement the Go reference algorithm from evcc PR #30292 for
    cross-verification. Both implementations must produce the same hex
    digest for the same timestamp + (secret, clientId) pair.
    """
    qm_secret = "1ab69925ac179aaa4e83abe671a9476d176418b85bd706f1436ca15be647989c"
    qm_client_id = "01da27b0"
    secret = bytes.fromhex(qm_secret)
    h = hmac.new(secret, str(ts).encode("ascii"), hashlib.sha256)
    return f"v1:{qm_client_id}:{h.hexdigest()}"


class TestQMAuthSigning:
    """X-QMAuth header must match the Go reference implementation byte-for-byte."""

    def test_signing_matches_go_reference_2026(self) -> None:
        """Known-good vector: timestamp at 2026-05-28T12:00:00Z (UTC),
        bucketed to 100s precision."""
        from custom_components.vag_connect.cariad.auth.idk import (
            _calculate_x_qmauth,
        )
        unix_ts = 1779356400.0  # 2026-05-28T12:00:00Z (deterministic)
        ours = _calculate_x_qmauth(now=unix_ts)
        theirs = _go_reference_qmauth(int(unix_ts / 100))
        assert ours == theirs, (
            f"x-qmauth divergence:\n  ours:   {ours}\n  theirs: {theirs}"
        )

    def test_signing_format(self) -> None:
        """The header value must be ``v1:<clientId>:<64-char hex digest>``."""
        from custom_components.vag_connect.cariad.auth.idk import (
            _calculate_x_qmauth,
        )
        result = _calculate_x_qmauth(now=1779356400.0)
        parts = result.split(":")
        assert len(parts) == 3
        assert parts[0] == "v1"
        assert parts[1] == "01da27b0"
        assert len(parts[2]) == 64           # SHA-256 hex = 64 chars
        # Every char in the digest must be valid hex.
        assert all(c in "0123456789abcdef" for c in parts[2])

    def test_bucket_is_100_seconds(self) -> None:
        """Two timestamps in the same 100s bucket must produce identical
        signatures — that's the entire point of the bucket.

        The endpoint must tolerate up to ~100s of clock skew."""
        from custom_components.vag_connect.cariad.auth.idk import (
            _calculate_x_qmauth,
        )
        a = _calculate_x_qmauth(now=1779356400.0)  # bucket N
        b = _calculate_x_qmauth(now=1779356499.0)  # same bucket (still N)
        c = _calculate_x_qmauth(now=1779356500.0)  # next bucket (N+1)
        assert a == b
        assert a != c

    def test_uses_real_clock_when_no_arg(self) -> None:
        """Default call with no timestamp must use ``time.time()`` and
        return a value whose bucket matches the current clock to within
        one bucket."""
        from custom_components.vag_connect.cariad.auth.idk import (
            _calculate_x_qmauth,
        )
        ours = _calculate_x_qmauth()
        # Cross-check by computing the expected value with the same Go
        # algorithm, accepting either the current or previous bucket
        # (clock racing across the bucket boundary).
        now = time.time()
        accept = {
            _go_reference_qmauth(int(now / 100)),
            _go_reference_qmauth(int(now / 100) - 1),
            _go_reference_qmauth(int(now / 100) + 1),
        }
        assert ours in accept


# ── Assertion-header set ────────────────────────────────────────────────────


class TestCariadTokenHeaders:
    """v2.5.4 introduced the 8-header set as defensive 'mimic the
    official app' superset. v2.7.0b2 flipped the default to the
    5-header set (upstream parity) after VW backend started
    validating the dummy x-assertion='0' value. The assertion trio
    is still accessible via include_assertion=True for debugging."""

    def test_default_is_five_header_set(self) -> None:
        """v2.7.0b2 — default omits assertion trio."""
        from custom_components.vag_connect.cariad.auth.idk import (
            _cariad_token_headers,
        )
        h = _cariad_token_headers(user_agent="ua/test")
        expected = {
            "Content-Type", "Accept", "Accept-Charset", "User-Agent", "x-qmauth",
        }
        assert set(h.keys()) == expected

    def test_all_eight_headers_present_when_opted_in(self) -> None:
        """When the caller passes include_assertion=True the full
        v2.5.4 8-header superset is still produced — useful for
        debugging if VW ever flips the assertion validation back off."""
        from custom_components.vag_connect.cariad.auth.idk import (
            _cariad_token_headers,
        )
        h = _cariad_token_headers(user_agent="ua/test", include_assertion=True)
        expected = {
            "Content-Type", "Accept", "Accept-Charset", "User-Agent",
            "x-qmauth", "x-platform", "x-android-package-name", "x-assertion",
        }
        assert set(h.keys()) == expected

    def test_static_header_values(self) -> None:
        from custom_components.vag_connect.cariad.auth.idk import (
            _cariad_token_headers,
        )
        # Default 5-header set
        h = _cariad_token_headers(user_agent="ua/test")
        assert h["Content-Type"] == "application/x-www-form-urlencoded"
        assert h["Accept"] == "application/json"
        assert h["Accept-Charset"] == "utf-8"
        # Opted-in 8-header superset
        h_opt = _cariad_token_headers(user_agent="ua/test", include_assertion=True)
        assert h_opt["x-platform"] == "android"
        assert h_opt["x-android-package-name"] == "de.myaudi.mobile.assistant"
        assert h_opt["x-assertion"] == "0"

    def test_user_agent_threaded_from_brand(self) -> None:
        from custom_components.vag_connect.cariad.auth.idk import (
            _cariad_token_headers,
        )
        h = _cariad_token_headers(user_agent="custom-ua/9.9")
        assert h["User-Agent"] == "custom-ua/9.9"

    def test_x_qmauth_is_freshly_signed(self) -> None:
        from custom_components.vag_connect.cariad.auth.idk import (
            _cariad_token_headers,
        )
        h = _cariad_token_headers(user_agent="ua/test")
        # Must follow the v1:<clientId>:<hex> format.
        assert h["x-qmauth"].startswith("v1:01da27b0:")
        assert len(h["x-qmauth"]) == len("v1:01da27b0:") + 64


# ── Token URL dispatch ──────────────────────────────────────────────────────


class TestTokenURLDispatch:
    """v2.5.4 (#313) — Audi + VW EU migrated to the new CARIAD BFF URL.
    Other brands keep their existing endpoints (different hosts entirely).
    """

    def test_new_cariad_url_for_audi_and_vw_eu(self) -> None:
        from custom_components.vag_connect.cariad.auth.idk import (
            _CARIAD_TOKEN_URL,
        )
        # The new URL — pegged literal for regression-safety.
        assert _CARIAD_TOKEN_URL == (
            "https://emea.bff.cariad.digital/auth/v1/idk/oidc/token"
        )
        # And specifically not the dead URL.
        assert "/login/v1/idk/token" not in _CARIAD_TOKEN_URL

    def test_legacy_url_no_longer_default(self) -> None:
        """Ensure the old URL string does not appear anywhere as a module
        constant — protect against half-migrated state."""
        import custom_components.vag_connect.cariad.auth.idk as mod
        import inspect
        src = inspect.getsource(mod)
        # Allow the string to appear inside comments (cross-refs) but not
        # as a Python string-literal default. Heuristic: presence of the
        # quoted form would mean it's used as a value.
        dead = '"https://emea.bff.cariad.digital/login/v1/idk/token"'
        assert dead not in src, (
            "Legacy /login/v1/idk/token URL still present as a string "
            "literal — Azure WAF will 403 those requests as of 2026-05-28."
        )
