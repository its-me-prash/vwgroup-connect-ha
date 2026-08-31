# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""MBB device-grant FAILOVER — a backup client for 9496332b.

VW killed the modern BFF two-way client (650d46ca) on 2026-08-18 with no warning.
The durable Car-Net (MBB) two-way rides a single device-grant client (9496332b);
if VW pulls that one too, the whole durable channel dies. ``40945ec0`` is a fresh
VW client that mints the SAME mbb-scoped token and was live-verified to
register→exchange into a durable XID_APP_VW bearer, so the config flow fails over
to it when the primary is rejected with ``unauthorized_client``. These pin the
backup config; the retry wiring lives in ``config_flow._do_request_device_code``.
"""
from __future__ import annotations

from custom_components.vag_connect.cariad.auth._device_grant import (
    MBB_DAG_CLIENT_ID,
    MBB_DAG_CLIENT_ID_BACKUP,
    MBB_DAG_SCOPE,
    mbb_dag_backup_config,
    mbb_dag_config,
)


def test_backup_is_a_drop_in_for_the_primary() -> None:
    primary = mbb_dag_config("volkswagen")
    backup = mbb_dag_backup_config("volkswagen")
    assert primary == (MBB_DAG_CLIENT_ID, MBB_DAG_SCOPE)
    assert backup == (MBB_DAG_CLIENT_ID_BACKUP, MBB_DAG_SCOPE)
    # A DIFFERENT client (so it survives a primary shutdown) but the SAME scope,
    # so register → exchange → refresh downstream are byte-for-byte identical.
    assert backup[0] != primary[0]
    assert backup[1] == primary[1]


def test_backup_client_is_the_verified_failover_id() -> None:
    assert MBB_DAG_CLIENT_ID_BACKUP.startswith("40945ec0-")
    assert MBB_DAG_CLIENT_ID_BACKUP.endswith("@apps_vw-dilab_com")
    assert MBB_DAG_CLIENT_ID_BACKUP != MBB_DAG_CLIENT_ID


def test_backup_config_mbb_brands_only() -> None:
    # b15 — audi joined the MBB brands (live-validated 2026-08-30) and the backup
    # shares MBB_DAG_BRANDS, so it fails over for audi too (same mbb scope).
    for brand in ("skoda", "seat", "cupra", "porsche", "bentley"):
        assert mbb_dag_backup_config(brand) is None
    assert mbb_dag_backup_config("Volkswagen") is not None  # case-insensitive
    assert mbb_dag_backup_config("audi") is not None         # b15
