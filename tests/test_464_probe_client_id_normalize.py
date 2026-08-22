# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#464 — the SEAT/CUPRA probe tolerates the common client-id paste mistakes.

A tester dropped the whole ``VAGC_SEATCUPRA_CLIENT=<id>`` line into the local
file instead of the bare id, so the script sent that entire string as the client
id and VW answered ``400 invalid_request: The legal entity is missing or invalid``
(reproduced live). ``_normalize_client_id`` now strips a ``KEY=`` prefix and
wrapping quotes/whitespace so the same slip can't trip anyone else up.

Uses a synthetic client id — the normalisation is value-agnostic.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_probe():
    p = Path(__file__).resolve().parents[1] / "scripts" / "seat_cupra_mbb_probe.py"
    spec = importlib.util.spec_from_file_location("seat_cupra_mbb_probe", p)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_CID = "00000000-0000-4000-8000-000000000000@apps_vw-dilab_com"


class TestNormalizeClientId:
    def setup_method(self) -> None:
        self.n = _load_probe()._normalize_client_id

    def test_clean_id_unchanged(self) -> None:
        assert self.n(_CID) == _CID

    def test_strips_env_key_prefix(self) -> None:
        # the exact #464 mistake: whole "VAGC_SEATCUPRA_CLIENT=<id>" line pasted
        assert self.n(f"VAGC_SEATCUPRA_CLIENT={_CID}") == _CID

    def test_strips_surrounding_quotes(self) -> None:
        assert self.n(f'"{_CID}"') == _CID

    def test_strips_prefix_and_quotes_together(self) -> None:
        assert self.n(f'VAGC_SEATCUPRA_CLIENT="{_CID}"') == _CID

    def test_strips_whitespace_and_newlines(self) -> None:
        assert self.n(f"  {_CID}\n\t") == _CID
