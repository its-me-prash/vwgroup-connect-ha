# Copyright 2026 Prash Balan (@its-me-prash) — Apache License 2.0
# SPDX-License-Identifier: Apache-2.0
"""v2.2.0 Phase 4 PR #16/20 — Bentley brand-adapter scaffold.

Sister-PR to PR #15 (Lamborghini Unica). Same pattern, same beta-gate
enforcement, same VWEUClient inheritance rationale.

Cross-luxury parity test ensures the two scaffolds stay shape-aligned:
both should inherit from VWEUClient, both should use the Cariad-BFF
host, both should keep PLACEHOLDER client_ids, both must remain
factory-rejected until tester validation.

"Two roads diverged in a wood, and I took the one beta-gated."
— Robert Frost, paraphrased for VAG-luxury onboarding
"""

from __future__ import annotations

import pytest


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
        from custom_components.vag_connect.cariad.api.vw_eu import (
            VWEUClient,
        )

        assert issubclass(BentleyClient, VWEUClient)

    def test_brand_bentley_config_importable(self) -> None:
        from custom_components.vag_connect.cariad.models import (
            BRAND_BENTLEY,
        )

        assert BRAND_BENTLEY is not None
        assert BRAND_BENTLEY.name == "bentley"


class TestBrandBentleyConfig:
    def test_api_base_is_cariad_bff(self) -> None:
        from custom_components.vag_connect.cariad.models import (
            BRAND_BENTLEY,
        )

        assert BRAND_BENTLEY.api_base == "https://emea.bff.cariad.digital"

    def test_client_id_is_placeholder(self) -> None:
        from custom_components.vag_connect.cariad.models import (
            BRAND_BENTLEY,
        )

        assert "PLACEHOLDER" in BRAND_BENTLEY.client_id

    def test_redirect_uri_uses_mybentley_scheme(self) -> None:
        from custom_components.vag_connect.cariad.models import (
            BRAND_BENTLEY,
        )

        assert BRAND_BENTLEY.redirect_uri.startswith("mybentley://")

    def test_user_agent_mentions_mybentley(self) -> None:
        from custom_components.vag_connect.cariad.models import (
            BRAND_BENTLEY,
        )

        assert "Bentley" in BRAND_BENTLEY.user_agent

    def test_scope_includes_baseline_claims(self) -> None:
        from custom_components.vag_connect.cariad.models import (
            BRAND_BENTLEY,
        )

        for required in ("openid", "profile", "vin"):
            assert required in BRAND_BENTLEY.scope


class TestFactoryNotWiredYet:
    """Beta-gate: factory MUST reject "bentley" until tester validates."""

    def test_factory_rejects_bentley(self) -> None:
        from custom_components.vag_connect.cariad.api.factory import (
            CariadClientFactory,
        )

        with pytest.raises(ValueError, match="bentley"):
            CariadClientFactory.create(
                brand="bentley",
                session=None,  # type: ignore[arg-type]
                email="x",
                password="x",
            )

    def test_brands_registry_does_not_contain_bentley(self) -> None:
        from custom_components.vag_connect.cariad.models import BRANDS

        assert "bentley" not in BRANDS


class TestScaffoldDoesNotBreakExistingBrands:
    """Phantom-protection — new BRAND_BENTLEY export must not perturb
    any existing brand client."""

    @pytest.mark.parametrize(
        "brand", ["volkswagen", "audi", "skoda", "seat", "cupra",
                  "volkswagen_na", "porsche"]
    )
    def test_existing_brands_still_factory_resolvable(
        self, brand: str
    ) -> None:
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


class TestLuxuryParityWithLambo:
    """The Bentley scaffold should be shape-aligned with the Lambo
    scaffold (PR #15) — both inherit from VWEUClient, both use
    Cariad-BFF, both stay PLACEHOLDER until tester validation. Any
    divergence in the scaffold pattern would indicate a contributor
    is treating them differently for no good reason."""

    def test_both_luxury_brands_inherit_vw_eu(self) -> None:
        from custom_components.vag_connect.cariad.api.bentley import (
            BentleyClient,
        )
        from custom_components.vag_connect.cariad.api.lambo import (
            LamboClient,
        )
        from custom_components.vag_connect.cariad.api.vw_eu import (
            VWEUClient,
        )

        assert issubclass(LamboClient, VWEUClient)
        assert issubclass(BentleyClient, VWEUClient)

    def test_both_luxury_brands_use_cariad_bff(self) -> None:
        from custom_components.vag_connect.cariad.models import (
            BRAND_BENTLEY,
            BRAND_LAMBO,
        )

        assert BRAND_LAMBO.api_base == BRAND_BENTLEY.api_base
        assert BRAND_LAMBO.api_base == "https://emea.bff.cariad.digital"

    def test_both_luxury_brands_kept_placeholder(self) -> None:
        from custom_components.vag_connect.cariad.models import (
            BRAND_BENTLEY,
            BRAND_LAMBO,
        )

        assert "PLACEHOLDER" in BRAND_LAMBO.client_id
        assert "PLACEHOLDER" in BRAND_BENTLEY.client_id

    def test_both_luxury_brands_factory_rejected(self) -> None:
        from custom_components.vag_connect.cariad.api.factory import (
            CariadClientFactory,
        )

        for brand in ("lambo", "bentley"):
            with pytest.raises(ValueError, match=brand):
                CariadClientFactory.create(
                    brand=brand,
                    session=None,  # type: ignore[arg-type]
                    email="x",
                    password="x",
                )
