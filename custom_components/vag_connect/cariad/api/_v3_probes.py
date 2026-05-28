# Copyright 2026 Prash Balan (@its-me-prash) — Apache License 2.0
"""v2.5.2 — Silent Scout-Channel Expansion: probe endpoint inventory.

The scout pipeline (``detect_unexpected``) emits per-field reports for any
JSON path it sees that is not declared in ``EXPECTED_KEYS``. Pre-v2.5.2 the
scout only watched responses from endpoints we *already call* in production
— so its discovery surface was capped by our production call-set.

v2.5.2 widens the scout surface by issuing low-frequency (1×/hour by
default) GETs against additional brand endpoints already documented in the
public open-source ecosystem but not currently called by us. Responses are
fed into the same ``detect_unexpected`` pipeline, so new VAG-side fields
surface in our scout reports without exposing any new HA entities. No
behaviour change for end users; pure information-harvest for prioritising
v3.0 entity exposure.

**Endpoint sources** (all public open-source, MIT/Apache):
- ``WulfgarW/pycupra`` (MIT) — OLA v1/v2 paths for SEAT + CUPRA
- ``skodaconnect/myskoda`` (Apache-2.0) — mysmob extended endpoints
- ``tillsteinbach/CarConnectivity-connector-volkswagen`` (Apache-2.0) — CARIAD-BFF capability probes
- ``robinostlund/volkswagencarnet`` (MIT) — `oilLevel`, `tyrePressure`, `parkingTime` field paths
- ``arjenvrh/audi_connect_ha`` (MIT) — Audi-specific MBB measurements
- ``evcc-io/evcc`` (MIT) — multi-brand auth + discovery hints
- audit cross-reference: ``docs/research/audit/v3.0-competitor-field-audit``

**Operational guardrails**:
- One probe pass per VIN per hour (counter on ``CariadBaseClient``)
- Probe pass skipped entirely if the brand's ``last_rate_limit_remaining``
  is under 50 (preserve daily budget for user-facing polling)
- Probe pass skipped if the auth-storm circuit-breaker has fired
- Per-probe timeout 5s, per-pass time budget 30s
- 404/403/500 swallowed silently; only 200+JSON feeds the scout
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence


@dataclass(frozen=True, slots=True)
class V3Probe:
    """One probe endpoint that the silent scout-channel will exercise.

    Attributes:
        name: Short identifier used as the scout-endpoint key.
              Should be unique within a brand family.
        path: URL path template. ``{vin}`` is substituted at call-time;
              ``{user_id}`` (where applicable) comes from
              ``IDKAuth.user_id`` captured during the login flow.
        host_override: Optional full ``scheme://host`` override. None
              means use the brand client's default backend host. Mainly
              for cross-IDP probes (e.g. Skoda calling the mysmob host).
        notes: Human-readable comment for code-readers — what the probe
              is verifying. Never emitted at runtime.
    """

    name: str
    path: str
    host_override: str | None = None
    notes: str = ""


# ── OLA (SEAT + CUPRA) ──────────────────────────────────────────────────────
# PyCupra docs `API_*` constants. SEAT + CUPRA share the OLA backend at
# `ola.prod.code.seat.cloud.vwgroup.com`. The v1 endpoint family returns
# data on legacy vehicles (SEAT Mii Electric, older CUPRA Born trim);
# v5 covers the current MEB platform. Our current production parser only
# hits v5 for most of these, so the probe surface picks up v1 fallbacks
# AND v2 endpoints (renders, driving-data) we don't yet read at all.
_OLA_PROBES: tuple[V3Probe, ...] = (
    V3Probe(
        name="ola_v1_mileage",
        path="/v1/vehicles/{vin}/mileage",
        notes="PyCupra fallback for legacy Mii Electric — odometer when v5 mycar returns null",
    ),
    V3Probe(
        name="ola_v1_maintenance",
        path="/v1/vehicles/{vin}/maintenance",
        notes="Service intervals (days+km) — PyCupra exposes via this v1 path",
    ),
    V3Probe(
        name="ola_v1_charging_info",
        path="/v1/vehicles/{vin}/charging/info",
        notes="target_soc + max_charge_current — PyCupra reads here for non-v5 vehicles",
    ),
    V3Probe(
        name="ola_v2_driving_data_custom",
        path="/v2/vehicles/{vin}/driving-data/CUSTOM",
        notes="Trip-statistics — PyCupra wraps as trip history, we don't probe today",
    ),
    V3Probe(
        name="ola_v2_renders",
        path="/v2/vehicles/{vin}/renders",
        notes="Vehicle render URLs — Image entity foundation for v3.0",
    ),
    V3Probe(
        name="ola_v1_ranges",
        path="/v1/vehicles/{vin}/ranges",
        notes="Separate ranges endpoint — PyCupra reads when mycar.engines[].rangeKm is null",
    ),
    V3Probe(
        name="ola_v2_departure_profiles",
        path="/v2/vehicles/{vin}/departure-profiles",
        notes="Per-location charging+climate plans — distinct from departure_timers",
    ),
    V3Probe(
        name="ola_v1_parking_position",
        path="/v1/vehicles/{vin}/parkingposition",
        notes="Cross-check carCapturedTimestamp / heading — confirm parking_time field",
    ),
    V3Probe(
        name="ola_v1_charging_battery_care",
        path="/v1/vehicles/{vin}/charging/battery-care",
        notes="Battery-care opt-in + target — already in our parser for v5, probe v1 fallback",
    ),
    V3Probe(
        name="ola_v1_charging_history",
        path="/v1/vehicles/{vin}/charging/history",
        notes="Recent charging sessions — PyCupra exposes; we expose for Skoda only",
    ),
)


# ── Skoda (mysmob) ──────────────────────────────────────────────────────────
# myskoda Apache-2.0 endpoints. Backend host is
# `mysmob.api.connect.skoda-auto.cz`. We already call several mysmob paths
# in production; the probes below are the *additional* ones our parser
# doesn't visit today (driving-score, predictive-maintenance, garage
# predictions, software-version status).
_MYSMOB_PROBES: tuple[V3Probe, ...] = (
    V3Probe(
        name="mysmob_v1_charging_history",
        path="/api/v1/charging/{vin}/history",
        notes="Total kWh charged + per-session — myskoda exposes; field-coverage gap for us",
    ),
    V3Probe(
        name="mysmob_v2_driving_score",
        path="/api/v2/vehicle-status/{vin}/driving-score",
        notes="Skoda app driving-score gamification — we surface partial today",
    ),
    V3Probe(
        name="mysmob_v1_renders",
        path="/api/v1/vehicle-information/{vin}/renders",
        notes="Composite-render layers (multi-angle vehicle imagery)",
    ),
    V3Probe(
        name="mysmob_v2_predictive_maintenance",
        path="/api/v2/maintenance/{vin}/predictive",
        notes="Predictive-maintenance opt-in + preferred channel",
    ),
    V3Probe(
        name="mysmob_v2_software_version",
        path="/api/v2/software-version/{vin}/update-status",
        notes="OTA-update availability — Skoda-only feature foreshadowing",
    ),
    V3Probe(
        name="mysmob_v1_bookings",
        path="/api/v1/maintenance/{vin}/bookings",
        notes="Next service appointment list (Booking dataclass)",
    ),
    V3Probe(
        name="mysmob_v1_service_partner",
        path="/api/v1/maintenance/{vin}/service-partner",
        notes="Preferred workshop — already exposed; probe for field-shape changes",
    ),
    V3Probe(
        name="mysmob_v1_warning_lights",
        path="/api/v1/vehicle-health-warnings/{vin}",
        notes="Skoda-flavoured warning-light enum that v3.0 unifies cross-brand",
    ),
)


# ── CARIAD-BFF (VW EU + Audi) ───────────────────────────────────────────────
# `emea.bff.cariad.digital`. These are documented in CarConnectivity-vw
# (Apache-2.0) and audi_connect_ha (MIT) but not currently in our
# production call-set. Most expand the v3.0 capability matrix:
# oil-level, tyre-pressure, parking-time, auxiliary-heating, charge
# contracts/subscriptions.
_CARIAD_BFF_PROBES: tuple[V3Probe, ...] = (
    V3Probe(
        name="cariad_bff_oil_level",
        path="/vehicle/v1/vehicles/{vin}/selectivestatus?jobs=oilLevel",
        notes="Continuous oil-level % — audit-flagged must-ship for Audi/VW EU",
    ),
    V3Probe(
        name="cariad_bff_tyre_pressure",
        path="/vehicle/v1/vehicles/{vin}/selectivestatus?jobs=tyrePressure",
        notes="Per-wheel tyre pressure (bar) — audit-flagged must-ship cross-brand",
    ),
    V3Probe(
        name="cariad_bff_parking_time",
        path="/vehicle/v1/vehicles/{vin}/parkingposition",
        notes="parkingTime UTC field — audit-flagged universal gap",
    ),
    V3Probe(
        name="cariad_bff_auxiliary_heating",
        path="/vehicle/v1/vehicles/{vin}/selectivestatus?jobs=auxiliaryHeating",
        notes="Standheizung (Webasto/Eberspächer) — ICE Audi/VW EU touring users",
    ),
    V3Probe(
        name="cariad_bff_active_ventilation",
        path="/vehicle/v1/vehicles/{vin}/selectivestatus?jobs=activeVentilation",
        notes="MEB ID.7 + facelift ID.3/.4 active-ventilation — interim-silenced in v2.4.2",
    ),
    V3Probe(
        name="cariad_bff_charge_contracts",
        path="/charge/v1/contracts/{vin}",
        notes="Subscription expiry + active charge contracts (Elli/Plug&Charge)",
    ),
    V3Probe(
        name="cariad_bff_pay_subscriptions",
        path="/pay/v1/subscriptions/{vin}",
        notes="Per-feature subscription state — feeds capability-filter Phase 3",
    ),
    V3Probe(
        name="cariad_bff_mobile_device_keys",
        path="/vehicle/v1/vehicles/{vin}/mobiledevicekeys",
        notes="Digital-key state — BLE+phone-as-key foundation",
    ),
    V3Probe(
        name="cariad_bff_bleident",
        path="/vehicle/v1/vehicles/{vin}/bleident",
        notes="BLE identity blob — v3.0 BLE binary_sensor.car_nearby foundation",
    ),
    V3Probe(
        name="cariad_bff_garage_capabilities",
        path="/vehicle/v1/vehicles/garage/capabilities",
        notes="Account-level capability inventory — distinct from per-VIN capabilities",
    ),
)


# ── VW NA (con-veh.net) ─────────────────────────────────────────────────────
# matpoulin/CarConnectivity-connector-volkswagen-na Apache-2.0. Backend host
# is regional (`b-h-s.spr.us00.p.con-veh.net` or `…ca00…`). We have limited
# production parser coverage for VW NA; even a 1-endpoint probe yields
# significant scout signal for the small but vocal US/CA user pool (#270).
_VW_NA_PROBES: tuple[V3Probe, ...] = (
    V3Probe(
        name="vw_na_vehicle_health",
        path="/v3/vehicles/{vin}/vehicleHealth",
        notes="Combined health + warning lights for myVW US/CA",
    ),
    V3Probe(
        name="vw_na_trip_data",
        path="/v3/vehicles/{vin}/tripData/longTerm",
        notes="Lifetime trip statistics — feature-parity with EU tripstatistics",
    ),
    V3Probe(
        name="vw_na_subscription",
        path="/v3/vehicles/{vin}/subscriptions",
        notes="Car-Net subscription state — US-equivalent of EU pay/subscriptions",
    ),
)


# ── Porsche (api.ppa.porsche.com) ───────────────────────────────────────────
# Porsche My-Porsche app behaviour confirmed via porschecarconnect community
# work. Backend host `api.ppa.porsche.com`. Probe surface focuses on
# measurements-bundle field-shape verification (audit risk #5 — wrong
# field= filter list returns a different shape).
_PORSCHE_PROBES: tuple[V3Probe, ...] = (
    V3Probe(
        name="porsche_measurements_full",
        path="/app/connect/v1/vehicles/{vin}/measurements",
        notes="Full measurements bundle (no fields=filter) — discover unknown measurement types",
    ),
    V3Probe(
        name="porsche_capabilities",
        path="/app/connect/v1/vehicles/{vin}/capabilities",
        notes="Per-VIN capability list — Porsche-flavoured subscription matrix",
    ),
    V3Probe(
        name="porsche_service_intervals",
        path="/app/connect/v1/vehicles/{vin}/serviceIntervals",
        notes="Porsche service-intervals shape (we surface partial today)",
    ),
)


# ── Brand → probe-list dispatch ─────────────────────────────────────────────
# The brand name strings here MUST match the values in ``BrandConfig.name``
# used across the codebase. SEAT + CUPRA share the OLA backend so they
# share the same probe set.
PROBES_BY_BRAND: dict[str, tuple[V3Probe, ...]] = {
    "seat":          _OLA_PROBES,
    "cupra":         _OLA_PROBES,
    "skoda":         _MYSMOB_PROBES,
    "volkswagen":    _CARIAD_BFF_PROBES,
    "audi":          _CARIAD_BFF_PROBES,
    "volkswagen_na": _VW_NA_PROBES,
    "porsche":       _PORSCHE_PROBES,
}


# Per-brand backend host. The probe runner combines this with each probe's
# ``path`` (after ``{vin}`` / ``{user_id}`` substitution) to build the full
# URL. ``V3Probe.host_override`` wins over this default when set, for the
# rare cases where a brand needs to probe a sibling-brand IDP.
BASE_URL_BY_BRAND: dict[str, str] = {
    "seat":          "https://ola.prod.code.seat.cloud.vwgroup.com",
    "cupra":         "https://ola.prod.code.seat.cloud.vwgroup.com",
    "skoda":         "https://mysmob.api.connect.skoda-auto.cz",
    "volkswagen":    "https://emea.bff.cariad.digital",
    "audi":          "https://emea.bff.cariad.digital",
    # VW NA is regional (us00 vs ca00); the brand client knows which.
    # The runner falls back to the brand client's own ``_BASE`` attribute
    # for VW NA when present, otherwise probes are skipped for VW NA.
    "porsche":       "https://api.ppa.porsche.com",
}


def probes_for_brand(brand_name: str) -> Sequence[V3Probe]:
    """Return the probe list for the given brand, or an empty tuple."""
    return PROBES_BY_BRAND.get(brand_name, ())


def base_url_for_brand(brand_name: str) -> str | None:
    """Return the backend base URL for the brand, or ``None``."""
    return BASE_URL_BY_BRAND.get(brand_name)


# Approx total probe surface (sum of unique endpoints across brand families):
#   OLA (SEAT+CUPRA): 10
#   mysmob (Skoda):    8
#   CARIAD-BFF (VW+Audi): 10
#   VW NA:             3
#   Porsche:           3
# = 34 distinct endpoints. Per-VIN per-pass at 1×/h = 34 calls/h max across
# a multi-brand HA install. Per-user typical scope: 8-10 calls/h. Well under
# any documented rate-limit for the targeted backends.
