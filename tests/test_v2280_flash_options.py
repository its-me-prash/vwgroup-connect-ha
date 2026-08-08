# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#1009 — the vehicle-signal service exposes duration and horn.

The manufacturer app's signal screen offers both, and the wire contract already
carried them: the CARIAD ``HonkAndFlashParameters$Mode`` enum has exactly
HONK_AND_FLASH and FLASH_ONLY, and ``duration_s`` is plain seconds (both read
out of the decompiled app when the endpoint was first grounded). Skoda's own
DTO carries the same two-value mode but no duration.

Nothing is invented here: a brand whose values are not grounded accepts the
arguments and ignores them, exactly as it already does for latitude/longitude.
Omitting both reproduces the previous fixed 10-second lights-only signal.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest

from custom_components.vag_connect.cariad.api.skoda import SkodaClient
from custom_components.vag_connect.cariad.api.vw_eu import VWEUClient

# Škoda honk-and-flash requires vehiclePosition (8.15.0) — pass real coords.
_LL = {"latitude": 48.1, "longitude": 11.5}


def _vw() -> tuple[VWEUClient, AsyncMock]:
    c = VWEUClient.__new__(VWEUClient)
    c._mbb_command_target = lambda: None  # type: ignore[method-assign]
    post = AsyncMock()
    c._post_command = post  # type: ignore[method-assign]
    return c, post


class TestVolkswagenAudi:
    def test_default_is_the_previous_behaviour(self) -> None:
        c, post = _vw()
        asyncio.run(c.command_flash("VIN"))
        assert post.await_args.kwargs["json"] == {
            "mode": "FLASH_ONLY", "duration_s": 10
        }

    def test_horn_uses_the_grounded_enum_value(self) -> None:
        c, post = _vw()
        asyncio.run(c.command_flash("VIN", honk=True))
        assert post.await_args.kwargs["json"]["mode"] == "HONK_AND_FLASH"

    def test_duration_is_sent_as_seconds(self) -> None:
        c, post = _vw()
        asyncio.run(c.command_flash("VIN", duration_s=30))
        assert post.await_args.kwargs["json"]["duration_s"] == 30

    def test_both_together(self) -> None:
        c, post = _vw()
        asyncio.run(c.command_flash("VIN", duration_s=20, honk=True))
        assert post.await_args.kwargs["json"] == {
            "mode": "HONK_AND_FLASH", "duration_s": 20
        }


class TestSkoda:
    def _client(self) -> tuple[SkodaClient, AsyncMock]:
        c = SkodaClient.__new__(SkodaClient)
        post = AsyncMock()
        c._post = post  # type: ignore[method-assign]
        return c, post

    def test_flash_only_keeps_skodas_own_enum_value(self) -> None:
        """Skoda's value is FLASH, not the VW-EU FLASH_ONLY (that mismatch was
        a real bug once). vehiclePosition is required (8.15.0)."""
        c, post = self._client()
        asyncio.run(c.command_flash("VIN", **_LL))
        body = post.await_args.kwargs["json"]
        assert body["mode"] == "FLASH"
        assert body["vehiclePosition"] == _LL

    def test_horn_is_grounded_here_too(self) -> None:
        c, post = self._client()
        asyncio.run(c.command_flash("VIN", honk=True, **_LL))
        assert post.await_args.kwargs["json"]["mode"] == "HONK_AND_FLASH"

    def test_duration_is_ignored_not_invented(self) -> None:
        """Skoda's DTO has no duration field, so we must not add one."""
        c, post = self._client()
        asyncio.run(c.command_flash("VIN", duration_s=30, **_LL))
        assert "duration_s" not in post.await_args.kwargs["json"]

    def test_flash_without_position_raises_not_400_body(self) -> None:
        """8.15.0 makes vehiclePosition required — with no cached GPS we fail
        with an actionable error instead of emitting the doomed position-less
        body (matches the VW-EU sibling)."""
        c, post = self._client()
        with pytest.raises(ValueError, match="GPS"):
            asyncio.run(c.command_flash("VIN"))
        post.assert_not_awaited()


class TestWiring:
    def test_every_brand_accepts_the_arguments(self) -> None:
        """Signature compatibility: the coordinator passes both to whichever
        client the entry has, so none may raise TypeError."""
        import inspect

        from custom_components.vag_connect.cariad.api import (
            base, porsche, seat_cupra, skoda, vw_eu, vw_na,
        )

        for mod in (base, porsche, seat_cupra, skoda, vw_eu, vw_na):
            for _name, obj in inspect.getmembers(mod, inspect.isclass):
                fn = obj.__dict__.get("command_flash")
                if fn is None:
                    continue
                params = inspect.signature(fn).parameters
                assert "duration_s" in params, f"{mod.__name__} missing duration_s"
                assert "honk" in params, f"{mod.__name__} missing honk"

    def test_service_is_registered_with_the_new_schema(self) -> None:
        import pathlib

        src = (
            pathlib.Path(__file__).resolve().parents[1]
            / "custom_components/vag_connect/__init__.py"
        ).read_text(encoding="utf-8")
        assert "SERVICE_FLASH_SCHEMA" in src
        assert '"flash_lights",                   _handle_flash,               SERVICE_FLASH_SCHEMA' in src

    def test_service_is_documented(self) -> None:
        import pathlib

        import yaml

        doc = yaml.safe_load(
            (
                pathlib.Path(__file__).resolve().parents[1]
                / "custom_components/vag_connect/services.yaml"
            ).read_text(encoding="utf-8")
        )
        fields = doc["flash_lights"]["fields"]
        assert "duration_seconds" in fields
        assert "signal_type" in fields
