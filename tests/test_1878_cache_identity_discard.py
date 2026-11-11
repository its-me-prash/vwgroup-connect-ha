# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#1878 — a cached vehicle snapshot must not survive a reauth onto a DIFFERENT
account.

The snapshot lives in a Store keyed by the config entry id, so a credential
reauth (which keeps the same entry id) left the old account's SoC / position
frozen in place while fresh fields updated. The fix fingerprints the account
(``account_identity_hash``) beside the snapshot and discards the VEHICLE restore
at load when a STORED fingerprint is present and differs — never when it is
absent (a pre-#1878 snapshot), so no existing user's cache is wiped once on
upgrade, and never the account-independent drop-retry budget.
"""
from __future__ import annotations

import pathlib

from custom_components.vag_connect.cariad.vehicle_cache import account_identity_hash

# ── the pure fingerprint ────────────────────────────────────────────────────


def test_hash_is_stable_and_normalised() -> None:
    # case + surrounding whitespace must not change the fingerprint (a cosmetic
    # re-type of the same e-mail must not discard a valid cache)
    assert account_identity_hash("User@X.com ") == account_identity_hash("user@x.com")
    # a genuinely different account must differ
    assert account_identity_hash("a@b.com") != account_identity_hash("c@d.com")


def test_hash_is_none_without_an_identity() -> None:
    assert account_identity_hash(None) is None
    assert account_identity_hash("") is None
    assert account_identity_hash("   ") is None


def test_hash_does_not_leak_the_identity() -> None:
    h = account_identity_hash("secret.person@email.com")
    assert h is not None
    assert "secret" not in h and "@" not in h and "email" not in h


# ── the wiring, pinned against the coordinator source ───────────────────────

_COORD = (
    pathlib.Path(__file__).resolve().parents[1]
    / "custom_components/vag_connect/coordinator.py"
)


def test_identity_hash_is_written_on_save_and_compared_on_load() -> None:
    src = _COORD.read_text(encoding="utf-8")
    # save side: the snapshot carries the fingerprint
    assert '"identity_hash": account_identity_hash(' in src
    # load side: current vs stored is computed and gates the restore
    assert "_stored_identity" in src
    assert "_current_identity" in src
    assert "_identity_ok" in src


def test_only_the_vehicle_restore_is_gated_not_the_drop_state_budget() -> None:
    src = _COORD.read_text(encoding="utf-8")
    # the vehicles restore is gated by the identity check …
    assert 'if _identity_ok and cached and isinstance(cached.get("vehicles"), dict):' in src
    # … while the drop-retry budget restore stays account-independent (present,
    # and NOT behind the identity gate).
    assert "drop_state_from_cache(" in src


def test_discard_only_on_present_and_different_fingerprint() -> None:
    # The missing-hash upgrade contract: discard requires a NON-None stored hash.
    src = _COORD.read_text(encoding="utf-8")
    assert "_stored_identity is not None and _stored_identity != _current_identity" in src
