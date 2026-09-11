# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""_validate_credentials' Porsche-captcha branch (b19, #1337, CJNE-comparison #12).

Exercises the isinstance(client, PorscheClient) forwarding logic directly
(without HA's full config-flow test harness) — the captcha resume kwargs must
reach PorscheClient.authenticate() only when a real PorscheClient instance is
returned by the factory, and never for any other brand's client.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from custom_components.vag_connect.cariad.api.porsche import PorscheClient
from custom_components.vag_connect.cariad.exceptions import (
    AuthenticationError,
    PorscheCaptchaRequiredError,
    PorscheLoginWallError,
)
from custom_components.vag_connect.config_flow import _map_error, _validate_credentials


class _FakeNonPorscheClient:
    def __init__(self) -> None:
        self.authenticate = AsyncMock()


@pytest.mark.asyncio
async def test_captcha_kwargs_forwarded_for_porsche_instance():
    client = PorscheClient.__new__(PorscheClient)
    client.authenticate = AsyncMock()  # type: ignore[method-assign]
    with patch(
        "custom_components.vag_connect.cariad.CariadClientFactory.create",
        return_value=client,
    ):
        await _validate_credentials(
            None, "porsche", "a@b.com", "pw",
            captcha_code="ABCD", captcha_state="st", captcha_verifier="ver",
        )
    client.authenticate.assert_awaited_once_with(
        mfa_code=None, captcha_code="ABCD",
        resume_state="st", resume_verifier="ver", captcha_resume=None,
    )


@pytest.mark.asyncio
async def test_captcha_kwargs_never_forwarded_to_other_brands():
    """Even if a caller mistakenly passed captcha kwargs for a non-Porsche
    brand, the isinstance guard must keep them off that client's call —
    other brands' authenticate() signatures would TypeError on them."""
    client = _FakeNonPorscheClient()
    with patch(
        "custom_components.vag_connect.cariad.CariadClientFactory.create",
        return_value=client,
    ):
        await _validate_credentials(
            None, "volkswagen", "a@b.com", "pw",
            captcha_code="ABCD", captcha_state="st", captcha_verifier="ver",
        )
    client.authenticate.assert_awaited_once_with(mfa_code=None)


@pytest.mark.asyncio
async def test_captcha_required_error_propagates_uncaught():
    """PorscheCaptchaRequiredError must reach the config-flow step as itself
    — not get collapsed into a generic ValueError like other auth errors."""
    client = PorscheClient.__new__(PorscheClient)
    client.authenticate = AsyncMock(  # type: ignore[method-assign]
        side_effect=PorscheCaptchaRequiredError("data:image/svg+xml;base64,X", "st", "ver")
    )
    with patch(
        "custom_components.vag_connect.cariad.CariadClientFactory.create",
        return_value=client,
    ), pytest.raises(PorscheCaptchaRequiredError) as excinfo:
        await _validate_credentials(None, "porsche", "a@b.com", "pw")
    assert excinfo.value.captcha_image == "data:image/svg+xml;base64,X"


class TestLoginWallMapping:
    """b23 (#1337) — a captcha/consent wall PAST the password step must surface
    as its own error, not the "email/password incorrect" that both v4.7.2
    reporters saw despite verified-good credentials."""

    @pytest.mark.asyncio
    async def test_login_wall_maps_to_distinct_error(self) -> None:
        client = PorscheClient.__new__(PorscheClient)
        client.authenticate = AsyncMock(side_effect=PorscheLoginWallError())  # type: ignore[method-assign]
        with patch(
            "custom_components.vag_connect.cariad.CariadClientFactory.create",
            return_value=client,
        ), pytest.raises(ValueError) as excinfo:
            await _validate_credentials(None, "porsche", "a@b.com", "pw")
        # v4.7.8 — the key now carries a ":<screen>|<marker>" suffix for the
        # one-click report; the KEY is what matters here.
        assert str(excinfo.value).startswith("porsche_login_wall")
        assert _map_error(str(excinfo.value)) == "porsche_login_wall"
        # The whole point of the fix: it must NOT be the credentials error.
        assert not str(excinfo.value).startswith("invalid_credentials")

    @pytest.mark.asyncio
    async def test_real_wrong_credentials_still_map_to_invalid(self) -> None:
        """Regression: an actual 401/400 rejection (raised as a plain
        AuthenticationError) must still say 'email/password incorrect'."""
        client = PorscheClient.__new__(PorscheClient)
        client.authenticate = AsyncMock(  # type: ignore[method-assign]
            side_effect=AuthenticationError("Porsche auth failed — wrong credentials")
        )
        with patch(
            "custom_components.vag_connect.cariad.CariadClientFactory.create",
            return_value=client,
        ), pytest.raises(ValueError) as excinfo:
            await _validate_credentials(None, "porsche", "a@b.com", "pw")
        assert str(excinfo.value) == "invalid_credentials"

    def test_map_error_recognises_login_wall(self) -> None:
        assert _map_error("porsche_login_wall") == "porsche_login_wall"
        assert _map_error("invalid_credentials") == "invalid_credentials"
        assert _map_error("something_unmapped") == "cannot_connect"
