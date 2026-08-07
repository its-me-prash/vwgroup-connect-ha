# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""P1-5 — opt-in on-disk raw-dataset ring buffer.

The archive is a best-effort diagnostic trail: bounded per vehicle by BOTH a
file count and a byte cap, VIN-hashed on disk, content-deduped, and never
raising on a filesystem error. These tests pin all four properties.
"""
from __future__ import annotations

from pathlib import Path

from custom_components.vag_connect.cariad.dataset_archive import (
    DatasetArchive,
    _hash_vin,
)

_VIN = "WVWZZZAAAA0000042"


def test_store_and_list_roundtrip(tmp_path: Path) -> None:
    arc = DatasetArchive(tmp_path)
    p = arc.store(_VIN, b"PK\x03\x04 one")
    assert p is not None and p.exists()
    assert p.read_bytes() == b"PK\x03\x04 one"
    listed = arc.list_datasets(_VIN)
    assert listed == [p]


def test_vin_is_hashed_never_in_path(tmp_path: Path) -> None:
    arc = DatasetArchive(tmp_path)
    p = arc.store(_VIN, b"x")
    assert p is not None
    # The raw VIN must not appear anywhere in the stored path.
    assert _VIN not in str(p)
    assert _hash_vin(_VIN) in str(p)


def test_identical_content_is_stored_once(tmp_path: Path) -> None:
    arc = DatasetArchive(tmp_path)
    a = arc.store(_VIN, b"same-bytes")
    b = arc.store(_VIN, b"same-bytes")
    assert a == b
    assert len(arc.list_datasets(_VIN)) == 1


def test_count_cap_keeps_newest(tmp_path: Path) -> None:
    arc = DatasetArchive(tmp_path, max_files=5, max_bytes=10**9)
    paths = [arc.store(_VIN, f"dataset-{i}".encode()) for i in range(12)]
    listed = arc.list_datasets(_VIN)
    assert len(listed) == 5
    # newest-first list must be exactly the last 5 written (order preserved)
    assert listed == list(reversed(paths[-5:]))


def test_byte_cap_prunes_oldest(tmp_path: Path) -> None:
    # 1 KiB payloads, 3 KiB cap → at most 3 retained.
    arc = DatasetArchive(tmp_path, max_files=1000, max_bytes=3 * 1024)
    for i in range(10):
        arc.store(_VIN, bytes([i % 256]) * 1024)
    listed = arc.list_datasets(_VIN)
    assert 1 <= len(listed) <= 3
    total = sum(p.stat().st_size for p in listed)
    assert total <= 3 * 1024


def test_single_oversized_dataset_is_still_kept(tmp_path: Path) -> None:
    # A lone dataset larger than the byte cap must not leave an empty archive.
    arc = DatasetArchive(tmp_path, max_files=10, max_bytes=100)
    p = arc.store(_VIN, b"z" * 500)
    assert p is not None and p.exists()
    assert arc.list_datasets(_VIN) == [p]


def test_empty_payload_is_ignored(tmp_path: Path) -> None:
    arc = DatasetArchive(tmp_path)
    assert arc.store(_VIN, b"") is None
    assert arc.list_datasets(_VIN) == []


def test_store_failure_is_swallowed(tmp_path: Path) -> None:
    # base_dir is a FILE → mkdir under it raises OSError, which must be caught.
    blocker = tmp_path / "not-a-dir"
    blocker.write_bytes(b"x")
    arc = DatasetArchive(blocker)
    assert arc.store(_VIN, b"data") is None  # no raise
    assert arc.list_datasets(_VIN) == []


def test_two_vins_are_isolated(tmp_path: Path) -> None:
    arc = DatasetArchive(tmp_path, max_files=2)
    other = "WVWZZZAAAA0000099"
    for i in range(3):
        arc.store(_VIN, f"a{i}".encode())
        arc.store(other, f"b{i}".encode())
    assert len(arc.list_datasets(_VIN)) == 2
    assert len(arc.list_datasets(other)) == 2
    # cross-VIN content never bleeds
    assert all(b"a" == p.read_bytes()[:1] for p in arc.list_datasets(_VIN))
    assert all(b"b" == p.read_bytes()[:1] for p in arc.list_datasets(other))
