# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#1690 — the Vehicle Data Scout posted a car's VIN into a public issue.

``auth_signature_response`` carries a hex blob with the VIN embedded as ASCII.
``mask_value`` masked VINs with a PLAIN-TEXT pattern, so nothing matched; the
80-character truncation then left the VIN sitting inside the surviving prefix,
and the Scout wrote it into the issue body.

**This happened five times.** #1510, #1549, #1585 and #1591 were each
hand-redacted after the fact — the bodies still carry those redaction notes —
and the masker was never fixed, so #1690 leaked the next reporter's VIN.
Truncation is not redaction.

The blob below is the real value from #1690 with its VIN bytes replaced by a
different, invented VIN, so the test exercises the real shape without carrying
anyone's identifier into the repository.
"""
from __future__ import annotations

import re

from custom_components.vag_connect.cariad._unexpected_keys import mask_value

# "WVGZZZE21TE099999" in ASCII-hex, wrapped in signature-shaped bytes
_FAKE_VIN = "WVGZZZE21TE099999"
BLOB = (
    "2378d141538eb5bca400190100000"
    + _FAKE_VIN.encode().hex()
    + "3cd89d16f1132"
)
VINISH = re.compile(rb"[A-HJ-NPR-Z0-9]{17}")


def _recoverable(masked: str) -> bool:
    """Can a VIN still be decoded out of what we would publish?"""
    for run in re.findall(r"[0-9a-fA-F]{24,}", masked):
        for off in (0, 1):
            cand = run[off:]
            cand = cand[: len(cand) // 2 * 2]
            try:
                raw = bytes.fromhex(cand)
            except ValueError:
                continue
            if VINISH.search(raw):
                return True
    return False


def test_the_real_blob_shape_leaked_before_and_must_not_now():
    assert _recoverable(BLOB), "the fixture itself must contain a recoverable VIN"
    out = mask_value(BLOB)
    assert not _recoverable(out), f"VIN still recoverable from {out!r}"
    assert _FAKE_VIN not in out


def test_the_replacement_says_what_was_removed_without_printing_it():
    out = mask_value(BLOB)
    assert "redacted" in out
    assert "credential" in out
    assert str(len(BLOB)) in out, "the length is the one useful fact to keep"


def test_odd_nibble_alignment_is_caught():
    """A VIN can start on an odd nibble — a decoder that only tries offset 0
    would walk straight past it."""
    shifted = "a" + _FAKE_VIN.encode().hex() + "b" * 30
    assert not _recoverable(mask_value(shifted))


def test_a_plain_text_vin_is_still_masked_the_old_way():
    out = mask_value(f"the car {_FAKE_VIN} reported")
    assert _FAKE_VIN not in out
    assert "099999" in out, "the last six are kept deliberately, as everywhere else"


def test_ordinary_values_are_untouched():
    # the encoded-identifier check must not turn normal samples into redactions
    assert mask_value("deadbeef") == '"deadbeef"'
    assert mask_value("18.0 Unit_DegreCelsi") == '"18.0 Unit_DegreCelsi"'
    assert mask_value("TRIGGER_NO_REASON") == '"TRIGGER_NO_REASON"'
    assert mask_value(42) == "42"
    assert mask_value(None) == "null"
    assert mask_value(True) == "true"
    assert mask_value({"a": 1, "b": 2}) == "{2 keys}"


def test_a_long_hex_run_without_an_identifier_is_kept():
    """Not every hex blob is a credential — a checksum or a raw frame still has
    diagnostic value and must survive, truncated as before."""
    benign = "ab12cd34" * 12  # 96 chars, decodes to no VIN-shaped ASCII
    out = mask_value(benign)
    assert "redacted" not in out
    assert out.startswith('"ab12cd34')


def test_the_gps_and_token_rules_still_apply():
    assert mask_value(48.123456) == "48.1"
    assert mask_value("a@b.example") == '"***@***"'
