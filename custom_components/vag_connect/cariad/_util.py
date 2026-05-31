# Copyright 2026 Prash Balan (@its-me-prash) — Apache License 2.0
"""Pure helpers usable from both the API client layer and the HA layer."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Iterable

_LOGGER = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# v1.10.1 — Defensive coding helpers (Issue #58, Phase 2).
#
# Three pure conversion helpers that NEVER raise. They're consumed by the
# brand parsers in places where a single malformed API value used to take
# down the whole vehicle's poll. The pattern documented in
# `skodaconnect/myskoda` issues #503 (CHARGING_INTERRUPTED), #207
# (NOT_ACTIVATED) and PR #565 (NO_UPDATE_AVAILABLE) — VAG ships new enum
# values without warning and integrations that don't tolerate them break
# overnight.
# ─────────────────────────────────────────────────────────────────────────────


def safe_int(value: Any, default: int | None = None) -> int | None:
    """Convert ``value`` to int or return ``default``.

    Accepts:
    - int, bool (Python bool is int subclass — preserved)
    - float (truncated)
    - str (numeric or numeric-with-whitespace)

    Returns ``default`` for None, empty strings, non-numeric strings,
    dicts, lists or any TypeError/ValueError. Never raises.
    """
    if value is None:
        return default
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        try:
            return int(value)
        except (OverflowError, ValueError):
            return default
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return default
        try:
            return int(stripped)
        except ValueError:
            try:
                return int(float(stripped))
            except (ValueError, OverflowError):
                return default
    return default


def safe_float(value: Any, default: float | None = None) -> float | None:
    """Convert ``value`` to float or return ``default``. Never raises."""
    if value is None:
        return default
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float)):
        try:
            return float(value)
        except (OverflowError, ValueError):
            return default
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return default
        try:
            return float(stripped)
        except ValueError:
            # v1.20.2 — locale-comma fallback. Skoda has shipped
            # ``"21,5"`` (comma decimal, EU locale formatting) on EU
            # accounts at least once historically. v1.10.1 #58 docs
            # claimed safe_float handles this but the original code
            # only accepted dot-decimal — locale-comma silently
            # returned default. Try once more with comma → dot.
            if "," in stripped:
                try:
                    return float(stripped.replace(",", ".", 1))
                except ValueError:
                    return default
            return default
    return default


def safe_enum(
    value: Any,
    known_values: Iterable[str],
    *,
    log_name: str = "enum",
    default: str | None = None,
    case_insensitive: bool = True,
) -> str | None:
    """Return ``value`` if it's in ``known_values``, else log + return default.

    Forward-compatibility shield against unannounced VAG backend changes.
    Every brand has shipped at least one new enum value mid-release
    (myskoda #503 CHARGING_INTERRUPTED, #207 NOT_ACTIVATED, PR #565
    NO_UPDATE_AVAILABLE). Without tolerance the integration crashes
    until we publish a hotfix; with tolerance the entity just shows
    ``unknown`` and the user keeps everything else.

    Args:
        value: The string the API returned. Non-strings are coerced
            via ``str()`` before comparison.
        known_values: Iterable of allowed strings. Performance-wise it's
            converted to a frozenset internally, so callers can pass any
            iterable shape (list, tuple, set, generator).
        log_name: Used in the warning log message — pass the field name
            (e.g. ``"charging_state"``) so the log line is actionable.
        default: Returned when ``value`` is None/empty or unknown.
        case_insensitive: When True (default), ``value`` is compared
            case-insensitively but the *original* string is returned on
            match. The CARIAD BFF mostly returns SCREAMING_SNAKE so
            mixed-case responses from a future firmware should still
            classify correctly.

    Returns:
        The original ``value`` if known, otherwise ``default``.
    """
    if value is None:
        return default
    text = str(value).strip()
    if not text:
        return default
    if case_insensitive:
        upper = text.upper()
        known_upper = {k.upper() for k in known_values}
        if upper in known_upper:
            return text
    elif text in set(known_values):
        return text
    _LOGGER.warning(
        "vag_connect: unknown %s value %r — keeping vehicle reachable, "
        "Vehicle Data Scout will surface it on next poll. "
        "Please open a GitHub issue with the masked log line.",
        log_name, text,
    )
    return default


# Connection-state thresholds (v1.8.12 — Multi-Brand Connection-State).
# Derived from `homeassistant-myskoda` issues #751 and #731 + verified
# against `skodaconnect/myskoda` PR #536 (pattern bestätigt).
#   age < 30 min  → "online"   (live, just heard from the car)
#   age < 24 h    → "standby"  (asleep but reachable via /wakeup)
#   age >= 24 h   → "offline"  (12V flat / underground / service)
_CONNECTION_ONLINE_THRESHOLD_S = 1800
_CONNECTION_STANDBY_THRESHOLD_S = 86400


def safe_get(
    data: Any,
    path: str,
    default: Any = None,
) -> Any:
    """v2.2.0 — Defensive dot-path nested accessor with list-index support.

    Replaces unsafe ``resp['a']['b'][0]['c']`` patterns that crash on
    MY26 schema rotations (where the backend silently changes a dict to
    a list, drops a key, or returns an empty/None container).

    Path syntax::

        "a.b.c"          → data["a"]["b"]["c"]
        "a.b[0]"         → data["a"]["b"][0]
        "a.b[0].c"       → data["a"]["b"][0]["c"]
        "doors[2].lock"  → data["doors"][2]["lock"]

    Returns ``default`` for ANY of: missing key, wrong type, list-index
    out of range, None encountered mid-traversal, list-index applied to
    non-list. Never raises.

    Use cases (closes VW HA #922, pycupra #76, audi #686 bug-classes):
    - ``safe_get(access, "doors[0].status[0].value")``
    - ``safe_get(charging, "rates[0].chargeRate_kmph", default=0)``

    Args:
        data: Any JSON-shaped object (dict, list, or scalar). Strings
            and primitives short-circuit immediately to ``default``.
        path: Dot-separated path. Bracket-numbered indices are parsed
            inline (``a.b[0].c`` is parsed as ``a → b → [0] → c``).
        default: Returned on any failure. ``None`` is the sane default
            because all our consumers already test ``if x is not None``.

    Sheldon-pedantry note: this is intentionally NOT a full JSONPath
    implementation. We support exactly what our parsers need —
    dot-path + integer-list-index — and nothing else, so the audit
    surface stays one screen of code.
    """
    if not path:
        return data
    # Split "a.b[0].c" → ["a", "b[0]", "c"] then per-segment handle [N]
    node: Any = data
    for raw_segment in path.split("."):
        if node is None:
            return default
        # Detect optional list-index suffix: "b[0]" → key="b", idx=0
        idx: int | None = None
        key = raw_segment
        if "[" in raw_segment and raw_segment.endswith("]"):
            try:
                bracket_start = raw_segment.index("[")
                key = raw_segment[:bracket_start]
                idx_str = raw_segment[bracket_start + 1:-1]
                idx = int(idx_str)
            except (ValueError, IndexError):
                return default
        # Dict-key step (skip when segment is bare-index like "[0]")
        if key:
            if not isinstance(node, dict):
                return default
            node = node.get(key)
            if node is None:
                return default
        # List-index step
        if idx is not None:
            if not isinstance(node, list) or not (-len(node) <= idx < len(node)):
                return default
            node = node[idx]
    return node if node is not None else default


def json_safe_dict(obj: dict[str, Any]) -> dict[str, Any]:
    """v2.2.0 — Typed wrapper for ``json_safe`` when input + output are both dicts.

    Exists to satisfy mypy strict ``--warn-return-any`` at call sites
    that need ``dict[str, Any]`` rather than ``Any``. Most
    ``extra_state_attributes`` methods declare ``dict[str, Any] | None``
    return and need this typed shape.
    """
    result = json_safe(obj)
    assert isinstance(result, dict)
    return result


def json_safe(obj: Any) -> Any:
    """v2.2.0 — Recursively convert ``obj`` to a JSON-serialisable shape.

    Closes the bug-class that hit Skoda PR #1090: ``extra_state_attributes``
    silently broke MQTT statestream, recorder + REST API when an entity
    exposed a ``datetime``, ``dataclass`` instance, ``set`` or any other
    non-JSON-native Python type. HA's frontend renders the attribute as
    ``unknown`` and the recorder logs a TypeError every poll.

    Conversion rules:
    - ``datetime`` / ``date`` → ISO 8601 string (UTC-suffixed when tz-aware)
    - ``timedelta``           → total seconds (float)
    - ``set`` / ``frozenset`` → sorted ``list``
    - ``bytes`` / ``bytearray`` → ``utf-8`` string, or hex if decode fails
    - dataclass instance → recursive ``asdict`` then re-process
    - ``dict``            → keys coerced to str, values processed
    - ``list`` / ``tuple`` → recursively processed
    - Everything else (str/int/float/bool/None) → passed through

    Never raises. On any unexpected error, falls back to ``str(obj)`` so
    the entity still updates rather than going ``unknown``.

    Usage in entity classes::

        @property
        def extra_state_attributes(self) -> dict[str, Any] | None:
            attrs = {"last_seen_at": self._vehicle.get("last_seen_at"), ...}
            return json_safe_dict(attrs)  # use typed wrapper for mypy
    """
    import dataclasses  # noqa: PLC0415 — local to keep _util import-light
    from datetime import date, timedelta  # noqa: PLC0415

    try:
        if obj is None or isinstance(obj, (str, int, float, bool)):
            return obj
        if isinstance(obj, datetime):
            # datetime → ISO 8601 with tz-suffix preserved
            return obj.isoformat()
        if isinstance(obj, date):
            return obj.isoformat()
        if isinstance(obj, timedelta):
            return obj.total_seconds()
        if isinstance(obj, (set, frozenset)):
            return sorted(
                (json_safe(item) for item in obj),
                key=lambda x: str(x),
            )
        if isinstance(obj, (bytes, bytearray)):
            try:
                return bytes(obj).decode("utf-8")
            except UnicodeDecodeError:
                return bytes(obj).hex()
        if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
            return json_safe(dataclasses.asdict(obj))
        if isinstance(obj, dict):
            return {str(k): json_safe(v) for k, v in obj.items()}
        if isinstance(obj, (list, tuple)):
            return [json_safe(item) for item in obj]
        # Unknown type — fallback to repr-string so we never crash
        return str(obj)
    except Exception:  # noqa: BLE001 — defensive guarantee
        _LOGGER.debug("json_safe: fallback for %s", type(obj).__name__, exc_info=True)
        return str(obj)


def mask_vin(vin: str | None) -> str:
    """Return a privacy-safe VIN representation for logs and diagnostics.

    Keeps the last 6 characters (enough for support to disambiguate vehicles
    on a single account) and drops the rest. A VIN ties to registration,
    insurance and ownership records, so full VINs must never end up in
    GitHub issues, public diagnostics or third-party log forwarders.
    """
    if not vin:
        return "***"
    if len(vin) <= 6:
        return f"***{vin}"
    return f"***{vin[-6:]}"


def compute_connection_state(
    *sub_objects: Any,
    timestamp_keys: tuple[str, ...] = ("carCapturedTimestamp",),
) -> tuple[str | None, datetime | None]:
    """Derive ``(connection_state, last_seen_at)`` from sub-object timestamps.

    The mysmob (Škoda), OLA (SEAT/CUPRA) and CARIAD-BFF (VW/Audi) backends
    all decorate every status sub-object with a ``carCapturedTimestamp``
    that records *when the vehicle itself last reported the data* — not
    when we polled the backend. Different sub-objects update independently
    (charging publishes more frequently than door state), so the freshest
    timestamp across all sub-objects wins.

    Pattern source: `skodaconnect/myskoda` PR #536
    (`process_charging_event` compares an event timestamp against the API
    snapshot's `carCapturedTimestamp`; older events are ignored). Our
    semantics: the freshest timestamp determines the *vehicle's*
    connection state, regardless of which sub-system produced it.

    Defensive against:

    - sub-objects that are exceptions (asyncio.gather with
      ``return_exceptions=True``)
    - sub-objects that are not dicts
    - missing timestamp fields (myskoda PR #565 confirms this is allowed —
      ``SoftwareStatus.NO_UPDATE_AVAILABLE`` doesn't include
      ``carCapturedTimestamp``)
    - corrupt ISO strings (``ValueError`` swallowed, sub-object skipped)

    Returns ``(None, None)`` if no usable timestamp is found anywhere —
    callers must NOT fabricate a value (Hard Rule #8). The
    ``connection_state`` sensor will simply read ``None`` and HA renders
    it as "unknown".

    Args:
        *sub_objects: Any number of dict / Exception / None values from
            ``asyncio.gather(..., return_exceptions=True)``.
        timestamp_keys: Override the field names to look for. Default
            covers the common ``carCapturedTimestamp``. Add
            ``"capturedAt"`` etc. for backends that diverge.

    Returns:
        Tuple ``(connection_state, last_seen_at)``:

        - ``connection_state``: "online" / "standby" / "offline" / None
        - ``last_seen_at``: datetime (UTC) of the freshest timestamp, or None
    """
    def _extract_timestamps(node: Any) -> list[datetime]:
        """Recursively walk dicts and lists, collecting any datetime that
        sits under one of ``timestamp_keys``.

        VW EU CARIAD-BFF nests deeper than Škoda mysmob:
        ``selectivestatus`` returns
        ``{access: {accessStatus: {value: {carCapturedTimestamp: ...}}}}``
        verified live in `upstream/volkswagencarnet` issue #921.
        Škoda mysmob returns the timestamp at top-level
        ``{carCapturedTimestamp: ..., ...}``. SEAT/CUPRA OLA mostly
        top-level too. The recursive walk handles all three without
        per-brand path lists.

        Accepts both ISO strings (Škoda, OLA) and pre-parsed
        ``datetime`` objects (volkswagencarnet's lib does the conversion
        before storing).
        """
        out: list[datetime] = []
        if isinstance(node, dict):
            for k, val in node.items():
                if k in timestamp_keys:
                    if isinstance(val, datetime):
                        out.append(val if val.tzinfo else val.replace(tzinfo=timezone.utc))
                    elif isinstance(val, str):
                        try:
                            ts = datetime.fromisoformat(val.replace("Z", "+00:00"))
                            out.append(ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc))
                        except ValueError:
                            pass
                else:
                    out.extend(_extract_timestamps(val))
        elif isinstance(node, list):
            for item in node:
                out.extend(_extract_timestamps(item))
        return out

    latest_ts: datetime | None = None
    for sub in sub_objects:
        if isinstance(sub, BaseException):
            continue
        for ts in _extract_timestamps(sub):
            if latest_ts is None or ts > latest_ts:
                latest_ts = ts

    if latest_ts is None:
        return None, None

    age_s = (datetime.now(tz=timezone.utc) - latest_ts).total_seconds()
    if age_s < _CONNECTION_ONLINE_THRESHOLD_S:
        return "online", latest_ts
    if age_s < _CONNECTION_STANDBY_THRESHOLD_S:
        return "standby", latest_ts
    return "offline", latest_ts


# v2.2.1 Phase 8 PR #5 — cross-brand `car_type` derivation helper.
#
# Skoda (Phase 8 PR #1) and VW EU/Audi (Phase 8 PR #2) read `car_type`
# directly from the backend (`driving-range.carType` / `measurements.
# fuelLevelStatus.value.carType`). CUPRA/SEAT, Porsche, VW NA don't
# expose a direct field — but we can DERIVE it from the existing
# parsed data (`has_battery`, `has_combustion`, `primary_engine_type`).
#
# Derivation rules (order matters):
#   1. has_battery + has_combustion → "hybrid"
#   2. has_battery only → "electric"
#   3. has_combustion only → derive from primary_engine_type:
#      "DIESEL" / "diesel" → "diesel"
#      "PETROL" / "GASOLINE" / "gasoline" → "gasoline"
#      anything else → leave None (don't guess)
#   4. neither flag set → leave None (insufficient signal)
#
# Defensive: NEVER overwrites a directly-read value. Only assigns
# when `d.car_type` is currently None. This way Skoda/VW EU/Audi
# users keep their authoritative backend value; CUPRA/SEAT/Porsche/
# VW NA users get the derived value.
def derive_car_type_if_missing(d: Any) -> None:
    """Cross-brand `car_type` derivation. Assigns ``d.car_type`` only
    when currently None; never overwrites a directly-read value.

    Safe to call at the end of any brand parser — pure-function on
    already-populated dataclass fields, never raises.
    """
    if getattr(d, "car_type", None) is not None:
        return  # already set by direct backend read — don't overwrite
    has_bat = bool(getattr(d, "has_battery", False))
    has_comb = bool(getattr(d, "has_combustion", False))
    if has_bat and has_comb:
        d.car_type = "hybrid"
        return
    if has_bat:
        d.car_type = "electric"
        return
    if has_comb:
        pet = (getattr(d, "primary_engine_type", None) or "").lower()
        if "diesel" in pet:
            d.car_type = "diesel"
        elif "petrol" in pet or "gasoline" in pet:
            d.car_type = "gasoline"
        # else: don't guess (could be CNG/LPG/H2 etc — wait for
        # explicit backend field or scout report)
    # neither flag set: insufficient signal, leave None


# ─────────────────────────────────────────────────────────────────────────────
# v2.8.0 — Brake service + preferred workshop helpers (Quick Win C).
#
# Two pure conversion helpers shared across brand parsers:
#
# 1. ``days_or_date_to_iso`` accepts the THREE shapes the CARIAD BFF + Skoda
#    mysmob + OLA backends ship for service due-dates:
#      - int / float "N" — N days from now (CARIAD BFF + Skoda)
#      - "2026-06-15" / "2026-06-15T08:30:00Z" — ISO 8601 (OLA + some Skoda)
#      - "15.06.2026" — EU dd.mm.yyyy (legacy SEAT/CUPRA OLA on some
#        firmwares + dealer-portal exports)
#    Returns a tz-aware ISO 8601 UTC string anchored at midnight when the
#    source was a day-offset, otherwise the source datetime passed through
#    normalised to UTC. None for any malformed input.
#
# 2. ``normalize_workshop_string`` trims + collapses whitespace + drops empty.
#    Backends ship workshop strings with stray double-spaces (city-zip
#    template glue) and trailing newlines (HTML scraper provenance). Pure
#    str.strip() leaves the internal mess; explicit collapsing keeps the
#    sensor state predictable.
# ─────────────────────────────────────────────────────────────────────────────


def days_or_date_to_iso(value: Any) -> str | None:
    """Convert backend service-due value to ISO 8601 UTC string.

    Accepts:
      - int / float / numeric str  → today + N days at 00:00 UTC
      - ISO 8601 date / datetime str → normalised to UTC ISO 8601
      - EU dd.mm.yyyy str → midnight UTC ISO 8601

    Returns None for None / empty / malformed inputs. Never raises.

    Used by the brake-service parsers (v2.8.0) so a HA TIMESTAMP sensor
    can render the value as a relative date regardless of which shape
    the brand backend happens to ship.
    """
    if value is None:
        return None
    # Numeric (int / float / bool) — treat as day offset from today.
    if isinstance(value, bool):
        # Booleans are int subclass — guard against True/False being
        # interpreted as 1/0 day offsets, which is meaningless here.
        return None
    if isinstance(value, (int, float)):
        try:
            days = int(value)
        except (OverflowError, ValueError):
            return None
        if days < -36500 or days > 36500:
            # ~100y sanity bound — backend ships nonsense ints during
            # error-envelope conditions (-2147483648 etc).
            return None
        anchor = datetime.now(tz=timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0,
        )
        from datetime import timedelta  # noqa: PLC0415
        return (anchor + timedelta(days=days)).isoformat()
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        # Numeric string — recurse into the int branch.
        try:
            as_int = int(stripped)
        except ValueError:
            pass
        else:
            return days_or_date_to_iso(as_int)
        # EU dd.mm.yyyy (legacy OLA + dealer-portal exports).
        if "." in stripped and "/" not in stripped and len(stripped) <= 10:
            parts = stripped.split(".")
            if len(parts) == 3 and all(p.isdigit() for p in parts):
                day_s, month_s, year_s = parts
                try:
                    dt = datetime(
                        int(year_s), int(month_s), int(day_s),
                        tzinfo=timezone.utc,
                    )
                except ValueError:
                    return None
                return dt.isoformat()
        # ISO 8601 — accept "YYYY-MM-DD" or full datetime, with
        # optional trailing Z. fromisoformat in Python 3.10 cannot
        # parse "Z" directly, so swap to "+00:00" defensively.
        candidate = stripped.replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(candidate)
        except ValueError:
            return None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.isoformat()
    return None


def normalize_workshop_string(value: Any) -> str | None:
    """Trim + collapse whitespace + drop empty strings.

    Backends ship workshop strings with stray double-spaces and
    trailing newlines depending on whether the upstream is a phone-
    number field (Skoda mysmob), a multi-line concatenated address
    (OLA dealer-card), or an HTML-scraped portal label. The HA state
    machine renders the value verbatim, so collapse here before the
    user ever sees it.

    Returns None when the input is None / not a string / empty after
    normalisation.
    """
    if not isinstance(value, str):
        return None
    cleaned = " ".join(value.split())
    return cleaned or None


def compose_workshop_address(parts: Any) -> str | None:
    """Compose a single-line address from a dict of address parts.

    Accepts the typical Skoda / CARIAD-BFF / OLA shapes:
      {"street": "...", "houseNumber": "...", "postalCode": "...",
       "city": "...", "country": "..."}

    Returns a comma-joined string with whitespace normalised, or None
    when no string parts are present. Defensive: any non-dict input
    (incl. None) returns None.
    """
    if not isinstance(parts, dict):
        return None
    # Preferred field: a backend-provided full string overrides
    # composition (Skoda v3 ships ``formattedAddress`` on some
    # variants since 2026-Q2).
    full = parts.get("formattedAddress") or parts.get("formatted")
    if isinstance(full, str) and full.strip():
        return normalize_workshop_string(full)
    street = parts.get("street") or parts.get("streetName") or ""
    house = parts.get("houseNumber") or parts.get("number") or ""
    line1 = f"{street} {house}".strip() if street or house else ""
    zip_code = parts.get("postalCode") or parts.get("zip") or ""
    city = parts.get("city") or parts.get("town") or ""
    line2 = f"{zip_code} {city}".strip() if zip_code or city else ""
    country = parts.get("country") or parts.get("countryCode") or ""
    components = [c for c in (line1, line2, country) if isinstance(c, str) and c.strip()]
    if not components:
        return None
    return normalize_workshop_string(", ".join(components))


def workshop_phone_from_contact(contact: Any) -> str | None:
    """Extract a phone number from a contact dict.

    Accepts the typical shapes:
      {"phone": "..."}
      {"phoneNumber": "..."}
      {"telephone": "..."}
      {"phones": ["..."]}

    Returns the first non-empty string found, with whitespace
    normalised. None on miss.
    """
    if not isinstance(contact, dict):
        return None
    for key in ("phone", "phoneNumber", "telephone", "tel"):
        candidate = contact.get(key)
        if isinstance(candidate, str) and candidate.strip():
            return normalize_workshop_string(candidate)
    phones = contact.get("phones")
    if isinstance(phones, list):
        for entry in phones:
            if isinstance(entry, str) and entry.strip():
                return normalize_workshop_string(entry)
            if isinstance(entry, dict):
                num = entry.get("number") or entry.get("value")
                if isinstance(num, str) and num.strip():
                    return normalize_workshop_string(num)
    return None
