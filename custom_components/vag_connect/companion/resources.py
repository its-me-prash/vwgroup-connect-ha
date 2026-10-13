# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Read battery, climate and Settings labels from the installed app's compiled translation tables.

Resource names are stable across locales; their values come from the phone,
not a translated word list. Only simple string entries are read. No APK code,
account data, network credentials, or third-party decoder is needed at runtime.
"""
from __future__ import annotations

import re
import struct

from .departure import TIMER_CANCEL, TIMER_SAVE, departure_rows
from .presets import coerce
from .screen import UiNode

StringResources = dict[str, set[str]]

# Single labels read besides the range tile and charge sheet families.
# The app's alert titles when the car refuses more requests: its daily power
# budget is used up (backend error 4295) or the backend answered HTTP 429.
_LIMIT_KEYS = (
    "alert_daily_power_budget_title",
    "dialog_maxrequests_headline",
    "dialog_maxrequest_bff_error_headline",
)
# The power-budget alert is the app's own (CapabilityStatusAlertDelegate, car
# capability status 1010): it is shown instead of sending the request. Its
# English title reads the same as the backend's 4295 headline, so only its
# footer tells the two apart. The backend dialogs' texts mean a request did go
# out (4295 / TooManyRequests, and the HTTP 429 lockout).
POWER_BUDGET_TITLE = "alert_daily_power_budget_title"
POWER_BUDGET_FOOTER = "alert_daily_power_budget_footer"
_BACKEND_LIMIT_TEXTS = (
    "dialog_maxrequests_text",
    "dialog_maxrequest_bff_error_headline",
    "dialog_maxrequest_bff_error_text",
)
# The overview toolbar's "Synchronised %s ago" line and its parts (#968): the
# frame, its "just now" and "too old" forms, and the duration plurals that fill
# the %s. Plurals are stored per quantity as ``name#one`` / ``name#other`` ...
SYNC_LAST_UPDATE = "acc_vehicle_tab_value_vehicledata_last_update"
SYNC_JUST_NOW = "acc_vehicle_tab_value_vehicledata_just_now"
SYNC_TOO_OLD = "common_timestamp_too_old"
# The generic alert the app shows after a refused request ("Vehicle data
# unavailable"), closed with BACK like the request-limit alert before it.
DATA_UNAVAILABLE = "dialog_error_vehicledata_notavailable_headline"
SYNC_PLURALS = (
    "duration_minutes_long_pluralised",
    "duration_hours_long_pluralised",
    "duration_days_long_pluralised",
)
# The Air Conditioning sheet, its mode picker and its Settings sheet, as the
# 4.3.2 APK builds them (ClimaViewModel, ClimaItemsMapper, ModeSelection).
CLIMA_LOW = "clima_temperature_low"  # the dial's "LO" (15.5)
CLIMA_HIGH = "clima_temperature_high"  # the dial's "HI" (30.0)
# The "°" drawn after every other dial number. The app has no Fahrenheit key:
# the dial is 15.5-30.0 °C only (GetAllTemperaturesUseCase, 4.6.4).
CLIMA_DEGREE = "unit_degree_sign"
CLIMA_ACTIVE = ("air_conditioning_screen_active", "common_activated")
CLIMA_OFF = "vehiclescreen_airconditioning_deactivated"
CLIMA_AUTOMATIC = "common_automatic_abbreviation"
CLIMA_MINUTES = "duration_minutes"  # " • %s min" after an active function
# The mode picker's two rows, which the sheet's mode row also shows as title.
CLIMA_MODE_AC = "common_airconditioning"
CLIMA_MODE_WINDOW_HEATING = "window_heating_abbreviation"
# The Settings sheet's Zones row and the values it shows: one zone by name,
# "%s zones" for several, nothing for none (ClimaItemsMapper.b).
CLIMA_ZONES = "common_airconditionedzones"
CLIMA_ZONES_SEVERAL = "vehiclesettingsscreen_airconditionedzones_options_multiplezones"
CLIMA_ZONE_KEYS = {
    "vehiclesettingsscreen_airconditionedzones_options_driverszone": "climate_zone_front_left",
    "vehiclesettingsscreen_airconditionedzones_options_passengerzone": "climate_zone_front_right",
    "vehiclesettingsscreen_airconditionedzones_options_leftrearseatzone": "climate_zone_rear_left",
    "vehiclesettingsscreen_airconditionedzones_options_rightrearseatzone": "climate_zone_rear_right",
}
_CLIMA_KEYS = (
    CLIMA_LOW, CLIMA_HIGH, CLIMA_DEGREE, *CLIMA_ACTIVE, CLIMA_OFF, CLIMA_AUTOMATIC, CLIMA_MINUTES,
    CLIMA_MODE_AC, CLIMA_MODE_WINDOW_HEATING, CLIMA_ZONES, CLIMA_ZONES_SEVERAL,
    *CLIMA_ZONE_KEYS,
)
# Switches on vehicle Settings, read into the field the VW cloud parser fills
# for the same setting (vw_eu: autoUnlockPlugWhenCharged).
SETTINGS_SWITCHES = {
    "vehiclesettingsscreen_automaticplugunlock": ("auto_unlock_when_charged", True, False),
}
# Vehicle Health Report subheads, each followed by its value line: a distance,
# or "<days> <word> / <distance>" for the service countdowns.
HEALTH_ROWS = {
    "screen_vehiclehealth_subhead_totaldistance": ("odometer_km", None),
    "screen_vehiclehealth_subhead_nextinspection": ("service_km", "service_due_in_days"),
    "screen_vehiclehealth_subhead_oil_service": ("oil_service_km", "oil_service_due_in_days"),
    "screen_vehiclehealth_subhead_adblue_level": ("adblue_range_km", None),
}
# The report's warning header ("No issues found" / "Issues found") and its
# categories, each a row tagged ``warningName<Category>`` in the 4.3.2 APK.
HEALTH_NO_ISSUES = "screen_vehiclehealth_overview_no_issues"
HEALTH_ISSUES = "screen_vehiclehealth_overview_issues_found_generic"
# Overview tiles narrate "<label>. <value>. <hint>" (Vehicle. Locked. Open details).
TILE_LOCK = "acc_vehicle_tab_label_lock_unlock_vehicle"
TILE_LOCKED = "acc_vehicle_tab_value_lock_unlock_vehicle_state_locked"
TILE_UNLOCKED = "acc_vehicle_tab_value_lock_unlock_vehicle_state_unlocked"
TILE_CLIMA = "acc_vehicle_tab_clima_tile_label"
TILE_CLIMA_ON = "acc_vehicle_tab_clima_tile_value_all_clima_on"
TILE_CLIMA_OFF = "acc_vehicle_tab_clima_tile_value_all_clima_off"
_TILE_KEYS = (TILE_LOCK, TILE_LOCKED, TILE_UNLOCKED, TILE_CLIMA, TILE_CLIMA_ON, TILE_CLIMA_OFF)
# The Driving data screen (the app's "snowshoe" trip statistics): the overview
# tile, the two trip cards' titles, their row labels and the units the values
# carry. The cyclic card is titled by drivetrain; every spelling is accepted.
DRIVING_TILE = "acc_vehicle_tab_label_driving_data"
_RTS = "volkswagen_acc_cat_snowshoe_rts_"
_RTS_UNIT = "volkswagen_cat_snowshoe_rts_"
TRIP_CARDS = {
    "last_trip": (_RTS + "lastSingleTripLabel", _RTS_UNIT + "lastSingleTripTileTitle"),
    "refuel_trip": (
        _RTS + "cyclicTripsScreenheaderLabelHybrid", _RTS + "cyclicTripsScreenheaderEV",
        _RTS + "cyclicTripsScreenheaderCombustion", _RTS_UNIT + "cyclicTripsHybrid",
        _RTS_UNIT + "cyclicTripsEV", _RTS_UNIT + "cyclicTripsCombustion",
    ),
}
TRIP_ROWS = {
    _RTS + "distanceDrivenLabel": "distance",
    _RTS + "consumptionLabel": "consumption",
    _RTS + "averageSpeedLabel": "speed",
    _RTS + "drivingTimeLabel": "time",
}
TRIP_UNITS = {
    _RTS_UNIT + "unitKm": ("distance", 1.0),
    _RTS_UNIT + "unitMiles": ("distance", 1.609344),
    _RTS_UNIT + "speedKmh": ("speed", 1.0),
    _RTS_UNIT + "speedMph": ("speed", 1.609344),
    _RTS_UNIT + "unitKwhPer100Km": ("electric", 1.0),
    _RTS_UNIT + "unitLiterPer100Km": ("fuel", 1.0),
}
DURATION_HOURS = "duration_hours"
_TRIP_KEYS = (
    DRIVING_TILE, *(k for keys in TRIP_CARDS.values() for k in keys), *TRIP_ROWS,
    *TRIP_UNITS, DURATION_HOURS,
)
# Charging-location rows and their timer/settings pages.
CHARGING_PLURAL = "active_chargingtimes_option"
_CHARGING_KEYS = (
    "common_charging", "common_status_active", "screen_charging_settings_title",
    "screen_charging_settings_relatedlocation", "vehiclesettingsscreen_reducedchargingspeed",
    "vehiclesettingsscreen_automaticplugunlock",
    "departure_timer_subscreen_every_day", "departure_timer_subscreen_weekdays",
    "departure_timer_subscreen_weekend",
    *(f"departure_timer_subscreen_{day}" for day in ("mon", "tue", "wed", "thu", "fri", "sat", "sun")),
    *(f"weekday_{day}" for day in ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")),
)
# Overview tiles opened by a nav read, by their translated label.
DEPARTURE_TILE = "acc_vehicle_tab_label_departure_times"
_SINGLE_KEYS = frozenset({
    "acc_common_hint_details", "acc_vehicle_tab_label_settings", *_LIMIT_KEYS,
    POWER_BUDGET_FOOTER, *_BACKEND_LIMIT_TEXTS,
    DEPARTURE_TILE, TIMER_SAVE, TIMER_CANCEL, *_TRIP_KEYS,
    SYNC_LAST_UPDATE, SYNC_JUST_NOW, SYNC_TOO_OLD, DATA_UNAVAILABLE, *_CLIMA_KEYS,
    *HEALTH_ROWS, HEALTH_NO_ISSUES, HEALTH_ISSUES, *SETTINGS_SWITCHES,
    *_TILE_KEYS, *_CHARGING_KEYS,
})
# Android's plural quantity attributes (``android:^attr-private`` ids).
_QUANTITIES = {
    0x01000004: "other", 0x01000005: "zero", 0x01000006: "one",
    0x01000007: "two", 0x01000008: "few", 0x01000009: "many",
}


def _pool(data: bytes, offset: int) -> list[str]:
    header, size = struct.unpack_from("<HI", data, offset + 2)
    count, _, flags, start = struct.unpack_from("<IIII", data, offset + 8)
    if offset + size > len(data) or count > size // 4:
        raise ValueError("invalid string pool")
    strings = []
    for index in range(count):
        relative = struct.unpack_from("<I", data, offset + header + index * 4)[0]
        pos = offset + start + relative
        if flags & 0x100:  # UTF-8: character count, then byte count.
            pos += 2 if data[pos] & 0x80 else 1
            length = data[pos]
            pos += 1
            if length & 0x80:
                length = ((length & 0x7f) << 8) | data[pos]
                pos += 1
            strings.append(data[pos:pos + length].decode("utf-8"))
        else:
            length = struct.unpack_from("<H", data, pos)[0]
            pos += 2
            if length & 0x8000:
                length = ((length & 0x7fff) << 16) | struct.unpack_from("<H", data, pos)[0]
                pos += 2
            strings.append(data[pos:pos + length * 2].decode("utf-16le"))
    return strings


def _read_plural(
    data: bytes, entry: int, end: int, keys: list[str], strings: list[str],
    out: StringResources,
) -> None:
    """One relevant plurals bag, stored as ``name#quantity`` strings."""
    es, ef, key = struct.unpack_from("<HHI", data, entry)
    name = keys[key]
    if not ef & 1 or es < 16 or entry + 16 > end or name not in (*SYNC_PLURALS, CHARGING_PLURAL):
        return
    count = struct.unpack_from("<I", data, entry + 12)[0]
    item = entry + es
    if count > 16 or item + count * 12 > end:
        raise ValueError("invalid plurals entry")
    for _ in range(count):
        quantity = _QUANTITIES.get(struct.unpack_from("<I", data, item)[0])
        if quantity is not None and data[item + 7] == 3:  # TYPE_STRING
            text = strings[struct.unpack_from("<I", data, item + 8)[0]]
            out.setdefault(f"{name}#{quantity}", set()).add(text)
        item += 12


def extract_app_strings(data: bytes) -> StringResources:
    """Decode the small relevant subset of Android's resources.arsc format.

    A malformed/unsupported table returns no labels. Complex entries (styles,
    bags) and non-string values are deliberately ignored, never interpreted as
    strings, except the relevant plurals, read per quantity. Dense,
    sparse, and 16-bit type offset tables are supported.
    """
    out: StringResources = {}
    try:
        kind, header, total = struct.unpack_from("<HHI", data)
        if kind != 2 or not header <= total <= len(data):
            return {}
        global_strings: list[str] = []
        pos = header
        while pos < total:
            kind, chunk_header, size = struct.unpack_from("<HHI", data, pos)
            if size < chunk_header or chunk_header < 8 or pos + size > total:
                return {}
            if kind == 1:
                global_strings = _pool(data, pos)
            elif kind == 0x200:  # ResTable_package
                if chunk_header < 284:
                    return {}
                types = _pool(data, pos + struct.unpack_from("<I", data, pos + 268)[0])
                keys = _pool(data, pos + struct.unpack_from("<I", data, pos + 276)[0])
                child = pos + chunk_header
                while child < pos + size:
                    ck, ch, cs = struct.unpack_from("<HHI", data, child)
                    if cs < ch or ch < 8 or child + cs > pos + size:
                        return {}
                    kind_name = types[data[child + 8] - 1] if ck == 0x201 else ""
                    if kind_name in ("string", "plurals"):
                        flags = data[child + 9]
                        count, start = struct.unpack_from("<II", data, child + 12)
                        if count > cs // 2:
                            return {}
                        for index in range(count):
                            if flags & 1:  # sparse (entry index, offset / 4)
                                relative = struct.unpack_from("<H", data, child + ch + index * 4 + 2)[0] * 4
                            elif flags & 2:
                                relative = struct.unpack_from("<H", data, child + ch + index * 2)[0]
                                if relative == 0xffff:
                                    continue
                                relative *= 4
                            else:
                                relative = struct.unpack_from("<I", data, child + ch + index * 4)[0]
                                if relative == 0xffffffff:
                                    continue
                            entry = child + start + relative
                            if entry < child + ch or entry + 8 > child + cs:
                                return {}
                            es, ef, key = struct.unpack_from("<HHI", data, entry)
                            if kind_name == "plurals":
                                _read_plural(data, entry, child + cs, keys, global_strings, out)
                                continue
                            if ef & 9 or es < 8:  # complex/compact entry
                                continue
                            name = keys[key]
                            if name not in _SINGLE_KEYS and not name.startswith(("acc_vehicle_tab_range_tile_", "acc_range_modal_")):
                                continue
                            value = entry + es
                            if value + 8 > child + cs:
                                return {}
                            if data[value + 3] == 3:  # TYPE_STRING
                                text = global_strings[struct.unpack_from("<I", data, value + 4)[0]]
                                out.setdefault(name, set()).add(text)
                    child += cs
            pos += size
    except (ValueError, IndexError, struct.error, UnicodeError):
        return {}
    return out


def _patterns(resources: StringResources, key: str) -> list[re.Pattern[str]]:
    patterns = []
    for template in sorted(resources.get(key, ())):
        # Android format placeholders: %s and %1$s. Numeric slots keep their
        # locale's digits/separators; prose can never supply a guessed number.
        parts = re.split(r"%\d*\$?s", template)
        pattern = r"(\d+(?:[.,\u00a0\u202f]\d+)*)".join(re.escape(p) for p in parts)
        patterns.append(re.compile(pattern, re.I))
    return patterns


def read_battery_resources(nodes: list[UiNode], resources: StringResources) -> dict[str, object]:
    """Match translated templates to canonical HA fields without locale tests."""
    out: dict[str, object] = {}
    values = (
        ("acc_vehicle_tab_range_tile_value_battery_level", "battery_soc", "percent", False),
        ("acc_vehicle_tab_range_tile_value_petrol_level", "fuel_level", "percent", False),
        ("acc_vehicle_tab_range_tile_value_battery_range_km", "electric_range_km", "int_km", False),
        ("acc_vehicle_tab_range_tile_value_battery_range_miles", "electric_range_km", "range_km", True),
        ("acc_vehicle_tab_range_tile_value_fuel_range_km", "combustion_range_km", "int_km", False),
        ("acc_vehicle_tab_range_tile_value_fuel_range_miles", "combustion_range_km", "range_km", True),
        ("acc_range_modal_value_charging_target_charge_level", "target_soc", "percent", False),
        ("acc_range_modal_value_charging_capacity", "charging_power_kw", "kw", False),
        ("acc_range_modal_value_charging_speed_kilometres", "charging_rate_kmh", "int_km", False),
        ("acc_range_modal_value_charging_speed_miles", "charging_rate_kmh", "range_km", True),
    )
    for key, target, parser, miles in values:
        for pattern in _patterns(resources, key):
            for node in nodes:
                match = pattern.search(node.content_desc)
                if match and match.lastindex:
                    raw = match.group(1) + (" miles" if miles else "")
                    value = coerce(parser, raw)
                    if value is not None:
                        out[target] = value
    states = (
        ("charge_level_reached", "Target charge level reached", False),
        ("charge_stopped", "Charging stopped", False),
        ("connect_charging_cable", "Not connected", False),
        ("waiting", "Waiting", False),
        ("waiting_for_charging_time", "Waiting for charging time", False),
        ("waiting_for_departure_time", "Waiting for departure time", False),
        ("currently_charging", "Currently charging", True),
        ("conservation_charging", "conservationCharging", True),
    )
    for suffix, canonical, active in states:
        for label in resources.get("acc_range_modal_value_" + suffix, ()):
            for node in nodes:
                if node.resource_id.split("/")[-1] == "rangeArcBatterySoc" and node.content_desc.rstrip(". ").casefold().endswith(label.casefold()):
                    out.update(charging_state=canonical, is_charging=active)
    # The live overview omits the SoC node but narrates charging on its tile.
    for pattern in _patterns(resources, "acc_vehicle_tab_range_tile_value_battery_currently_charging"):
        if any(pattern.search(n.content_desc) for n in nodes) and "electric_range_km" in out:
            out["is_charging"] = True
            # Without this the overview's catch-all selector hands the whole
            # tile narration to the Charging Status sensor.
            out.setdefault("charging_state", "Currently charging")
    # Each plural form is a separate named resource. The zero/one forms may
    # spell the number out; interpret the resource key, not the localized word.
    time_parts: dict[str, int] = {}
    for unit in ("hours", "minutes"):
        for form, constant in (("zero", 0), ("one", 1), ("other", None)):
            key = f"acc_vehicle_tab_range_tile_value_battery_charging_time_{unit}_pluralised_{form}"
            for pattern in _patterns(resources, key):
                for node in nodes:
                    match = pattern.search(node.content_desc)
                    if match:
                        value = constant if constant is not None else coerce("int_km", match.group(1))
                        if isinstance(value, int):
                            time_parts[unit] = value
    if time_parts:
        out["remaining_charge_time_min"] = time_parts.get("hours", 0) * 60 + time_parts.get("minutes", 0)
    mode = read_charge_mode(nodes, resources)
    if mode is not None:
        out["charge_mode"] = mode
    return out


# The range sheet's "Charging method" row (ChargeModeDescriptor in the 4.3.2
# APK): each label it shows stands for one ChargeModes$Mode wire value, the
# same value the VW cloud reports as ``chargeMode``.
CHARGE_MODE_LABEL = "acc_range_modal_label_charge_mode"
CHARGE_MODES = {
    "immediate_charging": "manual",
    "departure_time": "timer",
    "departure_time_charge_air_condition": "timerChargingWithClimatisation",
    "preferred_times": "preferredChargingTimes",
    "solar_power": "onlyOwnCurrent",
    "discharge": "immediateDischarging",
    "bidirectional_charging": "homeStorageCharging",
}


def read_charge_mode(nodes: list[UiNode], resources: StringResources) -> str | None:
    """The charge mode from "Charging method. Immediate charging. Change …"."""
    labels = _labels(resources, CHARGE_MODE_LABEL)
    if not labels:
        return None
    values = {
        label: wire
        for suffix, wire in CHARGE_MODES.items()
        for label in _labels(resources, "acc_range_modal_value_charge_mode_" + suffix)
    }
    for node in nodes:
        parts = [p.strip().casefold() for p in node.content_desc.split(". ")]
        if len(parts) >= 2 and parts[0] in labels:
            wire = values.get(parts[1].rstrip("."))
            if wire is not None:
                return wire
    return None


def find_battery_control(nodes: list[UiNode], resources: StringResources, action: str) -> UiNode | None:
    """Match a translated CTA, rejecting its app-defined disabled hint."""
    suffix = {"start_charging": "start", "stop_charging": "stop"}.get(action)
    if suffix is None:
        return None
    labels = resources.get("acc_range_modal_label_cta_" + suffix, set())
    disabled = resources.get("acc_range_modal_hint_cta_" + suffix + "_disabled", set())
    for node in nodes:
        if not node.enabled or node.tap_point is None:
            continue
        desc = node.content_desc
        if any(desc == label or desc.startswith(label + ".") for label in labels):
            if not any(hint and hint in desc for hint in disabled):
                return node
    return None


def find_battery_tile(nodes: list[UiNode], resources: StringResources) -> UiNode | None:
    """The translated range overview plus Open details proves a tile, not an arc."""
    labels = resources.get("acc_vehicle_tab_range_tile_label", set())
    hints = resources.get("acc_common_hint_details", set())
    return next((
        node for node in nodes if node.enabled and node.tap_point
        and any(node.content_desc.startswith(label + ".") for label in labels)
        and any(node.content_desc.rstrip(".").endswith(hint) for hint in hints)
    ), None)


def find_settings_entry(nodes: list[UiNode], resources: StringResources) -> UiNode | None:
    """The overview's vehicle Settings row, by its translated label and hint."""
    labels = resources.get("acc_vehicle_tab_label_settings", set())
    hints = resources.get("acc_common_hint_details", set())
    return next((
        node for node in nodes if node.enabled and node.tap_point
        and any(node.content_desc.startswith(label + ".") for label in labels)
        and any(node.content_desc.rstrip(".").endswith(hint) for hint in hints)
    ), None)


def find_tile_entry(nodes: list[UiNode], resources: StringResources, key: str) -> UiNode | None:
    """An overview tile by its translated label and the "Open details" hint."""
    labels = resources.get(key, set())
    hints = resources.get("acc_common_hint_details", set())
    return next((
        node for node in nodes if node.enabled and node.tap_point
        and any(node.content_desc.startswith(label + ".") for label in labels)
        and any(node.content_desc.rstrip(".").endswith(hint) for hint in hints)
    ), None)


def driving_tile_text(nodes: list[UiNode], resources: StringResources) -> str | None:
    """The overview's Driving data tile as read out, or None when it is not on screen.

    The tile carries the last trip ("Last driven: 3.0 kilometres. Average
    consumption: …"), so its text changes when a trip ends. It is compared,
    never parsed. Without the app's tables the English and German labels find
    it.
    """
    node = find_tile_entry(nodes, resources, DRIVING_TILE)
    if node is None:
        node = next((
            n for n in nodes
            if n.enabled and n.tap_point and _DRIVING_TILE_FALLBACK.match(n.content_desc)
        ), None)
    return node.content_desc if node is not None else None


_DRIVING_TILE_FALLBACK = re.compile(r"^(?:Driving\s*data|Fahrdaten)\.\s")


def read_departure_timers(nodes: list[UiNode]) -> dict[str, object]:
    """The Departure times screen's timer rows, top to bottom, at most three.

    Each row's switch is the timer's on/off and its clock text the time,
    reported as 24-hour "HH:MM" like the VW cloud's ``departureTime`` (see
    ``departure.departure_rows``). The words around them are not read, so
    this works in any language. The count is set only when all three timers
    were on screen.
    """
    rows = departure_rows(nodes)
    out: dict[str, object] = {}
    for index, row in enumerate(rows[:3], start=1):
        out[f"departure_timer_{index}_enabled"] = row.enabled
        out[f"departure_timer_{index}_time"] = row.time
    if len(rows) >= 3:
        out["departure_timer_enabled_count"] = sum(1 for row in rows[:3] if row.enabled)
    return out


_TRIP_VALUE_RE = re.compile(r"^\W*?(\d[\d.,\u00a0\u202f ]*?)\s*([^\d\s.,].*)$")


def _trip_number(raw: str) -> float | None:
    """ "1,234.5", "1.234,5", "16,5", "299": one separator followed by three
    digits groups thousands, any other last separator is the decimal mark."""
    digits = re.sub(r"[\s\u00a0\u202f]", "", raw)
    marks = [i for i, c in enumerate(digits) if c in ".,"]
    if marks and not (len(marks) == 1 and len(digits) - marks[0] - 1 == 3):
        whole = re.sub(r"[.,]", "", digits[:marks[-1]])
        digits = whole + "." + digits[marks[-1] + 1:]
    else:
        digits = re.sub(r"[.,]", "", digits)
    try:
        return float(digits)
    except ValueError:
        return None


def _trip_cards(
    nodes: list[UiNode], resources: StringResources,
) -> list[tuple[str, tuple[int, int, int, int]]]:
    """(card prefix, card box) for each trip card title on screen."""
    cards = []
    for prefix, keys in TRIP_CARDS.items():
        titles = _labels(resources, *keys)
        for title in nodes:
            if title.bounds is None or title.text.strip().casefold() not in titles:
                continue
            box = min(
                (n.bounds for n in nodes if n.clickable and n.bounds is not None
                 and _inside(title, n.bounds)),
                key=lambda b: (b[2] - b[0]) * (b[3] - b[1]),
                default=None,
            )
            if box is not None:
                cards.append((prefix, box))
    return cards


def trip_carousel_row(
    nodes: list[UiNode], resources: StringResources,
) -> tuple[int, int, int, int] | None:
    """The band the trip cards share, to swipe sideways in; None without both."""
    boxes = [box for _prefix, box in _trip_cards(nodes, resources)]
    if len(boxes) < 2:
        return None
    left = min(b[0] for b in boxes)
    right = max(b[2] for b in boxes)
    return left, max(b[1] for b in boxes), right, min(b[3] for b in boxes)


def read_driving_data(nodes: list[UiNode], resources: StringResources) -> dict[str, object]:
    """The trip cards' rows into the VW cloud's ``last_trip_*`` / ``refuel_trip_*``.

    Each row label is followed, to its right, by its value text (consumption
    by one line per energy). Values are kept only when their unit is one of the
    app's own: distance and speed in km or miles (miles converted), consumption
    in kWh/100 km or l/100 km. A card clipped at the screen edge shows its
    labels without values and gives nothing.
    """
    out: dict[str, object] = {}
    row_labels = {
        label: row for key, row in TRIP_ROWS.items() for label in _labels(resources, key)
    }
    units = {
        label: spec for key, spec in TRIP_UNITS.items() for label in _labels(resources, key)
    }
    hours = _patterns(resources, DURATION_HOURS)
    minutes = _patterns(resources, CLIMA_MINUTES)
    for prefix, box in _trip_cards(nodes, resources):
        inside = [n for n in nodes if n.text.strip() and n.bounds is not None and _inside(n, box)]
        labels = sorted(
            ((n.bounds, row_labels[n.text.strip().casefold()]) for n in inside
             if n.bounds is not None and n.text.strip().casefold() in row_labels),
        )
        for index, (label_box, row) in enumerate(labels):
            below = labels[index + 1][0][1] if index + 1 < len(labels) else box[3]
            texts = [
                n.text.strip() for n in inside
                if n.bounds is not None and n.bounds[0] >= label_box[2]
                and label_box[1] <= n.bounds[1] < below
            ]
            for text in texts:
                if row == "time":
                    total = _trip_duration(text, hours, minutes)
                    if total is not None:
                        out[f"{prefix}_duration_min"] = total
                    continue
                match = _TRIP_VALUE_RE.match(text)
                spec = units.get(match.group(2).strip().casefold()) if match else None
                number = _trip_number(match.group(1)) if match else None
                if spec is None or number is None:
                    continue
                kind, factor = spec
                if row == "distance" and kind == "distance":
                    out[f"{prefix}_distance_km"] = round(number * factor, 1)
                elif row == "speed" and kind == "speed":
                    out[f"{prefix}_avg_speed_kmh"] = round(number * factor, 1)
                elif row == "consumption" and kind == "electric":
                    out[f"{prefix}_avg_electric_consumption_kwh_100km"] = number
                elif row == "consumption" and kind == "fuel":
                    out[f"{prefix}_avg_fuel_consumption_l_100km"] = number
    return out


def _trip_duration(
    text: str, hours: list[re.Pattern[str]], minutes: list[re.Pattern[str]],
) -> int | None:
    """ "10 h 59 min", "12 min", "2 h" by the app's own duration templates."""
    found_h = next((m for p in hours if (m := p.search(text))), None)
    found_m = next((m for p in minutes if (m := p.search(text))), None)
    if found_h is None and found_m is None:
        return None
    total = 0
    for match, scale in ((found_h, 60), (found_m, 1)):
        if match is not None and match.lastindex:
            value = _trip_number(match.group(1))
            if value is None:
                return None
            total += int(value) * scale
    return total


def find_request_limit(nodes: list[UiNode], resources: StringResources) -> bool:
    """The app's "too many requests" alert, by its translated title."""
    titles = {
        label.casefold() for key in _LIMIT_KEYS for label in resources.get(key, ())
    }
    return bool(titles) and any(
        text.strip().casefold() in titles
        for node in nodes for text in (node.text, node.content_desc) if text
    )


def power_budget_labels(resources: StringResources) -> set[str]:
    """The local power-budget alert's title and footer, minus any wording a
    backend limit dialog shares (a shared wording proves nothing)."""
    return _labels(resources, POWER_BUDGET_TITLE, POWER_BUDGET_FOOTER) - _labels(
        resources, *_BACKEND_LIMIT_TEXTS
    )


def is_power_budget_alert(nodes: list[UiNode], resources: StringResources) -> bool:
    """True only for the app's local power-budget alert: its title AND its
    footer on screen, and no text of a backend limit dialog.

    Anything else, including unreadable tables, counts as a backend limit.
    """
    shown = {
        text.strip().casefold()
        for node in nodes for text in (node.text, node.content_desc) if text
    }
    footer = _labels(resources, POWER_BUDGET_FOOTER) - _labels(resources, *_BACKEND_LIMIT_TEXTS)
    return (
        bool(shown & _labels(resources, POWER_BUDGET_TITLE))
        and bool(shown & footer)
        and not shown & _labels(resources, *_BACKEND_LIMIT_TEXTS)
    )


def find_app_alert(nodes: list[UiNode], resources: StringResources) -> bool:
    """A known app alert dialog: the request limit or "Vehicle data unavailable".

    Matched by the translated titles of the installed app; the English 4.3.2
    headline stands in when the tables cannot be read.
    """
    titles = {
        label.casefold()
        for key in (*_LIMIT_KEYS, DATA_UNAVAILABLE)
        for label in resources.get(key, ())
    } or {"too many requests sent to the vehicle", "request limit reached",
          "vehicle data unavailable"}
    return any(
        text.strip().casefold() in titles
        for node in nodes for text in (node.text, node.content_desc) if text
    )


def _labels(resources: StringResources, *keys: str) -> set[str]:
    return {
        label.strip().casefold()
        for key in keys for label in resources.get(key, ()) if label.strip()
    }


def climate_function_state(text: str, resources: StringResources) -> bool | None:
    """A climate function row: "Active", "Active • 10 min", "Activated" or "Off".

    "Autom." is the automatic setting, not a state, so it stays unknown. Falls
    back to the German/English patterns when the tables could not be read.
    """
    value = text.strip().casefold()
    active = _labels(resources, *CLIMA_ACTIVE)
    off = _labels(resources, CLIMA_OFF)
    if not active and not off:
        fallback = coerce("clima_function_state", text)
        return fallback if isinstance(fallback, bool) else None
    if value in off:
        return False
    if any(value == label or value.startswith(label + " ") for label in active):
        return True
    return None


_AC_TITLE_FALLBACK = re.compile(r"\s*(?:Air\s*conditioning|Klimatisierung)\s*", re.I)


def climate_mode_is_window_heating(title: str, resources: StringResources) -> bool | None:
    """The mode row's title: True for window heating alone, False for AC."""
    value = title.strip().casefold()
    if not resources.get(CLIMA_MODE_WINDOW_HEATING):
        fallback = coerce("clima_mode_window_heating", title)
        if isinstance(fallback, bool):
            return fallback
        # The English/German air conditioning title, so a climate Start can
        # still tell the modes apart without the tables (a migration target).
        return False if _AC_TITLE_FALLBACK.fullmatch(title) else None
    if value in _labels(resources, CLIMA_MODE_WINDOW_HEATING):
        return True
    if value in _labels(resources, CLIMA_MODE_AC):
        return False
    return None


def dial_labels(resources: StringResources) -> tuple[set[str], set[str]]:
    """The dial's translated "LO" and "HI" labels, the APK defaults included."""
    return _labels(resources, CLIMA_LOW) | {"lo"}, _labels(resources, CLIMA_HIGH) | {"hi"}


def _inside(node: UiNode, box: tuple[int, int, int, int]) -> bool:
    if node.bounds is None:
        return False
    left, top, right, bottom = box
    n_left, n_top, n_right, n_bottom = node.bounds
    return left <= n_left <= n_right <= right and top <= n_top <= n_bottom <= bottom


def _rid(node: UiNode) -> str:
    return node.resource_id.split("/")[-1]


def read_climate_resources(nodes: list[UiNode], resources: StringResources) -> dict[str, object]:
    """The Air Conditioning sheet and its Settings sheet, by the app's own labels.

    Controls are found by resource-id as before; only their text is matched
    against the installed app's translations instead of a word list. Returns
    only what the screen proves, so the preset's selectors stay the fallback.
    """
    out: dict[str, object] = {}
    if not resources:
        return out
    running = any(_rid(n) == "cta_stop" for n in nodes)
    idle = any(_rid(n) == "cta_start" for n in nodes)
    by_rid = {_rid(n): n for n in reversed(nodes) if n.resource_id}
    automatic = _labels(resources, CLIMA_AUTOMATIC)
    for rid, target in (
        ("air_conditioning_description", "climatisation_active"),
        ("window_heating_description", "window_heating_front"),
    ):
        node = by_rid.get(rid)
        if node is None or not node.text:
            continue
        state = climate_function_state(node.text, resources)
        if state is not None:
            out[target] = state
        if target == "window_heating_front" and node.text.strip().casefold() in automatic:
            out["window_heating_enabled"] = True
    # The mode row (pick layout) names what Start starts. Window heating alone
    # means air conditioning is off and the window heating is what runs.
    pick = by_rid.get("clima_air_conditioning_pick")
    if pick is not None and pick.bounds is not None:
        title = next(
            (n.text for n in nodes if _rid(n) == "title" and n.text and _inside(n, pick.bounds)),
            "",
        )
        mode = climate_mode_is_window_heating(title, resources) if title else None
        if mode is not None:
            out["climate_start_mode"] = "window_heating" if mode else "air_conditioning"
            if mode:
                out["climatisation_active"] = False
                if running or idle:
                    out["window_heating_front"] = running
    if idle:
        out["climate_remaining_time_min"] = 0
    else:
        for pattern in _patterns(resources, CLIMA_MINUTES):
            for rid in ("air_conditioning_description", "description", "clima_time_remaining"):
                node = by_rid.get(rid)
                match = pattern.search(node.text) if node is not None and node.text else None
                if match and match.lastindex:
                    out["climate_remaining_time_min"] = int(match.group(1))
                    break
            if "climate_remaining_time_min" in out:
                break
    out.update(_read_zones(nodes, resources))
    return out


def _read_zones(nodes: list[UiNode], resources: StringResources) -> dict[str, object]:
    """The Settings sheet's Zones row: "Front left", "2 zones" or empty.

    The value is the text on the title's own line, right of it. One zone by
    name is exact for the front pair; a rear zone is reported only when the row
    names it. "%s zones" does not say which: "2 zones" is read as both front
    zones (the only pair a front-zone car has), more is left unknown.
    """
    titles = _labels(resources, CLIMA_ZONES)
    label = next(
        (n for n in nodes if n.text and n.text.strip().casefold() in titles and n.bounds),
        None,
    )
    if label is None or label.bounds is None:
        return {}
    _left, top, right, bottom = label.bounds
    values = [
        n.text.strip() for n in nodes
        if n is not label and n.text and n.text.strip() and n.bounds
        and n.bounds[0] >= right and n.bounds[1] < bottom and n.bounds[3] > top
    ]
    if not values:
        # The app shows nothing beside the title when no zone is on.
        return {"climate_zone_front_left": False, "climate_zone_front_right": False}
    for value in values:
        for key, target in CLIMA_ZONE_KEYS.items():
            if value.casefold() in _labels(resources, key):
                out: dict[str, object] = {
                    "climate_zone_front_left": False, "climate_zone_front_right": False,
                }
                out[target] = True
                return out
        for pattern in _patterns(resources, CLIMA_ZONES_SEVERAL):
            match = pattern.fullmatch(value)
            if match and match.lastindex and match.group(1) == "2":
                return {"climate_zone_front_left": True, "climate_zone_front_right": True}
    return {}


def read_settings_resources(nodes: list[UiNode], resources: StringResources) -> dict[str, object]:
    """Switches on vehicle Settings, by the app's own labels.

    A switch row is the checkable node whose bounds hold the label; its
    ``checked`` attribute is the setting. Read only: nothing here is tapped.
    """
    out: dict[str, object] = {}
    switches = [n for n in nodes if n.checkable and n.bounds is not None]
    for key, (target, on, off) in SETTINGS_SWITCHES.items():
        labels = _labels(resources, key)
        label = next((n for n in nodes if n.text and n.text.strip().casefold() in labels), None)
        if label is None:
            continue
        row = next((n for n in switches if _inside(label, n.bounds)), None)  # type: ignore[arg-type]
        if row is not None:
            out[target] = on if row.checked else off
    return out


_DISTANCE_UNIT_RE = re.compile(r"\d\s*(?:km|mi)\b", re.I)
_DAYS_RE = re.compile(r"^\D*(\d{1,4})\D*$")


def read_health_resources(nodes: list[UiNode], resources: StringResources) -> dict[str, object]:
    """The Vehicle Health Report's rows, found by the app's own subheads.

    Each subhead is followed by its value line. A value part with a km/mi
    unit is the distance; a bare number is the day count, whatever word the
    language uses for days.
    """
    out: dict[str, object] = {}
    texts = [n.text.strip() for n in nodes if n.text and n.text.strip()]
    for key, (distance_target, days_target) in HEALTH_ROWS.items():
        labels = _labels(resources, key)
        index = next((i for i, t in enumerate(texts) if t.casefold() in labels), None)
        if index is None or index + 1 >= len(texts):
            continue
        for part in texts[index + 1].split("/"):
            if _DISTANCE_UNIT_RE.search(part):
                value = coerce("range_km", part)
                if isinstance(value, int):
                    out[distance_target] = value
            elif days_target is not None:
                match = _DAYS_RE.match(part)
                if match and int(match.group(1)) <= 3650:
                    out[days_target] = int(match.group(1))
    out.update(_read_health_warnings(nodes, resources))
    return out


def _read_health_warnings(nodes: list[UiNode], resources: StringResources) -> dict[str, object]:
    """The warning header, into the fields the VW cloud's warning lights fill.

    "No issues found" clears them. "Issues found" sets the flag and names each
    category whose row carries a ``warningValue`` beside its name; a header
    seen without such rows leaves the count and the list unknown.
    """
    header = next((n for n in nodes if _rid(n) == "warningHeaderTitle" and n.text), None)
    if header is None:
        return {}
    title = header.text.strip().casefold()
    if title in _labels(resources, HEALTH_NO_ISSUES):
        return {"warning_active": False, "warning_count": 0, "warning_messages": ""}
    if title not in _labels(resources, HEALTH_ISSUES):
        return {}
    values = [n for n in nodes if _rid(n) == "warningValue" and n.text and n.bounds]
    messages = []
    for name in nodes:
        if not _rid(name).startswith("warningName") or not name.text or name.bounds is None:
            continue
        top, bottom = name.bounds[1], name.bounds[3]
        beside = [
            v.text.strip() for v in values
            if v.bounds is not None and v.bounds[1] < bottom and v.bounds[3] > top
        ]
        if beside:
            messages.append(f"{name.text.strip()}: {', '.join(beside)}")
    out: dict[str, object] = {"warning_active": True}
    if messages:
        out.update(warning_count=len(messages), warning_messages=", ".join(messages))
    return out


def read_overview_resources(nodes: list[UiNode], resources: StringResources) -> dict[str, object]:
    """The lock and climate tiles of the overview, by the app's own labels.

    Only a value the app names exactly is taken: "Is being locked" and the
    climate tile's "information not available" leave the field to the
    preset's selectors, as does a language whose labels could not be read.
    """
    out: dict[str, object] = {}
    lock, locked, unlocked = (_labels(resources, k) for k in (TILE_LOCK, TILE_LOCKED, TILE_UNLOCKED))
    clima, clima_on, clima_off = (_labels(resources, k) for k in (TILE_CLIMA, TILE_CLIMA_ON, TILE_CLIMA_OFF))
    for node in nodes:
        parts = [p.strip().casefold() for p in node.content_desc.split(". ")]
        if len(parts) < 2:
            continue
        label, value = parts[0], parts[1].rstrip(".")
        if label in lock and value in locked | unlocked:
            out["doors_locked"] = value in locked
        elif label in clima and value in clima_on | clima_off:
            out["climatisation_active"] = value in clima_on
            out["climatisation_state"] = node.content_desc.split(". ")[1].strip().rstrip(".")
    return out
