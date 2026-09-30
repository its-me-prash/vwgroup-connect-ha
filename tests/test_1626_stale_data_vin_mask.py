# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#1626 — the stale-data repair-issue id must not embed the raw VIN.

The id is dumped verbatim in config-entry diagnostics (it bypasses the VIN
redaction that masks the dedicated ``vin`` fields), and a reporter's public Scout
upload leaked a full VIN this way. The id is now keyed on the masked VIN, and the
legacy raw-VIN id is cleared on both raise and clear so a pre-fix repair does not
linger.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from custom_components.vag_connect import repairs

_VIN = "WVWZZZED9SE038720"
_ENTRY = "01M0R7251ZNWXP8G6G3CJMV4G5"


def test_raise_id_masks_the_vin_and_clears_legacy() -> None:
    hass = MagicMock()
    with patch.object(repairs.ir, "async_create_issue") as create, \
            patch.object(repairs.ir, "async_delete_issue") as delete:
        repairs.raise_issue_stale_data(
            hass, _ENTRY, _VIN, masked_vin=repairs.mask_vin(_VIN), age_hours=100,
        )
    issue_id = create.call_args.args[2]
    assert _VIN not in issue_id, "raw VIN must never be in the issue id"
    assert _VIN[-6:] in issue_id, "id should carry the masked (last-6) VIN"
    # legacy raw-VIN issue is deleted so a pre-fix one does not linger
    deleted = [c.args[2] for c in delete.call_args_list]
    assert f"{_ENTRY}_stale_data_{_VIN}" in deleted


def test_clear_deletes_masked_and_legacy_ids() -> None:
    hass = MagicMock()
    with patch.object(repairs.ir, "async_delete_issue") as delete:
        repairs.clear_stale_data_issue(hass, _ENTRY, _VIN)
    deleted = [c.args[2] for c in delete.call_args_list]
    # legacy raw id cleared (migration) AND a masked id cleared, matching raise
    assert f"{_ENTRY}_stale_data_{_VIN}" in deleted
    masked = [d for d in deleted if d != f"{_ENTRY}_stale_data_{_VIN}"]
    assert masked and all(_VIN not in d for d in masked)


def test_raise_and_clear_agree_on_the_masked_id() -> None:
    hass = MagicMock()
    with patch.object(repairs.ir, "async_create_issue") as create, \
            patch.object(repairs.ir, "async_delete_issue"):
        repairs.raise_issue_stale_data(
            hass, _ENTRY, _VIN, masked_vin="whatever-display", age_hours=100,
        )
    raised_id = create.call_args.args[2]
    with patch.object(repairs.ir, "async_delete_issue") as delete:
        repairs.clear_stale_data_issue(hass, _ENTRY, _VIN)
    cleared = [c.args[2] for c in delete.call_args_list]
    # the id used by raise must be one of the ids clear deletes (independent of the
    # display masked_vin passed to raise)
    assert raised_id in cleared
