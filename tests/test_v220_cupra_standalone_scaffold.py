# Copyright 2026 Prash Balan (@its-me-prash) — Apache License 2.0
# SPDX-License-Identifier: Apache-2.0
"""v2.2.0 Phase 4 PR #17/20 — CUPRA-standalone brand-adapter scaffold.

**Phase 4 closer.** Third luxury/standalone scaffold alongside Lambo
(PR #15) and Bentley (PR #16), but with a different inheritance story:

- Lambo + Bentley → ``VWEUClient`` (Cariad-BFF backend)
- CUPRA-standalone → ``SeatCupraClient`` (OLA backend, same parser)

Reserves brand-id ``cupra_standalone`` for the upcoming
``cupra-api.vwgroup.io`` cut-over. Per pycupra commit 0f3b1c7 +
multiple 2026-Q1/Q2 community reports, CUPRA Connect is migrating to
a brand-isolated backend (expected fully cut over by 2026-H2).

Existing CUPRA users see ZERO behaviour change — the legacy
``BRAND_CUPRA`` path (shared SEAT/CUPRA OLA) stays unchanged. The
standalone scaffold only activates when a tester explicitly opts in
after their account flips.

"In our profession, precision matters. Especially when reserving
brand-IDs for backend cut-overs that haven't fully cut over yet."
— Leonard Hofstadter
"""

from __future__ import annotations

import pytest


class TestCupraStandaloneImports:
    def test_class_importable(self) -> None:
        from custom_components.vag_connect.cariad.api.cupra_standalone import (
            CupraStandaloneClient,
        )

        assert CupraStandaloneClient is not None

    def test_inherits_seat_cupra_client(self) -> None:
        # Distinct from PR #15/#16 (which inherit VWEUClient) —
        # CUPRA-standalone uses the OLA-flavoured parser via the
        # existing SeatCupraClient.
        from custom_components.vag_connect.cariad.api.cupra_standalone import (
            CupraStandaloneClient,
        )
        from custom_components.vag_connect.cariad.api.seat_cupra import (
            SeatCupraClient,
        )

        assert issubclass(CupraStandaloneClient, SeatCupraClient)

    def test_brand_config_importable(self) -> None:
        from custom_components.vag_connect.cariad.models import (
            BRAND_CUPRA_STANDALONE,
        )

        assert BRAND_CUPRA_STANDALONE is not None
        assert BRAND_CUPRA_STANDALONE.name == "cupra_standalone"


class TestBrandCupraStandaloneConfig:
    def test_api_base_is_placeholder(self) -> None:
        # Critical — the cut-over host hasn't shipped publicly yet.
        # If someone accidentally puts a real-looking host here, that
        # implies the tester-validation step was skipped.
        from custom_components.vag_connect.cariad.models import (
            BRAND_CUPRA_STANDALONE,
        )

        assert "PLACEHOLDER" in BRAND_CUPRA_STANDALONE.api_base

    def test_oauth_client_id_matches_legacy_cupra(self) -> None:
        # The IDK login flow is unchanged — same OAuth client. Only
        # the post-auth API base differs.
        from custom_components.vag_connect.cariad.models import (
            BRAND_CUPRA,
            BRAND_CUPRA_STANDALONE,
        )

        assert (
            BRAND_CUPRA_STANDALONE.client_id == BRAND_CUPRA.client_id
        )

    def test_oauth_redirect_matches_legacy_cupra(self) -> None:
        from custom_components.vag_connect.cariad.models import (
            BRAND_CUPRA,
            BRAND_CUPRA_STANDALONE,
        )

        assert (
            BRAND_CUPRA_STANDALONE.redirect_uri == BRAND_CUPRA.redirect_uri
        )

    def test_client_secret_matches_legacy_cupra(self) -> None:
        # Per pycupra commit 0f3b1c7 — same client_secret on both
        # backends because the OAuth side hasn't rotated.
        from custom_components.vag_connect.cariad.models import (
            BRAND_CUPRA,
            BRAND_CUPRA_STANDALONE,
        )

        assert (
            BRAND_CUPRA_STANDALONE.client_secret == BRAND_CUPRA.client_secret
        )


class TestFactoryNotWiredYet:
    """Beta-gate: factory MUST reject the new brand-id."""

    def test_factory_rejects_cupra_standalone(self) -> None:
        from custom_components.vag_connect.cariad.api.factory import (
            CariadClientFactory,
        )

        with pytest.raises(ValueError, match="cupra_standalone"):
            CariadClientFactory.create(
                brand="cupra_standalone",
                session=None,  # type: ignore[arg-type]
                email="x",
                password="x",
            )

    def test_brands_registry_excludes_cupra_standalone(self) -> None:
        from custom_components.vag_connect.cariad.models import BRANDS

        assert "cupra_standalone" not in BRANDS


class TestLegacyCupraUnaffected:
    """Phantom-protection — existing CUPRA users MUST see zero
    behaviour change. The shared SEAT/CUPRA OLA path stays the
    canonical CUPRA backend until tester validates the cut-over."""

    def test_legacy_cupra_still_in_brands_registry(self) -> None:
        from custom_components.vag_connect.cariad.models import BRANDS

        assert "cupra" in BRANDS

    def test_legacy_cupra_factory_resolvable(self) -> None:
        from custom_components.vag_connect.cariad.api.factory import (
            CariadClientFactory,
        )

        client = CariadClientFactory.create(
            brand="cupra",
            session=None,  # type: ignore[arg-type]
            email="x",
            password="x",
        )
        assert client is not None

    def test_legacy_cupra_still_uses_ola_host(self) -> None:
        # Sanity: the existing CUPRA path hasn't been silently
        # repointed at the placeholder host.
        from custom_components.vag_connect.cariad.models import BRAND_CUPRA

        assert "ola.prod.code.seat.cloud.vwgroup.com" in BRAND_CUPRA.api_base


class TestThreeWayLuxuryParity:
    """Phase 4 = COMPLETE — all 3 scaffolds (Lambo + Bentley +
    CUPRA-standalone) must remain beta-gated. Any of them slipping
    past the gate without tester validation breaks this test."""

    def test_all_three_scaffolds_factory_rejected(self) -> None:
        from custom_components.vag_connect.cariad.api.factory import (
            CariadClientFactory,
        )

        for brand in ("lambo", "bentley", "cupra_standalone"):
            with pytest.raises(ValueError, match=brand):
                CariadClientFactory.create(
                    brand=brand,
                    session=None,  # type: ignore[arg-type]
                    email="x",
                    password="x",
                )

    def test_all_three_scaffolds_excluded_from_brands_registry(self) -> None:
        from custom_components.vag_connect.cariad.models import BRANDS

        for brand_id in ("lambo", "bentley", "cupra_standalone"):
            assert brand_id not in BRANDS, (
                f"beta-gate broken: '{brand_id}' leaked into BRANDS "
                f"registry without tester validation"
            )

    def test_all_three_scaffold_configs_importable(self) -> None:
        # Sanity: testers MUST be able to import the configs directly
        # for debug-script work even though factory rejects them.
        from custom_components.vag_connect.cariad.models import (
            BRAND_BENTLEY,
            BRAND_CUPRA_STANDALONE,
            BRAND_LAMBO,
        )

        assert BRAND_LAMBO.name == "lambo"
        assert BRAND_BENTLEY.name == "bentley"
        assert BRAND_CUPRA_STANDALONE.name == "cupra_standalone"
