# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The cached render images must not carry the VIN in their path or URL.

Why this is worse than a VIN in a log line. The cache lives under
``/config/www/``, which Home Assistant serves at ``/local/`` **without
authentication**, and the URL is published as an entity attribute. So the
filename ends up in a freely fetchable URL, in every dashboard that shows the
image, and in every screenshot of one.

The repository already made this decision once: ``dataset_archive`` hashes the
VIN out of its paths, with the docstring "keeps it out of paths". That rule was
never carried across to ``image.py``. This file is the rule in both places.

Two halves, and the second is the one that matters for anyone already running
the integration: new files are named from a hash, **and** files that an earlier
version named with the VIN are removed. A fix that only changes future names
leaves the old file sitting there, still served, still carrying the VIN.
"""
from __future__ import annotations

import os
from unittest.mock import MagicMock

import pytest

from custom_components.vag_connect.image import (
    _CACHE_SUBDIR,
    _local_path,
    _local_url,
    _purge_legacy_vin_files,
)

#: Synthetic, per the repository's own rule — never a real VIN in a test.
VIN = "WVWZZZAUZFW000000"
OTHER = "WVWZZZAUZFW000001"


def _hass(root: str = "/config"):
    hass = MagicMock()
    hass.config.path = MagicMock(
        side_effect=lambda *parts: os.path.join(root, *parts)
    )
    return hass


@pytest.mark.parametrize("vin", [VIN, OTHER, "wvwzzzauzfw000000"])
def test_the_url_does_not_carry_the_vin(vin):
    url = _local_url(vin, "side")
    assert vin not in url
    assert vin.lower() not in url.lower()
    assert vin.upper() not in url.upper()


def test_the_path_does_not_carry_the_vin():
    path = _local_path(_hass(), VIN, "side")
    assert VIN not in path
    assert VIN.lower() not in path.lower()


def test_the_url_still_points_into_the_cache_directory():
    # The change must not move the file out from under /local/, or every
    # existing dashboard card breaks.
    url = _local_url(VIN, "side")
    assert url.startswith(f"/local/{_CACHE_SUBDIR}/")
    assert url.endswith(".png")


def test_the_name_is_stable_across_calls():
    # Not stable means the cache never hits and every poll re-downloads.
    assert _local_url(VIN, "side") == _local_url(VIN, "side")
    assert _local_path(_hass(), VIN, "side") == _local_path(_hass(), VIN, "side")


def test_two_vehicles_do_not_share_one_file():
    assert _local_url(VIN, "side") != _local_url(OTHER, "side")


def test_the_tag_still_separates_the_images():
    assert _local_url(VIN, "side") != _local_url(VIN, "front")


def test_the_path_and_the_url_name_the_same_file():
    # They are built separately, so they can drift apart; a drift means the
    # entity publishes a URL for a file that is written somewhere else.
    path = _local_path(_hass(), VIN, "side")
    url = _local_url(VIN, "side")
    assert os.path.basename(path) == url.rsplit("/", 1)[-1]


# ── the half that heals an existing install ────────────────────────────────

def test_a_legacy_file_named_with_the_vin_is_removed(tmp_path):
    alt = tmp_path / f"{VIN}_side.png"
    alt.write_bytes(b"old")
    removed = _purge_legacy_vin_files(str(tmp_path), [VIN])
    assert removed == 1
    assert not alt.exists()


def test_every_tag_of_that_vehicle_goes(tmp_path):
    for tag in ("side", "front", "widget", "exterior_side"):
        (tmp_path / f"{VIN}_{tag}.png").write_bytes(b"old")
    removed = _purge_legacy_vin_files(str(tmp_path), [VIN])
    assert removed == 4
    assert not list(tmp_path.glob(f"{VIN}_*"))


def test_the_purge_touches_nothing_it_cannot_prove_is_vin_named(tmp_path):
    """It deletes by KNOWN VIN, not by guessing which names look like one."""
    keep = {
        "readme.txt": b"user file",
        "my_car.png": b"user file",
        # a hashed name, i.e. what this version writes
        os.path.basename(_local_path(_hass(), VIN, "side")): b"new",
        # another account's vehicle we were not told about
        "WVWZZZAUZFW000099_side.png": b"not ours to delete",
    }
    for name, data in keep.items():
        (tmp_path / name).write_bytes(data)
    (tmp_path / f"{VIN}_side.png").write_bytes(b"old")

    removed = _purge_legacy_vin_files(str(tmp_path), [VIN])

    assert removed == 1
    for name in keep:
        assert (tmp_path / name).exists(), name


def test_the_purge_survives_a_missing_directory():
    # Setup calls it before the first poll on a fresh install.
    assert _purge_legacy_vin_files("/nonexistent/vehicles", [VIN]) == 0


def test_the_purge_survives_an_empty_vin_list(tmp_path):
    (tmp_path / f"{VIN}_side.png").write_bytes(b"old")
    assert _purge_legacy_vin_files(str(tmp_path), []) == 0
    assert (tmp_path / f"{VIN}_side.png").exists()


def test_the_purge_ignores_a_blank_vin(tmp_path):
    """A blank VIN must not turn into a prefix that matches everything."""
    (tmp_path / "_side.png").write_bytes(b"x")
    (tmp_path / "anything.png").write_bytes(b"y")
    assert _purge_legacy_vin_files(str(tmp_path), ["", None]) == 0
    assert (tmp_path / "anything.png").exists()


def test_the_hash_is_the_one_the_repository_already_uses():
    """Same rule in both places, not two implementations of it."""
    from custom_components.vag_connect.cariad._util import hash_vin
    assert hash_vin(VIN) in _local_url(VIN, "side")
    assert hash_vin(VIN) != VIN
    assert len(hash_vin(VIN)) == 16


# ── the purge has to actually be CALLED ────────────────────────────────────
# Without this, a change that deletes the call from setup leaves every test
# above green: they exercise the function directly. A gate nobody passes
# through is not a gate.

async def test_setup_removes_the_legacy_file_for_a_known_vehicle(tmp_path):
    from custom_components.vag_connect import image as mod

    stale = tmp_path / f"{VIN}_side.png"
    stale.write_bytes(b"written by an earlier version")

    async def _run(fn, *args):
        return fn(*args)

    hass = MagicMock()
    hass.config.path = MagicMock(return_value=str(tmp_path))
    hass.async_add_executor_job = _run

    coordinator = MagicMock()
    coordinator.vehicles = {VIN: {}}
    coordinator.data = {VIN: {}}

    entry = MagicMock()
    entry.runtime_data = coordinator

    await mod.async_setup_entry(hass, entry, MagicMock())

    assert not stale.exists(), "setup did not purge the legacy VIN-named file"


async def test_setup_leaves_a_users_own_file_in_that_directory(tmp_path):
    from custom_components.vag_connect import image as mod

    mine = tmp_path / "my_own_picture.png"
    mine.write_bytes(b"not ours")

    async def _run(fn, *args):
        return fn(*args)

    hass = MagicMock()
    hass.config.path = MagicMock(return_value=str(tmp_path))
    hass.async_add_executor_job = _run

    coordinator = MagicMock()
    coordinator.vehicles = {VIN: {}}
    coordinator.data = {VIN: {}}

    entry = MagicMock()
    entry.runtime_data = coordinator

    await mod.async_setup_entry(hass, entry, MagicMock())

    assert mine.exists(), "setup deleted a file it was never told about"
