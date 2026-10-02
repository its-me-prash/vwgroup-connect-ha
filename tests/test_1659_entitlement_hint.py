# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#1659 (@Joassens) — make an entitlement refusal say what it means.

The reporter's vw.de maintenance read was refused with
``403 (BFF 4007 connectivityLicenseInactive)``. That is precise and completely
unactionable: he read it as a market/registration problem, I agreed with him in
writing, he spent a day on it — and then fixed it by buying the paid Car-Net
"Guide & Inform Plus" subscription, which is exactly what the code said.

The command path already classifies these codes (0xFA7 → SUBSCRIPTION_EXPIRED);
the read path only recorded the raw name. It now appends what the refusal means
and logs it once, so the next person does not repeat that day.

Transient and consent-shaped refusals must NOT get the subscription wording —
4004 missingUserConsent in particular, because that one is not an entitlement gap
and telling someone to buy a subscription for it would be a confident wrong
answer.
"""
from __future__ import annotations

from custom_components.vag_connect.cariad._bff_error_codes import (
    decode_bff_error,
    reason_for_bff_code,
)
from custom_components.vag_connect.cariad.auth._website_authproxy import (
    _ENTITLEMENT_HINTS,
)
from custom_components.vag_connect.cariad.exceptions import CommandFailureReason


def test_the_reporters_code_asks_for_the_subscription():
    code, name = decode_bff_error('{"error":{"code":4007}}')
    assert (code, name) == (0xFA7, "connectivityLicenseInactive")
    hint = _ENTITLEMENT_HINTS[reason_for_bff_code(code)]
    assert "paid connected-services subscription" in hint


def test_the_consent_refusal_gets_no_hint_at_all():
    # 4004 missingUserConsent sat right next to 4007 in the same report; it is a
    # consent problem, so it must never produce "buy a subscription".
    code, name = decode_bff_error('{"error":{"code":4004}}')
    assert name == "missingUserConsent"
    assert reason_for_bff_code(code) not in _ENTITLEMENT_HINTS


def test_not_entitled_asks_for_enrolment_not_for_money():
    """2101 userNotEnrolled is an entitlement gap too, but paying is the wrong
    advice for it — the account needs enrolling."""
    code, name = decode_bff_error('{"error":{"code":2101}}')
    assert name == "userNotEnrolled"
    hint = _ENTITLEMENT_HINTS[reason_for_bff_code(code)]
    assert "enrol" in hint
    assert "paid" not in hint and "subscription" not in hint


def test_only_entitlement_reasons_carry_a_hint():
    assert set(_ENTITLEMENT_HINTS) == {
        CommandFailureReason.SUBSCRIPTION_EXPIRED,
        CommandFailureReason.NOT_ENTITLED,
    }
    assert CommandFailureReason.BACKEND_ERROR not in _ENTITLEMENT_HINTS
    for hint in _ENTITLEMENT_HINTS.values():
        assert hint.endswith("."), "a hint is a sentence the user can act on"


def test_an_unknown_code_yields_nothing_to_claim():
    assert decode_bff_error('{"error":{"code":999999}}') is None
    assert decode_bff_error("not json") is None
    assert decode_bff_error("") is None


def test_the_hint_is_wired_into_the_read_path_and_logged_once():
    import inspect

    from custom_components.vag_connect.cariad.auth import _website_authproxy as wap

    src = inspect.getsource(wap)
    # the hint is gated on the entitlement classification, not the raw status
    assert "_ENTITLEMENT_HINTS.get(" in src
    assert "reason_for_bff_code(" in src
    # and the machine-readable diagnostics surface stays code-only, so existing
    # reports and tests keep parsing
    assert 'self.probe_outcomes[record_as] = f"{resp.status}{_detail}"' in src
    # and the WARNING is latched per read so a poll loop cannot spam the log
    assert "self._entitlement_logged" in src
    assert src.count("_entitlement_logged.add(") == 1


def test_the_latch_starts_empty_on_a_fresh_connector():
    from unittest.mock import MagicMock

    from custom_components.vag_connect.cariad.auth._website_authproxy import (
        WebsiteAuthProxyConnector,
    )

    c = WebsiteAuthProxyConnector(MagicMock(), "a@b.c", "pw", brand="volkswagen")
    assert c._entitlement_logged == set()
