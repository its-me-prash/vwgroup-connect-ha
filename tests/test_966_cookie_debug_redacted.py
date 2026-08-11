# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#966 (@Jradon001) — the vw.de resume can die ~20-30s after a restart, and the
log only recorded a cookie COUNT, so the failing cookie couldn't be identified.
``_redacted_cookie_summary`` produces a value-free, one-line diff aid (names,
hosts, paths, expiries) that MUST never leak a cookie value.
"""
from __future__ import annotations

from custom_components.vag_connect.cariad.auth._website_authproxy import (
    _redacted_cookie_summary,
)


def test_summary_lists_name_host_path_and_expiry() -> None:
    summary = _redacted_cookie_summary([
        {"name": "auth0", "value": "TOP_SECRET_SESSION",
         "domain": "identity.vwgroup.io", "path": "/", "expires": "Fri, 01"},
    ])
    assert "auth0@identity.vwgroup.io/" in summary
    assert "exp=Fri, 01" in summary


def test_summary_never_leaks_the_value() -> None:
    """The whole point of the redaction — the value stays out of the log."""
    summary = _redacted_cookie_summary([
        {"name": "auth0", "value": "TOP_SECRET_SESSION",
         "domain": "identity.vwgroup.io", "path": "/"},
    ])
    assert "TOP_SECRET_SESSION" not in summary


def test_multiple_cookies_are_joined() -> None:
    summary = _redacted_cookie_summary([
        {"name": "auth0", "value": "a", "domain": "identity.vwgroup.io",
         "path": "/"},
        {"name": "did", "value": "b", "domain": "www.volkswagen.de", "path": "/"},
    ])
    assert "auth0@identity.vwgroup.io" in summary
    assert "did@www.volkswagen.de" in summary
    assert summary.count(",") >= 1


def test_empty_set_is_labelled_not_blank() -> None:
    assert _redacted_cookie_summary([]) == "(none)"


def test_missing_keys_do_not_crash() -> None:
    summary = _redacted_cookie_summary([{"value": "SECRETVAL"}])
    assert "?@?" in summary
    assert "SECRETVAL" not in summary
