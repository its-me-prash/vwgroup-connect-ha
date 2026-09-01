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
    # v4.4.0 — geometric fallback for a value the app renders with NO label of
    # any kind. The climate detail's target temperature is the case: it is a
    # bare number drawn in the middle of the temperature dial, with no
    # resource-id, no description and nothing next to it to anchor on. Names
    # the container's resource-id; the value taken is the numeric text node
    # inside it that sits nearest the container's horizontal centre.
    centre_of_rid: str | None = None
    # v4.4.0 (#968, live 4.3.2 dump) — a settings switch carries its state in
    # the node's ``checked`` attribute, not in any text: the row's text says
    # what the switch IS ("Window heating"), never whether it is on. Names the
    # switch's resource-id; the value resolves to the literal "true"/"false",
    # which ``bool_switch`` turns into a real boolean.
    checked_of_rid: str | None = None
    # When matched via ``label_re``, where the value text comes from:
    #   "self"    → the label node's own text (e.g. "Ladung 74 %")
    #   "sibling" → the next sibling node's text (label and value are separate)
    value_from: str = "self"
    # Turns the raw on-screen text into the typed value. Defaults to a plain
    # string; the channel applies the field's own coercion on top.
    parse: str = "str"  # str, percent, int_km, range_km, bool_charging, kw, bool_locked, bool_ignition, hm_minutes


@dataclass(frozen=True)
class ActionSelector:
    """How to find a button to tap for a write action."""

    action: str  # logical action name, e.g. "start_climate"
    resource_id: str | None = None
    content_desc_re: str | None = None
    label_re: str | None = None
    # Some actions need to navigate to a screen first (tab labels, in order).
    nav_labels: tuple[str, ...] = ()
    # v4.4.0 — scroll the current screen up before looking for this control.
    # The MEB overview puts Vehicle Health and Settings below the fold, so
    # without this the walk correctly refuses to tap a control it cannot see,
    # and correctly never gets there either.
    scroll_first: bool = False
    # v4.4.0 — tap a point INSIDE the matched node rather than its centre,
    # given as (x, y) fractions of the node's own box. The map is the case
    # that needs it: the parked-car marker is not in the accessibility tree at
    # all, so the only way to open it is to tap where the app draws it inside
    # the map view. A fraction is device-independent; a pixel is not.
    tap_fraction: tuple[float, float] | None = None


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

    v4.4.0 — some values sit more than one tap deep (the MEB/ID app keeps the
    odometer on a Vehicle Health screen and the parking position behind
    navigation → share). ``steps`` generalises ``tile`` to an ordered PATH of
    taps; ``tile`` remains the one-step spelling and is used when ``steps`` is
    empty. ``back_presses`` says how many BACKs return to the overview, so a
    deep path does not leave the app parked on a sub-screen for the next poll.

    ``opt_in`` names the user opt-in that unlocks this path. Every group is OFF
    by default because each one taps the app; ``charge_detail`` is the original
    C9 option, deeper paths get their own so enabling a shallow read never
    silently starts a deep walk.
    """

    name: str
    values: tuple["FieldSelector", ...]  # values to read on the detail screen
    tile: ActionSelector | None = None   # single-tap spelling of ``steps``
    steps: tuple[ActionSelector, ...] = ()  # ordered taps, overview → detail
    back_presses: int = 1
    opt_in: str = "charge_detail"

    @property
    def path(self) -> tuple[ActionSelector, ...]:
        """The taps to walk, overview → detail. Never empty for a valid preset."""
        if self.steps:
            return self.steps
        return (self.tile,) if self.tile is not None else ()


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
    # v4.4.0 — the app's OWN up/close controls, in preference order. The nav
    # walk taps one of these to come back instead of pressing Android's global
    # BACK, which is not bounded by the app: from a shallow navigation stack it
    # can leave it entirely and the next poll then finds a launcher instead of
    # a car. Empty ⇒ BACK, as before.
    up_controls: tuple[ActionSelector, ...] = ()
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
                # #968: a Mk8 on imperial units narrates "14 miles". Capture the
                # number AND the unit into one group so ``range_km`` can convert
                # miles -> km and never mislabel 14 miles as 14 km.
                r"\D*(\d{1,4}\s*(?:km\b|[Kk]ilomet\w*|miles?\b|mi\b|[Mm]eilen?))"
            ),
            label_re=r"^(?:Batteriereichweite|Battery range|Electric range|Reichweite|Range)$",
            value_from="sibling",
            parse="range_km",
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
        # NOTE (#968, 4.3.2): the MEB/ID overview no longer carries a total
        # odometer at all — it shows a "Driving data" tile with the LAST trip.
        # That is why the odometer moved to the Vehicle Health nav-read below;
        # this overview selector stays for the layouts that still narrate it.
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
        # ── v4.4.0 (#968) — We Connect 4.3.2 / MEB (ID.3, ID.4, ID.5) ────────
        #
        # NOT VERIFIED IN-HOUSE: our reference car is a Golf GTE. The overview
        # selectors below come from 4.3.2 accessibility trees reported by users
        # in #968; the deeper paths (Vehicle Health, Settings, climate detail,
        # parking position) are modelled on an MEB layout documented elsewhere
        # in the open-source ecosystem, not on a tree we captured. Either way
        # they are READS only — no write action is inferred from a tree we have
        # not confirmed, because a wrong read is a wrong number while a wrong
        # tap is a physical action on a real car. They are additive: each fires
        # only on a screen that carries the 4.3.2 wording, so a 4.2.1 / metric
        # setup keeps resolving through the selectors above.
        #
        # 4.3.2 merges state and value into ONE label per tile, e.g.
        #   "Charging status. Battery charge level: 79 per cent. Charging stopped"
        # The generic ``battery_soc`` / ``electric_range_km`` selectors above
        # already capture their numbers out of those sentences; what needs its
        # own selector is the trailing STATE phrase, which would otherwise be
        # stored as the whole sentence.
        #
        # NOTE on where that sentence actually lives: on the live 4.3.2 Mk8
        # overview it does NOT appear at all — the overview carries range,
        # climate, lock, horn, departure times and a last-trip tile, and the
        # charge sentence is on the charge-detail sheet behind the range tile
        # (read there by the ``charge_detail`` nav below). These two stay for
        # the layouts that do narrate it on the main screen.
        FieldSelector(
            target="charging_state",
            content_desc_re=(
                r"Charging\s*status\b.*?\.\s*"
                r"(Charging\s*(?:stopped|paused|complete[d]?|active)?"
                r"|Currently\s*charging"
                r"|Not\s*(?:charging|connected)|Ready\s*to\s*charge)\s*\.?\s*$"
            ),
            parse="str",
        ),
        # Lock state. #968 (plainmad, live 4.3.2 dump) — the tile narrates it as
        # "Vehicle. Locked. Open details", i.e. sentence fragments, NOT "Vehicle
        # is locked": the earlier pattern matched nothing at all on a real
        # screen. Accept both spellings and the German build. ``bool_locked``
        # checks the negative first, so "Unlocked" cannot match the "locked"
        # substring inside it.
        FieldSelector(
            target="doors_locked",
            content_desc_re=(
                r"(?:Vehicle|Fahrzeug)[.:]?\s*(?:is\s*|ist\s*)?"
                r"((?:un)?locked|(?:ver|ent)riegelt)\b"
            ),
            parse="bool_locked",
        ),
        # Climate tile narration. ``climateTile`` is the stable resource-id in
        # the reported trees; the narration fallback covers builds that do not
        # expose it.
        FieldSelector(
            target="climatisation_state",
            resource_id="climateTile",
            content_desc_re=(
                r"(?:Climate|Air\s*conditioning|Klima(?:tisierung)?)[^.]*?\.\s*"
                r"([^.]*(?:on|off|running|stopped|active|ein|aus|läuft)[^.]*)"
            ),
            parse="str",
        ),
        FieldSelector(
            target="climatisation_active",
            resource_id="climateTile",
            content_desc_re=(
                r"(?:Climate|Air\s*conditioning|Klima(?:tisierung)?)[^.]*?\.\s*"
                r"([^.]*(?:on|off|running|stopped|active|ein|aus|läuft)[^.]*)"
            ),
            parse="bool_climate",
        ),
    ),
    # v2.26.0 — WRITES QUARANTINED. The previous single-tap actions were wrong:
    # ckomma proves We Connect needs a TWO-STEP nav (overview tile → detail
    # screen → action button) that our do_action never did, so climate/charge
    # commands could only ever fail with "control not found". Rather than ship
    # command entities that never work, this preset carries NO actions (so
    # ``writable`` is False and no command entities spawn) until the 2-step nav
    # is confirmed on a real device. Reads are unaffected.
    #
    # #968 (plainmad, 4.3.2 "while charging" + "climate active" dumps) — the two
    # write controls are now LOCATED (not yet wired, because a wrong tap is a
    # physical action on the car — they move into ``actions`` only once confirmed
    # on-device and the preset is marked ``verified``):
    #   • charge stop/start = the detail-sheet control whose content-desc flips
    #     "Start charging" ⇄ "Stop charging" (bounds [85,1278][635,1380]).
    #   • climate stop/start = the CTA whose resource-id itself flips
    #     ``cta_start`` (text "Start") ⇄ ``cta_stop`` (text "Stop").
    # Both are reached via the existing open_charge_detail / open_climate_detail
    # nav. NOT on the sheet at all on 4.3.2: charge target-% and live kW power.
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
                # #968 (plainmad, live 4.3.2 dump) — on 4.3.2 the charge STATE
                # is not on the overview at all: the whole sentence, state and
                # level together, lives on this detail sheet, in the same
                # ``rangeArcBatterySoc`` node's description ("Charging status.
                # Battery charge level: 79 per cent. Charging stopped"). Read
                # here, or a car's charging flag never updates from a real
                # screen. The overview selectors stay for layouts that do
                # narrate it there.
                # Matched on the description only, deliberately: that node's
                # ``text`` is the short "Battery 79 %" and a resource-id match
                # would resolve to it first, so the state sentence would never
                # be reached.
                FieldSelector(
                    target="charging_state",
                    content_desc_re=(
                        r"Charging\s*status\b.*?\.\s*"
                        r"(Charging\s*(?:stopped|paused|complete[d]?|active)?"
                r"|Currently\s*charging"
                        r"|Not\s*(?:charging|connected)|Ready\s*to\s*charge)\s*\.?\s*$"
                    ),
                    parse="str",
                ),
                FieldSelector(
                    target="is_charging",
                    content_desc_re=r"(Charging\s*status\b.*)",
                    parse="bool_charging",
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
        # ── v4.4.0 (#968) — deeper 4.3.2 paths, SEEDED like the fields above ──
        #
        # Each is opt-in under its OWN option, so enabling the charge-detail
        # read never silently starts a multi-tap walk, and every path states how
        # many BACKs return to the overview.
        NavReadSelector(
            name="vehicle_health",
            # 4.3.2 dropped the total odometer from the overview (it shows the
            # last trip instead), so the mileage and the service countdown are
            # only reachable on the Vehicle Health report — and on the MEB
            # layout that entry point sits BELOW the fold, hence the scroll.
            # The report labels its values and puts the number in the next node
            # ("Total distance" → "27,886 km"), with no id of its own.
            steps=(
                ActionSelector(
                    action="open_vehicle_health",
                    content_desc_re=(
                        r"^(?:Vehicle\s*Health\s*Report|Fahrzeug(?:zustands)?"
                        r"bericht)\b"
                    ),
                    scroll_first=True,
                ),
            ),
            values=(
                FieldSelector(
                    target="odometer_km",
                    label_re=r"^(?:Total\s*distance|Gesamt(?:strecke|kilometer))$",
                    value_from="sibling",
                    parse="range_km",
                ),
                FieldSelector(
                    target="service_due_in_days",
                    label_re=r"^(?:Next\s*service|Nächster\s*Service)$",
                    value_from="sibling",
                    parse="days",
                ),
                # The same report carries the oil interval one row down, in the
                # same label-then-value shape.
                FieldSelector(
                    target="oil_service_due_in_days",
                    label_re=r"^(?:Next\s*oil\s*service|Nächster\s*Ölwechsel)$",
                    value_from="sibling",
                    parse="days",
                ),
            ),
            back_presses=1,
            opt_in="vehicle_health",
        ),
        NavReadSelector(
            name="vehicle_settings",
            # The charge limit lives on the vehicle Settings screen, not behind
            # the range tile, on this layout. Same below-the-fold entry point as
            # Vehicle Health.
            steps=(
                ActionSelector(
                    action="open_vehicle_settings",
                    content_desc_re=r"^(?:Settings|Einstellungen)\b",
                    scroll_first=True,
                ),
            ),
            values=(
                FieldSelector(
                    target="target_soc",
                    label_re=(
                        r"^(?:Charg(?:e|ing)\s*(?:up\s*to|target|limit)"
                        r"|Ladeziel|Laden\s*bis)\b"
                    ),
                    value_from="sibling",
                    parse="percent",
                ),
            ),
            back_presses=1,
            opt_in="vehicle_health",
        ),
        NavReadSelector(
            name="climate_detail",
            steps=(
                ActionSelector(
                    action="open_climate_detail",
                    resource_id="climateTile",
                    content_desc_re=(
                        r"(?:Climate|Air\s*conditioning|Klima(?:tisierung)?)"
                    ),
                ),
            ),
            values=(
                # The target temperature is drawn in the middle of the
                # temperature dial as a bare number: no id, no description, no
                # neighbouring label. Geometry is the only handle it has.
                FieldSelector(
                    target="target_temperature",
                    centre_of_rid="clima_compose_view",
                    parse="temp_c",
                ),
                # The outside temperature is the one °C reading on this screen
                # that carries its unit, so the unit is the anchor. It sits
                # inside ``outside_temperature_layout`` and reads as
                # "<place>: 22°C" on a live screen, so the number is taken from
                # the unit, never from the text around it.
                FieldSelector(
                    target="outside_temp",
                    label_re=r"(-?\d{1,2}(?:[.,]\d+)?\s*°\s*[CF]?)",
                    value_from="self",
                    parse="temp_c",
                ),
                # #968 — the switch state is read from two possible shapes, most
                # reliable last (read_selectors keeps the last non-None). Older /
                # other layouts expose a checkable ``*_toggle`` whose ``checked``
                # is the state; but plainmad's live 4.3.2 "climate active" dump
                # shows the toggle row is ``clima_``-prefixed, NOT checkable, and
                # carries ``checked="false"`` even while air conditioning is on —
                # there the real state is the sibling ``*_description`` text
                # ("Active" / "Off"). Try ``checked`` first, then let the
                # description win (bool_climate maps Active/On→True, Off→False), so
                # both layouts read correctly.
                FieldSelector(
                    target="window_heating_enabled",
                    checked_of_rid="window_heating_toggle",
                    parse="bool_switch",
                ),
                FieldSelector(
                    target="window_heating_enabled",
                    resource_id="window_heating_description",
                    parse="bool_climate",
                ),
                FieldSelector(
                    target="climatisation_active",
                    checked_of_rid="air_conditioning_toggle",
                    parse="bool_switch",
                ),
                FieldSelector(
                    target="climatisation_active",
                    resource_id="air_conditioning_description",
                    parse="bool_climate",
                ),
            ),
            back_presses=1,
            opt_in="climate_detail",
        ),
        NavReadSelector(
            name="parking_position",
            # #923 / #968 — a VW EU car read through the EU Data Act portal has
            # NO position data point, and the app draws the parked car as a map
            # with no coordinate text, so both of our other paths are structurally
            # blind here. The app's own share sheet is not: sharing the parking
            # spot renders a Google Maps link whose preview text carries the
            # coordinates. We only READ that preview — nothing is sent anywhere.
            #
            # The middle step is the awkward one: the parked-car marker is not
            # in the accessibility tree at all, so there is no node to match.
            # What IS in the tree is the map view itself, and "Find vehicle"
            # centres the marker in its upper half — so we tap a fraction of
            # the map's own box rather than a node.
            steps=(
                ActionSelector(
                    action="open_map_tab",
                    resource_id="cat_nav_map_tab_navigation",
                    content_desc_re=r"^(?:Map|Navigation|Karte)\b",
                ),
                ActionSelector(
                    action="find_vehicle",
                    content_desc_re=r"^(?:Find\s*vehicle|Fahrzeug\s*finden)$",
                ),
                ActionSelector(
                    action="open_parking_marker",
                    content_desc_re=r"^(?:Google\s*Map|Google\s*Karte)$",
                    tap_fraction=(0.5, 0.43),
                ),
                ActionSelector(
                    action="share_parking_position",
                    label_re=r"^(?:Share|Teilen)$",
                ),
            ),
            values=(
                FieldSelector(
                    target="latitude",
                    label_re=r"(https?://\S*(?:google\.[a-z.]+/maps|goo\.gl/maps)\S*)",
                    value_from="self",
                    parse="maps_lat",
                ),
                FieldSelector(
                    target="longitude",
                    label_re=r"(https?://\S*(?:google\.[a-z.]+/maps|goo\.gl/maps)\S*)",
                    value_from="self",
                    parse="maps_lon",
                ),
            ),
            back_presses=4,
            opt_in="parking_position",
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
    # v4.4.0 — We Connect's own close/up controls, so a nav walk never presses
    # Android BACK out of the app. Ordered from the general Compose up-button
    # to the two screens that name their own.
    up_controls=(
        ActionSelector(action="up", resource_id="vwd_navigation_button"),
        ActionSelector(action="up", resource_id="vehicleHealthBack"),
        ActionSelector(action="up", resource_id="climatisationSettingsLeading"),
        # #968 (plainmad, live 4.3.2 dump) — the charge detail is a bottom
        # sheet, and its way out is a described Close control rather than any
        # of the ids above.
        ActionSelector(action="up", content_desc_re=r"^Close(?:\s*sheet)?$"),
    ),
    # v4.4.0 — the overview is the screen that carries both tiles. Used to stop
    # the return walk as soon as we are actually home, rather than pressing a
    # fixed number of times and hoping.
    screen_anchor=FieldSelector(target="_overview", resource_id="rangeTile"),
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
# v4.4.0 — the comma is a thousands separator too ("27,886 km" on an English
# build), and without it that odometer read back as 27. A group must be exactly
# three digits and not run on into a fourth, so a decimal comma ("12,5") still
# cannot match. Every consumer of this helper is an integer quantity
# (percent / int_km / range_km), so widening it here cannot reach a decimal.
_GROUPED_THOUSANDS_RE = re.compile(r"-?\d{1,3}(?:[\s.,]\d{3})+(?!\d)")


def _first_int(text: str) -> int | None:
    if not text:
        return None
    # Collapse a grouped-thousands number first, otherwise the first-digit-run
    # regex below truncates "27 886 km" to 27 (ckomma #7, an odometer read).
    gm = _GROUPED_THOUSANDS_RE.search(text)
    if gm:
        digits = re.sub(r"[\s.,]", "", gm.group())
        try:
            return int(digits)
        except ValueError:  # pragma: no cover - regex guarantees digits
            pass
    m = _FIRST_INT_RE.search(text)
    return int(m.group()) if m else None


# v4.4.0 — coordinate pairs as they appear in a shared Google Maps link. Tried
# in order; the first that hits wins. Latitude is bounded to ±90 and longitude
# to ±180 by ``_maps_latlon`` so a zoom level or a place id can never be read as
# a coordinate.
_MAPS_LATLON_RES = (
    re.compile(r"[!]3d(-?\d+\.\d+)[!]4d(-?\d+\.\d+)"),
    re.compile(r"/place/(-?\d+\.\d+),\s*(-?\d+\.\d+)"),
    re.compile(r"[/@](-?\d+\.\d+),\s*(-?\d+\.\d+)"),
    re.compile(r"[?&](?:q|ll|daddr|destination)=(-?\d+\.\d+),\s*(-?\d+\.\d+)"),
)


def _maps_latlon(raw: str) -> tuple[float, float] | None:
    """Pull a (lat, lon) pair out of a Google Maps URL, or None."""
    for rx in _MAPS_LATLON_RES:
        m = rx.search(raw)
        if not m:
            continue
        lat = float(m.group(1))
        lon = float(m.group(2))
        if -90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0:
            return lat, lon
    return None


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
    if parse == "range_km":
        # #968 — the app narrates the range unit in words, and a car on imperial
        # units reads "14 miles" while a metric one reads "253 Kilometer". The
        # selector captures the number AND the unit, so convert miles -> km here
        # instead of storing 14 and mislabelling it km. (kgroshert/plainmad Mk8.)
        val = _first_int(raw)
        if val is None:
            return None
        if re.search(r"mile|meile|\bmi\b", raw, re.I):
            return round(val * 1.60934)
        return val
    if parse == "bool_charging":
        # v4.4.0 — the MEB/ID app 4.3.2 narrates state and level in ONE label:
        # "Charging status. Battery charge level: 79 per cent. Charging stopped".
        # "Charging" appears in that sentence even when the car is NOT charging,
        # so the explicit stopped/paused wording has to win over the bare verb.
        if re.search(
            r"(?:Charging\s*(?:stopped|paused|complete[d]?)|Ladevorgang\s*"
            r"(?:beendet|gestoppt|pausiert)|Nicht\s*(?:geladen|verbunden)"
            r"|Not\s*(?:charging|connected))",
            raw, re.I,
        ):
            return False
        return bool(re.search(r"(?:Lädt|Wird geladen|Charging)", raw, re.I))
    if parse == "days":
        # #968 (plainmad, live 4.3.2 dump) — the Vehicle Health report writes
        # the service countdown as "71 days / 12,100 mi": a day count AND a
        # distance in one string. Taking the first number found reads 12,100
        # (the grouped-thousands mileage) and then fails the range check, so
        # the countdown never appeared. Bind to the unit instead.
        m = re.search(r"(\d{1,4})\s*(?:days?|Tage?n?)\b", raw, re.I)
        if m is None:
            return None
        val = int(m.group(1))
        return val if 0 <= val <= 3650 else None
    if parse == "bool_switch":
        # Straight from a node's ``checked`` attribute, so only the two literal
        # values are accepted; anything else is a mis-match, not a False.
        if raw == "true":
            return True
        if raw == "false":
            return False
        return None
    if parse == "bool_climate":
        # v4.4.0 (#968) — the climate tile narrates its own state; "off",
        # "stopped" and "aus" are the negatives, and they are checked first so
        # "Climate control off" cannot match the positive verb in front of it.
        if re.search(
            r"(?:\boff\b|stopped|not\s*running|\baus\b|beendet|gestoppt)", raw, re.I
        ):
            return False
        if re.search(r"(?:\bon\b|running|active|\bein\b|läuft|aktiv)", raw, re.I):
            return True
        return None
    if parse == "temp_c":
        # A temperature reading off a climate screen: "22°C", "21,5 °C", "70°F".
        m = re.search(r"(-?\d+(?:[.,]\d+)?)\s*°?\s*([CF])?", raw)
        if not m:
            return None
        degrees = float(m.group(1).replace(",", "."))
        if (m.group(2) or "").upper() == "F":
            degrees = (degrees - 32.0) * 5.0 / 9.0
        return round(degrees, 1)
    if parse in ("maps_lat", "maps_lon"):
        # v4.4.0 — parking position off a shared map link. The app draws the
        # parking spot as a map with no coordinate text, but its share sheet
        # renders a Google Maps URL that carries the coordinates, and the share
        # preview is readable in the accessibility tree. Accepted spellings:
        #   /place/48.208174,16.373819      /maps?q=48.208174,16.373819
        #   /@48.208174,16.373819,17z       !3d48.208174!4d16.373819
        pair = _maps_latlon(raw)
        if pair is None:
            return None
        return pair[0] if parse == "maps_lat" else pair[1]
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
