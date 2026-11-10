# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#2071 — the keep_raw_datasets archive hook must be attached on the PERIODIC
poll path, not only on the manual-refresh path.

``update_interval`` is None, so HA never calls ``_async_update_data`` on a timer;
the background ``_poll_loop`` is the periodic driver. The archive hook was wired
only inside ``_async_update_data``, so after a restart (when only the poll loop
runs) the on-disk dataset ring buffer silently stopped growing while the portal
feed kept delivering. ``_wire_dataset_archive`` is documented idempotent and
"safe to call on every poll", so both paths must (re)attach it.
"""
from __future__ import annotations

import inspect

from custom_components.vag_connect.coordinator import VagConnectCoordinator


def test_archive_is_wired_on_both_the_poll_loop_and_the_manual_path() -> None:
    poll = inspect.getsource(VagConnectCoordinator._poll_loop)
    manual = inspect.getsource(VagConnectCoordinator._async_update_data)
    assert "_wire_dataset_archive()" in poll, (
        "the periodic _poll_loop must (re)attach the keep_raw_datasets archive "
        "hook — otherwise archiving stops after a restart (#2071)"
    )
    assert "_wire_dataset_archive()" in manual
