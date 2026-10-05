# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Read battery and Settings labels from the installed app's compiled translation tables.

Resource names are stable across locales; their values come from the phone,
not a translated word list. Only simple string entries are read. No APK code,
account data, network credentials, or third-party decoder is needed at runtime.
"""
from __future__ import annotations

import re
import struct

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
_SINGLE_KEYS = frozenset({
    "acc_common_hint_details", "acc_vehicle_tab_label_settings", *_LIMIT_KEYS,
    SYNC_LAST_UPDATE, SYNC_JUST_NOW, SYNC_TOO_OLD, DATA_UNAVAILABLE,
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
    """One plurals bag of the sync line, stored as ``name#quantity`` strings."""
    es, ef, key = struct.unpack_from("<HHI", data, entry)
    name = keys[key]
    if not ef & 1 or es < 16 or entry + 16 > end or name not in SYNC_PLURALS:
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


def extract_battery_strings(data: bytes) -> StringResources:
    """Decode the small relevant subset of Android's resources.arsc format.

    A malformed/unsupported table returns no labels. Complex entries (styles,
    bags) and non-string values are deliberately ignored, never interpreted as
    strings, except the sync line's duration plurals, read per quantity. Dense,
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
    return out


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


def find_request_limit(nodes: list[UiNode], resources: StringResources) -> bool:
    """The app's "too many requests" alert, by its translated title."""
    titles = {
        label.casefold() for key in _LIMIT_KEYS for label in resources.get(key, ())
    }
    return bool(titles) and any(
        text.strip().casefold() in titles
        for node in nodes for text in (node.text, node.content_desc) if text
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
