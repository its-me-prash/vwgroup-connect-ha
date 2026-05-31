# MBB Legacy Bruno Collection — Test-Anleitung

Verifikation der MBB-Endpoints (pre-Cariad VW/Audi/Skoda/SEAT) für **Golf 7 GTE** und alle anderen MIB2-Ära Fahrzeuge.

## Was ist drin

- **18 Endpoint-Files** (auth → discovery → read → write → SPIN)
- **1 Negative-Test** (Health-Check)
- **2 Environment-Files** (Template committed + Local gitignored)

## Setup (5 Min)

### 1. Bruno installieren

Falls noch nicht: <https://www.usebruno.com/downloads> — Open Source, Desktop-App, kein Cloud-Account nötig.

### 2. Collection in Bruno öffnen

`File → Open Collection` → wähle den Ordner `tests/bruno/mbb_legacy/`.

### 3. Local-Environment anlegen

```bash
cp environments/mbb.template.bru environments/mbb.local.bru
```

Dann in Bruno **Environment-Selector oben rechts → "mbb.local"** wählen.

### 4. Local-Werte ausfüllen

In Bruno auf Environment-Icon (oben rechts) klicken, dann `mbb.local` editieren:

| Variable | Wert | Wo herkriegen? |
|---|---|---|
| `vin` | `WVWZZZAUZFW805377` | Dein Golf 7 GTE VIN |
| `brand` | `VW` | Festwert (VW / Audi / Skoda) |
| `country` | `DE` / `CH` | Dein Country |
| `idk_id_token` | aus HA-Logs (siehe unten) | wird gleich erklärt |
| `vw_access_token` | bleibt leer — füllst du nach `01` selbst aus | — |
| `vw_refresh_token` | bleibt leer | — |
| `x_client_id` | siehe unten | — |
| `spin` | dein 4-stelliger Auto-PIN | nur falls Lock/Unlock test |

### 5. IDK id_token holen — der einfache Weg (Python-Helper)

Im Repo gibt es `scripts/get_idk_token.py`. Der nutzt EXAKT den selben OAuth-Flow
wie deine HA-Integration. Du gibst Email + Password ein, kriegst `id_token`
direkt im Terminal — fertig, kein HA-Detour nötig.

```bash
cd "C:\Users\The Balan's Empire\vag-connect-ha"
python scripts/get_idk_token.py --brand vw --bruno
```

Du wirst gefragt:
```
VW account email: deine@email.de
VW account password: ********    (nicht sichtbar — getpass)
```

Output:
```
============================================================
BRUNO mbb.local.bru — copy/paste these lines:
============================================================
  idk_id_token: eyJhbGciOiJSUzI1NiIs...
  vw_access_token: eyJhbGciOiJSUzI1Ni...
  vw_refresh_token: 6f8a3c2d-...
```

→ die 3 Zeilen kopierst du DIREKT in `mbb.local.bru` (überschreibe die
`PASTE_..._HERE` Platzhalter).

**Andere Brands:**
```bash
python scripts/get_idk_token.py --brand audi --bruno
python scripts/get_idk_token.py --brand skoda --bruno
python scripts/get_idk_token.py --brand seat --bruno
python scripts/get_idk_token.py --brand cupra --bruno
```

**MFA aktiv?**
```bash
python scripts/get_idk_token.py --brand vw --mfa 123456 --bruno
```

⚠️ **id_token läuft nach ~1h ab**. Wenn Bruno-`01` 401 gibt → einfach
`get_idk_token.py` nochmal laufen lassen, neuen Wert in `mbb.local.bru`.

**Sicherheit:**
- Password wird via `getpass` abgefragt — niemals echo'd, niemals in History
- Wenn du das in Bash-History haben willst: `--email deine@email.de` ist OK,
  Password trotzdem nie als Argument (würde in `ps`/History landen)
- Pipe-Mode für CI: `echo 'pw' | python scripts/get_idk_token.py --silent --email me@me.de`

**Voraussetzung:**
- Python 3.11+ + `aiohttp` installiert (`pip install aiohttp`)
- Wenn schon HA läuft + die Integration funktioniert → Python-Setup hast du eh schon

### 6. X-Client-Id (zwei Wege)

**Easy:** Aus upstream hardcoded copy (battle-tested):

```
VW Apps:   77869e21-e30a-4a92-b016-48ab7d3db1d8
Audi Apps: 09b6cbec-cd19-4589-82fd-363dfa8c24da@apps_vw-dilab_com
```

**Sauber (für Production):** Selbst registrieren via `/mbbcoauth/mobile/register/v1`. Schicke ich dir als 20er .bru wenn nötig — aber zum Testen reicht hardcoded.

## Test-Reihenfolge — STRIKT von oben nach unten

### 🔴 Stufe 1 — Auth (KRITISCH)

```
01_POST_token_exchange    → 200 mit access_token + refresh_token
                          → wenn 401: stop, MBB akzeptiert deinen Account nicht
                          → wenn connection refused: MBB tot, Plan canceln
```

✅ Bei Erfolg: kopiere `access_token` aus Response in `vw_access_token`,
`refresh_token` in `vw_refresh_token`.

### 🟡 Stufe 2 — Discovery (Funktioniert dein Account?)

```
03_GET_homeRegion        → 200 mit baseUri.content
                          → Wenn != "https://msg.volkswagen.de" → home_region updaten

04_GET_operationList     → 200 mit serviceInfo[]
                          → SCAN: ist rbatterycharge_v1 dabei? → PHEV bestätigt
                          → ist statusreport_v1 enabled? → VSR funktioniert

05_GET_vehicles_list     → 200 mit deine VIN(s) in userVehicles.vehicle[]
                          → Wenn LEER: dein Account hat keine MBB-Autos
```

### 🟢 Stufe 3 — Read (alle Daten holen)

```
06_GET_vehicle_status   → 200 mit StoredVehicleDataResponse
                          → SCAN: 0x030103000A (Tank %), 0x030103000D (SoC %)
                          → wenn 502/503: probiere zuerst 11_POST_vsr_request

07_GET_charger          → 200 mit charger.status.batteryStatusData.stateOfChargeInPercent
                          → SOLL: dein aktueller GTE-Lade-State
08_GET_climater         → 200 mit climater.status.temperatureStatusData.outdoorTemperature
09_GET_tripdata_short   → 200 mit tripData.tripStatistics[]
10_GET_position         → 200 mit findCarResponse.Position.carCoordinate
                          → Oder 204 wenn Auto AKTUELL fährt (normal)
18_GET_departuretimer   → 200 mit timer.timersAndProfiles
```

### 🟠 Stufe 4 — Write OHNE SPIN (Vorsicht — echte Aktionen am Auto!)

```
11_POST_vsr_request     → 200/202 mit requestId — DAS IST WAKE
                          → kopiere requestId in env var request_id
16_GET_jobstatus        → polling bis status=request_successful

12_POST_charger_actions → 200/202 — startet/stoppt Laden (PRÜFE AUTO!)
13_POST_climater_start  → 200/202 — startet Klima (HÖRBAR!)
17_POST_honk_flash      → 200/202 — Auto blinkt (NACHBARN!)
```

### 🔴 Stufe 5 — Write MIT SPIN (Lockout-Risiko!)

```
14_GET_spin_challenge   → 200 mit challenge + securityToken (level 1)
                          → MANUELL: berechne SHA-512(spin + challenge)
                          → POST /security-pin-auth-completed mit hash
                          → Bekomme finalen securityToken (level 2)

15_POST_lock_action     → 200/202 — Auto sperrt
                          → 3 Falscheingaben → Account-Lockout!
                          → Erst testen mit RICHTIGER SPIN
```

## Was zu mir reportieren nach jedem Stufen-Block

Damit ich Phase 1 v1.26.3 sauber implementieren kann, brauche ich:

```
Stufe 1 — 01 Token Exchange:
[ ] HTTP Status:
[ ] Response (Body — TOKEN-WERTE schwärzen mit XXX!):

Stufe 2 — 03 + 04 + 05:
[ ] homeRegion baseUri.content:
[ ] operationList: welche serviceIDs sind "Enabled"?
[ ] vehicles_list: deine VINs (kannst du letzten 4 Stellen schwärzen)

Stufe 3 — 06 + 07:
[ ] vehicle_status field 0x030103000A wert (Tank %):
[ ] vehicle_status field 0x030103000D wert (SoC %):
[ ] charger stateOfChargeInPercent:
[ ] charger plugStatusData.plugState:
```

Damit kriege ich:
1. **Bestätigung dass MBB dein Konto akzeptiert**
2. **Bestätigung welche Endpoints für GTE konkret funktionieren**
3. **Realistische Sample-Daten für unsere Test-Suite**

## Risiko-Matrix

| Aktion | Risiko | Mitigation |
|---|---|---|
| 01-10 Read-only Tests | 🟢 None — keine Auto-Aktion | Beruhigt testen |
| 11 VSR Wake | 🟡 zählt gegen 3-wakes/Tag soft-cap | Max 2x/Tag |
| 12 Charger | 🟠 startet Ladevorgang | Nur wenn Plug connected, sonst no-op |
| 13 Climater | 🟠 startet Klima (Strom-Verbrauch) | Plug connected = ok, sonst HV-Battery zieht |
| 17 Honk/Flash | 🟠 Lärm/Lichter | Tagsüber, Eigentum-Parkplatz |
| 15 Lock/Unlock SPIN | 🔴 3 falsche SPIN → Account-Lockout | SPIN 100% sicher wissen vor Test |

## Privacy Reminder

- `mbb.local.bru` ist in `.gitignore` — **wird nicht committed**
- Bruno hat KEINEN automatischen Cloud-Sync (im Gegensatz zu Postman)
- Falls du mir Response-Bodies schickst: **immer Token-Werte schwärzen** (XXX statt echtem Wert)

## Drift-Detection für CI (später)

`99_NEGATIVE_invalid_token.bru` ist der Daily-Health-Check. Wenn das negative-test Format jemals von `gw.error.authentication` abweicht → MBB hat sich geändert → wir müssen Code aktualisieren BEVOR User Bug-Reports schreiben.

In Phase 2 v1.27 wird `scripts/check_bruno_url_drift.py --probe-mbb` daraus einen automatischen Check.
