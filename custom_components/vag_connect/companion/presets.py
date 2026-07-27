# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Per-brand screen presets for the companion (ADB) channel — v3.0.0-alpha.

A preset says how to find a value or a button in one brand's app: which node in
the accessibility tree, and how to turn its text into a number or a bool. The
selector is deliberately layered so it survives small app changes:

1. ``resource_id`` — the most stable handle when the app assigns one.
2. ``content_desc_re`` — the accessibility description, next most stable.
3. ``label_re`` + ``value_from`` — find a known localized label node, then read
   the value from that node's text or a sibling. This is the fallback the
   prior-art projects rely on, and it is why the app language must be German or
   English for now.

HONESTY: only ``volkswagen`` is verified against a real device (a Golf GTE).
The other four are ``verified=False``. Their selectors are seeded from what the
decoded apps and the VW shape suggest, but they are NOT confirmed. An unverified
preset is allowed to read (a wrong read is a wrong number, recoverable) but must
never write (a wrong tap is a physical action on the car). ``CompanionChannel``
enforces that; see ``BrandPreset.writable``.
"""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class FieldSelector:
    """How to locate one value in the accessibility tree and parse it.

    At least one of ``resource_id`` / ``content_desc_re`` / ``label_re`` must be
    set. They are tried in that order; the first that hits wins.
    """

    target: str  # the VehicleData field this fills, e.g. "battery_soc"
    resource_id: str | None = None
    content_desc_re: str | None = None
    label_re: str | None = None
    # When matched via ``label_re``, where the value text comes from:
    #   "self"    → the label node's own text (e.g. "Ladung 74 %")
    #   "sibling" → the next sibling node's text (label and value are separate)
    value_from: str = "self"
    # Turns the raw on-screen text into the typed value. Defaults to a plain
    # string; the channel applies the field's own coercion on top.
    parse: str = "str"  # one of: str, percent, int_km, bool_charging, kw


@dataclass(frozen=True)
class ActionSelector:
    """How to find a button to tap for a write action."""

    action: str  # logical action name, e.g. "start_climate"
    resource_id: str | None = None
    content_desc_re: str | None = None
    label_re: str | None = None
    # Some actions need to navigate to a screen first (tab labels, in order).
    nav_labels: tuple[str, ...] = ()


@dataclass(frozen=True)
class OverlaySelector:
    """A known interstitial / nag screen (power-saving prompt, delay notice, …).

    Detected before every read and every tap; dismissed with BACK only (which
    can never actuate the car), so overlay recovery is safe even on the
    unverified read-only brands. Matched on content-description or visible text.
    """

    name: str  # for logging / diagnostics
    content_desc_re: str | None = None
    text_re: str | None = None


@dataclass(frozen=True)
class BrandPreset:
    """Everything the channel needs to read and (maybe) write one brand's app."""

    brand: str
    package: str  # the Android package name of the app
    verified: bool  # True only when confirmed against a real device
    # The app version this preset was built against. The channel refuses writes
    # when the live app version differs (reads still run); mirrors the
    # app-version quarantine idea from the prior-art projects.
    verified_app_version: str | None
    fields: tuple[FieldSelector, ...]
    actions: tuple[ActionSelector, ...] = ()
    # v2.26.0 — nag/interstitial screens to dismiss before reading/tapping.
    overlays: tuple[OverlaySelector, ...] = ()
    # v2.26.0 (ckomma #21) — "too many requests" / account-lockout banners. On
    # match the channel trips a LONG, PERSISTED backoff and blocks writes, so we
    # never drive further into a real rate-limit. Distinct from a nag (which is
    # dismissed): a rate-limit banner means back off, not press BACK.
    rate_limit_banners: tuple[OverlaySelector, ...] = ()
    # v2.26.0 — a node that proves we are on the expected main/detail screen.
    # A read/tap only proceeds when this anchor is present, so a stray screen
    # (or a dismissed-overlay-left-us-elsewhere state) yields no_data rather than
    # a wrong value or a tap into the void. None = no anchor gate (VW best-effort
    # until a dump confirms one; see #10 where tiles can be absent entirely).
    screen_anchor: FieldSelector | None = None

    @property
    def writable(self) -> bool:
        """Writes are only ever attempted on a verified preset with actions.

        An unverified preset must not tap: a wrong selector on a read is a wrong
        number, but a wrong selector on a tap is a physical command sent to the
        wrong control on the car.
        """
        return self.verified and bool(self.actions)


# v2.26.0 (ckomma #21) — a shared, multilingual "too many requests / temporarily
# blocked" banner. The CARIAD rate-limit backend is shared across all five
# brands, so the same seeded matcher is correct brand-agnostically; only the
# exact wording would be tightened per brand once a tester captures it.
_RATE_LIMIT_BANNER = OverlaySelector(
    name="rate_limited",
    content_desc_re=(
        r"(?:Zu\s*(?:viele|häufige)\s*Anfragen|Too\s*many\s*requests"
        r"|vorübergehend\s*(?:gesperrt|blockiert|nicht\s*verfügbar)"
        r"|temporarily\s*(?:blocked|unavailable)|Demasiadas\s*solicitudes)"
    ),
    text_re=(
        r"(?:Zu\s*(?:viele|häufige)\s*Anfragen|Too\s*many\s*requests"
        r"|vorübergehend\s*(?:gesperrt|blockiert|nicht\s*verfügbar)"
        r"|temporarily\s*(?:blocked|unavailable)|Demasiadas\s*solicitudes)"
    ),
)


# ── Volkswagen — the one brand verified in-house (Golf GTE, app 4.2.1) ───────

_VW = BrandPreset(
    brand="volkswagen",
    package="com.volkswagen.weconnect",
    verified=True,
    verified_app_version="4.2.1",
    fields=(
        FieldSelector(
            target="battery_soc",
            content_desc_re=r"(?:Ladezustand|State of charge|Ladung)\D*(\d{1,3})\s*%",
            label_re=r"^(?:Ladung|Charge|Ladezustand|State of charge)$",
            value_from="sibling",
            parse="percent",
        ),
        FieldSelector(
            target="electric_range_km",
            content_desc_re=r"(?:Reichweite|Range)\D*(\d{1,4})\s*km",
            label_re=r"^(?:Reichweite|Range)$",
            value_from="sibling",
            parse="int_km",
        ),
        FieldSelector(
            target="charging_state",
            content_desc_re=r"(?:Lädt|Charging|Wird geladen|Nicht verbunden|Not connected|Bereit|Ready)",
            parse="str",
        ),
        FieldSelector(
            target="is_charging",
            content_desc_re=r"(?:Lädt|Wird geladen|Charging)",
            parse="bool_charging",
        ),
        FieldSelector(
            target="target_soc",
            label_re=r"^(?:Zielladung|Ziel-Ladung|Target|Zielwert)$",
            value_from="sibling",
            parse="percent",
        ),
        FieldSelector(
            target="remaining_charge_time_min",
            content_desc_re=r"(?:noch|remaining)\D*(\d{1,4})\s*min",
            parse="int_km",  # reuse the "first integer" parser
        ),
        # v2.26.0 (ckomma #7) — odometer. Grouped-thousands safe now (_first_int).
        FieldSelector(
            target="odometer_km",
            content_desc_re=r"(?:Kilometerstand|Odometer|Mileage|km-Stand)\D*([\d\s.]+)\s*km",
            label_re=r"^(?:Kilometerstand|Odometer|Mileage|km-Stand)$",
            value_from="sibling",
            parse="int_km",
        ),
        # v2.26.0 (ckomma #15) — live charge power in kW.
        FieldSelector(
            target="charging_power_kw",
            content_desc_re=r"(?:Ladeleistung|Charge\s*power|Charging\s*power)\D*([\d.,]+)\s*kW",
            label_re=r"^(?:Ladeleistung|Charge power|Charging power)$",
            value_from="sibling",
            parse="kw",
        ),
    ),
    actions=(
        ActionSelector(
            action="start_climate",
            content_desc_re=r"(?:Klima\w*\s*(?:starten|ein)|Start climate|Climatisation on)",
            label_re=r"^(?:Klimatisierung|Climate|Klima)$",
        ),
        ActionSelector(
            action="stop_climate",
            content_desc_re=r"(?:Klima\w*\s*(?:stoppen|aus)|Stop climate|Climatisation off)",
        ),
        ActionSelector(
            action="start_charging",
            content_desc_re=r"(?:Laden\s*starten|Start charging)",
        ),
        ActionSelector(
            action="stop_charging",
            content_desc_re=r"(?:Laden\s*stoppen|Stop charging)",
        ),
    ),
    # v2.26.0 (ckomma #13, #8) — confirmed VW nag screens. BACK dismisses both.
    overlays=(
        OverlaySelector(
            name="power_saving",
            content_desc_re=r"(?:Intelligentes\s*Stromsparen|Intelligent\s*power\s*saving)",
            text_re=r"(?:Intelligentes\s*Stromsparen|Intelligent\s*power\s*saving)",
        ),
        OverlaySelector(
            name="vehicle_health_delay",
            content_desc_re=r"(?:verzögert\s*ausgeführt|executed\s*with\s*a\s*delay)",
            text_re=r"(?:verzögert\s*ausgeführt|executed\s*with\s*a\s*delay)",
        ),
    ),
    # v2.26.0 (ckomma #21) — SEEDED (unverified even for VW: the ckomma report
    # was a backend request-limit, not a confirmed on-screen banner). The
    # mechanism is what matters; the exact string comes with a tester capture.
    rate_limit_banners=(_RATE_LIMIT_BANNER,),
)

# ── The four unverified brands — structure present, selectors best-effort ────
#
# These read what they can and refuse writes (``verified=False`` → not
# ``writable``). Each needs a tester's uiautomator dump to confirm the field
# selectors and to promote it to verified with real actions. The label
# alternations below are seeded from the German/English wording the apps use;
# they are a starting point for a tester, NOT a validated map.

def _readonly_soc_range_fields(soc_label: str, range_label: str) -> tuple[FieldSelector, ...]:
    return (
        FieldSelector(
            target="battery_soc",
            label_re=soc_label,
            value_from="sibling",
            parse="percent",
        ),
        FieldSelector(
            target="electric_range_km",
            label_re=range_label,
            value_from="sibling",
            parse="int_km",
        ),
        # v2.26.0 — odometer is brand-generic (every app shows it). Label is the
        # same German/English wording; promote to verified once a tester dump
        # confirms the exact string for this brand.
        FieldSelector(
            target="odometer_km",
            label_re=r"^(?:Kilometerstand|Odometer|Mileage|km-Stand)$",
            value_from="sibling",
            parse="int_km",
        ),
        FieldSelector(
            target="charging_state",
            content_desc_re=r"(?:Lädt|Charging|Wird geladen|Nicht verbunden|Not connected)",
            parse="str",
        ),
        FieldSelector(
            target="is_charging",
            content_desc_re=r"(?:Lädt|Wird geladen|Charging)",
            parse="bool_charging",
        ),
    )


# v2.26.0 — seeded (unverified) power-saving nag for the read-only brands.
# German / English / Spanish wording; promote per brand once a tester dump
# confirms the exact string. Dismissed with BACK, so it is safe on reads.
_SEEDED_POWERSAVE = OverlaySelector(
    name="power_saving",
    content_desc_re=(
        r"(?:Intelligentes\s*(?:Strom|Energie)sparen"
        r"|Intelligent\s*power\s*saving|Ahorro\s*inteligente)"
    ),
    text_re=(
        r"(?:Intelligentes\s*(?:Strom|Energie)sparen"
        r"|Intelligent\s*power\s*saving|Ahorro\s*inteligente)"
    ),
)


_AUDI = BrandPreset(
    brand="audi",
    package="de.myaudi.mobile.assistant",
    verified=False,
    verified_app_version=None,
    fields=_readonly_soc_range_fields(
        r"^(?:Ladezustand|State of charge)$", r"^(?:Reichweite|Range)$"
    ),
    overlays=(_SEEDED_POWERSAVE,),
    rate_limit_banners=(_RATE_LIMIT_BANNER,),
)

_SKODA = BrandPreset(
    brand="skoda",
    package="cz.skodaauto.connect",
    verified=False,
    verified_app_version=None,
    fields=_readonly_soc_range_fields(
        r"^(?:Ladestand|Ladezustand|State of charge)$", r"^(?:Reichweite|Range)$"
    ),
    overlays=(_SEEDED_POWERSAVE,),
    rate_limit_banners=(_RATE_LIMIT_BANNER,),
)

_SEAT = BrandPreset(
    brand="seat",
    package="com.seat.myseat.ola",
    verified=False,
    verified_app_version=None,
    fields=_readonly_soc_range_fields(
        r"^(?:Ladezustand|State of charge)$", r"^(?:Reichweite|Range)$"
    ),
    overlays=(_SEEDED_POWERSAVE,),
    rate_limit_banners=(_RATE_LIMIT_BANNER,),
)

_CUPRA = BrandPreset(
    brand="cupra",
    package="com.cupra.mycupra",
    verified=False,
    verified_app_version=None,
    fields=_readonly_soc_range_fields(
        r"^(?:Ladezustand|State of charge)$", r"^(?:Reichweite|Range)$"
    ),
    overlays=(_SEEDED_POWERSAVE,),
    rate_limit_banners=(_RATE_LIMIT_BANNER,),
)


PRESETS: dict[str, BrandPreset] = {
    p.brand: p for p in (_VW, _AUDI, _SKODA, _SEAT, _CUPRA)
}


# ── value parsers ────────────────────────────────────────────────────────────

_FIRST_INT_RE = re.compile(r"-?\d+")
# v2.26.0 (ckomma #7) — a grouped-thousands number: 1-3 digits then one or more
# 3-digit groups: whitespace (\s covers space + nbsp) or dot as separator.
# A plain decimal ("12,5", "12.5") is NOT matched (comma, or a non-3-digit tail),
# so it is left untouched for the kw parser.
_GROUPED_THOUSANDS_RE = re.compile(r"-?\d{1,3}(?:[\s.]\d{3})+(?!\d)")


def _first_int(text: str) -> int | None:
    if not text:
        return None
    # Collapse a grouped-thousands number first, otherwise the first-digit-run
    # regex below truncates "27 886 km" to 27 (ckomma #7, an odometer read).
    gm = _GROUPED_THOUSANDS_RE.search(text)
    if gm:
        digits = re.sub(r"[\s.]", "", gm.group())
        try:
            return int(digits)
        except ValueError:  # pragma: no cover - regex guarantees digits
            pass
    m = _FIRST_INT_RE.search(text)
    return int(m.group()) if m else None


def coerce(parse: str, raw: str | None) -> object | None:
    """Turn a matched raw string into the typed value the field expects."""
    if raw is None:
        return None
    raw = raw.strip()
    if not raw:
        return None
    if parse == "str":
        return raw
    if parse in ("percent", "int_km"):
        val = _first_int(raw)
        if val is None:
            return None
        if parse == "percent" and not (0 <= val <= 100):
            return None  # a "%" that is not a plausible SoC is a mis-match
        return val
    if parse == "bool_charging":
        return bool(re.search(r"(?:Lädt|Wird geladen|Charging)", raw, re.I))
    if parse == "kw":
        m = re.search(r"(\d+(?:[.,]\d+)?)", raw)
        return float(m.group(1).replace(",", ".")) if m else None
    return raw


# The logical write actions the channel understands, mapped to the coordinator
# command names. Only actions listed here can ever be dispatched.
ACTION_TO_COMMAND: dict[str, str] = {
    "start_climate": "command_start_climate",
    "stop_climate": "command_stop_climate",
    "start_charging": "command_start_charging",
    "stop_charging": "command_stop_charging",
}
