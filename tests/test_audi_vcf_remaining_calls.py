# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The Audi BFF reports its remaining daily calls as ``Vcf-Remaining-Calls``.

Only ``X-RateLimit-Remaining`` was read, so ``requests_remaining_today`` and the
probe guard stayed empty on Audi accounts. The Audi header is now the fallback;
``X-RateLimit-Remaining`` still wins when both are present.
"""
from __future__ import annotations

from custom_components.vag_connect.cariad.api.base import CariadBaseClient


def _client() -> CariadBaseClient:
    c = CariadBaseClient.__new__(CariadBaseClient)
    c.last_rate_limit_remaining = None
    c.last_rate_limit_limit = None
    c.last_rate_limit_reset_at = None
    return c


def test_the_audi_header_fills_the_remaining_calls() -> None:
    c = _client()
    c._capture_rate_limit_headers({"Vcf-Remaining-Calls": "4876"})
    assert c.last_rate_limit_remaining == 4876


def test_the_standard_header_still_wins() -> None:
    c = _client()
    c._capture_rate_limit_headers({"X-RateLimit-Remaining": "12", "Vcf-Remaining-Calls": "4876"})
    assert c.last_rate_limit_remaining == 12


def test_an_unreadable_audi_header_keeps_the_previous_value() -> None:
    c = _client()
    c.last_rate_limit_remaining = 30
    c._capture_rate_limit_headers({"Vcf-Remaining-Calls": "unlimited"})
    assert c.last_rate_limit_remaining == 30


def test_no_header_at_all_keeps_the_previous_value() -> None:
    c = _client()
    c.last_rate_limit_remaining = 30
    c._capture_rate_limit_headers({})
    assert c.last_rate_limit_remaining == 30
