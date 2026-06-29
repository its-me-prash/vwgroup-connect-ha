# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Bentley brand-adapter — v2.2.0 scaffold, ACTIVATED v2.14.11.

The 2026-06-18 app-atlas resolved the former placeholders from
``uk.co.bentley.mybentley``: the production IDK client_id (``idkClientIDLive``
in the app's url-configuration.json) is byte-identical to Audi's primary, and
the redirect_uri is ``mybentleyapp:///``. Bentley is now wired into BRANDS +
factory + config-flow (login + read). Two-way stays live-test gated (the
qmauth gates in idk.py still exclude "bentley").

This test pins the ACTIVATED contract (was: scaffold-not-wired).
"""

from __future__ import annotations

import pytest

# Audi primary client_id — Bentley runs on the same IDK client/tenant.
_AUDI_PRIMARY = "09b6cbec-cd19-4589-82fd-363dfa8c24da@apps_vw-dilab_com"

_EXISTING_BRANDS = [
    "volkswagen", "audi", "skoda", "seat", "cupra", "volkswagen_na", "porsche",
]


class TestBentleyClientImports:
    def test_bentley_client_class_importable(self) -> None:
        from custom_components.vag_connect.cariad.api.bentley import (
            BentleyClient,
        )

        assert BentleyClient is not None

    def test_bentley_client_inherits_vw_eu(self) -> None:
        from custom_components.vag_connect.cariad.api.bentley import (
            BentleyClient,
        )
        from custom_components.vag_connect.cariad.api.vw_eu import VWEUClient

        assert issubclass(BentleyClient, VWEUClient)

    def test_brand_bentley_config_importable(self) -> None:
        from custom_components.vag_connect.cariad.models import BRAND_BENTLEY

        assert BRAND_BENTLEY is not None
        assert BRAND_BENTLEY.name == "bentley"


class TestBrandBentleyConfig:
    def test_api_base_is_cariad_bff(self) -> None:
        from custom_components.vag_connect.cariad.models import BRAND_BENTLEY

        assert BRAND_BENTLEY.api_base == "https://emea.bff.cariad.digital"

    def test_client_id_is_audi_primary(self) -> None:
        """Atlas: Bentley's idkClientIDLive == Audi primary (shared tenant)."""
        from custom_components.vag_connect.cariad.models import (
            BRAND_AUDI,
            BRAND_BENTLEY,
        )

        assert BRAND_BENTLEY.client_id == _AUDI_PRIMARY
        assert BRAND_BENTLEY.client_id == BRAND_AUDI.client_id
        assert "PLACEHOLDER" not in BRAND_BENTLEY.client_id

    def test_redirect_uri_is_atlas_value(self) -> None:
        from custom_components.vag_connect.cariad.models import BRAND_BENTLEY

        # Atlas (classes5.dex): mybentleyapp:/// — the old scaffold value
        # mybentley://oauth-callback was wrong and would fail redirect match.
        assert BRAND_BENTLEY.redirect_uri == "mybentleyapp:///"

    def test_user_agent_mentions_mybentley(self) -> None:
        from custom_components.vag_connect.cariad.models import BRAND_BENTLEY

        assert "Bentley" in BRAND_BENTLEY.user_agent

    def test_scope_includes_baseline_claims(self) -> None:
        from custom_components.vag_connect.cariad.models import BRAND_BENTLEY

        for required in ("openid", "profile", "vin"):
            assert required in BRAND_BENTLEY.scope


class TestBentleyWired:
    """v2.14.11 — Bentley is now wired (was: factory-rejected)."""

    def test_brands_registry_contains_bentley(self) -> None:
        from custom_components.vag_connect.cariad.models import BRANDS

        assert "bentley" in BRANDS

    def test_factory_resolves_bentley(self) -> None:
        from custom_components.vag_connect.cariad.api.bentley import (
            BentleyClient,
        )
        from custom_components.vag_connect.cariad.api.factory import (
            CariadClientFactory,
        )

        client = CariadClientFactory.create(
            brand="bentley",
            session=None,  # type: ignore[arg-type]
            email="x",
            password="x",
        )
        assert isinstance(client, BentleyClient)


class TestActivationDoesNotBreakExistingBrands:
    """New wiring must not perturb any existing brand client."""

    @pytest.mark.parametrize("brand", _EXISTING_BRANDS)
    def test_existing_brands_still_factory_resolvable(self, brand: str) -> None:
        from custom_components.vag_connect.cariad.api.factory import (
            CariadClientFactory,
        )

        client = CariadClientFactory.create(
            brand=brand,
            session=None,  # type: ignore[arg-type]
            email="x",
            password="x",
        )
        assert client is not None


class TestLamboStillNotWired:
    """Lamborghini, unlike Bentley, is NOT activatable — it uses an
    SDP-proxy MBB flow, not the IDK/Cariad-BFF path. It must stay
    factory-rejected and out of the BRANDS registry."""

    def test_lambo_not_in_brands(self) -> None:
        from custom_components.vag_connect.cariad.models import BRANDS

        assert "lambo" not in BRANDS

    def test_factory_rejects_lambo(self) -> None:
        from custom_components.vag_connect.cariad.api.factory import (
            CariadClientFactory,
        )

        with pytest.raises(ValueError, match="lambo"):
            CariadClientFactory.create(
                brand="lambo",
                session=None,  # type: ignore[arg-type]
                email="x",
                password="x",
            )
