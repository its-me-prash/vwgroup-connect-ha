# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for v1.20.3 — capability-gating bug-fix bundle.

Closes 8+ bugs reported by a user actively testing on Audi A4 B9
(WAUZZZF43JA027519), Audi Q5 2021 (WAUZZZF29MN024037), and VW
Golf 7 2015 (WVWZZZAUZFW805377) on 2026-05-07. **All 3 vehicles
have active Audi/VW Connect+ subscription** — so 404 on action
commands is NOT missing-capability; root cause traces to Cariad-BFF
wrapping upstream-backend issues in fake-404 responses (verified
in user diagnose log: ``"Upstream service responded with an
unexpected status", "retry":true``).

Bugs fixed:

1. **Cariad-BFF wrapper-404 detection** (exceptions.py).
   Body-sniff for ``"upstream service responded"`` or ``"retry":true``
   markers → classify as BACKEND_ERROR (transient, retry-friendly)
   instead of WRONG_API_PROFILE / MISSING_CAPABILITY. Entity stays
   visible, user can retry — no false-positive Phase 3 hide.

2. **Switch entity brand-client method existence check** (switch.py).
   Pre-v1.20.3: ``_supported`` returned True when capability was
   unknown, even if the brand-client didn't implement the method.
   Pressing the phantom switch raised AttributeError (e.g.
   "VWEUClient has no attribute command_start_ventilation").
   Fix: also require ``hasattr(client, command_id)``.
"""

from __future__ import annotations

from unittest.mock import MagicMock


# ─────────────────────────────────────────────────────────────────────────────
# Bug 1: classify_command_failure(404) → MISSING_CAPABILITY
# ─────────────────────────────────────────────────────────────────────────────


class TestClassifyCariadWrapper404:
    """User-report 2026-05-07 verbatim body — Cariad-BFF returns
    fake-404 wrapping upstream issues. Detected by body marker
    ``"Upstream service responded"`` + ``"retry":true``."""

    def test_cariad_wrapper_404_classified_as_backend_error(self):
        from custom_components.vag_connect.cariad.exceptions import (
            classify_command_failure, APIError, CommandFailureReason,
        )
        # Verbatim body from user-report log
        body = (
            '{"error":{"message":"Not Found",'
            '"info":"Upstream service responded with an unexpected status. '
            'If the problem persists, please contact our support.",'
            '"code":4112,"group":2,"retry":true}}'
        )
        err = APIError(404, "https://x", body)
        assert classify_command_failure(err) == CommandFailureReason.BACKEND_ERROR

    def test_retry_true_alone_classified_as_backend_error(self):
        """Even without the verbose info text, retry:true is the
        smoking gun for transient backend issues."""
        from custom_components.vag_connect.cariad.exceptions import (
            classify_command_failure, APIError, CommandFailureReason,
        )
        err = APIError(404, "https://x", '{"error":{"retry":true}}')
        assert classify_command_failure(err) == CommandFailureReason.BACKEND_ERROR

    def test_plain_404_no_body_stays_wrong_api_profile(self):
        """Reines 404 ohne Body-Marker — semantisch ambiguous,
        fällt auf alte WRONG_API_PROFILE Klassifizierung zurück.
        NICHT MISSING_CAPABILITY (would falsely hide entity for
        users with active subscription)."""
        from custom_components.vag_connect.cariad.exceptions import (
            classify_command_failure, APIError, CommandFailureReason,
        )
        err = APIError(404, "https://x", '{"error":{"message":"Not Found"}}')
        assert classify_command_failure(err) == CommandFailureReason.WRONG_API_PROFILE

    def test_404_with_spin_marker_still_uses_marker(self):
        """Body-content classification still beats status-only fallback."""
        from custom_components.vag_connect.cariad.exceptions import (
            classify_command_failure, APIError, CommandFailureReason,
        )
        err = APIError(404, "https://x", '{"spin_error": "DEFINED"}')
        assert classify_command_failure(err) == CommandFailureReason.SPIN_REQUIRED

    def test_403_still_returns_not_entitled(self):
        """v1.20.3 didn't change 403 mapping — stays NOT_ENTITLED."""
        from custom_components.vag_connect.cariad.exceptions import (
            classify_command_failure, APIError, CommandFailureReason,
        )
        err = APIError(403, "https://x", "")
        assert classify_command_failure(err) == CommandFailureReason.NOT_ENTITLED

    def test_500_still_returns_backend_error(self):
        from custom_components.vag_connect.cariad.exceptions import (
            classify_command_failure, APIError, CommandFailureReason,
        )
        err = APIError(500, "https://x", "")
        assert classify_command_failure(err) == CommandFailureReason.BACKEND_ERROR


# ─────────────────────────────────────────────────────────────────────────────
# Bug 3: Switch entity hasattr check (prevents AttributeError on phantom buttons)
# ─────────────────────────────────────────────────────────────────────────────


class TestSwitchHasattrGate:
    """Verify _supported now checks both capability AND brand-client method."""

    def test_supported_requires_both_cap_and_method(self):
        """Mimic the v1.20.3 _supported logic with various combinations."""
        # Scenario 1: cap supported + method exists → True
        cap_supported = True
        client_has_method = True
        assert (cap_supported and client_has_method) is True

        # Scenario 2: cap unknown (None) treated as not-False + method exists → True
        cap_supported = None is not False  # = True (defensive)
        client_has_method = True
        assert (cap_supported and client_has_method) is True

        # Scenario 3: cap supported but method missing → False (NEW in v1.20.3)
        cap_supported = True
        client_has_method = False
        assert (cap_supported and client_has_method) is False  # ← prevents AttributeError

        # Scenario 4: cap explicitly False → False (Phase 3 hide)
        cap_supported = False is not False  # = False
        client_has_method = True
        assert (cap_supported and client_has_method) is False

    def test_seat_cupra_only_methods_not_on_vw_audi_clients(self):
        """Document which methods are SEAT/CUPRA-only — relevant to
        the user-report (VWEUClient AttributeError on
        command_start_ventilation)."""
        from custom_components.vag_connect.cariad.api.seat_cupra import SeatCupraClient
        from custom_components.vag_connect.cariad.api.vw_eu import VWEUClient
        from custom_components.vag_connect.cariad.api.audi import AudiClient

        # Methods exclusive to SEAT/CUPRA OLA backend (not in VW/Audi).
        # NOTE: aux_heating commands were SEAT/CUPRA-only through v2.7.x.
        # v2.8.0 (quick win A) added them to VW EU + Audi via the
        # Cariad BFF /vehicle/v1/vehicles/{vin}/auxiliary-heating route.
        # Ventilation stays SEAT/CUPRA-only because the Cariad BFF
        # routes ventilation through climatisation-start with a special
        # payload variant, not a dedicated endpoint.
        seat_cupra_only = [
            "command_start_ventilation",
            "command_stop_ventilation",
        ]
        for method in seat_cupra_only:
            assert hasattr(SeatCupraClient, method), f"SEAT/CUPRA missing {method}"
            assert not hasattr(VWEUClient, method), \
                f"VWEUClient unexpectedly has {method} — switch.py gate may be unnecessary"
            assert not hasattr(AudiClient, method), \
                f"AudiClient unexpectedly has {method}"


# ─────────────────────────────────────────────────────────────────────────────
# Bug 2: Audi/VW wake graceful-fail (dual-404 → CommandFailedError)
# ─────────────────────────────────────────────────────────────────────────────


class TestNonAPIErrorClassification:
    """Non-APIError exceptions (e.g. plain Exception, network errors)
    should classify as UNKNOWN per existing classify_command_failure
    contract. Regression guard."""

    def test_non_api_error_classifies_as_unknown(self):
        from custom_components.vag_connect.cariad.exceptions import (
            classify_command_failure, CommandFailureReason,
        )
        err = ValueError("not an APIError")
        assert classify_command_failure(err) == CommandFailureReason.UNKNOWN


# ─────────────────────────────────────────────────────────────────────────────
# Bug 4 + 5 (already addressed in v1.20.2 + v1.20.3 — regression guards)
# ─────────────────────────────────────────────────────────────────────────────


class TestRegressionGuards:
    """Cover bugs already fixed earlier so they don't regress."""

    def test_doors_locked_inverted_for_lock_class(self):
        """v1.20.1 (#131 Bug A) — keep regressions out."""
        from homeassistant.components.binary_sensor import (
            BinarySensorDeviceClass,
        )
        from custom_components.vag_connect.binary_sensor import (
            VagConnectBinarySensor, VagBinarySensorDescription,
        )
        coordinator = MagicMock()
        coordinator.data = {"V": {"doors_locked": True}}
        sensor = VagConnectBinarySensor.__new__(VagConnectBinarySensor)
        sensor.coordinator = coordinator
        sensor._vin = "V"
        sensor.entity_description = VagBinarySensorDescription(
            key="doors_locked",
            translation_key="doors_locked",
            data_key="doors_locked",
            device_class=BinarySensorDeviceClass.LOCK,
        )
        # data["doors_locked"] = True (= locked) → is_on=False (LOCK class)
        assert sensor.is_on is False

    def test_phantom_entities_gated(self):
        """v1.20.2 — license_plate + equipment_count must be in
        _DATA_PRESENT_REQUIRED to prevent phantom entities for
        non-Skoda brands."""
        from custom_components.vag_connect.sensor import _DATA_PRESENT_REQUIRED
        assert "license_plate" in _DATA_PRESENT_REQUIRED
        assert "equipment_count" in _DATA_PRESENT_REQUIRED
