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
    # v2.26.0 (#968) — split-node apps. Some apps (My CUPRA) render a value and
    # its unit as SEPARATE text nodes with NO label sentence: "51" then "%",
    # "182" then "KM". ``unit_re`` matches the UNIT node's text exactly; the
    # value taken is the nearest preceding bare-number node. This is the only
    # way to read those apps, which carry neither content-desc sentences nor a
    # localized label next to the number.
    unit_re: str | None = None
    # When matched via ``label_re``, where the value text comes from:
    #   "self"    → the label node's own text (e.g. "Ladung 74 %")
    #   "sibling" → the next sibling node's text (label and value are separate)
    value_from: str = "self"
    # Turns the raw on-screen text into the typed value. Defaults to a plain
    # string; the channel applies the field's own coercion on top.
    parse: str = "str"  # str, percent, int_km, bool_charging, kw, bool_locked, bool_ignition


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
class NavReadSelector:
    """v2.26.0 (C9, ckomma-grounded) — read values that live on a DETAIL screen.

    Some values are not on the overview at all: on the verified VW app the
    charge target, remaining time and live power are behind the range/charge
    tile (ckomma's ``set_charging`` reaches them by tapping ``range_tile`` and
    reading the charge-detail narration). This selector says how to open that
    detail (``tile``) and which values to read once there (``values``).

    A nav-READ still taps FORWARD, so it is gated exactly like a write on the
    verified preset + matching app version (``CompanionChannel.nav_reads_enabled``)
    — a wrong tile tap is as bad as a wrong command. It is NOT gated on
    ``writable``: reading the charge target is allowed even while command
    entities are quarantined. The channel always returns to the overview (BACK)
    afterwards so the next plain read sees the main screen.
    """

    name: str
    tile: ActionSelector                 # the tile to tap to open the detail
    values: tuple["FieldSelector", ...]  # values to read on the detail screen


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
    # The app version(s) this preset was built against. The channel refuses
    # writes/nav-taps when the live app version is not one of these (plain reads
    # still run); mirrors the app-version quarantine idea from the prior-art
    # projects. A TUPLE accepts several known-compatible versions at once, which
    # matters because We Connect reports its version inconsistently (a Play
    # marketing "4.3.2" vs an internal versionName like "3.63.2"/"3.64.0" that all
    # ship the SAME accessibility tree), so pinning a single string re-quarantines
    # users on every patch. A bare string still works for the read-only brands.
    verified_app_version: str | tuple[str, ...] | None
    fields: tuple[FieldSelector, ...]
    actions: tuple[ActionSelector, ...] = ()
    # v2.26.0 (C9) — values behind a detail screen, read by tapping a tile and
    # reading the detail, then BACK. Gated like writes (verified + version) but
    # not on ``writable``. Empty for the unverified brands (no confirmed nav).
    nav_reads: tuple[NavReadSelector, ...] = ()
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
    # v2.26.0 (ckomma #22/#16) — the app's own "synchronised N ago" line. Parsed
    # into a source-data age so we can tell "the car's data is old" (a VW-side
    # freshness issue) apart from "our connector is unhealthy". Captures a number
    # and a unit. None = not wired for this brand.
    sync_age_re: str | None = None

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


# v2.26.0 (ckomma #22) — the app's freshness line, "Synchronised 5 minutes ago"
# / "Aktualisiert vor 5 Minuten". Captures the number and the unit; shared
# across brands (same wording family), tightened per brand with a tester dump.
_SYNC_AGE_RE = (
    r"(?:Synchronisiert|Aktualisiert|Synchronised|Synchronized|Updated|"
    r"Letzte\s*Aktualisierung)[^0-9]*?(\d+)\s*"
    r"(Sekunden?|Minuten?|Stunden?|Tage?n?|seconds?|minutes?|hours?|days?"
    r"|min|sek|std|h|d)"
)


# ── Volkswagen — the one brand verified in-house (Golf GTE, app 4.2.1) ───────

_VW = BrandPreset(
    brand="volkswagen",
    package="com.volkswagen.weconnect",
    verified=True,
    # #968 (Philip-Wiege) — We Connect updated 4.2.1 → 4.3.2 and the single-value
    # quarantine then disabled every nav-read ("app 4.3.2 > preset 4.2.1"). The
    # 4.3.2 accessibility tree keeps the SAME stable resource-ids this preset
    # already reads (rangeArcBatterySoc / rangeTile / rangeArcRangeAndUnit — the
    # prior-art connector reads exactly these on 4.3.2), so this is a version
    # widening, not a selector rewrite. Accept the Play "4.3.2" and the internal
    # versionName forms ("3.64.0" / "3.63.2") that report the same UI, so a patch
    # bump no longer re-quarantines readers.
    verified_app_version=("4.3.2", "3.64.0", "3.63.2", "4.2.1"),
    # v2.26.0 — READ vocabulary re-grounded against ckomma/charge-app-connector-vw
    # (real-device VW app 4.2.x). The old words ("Ladezustand", "Reichweite",
    # "Zielladung") did NOT match what We Connect actually narrates in its
    # accessibility descriptions; ckomma's verified patterns do ("Battery charge
    # level", "Battery range", "Target charge level"). Overview-only values stay
    # here; charge-target / power / time live behind the range tile and moved to
    # ``nav_reads`` below (that is where ckomma reads them too).
    fields=(
        FieldSelector(
            target="battery_soc",
            content_desc_re=(
                r"(?:Batterie(?:ladung)?|Battery(?:\s*charge(?:\s*level)?|\s*level)?"
                r"|State of charge|Ladezustand|Ladung)\D*(\d{1,3})\s*"
                r"(?:%|Prozent|per\s*cent|percent)"
            ),
            label_re=r"^(?:Batterie(?:ladung)?|Battery(?:\s*charge)?|Ladung|Charge|State of charge)$",
            value_from="sibling",
            parse="percent",
        ),
        FieldSelector(
            target="electric_range_km",
            content_desc_re=(
                r"(?:Batteriereichweite|Battery range|Electric range|Reichweite|Range)"
                # The app narrates the unit in words, not as a symbol: a real
                # We Connect 4.2.1 tile reads "Batteriereichweite: 253
                # Kilometer". Matching only "km" read nothing at all here.
                # NOTE (#968): a Mk8 on imperial units narrates "14 miles" — not
                # read here yet; a unit-aware range parse is a follow-up so we
                # never mislabel miles as km.
                r"\D*(\d{1,4})\s*(?:km\b|[Kk]ilomet)"
            ),
            label_re=r"^(?:Batteriereichweite|Battery range|Electric range|Reichweite|Range)$",
            value_from="sibling",
            parse="int_km",
        ),
        FieldSelector(
            target="charging_state",
            content_desc_re=(
                r"(?:Wird geladen|Lädt|Charging|Nicht verbunden|Not connected"
                r"|Ladekabel|Connect(?:ing)?\s*(?:the\s*)?charging cable"
                r"|Vollständig geladen|Fully charged|Bereit|Ready)"
            ),
            parse="str",
        ),
        FieldSelector(
            target="is_charging",
            content_desc_re=r"(?:Wird geladen|Lädt|Charging)",
            parse="bool_charging",
        ),
        # v2.26.0 (ckomma #7) — odometer. Grouped-thousands safe now (_first_int).
        FieldSelector(
            target="odometer_km",
            content_desc_re=(
                r"(?:Kilometerstand|Odometer|Mileage|km-Stand)"
                r"\D*([\d\s.]+)\s*(?:km\b|[Kk]ilomet)"
            ),
            label_re=r"^(?:Kilometerstand|Odometer|Mileage|km-Stand)$",
            value_from="sibling",
            parse="int_km",
        ),
    ),
    # v2.26.0 — WRITES QUARANTINED. The previous single-tap actions were wrong:
    # ckomma proves We Connect needs a TWO-STEP nav (overview tile → detail
    # screen → action button) that our do_action never did, so climate/charge
    # commands could only ever fail with "control not found". Rather than ship
    # command entities that never work, this preset carries NO actions (so
    # ``writable`` is False and no command entities spawn) until the 2-step nav
    # is confirmed on a real device. Reads are unaffected.
    actions=(),
    # v2.26.0 (C9) — charge target / power / remaining-time live behind the
    # range tile (ckomma's set_charging taps range_tile_center to reach the
    # charge detail, then reads exactly these). Gated like a write (verified +
    # matching app version), but allowed while command entities are quarantined.
    nav_reads=(
        NavReadSelector(
            name="charge_detail",
            tile=ActionSelector(
                action="open_charge_detail",
                # #968 — resource-id first (the most stable handle, unchanged on
                # 4.3.2 per the prior-art connector); the narration fallback keeps
                # older/localised builds working.
                resource_id="rangeTile",
                content_desc_re=r"(?:Batteriereichweite|Battery range|Electric range)",
            ),
            values=(
                # #968 (plainmad, Mk8 Golf GTE) — on the Mk8 the state-of-charge
                # and range live on THIS charge-detail sheet, not the overview
                # (overview shows only the range tile). ``rangeArcBatterySoc``
                # carries text "Battery 41 %"; the content-desc reads "Battery
                # charge level: 41 per cent". Range is captured number+unit so
                # range_km converts imperial. A nav-read reads only its own
                # values, so SoC/range must be listed here to be seen at all.
                FieldSelector(
                    target="battery_soc",
                    resource_id="rangeArcBatterySoc",
                    content_desc_re=(
                        r"(?:Battery charge level|Batterie(?:ladung)?|Ladezustand"
                        r"|State of charge)\D*(\d{1,3})\s*"
                        r"(?:%|Prozent|per\s*cent|percent)"
                    ),
                    parse="percent",
                ),
                FieldSelector(
                    target="target_soc",
                    content_desc_re=(
                        r"(?:Zielladestand|Target charge(?:\s*level)?|Upper charge limit"
                        r"|Ladeobergrenze|Obere Ladegrenze)\D*(\d{1,3})\s*"
                        r"(?:%|Prozent|per\s*cent|percent)"
                    ),
                    parse="percent",
                ),
                FieldSelector(
                    target="charging_power_kw",
                    content_desc_re=(
                        r"(?:Ladeleistung|Charging power|Charging capacity|Charge power)"
                        r"\D*([\d.,]+)\s*kW"
                    ),
                    parse="kw",
                ),
                FieldSelector(
                    target="remaining_charge_time_min",
                    content_desc_re=(
                        r"(?:\d{1,2}\s*(?:Stunden?|hours?)|\d{1,2}:\d{2}\s*h"
                        r"|(?:noch|remaining)\s*\d)"
                    ),
                    parse="hm_minutes",
                ),
            ),
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
    # v2.26.0 (ckomma #22) — VW shows a "Synchronised … ago" line (#22 confirms
    # the wording exists); seeded German + English, number + unit.
    sync_age_re=_SYNC_AGE_RE,
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
    sync_age_re=_SYNC_AGE_RE,
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
    sync_age_re=_SYNC_AGE_RE,
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
    sync_age_re=_SYNC_AGE_RE,
)

# v2.26.0 (#968) — My CUPRA grounded from a real uiautomator dump. Unlike We
# Connect (rich content-desc sentences), this app renders values as SPLIT bare
# text nodes with no label sentence: "51" then "%", "182" then "KM", plus plain
# "Vehicle locked" / "Engine on" lines and a "Last updated: N ago" freshness
# line. The old German-label seed read NOTHING here. Still verified=False: only
# the overview is confirmed (no app version, no charge-detail dump yet), so it
# stays read-only and carries no nav_reads.
_CUPRA = BrandPreset(
    brand="cupra",
    package="com.cupra.mycupra",
    verified=False,
    verified_app_version=None,
    fields=(
        FieldSelector(target="battery_soc", unit_re=r"^%$", parse="percent"),
        FieldSelector(target="electric_range_km", unit_re=r"^(?:KM|km)$", parse="int_km"),
        FieldSelector(
            target="doors_locked",
            label_re=r"(?:Vehicle\s+(?:un)?locked|Fahrzeug\s+(?:ent|ver)riegelt)",
            value_from="self",
            parse="bool_locked",
        ),
        FieldSelector(
            target="ignition_on",
            label_re=r"(?:Engine\s+(?:on|off)|Motor\s+(?:an|aus))",
            value_from="self",
            parse="bool_ignition",
        ),
    ),
    overlays=(_SEEDED_POWERSAVE,),
    rate_limit_banners=(_RATE_LIMIT_BANNER,),
    # "Last updated: 1 Minute ago" — _SYNC_AGE_RE already covers "Updated … ago".
    sync_age_re=_SYNC_AGE_RE,
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
    if parse == "hm_minutes":
        # v2.26.0 (C9, ckomma-grounded) — the charge-detail remaining-time line:
        # "2 hours and 15 minutes" / "2 Stunden und 15 Minuten" / "1:45 h" /
        # "noch 90 min". Return whole minutes.
        m = re.search(
            r"(\d{1,2})\s*(?:Stunden?|hours?)\s*(?:und\s*|and\s*)?(\d{1,2})?\s*"
            r"(?:Minuten?|minutes?)?",
            raw, re.I,
        )
        if m and re.search(r"Stunden?|hours?", raw, re.I):
            return int(m.group(1)) * 60 + int(m.group(2) or 0)
        m = re.search(r"(\d{1,2}):(\d{2})\s*h", raw, re.I)
        if m:
            return int(m.group(1)) * 60 + int(m.group(2))
        m = re.search(r"(\d{1,4})\s*min", raw, re.I)
        if m:
            return int(m.group(1))
        return None
    if parse == "bool_locked":
        # v2.26.0 (#968) — "Vehicle unlocked" / "Fahrzeug entriegelt" is False;
        # "Vehicle locked" / "verriegelt" / "geschlossen" is True. Check the
        # negative first so "unlocked" never matches the "locked" substring.
        if re.search(r"(?:unlock|entriegel|entsperr|offen|geöffnet)", raw, re.I):
            return False
        if re.search(r"(?:lock|verriegel|gesperrt|geschlossen|secure)", raw, re.I):
            return True
        return None
    if parse == "bool_ignition":
        # v2.26.0 (#968) — "Engine on" / "Motor an" / "Zündung an" is True.
        if re.search(r"(?:Engine|Motor|Zündung|Ignition)\s+(?:on|an|ein)\b", raw, re.I):
            return True
        if re.search(r"(?:Engine|Motor|Zündung|Ignition)\s+(?:off|aus)\b", raw, re.I):
            return False
        return None
    return raw


# The logical write actions the channel understands, mapped to the coordinator
# command names. Only actions listed here can ever be dispatched.
ACTION_TO_COMMAND: dict[str, str] = {
    "start_climate": "command_start_climate",
    "stop_climate": "command_stop_climate",
    "start_charging": "command_start_charging",
    "stop_charging": "command_stop_charging",
}
