# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Opt-in on-disk ring buffer of raw EU Data Act datasets (P1-5).

Why this exists — and why it is OFF by default. The parsed last-known-good
vehicle snapshot is already persisted to ``.storage`` and restored on restart
(see ``vehicle_cache`` + the coordinator's ``_vehicle_store``), so cold-restart
backfill is already handled. What this adds is a *diagnostic trail*: when a user
reports a wrong or missing field, the last few RAW portal ZIPs let us reproduce
and re-parse the exact bytes the car sent, instead of asking them to extract and
share data by hand (the #465 / #702 / #957 investigations all needed that).

A raw dataset carries GPS + VIN + telemetry, so keeping it on disk is a privacy
cost the user opts into knowingly — hence the default-off option. When enabled
the archive is strictly bounded (a small count AND a byte cap per vehicle), the
VIN never appears in a path (it is hashed), identical datasets are stored once
(content-hash naming dedups a re-downloaded ZIP), and every filesystem op is
best-effort: a failure to write or prune never disturbs the poll.

The class is deliberately Home-Assistant-free — it takes a base directory and
does plain filesystem work — so it is unit-testable with ``tmp_path`` and its
blocking I/O can be driven from an executor by the coordinator.
"""
from __future__ import annotations

import hashlib
import itertools
import logging
import time
from pathlib import Path

_LOGGER = logging.getLogger(__name__)

_DEFAULT_MAX_FILES = 20
_DEFAULT_MAX_BYTES = 10 * 1024 * 1024  # 10 MiB per vehicle
_SUFFIX = ".zip"

# Process-wide monotonic sequence, so two datasets written in the same
# millisecond still get a stable order. The wall-clock epoch prefix drives
# ordering ACROSS restarts (the counter resets each run); the sequence only
# breaks ties within one run.
_SEQ = itertools.count()


def _hash_vin(vin: str) -> str:
    """Stable, non-reversible directory name for a VIN (keeps it out of paths)."""
    return hashlib.sha256(vin.encode("utf-8")).hexdigest()[:16]


def _content_tag(data: bytes) -> str:
    return hashlib.sha1(data, usedforsecurity=False).hexdigest()[:8]


def _sort_key(path: Path) -> tuple[float, int]:
    """Sort key from the ``{epoch}_{seq}_{tag}.zip`` filename; oldest sorts low.

    Epoch dominates (recency across restarts); the sequence breaks same-ms ties.
    An unparseable name falls back to mtime with sequence 0.
    """
    parts = path.name.split("_", 2)
    try:
        return (float(parts[0]), int(parts[1]))
    except (ValueError, IndexError):
        try:
            return (path.stat().st_mtime, 0)
        except OSError:
            return (0.0, 0)


class DatasetArchive:
    """A bounded per-vehicle ring buffer of raw dataset ZIPs on disk.

    Retention is enforced on every write by BOTH a file count and a total byte
    cap, oldest-first. All methods swallow filesystem errors and return a
    sentinel rather than raising — this is a best-effort diagnostic aid, never
    something that may break a poll.
    """

    def __init__(
        self,
        base_dir: str | Path,
        *,
        max_files: int = _DEFAULT_MAX_FILES,
        max_bytes: int = _DEFAULT_MAX_BYTES,
    ) -> None:
        self._base = Path(base_dir)
        self._max_files = max(1, int(max_files))
        self._max_bytes = max(1, int(max_bytes))

    def vin_dir(self, vin: str) -> Path:
        return self._base / _hash_vin(vin)

    def store(self, vin: str, data: bytes) -> Path | None:
        """Archive one raw dataset ZIP for *vin*, then prune. Best-effort.

        Returns the written (or already-present) path, or ``None`` if nothing
        was stored. A dataset whose content is already archived is not written
        again — the content hash is part of the filename, so a re-downloaded
        identical ZIP is a no-op.
        """
        if not data:
            return None
        try:
            vdir = self.vin_dir(vin)
            vdir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:  # pragma: no cover - unusual FS failure
            _LOGGER.debug("dataset archive: cannot create dir: %s", type(exc).__name__)
            return None

        tag = _content_tag(data)
        # Dedup: if this exact content is already on disk (any epoch), keep it.
        try:
            existing = list(vdir.glob(f"*_{tag}{_SUFFIX}"))
        except OSError:
            existing = []
        if existing:
            self._prune(vdir)
            return existing[0]

        path = vdir / f"{time.time():.3f}_{next(_SEQ):06d}_{tag}{_SUFFIX}"
        try:
            path.write_bytes(data)
        except OSError as exc:
            _LOGGER.debug("dataset archive: write failed: %s", type(exc).__name__)
            return None
        self._prune(vdir)
        return path

    def list_datasets(self, vin: str) -> list[Path]:
        """Newest-first list of archived ZIPs for *vin* (empty on any error)."""
        try:
            files = [p for p in self.vin_dir(vin).glob(f"*{_SUFFIX}") if p.is_file()]
        except OSError:
            return []
        return sorted(files, key=_sort_key, reverse=True)

    def _prune(self, vdir: Path) -> None:
        """Enforce the count + byte caps, oldest-first. Drops unreadable files."""
        try:
            files = [p for p in vdir.glob(f"*{_SUFFIX}") if p.is_file()]
        except OSError:
            return
        # oldest first
        files.sort(key=_sort_key)

        sizes: dict[Path, int] = {}
        for p in files:
            try:
                sizes[p] = p.stat().st_size
            except OSError:
                # unreadable/vanished → try to remove, exclude from accounting
                self._unlink(p)
        live = [p for p in files if p in sizes]

        total = sum(sizes[p] for p in live)
        # Drop oldest until BOTH caps are satisfied. Always keep at least the
        # newest file even if it alone exceeds the byte cap (a single dataset is
        # worth more than an empty archive).
        idx = 0
        while live and idx < len(live) - 1 and (
            len(live) - idx > self._max_files or total > self._max_bytes
        ):
            victim = live[idx]
            self._unlink(victim)
            total -= sizes.get(victim, 0)
            idx += 1

    @staticmethod
    def _unlink(path: Path) -> None:
        try:
            path.unlink(missing_ok=True)
        except OSError as exc:  # pragma: no cover
            _LOGGER.debug("dataset archive: could not remove %s: %s", path.name, exc)
