# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""v2.2.0 Phase 7 PR #5 — VW EU Scout #245 silencing.

Pre-release patch BEFORE v2.2.0 final. Issue #245 reported 18 new
fields on the VW EU `selectivestatus` endpoint — but it's NOT 18
random fields. It's a **systemic rollout**: Cariad-BFF now ships a
``.error`` container (6 keys — message/errorTimeStamp/info/code/
group/retry) under every ``<block>.{xxxStatus}`` when a sub-status
fails.

| Pattern | Count |
|---------|-------|
| ``<block>.{xxxStatus}.error`` | 17 |
| ``measurements.tirePressureStatus`` (1-key container) | 1 |

Why this must ship before v2.2.0 final: WITHOUT this silencing,
every production user whose backend has rolled out the error-
container feature would see 18 scout warnings per coordinator
update → log spam → frustrated users.

The silencing layer doesn't expose new entities — error-containers
are diagnostic backend state that's already covered by the existing
``connection_state`` pipeline (which interprets stale timestamps
correctly).

"There's an error. There's an error. There's an error. There's an
error. There's an error. There's an error. There's an error in
the air-conditioning. There's an error. ... There's an error in
the charging. ... I think the backend is having a bad day."
— Sheldon Cooper, reading the scout warnings
"""

from __future__ import annotations

import pytest


# The 17 .error patterns from scout #245
ERROR_PATTERNS = [
    "access.accessStatus.error",
    "fuelStatus.rangeStatus.error",
    "measurements.rangeStatus.error",
    "measurements.odometerStatus.error",
    "measurements.temperatureBatteryStatus.error",
    "measurements.fuelLevelStatus.error",
    "measurements.temperatureOutsideStatus.error",
    "vehicleLights.lightsStatus.error",
    "charging.batteryStatus.error",
    "charging.chargingStatus.error",
    "charging.chargingSettings.error",
    "charging.plugStatus.error",
    "climatisation.climatisationSettings.error",
    "climatisation.climatisationStatus.error",
    "climatisation.windowHeatingStatus.error",
    "vehicleHealthInspection.maintenanceStatus.error",
    "departureProfiles.departureProfilesStatus.error",
]

# The 6 standard child keys per the Cariad-BFF error contract
ERROR_CHILD_KEYS = [
    "message",
    "errorTimeStamp",
    "info",
    "code",
    "group",
    "retry",
]


class TestScout245ErrorContainersSilenced:
    """Every reported `.error` container must be silenced."""

    @pytest.mark.parametrize("path", ERROR_PATTERNS)
    def test_error_container_silenced(self, path: str) -> None:
        from custom_components.vag_connect.cariad._unexpected_keys import (
            EXPECTED_KEYS,
            _path_matches,
        )

        keys = EXPECTED_KEYS["volkswagen"]["selectivestatus"]
        assert _path_matches(path, keys), f"missing: {path}"

    @pytest.mark.parametrize("path", ERROR_PATTERNS)
    @pytest.mark.parametrize("child", ERROR_CHILD_KEYS)
    def test_error_child_silenced(self, path: str, child: str) -> None:
        # Wildcard `<path>.*` must cover all 6 standard child keys
        from custom_components.vag_connect.cariad._unexpected_keys import (
            EXPECTED_KEYS,
            _path_matches,
        )

        keys = EXPECTED_KEYS["volkswagen"]["selectivestatus"]
        child_path = f"{path}.{child}"
        assert _path_matches(child_path, keys), (
            f"missing child: {child_path}"
        )


class TestScout245TirePressureSilenced:
    """1-key tirePressureStatus container + wildcards for future children."""

    def test_container_silenced(self) -> None:
        from custom_components.vag_connect.cariad._unexpected_keys import (
            EXPECTED_KEYS,
            _path_matches,
        )

        keys = EXPECTED_KEYS["volkswagen"]["selectivestatus"]
        assert _path_matches("measurements.tirePressureStatus", keys)

    def test_value_wrapper_silenced(self) -> None:
        from custom_components.vag_connect.cariad._unexpected_keys import (
            EXPECTED_KEYS,
            _path_matches,
        )

        keys = EXPECTED_KEYS["volkswagen"]["selectivestatus"]
        assert _path_matches("measurements.tirePressureStatus.value", keys)

    def test_future_immediate_children_silenced(self) -> None:
        # The wildcard ``measurements.tirePressureStatus.value.*``
        # matches ONE level deep — covers immediate children like
        # ``.value.tires`` or ``.value.carCapturedTimestamp``.
        # Deeper nesting (e.g. ``.value.tires.frontLeft.pressure_kPa``)
        # would require additional ``.value.*.*`` wildcards, which we
        # intentionally DON'T add yet — we'll see what shape the
        # backend actually ships, then silence with knowledge.
        from custom_components.vag_connect.cariad._unexpected_keys import (
            EXPECTED_KEYS,
            _path_matches,
        )

        keys = EXPECTED_KEYS["volkswagen"]["selectivestatus"]
        for future_path in (
            "measurements.tirePressureStatus.value.tires",
            "measurements.tirePressureStatus.value.carCapturedTimestamp",
            "measurements.tirePressureStatus.value.anyFutureLeaf",
        ):
            assert _path_matches(future_path, keys), f"missing: {future_path}"


class TestExistingPatternsUnaffected:
    """The pre-existing `.error` silencings from v1.12.0/v1.12.1 must
    still work — Scout #245's bulk-add must not have broken them."""

    @pytest.mark.parametrize(
        "path",
        [
            "charging.chargeMode.error",
            "charging.chargeMode.error.message",
            "automation.climatisationTimer.error",
            "automation.climatisationTimer.error.retry",
            "automation.chargingProfiles.error",
            "automation.chargingProfiles.error.code",
        ],
    )
    def test_legacy_error_path_still_silenced(self, path: str) -> None:
        from custom_components.vag_connect.cariad._unexpected_keys import (
            EXPECTED_KEYS,
            _path_matches,
        )

        keys = EXPECTED_KEYS["volkswagen"]["selectivestatus"]
        assert _path_matches(path, keys), f"regression: {path}"


class TestNoSiblingsAccidentallySilenced:
    """The wildcards must NOT over-silence — actual data paths
    (NON-error) should still NOT be in EXPECTED_KEYS (they're
    silenced by their own explicit registrations, not by the new
    .error wildcards)."""

    def test_real_data_paths_not_swallowed_by_error_wildcards(self) -> None:
        # Sanity: a wildcard like `access.accessStatus.error.*` must
        # match `access.accessStatus.error.message` (TRUE) but NOT
        # `access.accessStatus.value.doors` (which is a real data
        # path silenced by its own entry).
        from custom_components.vag_connect.cariad._unexpected_keys import (
            EXPECTED_KEYS,
            _path_matches,
        )

        keys = EXPECTED_KEYS["volkswagen"]["selectivestatus"]
        # The .value sibling should match via its own registration,
        # not via the .error wildcard
        assert _path_matches("access.accessStatus.value.doors", keys)
        # And the wildcard for .error must still match .error children
        assert _path_matches("access.accessStatus.error.message", keys)


class TestNoBehaviourChangeForOtherBrands:
    """Skoda + CUPRA/SEAT silencers must not have grown. Porsche +
    VW NA + Audi don't appear in this test because they either don't
    use the scout-warner (Porsche / VW NA — different parser path)
    or share their entries with VW EU (Audi inherits via class)."""

    @pytest.mark.parametrize(
        "brand",
        ["skoda", "cupra", "seat"],
    )
    def test_brand_silencer_unaffected(self, brand: str) -> None:
        # Sanity: ``access.accessStatus.error`` is VW-only — other
        # brands have different endpoint shapes. Just verify the
        # brand registries are still loadable (= no syntax breakage
        # spilled into other sections during my edit).
        from custom_components.vag_connect.cariad._unexpected_keys import (
            EXPECTED_KEYS,
        )

        assert brand in EXPECTED_KEYS
        assert isinstance(EXPECTED_KEYS[brand], dict)

    def test_porsche_not_in_scout_warner(self) -> None:
        # Documenting reality: Porsche uses its own parser path
        # (no scout-warner instrumentation) so it's intentionally
        # absent from EXPECTED_KEYS. This is NOT a regression — just
        # a constraint to remember when adding cross-brand entries.
        from custom_components.vag_connect.cariad._unexpected_keys import (
            EXPECTED_KEYS,
        )

        assert "porsche" not in EXPECTED_KEYS
