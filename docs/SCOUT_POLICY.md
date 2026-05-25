# Scout Policy — handling Vehicle Data Scout reports

> **Effective**: v2.4.1+ (2026-05-25)
>
> **Authority**: this document is the canonical rule. Pull-requests
> touching `_unexpected_keys.py` MUST follow it.

---

## TL;DR

When the Vehicle Data Scout reports a new field, the response is:

1. **Parse it** into a dataclass field (`models.py`)
2. **Silence it** by adding the path to `EXPECTED_KEYS`
3. **Surface it** as a sensor entity (usually `entity_registry_enabled_default=False`)
4. **Cross-brand check** — if the same path exists in other brands' API, add the parser there too

**Silencing without parsing is no longer acceptable** for leaf-value fields. Every scout report is free signal about new backend functionality, and silencing-only wastes potential entities/diagnostics.

---

## Why this policy exists

Pre-v2.4.1, the project frequently registered new scout-reported fields in `EXPECTED_KEYS` to suppress the Scout from re-firing — but did NOT add a parser. The reasoning was understandable: "this field doesn't look useful yet."

That reasoning turned out wrong in retrospect. Several historically-silenced fields became useful when:
- A user asked "where is X?" and the answer was "we silence X but don't read it"
- A backend evolution made a previously-noisy field meaningful
- A power-user wanted to build automations on a "diagnostic" field

Plus: parsing is cheap. A dataclass field + a sensor description is ~5 LoC. The future cost of NOT parsing (manual re-investigation, missed entities, user disappointment) is much higher.

---

## The rules

### Rule 1: Every silenced leaf path MUST be parsed

A "leaf path" is one whose final segment is a scalar value (string, number, bool) — not a container.

✅ Compliant:
```python
# _unexpected_keys.py
"charging.batteryStatus.value.temp_C",

# api/vw_eu.py
d.battery_temp_c = safe_float(v(raw, "charging", "batteryStatus", "value", "temp_C"))

# models.py
@dataclass
class VehicleData:
    battery_temp_c: float | None = None

# sensor.py
VagSensorDescription(
    key="battery_temp_c",
    device_class=SensorDeviceClass.TEMPERATURE,
    native_unit_of_measurement=UnitOfTemperature.CELSIUS,
    entity_registry_enabled_default=False,  # opt-in
    ...
)
```

❌ Non-compliant (silencer-only):
```python
# _unexpected_keys.py
"charging.batteryStatus.value.temp_C",
# (nothing in vw_eu.py — gap)
```

### Rule 2: Containers and timestamps are exempt

| Pattern | Why exempt | Action |
|---|---|---|
| `*.carCapturedTimestamp` | Universal per-endpoint timestamp, consolidated into the `last_updated_at` field on the coordinator | Comment: `# T3 — timestamp, covered by last_updated_at` |
| `*.value` (alone) | Container wrapper for the actual leaves | Comment: `# T4 — container, parsed via .value.{leaf}` |
| `*.error` / `*.error.*` | Backend error envelope, parser ignores cleanly | Comment: `# T4 — defensive .error wrapper, no leaf value` |
| Endpoint root names like `selectivestatus`, `parkingposition`, `mycar` | Endpoint declarations, not field paths | Comment: `# T4 — endpoint root, not a leaf` |

### Rule 3: Unit-variant duplicates are exempt

When the backend ships the same value in multiple units (e.g. `temperatureOutside_K` alongside `temperatureOutside_C`), we parse ONE canonical form and use HA's `SensorDeviceClass` for unit conversion at display-time.

✅ Compliant exemption:
```python
# _unexpected_keys.py
"measurements.temperatureOutsideStatus.value.temperatureOutside_C",
# T2 exempt — Kelvin variant below is redundant; we parse Celsius and let
# SensorDeviceClass.TEMPERATURE handle K/F display conversion.
"measurements.temperatureOutsideStatus.value.temperatureOutside_K",
```

### Rule 4: Cross-brand expansion

When a scout fires on brand X and the same path likely exists on brand Y (same Cariad-BFF backend = Audi + VW EU; SEAT inherits CUPRA), check the other brand's parser AND silencer. Apply the fix to both.

Brand-vererbung pairs (no separate work needed):
- `EXPECTED_KEYS["audi"] = EXPECTED_KEYS["volkswagen"]` (auto-inheritance)
- `EXPECTED_KEYS["seat"] = EXPECTED_KEYS["cupra"]` (auto-inheritance)

Manual cross-brand expansion needed for:
- VW EU ↔ Audi shared parser (`vw_eu.py` parses both — change once)
- Audi → Lambo / Bentley inheritance (`cariad/api/lambo.py`, `bentley.py` extend `audi.py`)
- CUPRA ↔ CUPRA-standalone (`cupra_standalone.py` is a separate variant)

### Rule 5: Entity-enabled-default

New scout-derived entities ship **disabled by default** (`entity_registry_enabled_default=False`) unless:
- The value is **user-actionable** (e.g. "doors open" alarm) → enabled
- The value is part of a **completing-existing-set** (e.g. 4th door binary when we already enable 3) → enabled for consistency
- Otherwise → disabled, user opts in via entity registry

Why: most scout-discovered fields are diagnostic/edge-case. Defaulting them on would flood every user's UI with niche entities they don't need. Power-users find and enable them deliberately.

---

## When you add a new silencer-entry — checklist

Before merging any PR that adds a path to `EXPECTED_KEYS`:

- [ ] Parser exists in the relevant `cariad/api/{brand}.py`
- [ ] Dataclass field declared in `cariad/models.py`
- [ ] Sensor description in `sensor.py` (or `binary_sensor.py` / `time.py` etc.)
- [ ] Entity name in `strings.json` (English-primary per v2.4.1+ convention)
- [ ] Cross-brand check completed (other CARIAD brands, OLA brands)
- [ ] Test added in the corresponding `tests/test_v{XYZ}_*.py`
- [ ] CHANGELOG `[Unreleased]` entry mentions the field

Or — if intentionally exempt — add an inline comment citing the exemption rule from this document:

```python
# T2 exempt — Kelvin variant, parsed as Celsius (see SCOUT_POLICY.md)
"measurements.temperatureOutsideStatus.value.temperatureOutside_K",
```

---

## How this policy is enforced

1. **CI lint script** (planned for v2.5.0): walks `EXPECTED_KEYS`, cross-checks against parser presence, fails on uncommented silencer-only entries
2. **PR-review checklist** (above) — manual reviewer responsibility
3. **`docs/CHANGELOG_TECHNICAL.md`** documents the audit history per release

---

## Migration history

- **Pre-v2.4.1**: silencer-only entries were common. ~67 fields in EXPECTED_KEYS had no corresponding parser.
- **v2.4.1 audit**: classified 67 silenced-only paths into T1-T5 tiers. Added parsers + entities for ~12 T1 (genuinely useful). Documented T2-T5 exemptions inline in `_unexpected_keys.py`.
- **v2.4.1+**: all new silencer-entries must follow this policy. PR-review enforces.
- **v2.5.0 (planned)**: automated CI lint that fails on uncommented silencer-only entries.

---

## Why "always parse" is the right default

> "The cheapest entity is the one you don't have to add later when a user asks for it."
>
> — derived from 2026-05 community FB-group experience

Every scout report represents one tester's vehicle sending a field that the integration's parser didn't recognize. That tester noticed only because our Scout flagged it. Adding parser + entity at scout-time is a 5-minute investment that converts a "noise suppression" into a "potential power-user diagnostic". The alternative — silencing only — burns the signal and forces a re-investigation if the field ever becomes interesting.

The integration treats scout-reports as **first-class API discoveries**, not as nuisance reports to suppress.
