# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#1772 (@HeBraun, VW ID.4 Pro 4MOTION) / #1769 (@derschneewolf, Audi) — the
Scout reported eight new fields on the ID.4 whose DIDs are all eight we already
decode. That can only happen one way: ``_uds_envelope`` returned no parameters
for every one of them, because the dispatch loop adds a key to ``used`` only
after a non-empty decode, so an envelope we fail to read keeps being reported.

What makes it fail is visible in @derschneewolf's attachment. Every UDS value in
it arrives with a trailing space — ``"MTIw "`` — and ``base64.b64decode`` with
``validate=True`` rejects any character outside the alphabet, a space included.
That is not stray whitespace: it is the portal's own ``<value> <unit-token>``
convention with an empty unit, the same shape ``_first_number`` was written for
in #1622 (``"3644.0 Unit_MilliVolt"``). So the fix is the split that function
already uses, not a strip — a value arriving as ``"<base64> Unit_Something"``
must survive too.

The payload below is @dasebi91's real 0x2AB6 envelope from #1661, reused
deliberately: a byte-identical payload must decode whether or not the portal
appends the separator, which is what makes the pair of assertions decisive
rather than a restatement of the implementation.
"""
from __future__ import annotations

import base64
import json

from custom_components.vag_connect.cariad.auth._eu_data_act import (
    _UDS_HANDLED_DIDS,
    _uds_envelope,
)

from .test_1661_uds_envelopes import REAL_RANGE_ENVELOPE


def test_real_envelope_still_decodes_without_a_separator() -> None:
    """Control. If this ever fails the rest of the file proves nothing."""
    params, captured = _uds_envelope(REAL_RANGE_ENVELOPE)
    assert params.get("Param_RangeSumDispl") == "244"
    assert params.get("Param_RangeUnitDispl") == "kilometre"
    assert captured == "2026-10-01T08:02:31.126Z"


def test_trailing_space_does_not_discard_the_reading() -> None:
    """@derschneewolf's observed shape: the value then one trailing space."""
    params, captured = _uds_envelope(REAL_RANGE_ENVELOPE + " ")
    assert params.get("Param_RangeSumDispl") == "244", (
        "a trailing separator must not cost us the whole envelope"
    )
    assert captured == "2026-10-01T08:02:31.126Z"


def test_appended_unit_token_does_not_discard_the_reading() -> None:
    """The same convention with a non-empty unit token (#1622's shape)."""
    params, _ = _uds_envelope(REAL_RANGE_ENVELOPE + " Unit_Unknown")
    assert params.get("Param_RangeSumDispl") == "244"


def test_leading_whitespace_is_tolerated_too() -> None:
    params, _ = _uds_envelope("  " + REAL_RANGE_ENVELOPE + "\n")
    assert params.get("Param_RangeSumDispl") == "244"


def test_every_handled_did_survives_the_separator() -> None:
    """#1772 reported all eight handled DIDs at once, so cover all eight.

    One envelope per DID, each carrying a single recognisable parameter, each
    with the trailing separator. A regression that breaks only some DIDs (for
    example one dispatching on a differently-shaped key) fails here.
    """
    for did in sorted(_UDS_HANDLED_DIDS):
        doc = {
            "schema": "diagDataResults_Response_Schema_V1.3.json",
            "DiagnosticData": [{
                "DiagNodeStatus": "Success",
                "Timestamp": "2026-10-09T11:50:04.088506Z",
                "DataObjects": [{
                    "Result": "Success",
                    "Values": [{"ParamShortName": "Param_Probe", "Value": did}],
                }],
            }],
        }
        raw = base64.b64encode(json.dumps(doc).encode()).decode()
        params, _ = _uds_envelope(raw + " ")
        assert params.get("Param_Probe") == did, f"{did} lost its envelope"


def test_a_genuinely_corrupt_payload_still_yields_nothing() -> None:
    """The tolerance must not become "decode anything".

    ``validate=True`` is deliberate: a corrupt or non-base64 value has to stay
    Scout-visible rather than half-parse. Only the separator is forgiven.
    """
    for bad in (
        "not base64 at all!!",
        "eyJzY2hlbWEiOiAi",                      # valid base64, truncated JSON
        REAL_RANGE_ENVELOPE[:-8] + "@@@@@@@@",   # in-band corruption
        "",
        None,
    ):
        params, captured = _uds_envelope(bad)
        assert params == {}, f"{bad!r} must not produce parameters"
        assert captured is None


def test_a_bare_scalar_payload_is_not_mistaken_for_an_envelope() -> None:
    """#1767/#1769's TPMS values are base64 of a plain number, not a document.

    ``MTIw`` is ``120``: valid base64, valid JSON, and not an envelope. It must
    yield nothing here so the field stays Scout-visible — those four DIDs
    (0x4E94-0x4E97) carry no published unit yet, and a number without a unit is
    exactly what we must not turn into a sensor.
    """
    for scalar in ("MTIw ", "MjU1 ", "MTIw"):
        params, captured = _uds_envelope(scalar)
        assert params == {}
        assert captured is None
