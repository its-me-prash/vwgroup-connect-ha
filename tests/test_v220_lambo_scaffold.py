# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""v2.2.0 Phase 4 PR #15/20 — Lamborghini brand-adapter scaffold.

**BETA — TESTER VALIDATION PENDING.** This PR ships the LamboClient
class + BRAND_LAMBO config as scaffolding only. The class is NOT
wired into the factory / UI yet — activation requires a tester with
a Lamborghini Unica app install to confirm the OAuth client_id +
redirect_uri values currently set as PLACEHOLDERs.

Beta-gate semantics:
  - LamboClient imports cleanly (regression-shield for accidental
    breakage by future refactors)
  - BRAND_LAMBO config exists in models.py with documented
    PLACEHOLDER values
  - CariadClientFactory does NOT recognise "lambo" (must still
    raise ValueError)
  - Config-flow does NOT expose Lambo as a brand choice

Tester onboarding path:
  1. Install the Unica app on Android/iOS
  2. Capture OAuth flow via mitmproxy
  3. Extract client_id + redirect_uri + scope set
  4. Replace BRAND_LAMBO placeholders in models.py
  5. Add one line to factory.py: ``if lower == "lambo": return LamboClient(...)``
  6. Add "lambo" to config-flow brand list

"And that's why you always leave a note." — Marshall Eriksen,
on shipping defensive scaffolding for unknown firmware
"""

from __future__ import annotations

import pytest


class TestLamboClientImports:
    """Sanity: the scaffold compiles and the symbols are reachable."""

    def test_lambo_client_class_importable(self) -> None:
        from custom_components.vag_connect.cariad.api.lambo import (
            LamboClient,
        )

        assert LamboClient is not None

    def test_lambo_client_inherits_vw_eu(self) -> None:
        from custom_components.vag_connect.cariad.api.lambo import (
            LamboClient,
        )
        from custom_components.vag_connect.cariad.api.vw_eu import (
            VWEUClient,
        )

        assert issubclass(LamboClient, VWEUClient)

    def test_brand_lambo_config_importable(self) -> None:
        from custom_components.vag_connect.cariad.models import BRAND_LAMBO

        assert BRAND_LAMBO is not None
        assert BRAND_LAMBO.name == "lambo"


class TestBrandLamboConfig:
    """The BRAND_LAMBO config must have the right shape (Cariad-BFF
    host + scope set inherited from VW EU pattern) even with placeholder
    OAuth values."""

    def test_api_base_is_structurally_wrong_kept_marker(self) -> None:
        from custom_components.vag_connect.cariad.models import BRAND_LAMBO

        # v2.14.11 — atlas proved Unica is NOT on the Cariad-BFF; api_base is
        # left only so the scaffold imports. It is documented WRONG (real flow
        # is sdp.lamborghini.com/unicav2/mbbcoauth). Pinned to detect anyone
        # mistaking it for a working data base.
        assert BRAND_LAMBO.api_base == "https://emea.bff.cariad.digital"

    def test_client_id_marked_server_side_not_real(self) -> None:
        # v2.14.11 — atlas: Unica ships NO dilab client_id; the real MBB
        # client is held server-side on the SDP proxy. The config carries a
        # non-functional marker, never a usable client.
        from custom_components.vag_connect.cariad.models import BRAND_LAMBO

        assert "SERVER-SIDE" in BRAND_LAMBO.client_id

    def test_redirect_uri_uses_unica_scheme(self) -> None:
        from custom_components.vag_connect.cariad.models import BRAND_LAMBO

        assert BRAND_LAMBO.redirect_uri.startswith("unica://")

    def test_user_agent_mentions_unica(self) -> None:
        from custom_components.vag_connect.cariad.models import BRAND_LAMBO

        assert "Unica" in BRAND_LAMBO.user_agent

    def test_scope_is_mbb_sc2_fal(self) -> None:
        from custom_components.vag_connect.cariad.models import BRAND_LAMBO

        # v2.14.11 — atlas: Unica's MBB co-auth scope is ``sc2:fal``, NOT the
        # Cariad-BFF openid/profile/vin claim set.
        assert BRAND_LAMBO.scope == "sc2:fal"


class TestFactoryNotWiredYet:
    """Beta-gate enforcement: until tester confirms, the factory
    MUST reject "lambo" — preventing accidental activation."""

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

    def test_brands_registry_does_not_contain_lambo(self) -> None:
        # The exposed BRANDS dict (used by config-flow + user-facing
        # validation) must NOT include lambo until activation.
        from custom_components.vag_connect.cariad.models import BRANDS

        assert "lambo" not in BRANDS


class TestScaffoldDoesNotBreakExistingBrands:
    """Phantom-protection — the new BRAND_LAMBO export must not
    perturb any existing brand client."""

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

        # Confirms factory still creates a non-None client for each
        # existing brand even after the BRAND_LAMBO addition.
        client = CariadClientFactory.create(
            brand=brand,
            session=None,  # type: ignore[arg-type]
            email="x",
            password="x",
        )
        assert client is not None
