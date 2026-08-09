# Copyright 2026 Prash Balan (@its-me-prash) - Apache License 2.0
# SPDX-License-Identifier: AGPL-3.0-or-later
"""v3.0.1 — Škoda passwordless (QR / device_code) login retired.

Volkswagen revoked the Škoda client's device_code grant in 2026-08:
``identity.vwgroup.io/oidc/v1/device_authorization`` returns
``403 unauthorized_client`` ("client is not allowed to use the device_code
grant") for the canonical Škoda client (7f045eee) and ``400`` for the
alternate (4fffed6b), while Audi still returns ``200`` (live-probed). Offering
the QR path for Škoda produced a silent config-flow reload for users.

The hotfix removes Škoda from the QR/device-grant surface; it now signs in via
email + password (IDK authorization-code), an independent path VW's revocation
does not touch. These tests pin the invariants of that fix.
"""
from __future__ import annotations

import json
from pathlib import Path

from custom_components.vag_connect.cariad.auth._device_grant import (
    DAG_ENABLED_BRANDS,
)
from custom_components.vag_connect.cariad._capabilities import (
    DECLARED_CAPABILITIES,
)

_COMPONENT = Path(__file__).resolve().parents[1] / "custom_components" / "vag_connect"


def test_skoda_not_dag_eligible() -> None:
    """Škoda must no longer be offered the QR/device_code path."""
    assert "skoda" not in DAG_ENABLED_BRANDS
    # the other DAG brands are untouched
    assert {"audi", "seat", "cupra", "audi_na"} <= DAG_ENABLED_BRANDS


def test_skoda_capability_dag_login_false() -> None:
    """The declared-capabilities table reflects the revoked grant."""
    assert DECLARED_CAPABILITIES["skoda"]["dag_login"] is False


def _error_block(fname: str) -> dict:
    data = json.loads((_COMPONENT / fname).read_text(encoding="utf-8"))
    return data["config"]["error"]


def test_skoda_qr_retired_string_present() -> None:
    """The guidance string exists in the source and the must-do locales."""
    for fname in ("strings.json", "translations/en.json", "translations/de.json"):
        errors = _error_block(fname)
        assert "skoda_qr_retired" in errors, fname
        # points the user at the email + password flow
        assert errors["skoda_qr_retired"].strip()
