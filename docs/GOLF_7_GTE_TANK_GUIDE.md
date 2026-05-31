# Golf 7 GTE Tank-Level Test-Guide (v1.25.0+)

> **Wer das hier liest:** Owner eines VW Golf 7 GTE PHEV (2014–2020) oder eines anderen pre-PPE/MEB Hybriden (Passat GTE B7/B8, A3 e-tron, Q5 hybrid 2014+, etc.) bei dem die WeConnect App **kein Tank-% anzeigt** UND VAG Connect den `fuel_level` Sensor leer lässt.

## Was v1.25.0 geändert hat

VAG Connect v1.25.0 PR-G (Sprint C) bringt einen **MBB VSR Phase 2 read-side Fallback** für genau diese Vehicle-Klasse. Der Hintergrund:

- **Cariad-BFF Gateway** (`emea.bff.cariad.digital`) — die "moderne" API die wir primär nutzen — gibt für Golf 7 GTE bei `fuelStatus.rangeStatus` einen `{error: ...}` Block zurück. Kein Tank-%, keine combustion-range. Das ist das gleiche Problem das die WeConnect App selbst hat.
- **MBB Legacy Stack** (`fal-3a.prd.eu.dp.vwg-connect.com`, etc.) — die ALTE API die das Auto eigentlich seit Car-Net-Zeiten spricht — publisht das Feld `0x030103000A` (TANK_LEVEL_IN_PERCENTAGE) **immer noch**. Die App hat den Switch zu Cariad gemacht und verloren auf Hybriden.
- v1.25.0 fügt einen **defensiven Fallback** hinzu: wenn Cariad-BFF leer UND VIN bekanntermaßen MBB-backed → GET die legacy `/fs-car/bs/vsr/v1/.../status` und parse das Field.

## Voraussetzungen

| | |
|---|---|
| **Integration-Version** | v1.25.0 oder neuer |
| **Brand** | Volkswagen EU oder Audi (CARIAD-BFF brands) |
| **Vehicle-Era** | MIB1 / MIB2 / MIB3 mit Connect+ — typisch 2014–2020 |
| **Subscription** | aktiver We Connect (Plus) Vertrag — ohne kommt KEIN backend response |
| **Auth-Token** | gültig (HACS-Update überlebt seit v1.19.2) |

## Schritt-für-Schritt

### 1. Update auf v1.25.0

**HACS:** Settings → HACS → VAG Connect → Update auf v1.25.0 → **HA neu starten**.

Verify in den Settings → Devices & Services → VAG Connect → ⋮ → Über die Integration: **Version 1.25.0** (oder neuer).

### 2. Logs vorbereiten

Settings → System → Logs → ⋮ → Filter:

```
Logger: custom_components.vag_connect
Level: DEBUG
```

Save + scroll-to-end aktiv lassen.

### 3. Wake-Service triggern

Settings → Devices & Services → VAG Connect → DEVICE-Card vom Golf 7 GTE → **Wake Vehicle** Button drücken (oder via `vag_connect.wake_vehicle` Service mit der VIN).

### 4. Was du in den Logs sehen solltest

**Erfolg-Variante A** — VIN war schon vorher als MBB-backed markiert (Fall A4 B9 / Q5 2021 / Golf 7 die schon mal in v1.21.0 wake-fallback gelaufen sind):

```
INFO MBB VSR Phase 2: filled fuel_level=60% for ***xxxxxx (Cariad-BFF was empty)
INFO MBB VSR Phase 2: filled combustion_range_km=450 for ***xxxxxx
```

**Erfolg-Variante B** — VIN wird ERST jetzt als MBB-backed klassifiziert:

```
INFO VAG wake: Cariad-wrapper-404 for vin ***xxxxxx — marking as MBB-backed and retrying via legacy path
DEBUG MBB wake POST → https://msg.volkswagen.de/fs-car/bs/vsr/v1/VW/DE/vehicles/***xxxxxx/requests
```

→ Dann **10 Minuten warten** auf nächsten automatischen Coordinator-Poll, dann sollten die "MBB VSR Phase 2: filled" Lines erscheinen.

### 5. HA-Sensor checken

Settings → Devices & Services → VAG Connect → DEVICE Golf 7 GTE → **Sensoren-Liste**:

- `sensor.<dein_vin_slug>_fuel_level` — sollte jetzt einen Wert haben (z.B. `60` mit Unit `%`)
- `sensor.<dein_vin_slug>_combustion_range_km` — sollte zugehörige Range haben
- `sensor.<dein_vin_slug>_total_range_km` (PHEV) — Summe aus electric + combustion

## Wenn nach 24h immer noch `unknown`

### Diagnose 1: Logs lesen

Filter `MBB VSR` in den Logs:

| Log-Line | Bedeutung |
|---|---|
| `MBB VSR fetch failed for ***xxxxxx: ...` | HTTP-Request scheiterte. Häufig: 401 (Token), 403 (no Subscription), 404 (vehicle nicht in MBB registry), 500 (Backend down) |
| `MBB VSR Phase 2: filled fuel_level=...` | ✅ Funktioniert — Sensor sollte Wert haben |
| Nichts | VIN wurde noch nicht als MBB-backed markiert. Trigger Wake (Schritt 3) noch mal |

### Diagnose 2: Diagnostics Export

Settings → Devices & Services → VAG Connect → Configuration-Card → **Download Diagnostics**.

Im JSON file nach `mbb_backend_cache` suchen — sollte deine Golf-VIN als `"mbb"` markiert sein. Wenn `"cariad"` → Wake hat noch nicht den wrapper-404 erkannt, möglicherweise echtes Cariad-vehicle (selten bei Golf 7).

### Diagnose 3: Worst Case — MBB liefert das Feld nicht

Wenn HTTP success aber field absent → das Auto publisht `0x030103000A` einfach nicht via OCU. Mögliche Gründe:
- Sehr frühe Golf 7 GTE Firmware (vor 2016) ohne Tank-Telemetrie
- OCU-Defekt / SIM-Probleme
- Connect-Subscription ist auf einem reduzierten Tier

**Alternative-Wege wenn MBB tot ist:**
1. **OBD-II Dongle** (OBDLink MX+ ~80€): HA `obd` Integration → PID `0x2F` (fuel level). 100% zuverlässig weil bypasst die OCU komplett.
2. **CarConnectivity-connector-volkswagen** ([upstream](https://github.com/upstream/cc-vw)): debug-log dump dort posten — Till maintains die kanonische "what does this VIN actually publish" reverse-engineering ledger.
3. **EU Data Act portal** (live seit Sep 2025): Cariad muss dir auf Anfrage CSV-Export deiner raw vehicle data geben. Manuell alle paar Wochen, kein real-time API.

## Dem Maintainer melden (so wird's noch besser)

**Egal welches Ergebnis** (success oder failure) — bitte unter [Issue #160](https://github.com/its-me-prash/vag-connect-ha/issues/160) kommentieren mit:

```
Vehicle: Golf 7 GTE
Year: 20XX
Firmware: <wenn bekannt — siehe sensor.software_version>
HA: 2026.X.X
VAG Connect: v1.25.0
Subscription: We Connect Plus aktiv (ja/nein)
Result: ✅ tank_pct gefüllt mit 60% nach 12min wait
        ODER: ❌ blieb unknown — Log-Auszug:
              MBB VSR fetch failed for ***xxxxxx: APIError 404 ...
```

→ Mit ~3 erfolgreichen Reports können wir Phase 2 **write-side** (lock/climate/charger MBB fallback) auch shippen, was die anderen Audi-A4-B9 / Q5-2021 user-reports von Mai 2026 strukturell schließt.

## Weiterführend

- v1.21.0 Phase 1 (wake-side MBB fallback): commit `f247d2d`
- v1.25.0 PR-G (read-side MBB VSR Phase 2): PR [#172](https://github.com/its-me-prash/vag-connect-ha/pull/172), commit `9fd79f2`
- MBB endpoint-catalog reference: `cariad/_mbb.py` module docstring + `upstream/upstream audi_models.py` legacy IDS table
- Golf 7 GTE Range fix (PHEV detection) v1.11.1: closed [#96](https://github.com/its-me-prash/vag-connect-ha/issues/96)
