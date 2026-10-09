# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#1768 — two config entries must not share a cookie jar, and a repair id must
not carry a raw VIN.

A household ran two Volkswagen entries, one per spouse's account, and reported
that one car showed up in both hubs while the other vanished and neither
delivered data. It is ours, and it is NOT fixed here — see the separate issue. The brand
client is handed Home Assistant's SHARED aiohttp session, which has one cookie jar for the whole installation,
and the EU Data Act portal is a pure cookie session: both entries logged into
the same portal host, into the same jar, so the second login takes over the
first and both coordinators then read the same car. Isolating that needs a
private session, and Home Assistant's helper for one reaches into its frame
helper, which a mocked hass has never set up — so it is its own change with
its own tests, not a line in a privacy hotfix.

The same report exposed a second, worse thing. The reporter attached two
config-entry diagnostics, and both contained a full cleartext VIN — inside the
repair id ``<entry>_historical_timeout_<VIN>``. Home Assistant writes its own
issue registry into those diagnostics, so our VIN redaction never sees it. That
exact failure mode was found and fixed for the sibling ``stale_data`` id under
#1626, whose comment says it "has leaked a full VIN in a public Scout upload" —
and the fix was never applied here.
"""
from __future__ import annotations

import inspect
import re
from unittest.mock import MagicMock, patch

from custom_components.vag_connect import repairs
from custom_components.vag_connect.cariad._util import mask_vin

VIN = "WVWZZZ1KZAW123456"
ENTRY = "01M2ZPQYGZEPAZH9KV8CN7D2KK"


# ── the repair id ───────────────────────────────────────────────────────────


def test_the_timeout_repair_id_carries_no_raw_vin() -> None:
    hass = MagicMock()
    with patch.object(repairs.ir, "async_create_issue") as create, \
            patch.object(repairs.ir, "async_delete_issue") as delete:
        repairs.raise_issue_historical_timeout(
            hass, ENTRY, VIN, masked_vin=mask_vin(VIN),
        )

    create.assert_called_once()
    issue_id = create.call_args.args[2]
    assert VIN not in issue_id, "the raw VIN is back in the repair id"
    assert issue_id == f"{ENTRY}_historical_timeout_{mask_vin(VIN)}"

    # the pre-upgrade card is cleared, or it would linger with the VIN in it
    assert any(
        c.args[2] == f"{ENTRY}_historical_timeout_{VIN}" for c in delete.call_args_list
    ), "the legacy raw-VIN id is not deleted on upgrade"


def test_clearing_removes_both_the_masked_and_the_legacy_id() -> None:
    hass = MagicMock()
    with patch.object(repairs.ir, "async_delete_issue") as delete:
        repairs.clear_issue_historical_timeout(hass, ENTRY, VIN)

    ids = [c.args[2] for c in delete.call_args_list]
    assert f"{ENTRY}_historical_timeout_{mask_vin(VIN)}" in ids
    assert f"{ENTRY}_historical_timeout_{VIN}" in ids


def test_no_repair_id_in_this_module_is_built_from_a_raw_vin() -> None:
    """The whole class of bug, not just the one instance. Creation sites only —
    deletes legitimately still name the legacy id."""
    src = inspect.getsource(repairs)
    creates = re.findall(
        r"async_create_issue\((.*?)\)\s*\n(?=\s*(?:def|#|@|\Z))", src, re.S,
    )
    assert creates, "found no create sites — the pattern stopped matching"
    offenders = [
        c[:80] for c in creates
        if re.search(r'_\{vin\}"', c) and "mask_vin" not in c
    ]
    assert not offenders, f"repair ids built from a raw VIN: {offenders}"
